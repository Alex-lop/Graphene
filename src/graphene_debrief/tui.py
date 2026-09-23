"""`graphene watch`: the plan on one screen, with vim keys.

A view over commands and text, never the only way to do anything: every key runs a `graphene`
command that exists on its own (the status line says which), editing opens the plan's text in the
person's $EDITOR, and a run or a planner started from here is its own process, which goes on when
this screen is closed. The left pane is the tree; the right one (below it, when the terminal is
narrow) is the selected node: its contract, and while it runs, which executor, where, what it did
last and how long ago; when it came back, the fixes it offers. The top line says which repository
and which plan, so a stray `cd` fools nobody; the bottom line names the two agents: the planner,
which proposes, and the executors, which `run` starts.
"""

from __future__ import annotations

import contextlib
import io
import os
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static, Tree

from . import plan as P
from . import plan_text as T
from . import run as R

GLYPH = {
    P.PROPOSED: ("?", "bold cyan"),
    P.OPEN: ("○", ""),
    P.RUNNING: ("●", "bold yellow"),  # not ▶: the tree draws that for a folded branch
    P.REVIEW: ("◆", "bold magenta"),
    P.DONE: ("✓", "green"),
}
RUN_WITH = "--parallel 4"  # `R` and `r`: ready leaves at once, a worktree each, landed here as they pass
HELP = """\
move     j k   gg G   / search   n next      fold  za zo zc   zR all open   zM all closed
shape    a sibling   A child   e edit this contract   E edit this subtree as text
         d drop   s split (the planner)   y accept   u undo   V select several, then y or d
run      R run everything ready   r run this subtree   x release (running) or reopen (done)
see      Enter the record   l the executor's output   ctrl-d ctrl-u scroll it
a leaf that came back:  w widen its scope   b a sibling for what it wanted   n wait on what it names
                        ? ask the planner (elsewhere ? is this help)
:        any graphene command, as you would type it (`:node show x`, `:plan log`), and
         :ask <what you want>   the planner proposes it       :stop   stops a run started here
q quit (a run started here goes on; `:stop` stops it)

Each key is a command you can type yourself; the bottom line says which one it ran.
The planner proposes the tree (a session, or :ask); the executors do its leaves (R, r)."""


def _cli(argv: list[str]) -> tuple[int, str]:
    """A `graphene` command, run here, as the person at this terminal: its exit code and what it said."""
    import typer.main

    from .cli import build

    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            result = typer.main.get_command(build()).main(argv, prog_name="graphene", standalone_mode=False)
            code = result if isinstance(result, int) else 0
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else 1
        except Exception as error:  # a click usage error, or a bug: said, never a crash of the screen
            code, _ = 2, out.write(f"{type(error).__name__}: {error}")
    return code, out.getvalue().strip()


