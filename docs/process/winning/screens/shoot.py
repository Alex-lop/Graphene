"""Screens of `graphene watch`, at 80x24 and 120x36, as SVG and as text.

From a scripted stand-in for Token Factory (tests/fake_tokenfactory.py), not Nemotron: the models are
named `-fake`, and every screen's title says so. Without ``--repo`` it makes a repository with two
leaves in a scratch directory and runs, against the stand-in,

    graphene run --with "nemotron --model <Nano> --model <Super> --forks 3" --attempts 2

whose replies hold each moment still while its screens are taken:

- ``forks-running``: greet's three forks, each waiting on its first answer;
- ``fork-lost``: fork 2's check passed, fork 1 was stopped (lost), fork 3 still waits on an answer;
- ``stepped-up``: farewell's attempt 1 was refused on Nano, and its forks run again on Super (the
  cursor on the goal: nobody pointed at the leaf); ``stepped-up-pane``: the cursor on farewell.

The moments are read from the stand-in's requests and the executor's own output, never from the
store, so this same file takes the screens of a Graphene from before the forks were logged: the
"before" screens come from it run in a checkout of that commit.

With ``--repo`` it takes the screens of that repository's store as it is now (a live run's, say),
after ``--keys``; name them with ``--label``. A live store's screens name its sandbox's image by its
first twelve characters: read them before they are committed.

    uv run python docs/process/winning/screens/shoot.py --out docs/process/winning/screens/after
    uv run python docs/process/winning/screens/shoot.py --repo ~/feeds --label live --keys j --out /tmp/s
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))

from fake_tokenfactory import Fake, call  # noqa: E402

from graphene_map import plan  # noqa: E402
from graphene_map import tokenfactory as tf  # noqa: E402
from graphene_map.run import named, run_plan  # noqa: E402
from graphene_map.store import Store  # noqa: E402
from graphene_map.tui import Watch  # noqa: E402

NANO, SUPER = "nvidia/Nemotron-3-Nano-fake", "nvidia/Nemotron-3-Super-fake"
SIZES = ((80, 24), (120, 36))
STAND_IN = "a scripted stand-in for Token Factory, not Nemotron"
HELLO = "python3 -c 'import app; assert app.greet() == \"hello\"'"
GOODBYE = "python3 -c 'import bye; assert bye.bye() == \"goodbye\"'"
WAIT = 120  # seconds any one moment may take to arrive


class Moment:
    """Forks held on an answer until this moment's screens are taken."""

    def __init__(self, forks: int) -> None:
        self.forks, self.here, self.go, self.lock = forks, 0, threading.Event(), threading.Lock()

    def hold(self, answer: dict):
        def held(body):
            with self.lock:
                self.here += 1
            self.go.wait(WAIT)
            return answer

        return held

    def arrived(self) -> bool:
        return self.here >= self.forks


def said(repo: Path, fork: int, words: str) -> bool:
    """Has the executor said this of that fork (in its own output, which it flushes line by line)?"""
    for log in (repo / ".graphene" / "runs").glob("*.txt"):
        if any(line.startswith(f"[fork {fork}]") and words in line for line in log.read_text().splitlines()):
            return True
    return False


def until(test, what: str) -> None:
    ends = time.monotonic() + WAIT
    while not test():
        if time.monotonic() > ends:
            raise SystemExit(f"the moment never came: {what}")
        time.sleep(0.1)


def answers(repo: Path, running: Moment, lost: Moment, stepped: Moment):
    """The stand-in's script, by leaf, model, fork and step (a step that is a function is called)."""
    after_fork_2 = call("view", path="app.py")

    def once_fork_2_passed(body):
        until(lambda: said(repo, 2, "the check passed in this fork"), "greet's fork 2 passing")
        return after_fork_2

    quiet = {"content": "I am not sure what to change"}
    script = {
        ("greet", NANO): {
            1: [running.hold(call("edit", path="app.py", old='"hi"', new='"hey"')), call("done"),
                once_fork_2_passed],
            2: [running.hold(call("edit", path="app.py", old='"hi"', new='"hello"')), call("done")],
            3: [running.hold(call("view", path="app.py")), lost.hold({"content": "still reading app.py"})],
        },
        ("farewell", NANO): {
            1: [call("edit", path="bye.py", old='"bye"', new='"ciao"'), call("done"), quiet, quiet, quiet],
            2: [quiet, quiet, quiet],
            3: [quiet, quiet, quiet],
        },
        ("farewell", SUPER): {
            1: [stepped.hold(call("edit", path="bye.py", old='"bye"', new='"goodbye"')), call("done")],
            2: [stepped.hold(call("view", path="bye.py")), quiet],
            3: [stepped.hold(call("view", path="bye.py")), quiet],
        },
    }

    def answer(body):
        leaf = next(n for n in ("greet", "farewell") if f"{n} (revision" in body["messages"][1]["content"])
        fork = next(k for k in (1, 2, 3) if f"This is fork {k} of" in body["messages"][0]["content"])
        steps = script[(leaf, body["model"])][fork]
        k = sum(1 for m in body["messages"] if m["role"] == "assistant")
        step = steps[k] if k < len(steps) else quiet
        return step(body) if callable(step) else step

    return answer


