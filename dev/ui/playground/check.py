"""The playground's check: drives the three screens headless and asserts what makes them worth having.

    uv run python dev/ui/playground/check.py          prints the numbers it measured, exits 0 when all hold

It reads no real plan except a throwaway one it builds itself, and writes nothing outside a temp folder.
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as A  # noqa: E402
import flowlayout as F  # noqa: E402
import territory as T  # noqa: E402
import views as V  # noqa: E402
from fixtures import PASTED_EDGES, PASTED_NODES  # noqa: E402
from model import demo_model, repo_model  # noqa: E402

REPORT: list[str] = []


def words(lines: list[V.Line]) -> int:
    """Tokens with a letter or digit: the measure the watch screen's frames were counted with."""
    return sum(
        1 for tok in " ".join(line.plain() for line in lines).split() if any(ch.isalnum() for ch in tok)
    )


def ok(cond: bool, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def say(text: str) -> None:
    REPORT.append(text)
    print(text)


def warm(m, seconds: int = 45) -> None:
    for _ in range(seconds * 4):
        m.tick(0.25)


# -- the layout, on its own --------------------------------------------------------------------------


def check_layout() -> None:
    lay = F.layout(PASTED_NODES, PASTED_EDGES, label_w=12)
    ok(len(lay.rects) == 10, "all ten nodes of the pasted graph are drawn")
    boxes = list(lay.rects.values())
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            apart = a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]
            ok(apart, "no two boxes overlap")
    text = lay.text()
    ok(text.count("▶") + text.count("◀") >= len(PASTED_EDGES), "every edge has an arrowhead")
    ok(len(lay.back) >= 1, "the feedback edge is found and drawn as a back edge")
    ok(lay.width <= 150, f"the pasted graph fits 150 columns at label width 12 (was {lay.width})")
    ok(F.layout(PASTED_NODES, PASTED_EDGES, label_w=12).text() == text, "the layout is deterministic")
    # a recolour never moves a node: positions are a function of the graph alone
    recoloured = [F.GNode(n.id, n.label, "running", "fox") for n in PASTED_NODES]
    again = F.layout(recoloured, PASTED_EDGES, label_w=12)
    ok(again.rects == lay.rects, "a state change does not move a node")
    say(
        f"flow: the pasted graph ({len(PASTED_NODES)} nodes, {len(PASTED_EDGES)} edges) is "
        f"{lay.width}x{lay.height} cells at label width 12"
    )
    # a neighbourhood fits where the whole does not
    near_n, near_e = F.neighbourhood(PASTED_NODES, PASTED_EDGES, "ai", 1)
    narrow = F.layout(near_n, near_e, label_w=12)
    ok(len(near_n) < 10 and narrow.width < lay.width, "a neighbourhood is smaller than the whole")
    say(f"flow: the neighbourhood of one node is {len(near_n)} nodes and {narrow.width} cells wide")
    # a graph that is not a chain, and a cycle among plain needs, both lay out
    ring = [F.GNode(x, x) for x in "abc"]
    L = F.layout(ring, [F.GEdge("a", "b"), F.GEdge("b", "c"), F.GEdge("c", "a")], label_w=8)
    ok(len(L.rects) == 3 and len(L.back) == 1, "a cycle becomes one back edge")


# -- the screens, headless -----------------------------------------------------------------------------


