"""`graphene plan` and `graphene node`: the plan in a terminal, for a person and for an agent alike.

Plain text, never wrapped or cut: an agent reads these lines as its contract, and a person greps them.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import typer

from . import gate as G
from . import plan as P
from . import plan_text as T

# What `graphene` and `graphene plan` say in a repository with nothing planned: paragraph in, tree out.
NO_PLAN = (
    "nothing is planned here yet. Say what you want to your agent, in a paragraph: it proposes the "
    "tree, and you prune it in `graphene watch`. Or `graphene ask '<what you want>'`"
)


def register(cli: typer.Typer, root, open_store, fail):
    out = typer.echo

    def checkout() -> Path:
        """The working tree the caller stands in: a worktree is its own checkout, with one shared plan."""
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        return Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else root()

    def run(operation):
        """One plan operation against the repo's store; a refusal is one plain message and exit 1."""
        with open_store(root()) as store:
            try:
                return operation(store)
            except P.Refused as no:
                fail(str(no), 1)

    def write(what: str, operation):
        """A person's act on the plan's shape: kept for `graphene plan undo`. What git tracks is asked
        before the plan's write lock is taken (``tracked``), never under it: a hook waiting on the
        lock gives up after a quarter of a second, and lets the call through."""
        who = P.caller()

        def go(store):
            with P.undoable(store, who, what):
                return operation(store)

        return run(go)

    def tracked() -> list[str]:
        return P.tracked(checkout())

    def where() -> str:
        return f"  (the plan of {P.where(root())})"

    def said_where() -> None:
        """The last line of every command that changes the plan, the words the screen's top line
        uses: which repository's plan it changed, so a stray `cd` cannot fool anyone."""
        typer.echo(where(), err=True)

    def asked(command: str, option: str, what: str) -> str:
        """An option a person at a terminal may leave out: asked for, in one line. With no terminal
        its absence is refused in one line, in the words of any missing option (`cli.usage`). A
        command typed at `graphene watch`'s `:` runs with the screen's terminal as its stdin and its
        output captured: it is refused too, never left reading keys the screen is waiting for."""
        if sys.stdin.isatty() and sys.stdout.isatty():
            return typer.prompt(what)
        fail(f"{command} needs {option}: {what}", 2)
        raise AssertionError  # unreachable: fail() exits

    def warn_unreachable(ids, files: list[str] | None = None) -> None:
        """A check that names a path no leaf may create and the repo does not have: said now, not
        after a run, as the guess it is. Asked after the act, outside the plan's write lock."""
        files, top = tracked() if files is None else files, checkout()
        with open_store(root()) as store:
            everything = [n for n in P.nodes(store) if n.state not in P.GONE]
            for node in [n for n in everything if n.id in set(ids)]:
                missing = P.unreachable(node, files, top, everything)
                if missing:
                    said = P.unreachable_said(missing)
                    typer.echo(
                        f"warning: {node.id}'s check {said} (`graphene node edit {node.id}`)", err=True
                    )

    def next_lines(store, who: P.Caller, but: str | None = None, shown: bool = False) -> list[str]:
        """What the caller can do now, in one line, read from the plan as it stands at this moment:
        what is ready and its command, or that nothing is; `graphene plan` has the rest (``shown``:
        the plan is printed right above, so it is not pointed at). An agent is told what it may take;
        the person, what `graphene run` would. ``but`` is a node the caller has just handed back: it
        is not sent straight back to it."""
        everything = P.nodes(store)
        rest = "" if shown else " (graphene plan says what each leaf waits on)"
        if os.environ.get("GRAPHENE_NODE") and not who.person:
            return ["next: stop here. `graphene run` started you for one leaf, and it decides what runs next"]
        held = [n for n in everything if n.state == P.RUNNING and holds(n, who)]
        if held:
            n = held[0]
            return [
                f"next: you hold {n.id} ({n.title}). Finish it with `graphene node done {n.id}`, or hand "
                f"it back with `graphene node release {n.id} --why '…'`"
            ]
        if not [n for n in everything if n.state in (P.PROPOSED, P.OPEN, P.RUNNING, P.REVIEW)]:
            return ["next: nothing; every node is done"]
        agents = [n for n in P.ready(everything, P.Caller("agent", False)) if n.id != but]
        mine = [n for n in P.ready(everything, who) if n.id != but]
        if who.person:
            if agents:
                first, more = agents[0], len(agents) - 1
                also = f", and {more} more" if more else ""
                return [f"next: {first.id} ({first.title}) is ready{also}: `graphene run` runs "
                        f"{'them' if more else 'it'}"]  # fmt: skip
            if mine:
                return [f"next: {mine[0].id} ({mine[0].title}) is yours to do"]
            return [f"next: nothing is ready to run{rest}"]
        if mine:
            first, more = mine[0], len(mine) - 1
            also = f", and {more} more" if more else ""
            return [
                f"next: {first.id} ({first.title}) is ready{also}: `graphene node start {first.id}` takes "
                "it, with its contract as it stands now"
            ]
        return [f"next: nothing is ready for you, so you can stop{rest}"]

    def brief(text: str, node_id: str) -> str:
        """A reason as one table cell: the whole of it is in `node show`."""
        text = " ".join(text.split())
        return text if len(text) <= 100 else f"{text[:97]}… (`graphene node show {node_id}` has all of it)"

    def scope_cell(n: P.Node, wide: int = 36) -> str:
        """The scope as one table cell: as many globs as fit, then how many more (`node show` has all)."""
        shown: list[str] = []
        for glob in n.scope:
            if shown and len(", ".join([*shown, glob])) > wide - 9:
                return f"{', '.join(shown)}, +{len(n.scope) - len(shown)} more"
            shown.append(glob)
        return ", ".join(shown)

    def holds(n: P.Node, who: P.Caller) -> bool:
        return n.session_id == who.session_id if who.session_id else n.executor == who.name

    def describe(store, n: P.Node, word: str, by_id: dict[str, P.Node], words: dict, who: P.Caller) -> str:
        """What a leaf's row adds after its state: where it may write, what it waits on, and the
        command for the move that is the person's (accept, sign off)."""
        said = [scope_cell(n)] if n.scope else []
        if word == "running":
            said.append(f"{P.said_by(n.executor)}, since {T.clock(n.started_at)}")
        elif word == "review":
            said.append(f"its check passed: `graphene node signoff {n.id}`")
        elif n.state == P.PROPOSED:
            said += [f"would wait on {', '.join(n.needs)}"] if n.needs else []
            said.append(f"`graphene plan accept {n.id}`")
        elif word == "waiting":
            said.append("waits on " + ", ".join(f"{b.id} ({T.blocker(b, words)})" for b in P.unmet(n, by_id)))
        elif word == "yours" and n.owner != who.name:
            said.append(f"{n.owner}'s")
        elif word == "to fill in":
            said.append(
                f"no scope and no leaves yet: `graphene node split {n.id}`, or `graphene node edit {n.id}`"
            )
        last = (store.node_log(n.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
        if n.state == P.OPEN and last["kind"] == "released":
            said.append(f"handed back: {brief(last['detail'].get('why', ''), n.id)}")
        elif n.state == P.OPEN and last["kind"] == "reopened":
            said.append(f"sent back: {brief(last['detail'].get('note', ''), n.id)}")
        return " · ".join(said)

    FOLD = 12  # lines of tree the plain print shows before finished leaves fold into their sub-goal

    def plan_lines(store, who: P.Caller, everything: bool = False) -> list[str]:
        """The plan as a tree, for a person and an agent alike: what waits on the person first, then
        the goal, then the tree folded to what is still moving. ``everything`` unfolds it."""
        alive = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
        if not alive:
            return [NO_PLAN]
        by_id = {n.id: n for n in alive}
        under = P.kids(alive, drawn=True)  # proposals are drawn where they would go; they bind nothing
        leaves = [n for n in P.leaves(alive) if not n.aside]
        asides = [n for n in alive if n.aside]
        count = {s: sum(1 for n in leaves if n.state == s) for s in (P.RUNNING, P.DONE)}
        proposed = store.meta("goal:proposed")
        lines = (
            [f"the plan: {P.goal(store)}"]
            if P.goal(store)
            else [f"the plan (proposed with the tree, accepted with it): {proposed}"]
            if proposed
            else []
        )
        head = (
            f"{'' if lines else 'the plan: '}{len(leaves)} lea{'f' if len(leaves) == 1 else 'ves'}, "
            f"{count[P.DONE]} done, {count[P.RUNNING]} running"
        )
        if asides:
            head += f" · {len(asides)} made from a prompt"
        if P.paused(store):
            head += " · PAUSED: nothing starts and nothing is enforced"
        stuck = [
            n
            for n in alive
            if n.state == P.OPEN and under.get(n.id) and all(c.state == P.DONE for c in under[n.id])
        ]
        if not P.paused(store) and leaves and count[P.DONE] == len(leaves) and not stuck:
            head += " · finished; `graphene plan archive` puts it away"
        lines.append(head)
        yours = [n for n in alive if n.state == P.REVIEW]
        yours += [  # a proposed subtree is asked about once, at its top
            n
            for n in alive
            if n.state == P.PROPOSED and (n.parent not in by_id or by_id[n.parent].state != P.PROPOSED)
        ]
        back = {n.id for n in alive if P.came_back(store, n)}  # it came back: the next move is the person's
        words = {n.id: P.reads(n, alive, back) for n in alive}  # the words the screen and the text use
        yours += [n for n in alive if words[n.id] == "yours"]  # a person's own leaf, scope or none
        if who.person and (yours or stuck or back):
            seen: list[str] = []
            told = [
                f"{n.id} ({words[n.id]}"
                + (f", with the {len(P.below(n.id, alive))} under it" if under.get(n.id) else "")
                + ")"
                for n in yours
                if n.id not in seen and not seen.append(n.id)
            ]
            told += [f"{n.id} (its leaves are done and its own check fails)" for n in stuck]
            told += [f"{n.id} (came back: `graphene node show {n.id}`)" for n in alive if n.id in back]
            more = (
                f", and {len(told) - 8} more (`graphene plan --all`)"
                if len(told) > 8 and not everything
                else ""
            )
            lines.append("waiting on you: " + ", ".join(told if everything else told[:8]) + more)
        # One row grammar, as on the screen: glyph and title (cut at a word) in one column, the id in the
        # next, the state word in the next, whatever the depth; then what the print adds.
        heads = {n.id: 2 * len(P.above(n, by_id)) + 2 for n in alive}  # the indent, the glyph and a space
        wt = max(min(48, max(heads[n.id] + len(n.title) for n in alive)), max(heads.values()) + 12)
        wid, ww = max(len(n.id) for n in alive), max(len(w) for w in words.values())
        shown = [n for n in alive if not n.aside or n.state != P.DONE]
        fold = not everything and len(shown) > FOLD

        def row(n: P.Node, depth: int) -> str:
            word = words[n.id]
            if under.get(n.id):
                of = sum(1 for c in P.below(n.id, alive) if not under.get(c.id))
                what = f"then `{n.check}`" if n.check and n.state != P.DONE else ""
                what += f" · `graphene plan accept {n.id}`" if n.state == P.PROPOSED else ""
                if n.id in closed:
                    inside = [c for c in P.below(n.id, alive) if c.id in ready_ids]
                    what += f" · {len(inside)} ready" if inside else ""
                    what += f" · {of} leaves folded (`graphene plan --all` unfolds)"
                what = what.removeprefix(" · ")
            else:
                what = describe(store, n, word, by_id, words, who)
            head = f"{'  ' * depth}{P.look(word)[0]} "
            title = f"{head}{T.elide(n.title, wt - len(head))}"
            cells = f"  {title.ljust(wt)}  {n.id.ljust(wid)}  {word.ljust(ww)}"
            return f"{cells}  · {what}" if what else cells.rstrip()

        # Folded, a sub-goal with nothing moving under it (nothing running, in review or proposed) is one
        # line: a plan of sixty leaves just accepted is a dozen lines, not seventy-eight.
        moving = (P.RUNNING, P.REVIEW, P.PROPOSED)
        closed = {
            n.id
            for n in alive
            if fold and under.get(n.id) and not any(c.state in moving for c in P.below(n.id, alive))
        }
        ready_ids = {n.id for n in P.ready(alive)}

        def walk(parent: str | None, depth: int) -> None:
            folded: list[P.Node] = []
            if parent in closed:
                return
            for n in under.get(parent, []):
                if n.aside and n.state == P.DONE and not everything:
                    continue
                if fold and n.state == P.DONE:
                    folded.append(n)
                    continue
                lines.append(row(n, depth))
                walk(n.id, depth + 1)
            if folded:
                inside = sum(len(P.below(n.id, alive)) for n in folded)
                lines.append(
                    f"  {'  ' * depth}✓ {len(folded)} done here"
                    + (f" (with {inside} under them)" if inside else "")
                    + f": {T.elide(', '.join(n.id for n in folded), 60)}   (`graphene plan --all` unfolds)"
                )

        walk(None, 0)
        done_asides = [n for n in asides if n.state == P.DONE]
        if done_asides and not everything:
            lines.append(
                f"  ✓ {len(done_asides)} done from a prompt, each with its record "
                f"(`graphene plan --all`; latest: {done_asides[-1].id}, {T.elide(done_asides[-1].title, 40)})"
            )
        try:
            loose = P.unowned(store, checkout()) if not P.nodes(store, (P.RUNNING,)) else []
        except P.Refused:
            loose = []  # not a checkout git can read: nothing to compare
        if loose:
            listed = ", ".join(loose[:8]) + (f" and {len(loose) - 8} more" if len(loose) > 8 else "")
            lines.append(
                f"uncommitted changes no node made: {listed}  (yours as they stand? `graphene plan ack`, "
                "or commit them; else put them back)"
            )
        if not who.person:
            lines += next_lines(store, who, shown=True)
        return lines

    def print_plan(store, who: P.Caller, everything: bool = False) -> None:
        for line in plan_lines(store, who, everything):
            out(line)

    def value(v) -> str:
        """A logged value as a person reads it: a list is its items, nothing is "none", not a repr."""
        if isinstance(v, list | tuple):
            return ", ".join(value(x) for x in v) or "none"
        if v is None or v == "":
            return "none"
        if isinstance(v, bool):
            return "yes" if v else "no"
        return " ".join(str(v).split())

    def one_row(store, n: P.Node, depth: int = 0) -> str:
        """A node the command just made or moved, in the row grammar `graphene plan` and the screen
        use: glyph, title, id, the word its state reads as."""
        everything = P.nodes(store)
        word = P.reads(P.get(store, n.id), everything)
        return f"{'  ' * depth}{P.look(word)[0]} {n.title}  {n.id}  {word}"

    def log_line(e: dict, with_node: int = 0, who_wide: int = 16) -> str:
        detail = e["detail"]
        changed = detail.get("changed")  # an edit's field changes (a dict), or an ending's paths (a list)
        fields = changed.items() if isinstance(changed, dict) else ()
        said = (
            (value(detail["why"]) if detail.get("why") else "")
            or (
                f"{detail['note']}  (it said: {detail['was']})"
                if detail.get("was") and detail.get("note")
                else ""
            )
            or (value(detail["note"]) if detail.get("note") else "")
            or detail.get("override")
            or (f"by their prompt in the session: {detail.get('prompt', '')!r}" if detail.get("by") else "")
            or detail.get("path")
            or ", ".join(detail.get("outside") or detail.get("paths") or detail.get("unowned") or [])
            or "; ".join(f"{k}: {value(a)} → {value(b)}" for k, (a, b) in fields)
            or (f"changed: {', '.join(changed)}" if isinstance(changed, list) and changed else "")
            or detail.get("command")
            or ""
        )
        who = e["actor"] or (f"claude:{e['session_id'][:8]}" if e["session_id"] else "")
        node = f"{e['node_id'].ljust(with_node)}  " if with_node else ""
        return (
            f"  {e['timestamp'][:19]}Z  {node}{e['kind'].ljust(12)}  {who.ljust(who_wide)}  {said}".rstrip()
        )

    # -- graphene plan ----------------------------------------------------------------------------

    plan_cli = typer.Typer(
        help="The shared plan: what will be done, by whom, inside which paths.", invoke_without_command=True
    )
    cli.add_typer(plan_cli, name="plan")

    @plan_cli.callback()
    def show_plan(
        ctx: typer.Context,
        as_json: bool = typer.Option(False, "--json", help="The plan as JSON."),
        as_text: bool = typer.Option(
            False, "--text", help="The plan as text: the form `plan edit` opens and `propose` reads."
        ),
        everything: bool = typer.Option(False, "--all", help="Unfold the tree: finished work included."),
    ) -> None:
        """Print the plan as a tree: what waits on you, then what is moving. Finished work is folded."""
        if ctx.invoked_subcommand is not None:
            return
        who = P.caller()
        if as_text:
            run(lambda s: out(T.render(s)[0].rstrip("\n")))
            return
        run(lambda s: out(P.to_json(P.nodes(s))) if as_json else print_plan(s, who, everything))

    @plan_cli.command("goal")
    def goal_(text: str = typer.Argument(None, help="Why any of this is being done, in your words.")) -> None:
        """Say (or read) the root of the tree. Every executor is told it, above its own node."""
        if text is None:
            out(run(P.goal) or "no goal yet: `graphene plan goal 'why any of this is being done'`")
            return
        was = run(P.goal)
        write("plan goal", lambda s: P.set_goal(s, text, P.caller()))
        out(f"the plan: {text.strip()}")
        if was:
            out(f"  (it said: {was})")
        said_where()

    @cli.command()
    def watch(
        everything: bool = typer.Option(
            False, "--all", help="With --once: unfold the tree, finished work too."
        ),
        every: float = typer.Option(1.0, "--every", help="Seconds between looks at the plan."),
        once: bool = typer.Option(
            False, "--once", help="Print the plan once, with what just happened, and leave."
        ),
    ) -> None:
        """The plan on one screen, live, with vim keys: the tree, the node under the cursor, the
        executors as they work. Every key is a command you could type (the bottom line says which);
        `?` lists them, `q` leaves. `--once` prints the plan instead, for a script or a terminal you
        do not want to give up."""
        who = P.caller()
        if once or not sys.stdout.isatty():
            with open_store(root()) as store:
                lines = plan_lines(store, who, everything)
                recent = store.node_log()[-6:]
            for line in lines:
                out(line)
            if recent:
                out("\njust now")
                for e in recent:
                    out(log_line(e, with_node=8))
            return
        try:
            from .tui import run as watch_tui
        except ImportError as missing:  # an install from before the screen: code new, dependencies old
            fail(
                f"graphene watch needs {missing.name or 'textual'}, which this install lacks\n"
                "  `uv tool install --force git+https://github.com/Alex-lop/Graphene` (`--editable .` in a "
                "checkout); `graphene watch --once` prints the plan meanwhile",
                1,
            )

        r = root()
        watch_tui(r, lambda: open_store(r), every)

    @plan_cli.command()
    def propose(
        file: str = typer.Argument(..., help="A file of the plan's text; '-' reads it from a pipe."),
    ) -> None:
        """Add a tree, in the text `graphene plan --text` prints. From an agent every line is a
        proposal, which nobody can start until a person accepts it; a line with the [id] of a node
        already in the plan is where the new lines under it go. JSON ({"nodes": [...]}) is read too.

        \b
        graphene plan propose - <<'EOF'
        goal: the aim in one sentence
        - a sub-goal  [short-id]
          - a leaf: one piece of work  [leaf-id]
              what it should achieve, in a line or two
              scope: src/pdf/**, tests/pdf/**
              check: pytest tests/pdf -q
              needs: other-leaf-id
        EOF"""
        if file == "-" and sys.stdin.isatty():
            fail(
                "`graphene plan propose -` reads a pipe, and nothing is piped here\n"
                "  graphene plan propose - <<'EOF' … EOF; at a terminal, `graphene plan edit`",
                1,
            )
        try:
            text = sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"cannot read {file}: {exc.strerror or exc}", 1)
        who = P.caller()
        files = P.tracked(checkout())

        def as_json(store) -> list[P.Node]:
            try:
                raw = json.loads(text)
            except ValueError as exc:
                raise P.Refused(f"cannot read {file} as JSON: {exc}") from None
            items = raw.get("nodes") if isinstance(raw, dict) else raw
            if not isinstance(items, list) or not items:
                raise P.Refused('expected {"nodes": [ … ]} with at least one node')
            added = P.propose(store, items, who, files=files)
            by_id = {n.id: n for n in P.nodes(store)}
            for n in added:
                out(one_row(store, n, len(P.above(n, by_id))))
            return added

        def as_text(store) -> list[P.Node]:
            before = {n.id for n in P.nodes(store)}
            for line in T.apply(store, text, who, None, files=files):
                out(line)
            return [n for n in P.nodes(store) if n.id not in before]

        def go(store):
            added = as_json(store) if text.lstrip().startswith(("{", "[")) else as_text(store)
            if not who.person and added:
                out(
                    G.one_line_ask(store, added, who)  # one leaf for the person's own ask is theirs at once
                    or f"{len(added)} proposed: nobody can start {'it' if len(added) == 1 else 'them'} until "
                    "the person accepts, in `graphene watch`. Tell them the tree is ready, and stop"
                )
            return [n.id for n in added]

        warn_unreachable(write("plan propose", go) or [], files)
        said_where()

    @plan_cli.command("edit")
    def edit_(
        node_id: str = typer.Argument(None, help="A subtree: this node and what is under it. Default: all."),
    ) -> None:
        """Open the plan (or a subtree) as text in your editor ($VISUAL, $EDITOR, else vi). Add a line,
        move one, delete one, change a scope, turn a "?" into "-" to accept; save and quit, and
        Graphene applies the difference, all of it or none. A line it cannot read is refused by its
        number and nothing is applied."""
        edit_in_editor(node_id, alone=False)

    @plan_cli.command()
    def undo() -> None:
        """Put back your last act on the plan (an edit, an add, a drop, an acceptance, a saved text)."""
        what = run(lambda s: P.undo(s, P.caller()))
        out(f"undid: {what}")
        said_where()

    def edit_in_editor(node_id: str | None, alone: bool) -> None:
        who = P.caller()
        if not who.person:
            fail("an editor is for the person at a terminal; an agent proposes: `graphene plan propose -`", 1)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        try:
            name = Path(shlex.split(editor)[0]).name
        except (ValueError, IndexError):
            name = editor
        if not sys.stdin.isatty() and name in ("vi", "vim", "nvim", "nano", "emacs", "micro", "hx", "kak"):
            fail(f"{name} needs a terminal, and there is none here; run this in one, or set $EDITOR", 1)
        kept = sorted((root() / ".graphene" / "edits").glob("*.txt"))
        path = T.edit_path(root(), node_id)
        try:
            said = T.edit_loop(
                lambda: open_store(root()), node_id, alone, who, P.tracked(checkout()), path,
                where().strip(), T.run_editor, interactive=sys.stdin.isatty(),
            )  # fmt: skip
        except P.Refused as no:
            fail(str(no), 1)
        for line in said or ["nothing changed"]:
            out(line)
        if kept:
            typer.echo(
                f"an edit you did not finish is kept in {kept[-1]}"
                + (f" (and {len(kept) - 1} before it)" if len(kept) > 1 else ""),
                err=True,
            )
        if said:
            with open_store(root()) as store:
                ids = [i for i in said.ids if store.node_row(i)]
            warn_unreachable(ids)
            said_where()

    @plan_cli.command()
    def accept(ids: list[str] = typer.Argument(None, help="Node ids; none means every proposal.")) -> None:
        """Accept proposals into the plan, and say what an unattended run will and will not reach."""

        def go(store):
            by_id = {n.id: n for n in P.nodes(store)}
            goal_was = P.goal(store)
            accepted = P.accept(store, ids or [], P.caller())
            if accepted:  # first, in a line: what the screen's bottom line gives of it
                out(f"accepted {', '.join(n.id for n in accepted)}")
            for n in accepted:
                out(one_row(store, n, len(P.above(n, by_id))))
            if P.goal(store) != goal_was:
                out(f"the plan: {P.goal(store)}  (the planner's sentence, accepted with its tree)")
            runs, waits = P.forecast(P.nodes(store))
            out("left alone, agents can reach: " + (", ".join(n.id for n in runs) or "nothing"))
            for n, why in waits:
                out(f"  {n.id} will wait: {'; '.join(why)}")
            return [n.id for n in accepted]

        warn_unreachable(write("plan accept" + (f" {' '.join(ids)}" if ids else ""), go) or [])
        said_where()

    @plan_cli.command("log")
    def log_() -> None:
        """Everything that happened on the plan, oldest first; `*` is what belonged to no node."""

        def go(store):
            entries = store.node_log()
            wide = max((len(e["node_id"]) for e in entries), default=1)
            who_wide = max((len(e["actor"] or "") for e in entries), default=16)
            for e in entries:
                out(log_line(e, with_node=wide, who_wide=max(who_wide, 16)))

        run(go)

    @plan_cli.command()
    def record() -> None:
        """The record of the whole plan: every leaf's added up. One leaf's is `graphene node show`."""
        from .node_record import bill, bill_line, rolled_up

        def go(store):
            for line in rolled_up(store, root(), P.leaves(P.nodes(store))):
                out(line.replace("under it", "in the plan"))
            for line in bill_line(bill(store.node_log("*", ("usage",))), "    "):
                out(line.replace("bill:", "the planner's bill:"))

        run(go)

    @plan_cli.command()
    def archive() -> None:
        """Put finished nodes away. With nothing else left, the plan is no longer in force."""
        gone = run(lambda s: P.archive(s, P.caller()))
        out(f"archived {', '.join(n.id for n in gone)}" if gone else "nothing finished to archive")
        said_where()

    @plan_cli.command()
    def ack() -> None:
        """The uncommitted changes in the checkout that no leaf made are yours, as they stand (committing
        them does the same: a commit is the repository moving, and the plan follows it)."""
        paths = run(lambda s: P.acknowledge(s, checkout(), P.caller()))
        out(f"yours as they stand: {', '.join(paths)}" if paths else "no uncommitted change is left unowned")
        said_where()

    @plan_cli.command()
    def pause() -> None:
        """Suspend the plan: nothing starts, and no write is refused, until `graphene plan resume`."""
        run(lambda s: P.set_paused(s, True, P.caller()))
        out("paused: nothing starts and nothing is enforced until `graphene plan resume`")
        said_where()

    @plan_cli.command()
    def prompts(
        how: str = typer.Argument(
            None, help="'leaf' (default): a prompt you type is a leaf. 'strict': it is not."
        ),
    ) -> None:
        """What a request typed into a session means while the plan is in force. 'leaf': the first
        write of the turn makes a leaf from your prompt, held by that session, and its record says
        what it touched. 'strict': a session that holds no node writes nothing, as in 0.3."""
        if how not in (None, "leaf", "strict"):
            fail(f"graphene plan prompts takes leaf or strict, not {how!r}", 1)

        def go(store):
            if how is not None:
                P._person_only(P.caller(), "changing what a typed prompt means")
                store.set_meta("asides", "off" if how == "strict" else "on")
            return "strict" if store.meta("asides") == "off" else "leaf"

        now = run(go)
        out(
            "strict: a session that holds no node writes nothing; it proposes, and you accept"
            if now == "strict"
            else "leaf: what you type into a session becomes a leaf when the agent first writes for it"
        )
        if how is not None:
            said_where()

    @plan_cli.command()
    def first(
        how: str = typer.Argument(None, help="'on' or 'off'; nothing prints what it is now."),
    ) -> None:
        """Plan first: what you ask for in a session is proposed as a tree before any code, and the
        agent writes nothing until a leaf of it is accepted and taken (a one-line ask is proposed as
        one leaf, which is yours at once). `P` in graphene watch turns it on and off."""
        if how not in (None, "on", "off"):
            fail(f"graphene plan first takes on or off, not {how!r}", 1)
        if how is not None:
            run(lambda s: P.set_plan_first(s, how == "on", P.caller()))
        on = run(P.plan_first)
        out(
            "plan first: on. What you ask for in a session is proposed as a tree before any code"
            if on
            else "plan first: off. What you ask for in a session is done at once, as a leaf of its own"
        )
        if how is not None:
            said_where()

    @plan_cli.command()
    def resume() -> None:
        """Put the plan back in force."""
        run(lambda s: P.set_paused(s, False, P.caller()))
        out("the plan is in force")
        said_where()

    @cli.command("run")
    def run_(
        executor: str = typer.Option(
            None,
            "--with",
            help="The executor: a command that takes a prompt as its last argument. Default: "
            "claude that may edit files and run graphene; e.g. 'codex exec --sandbox workspace-write'.",
        ),
        attempts: int = typer.Option(3, "--attempts", help="How often a refused executor is sent back."),
        node: list[str] = typer.Option(None, "--node", help="Only this node; repeat it."),
        parallel: int = typer.Option(
            1,
            "--parallel",
            help="Leaves at once, each in its own worktree and branch, merged here when clean. "
            "1 (default) works in this checkout and commits nothing.",
        ),
    ) -> None:
        """Run every leaf an agent can reach: one executor per leaf, and Graphene decides what is done.
        The last line says what the run did; `graphene watch` shows it when the run ends."""
        if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
            fail("an executor or a planner does not start runs: through --with a run is any command", 1)
        from .run import named, run_parallel, run_plan, summary

        r = root()
        with open_store(r) as store:
            if not P.nodes(store, (P.OPEN, P.RUNNING)):
                fail("nothing to run: the plan has no open leaf", 1)
            said_where()  # first: a run changes the plan for as long as it goes
            logs = r / ".graphene" / "runs"
            since = len(store.node_log())  # what this run did is what the log says after this
            try:
                if parallel > 1:
                    run_parallel(
                        lambda: open_store(r), r, checkout(), parallel, named(executor),
                        attempts, node or None, out, logs,
                    )  # fmt: skip
                else:
                    run_plan(store, checkout(), named(executor), attempts, node or None, out, logs)
            except P.Refused as no:
                fail(str(no), 1)
            except KeyboardInterrupt:
                out(summary(store, since, stopped=True))
                raise typer.Exit(130) from None
            out(summary(store, since))

    def planner(sentence: str, executor: str | None, about: str | None, split: bool) -> None:
        from .ask import ask, named

        who = P.caller()
        if not who.person:
            fail("asking a planner is the person's: it starts an agent, and spends\n"
                 "  propose the tree yourself: graphene plan propose - <<'EOF' … EOF", 1)  # fmt: skip

        def go(store):
            said = ask(store, checkout(), sentence, named(executor), about, split, out)
            for line in said:
                out(line)
            if said:
                out("prune it: `graphene watch` (y accepts, d drops), or `graphene plan edit`")
            return list(getattr(said, "ids", []))

        proposed = run(go)
        warn_unreachable(proposed or [])
        said_where()

    @cli.command("ask")
    def ask_(
        sentence: str = typer.Argument(..., help="What you want, as you would say it."),
        executor: str = typer.Option(
            None,
            "--with",
            help="The planner, a command taking a prompt last. Default: claude with read-only tools.",
        ),
        about: str = typer.Option(None, "--about", help="A node the question is about (one that came back)."),
    ) -> None:
        """Ask a planner for a proposal: it reads the repo with read-only tools and prints the tree in
        the plan's text, which is added as proposals for you to prune. Nothing runs."""
        planner(sentence, executor, about, False)

    # -- graphene node ----------------------------------------------------------------------------

    node_cli = typer.Typer(help="One node of the plan: shape it, take it, finish it, read its record.")
    cli.add_typer(node_cli, name="node")

    def changes(**given) -> dict:
        found = {k: v for k, v in given.items() if v not in (None, [], ())}
        if "needs" in found:
            found["needs"] = [i for i in found["needs"] if i != "none"]
        return found

    @node_cli.command()
    def add(
        title: str = typer.Argument(..., help="One line: what this node is."),
        scope: list[str] = typer.Option(
            None, "--scope", help="A glob it may touch; repeat it. '!glob' excludes."
        ),
        check: str = typer.Option(
            None, "--check", help="The command that must pass for it to be done. Run with sh, not bash."
        ),
        goal: str = typer.Option(None, "--goal", help="What the work should achieve, in a sentence or two."),
        needs: list[str] = typer.Option(None, "--needs", help="A node it waits on; repeat it."),
        owner: str = typer.Option(None, "--owner", help="'agent' (default), 'me', or a person's name."),
        signoff: bool = typer.Option(False, "--signoff", help="A person must also sign it off."),
        node_id: str = typer.Option(None, "--id", help="An id of your choosing; else n1, n2, …"),
        parent: str = typer.Option(
            None, "--parent", help="The node this one helps achieve. Under a leaf, it splits the leaf."
        ),
    ) -> None:
        """Add a node. From a person it is in the plan at once; from an agent it is a proposal.
        With children to come it needs only a title: `graphene node add 'the API' --id api`, then
        `graphene node add … --parent api`."""
        item = changes(
            title=title,
            scope=scope,
            check=check,
            goal=goal,
            needs=needs,
            owner=owner,
            id=node_id,
            parent=parent,
        )
        item["signoff"] = signoff

        files = tracked()

        def go(store):
            [n] = P.propose(store, [item], P.caller(), files=files)
            out(one_row(store, n))
            return [n.id]

        warn_unreachable(write(f"node add {title!r}", go), files)
        said_where()

    @node_cli.command("set")
    def set_(
        node_id: str = typer.Argument(...),
        title: str = typer.Option(None, "--title"),
        scope: list[str] = typer.Option(None, "--scope", help="Replaces the scope; repeat it."),
        check: str = typer.Option(None, "--check"),
        goal: str = typer.Option(None, "--goal"),
        needs: list[str] = typer.Option(None, "--needs", help="Replaces what it waits on; 'none' clears it."),
        owner: str = typer.Option(None, "--owner", help="'agent', 'me', or a person's name."),
        signoff: bool = typer.Option(None, "--signoff/--no-signoff"),
        parent: str = typer.Option(None, "--parent", help="Move it under another node; 'none' is the top."),
    ) -> None:
        """Change a node's contract (a person only). It binds the very next write, and the next start."""
        edits = changes(title=title, scope=scope, check=check, goal=goal, owner=owner, parent=parent)
        if needs:
            edits["needs"] = [i for i in needs if i != "none"]
        if signoff is not None:
            edits["signoff"] = signoff
        if not edits:
            fail(f"graphene node set {node_id} needs what to change: --title, --scope, --check, --goal, "
                 "--needs, --owner, --signoff or --parent", 1)  # fmt: skip

        files = tracked()

        def go(store):
            before = P.get(store, node_id).rev
            node = P.edit(store, node_id, edits, P.caller(), files=files)
            last = store.node_log(node_id, ("edited",))[-1] if node.rev != before else None
            return node, last

        n, last = write(f"node set {node_id}", go)
        if last is None:
            out(f"{n.id} is unchanged (revision {n.rev})")
            said_where()
            return
        out(f"{n.id} is now revision {n.rev}:")
        for name, (before, after) in last["detail"]["changed"].items():
            out(f"  {name}: {value(before)} → {value(after)}")
        if n.state == P.RUNNING:
            out(f"{n.id} is running on revision {n.told_rev}: its next write is held to the new scope, and "
                "its `done` to the new check")  # fmt: skip
        warn_unreachable([node_id], files)
        said_where()

    @node_cli.command()
    def drop(
        node_ids: list[str] = typer.Argument(..., help="The node; name several to drop them at once."),
    ) -> None:
        """Take a node out of the plan, with everything under it. Dropping a sub-goal's children
        makes it a leaf again: that is how a split is undone. Several are one act, all or none, which
        one `graphene plan undo` puts back; what waits on any of them is asked of them together."""
        who = P.caller()

        def go(store):
            with store.claim():  # an agent's act too is all or none, though only a person's is kept
                everything = P.nodes(store)
                named = [P.get(store, i) for i in node_ids]
                gone = {i for n in named for i in [n.id, *(c.id for c in P.below(n.id, everything))]}
                left = [
                    n
                    for n in everything
                    if n.id not in gone and n.state not in P.GONE and gone & set(n.needs)
                ]
                if left and len(named) > 1:
                    told = "; ".join(
                        f"{n.id} waits on {', '.join(sorted(gone & set(n.needs)))}" for n in left
                    )
                    raise P.Refused(f"{told}; change what it needs first, or drop it too")
                for n in named:
                    if P.get(store, n.id).state not in P.GONE:  # else it went with the one it was under
                        P.drop(store, n.id, who, waiting=len(named) == 1)

        write(f"node drop {' '.join(node_ids)}", go)
        them = "it" if len(node_ids) == 1 else "them"
        out(f"{', '.join(node_ids)} dropped (`graphene plan undo` puts {them} back)")
        said_where()

    @node_cli.command("edit")
    def node_edit(node_id: str = typer.Argument(...)) -> None:
        """Open one node's contract as text in your editor; what you save is applied. A line you add
        under it is a new child; one you add beside it, a sibling."""
        edit_in_editor(node_id, alone=True)

    @node_cli.command()
    def start(node_id: str = typer.Argument(...)) -> None:
        """Take a node and print its contract as it stands now."""

        def go(store):
            n = P.start(store, node_id, P.caller(), checkout())
            out(P.contract(n, P.trail(store, n)))
            for note in P.notes(store, n.id):
                out(f"  sent back with: {note}")

        run(go)
        said_where()

    @node_cli.command()
    def done(
        node_id: str = typer.Argument(None, help="The node; may be left out when you hold exactly one."),
        override: str = typer.Option(None, "--override", help="A person's reason for overruling the gate."),
    ) -> None:
        """Finish a node: Graphene runs its check and asks git what changed. Then says what is next."""
        who = P.caller()

        def go(store):
            target = node_id
            if target is None:
                held = [n for n in P.nodes(store, (P.RUNNING,)) if holds(n, who)]
                if len(held) != 1:
                    them = f"{len(held)} nodes ({', '.join(n.id for n in held)})" if held else "no node"
                    raise P.Refused(f"you hold {them}: `graphene node done <id>` names one")
                target = held[0].id
            n = P.finish(store, target, who, override=override, checkout=checkout())
            how = (
                "overruled by a person" if override is not None
                else "by hand: yours, with no check to run" if not n.scope
                else "check passed, nothing outside its scope"
            )  # fmt: skip
            out(f"{n.id} is {'done' if n.state == P.DONE else 'finished and waits for a sign-off'} ({how})")
            for line in next_lines(store, who):
                out(line)

        run(go)
        said_where()

    @node_cli.command()
    def release(
        node_id: str = typer.Argument(...),
        why: str = typer.Option(
            None, "--why", help="What is in the way; the person reads it. Asked for at a terminal."
        ),
        wants: list[str] = typer.Option(
            None,
            "--wants",
            help="A path outside the scope it would need; repeat it. The person is offered it.",
        ),
    ) -> None:
        """Hand a running node back, saying why. The way out when it cannot be finished as written."""
        who = P.caller()
        if why is None:  # asked for only when there is something to hand back
            state = run(lambda s: P.get(s, node_id).state)
            if state != P.RUNNING:
                fail(f"{node_id} is {state}, not running", 1)
            why = asked(f"graphene node release {node_id}", "--why", "what is in the way")

        def go(store):
            P.release(store, node_id, who, why or "", wants=wants or None)
            out(f"{node_id} handed back: {why}")
            for line in next_lines(store, who, but=node_id):
                out(line)

        run(go)
        said_where()

    @node_cli.command("signoff")
    def signoff_(node_id: str = typer.Argument(...)) -> None:
        """A person's say-so: the node is done."""

        def go(store):
            P.signoff(store, node_id, P.caller(), checkout=checkout())
            return (store.node_log(node_id, ("unlanded",)) or [{"detail": {}}])[-1]["detail"]

        left = run(go)
        out(f"{node_id} is done (signed off)")
        if left.get("branch"):  # the person merged it by hand: its worktree goes, and its branch if merged
            git = ["git", "-C", str(checkout())]
            subprocess.run([*git, "worktree", "remove", "--force", left["worktree"]], capture_output=True)
            gone = subprocess.run([*git, "branch", "-d", left["branch"]], capture_output=True)
            kept = subprocess.run([*git, "rev-parse", "-q", "--verify", left["branch"]], capture_output=True)
            if gone.returncode != 0 and kept.returncode == 0:  # not when it was gone already
                out(
                    f"{left['branch']} is not merged here, so it was kept: "
                    f"`git branch -D {left['branch']}` drops it"
                )
        said_where()

    @node_cli.command()
    def reopen(
        node_id: str = typer.Argument(...),
        note: str = typer.Option(
            None, "--note", help="What is wrong; whoever takes it next is told. Asked for at a terminal."
        ),
    ) -> None:
        """Not good enough: send a finished node back, with what is wrong."""
        if note is None and run(lambda s: P.get(s, node_id).state in (P.DONE, P.REVIEW)):  # else its refusal
            note = asked(f"graphene node reopen {node_id}", "--note", "what is wrong")
        run(lambda s: P.reopen(s, node_id, P.caller(), note or ""))
        out(f"{node_id} is open again; whoever takes it next is shown your note (its contract is as it was: "
            f"`graphene node edit {node_id}` changes it)")  # fmt: skip
        said_where()

    @node_cli.command()
    def show(node_id: str = typer.Argument(...)) -> None:
        """A node's contract, then its record: who held it, what changed, what was refused, and how
        much of it is verified."""
        from .node_record import node_record, render, rolled_up

        def go(store):
            n = P.get(store, node_id)
            out(P.contract(n, P.trail(store, n)))
            for line in came_back(store, n):
                out(line)
            everything = P.nodes(store)
            under = [c for c in P.below(n.id, everything) if c in P.leaves(everything)]
            for line in rolled_up(store, root(), under) if under else render(node_record(store, root(), n)):
                out(line)
            entries = len(store.node_log(n.id))
            out(f"  every entry, check runs included: `graphene plan log` ({entries} for {n.id})")

        run(go)

    def came_back(store, n: P.Node) -> list[str]:
        """A leaf that came back: why, what it wanted, where its last attempt is, and the fixes on
        offer, each a command."""
        lines = []
        offers = P.offers(store, n)
        if offers:
            why = (store.node_log(n.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
            lines.append(f"  came back: {' '.join(str(why).split())}")
            for _key, what, command in offers:
                lines.append(f"    {what}: `graphene {' '.join(command)}`")
        if n.state == P.OPEN and P.RUN_TREE in (n.checkout or "") and Path(n.checkout or "").is_dir():
            lines.append(f"  its last attempt is kept in {n.checkout} (branch graphene/{n.id})")
        return lines

    @node_cli.command()
    def split(
        node_id: str = typer.Argument(...),
        executor: str = typer.Option(
            None, "--with", help="The planner. Default: claude with read-only tools."
        ),
    ) -> None:
        """Ask the planner to cut a leaf into smaller leaves under it, as proposals for you to prune."""
        planner(f"split {node_id} into smaller leaves", executor, node_id, True)

    @node_cli.command()
    def widen(
        node_id: str = typer.Argument(...),
        paths: list[str] = typer.Argument(None, help="Default: the paths it wanted outside its scope."),
    ) -> None:
        """A leaf came back needing paths outside its scope: widen the scope to them."""

        files = tracked()

        def go(store):
            n = P.widen(store, node_id, paths or [], P.caller(), files=files)
            out(f"{n.id}'s scope is now {', '.join(n.scope)}; it is ready again")

        write(f"node widen {node_id}", go)
        said_where()

    @node_cli.command()
    def sibling(
        node_id: str = typer.Argument(...),
        paths: list[str] = typer.Argument(None, help="Default: the paths it wanted outside its scope."),
    ) -> None:
        """A leaf came back needing paths outside its scope: a leaf beside it for them, which it waits on."""

        files = tracked()

        def go(store):
            made = P.sibling(store, node_id, paths or [], P.caller(), files=files)
            out(f"added {made.id} ({', '.join(made.scope)}); {node_id} waits on it")
            out(f"  its check is `{made.check}`; {node_id}'s, run after it, says if they work together")

        write(f"node sibling {node_id}", go)
        said_where()

    def plan_or_nothing() -> bool:
        """Plain `graphene`: where the work stands, when the repo has a plan. False when it has none."""
        r = root()
        if not (r / ".graphene" / "graphene.db").exists():
            return False
        with open_store(r) as store:
            if not [n for n in P.nodes(store) if n.state not in P.GONE]:
                return False
            print_plan(store, P.caller())
        return True

    return plan_or_nothing