def repository(work: Path) -> Path:
    repo = work / "feeds"
    repo.mkdir(parents=True)
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    (repo / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    (repo / "app.py").write_text('def greet():\n    return "hi"\n')
    (repo / "bye.py").write_text('def bye():\n    return "bye"\n')
    git("add", "-A")
    git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "start")
    alex = plan.Caller("alex", True)
    with Store.open(repo) as store:
        plan.set_goal(store, "a friendlier app", alex)
        plan.propose(store, [
            {"id": "greet", "title": "greet says hello", "scope": ["app.py"], "check": HELLO},
            {"id": "farewell", "title": "bye says goodbye", "scope": ["bye.py"], "check": GOODBYE},
        ], alex)  # fmt: skip
    return repo


async def shoot(repo: Path, out: Path, name: str, size: tuple[int, int], keys: list[str]) -> None:
    app = Watch(repo, lambda: Store.open(repo), every=60)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.pause()
        stem = out / f"{name}-{size[0]}x{size[1]}"
        stem.with_suffix(".svg").write_text(app.export_screenshot(title=f"{name}, {STAND_IN}"))
        text = [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]
        stem.with_suffix(".txt").write_text("\n".join(text) + "\n")


def shots(repo: Path, out: Path, name: str, keys: list[str]) -> None:
    time.sleep(0.5)  # the executor writes a fork's row on the leaf just after it says so in its output
    for size in SIZES:
        asyncio.run(shoot(repo, out, name, size, keys))
    print(f"{name}: {', '.join(f'{name}-{w}x{h}.svg' for w, h in SIZES)}", flush=True)


def scripted(out: Path, work: Path) -> None:
    for name in ("GRAPHENE_LEDGER", "GRAPHENE_TOKENFACTORY_RECORD", "GRAPHENE_SANDBOX", "NEBIUS_PROJECT_ID"):
        os.environ.pop(name, None)
    os.environ["HOME"] = str(work)  # the top line reads `the plan of ~/feeds`, not where the scratch is
    repo = repository(work)
    running, lost, stepped = Moment(3), Moment(1), Moment(3)
    with Fake([answers(repo, running, lost, stepped)] * 200) as fake:
        os.environ.update(fake.env())  # the stand-in's key and address: no real key is read or sent
        tf._listed.cache_clear()
        said_by_run: list[str] = []
        spec = f"nemotron --model {NANO} --model {SUPER} --forks 3"

        def go() -> None:
            with Store.open(repo) as store:
                run_plan(store, repo, named(spec), 2, None, said_by_run.append, repo / ".graphene" / "runs")

        run = threading.Thread(target=go)
        run.start()
        try:
            until(running.arrived, "greet's three forks asking")
            shots(repo, out, "forks-running", ["j"])
            running.go.set()
            until(lambda: lost.arrived() and said(repo, 1, "stopped: another fork's check passed"),
                  "greet's fork 2 passing and fork 1 stopped")  # fmt: skip
            shots(repo, out, "fork-lost", ["j"])
            lost.go.set()
            until(stepped.arrived, "farewell's forks asking Super")
            shots(repo, out, "stepped-up", [])
            shots(repo, out, "stepped-up-pane", ["j", "j"])
        finally:
            for moment in (running, lost, stepped):
                moment.go.set()
            run.join(WAIT)
    print("\n".join(said_by_run), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "after")
    parser.add_argument("--work", type=Path, help="where the scratch repository is made (by default, anew)")
    parser.add_argument("--repo", type=Path, help="a repository whose store to take, as it is now")
    parser.add_argument("--label", default="now", help="the screens' name, with --repo")
    parser.add_argument("--keys", nargs="*", default=[], help="keys pressed first, with --repo (j, enter, …)")
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.repo:
        shots(args.repo, args.out, args.label, args.keys)
    else:
        scripted(args.out, (args.work or Path(tempfile.mkdtemp(prefix="graphene-screens-"))).resolve())


if __name__ == "__main__":
    main()