async def drive() -> None:
    m = demo_model()
    app = A.Playground(m)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.2)
        warm(m, 45)
        m.selected = "users"
        app.paint()
        await pilot.pause(0.1)
        canvas = app.query_one(A.Canvas)
        lines = canvas.lines
        ok(all(line.width() <= 80 for line in lines), "every cockpit line fits 80 columns")
        n80 = words(lines)
        say(f"cockpit at 80x24: {n80} words with one agent expanded (the watch screen today: about 145)")
        ok(n80 <= 100, f"the cockpit stays light: {n80} words")
        collapsed = V.build_cockpit(m, 80)
        m.selected = "river"
        quiet = words(V.build_cockpit(m, 80))
        m.selected = "users"
        say(f"cockpit at 80x24 with nothing expanded: {quiet} words")
        ok(quiet <= 66, f"nothing expanded, it is under 66 words (was {quiet})")
        ok(len(collapsed) > 5, "the cockpit has rows")

        # the numbers: pace, reach, proof, and a stall someone can see
        text = "\n".join(line.plain() for line in V.build_cockpit(m, 100))
        ok(
            "✎" in text and "✓" in text and any(c in text for c in "▁▂▃▄▅▆▇█"),
            "pace, files and proof are on the rows",
        )
        warm(m, 20)

        # linked selection: one cursor, three screens
        await pilot.press("j")
        first = m.selected
        await pilot.press("j")
        ok(m.selected != first, "j moves the selection")
        m.selected = "users"
        app.view = "flow"
        app.paint()
        await pilot.pause(0.1)
        ok(
            app.flow_layout is not None and "users" in app.flow_layout.rects,
            "the flow shows the selected task",
        )
        app.view = "territory"
        app.paint()
        ok(
            any(g.owners.get("users") for g in app.groups),
            "the territory shows what the selected task may touch",
        )
        app.view = "cockpit"
        app.paint()

        # answer: one key takes the default
        need0 = m.scoreboard()[0]
        m.selected = "keep"
        await pilot.press("enter")
        ok(m.scoreboard()[0] == need0 - 1 and m.questions[0].answer == "keep both", "Enter takes the default")

        # tell: one line, heard
        m.selected = "users"
        await pilot.press("t")
        ok(app.tell_open, "t opens the tell box")
        for ch in "keep ids as strings":
            await pilot.press("space" if ch == " " else ch)
        await pilot.press("enter")
        ok(
            m.tasks["users"].told and m.tasks["users"].told[-1][0] == "keep ids as strings",
            "the note is recorded",
        )
        warm(m, 3)
        ok(m.tasks["users"].told[-1][2] > 0, "the note is heard after a moment")

        # allow: a stopped write becomes territory
        warm(m, 30)
        users = m.tasks["users"]
        if not users.stopped:  # the scene stops a write at a point of its work: run on until it has
            warm(m, 40)
        ok(
            bool(users.stopped) or any("db/" in s for s in users.scope),
            "a write outside its territory was stopped",
        )
        if users.stopped:
            m.selected = "users"
            await pilot.press("w")
            ok(
                any(s.startswith("db/") for s in users.scope) and not users.stopped,
                "w gives the agent the folder it was stopped at",
            )

        # pull back
        oak = m.tasks["migrate"]
        oak.state = "running"
        m.selected = "migrate"
        await pilot.press("x")
        ok(oak.state == "came back", "x pulls an agent back")

        # paint: territory edits scope
        m.selected = "tests"
        before = list(m.tasks["tests"].scope)
        m.paint("tests", "docs/")
        ok(len(m.tasks["tests"].scope) == len(before) + 1, "painting a folder gives it to the selected task")
        m.paint("tests", "docs/")
        ok(m.tasks["tests"].scope == before, "painting it again takes it back")

        # a click is an action: the words on a row are its buttons
        m2 = demo_model()
        a2 = A.Playground(m2)
        async with a2.run_test(size=(100, 30)) as p2:
            await p2.pause(0.2)
            warm(m2, 5)
            a2.paint()
            cv = a2.query_one(A.Canvas)
            y = next(k for k, ln in enumerate(cv.lines) if ln.row == "keep")
            x = next(
                sum(len(s.text) for s in cv.lines[y].segs[:i])
                for i, s in enumerate(cv.lines[y].segs)
                if s.action == "take"
            )
            await p2.click(A.Canvas, offset=(x + 1, y))
            ok(m2.questions[0].answer == "keep both", "clicking the default answers the question")

    # two widths, three screens, no crash
    for size in ((80, 24), (120, 36), (60, 20)):
        m3 = demo_model()
        a3 = A.Playground(m3)
        async with a3.run_test(size=size) as p3:
            warm(m3, 20)
            for key in ("g", "m", "v", "v", "c", "b", "b"):
                await p3.press(key)
            await p3.pause(0.1)
    say("screens: cockpit, flow and territory run at 80x24, 120x36 and 60x20")


def check_screens() -> None:
    asyncio.run(drive())


# -- real data: a throwaway repository and its plan ------------------------------------------------


def check_real_plan() -> None:
    from graphene_map import plan as P
    from graphene_map.store import Store

    with tempfile.TemporaryDirectory(prefix="playground-") as tmp:
        root = Path(tmp)

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

        git("init", "-q", "-b", "main")
        for rel in ("api/a.py", "api/b.py", "models/m.py", "tests/test_a.py", "docs/d.md", "vendor/v.py"):
            (root / rel).parent.mkdir(exist_ok=True)
            (root / rel).write_text("x\n")
        git("add", "-A")
        git(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "start",
        )
        leaves = [
            {"id": "models", "title": "models know the new id", "scope": ["models/**"], "check": "true"},
            {
                "id": "api",
                "title": "the api returns it",
                "scope": ["api/**"],
                "check": "true",
                "needs": ["models"],
            },
            {
                "id": "tests",
                "title": "tests for it",
                "scope": ["tests/**", "new/tests/**"],
                "check": "true",
                "needs": ["api"],
            },
        ]
        with Store.open(root) as store:
            P.propose(store, leaves, P.Caller("alex", True))
        db = next(root.rglob("*.db"))
        before = hashlib.sha1(db.read_bytes()).hexdigest()
        m = repo_model(root)
        ok(set(m.tasks) == {"models", "api", "tests"}, "the plan's tasks are read")
        ok(m.tasks["api"].needs == ["models"], "needs become edges")
        nodes, edges = V.flow_graph(m)
        lay = F.layout(nodes, edges, label_w=18)
        ok(
            len(lay.rects) == 3 and lay.layers["tests"] > lay.layers["models"],
            "the real plan lays out left to right",
        )
        groups, summary = T.compute(m.files, m.tasks_dict(), m.protected)
        ok(summary["files"] == 6 and summary["may"] >= 3, "the territory counts the files the plan may touch")
        ok(summary["new"] == 1, "a scope that matches no file yet is a place for new files")
        ok(
            hashlib.sha1(db.read_bytes()).hexdigest() == before,
            "reading the plan changes nothing in the store",
        )
        say(
            f"territory on a real plan: {summary['may']} of {summary['files']} files may be touched, "
            f"{summary['new']} new place"
        )


def main() -> None:
    check_layout()
    check_screens()
    check_real_plan()
    print("\nplayground check: all hold")


if __name__ == "__main__":
    main()
