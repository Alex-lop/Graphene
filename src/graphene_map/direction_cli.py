"""`graphene direction`: the direction above the plans, with every session attached, at the command
line. One command for each act, so a key a screen gives it is a command a person could type."""

from __future__ import annotations

import json
import shutil
import sys
import textwrap

import typer
from rich.console import Console
from rich.text import Text

from . import direction as D
from . import plan as P
from . import plan_text as T

EMPTY = (
    f"no direction yet ({D.FILE}). An agent proposes one (`graphene direction propose -`, one line a "
    "node: `? title  [id]`, indented for the tree), or write the file yourself"
)
ACTS = "graphene direction accept ID · drop ID · plan NODE · attach SESSION NODE|none · edit · propose -"


def register(cli: typer.Typer, root, open_store, fail):
    out = typer.echo
    app = typer.Typer(
        help="The direction: the goals above the plans, with every plan and session hanging from one.",
        invoke_without_command=True,
    )
    cli.add_typer(app, name="direction")

    def load(required: bool = True) -> D.Direction | None:
        try:
            d = D.read(root())
        except P.Refused as no:
            fail(str(no), 1)
            raise AssertionError from None  # unreachable: fail() exits
        if d is None and required:
            fail(EMPTY, 1)
        return d

    def changed(what: str, act) -> None:
        """A read-modify-write of the file under the store's write lock, so two acts never interleave;
        written whole or not at all."""
        with open_store(root()) as store, store.claim():
            d = load(required=what != "propose")
            d = d or D.Direction([], [])
            try:
                said = act(store, d)
                D.write(root(), d)
            except P.Refused as no:
                fail(str(no), 1)
            store.log_node("*", P._now(), "direction", P.caller().label, None, None, {"note": said})
        out(said)
        if D.ignored_by_git(root()):
            typer.echo(f"  git ignores {D.FILE} here: `git add -f {D.FILE}` commits it", err=True)
        typer.echo(f"  (the direction of {P.where(root())})", err=True)

    @app.callback()
    def show(
        ctx: typer.Context,
        as_text: bool = typer.Option(False, "--text", help="The file as it is: the form `propose` reads."),
        as_json: bool = typer.Option(
            False, "--json", help="The direction, the plan and every session, as the page reads them."
        ),
        width: int = typer.Option(None, "--width", help="The columns ($COLUMNS if left out)."),
    ) -> None:
        """Print the direction as a tree, each node with what waits on you below it, what runs and what
        is next; the plan under the node it hangs from, and each session under what it works on. A
        session quiet for a day is left out."""
        if ctx.invoked_subcommand is not None:
            return
        d = load(required=False)
        if as_text:
            if d is None:
                fail(EMPTY, 1)
            sys.stdout.write(d.text())
            return
        with open_store(root()) as store:
            st = D.status(store, d)
        if as_json:
            out(json.dumps(st, ensure_ascii=False, indent=2))
            return
        if d is None and not st["sessions"] and st["plan"] is None:
            fail(EMPTY, 1)
        wide = width or shutil.get_terminal_size().columns
        console = Console(width=wide, highlight=False)
        plain = not (console.is_terminal and not console.no_color)
        said = [(D.head(st, P.where(root()), wide), "bold"), *D.lines(st, wide)]
        if d is None:
            said.insert(1, (EMPTY, "dim"))
        if st["older"]:
            said.append(
                (
                    f"  {st['older']} older session{'s' if st['older'] > 1 else ''} left out: "
                    "quiet for a day",
                    "dim",
                )
            )
        said += [(part, "dim") for part in textwrap.wrap(ACTS, wide, break_on_hyphens=False)]
        for line, style in said:
            if plain:
                out(line)
            else:
                console.print(Text(line, style=style), no_wrap=True, crop=True)

    @app.command("propose")
    def propose(
        source: str = typer.Argument("-", help="`-` reads the text from stdin."),
        under: str = typer.Option(None, "--under", help="The node to put it under; the top if left out."),
    ) -> None:
        """Add nodes, in the file's own text (`? title  [id]`, indented for the tree, lines under a node
        for what it is for). From an agent every node is a proposal until the person accepts it."""
        if source != "-":
            fail("propose reads the text from stdin: `graphene direction propose - <<'EOF' … EOF`", 2)
        text = sys.stdin.read()
        who = P.caller()

        def act(store, d):
            ids = D.propose(d, text, who, under)
            mark = "proposed" if not who.person else "added"
            return f"{mark} {', '.join(ids)}" + (
                "" if who.person else ": the person accepts them (`graphene direction accept ID`)"
            )

        changed("propose", act)

    @app.command("accept")
    def accept(ids: list[str] = typer.Argument(..., help="The nodes to accept.")) -> None:
        """Accept proposed nodes, with the proposals they sit under and those under them. The person's."""
        changed(
            "accept",
            lambda store, d: "accepted " + (", ".join(D.accept(d, ids, P.caller())) or "nothing new"),
        )

    @app.command("drop")
    def drop(node: str = typer.Argument(..., help="The node to drop, with what is under it.")) -> None:
        """Drop a node and what is under it. The person's."""
        changed("drop", lambda store, d: "dropped " + ", ".join(D.drop(d, node, P.caller())))

    @app.command("plan")
    def hang(
        node: str = typer.Argument(..., help="The direction node the plan in force hangs from."),
    ) -> None:
        """Hang the plan in force from a node. The person's. An earlier plan keeps its node."""
        d = load()
        with open_store(root()) as store:
            try:
                goal = D.hang(store, d, node, P.caller())
            except P.Refused as no:
                fail(str(no), 1)
        out(f"the plan ({T.elide(goal, 60)}) hangs from {node}")

    @app.command("attach")
    def attach(
        session: str = typer.Argument(..., help="The start of a session's or a subagent's id."),
        node: str = typer.Argument(..., help="The direction node, or `none` to undo the attachment."),
    ) -> None:
        """Attach a session (or one subagent) to a node. The person's. A session that works on the plan
        is attached through the plan's node without this; `none` gives it back to that, or to unattached."""
        d = load(required=node != "none")
        with open_store(root()) as store:
            try:
                short = D.attach(store, d, session, None if node == "none" else node, P.caller())
            except P.Refused as no:
                fail(str(no), 1)
        out(f"{short} attached to {node}" if node != "none" else f"{short} is no longer attached by you")

    @app.command("edit")
    def edit() -> None:
        """The direction in your editor. Saved, it is read back whole: a line it cannot read goes back
        to the editor with the reason under it, and nothing is written until every line reads."""
        who = P.caller()
        if not who.person:
            fail("editing the direction is the person's: propose instead (`graphene direction propose -`)", 1)
        def on_disk() -> str:  # the file as it is, even one that does not read (a merge, a hand edit)
            try:
                return D.path(root()).read_text(encoding="utf-8")
            except FileNotFoundError:
                return ""
            except UnicodeDecodeError:
                fail(f"{D.FILE} is not UTF-8: open it in an editor that can save it as UTF-8", 1)
                raise AssertionError from None  # unreachable: fail() exits

        was = on_disk()
        path = T.edit_path(root(), "direction")
        try:
            D.parse(was)
            path.write_text(was, encoding="utf-8")
        except P.Refused as no:  # it goes to the editor with the reason under its line, to be mended
            path.write_text(T._annotated(was, str(no).split("\n", 1)[1].strip()), encoding="utf-8")
        while True:
            if T.run_editor(path) != 0:
                fail(f"the editor exited with an error; nothing was written (your text is in {path})", 1)
            said = path.read_text(encoding="utf-8").splitlines(keepends=True)
            text = "".join(line for line in said if not line.lstrip().startswith(T._REFUSED))
            try:
                new = D.parse(text)
            except P.Refused as no:
                if not sys.stdin.isatty():
                    fail(f"{no}\n  nothing was written; your text is in {path}", 1)
                path.write_text(T._annotated(text, str(no).split("\n", 1)[1].strip()), encoding="utf-8")
                continue
            break
        with open_store(root()) as store, store.claim():
            if on_disk() != was:
                fail(f"{D.FILE} changed while you edited it; nothing was written (your text is in {path})", 1)
            D.write(root(), new)
            store.log_node(
                "*", P._now(), "direction", who.label, None, None, {"note": "edited the direction"}
            )
        path.unlink(missing_ok=True)
        out(f"the direction: {len(new.nodes)} nodes, {sum(n.proposed for n in new.nodes)} proposed")
