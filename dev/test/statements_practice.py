#!/usr/bin/env python3
"""The statements task as practice: the tree arm, start to end, with a scripted stand-in for the person.

    dev/test/statements_practice.py OUT --tool BIN --python PY [--runs 2] [--every 120] [--together]

Never registered: the style is `practice`, not `alex`, and every row on the night's ledger says
`statements-practice`, or the purpose GRAPHENE_NIGHT_PURPOSE names. The runs go one after another, so
the night holds one run's worst cases at a time; --together starts them all at once. Each run is the
tree arm of PROVE.md, with the 23 September harness (newrun.sh, logline.py, the clock):

1. `newrun.sh OUT statements practice tree N`, then plan first on, as the person.
2. The paragraph, byte for byte, to a Claude Code session in the repo (PROVE.md's flags): it plans.
3. The stand-in takes every board default and prunes nothing (`graphene plan accept`). That is the
   whole of its judgment: what the tree would do with a person who agrees with the planner.
4. `graphene run --parallel 3` with Claude Code on Sonnet, its stream on so the meter reads it, and the
   screen of `graphene watch` every --every seconds (meter_shot.py).
5. `prove.py count`: traps, accept, held-out, the clock, and the bill.

It answers three questions for tonight: how long a run takes (the task should take one to three hours),
whether the paragraph's conditions reach every executor, and what the meter shows on a long run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE / "tasks" / "statements"
sys.path.insert(0, str(HERE.parents[1] / "src"))
from graphene_map.nemotron import night  # noqa: E402

TOOLS = [
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    "Bash(graphene *)",
    "Bash(python3 *)",
    "Bash(git *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(mkdir *)",
    "Bash(sh scripts/*)",
]
SESSION = [
    "--model",
    "sonnet",
    "--permission-mode",
    "acceptEdits",
    "--output-format",
    "json",
    "--max-turns",
    "60",
    "--max-budget-usd",
    "3",
    "--setting-sources",
    "project,local",
    "--allowedTools",
    *TOOLS,
]
EXECUTOR = (
    "claude -p --model sonnet --permission-mode acceptEdits --output-format stream-json --verbose "
    "--max-budget-usd 4 --allowedTools " + " ".join(f"'{t}'" for t in TOOLS)
)
MARKS = (
    "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_ENTRYPOINT",
    "AI_AGENT",
    "GRAPHENE_NODE",
    "GRAPHENE_PLANNER",
)


def one(n: int, a) -> dict:
    env = os.environ | {
        "PATH": f"{a.tool}{os.pathsep}{os.environ['PATH']}",
        "GRAPHENE_NIGHT_PURPOSE": os.environ.get(night.PURPOSE) or "statements-practice",
    }
    made = subprocess.run(
        ["bash", str(HERE / "newrun.sh"), str(a.out), "statements", "practice", "tree", str(n)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    run = Path(next(line.split()[1] for line in made.splitlines() if line.startswith("run ")))
    repo, tmp, runlog = run / "repo", run / "tmp", run / "runlog.jsonl"
    me = {k: v for k, v in env.items() if k not in MARKS} | {
        "TMPDIR": str(tmp),
        "GRAPHENE_AS": f"person:{os.environ['USER']}",
    }

    def log(*what: str, stdin: str | None = None) -> None:
        subprocess.run(
            [sys.executable, str(HERE / "logline.py"), str(runlog), "person", *what],
            input=stdin,
            text=True,
            capture_output=True,
            env=me,
        )

    def sh(*argv: str, who: dict = me, out: Path | None = None, timeout: int = 3600) -> str:
        with open(out, "w") if out else open(os.devnull, "w") as sink:
            done = subprocess.run(
                argv,
                cwd=repo,
                env=who,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                stdout=subprocess.PIPE if out is None else sink,
                stderr=subprocess.STDOUT,
                text=True,
            )
        return (done.stdout or "").rstrip() if out is None else out.read_text()

    sh("graphene", "plan", "first", "on")
    paragraph = (TASK / "paragraph.md").read_text()
    log("clock", "start")
    log("prompt", stdin=paragraph)
    started = time.time()
    os.environ[night.PURPOSE] = os.environ.get(night.PURPOSE) or "statements-practice"
    held = night.reserve("claude:sonnet", 3.0, f"statements-practice: run {n} plans", "claude code")
    sh("claude", "-p", paragraph, *SESSION, who=env | {"TMPDIR": str(tmp)}, out=run / "e1.json", timeout=1800)
    try:
        said = json.loads((run / "e1.json").read_text())
    except ValueError:
        said = {}
    night.settle(
        held, "claude:sonnet", float(said.get("total_cost_usd") or 3.0), {}
    )  # unread: its worst case
    planned = time.time()
    board = sh("graphene", "board")
    tree = sh("graphene", "plan", "--text", "--all")
    log("accept", stdin="as_me graphene plan accept")
    accepted = sh("graphene", "plan", "accept")
    log("clock", "away")
    shots = run / "shots"
    shots.mkdir(exist_ok=True)
    with open(run / "run-1.txt", "w") as out:
        go = subprocess.Popen(
            ["graphene", "run", "--parallel", "3", "--with", EXECUTOR],
            cwd=repo,
            env=me,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        k = 0
        while go.poll() is None:
            time.sleep(a.every)
            k += 1
            subprocess.run(
                [
                    a.python,
                    str(HERE.parent / "screens" / "meter_shot.py"),
                    str(repo),
                    str(shots / f"{k:03d}"),
                ],
                env=me,
                capture_output=True,
                timeout=120,
            )
    ended = time.time()
    log("clock", "back")
    log("clock", "done")
    counted = subprocess.run(
        [sys.executable, str(HERE / "prove.py"), "count", str(run)],
        capture_output=True,
        text=True,
        env=me,
        timeout=1800,
    )
    text = (run / "run-1.txt").read_text()
    bill = next((line for line in reversed(text.splitlines()) if line.startswith("run")), "")
    (run / "practice.txt").write_text(
        "\n\n".join(
            [
                f"planned in {planned - started:.0f} s; the run took {(ended - planned) / 60:.1f} min",
                "$ graphene board",
                board,
                "$ graphene plan --text --all",
                tree,
                "$ graphene plan accept",
                accepted,
                "$ graphene run --parallel 3 (last 40 lines)",
                "\n".join(text.splitlines()[-40:]),
                "$ prove.py count",
                counted.stdout + counted.stderr,
            ]
        )
        + "\n"
    )
    return {
        "run": run.name,
        "plan_s": round(planned - started),
        "run_min": round((ended - planned) / 60, 1),
        "bill": bill,
        "count": counted.stdout.strip()[-1500:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--tool", required=True, help="the bin directory of graphene installed as a tool")
    ap.add_argument("--python", required=True, help="that tool's python, which draws the screens")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--every", type=float, default=120.0)
    ap.add_argument("--together", action="store_true", help="every run at once, all their worst cases held")
    a = ap.parse_args()
    if not os.environ.get("GRAPHENE_AGENT_LIVE_USD"):
        sys.exit(
            "GRAPHENE_AGENT_LIVE_USD is not set: these runs spend, and the night's ledger must count them"
        )
    a.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.runs if a.together else 1) as pool:  # one at a time: one run's holds at once
        for got in pool.map(lambda n: one(n, a), range(1, a.runs + 1)):
            print(json.dumps(got), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