class Ask(ModalScreen[str | None]):
    """One line typed for a command that needs words (a title, a note, what to ask the planner)."""

    BINDINGS = [Binding("escape", "cancel", show=False)]
    AUTO_FOCUS = "#ask"
    DEFAULT_CSS = """
    Ask { align: center bottom; }
    Ask > Input { width: 100%; margin: 0 0 1 0; }
    """

    def __init__(self, prompt: str, value: str = "") -> None:
        super().__init__()
        self.prompt, self.value = prompt, value

    def compose(self) -> ComposeResult:
        yield Input(value=self.value, placeholder=self.prompt, id="ask")

    @on(Input.Submitted)
    def done(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,question_mark", "app.pop_screen", show=False)]
    DEFAULT_CSS = """
    Help { align: center middle; }
    Help > Static { width: auto; max-width: 100%; padding: 1 2; border: round $primary; }
    Help > Static { background: $surface; }
    """

    def compose(self) -> ComposeResult:
        yield Static(Text(HELP), id="help")


class PlanTree(Tree[str]):
    """The tree, with vim's movement and folding. Two-key sequences (gg, za, …) are read here, so
    the `a` of `za` never adds a node."""

    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("G", "scroll_end_node", show=False),
        Binding("enter", "app.record", show=False),
    ]
    CHORDS = {
        "gg": "top",
        "za": "toggle_node",
        "zo": "open",
        "zc": "close",
        "zR": "open_all",
        "zM": "close_all",
    }
    pending = ""

    async def on_key(self, event) -> None:
        char = event.character or ""
        if self.pending:
            sequence, self.pending = self.pending + char, ""
            event.stop()
            event.prevent_default()
            if sequence in self.CHORDS:
                await self.run_action(self.CHORDS[sequence])
            return
        if char in ("g", "z"):
            self.pending = char
            event.stop()
            event.prevent_default()

    def action_top(self) -> None:
        self.cursor_line = 0
        self.scroll_home(animate=False)

    def action_scroll_end_node(self) -> None:
        self.cursor_line = max(self.last_line, 0)
        self.scroll_end(animate=False)

    def action_open(self) -> None:
        if self.cursor_node is not None:
            self.cursor_node.expand()

    def action_close(self) -> None:
        node = self.cursor_node
        if (
            node is not None
            and not node.is_expanded
            and node.parent is not None
            and node.parent is not self.root
        ):
            node = node.parent  # closing a leaf closes what it is in, as vim's zc does in a fold
        if node is not None:
            node.collapse()
            self.move_cursor(node)

    def action_open_all(self) -> None:
        self.root.expand_all()

    def action_close_all(self) -> None:
        node = self.cursor_node
        while node is not None and node.parent is not None and node.parent is not self.root:
            node = node.parent
        for top in self.root.children:
            top.collapse_all()
        _ = self.last_line
        if node is not None:
            self.move_cursor(node)


