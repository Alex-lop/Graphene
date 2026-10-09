"""`graphene plan` and `graphene node`: the plan in a terminal, for a person and for an agent alike.

Plain text, never wrapped or cut: an agent reads these lines as its contract, and a person greps them.
The one exception is the plan itself (`graphene`, `graphene plan`, `watch --once`) at a terminal or
under $COLUMNS: it fits that width (`room`).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from . import board as B
from . import direction as D
from . import extra
from . import gate as G
from . import plan as P
from . import plan_text as T
from . import views as V

# What `graphene` and `graphene plan` say in a repository with nothing planned: paragraph in, tree out.
NO_PLAN = (
    "nothing is planned here yet. Say what you want to your agent, in a paragraph: it proposes the "
    "tree, and you prune it in `graphene watch`. Or `graphene ask '<what you want>'`"
)
# ... and in a repository `graphene init` never set up, what comes before either
NOT_INIT = (
    "Before either, `graphene init` chooses who plans and who runs (until then, `ask` and `run` refuse)"
)
# What `graphene plan first` says each setting does
FIRST_SAID = {
    "on": "Every ask in a session is proposed, one leaf included, and waits for you.",
    "auto": f"Every ask is proposed first. One leaf of at most {G.WIDE} paths, with nothing on the board, "
    "is yours at once; anything else waits for you.",
    "off": "What you ask for in a session is done at once, as a leaf of its own.",
}


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
        uses (`plan.where_said`)."""
        if line := P.where_said(root()):
            typer.echo(line, err=True)

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
        # a leaf that came back reads so, as on the screen and in `plan --view`: it is said after the
        # leaves that are ready, and in its own word, since its next move is the person's
        back = {n.id for n in everything if P.came_back(store, n)}
        agents = sorted((n for n in P.ready(everything, P.Caller("agent", False)) if n.id != but),
                        key=lambda n: n.id in back)  # fmt: skip
        mine = sorted((n for n in P.ready(everything, who) if n.id != but), key=lambda n: n.id in back)

        def is_(n: P.Node) -> str:
            return f"came back (`graphene node show {n.id}`)" if n.id in back else "is ready"

        def again(n: P.Node, more: int) -> list[str]:
            """A leaf that came back: what `graphene watch` offers on it, as the commands its keys run,
            not a `start` (the screen offered w, b and r while this line said `node start`)."""
            offers = P.offers(store, n)
            said = [f"`graphene {' '.join(argv)}` ({what})" for _, what, argv in offers]
            said.append(f"{'or ' if said else ''}`graphene run --node {n.id}` (run it again)")
            said[-1] += f"; {', '.join([*(k for k, _, _ in offers), 'r'])} in `graphene watch`"
            also = f", and {more} more did" if more else ""
            return [f"next: {n.id} ({n.title}) came back{also}: {', '.join(said)}"]

        if who.person:
            if agents and agents[0].id in back:  # each came back: plain `graphene run` leaves them to you
                first = agents[0]
                return [f"next: {first.id} ({first.title}) {is_(first)}: `graphene run --node {first.id}` "
                        "runs it again"]  # fmt: skip
            if agents:
                agents = [n for n in agents if n.id not in back]
                first, more = agents[0], len(agents) - 1
                if first.id in back:  # the ready ones come first: every one left came back
                    return again(first, more)
                also = f", and {more} more" if more else ""
                return [f"next: {first.id} ({first.title}) {is_(first)}{also}: `graphene run` runs "
                        f"{'them' if more else 'it'}"]  # fmt: skip
            if mine:
                return [f"next: {mine[0].id} ({mine[0].title}) is yours to do"]
            return [f"next: nothing is ready to run{rest}"]
        if mine:
            first, more = mine[0], len(mine) - 1
            if first.id in back:  # its next move is the person's
                return again(first, more)
            also = f", and {more} more" if more else ""
            return [
                f"next: {first.id} ({first.title}) {is_(first)}{also}: `graphene node start {first.id}` "
                "takes it, with its contract as it stands now"
            ]
        proposed = len(P.leaves([n for n in everything if n.state == P.PROPOSED]))
        board = B.waiting(store)[0]
        if proposed or board:  # the next move is the person's: said, so an agent does not tell them to stop
            what = [f"the proposal ({_leaves(proposed)})"] * bool(proposed)
            what += [f"the board ({board})"] * bool(board)
            verb = "waits" if len(what) == 1 else "wait"
            return [f"next: nothing is ready for you: {' and '.join(what)} {verb} on the person"]
        return [f"next: nothing is ready for you, so you can stop{rest}"]

    def _leaves(n: int) -> str:
        return f"{n} leaf" if n == 1 else f"{n} leaves"

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

    def describe(
        store, n: P.Node, word: str, by_id: dict[str, P.Node], words: dict, who: P.Caller, room: int | None
    ) -> list[str]:
        """What a leaf's row adds after its state: where it may write, what it waits on, and the
        command for the move that is the person's (accept, sign off). ``room``: the columns a line of
        its own has; a reason longer is cut there, and where the rest is goes on the next."""
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
        how = {"released": ("handed back", "why"), "reopened": ("sent back", "note")}.get(last["kind"])
        if n.state == P.OPEN and how:
            reason = " ".join(str(last["detail"].get(how[1], "")).split())
            if room and len(f"{how[0]}: {reason}") > room:
                said += [T.elide(f"{how[0]}: {reason}", room), f"(`graphene node show {n.id}` has all of it)"]
            else:
                said.append(f"{how[0]}: {brief(reason, n.id)}")
        return said

    FOLD = 12  # lines of tree the plain print shows before finished leaves fold into their sub-goal

    def room() -> int | None:
        """The columns the plan's print fits: the terminal's, or $COLUMNS; None in a pipe or an agent's
        shell with neither, where every line stays whole for grep."""
        at_terminal = os.environ.get("COLUMNS") or sys.stdout.isatty()
        return shutil.get_terminal_size().columns if at_terminal else None

    def wrapped(line: str, width: int) -> list[str]:
        """A line of words at ``width``: broken between words, never inside a `command`, the rest
        indented under it."""
        import textwrap

        if len(line) <= width:
            return [line]
        indent = " " * (len(line) - len(line.lstrip()) + 2)
        kept = re.sub(r"`[^`]*`", lambda m: m.group().replace(" ", "\u00a0"), line)  # one word each
        lines = textwrap.wrap(kept, width, subsequent_indent=indent, break_long_words=False,
                              break_on_hyphens=False, drop_whitespace=True)  # fmt: skip
        return [part.replace("\u00a0", " ") for part in lines]

    def plan_lines(
        store, who: P.Caller, everything: bool = False, archive: bool = True, width: int | None = None
    ) -> list[str]:
        """The plan as a tree, for a person and an agent alike: what waits on the person first, then
        the goal, then the tree folded to what is still moving. ``everything`` unfolds it; without
        ``archive`` a finished plan is not told how to put it away (a replay's repository is gone).
        ``width``: every line fits it (80 columns at least): a row keeps its title (cut), id and state
        word on its line, and what it adds goes on lines of its own under it; the rest wrap at words."""
        alive = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
        asked, board = B.waiting(store)  # what the board waits on the person for
        if not alive:
            none = NO_PLAN if store.meta("plan_first") is not None else f"{NO_PLAN}. {NOT_INIT}"
            return [board, none] if board else [none]
        by_id = {n.id: n for n in alive}
        under = P.kids(alive, drawn=True)  # proposals are drawn where they would go; they bind nothing
        leaves = P.counted(alive)
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
            try:
                left = P.uncommitted(store, checkout()) if archive else []
            except P.Refused:
                left = []  # not a checkout git can read: nothing to compare
            if left:  # "finished" had read as landed while `git status` held their work
                head += f" · finished; the work of {len(left)} lea{'f' if len(left) == 1 else 'ves'} is "
                head += P.UNCOMMITTED
            head += " · finished" * (not left) + ("; `graphene plan archive` puts it away" if archive else "")
        lines += [head, *([board] if board else [])]
        yours = [n for n in alive if n.state == P.REVIEW]
        yours += [  # a proposed subtree is asked about once, at its top
            n
            for n in alive
            if n.state == P.PROPOSED and (n.parent not in by_id or by_id[n.parent].state != P.PROPOSED)
        ]
        back = {n.id for n in alive if P.came_back(store, n)}  # it came back: the next move is the person's
        words = {n.id: P.reads(n, alive, back) for n in alive}  # the words the screen and the text use
        yours += [n for n in alive if words[n.id] == "yours"]  # a person's own leaf, scope or none
        if who.person and (yours or stuck or back or asked):
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
            told += [f"{asked} on the board (`graphene board`)"] if asked else []
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
        if width:  # the title gives way, never the id or the word: commands take them
            wt = max(min(wt, width - 6 - wid - ww), max(heads.values()) + 6)
        shown = [n for n in alive if not n.aside or n.state != P.DONE]
        fold = not everything and len(shown) > FOLD

        def row(n: P.Node, depth: int) -> list[str]:
            word = words[n.id]
            indent = f"  {'  ' * depth}    "  # a line of its own, under the title
            if under.get(n.id):
                of = sum(1 for c in P.below(n.id, alive) if not under.get(c.id))
                what = [f"then `{n.check}`"] if n.check and n.state != P.DONE else []
                what += [f"`graphene plan accept {n.id}`"] if n.state == P.PROPOSED else []
                if n.id in closed:
                    inside = [c for c in P.below(n.id, alive) if c.id in ready_ids]
                    what += [f"{len(inside)} ready"] if inside else []
                    what += [f"{of} leaves folded (`graphene plan --all` unfolds)"]
            else:
                what = describe(store, n, word, by_id, words, who, width and width - len(indent))
            head = f"{'  ' * depth}{P.look(word)[0]} "
            title = f"{head}{T.elide(n.title, wt - len(head))}"
            cells = f"  {title.ljust(wt)}  {n.id.ljust(wid)}  {word.ljust(ww)}"
            one = f"{cells}  · {' · '.join(what)}" if what else cells.rstrip()
            if not width or len(one) <= width:
                return [one]
            said, sep = [cells], "  · "  # what fits beside the cells, then lines of its own, each cut
            for piece in what:
                if len(said[-1]) + len(sep) + len(piece) <= width:
                    said[-1] += sep + piece
                else:
                    said.append(indent + T.elide(piece, width - len(indent)))
                sep = " · " if said[1:] else "  · "
            return [line.rstrip() for line in said]

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
                lines.extend(row(n, depth))
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
        return [part for line in lines for part in wrapped(line, width)] if width else lines

    def above(store) -> None:
        """The direction above the plan: the path to the node it hangs from (`direction.above_plan`)."""
        for line, _ in D.above_plan(store, root(), shutil.get_terminal_size().columns):
            out(line)

    def print_plan(store, who: P.Caller, everything: bool = False) -> None:
        above(store)
        for line in plan_lines(store, who, everything, width=room()):
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
        everything, now = P.nodes(store), P.get(store, n.id)
        word = P.reads(now, everything, {n.id} if P.came_back(store, now) else set())
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
        help="Print the plan: what will be done, by whom, inside which paths.\n\n"
        "The commands below change the plan. The options print the plan as text, JSON or a view.",
        invoke_without_command=True,
    )
    cli.add_typer(plan_cli, name="plan")
    if cover := extra.load("cover"):  # the Nemotron extra's, when it is installed
        cover.command(plan_cli, run, out)  # graphene plan cover: the person's words, accounted for
        extra.need("precheck").register(plan_cli, root, open_store, fail)  # `graphene plan precheck`

    @plan_cli.callback()
    def show_plan(
        ctx: typer.Context,
        as_json: bool = typer.Option(False, "--json", help="Print the plan as JSON."),
        as_text: bool = typer.Option(
            False,
            "--text",
            help="Print the plan as text, the form `plan edit` opens and `plan propose` reads.",
        ),
        everything: bool = typer.Option(False, "--all", help="Unfold the tree, finished work included."),
        view: str = typer.Option(
            None, "--view", help=f"Draw the plan as one view: {', '.join(['auto', *V.VIEWS])}."
        ),
        width: int = typer.Option(
            None, "--width", help="With --view, the columns to draw in; $COLUMNS if left out."
        ),
        height: int = typer.Option(
            None, "--height", help="With --view, the rows to draw in; $LINES if left out."
        ),
    ) -> None:
        """Print the plan as a tree: what waits on you, then what is moving. Finished work is folded."""
        if ctx.invoked_subcommand is not None:
            return
        who = P.caller()
        if view and (as_json or as_text):
            fail("--view draws the plan; --json and --text print what it holds: one or the other", 2)
        if as_text:
            run(lambda s: out(T.render(s)[0].rstrip("\n")))
            return
        if view:
            return print_view(view, width, height, lambda: run(lambda s: print_plan(s, who, everything)))
        run(lambda s: out(P.to_json(P.nodes(s))) if as_json else print_plan(s, who, everything))

    @plan_cli.command("goal", hidden=True)
    def goal_(text: str = typer.Argument(None, help="Why any of this is being done, in your words.")) -> None:
        """Set the plan's goal, or print it.

        Every executor reads the goal above its own leaf."""
        if text is None:
            out(run(P.goal) or "no goal yet: `graphene plan goal 'why any of this is being done'`")
            return
        was = run(P.goal)
        write("plan goal", lambda s: P.set_goal(s, text, P.caller()))
        out(f"the plan: {text.strip()}")
        if was:
            out(f"  (it said: {was})")
        said_where()

    def print_once(who: P.Caller, everything: bool, archive: bool = True, recent_as: str = "just now",
                   wide: int | None = None) -> None:  # fmt: skip
        """`graphene watch --once`: the plan, then what just happened (``recent_as``), each of its rows cut
        to ``wide`` columns when given, else fitted to the terminal's width (none in a pipe)."""
        from rich.text import Text

        width = wide or room()
        with open_store(root()) as store:
            above(store)
            lines = plan_lines(store, who, everything, archive, width=width)
            recent = store.node_log()[-6:]
        for line in lines:
            out(line)
        if recent:
            out(f"\n{recent_as}")
            for e in recent:
                if wide:
                    said = Text(log_line(e, with_node=8))
                    said.truncate(wide, overflow="ellipsis")
                    out(said.plain)
                    continue
                for part in wrapped(log_line(e, with_node=8), width) if width else [log_line(e, with_node=8)]:
                    out(part)

    def known_view(name: str) -> None:
        if name != "auto" and name not in V.VIEWS:
            fail(f"no view named {name}: the views are {', '.join(['auto', *V.VIEWS])}", 2)

    def print_view(name: str, width: int | None, height: int | None, outline) -> None:
        """`graphene plan --view NAME`: the plan as that view draws it, in plain text, at $COLUMNS (or
        --width) by $LINES (or --height), for a script, a test or a stand-in; what a screen of that size
        shows when Tab reaches it, drawn in the room the screen gives a view (`views.room`). `auto` is
        the view such a screen opens in. The outline, a view
        that does not fit (said on stderr, as the screen says it) and an empty plan print as
        ``outline()`` does: `graphene plan`, with --all if asked, or `watch --once`, with what just
        happened."""
        known_view(name)
        size = shutil.get_terminal_size()
        width, height = width or size.columns, height or size.lines

        def show(store) -> bool:
            nodes, words, goal = V.inputs(store)
            wide, high = V.room(width, height)
            chosen = V.choose(nodes, words, goal, wide, high) if name == "auto" else name
            view = V.VIEWS[chosen]
            noted = {"meter": V.billed(store.node_log())} if getattr(view, "METER", False) else {}
            if getattr(view, "EVENTS", False):
                who = P.caller()  # the person's lane, whoever prints it: an agent's acts are not theirs
                noted["events"] = V.happened(store.node_log(), who.name if who.person else P.person_name())
            drawn = view.draw(nodes, words, goal, wide, high, None, **noted) if view else None
            if drawn is None or not nodes:
                if chosen != "outline" and nodes:
                    typer.echo(f"the {chosen} does not fit at {width} columns: the outline", err=True)
                return False
            for line, _ in D.above_plan(store, root(), width):
                out(line)
            for line in drawn.lines:
                out(line.plain.rstrip())
            if drawn.note:
                out(drawn.note)
            return True

        if not run(show):
            outline()

    @cli.command()
    def watch(
        everything: bool = typer.Option(
            False, "--all", help="With --once, unfold the tree, finished work included."
        ),
        every: float = typer.Option(1.0, "--every", help="Seconds between looks at the plan."),
        once: bool = typer.Option(
            False, "--once", help="Print the plan once, with what just happened, and leave."
        ),
        view: str = typer.Option(
            None,
            "--view",
            help=f"Open in this view ({', '.join(['auto', *V.VIEWS])}); the outline if left out.",
        ),
    ) -> None:
        """Show the plan on one screen, live, with vim keys.

        Every key runs a graphene command. Press ? for the keys and q to leave. In a script, use --once."""
        who = P.caller()
        if view:
            known_view(view)
        if (once or not sys.stdout.isatty()) and view not in (None, "outline"):
            return print_view(view, None, None, lambda: print_once(who, everything))
        if once or not sys.stdout.isatty():
            return print_once(who, everything)
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
        watch_tui(r, lambda: open_store(r), every, view)

    @cli.command()
    def demo(
        recording: Path = typer.Argument(
            None, help="A file --record made; Graphene's own recording if left out."
        ),
        once: bool = typer.Option(False, "--once", help="Print where the replay ends, and leave."),
        record: Path = typer.Option(
            None,
            "--record",
            help="Record this repo's plan, never a key or a path, into this file until Ctrl-C.",
        ),
        speed: float = typer.Option(
            1.0,
            "--speed",
            min=0.1,
            max=20.0,
            help="Play this many times faster, such as 2, or slower, such as 0.5.",
        ),
    ) -> None:
        """Replay a recorded run in `graphene watch`, change by change.

        The replay needs no key, no network and no Docker. Nothing in it runs."""
        import contextlib
        import tempfile

        from . import demo as D

        if record is not None:
            try:
                n = D.record(root(), record)
            except OSError as no:
                fail(f"cannot write {record}: {no.strerror or no}", 1)
            typer.echo(f"recorded {n} changes to {record}", err=True)
            return
        try:
            head, lines = D.load(recording or D.SHIPPED, speed)
        except (OSError, ValueError, KeyError) as no:
            fail(f"cannot replay {recording or D.SHIPPED}: {no}", 1)
        with tempfile.TemporaryDirectory(prefix="graphene-demo-") as tmp:
            try:
                repo = D.repository(Path(tmp), head)
            except (OSError, subprocess.CalledProcessError) as no:
                fail(f"graphene demo makes a git repository for the replay, and could not: {no}", 1)
            if not once and sys.stdout.isatty():
                D.Replay(repo, head, lines).run()  # the temporary repository goes when the screen closes
                return
            D.last_frame(repo, lines)
            wide = shutil.get_terminal_size().columns
            out(D.fit(D.banner(head, D.ENDED), wide).plain)  # whole pieces, as the screen's top line
            with contextlib.chdir(repo):  # printed as `graphene watch --once` prints it, in the replay's repo
                print_once(P.caller(), everything=False, archive=False, recent_as=D.ENDING, wide=wide)

    @plan_cli.command(hidden=True)
    def propose(
        file: str = typer.Argument(..., help="A file of the plan's text or JSON; '-' reads a pipe."),
    ) -> None:
        """Add a tree, in the text `graphene plan --text` prints.

        From an agent each node is a proposal. A line with an existing [id] adds under that node."""
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
        here = checkout()
        files = P.tracked(here)

        def as_json(store) -> list[P.Node]:
            try:
                raw = json.loads(text)
            except ValueError as exc:
                raise P.Refused(f"cannot read {file} as JSON: {exc}") from None
            items = raw.get("nodes") if isinstance(raw, dict) else raw
            if not isinstance(items, list) or not items:
                raise P.Refused('expected {"nodes": [ … ]} with at least one node')
            told: list[str] = []
            added = P.propose(store, items, who, files=files, told=told)
            by_id = {n.id: n for n in P.nodes(store)}
            for n in added:
                out(one_row(store, n, len(P.above(n, by_id))))
            for line in told:
                out(line)
            return added

        def as_text(store) -> list[P.Node]:
            before = {n.id for n in P.nodes(store)}
            for line in T.apply(store, text, who, None, files=files):
                out(line)
            return [n for n in P.nodes(store) if n.id not in before]

        def go(store):
            added = as_json(store) if text.lstrip().startswith(("{", "[")) else as_text(store)
            if not who.person and added:  # one leaf of the person's ask is theirs at once
                out(
                    G.one_line_ask(store, added, who, files, B.split(text)[1], here)  # the text's board items
                    or f"{len(added)} proposed: nobody can start {'it' if len(added) == 1 else 'them'} until "
                    "the person accepts, in `graphene watch`. Tell them the tree is ready, and stop"
                )
            return [n.id for n in added]

        warn_unreachable(write("plan propose", go) or [], files)
        said_where()

    @plan_cli.command("edit")
    def edit_(
        node_id: str = typer.Argument(None, help="Open only this node and what is under it."),
    ) -> None:
        """Open the plan as text in your editor ($VISUAL, $EDITOR, else vi).

        Graphene applies what you save, all or none. Turn "?" into "-" to accept a node."""
        edit_in_editor(node_id, alone=False)

    @plan_cli.command()
    def undo() -> None:
        """Undo your last act on the plan, such as a drop or an accept."""
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
    def accept(
        ids: list[str] = typer.Argument(None, help="The nodes to accept; every proposal if left out."),
    ) -> None:
        """Accept proposals into the plan.

        Graphene then says which leaves a run can reach, and why the rest wait."""

        files = tracked()  # asked before the plan's write lock, as `write` says

        def go(store):
            by_id = {n.id: n for n in P.nodes(store)}
            goal_was, told = P.goal(store), []
            accepted = P.accept(store, ids or [], P.caller(), files=files, told=told)
            took = None
            if not P.nodes(store, (P.PROPOSED,)):  # the whole plan is accepted: what the person left
                took = B.took(B.defaults(store, P.caller(), files), B.left(store))  # open takes its default
            if accepted:  # first, in a line: what the screen's bottom line gives of it, the defaults too
                out(f"accepted {', '.join(n.id for n in accepted)}" + (f"; {took}" if took else ""))
            for n in accepted:
                out(one_row(store, n, len(P.above(n, by_id))))
            for line in told:  # what in the plan now waits on what was accepted
                out(line)
            if P.goal(store) != goal_was:
                out(f"the plan: {P.goal(store)}  (the planner's sentence, accepted with its tree)")
            now = P.nodes(store)
            runs, waits = P.forecast(now, {n.id for n in now if P.came_back(store, n)})
            out("left alone, agents can reach: " + (", ".join(n.id for n in runs) or "nothing"))
            for n, why in waits:
                out(f"  {n.id} will wait: {'; '.join(why)}")
            return [n.id for n in accepted]

        warn_unreachable(write("plan accept" + (f" {' '.join(ids)}" if ids else ""), go) or [])
        said_where()

    @plan_cli.command("log")
    def log_() -> None:
        """Print everything that happened on the plan, oldest first.

        A `*` marks what belonged to no node."""

        def go(store):
            entries = store.node_log()
            wide = max((len(e["node_id"]) for e in entries), default=1)
            who_wide = max((len(e["actor"] or "") for e in entries), default=16)
            for e in entries:
                out(log_line(e, with_node=wide, who_wide=max(who_wide, 16)))

        run(go)

    @plan_cli.command(hidden=True)
    def record() -> None:
        """Print the record of the whole plan, every leaf's added up.

        `graphene node show` prints one leaf's record."""
        from .node_record import bill, bill_line, rolled_up

        def go(store):
            for line in rolled_up(store, root(), P.leaves(P.nodes(store))):
                out(line.replace("under it", "in the plan"))
            usage = store.node_log("*", ("usage",))  # the planner's, and each helper's under its own name
            for actor in dict.fromkeys(e["actor"] for e in usage):
                whose = "the planner's" if actor.startswith("planner") else f"{actor}'s"
                for line in bill_line(bill([e for e in usage if e["actor"] == actor]), "    "):
                    out(line.replace("bill:", f"{whose} bill:"))

        run(go)

    @plan_cli.command()
    def archive() -> None:
        """Put finished nodes away.

        When nothing else is left, the plan is no longer in force."""
        gone = run(lambda s: P.archive(s, P.caller()))
        out(f"archived {', '.join(n.id for n in gone)}" if gone else "nothing finished to archive")
        said_where()

    @plan_cli.command(hidden=True)
    def ack() -> None:
        """Make the uncommitted changes no leaf made yours, as they stand.

        A commit does the same. The plan follows the repository."""
        paths = run(lambda s: P.acknowledge(s, checkout(), P.caller()))
        out(f"yours as they stand: {', '.join(paths)}" if paths else "no uncommitted change is left unowned")
        said_where()

    @plan_cli.command()
    def pause() -> None:
        """Pause the plan: nothing starts and no write is refused.

        `graphene plan resume` puts the plan back in force."""
        run(lambda s: P.set_paused(s, True, P.caller()))
        out("paused: nothing starts and nothing is enforced until `graphene plan resume`")
        said_where()

    @plan_cli.command(hidden=True)
    def prompts(
        how: str = typer.Argument(None, help="leaf, the default, or strict; prints the setting if left out."),
    ) -> None:
        """Set what a prompt typed into a session means while a plan is in force.

        With leaf, the first write makes the prompt a leaf. With strict, a session with no node
        writes nothing."""
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
        how: str = typer.Argument(None, help="on, auto or off; prints the setting if left out."),
    ) -> None:
        """Set whether an agent proposes before it writes, and what waits for you.

        On: every ask waits. Auto: one small leaf is yours at once, more waits. Off never proposes."""
        if how not in (None, *P.FIRST):
            fail(f"graphene plan first takes on, auto or off, not {how!r}", 1)
        if how is not None:
            run(lambda s: P.set_plan_first(s, how, P.caller()))
        now = run(P.plan_first)
        out(f"plan first: {now}. {FIRST_SAID[now]}")
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
            help="Use this executor, not init's: claude, codex, nemotron or a command.",
        ),
        attempts: int = typer.Option(3, "--attempts", help="How often a refused executor is sent back."),
        node: list[str] = typer.Option(None, "--node", help="Only this node; repeat it."),
        parallel: int = typer.Option(1, "--parallel", help="How many leaves run at once."),
        here: bool = typer.Option(
            False, "--here", help="Run in your checkout and commit nothing; the checkout is exposed."
        ),
    ) -> None:
        """Run every ready leaf in its own worktree, one executor per leaf.

        Graphene runs each leaf's check and merges what passes. A leaf that fails comes back."""
        if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
            fail("an executor or a planner does not start runs: through --with a run is any command", 1)
        from .run import named, run_parallel, run_plan, summary, sweep

        r = root()
        with open_store(r) as store:
            if not P.nodes(store, (P.OPEN, P.RUNNING)):
                sweep(store, out, r)  # a dead parallel run's finished leaves are parked, and said, first
            if not P.nodes(store, (P.OPEN, P.RUNNING)):
                waiting = len(P.leaves(P.nodes(store, (P.PROPOSED,))))
                fail(f"nothing to run: the tree is a proposal ({_leaves(waiting)}) nobody has accepted: "
                     "`graphene plan accept`, or y on the goal in `graphene watch`, accepts it"
                     if waiting else "nothing to run: the plan has no open leaf", 1)  # fmt: skip
            try:  # --with, else the repo's (`graphene init`); neither, and nothing starts
                template = named(executor or store.meta("executor"))
            except P.Refused as no:
                fail(str(no), 1)
            said_where()  # first: a run changes the plan for as long as it goes
            who = P.caller()
            # a run that starts nothing answers nothing on the board
            starts = [n for n in P.ready(P.nodes(store), who) if not P.came_back(store, n)
                      and (not node or n.id in node)]  # fmt: skip
            if who.person and starts and any(B.has_default(it) for it in B.items(store)):  # R takes the rest
                files = P.tracked(r)  # before the write lock, never under it

                class NothingStarts(Exception):  # the defaults would leave no leaf to start: none is taken
                    pass

                def startable(n: P.Node) -> bool:  # a condition a default set binds at start, as `start` asks
                    try:
                        P._keeps_standing(P.get(store, n.id), P.standing(store), files)
                    except P.Refused:
                        return False
                    return True

                took = None
                with contextlib.suppress(NothingStarts), P.undoable(store, who, "board take"):
                    said = B.took(B.defaults(store, who, files), B.left(store))
                    if not any(startable(n) for n in starts):
                        raise NothingStarts  # rolls the takes back: the run then says why nothing starts
                    took = said
                if took:
                    out(took)
            logs = r / ".graphene" / "runs"
            since = len(store.node_log())  # what this run did is what the log says after this
            try:
                if here:
                    out("--here: your checkout is exposed. The executor writes in it. Nothing is committed")
                    run_plan(store, checkout(), template, attempts, node or None, out, logs)
                else:
                    run_parallel(
                        lambda: open_store(r), r, checkout(), max(parallel, 1), template,
                        attempts, node or None, out, logs,
                    )  # fmt: skip
            except P.Refused as no:
                fail(str(no), 1)
            except KeyboardInterrupt:
                out(summary(store, since, stopped=True))
                raise typer.Exit(130) from None
            left = P.uncommitted(store, checkout()) if here else []  # a worktree's leaf committed its own
            out(summary(store, since) + (f" · the work of {', '.join(left)} is {P.UNCOMMITTED}" * bool(left)))

    def planner(
        sentence: str, executor: str | None, about: str | None, split: bool, size: str | None = None
    ) -> None:
        from .ask import ask, named

        who = P.caller()
        if not who.person:
            fail("asking a planner is the person's: it starts an agent, and spends\n"
                 "  propose the tree yourself: graphene plan propose - <<'EOF' … EOF", 1)  # fmt: skip

        def go(store):
            spec = executor or store.meta("planner")  # --with, else the repo's (`graphene init`); or refused
            said = ask(store, checkout(), sentence, named(spec), about, split, out, size, planner=spec)
            for line in said:
                out(line)
            ids, (waits, _) = list(getattr(said, "ids", [])), B.waiting(store)
            here = "GRAPHENE_WATCH" in os.environ  # typed at `graphene watch`'s `:`: the screen is open
            if said and waits:  # what waits on the person is named first, where they would find it
                hint = "at the top, y takes, d drops" if here else "`graphene board`, or `graphene watch`"
                out(f"the board waits on you ({waits}): {hint}")
            if ids or (said and not waits):
                hint = (
                    "y accepts, d drops"
                    if here
                    else "`graphene watch` (y accepts, d drops), or `graphene plan edit`"
                )
                out(f"prune it: {hint}")
            return ids

        proposed = run(go)
        warn_unreachable(proposed or [])
        said_where()

    @cli.command("ask")
    def ask_(
        sentence: str = typer.Argument(..., help="What you want, as you would say it."),
        executor: str = typer.Option(
            None,
            "--with",
            help="Use this planner, not init's: claude, codex, nemotron or a command.",
        ),
        about: str = typer.Option(
            None, "--about", help="The node this ask is about, such as a leaf that came back."
        ),
        finer: bool = typer.Option(False, "--finer", help="Size this ask finer, whatever the saved size."),
        coarser: bool = typer.Option(
            False, "--coarser", help="Size this ask coarser, whatever the saved size."
        ),
    ) -> None:
        """Ask the planner for a tree from a paragraph.

        The planner reads the repo and writes nothing. Nothing runs until you accept the tree."""
        if finer and coarser:
            fail("--finer or --coarser, not both", 2)
        planner(sentence, executor, about, False, "finer" if finer else "coarser" if coarser else None)

    if N := extra.load("note"):
        N.register(plan_cli, root, open_store, fail)  # `graphene plan note`

    # -- graphene node ----------------------------------------------------------------------------

    node_cli = typer.Typer(
        help="Add, change, finish or read one node of the plan.\n\n"
        "A node has a title, a goal, a scope, a check and the nodes it waits on."
    )
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
            None, "--scope", help="A glob the node may write; repeat it, and '!glob' excludes."
        ),
        check: str = typer.Option(
            None, "--check", help="The command that must pass for the node to be done, run with sh."
        ),
        goal: str = typer.Option(None, "--goal", help="What the work should achieve, in a sentence or two."),
        needs: list[str] = typer.Option(None, "--needs", help="A node this one waits on; repeat it."),
        owner: str = typer.Option(None, "--owner", help="'agent' (default), 'me', or a person's name."),
        signoff: bool = typer.Option(
            False, "--signoff", help="Require a person's sign-off as well as the check."
        ),
        node_id: str = typer.Option(None, "--id", help="An id of your choosing; else n1, n2, …"),
        parent: str = typer.Option(
            None, "--parent", help="The node this one helps achieve; under a leaf, this splits the leaf."
        ),
    ) -> None:
        """Add a node to the plan.

        A person's node is in the plan at once. An agent's node is a proposal."""
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
            told: list[str] = []
            [n] = P.propose(store, [item], P.caller(), files=files, told=told)
            out(one_row(store, n))
            for line in told:
                out(line)
            return [n.id]

        warn_unreachable(write(f"node add {title!r}", go), files)
        said_where()

    @node_cli.command("set")
    def set_(
        node_id: str = typer.Argument(...),
        title: str = typer.Option(None, "--title", help="Replaces the title."),
        scope: list[str] = typer.Option(None, "--scope", help="Replaces the scope; repeat it."),
        add_scope: list[str] = typer.Option(None, "--add-scope", help="Adds a glob to the scope; repeat it."),
        check: str = typer.Option(None, "--check", help="Replaces the check."),
        goal: str = typer.Option(None, "--goal", help="Replaces the goal."),
        add_goal: str = typer.Option(None, "--add-goal", help="Adds a sentence at the end of the goal."),
        needs: list[str] = typer.Option(None, "--needs", help="Replaces what it waits on; 'none' clears it."),
        owner: str = typer.Option(None, "--owner", help="'agent', 'me', or a person's name."),
        signoff: bool = typer.Option(
            None, "--signoff/--no-signoff", help="Require a person's sign-off, or not."
        ),
        parent: str = typer.Option(None, "--parent", help="Move it under another node; 'none' is the top."),
    ) -> None:
        """Change a node's contract.

        Only a person can. The change binds the node's next write and next start."""
        edits = changes(title=title, scope=scope, check=check, goal=goal, owner=owner, parent=parent)
        if needs:
            edits["needs"] = [i for i in needs if i != "none"]
        if signoff is not None:
            edits["signoff"] = signoff
        for said, adds in (("scope", add_scope), ("goal", add_goal)):
            if adds and said in edits:
                fail(f"--{said} replaces the {said} and --add-{said} adds to it: one or the other", 2)
        if not (edits or add_scope or add_goal):
            fail(f"graphene node set {node_id} needs what to change: --title, --scope, --check, --goal, "
                 "--needs, --owner, --signoff or --parent", 1)  # fmt: skip

        files = tracked()
        told: list[str] = []

        def go(store):
            now = P.get(store, node_id)  # added to as it is at this moment, so an edit made since stays
            seen = len(store.node_log(node_id, ("edited",)))
            if add_scope:
                edits["scope"] = [*now.scope, *(g for g in dict.fromkeys(add_scope) if g not in now.scope)]
            if add_goal:
                edits["goal"] = P.goal_plus(now.goal, add_goal) or now.goal
            node = P.edit(store, node_id, edits, P.caller(), files=files, told=told)
            return node, store.node_log(node_id, ("edited",))[seen:]  # yours, then a need Graphene added

        n, rows = write(f"node set {node_id}", go)
        if not rows:
            out(f"{n.id} is unchanged (revision {n.rev})")
            said_where()
            return
        out(f"{n.id} is now revision {n.rev}:")
        for name, (before, after) in (c for e in rows for c in e["detail"]["changed"].items()):
            out(f"  {name}: {value(before)} → {value(after)}")
        for line in told:
            out(line)
        if n.state == P.RUNNING:
            out(f"{n.id} is running on revision {n.told_rev}: its next write is held to the new scope, and "
                "its `done` to the new check")  # fmt: skip
        warn_unreachable([node_id], files)
        said_where()

    @node_cli.command()
    def drop(
        node_ids: list[str] = typer.Argument(..., help="The node; name several to drop them at once."),
    ) -> None:
        """Drop a node from the plan, with everything under it.

        `graphene plan undo` puts the nodes back. Dropping a split's children undoes the split."""
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
        """Open one node's contract as text in your editor.

        Graphene applies what you save. A line you add under the node is a new child."""
        edit_in_editor(node_id, alone=True)

    @node_cli.command(hidden=True)
    def start(node_id: str = typer.Argument(...)) -> None:
        """Take a node and print its contract as it stands now.

        An executor runs this before it writes."""

        def go(store):
            n = P.start(store, node_id, P.caller(), checkout())
            out(P.contract(n, P.trail(store, n), B.decided(store, n)))
            for note in P.notes(store, n.id):
                out(f"  sent back with: {note}")

        run(go)
        said_where()

    @node_cli.command()
    def done(
        node_id: str = typer.Argument(None, help="The node; may be left out when you hold exactly one."),
        override: str = typer.Option(None, "--override", help="A person's reason for overruling the gate."),
    ) -> None:
        """Finish a node: Graphene runs its check and asks git what changed.

        Graphene then says what is next."""
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
            None, "--why", help="What is in the way, for the person; asked for at a terminal."
        ),
        wants: list[str] = typer.Option(
            None,
            "--wants",
            help="A path the node needs outside its scope, offered to the person; repeat it.",
        ),
    ) -> None:
        """Hand a running node back, and say why.

        Use this when the node cannot be finished as written."""
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

    @node_cli.command("signoff", hidden=True)
    def signoff_(node_id: str = typer.Argument(...)) -> None:
        """Sign off a node: a person's say-so that it is done."""

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

    @node_cli.command(hidden=True)
    def reopen(
        node_id: str = typer.Argument(...),
        note: str = typer.Option(
            None, "--note", help="What is wrong, told to whoever takes it next; asked for at a terminal."
        ),
    ) -> None:
        """Send a finished node back, with what is wrong."""
        if note is None and run(lambda s: P.get(s, node_id).state in (P.DONE, P.REVIEW)):  # else its refusal
            note = asked(f"graphene node reopen {node_id}", "--note", "what is wrong")
        run(lambda s: P.reopen(s, node_id, P.caller(), note or ""))
        out(f"{node_id} is open again; whoever takes it next is shown your note (its contract is as it was: "
            f"`graphene node edit {node_id}` changes it)")  # fmt: skip
        said_where()

    @node_cli.command()
    def show(node_id: str = typer.Argument(...)) -> None:
        """Print a node's contract and its record.

        The record says who held the node, what changed, what was refused and what is verified."""
        from .node_record import node_record, render, rolled_up

        def go(store):
            n = P.get(store, node_id)
            out(P.contract(n, P.trail(store, n), B.decided(store, n)))
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
        if n.state == P.OPEN and P.not_offered(store, n):
            lines.append(f"    {P.not_offered(store, n)}")
        if n.state == P.OPEN and P.RUN_TREE in (n.checkout or "") and Path(n.checkout or "").is_dir():
            lines.append(f"  its last attempt is kept in {n.checkout} (branch graphene/{n.id})")
        return lines

    @node_cli.command(hidden=True)
    def split(
        node_id: str = typer.Argument(...),
        executor: str = typer.Option(
            None, "--with", help="Use this planner, not the one `graphene init` chose."
        ),
    ) -> None:
        """Ask the planner to cut a leaf into smaller leaves.

        The new leaves are proposals for you to prune."""
        planner(f"split {node_id} into smaller leaves", executor, node_id, True)

    @node_cli.command()
    def widen(
        node_id: str = typer.Argument(...),
        paths: list[str] = typer.Argument(
            None, help="The paths to add; every path the leaf asked for if left out."
        ),
    ) -> None:
        """Widen a leaf's scope to the paths it came back needing."""

        files = tracked()

        def go(store):
            n = P.widen(store, node_id, paths or [], P.caller(), files=files)
            out(f"{n.id}'s scope is now {', '.join(n.scope)}; it is ready again")

        write(f"node widen {node_id}", go)
        said_where()

    @node_cli.command()
    def sibling(
        node_id: str = typer.Argument(...),
        paths: list[str] = typer.Argument(
            None, help="The paths for the new leaf; every path asked for if left out."
        ),
    ) -> None:
        """Add a leaf beside one that came back, for the paths it needed.

        The leaf that came back waits on the new one."""

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
