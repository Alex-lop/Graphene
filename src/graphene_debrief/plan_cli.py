"""`graphene plan` and `graphene node`: the plan in a terminal, for a person and for an agent alike.

Plain text, never wrapped or cut: an agent reads these lines as its contract, and a person greps them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer

from . import plan as P
from . import plan_text as T


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
        """A person's act on the plan's shape: kept for `graphene plan undo`, and said which
        repository it went to, so a stray `cd` cannot fool anyone."""
        who = P.caller()

        def go(store):
            with P.undoable(store, who, what):
                return operation(store)

        done = run(go)
        typer.echo(where(), err=True)
        return done

    def where() -> str:
        r, home = str(root()), str(Path.home())
        return f"  (the plan of {'~' + r[len(home) :] if r.startswith(home + os.sep) else r})"

    def warn_unreachable(store, ids) -> None:
        """A check that names a path no executor can create or find: said now, not after a run."""
        files, top = P.tracked(checkout()), checkout()
        for node_id in ids:
            node = P.get(store, node_id)
            missing = P.unreachable(node, files, top)
            if missing:
                typer.echo(
                    f"warning: {node.id}'s check names {', '.join(missing)}, which "
                    f"{'is' if len(missing) == 1 else 'are'} not in the repo and not in its scope, so no "
                    f"executor can make it pass as written (`graphene node edit {node.id}`)",
                    err=True,
                )

    def next_lines(store, who: P.Caller, but: str | None = None) -> list[str]:
        """What the caller can do now, read from the plan as it stands at this moment. ``but`` is a
        node the caller has just handed back: it is not sent straight back to it."""
        everything = P.nodes(store)
        by_id = {n.id: n for n in everything}
        if os.environ.get("GRAPHENE_NODE") and not who.person:
            return ["next: stop here. `graphene run` started you for one leaf, and it decides what runs next"]
        held = [n for n in everything if n.state == P.RUNNING and holds(n, who)]
        if held:
            n = held[0]
            return [
                f"next: you hold {n.id} ({n.title}). Finish it with `graphene node done {n.id}`, or hand "
                f"it back with `graphene node release {n.id} --why '…'`"
            ]
        mine = [n for n in P.ready(everything, who) if n.id != but]
        if mine:
            first = mine[0]
            more = f" and {len(mine) - 9} more" if len(mine) > 9 else ""
            also = f" (also ready: {', '.join(n.id for n in mine[1:9])}{more})" if mine[1:] else ""
            return [
                f"next: {first.id}, {first.title}{also}. `graphene node start {first.id}` prints its "
                "contract as it stands now; it may have changed since you last saw it"
            ]
        left = [n for n in everything if n.state in (P.PROPOSED, P.OPEN, P.RUNNING, P.REVIEW)]
        if not left:
            return ["next: nothing; every node is done"]
        why = []
        for n in left:
            reasons = [f"{b.id} ({b.state})" for b in P.unmet(n, by_id)]
            if n.id == but:
                why.append(f"{n.id} is back with the person, who reads why you handed it back")
            elif n.state == P.RUNNING:
                why.append(f"{n.id} is held by {n.executor}")
            elif n.state == P.REVIEW:
                why.append(f"{n.id} waits for a sign-off")
            elif n.state == P.PROPOSED:
                why.append(f"{n.id} is a proposal not yet accepted")
            elif not P.may_take(n, who):
                why.append(f"{n.id} is {n.owner}'s")
            elif reasons:
                why.append(f"{n.id} waits on {', '.join(reasons)}")
        tail = (
            ""
            if who.person
            else " You can stop: the rest waits for a person, and `graphene plan` shows them that"
        )
        more = f"; and {len(why) - 8} more" if len(why) > 8 else ""
        return [f"next: nothing is ready for you: {'; '.join(why[:8])}{more}.{tail}"]

    def brief(text: str, node_id: str) -> str:
        """A reason as one table cell: the whole of it is in `node show`."""
        text = " ".join(text.split())
        return text if len(text) <= 100 else f"{text[:97]}… (`graphene node show {node_id}` has all of it)"

    def cut(text: str, wide: int) -> str:
        return text if len(text) <= wide else text[: wide - 1] + "…"

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

    def describe(store, n: P.Node, by_id: dict[str, P.Node]) -> str:
        if n.state == P.RUNNING:
            return f"{n.executor} since {(n.started_at or '')[11:16]}Z"
        if n.state == P.REVIEW:
            return f"check passed; waits for a sign-off: `graphene node signoff {n.id}`"
        if n.state == P.PROPOSED:
            needs = f"would wait on {', '.join(n.needs)}; " if n.needs else ""
            return f"proposed by {n.proposed_by}; {needs}`graphene plan accept {n.id}`"
        if n.state == P.OPEN:
            blockers = P.unmet(n, by_id)
            if blockers:
                return "waits on " + ", ".join(
                    f"{b.id} ({b.owner}'s)" if b.owner != P.AGENT else b.id for b in blockers
                )
            last = (store.node_log(n.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
            if last["kind"] == "released":
                return f"ready · handed back: {brief(last['detail'].get('why', ''), n.id)}"
            if last["kind"] == "reopened":
                return f"ready · sent back: {brief(last['detail'].get('note', ''), n.id)}"
            return "ready"
        return ""

    FOLD = 12  # lines of tree the plain print shows before finished leaves fold into their sub-goal

    def plan_lines(store, who: P.Caller, everything: bool = False) -> list[str]:
        """The plan as a tree, for a person and an agent alike: what waits on the person first, then
        the goal, then the tree folded to what is still moving. ``everything`` unfolds it."""
        alive = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
        if not alive:
            return [
                "no plan yet. Tell your agent what you want, in a paragraph: it proposes the tree "
                "(`graphene plan propose -`, in the text `graphene plan --text` prints), and you prune it "
                "(`graphene watch`, or `graphene plan edit` in your editor). `graphene node add 'title' "
                "--scope 'src/x/**' --check 'pytest tests/x'` adds one node by hand"
            ]
        by_id = {n.id: n for n in alive}
        under = P.kids(alive, drawn=True)  # proposals are drawn where they would go; they bind nothing
        leaves = [n for n in P.leaves(alive) if not n.aside]
        asides = [n for n in alive if n.aside]
        count = {s: sum(1 for n in leaves if n.state == s) for s in (P.RUNNING, P.DONE)}
        lines = [f"the plan: {P.goal(store)}"] if P.goal(store) else []
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
        yours += [n for n in P.ready(alive) if n.owner != P.AGENT]
        back = [n for n in alive if P.offers(store, n)]  # it came back with a fix on offer: the person's
        if who.person and (yours or stuck or back):
            ask = {P.PROPOSED: "accept", P.REVIEW: "sign off", P.OPEN: "yours to do"}
            seen: list[str] = []
            told = [
                f"{n.id} ({ask[n.state]}"
                + (f", with the {len(P.below(n.id, alive))} under it" if under.get(n.id) else "")
                + ")"
                for n in yours
                if n.id not in seen and not seen.append(n.id)
            ]
            told += [f"{n.id} (its leaves are done and its own check fails)" for n in stuck]
            told += [f"{n.id} (came back: `graphene node show {n.id}`)" for n in back]
            more = (
                f", and {len(told) - 8} more (`graphene plan --all`)"
                if len(told) > 8 and not everything
                else ""
            )
            lines.append("waiting on a person: " + ", ".join(told if everything else told[:8]) + more)
        wid = max(len(n.id) + 2 * len(P.above(n, by_id)) for n in alive)
        wt = min(44, max(len(n.title) for n in alive))
        wo = max(len(n.owner) for n in alive)
        ws = max(len(scope_cell(n)) for n in alive)
        shown = [n for n in alive if not n.aside or n.state != P.DONE]
        fold = not everything and len(shown) > FOLD

        def row(n: P.Node, depth: int) -> str:
            mine = under.get(n.id, [])
            if not mine and not n.scope:
                state, what = "sub-goal", f"no leaves yet: `graphene node add … --parent {n.id}`"
            elif mine:
                done = sum(1 for c in P.below(n.id, alive) if not under.get(c.id) and c.state == P.DONE)
                of = sum(1 for c in P.below(n.id, alive) if not under.get(c.id))
                state, what = (
                    ("done" if n.state == P.DONE else n.state if n.state != P.OPEN else "sub-goal"),
                    (f"{done}/{of} done" + (f"; then `{n.check}`" if n.check and n.state != P.DONE else "")),
                )
                if n.id in closed:
                    inside = [c for c in P.below(n.id, alive) if c.id in ready_ids]
                    what += f" · {len(inside)} ready" if inside else ""
                    what += f" · {of} leaves folded (`graphene plan --all` unfolds)"
            else:
                state = "waiting" if n.state == P.OPEN and P.unmet(n, by_id) else n.state
                what = describe(store, n, by_id)
            ident = ("  " * depth + n.id).ljust(wid)
            cells = f"  {ident}  {state.ljust(8)}  {cut(n.title, wt).ljust(wt)}  {n.owner.ljust(wo)}  "
            return f"{cells}{scope_cell(n).ljust(ws)}  ·  {what}".rstrip()

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
                    + f": {cut(', '.join(n.id for n in folded), 60)}   (`graphene plan --all` unfolds)"
                )

        walk(None, 0)
        done_asides = [n for n in asides if n.state == P.DONE]
        if done_asides and not everything:
            lines.append(
                f"  ✓ {len(done_asides)} done from a prompt, each with its record "
                f"(`graphene plan --all`; latest: {done_asides[-1].id}, {cut(done_asides[-1].title, 40)})"
            )
        try:
            loose = P.unowned(store, checkout()) if not P.nodes(store, (P.RUNNING,)) else []
        except P.Refused:
            loose = []  # not a checkout git can read: nothing to compare
        if loose:
            listed = ", ".join(loose[:8]) + (f" and {len(loose) - 8} more" if len(loose) > 8 else "")
            lines.append(
                f"changed while no node owned it: {listed}  (yours? `graphene plan ack`; else put it back)"
            )
        if not who.person:
            lines += next_lines(store, who)
        return lines

    def print_plan(store, who: P.Caller, everything: bool = False) -> None:
        for line in plan_lines(store, who, everything):
            out(line)

    def log_line(e: dict, with_node: int = 0, who_wide: int = 16) -> str:
        detail = e["detail"]
        changed = detail.get("changed")  # an edit's field changes (a dict), or an ending's paths (a list)
        fields = changed.items() if isinstance(changed, dict) else ()
        said = (
            detail.get("why")
            or (
                f"{detail['note']}  (it said: {detail['was']})"
                if detail.get("was") and detail.get("note")
                else ""
            )
            or detail.get("note")
            or detail.get("override")
            or (f"by their prompt in the session: {detail.get('prompt', '')!r}" if detail.get("by") else "")
            or detail.get("path")
            or ", ".join(detail.get("outside") or detail.get("paths") or detail.get("unowned") or [])
            or "; ".join(f"{k}: {a!r} -> {b!r}" for k, (a, b) in fields)
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
        from .tui import run as watch_tui

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
                "`propose -` reads the plan from a pipe, and nothing is piped here, so nothing was read. An "
                "agent pipes it (graphene plan propose - <<'EOF' … EOF); at a terminal, `graphene plan edit` "
                "opens the plan in your editor",
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
                out(f"{'  ' * len(P.above(n, by_id))}{n.id}  {n.state}  {n.title}")
            return added

        def as_text(store) -> list[P.Node]:
            before = {n.id for n in P.nodes(store)}
            for line in T.apply(store, text, who, None, files=files):
                out(line)
            return [n for n in P.nodes(store) if n.id not in before]

        def go(store):
            added = as_json(store) if text.lstrip().startswith(("{", "[")) else as_text(store)
            warn_unreachable(store, [n.id for n in added])
            if not who.person and added:
                out(
                    f"{len(added)} proposed. The person sees them now (`graphene watch`, `graphene plan`) "
                    "and accepts or prunes them; nobody can start them before that. Tell them the tree is "
                    "ready, and stop"
                )

        write("plan propose", go)

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
        typer.echo(where(), err=True)

    def edit_in_editor(node_id: str | None, alone: bool) -> None:
        who = P.caller()
        if not who.person:
            fail("an editor is for the person at a terminal; an agent proposes: `graphene plan propose -`", 1)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if not editor and not sys.stdin.isatty():
            fail("no terminal to open vi in, and no $EDITOR set; set $EDITOR, or run this in a terminal", 1)
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
        if said:
            with open_store(root()) as store:
                warn_unreachable(store, [i for i in said.ids if store.node_row(i)])
            typer.echo(where(), err=True)

    @plan_cli.command()
    def accept(ids: list[str] = typer.Argument(None, help="Node ids; none means every proposal.")) -> None:
        """Accept proposals into the plan, and say what an unattended run will and will not reach."""

        def go(store):
            by_id = {n.id: n for n in P.nodes(store)}
            for n in P.accept(store, ids or [], P.caller()):
                out(f"{'  ' * len(P.above(n, by_id))}{n.id}  accepted  {n.title}")
            runs, waits = P.forecast(P.nodes(store))
            out("left alone, agents can reach: " + (", ".join(n.id for n in runs) or "nothing"))
            for n, why in waits:
                out(f"  {n.id} will wait: {'; '.join(why)}")

        write("plan accept" + (f" {' '.join(ids)}" if ids else ""), go)

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
        from .node_record import rolled_up

        def go(store):
            for line in rolled_up(store, root(), P.leaves(P.nodes(store))):
                out(line.replace("under it", "in the plan"))

        run(go)

    @plan_cli.command()
    def archive() -> None:
        """Put finished nodes away. With nothing else left, the plan is no longer in force."""
        gone = run(lambda s: P.archive(s, P.caller()))
        out(f"archived {', '.join(n.id for n in gone)}" if gone else "nothing finished to archive")

    @plan_cli.command()
    def ack() -> None:
        """Accept, as they are, the changes made while no node owned them (they are yours, or fine)."""
        paths = run(lambda s: P.acknowledge(s, checkout(), P.caller()))
        out(f"acknowledged: {', '.join(paths)}" if paths else "nothing had changed between nodes")

    @plan_cli.command()
    def pause() -> None:
        """Suspend the plan: nothing starts, and no write is refused, until `graphene plan resume`."""
        run(lambda s: P.set_paused(s, True, P.caller()))
        out("paused: nothing starts and nothing is enforced until `graphene plan resume`")

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
            fail("say 'leaf' or 'strict'", 1)

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

    @plan_cli.command()
    def resume() -> None:
        """Put the plan back in force."""
        run(lambda s: P.set_paused(s, False, P.caller()))
        out("the plan is in force")

    @cli.command("run")
    def run_(
        executor: str = typer.Option(
            None,
            "--with",
            help="The executor: a command that takes a prompt as its last argument. Default: "
            "'claude -p --permission-mode acceptEdits'; e.g. 'codex exec --sandbox workspace-write'.",
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
        """Run every leaf an agent can reach: one executor per leaf, and Graphene decides what is done."""
        from .run import DEFAULT_WITH, run_parallel, run_plan

        r = root()
        with open_store(r) as store:
            if not P.nodes(store, (P.OPEN, P.RUNNING)):
                fail("nothing to run: the plan has no open node (`graphene plan`)", 1)
            logs = r / ".graphene" / "runs"
            try:
                if parallel > 1:
                    run_parallel(
                        lambda: open_store(r), r, checkout(), parallel, executor or DEFAULT_WITH,
                        attempts, node or None, out, logs,
                    )  # fmt: skip
                else:
                    run_plan(store, checkout(), executor or DEFAULT_WITH, attempts, node or None, out, logs)
            except P.Refused as no:
                fail(str(no), 1)
            except KeyboardInterrupt:
                out("stopped. What was running is handed back and ready again; `graphene plan` shows it")
                raise typer.Exit(130) from None
            for line in next_lines(store, P.caller()):
                out(line)

    def planner(sentence: str, executor: str | None, about: str | None, split: bool) -> None:
        from .ask import DEFAULT_PLANNER, ask

        who = P.caller()
        if not who.person:
            fail(
                "asking a planner is the person's: it starts an agent, and spends. Propose the tree yourself",
                1,
            )

        def go(store):
            said = ask(store, checkout(), sentence, executor or DEFAULT_PLANNER, about, split, out)
            for line in said:
                out(line)
            if said:
                out("prune it: `graphene watch` (y accepts, d drops), or `graphene plan edit`")

        run(go)
        typer.echo(where(), err=True)

    @cli.command("ask")
    def ask_(
        sentence: str = typer.Argument(..., help="What you want, as you would say it."),
        executor: str = typer.Option(
            None,
            "--with",
            help="The planner: a command taking a prompt last. Default: 'claude -p --tools Read,Grep,Glob'.",
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

        def go(store):
            [n] = P.propose(store, [item], P.caller(), files=P.tracked(checkout()))
            out(f"{n.id}  {n.state}  {n.title}")
            warn_unreachable(store, [n.id])

        write(f"node add {title!r}", go)

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
            fail(
                "nothing to change: pass --scope, --check, --goal, --needs, --owner, --title or --signoff", 1
            )

        def go(store):
            before = P.get(store, node_id).rev
            node = P.edit(store, node_id, edits, P.caller(), files=P.tracked(checkout()))
            last = store.node_log(node_id, ("edited",))[-1] if node.rev != before else None
            if last is not None:
                warn_unreachable(store, [node_id])
            return node, last

        n, last = write(f"node set {node_id}", go)
        if last is None:
            out(f"{n.id} is unchanged (revision {n.rev})")
            return
        out(f"{n.id} is now revision {n.rev}:")
        for name, (before, after) in last["detail"]["changed"].items():
            out(f"  {name}: {before!r} -> {after!r}")
        if n.state == P.RUNNING:
            out(
                f"{n.id} is running: {n.executor} was told revision {n.told_rev}. Writes are checked against "
                "the new scope from now on, and `done` against the new check"
            )

    @node_cli.command()
    def drop(node_id: str = typer.Argument(...)) -> None:
        """Take a node out of the plan, with everything under it. Dropping a sub-goal's children
        makes it a leaf again: that is how a split is undone."""
        write(f"node drop {node_id}", lambda s: P.drop(s, node_id, P.caller()))
        out(f"{node_id} dropped (`graphene plan undo` puts it back)")

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
                    raise P.Refused("which node? `graphene node done <id>`")
                target = held[0].id
            n = P.finish(store, target, who, override=override, checkout=checkout())
            how = (
                "overruled by a person" if override is not None else "check passed, nothing outside its scope"
            )
            out(f"{n.id} is {'done' if n.state == P.DONE else 'finished and waits for a sign-off'} ({how})")
            for line in next_lines(store, who):
                out(line)

        run(go)

    @node_cli.command()
    def release(
        node_id: str = typer.Argument(...),
        why: str = typer.Option(..., "--why", help="What is in the way. The person reads this."),
    ) -> None:
        """Hand a running node back, saying why. The way out when it cannot be finished as written."""
        who = P.caller()

        def go(store):
            P.release(store, node_id, who, why)
            out(f"{node_id} handed back: {why}")
            for line in next_lines(store, who, but=node_id):
                out(line)

        run(go)

    @node_cli.command("signoff")
    def signoff_(node_id: str = typer.Argument(...)) -> None:
        """A person's say-so: the node is done."""

        def go(store):
            P.signoff(store, node_id, P.caller(), checkout=checkout())
            return (store.node_log(node_id, ("unlanded",)) or [{"detail": {}}])[-1]["detail"]

        left = run(go)
        out(f"{node_id} is done (signed off)")
        if left.get("branch"):  # the person merged it by hand: its worktree goes, and its branch if merged
            where = ["git", "-C", str(checkout())]
            subprocess.run([*where, "worktree", "remove", "--force", left["worktree"]], capture_output=True)
            gone = subprocess.run([*where, "branch", "-d", left["branch"]], capture_output=True)
            if gone.returncode != 0:
                out(
                    f"{left['branch']} is not merged here, so it was kept: "
                    f"`git branch -D {left['branch']}` drops it"
                )

    @node_cli.command()
    def reopen(
        node_id: str = typer.Argument(...),
        note: str = typer.Option(..., "--note", help="What is wrong; whoever takes it next is told."),
    ) -> None:
        """Not good enough: send a finished node back, with what is wrong."""
        run(lambda s: P.reopen(s, node_id, P.caller(), note))
        out(
            f"{node_id} is open again. Whoever takes it next is shown your note; the contract itself is "
            "unchanged, so if the note changes what is wanted, say it there too: "
            f"`graphene node set {node_id} --goal …`"
        )

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
            None, "--with", help="The planner. Default: 'claude -p --tools Read,Grep,Glob'."
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

        def go(store):
            n = P.widen(store, node_id, paths or [], P.caller(), files=P.tracked(checkout()))
            out(f"{n.id}'s scope is now {', '.join(n.scope)} (revision {n.rev}); it is ready again")

        write(f"node widen {node_id}", go)

    @node_cli.command()
    def sibling(
        node_id: str = typer.Argument(...),
        paths: list[str] = typer.Argument(None, help="Default: the paths it wanted outside its scope."),
    ) -> None:
        """A leaf came back needing paths outside its scope: a leaf beside it for them, which it waits on."""

        def go(store):
            made = P.sibling(store, node_id, paths or [], P.caller(), files=P.tracked(checkout()))
            out(f"added {made.id} ({', '.join(made.scope)}); {node_id} waits on it")
            out(f"  its check is `{made.check}`; {node_id}'s, run after it, says if they work together")

        write(f"node sibling {node_id}", go)

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