class Watch(App):
    """The plan, live, on one screen."""

    CSS = """
    Screen { layout: vertical; }
    #where { height: 1; background: $boost; color: $text; padding: 0 1; }
    #main { height: 1fr; layout: horizontal; }
    #tree { width: 1fr; min-width: 30; }
    #side { width: 1fr; border-left: solid $primary; padding: 0 1; }
    Screen.-narrow #main { layout: vertical; }
    Screen.-narrow #tree { height: 3fr; width: 100%; }
    Screen.-narrow #side { height: 2fr; width: 100%; border-left: none; border-top: solid $primary; }
    #status { height: 2; background: $boost; padding: 0 1; }
    #line { dock: bottom; height: 1; border: none; padding: 0; display: none; }
    #line.-open { display: block; }
    """
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (110, "-wide")]
    AUTO_FOCUS = "#tree"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("question_mark", "help_or_ask", show=False),
        Binding("colon", "line(':')", show=False),
        Binding("slash", "line('/')", show=False),
        Binding("escape", "escape", show=False),
        Binding("n", "next_or_needs", show=False),
        Binding("a", "add(False)", show=False),
        Binding("A", "add(True)", show=False),
        Binding("e", "edit(True)", show=False),
        Binding("E", "edit(False)", show=False),
        Binding("d", "each('drop')", show=False),
        Binding("y", "each('accept')", show=False),
        Binding("s", "split", show=False),
        Binding("u", "undo", show=False),
        Binding("R", "run(False)", show=False),
        Binding("r", "run(True)", show=False),
        Binding("x", "release_or_reopen", show=False),
        Binding("l", "tail", show=False),
        Binding("V", "visual", show=False),
        Binding("w", "offer('w')", show=False),
        Binding("b", "offer('b')", show=False),
        Binding("ctrl+d", "page(1)", show=False),
        Binding("ctrl+u", "page(-1)", show=False),
    ]

    def __init__(self, root: Path, open_store: Callable, every: float = 1.0) -> None:
        super().__init__()
        self.root_path, self.open_store, self.every = root, open_store, every
        self.view = "contract"  # or "tail", "record": what the side pane shows for the selected node
        self.message = ""
        self.search = ""
        self.anchor: int | None = None  # the line visual selection started on
        self.shape: object = None  # what the tree was last built from: rebuilt only when it changed
        self.runs: list[subprocess.Popen] = []
        self.first = True
        self.known: set[str] = set()
        self.files: list[str] = []  # what git tracks, for the check that names a missing file
        self.files_at = 0.0

    # -- the screen ----------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="where")
        with Horizontal(id="main"):
            tree = PlanTree("the plan", id="tree")
            tree.show_root = False
            tree.guide_depth = 2
            yield tree
            with VerticalScroll(id="side"):
                yield Static(id="detail", markup=False)
        yield Static(id="status", markup=False)
        yield Input(id="line", select_on_focus=False)  # else the first key typed replaces the ":"

    def on_mount(self) -> None:
        self.refresh_plan()
        self.set_interval(self.every, self.refresh_plan)

    @property
    def tree(self) -> PlanTree:
        return self.query_one("#tree", PlanTree)

    def selected(self) -> str | None:
        node = self.tree.cursor_node
        return node.data if node is not None else None

    def chosen(self) -> list[str]:
        """The nodes a key acts on: the visual selection, else the one under the cursor."""
        if self.anchor is None:
            return [i for i in [self.selected()] if i]
        low, high = sorted((self.anchor, self.tree.cursor_line))
        out = []
        for line in range(low, high + 1):
            node = self.tree.get_node_at_line(line)
            if node is not None and node.data:
                out.append(node.data)
        return out

    def refresh_plan(self) -> None:
        with self.open_store() as store:
            nodes = [
                n for n in P.nodes(store) if n.state not in P.GONE and not (n.aside and n.state == P.DONE)
            ]
            goal, proposed = P.goal(store), store.meta("goal:proposed")
            by_id = {n.id: n for n in nodes}
            under = P.kids(nodes, drawn=True)
            back = {n.id for n in nodes if P.offers(store, n)}
            live = {n.id: R.live(store, n) for n in nodes if n.state == P.RUNNING}
            shape = [(n.id, n.parent, n.state, n.title, n.rev, n.id in back) for n in nodes]
            if shape != self.shape:
                self.rebuild(nodes, under, back)
                if self.shape is not None and self.view == "said":
                    self.view = "contract"  # the plan moved: what a `:` command printed is old news
                self.shape = shape
            self.relabel(by_id, under, back, live)
            self.say_where(goal, proposed, nodes, store)
            self.show_detail(store)

    def label(self, node: P.Node, under: dict, back: set[str], live: dict) -> Text:
        glyph, style = GLYPH.get(node.state, ("·", ""))
        if node.id in back:
            glyph, style = "↩", "bold red"
        text = Text()
        text.append(f"{glyph} ", style)
        text.append(" ".join(node.title.split()), "bold" if under.get(node.id) else "")
        text.append(f"  [{node.id}]", "dim")
        if node.id in live:
            seen = live[node.id]
            idle = f" · {seen['idle']}s" if seen.get("idle") is not None else ""
            text.append(f"  {seen['executor']}{idle}", "yellow")
        elif node.id in back:
            text.append("  came back", "red")
        if self.anchor is not None and node.id in self.chosen():
            text.stylize("reverse")
        return text

    def rebuild(self, nodes: list[P.Node], under: dict, back: set[str]) -> None:
        tree = self.tree
        y = tree.scroll_y
        was_open = {n.data for n in _walk(tree.root) if n.is_expanded}
        cursor = self.selected()
        tree.clear()
        placed = {None: tree.root}
        for node in nodes:
            parent = placed.get(node.parent) or tree.root
            has_kids = bool(under.get(node.id))
            finished = has_kids and all(c.state == P.DONE for c in P.below(node.id, nodes))
            opened = (not finished) if self.first else node.id in was_open or node.id not in self.known
            placed[node.id] = parent.add(Text(node.title), data=node.id, expand=opened, allow_expand=has_kids)
        self.known = {n.id for n in nodes}
        self.first = False
        if cursor in placed:
            _ = tree.last_line  # lays the new tree out, so the line of each node is known
            tree.cursor_line = placed[cursor].line
        tree.scroll_to(y=y, animate=False)

    def relabel(self, by_id: dict, under: dict, back: set[str], live: dict) -> None:
        for node in _walk(self.tree.root):
            if node.data in by_id:
                node.set_label(self.label(by_id[node.data], under, back, live))

    def say_where(self, goal: str, proposed: str | None, nodes: list[P.Node], store) -> None:
        home = str(Path.home())
        where = str(self.root_path)
        where = "~" + where[len(home) :] if where.startswith(home + os.sep) else where
        if len(where) > 32:  # the repository's own name and the one above it say which it is
            where = "…/" + "/".join(Path(where).parts[-2:])
        plan = " ".join((goal or proposed or "no goal yet").split())
        tag = " (proposed)" if proposed and not goal else ""
        self.query_one("#where", Static).update(
            Text.assemble((where, "bold"), "  ·  the plan", tag, ": ", plan)
        )
        leaves = [n for n in P.leaves(nodes) if not n.aside]
        done = sum(1 for n in leaves if n.state == P.DONE)
        running = [n for n in leaves if n.state == P.RUNNING]
        agents = [n for n in nodes if n.proposed_by and not n.proposed_by.startswith(P.person_name())]
        proposer = max(agents, key=lambda n: n.created_at or "").proposed_by if agents else None
        proposer = (proposer or "").removeprefix("planner:")
        planner = f"planner: {proposer}" if proposer else "planner: none yet (a session, or :ask)"
        names = sorted({n.executor or "?" for n in running})
        executors = (
            f"executors: {len(running)} running ({', '.join(names)})" if running else "executors: none"
        )
        counts = f"{done}/{len(leaves)} done"
        mode = "VISUAL · " if self.anchor is not None else ""
        said = self.message or "? help · : command · y accept · R run · q quit"
        self.query_one("#status", Static).update(f"{mode}{planner} · {executors} · {counts}\n{said}")

    def show_detail(self, store) -> None:
        node_id = self.selected()
        pane = self.query_one("#detail", Static)
        if node_id is None or store.node_row(node_id) is None:
            pane.update(Text("Nothing planned yet. Say what you want to your agent (it proposes the tree), "
                             "or :ask what you want.\n\n" + HELP))  # fmt: skip
            return
        node = P.get(store, node_id)
        if self.view == "tail":
            seen = R.live(store, node)
            lines = R.tail(seen.get("log"), 200)
            attempt, log = seen.get("attempt") or "-", seen.get("log") or "none yet"
            head = f"{node.id}: the executor's output, attempt {attempt} ({log})"
            pane.update(Text("\n".join([head, "", *(lines or ["(nothing yet)"])])))
            return
        if self.view == "record":
            _, said = _cli(["node", "show", node.id])
            pane.update(Text(said))
            return
        if self.view == "said":
            return  # what a `:` command printed stays until the cursor moves
        if time.monotonic() - self.files_at > 10:
            self.files, self.files_at = P.tracked(self.root_path), time.monotonic()
        pane.update(detail(store, node, self.root_path, self.files))

    # -- keys ------------------------------------------------------------------------------------

    def did(self, argv: list[str], quiet: bool = False, keep: bool = False):
        """Run one command, and say on the bottom line which it was and the gist of what it said.
        Returns its exit code, or with ``keep`` all it said."""
        code, said = _cli(argv)
        lines = [line for line in said.splitlines() if line.strip() and not line.startswith("  (the plan")]
        first = lines[0].strip() if lines else ""
        self.message = f"{'✗ ' if code else ''}graphene {shlex.join(argv)}" + (f": {first}" if first else "")
        if not quiet:
            self.refresh_plan()
        return said if keep else code

    @on(Tree.NodeHighlighted)
    def moved(self) -> None:
        if self.view == "said":
            self.view = "contract"
        if self.shape is not None:
            with self.open_store() as store:
                self.show_detail(store)

    def action_help_or_ask(self) -> None:
        node_id = self.selected()
        with self.open_store() as store:
            back = node_id is not None and store.node_row(node_id) and P.offers(store, P.get(store, node_id))
        if back:
            self.background(
                ["ask", f"{node_id} came back: propose what would let it be done", "--about", node_id]
            )
        else:
            self.push_screen(Help())

    def action_line(self, kind: str) -> None:
        line = self.query_one("#line", Input)
        line.value = kind
        line.add_class("-open")
        self.call_after_refresh(line.focus)  # shown first: a hidden input takes no focus
        line.cursor_position = len(kind)

    @on(Input.Submitted, "#line")
    def ran_line(self, event: Input.Submitted) -> None:
        text = event.value
        line = self.query_one("#line", Input)
        line.remove_class("-open")
        self.tree.focus()
        if text.startswith("/"):
            self.search = text[1:].strip().lower()
            self.find(self.search)
            return
        words = text[1:].strip()
        if not words:
            return
        try:
            argv = shlex.split(words)
        except ValueError as no:
            self.message = f"✗ {no}"
            return
        if argv[0] == "graphene":
            argv = argv[1:]
        if argv[:1] == ["stop"]:
            return self.stop_runs()
        if argv[:1] == ["ask"]:  # `:ask words, as typed`: one sentence, whatever it holds
            sentence = words.split(None, 1)[1] if len(argv) > 1 and not argv[1].startswith("-") else None
            return self.background(["ask", sentence] if sentence else argv)
        if argv[:1] in (["run"], ["ask"]) or argv[:2] == ["node", "split"]:
            return self.background(argv)
        if argv[:2] in (["plan", "edit"], ["node", "edit"]):
            return self.edit_with(argv)
        said = self.did(argv, keep=True)
        if said.count("\n") > 0:  # more than a line (a record, the log): it gets the side pane
            self.view = "said"
            self.query_one("#detail", Static).update(Text(said))

    def action_escape(self) -> None:
        line = self.query_one("#line", Input)
        if line.has_class("-open"):
            line.remove_class("-open")
            self.tree.focus()
        self.anchor = None
        self.view = "contract"
        self.refresh_plan()

    def find(self, text: str, after: int | None = None) -> None:
        if not text:
            return
        with self.open_store() as store:
            nodes = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
        hits = [n.id for n in nodes if text in n.title.lower() or text in n.id.lower()]
        if not hits:
            self.message = f"✗ nothing matches {text!r}"
            return
        current = self.selected()
        start = hits.index(current) + 1 if current in hits else 0
        target = hits[start % len(hits)]
        for node in _walk(self.tree.root):
            if node.data == target:
                parent = node.parent
                while parent is not None:
                    parent.expand()
                    parent = parent.parent
                _ = self.tree.last_line
                self.tree.move_cursor(node)
        self.message = f"/{text}: {hits.index(target) + 1} of {len(hits)}"
        self.refresh_plan()

    def action_next_or_needs(self) -> None:
        if self.search:
            return self.find(self.search)
        self.action_offer("n")

    def action_add(self, child: bool) -> None:
        node_id = self.selected()
        with self.open_store() as store:
            parent = node_id if child else (P.get(store, node_id).parent if node_id else None)

        def added(title: str | None) -> None:
            if title:
                self.did(["node", "add", title, *(["--parent", parent] if parent else [])])

        where = f"under {parent}" if parent else "at the top"
        self.push_screen(
            Ask(f"a new {'child' if child else 'sibling'} {where}: its title (s then fills it in)"),
            added,
        )

    def action_edit(self, alone: bool) -> None:
        node_id = self.selected()
        self.edit_with(
            ["node", "edit", node_id]
            if alone and node_id
            else ["plan", "edit", *([node_id] if node_id else [])]
        )

    def edit_with(self, argv: list[str]) -> None:
        from textual.app import SuspendNotSupported

        try:
            with self.suspend():
                self.did(argv, quiet=True)
        except SuspendNotSupported:  # no terminal to hand over (a test): the editor runs without one
            self.did(argv, quiet=True)
        self.shape = None
        self.refresh_plan()

    def action_each(self, what: str) -> None:
        ids = self.chosen()
        for node_id in ids:
            self.did(
                ["plan", "accept", node_id] if what == "accept" else ["node", "drop", node_id], quiet=True
            )
        if len(ids) > 1:
            self.message = f"{what} {', '.join(ids)}: " + self.message
        self.anchor = None
        self.refresh_plan()

    def action_split(self) -> None:
        if self.selected():
            self.background(["node", "split", self.selected()])

    def action_undo(self) -> None:
        self.did(["plan", "undo"])

    def action_run(self, here: bool) -> None:
        node_id = self.selected()
        argv = ["run", *shlex.split(RUN_WITH), *(["--node", node_id] if here and node_id else [])]
        self.background(argv)

    def action_release_or_reopen(self) -> None:
        node_id = self.selected()
        if node_id is None:
            return
        with self.open_store() as store:
            state = P.get(store, node_id).state
        if state == P.RUNNING:
            self.did(["node", "release", node_id, "--why", "the person released it, from graphene watch"])
        elif state in (P.DONE, P.REVIEW):

            def reopened(note: str | None) -> None:
                if note:
                    self.did(["node", "reopen", node_id, "--note", note])

            self.push_screen(Ask(f"reopen {node_id}: what is wrong (its next executor is told)"), reopened)
        else:
            self.message = f"{node_id} is {state}: x releases a running leaf, or reopens a finished one"

    def action_tail(self) -> None:
        self.view = "contract" if self.view == "tail" else "tail"
        self.refresh_plan()

    def action_record(self) -> None:
        self.view = "contract" if self.view == "record" else "record"
        self.refresh_plan()

    def action_visual(self) -> None:
        self.anchor = None if self.anchor is not None else self.tree.cursor_line
        self.refresh_plan()

    def action_offer(self, key: str) -> None:
        node_id = self.selected()
        if node_id is None:
            return
        with self.open_store() as store:
            offers = {k: argv for k, _, argv in P.offers(store, P.get(store, node_id))}
        if key in offers:
            self.did(offers[key])
        else:
            self.message = f"{node_id} has no '{key}' to offer: it did not come back wanting one"

    def action_page(self, way: int) -> None:
        side = self.query_one("#side", VerticalScroll)
        side.scroll_relative(y=way * max(side.size.height - 2, 3), animate=False)

    # -- what runs on its own ------------------------------------------------------------------------

    def background(self, argv: list[str]) -> None:
        """A run or a planner: its own process, with its output in .graphene/runs/, so it goes on
        whatever happens to this screen."""
        logs = self.root_path / ".graphene" / "runs"
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"{argv[0]}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        cli = "import sys; from graphene_debrief.cli import app; sys.argv[0] = 'graphene'; app()"
        with open(log, "w", encoding="utf-8") as sink:
            proc = subprocess.Popen(
                [sys.executable, "-c", cli, *argv], cwd=self.root_path, stdin=subprocess.DEVNULL,
                stdout=sink, stderr=subprocess.STDOUT, start_new_session=True,
            )  # fmt: skip
        self.runs.append(proc)
        self.message = f"graphene {shlex.join(argv)}: started (its output: {log.relative_to(self.root_path)})"
        self.follow(proc, argv, log)

    @work(thread=True)
    def follow(self, proc: subprocess.Popen, argv: list[str], log: Path) -> None:
        code = proc.wait()
        said = R.tail(log, 3)
        gist = next((line for line in reversed(said) if line.strip()), "")
        self.call_from_thread(
            self.finished, f"{'✗ ' if code else ''}graphene {shlex.join(argv)} ended: {gist}"
        )

    def finished(self, message: str) -> None:
        self.message = message
        self.view = "contract" if self.view == "said" else self.view
        self.refresh_plan()

    def stop_runs(self) -> None:
        """`:stop`: Ctrl-C to a run started here (or to the parallel run this repo has going): it hands
        back what it holds, and stops its executors."""
        pids = [p.pid for p in self.runs if p.poll() is None]
        lock = self.root_path / ".graphene" / "run.lock"
        with contextlib.suppress(OSError, ValueError):
            pids.append(int(lock.read_text()))
        for pid in set(pids):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGINT)
        self.message = (
            f"stopping {len(set(pids))} run(s): what they hold is handed back" if pids else "no run to stop"
        )


def _walk(node):
    for child in node.children:
        yield child
        yield from _walk(child)


def detail(store, node: P.Node, root: Path, files: list[str] | None = None) -> Text:
    """The selected node, for the person: what it is for, its contract, what is true of it now, and,
    when it came back, the fixes it offers, each with its key."""
    everything = [n for n in P.nodes(store) if n.state not in P.GONE]
    by_id = {n.id: n for n in everything}
    under = P.kids(everything, drawn=True)
    out = Text()
    out.append(f"{node.title}\n", "bold")
    out.append(f"[{node.id}] {node.state}, revision {node.rev}", "dim")
    out.append(f"   {'proposed by ' + node.proposed_by if node.state == P.PROPOSED else ''}\n", "cyan")
    if node.state == P.RUNNING:  # while it runs, this is what the person is looking for: first
        seen = R.live(store, node)
        out.append(f"running: {seen['executor']}, attempt {seen.get('attempt') or 1}", "bold yellow")
        if seen.get("idle") is not None:
            out.append(f", {seen['idle']} s since it did anything", "red" if seen["idle"] > 120 else "")
        if seen.get("checkout") and ".graphene" in seen["checkout"]:
            out.append(f"\n  in {seen['checkout'][seen['checkout'].index('.graphene') :]}")
        if seen.get("last"):
            out.append(f"\n  last: {seen['last']}")
        out.append("\n  l its output · x release it\n", "dim")
    offers = P.offers(store, node)
    if offers:  # it came back: why, and the keys that fix it, before anything else
        why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
        out.append("came back: ", "bold red")
        out.append(" ".join(str(why).split()) + "\n")
        for key, what, argv in offers:
            out.append(f"  {key}  ", "bold")
            out.append(f"{what}", "")
            out.append(f"   graphene {shlex.join(argv)}\n", "dim")
        out.append("  ?  ", "bold")
        out.append("ask the planner, when neither is right\n")
    trail = P.trail(store, node)[1 if P.goal(store) else 0 :]  # the goal itself is on the top line
    for depth, line in enumerate(trail):
        out.append(f"{'under: ' if depth == 0 else '       '}{'  ' * depth}{line}\n", "dim")
    out.append("\n")
    if not under.get(node.id):
        out.append("scope  ", "bold")
        out.append(
            ", ".join(node.scope) or "(none: a sub-goal whose leaves are still to come; s asks the planner)"
        )
        out.append("\ncheck  ", "bold")
        out.append(node.check or "(none)")
        missing = P.unreachable(node, P.tracked(root) if files is None else files, root)
        if missing:
            out.append(f"\n       ⚠ names {', '.join(missing)}: not in the repo, not in its scope", "yellow")
    elif node.check:
        out.append("check  ", "bold")
        out.append(f"{node.check}  (when its leaves are done: where they meet)")
    if node.needs:
        out.append("\nneeds  ", "bold")
        out.append(", ".join(node.needs))
    if node.owner != P.AGENT:
        out.append("\nowner  ", "bold")
        out.append(node.owner)
    if node.signoff:
        out.append("\n       and a person signs it off", "bold")
    out.append("\n")
    if node.goal and node.goal != node.title:
        out.append(f"\n{node.goal}\n")
    for note in T.notes(store, node, by_id, under):
        if offers and note.startswith(("handed back", "it wanted")):
            continue  # said at the top, with its keys
        out.append(f"\n{note}", "magenta" if note.startswith(("handed back", "it wanted")) else "")
    if node.state == P.PROPOSED:
        out.append("\n\ny accept · d drop · e edit its contract · E edit it with what is under it", "dim")
    return out


def run(root: Path, open_store: Callable, every: float = 1.0) -> None:
    Watch(root, open_store, every).run()
