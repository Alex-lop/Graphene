#!/usr/bin/env python3
"""The statements tree arm, as practice, with a stand-in who wants every report per currency.

    dev/test/statements_wide.py OUT --tool BIN --python PY [--every 120]

statements_practice.py's run, with one act more at the start. On 7 October the planner put the task's
eight money-summing subsystems on the board as a risk, defaulted them to USD-only ("per-currency reports
are a separate job"), and a stand-in who took the default got a run of minutes. This stand-in reads that
risk and answers it with work: a second `graphene ask` for the subsystems, then accepts everything. It
measures whether the person's answer, not the repo's size, is what makes the run long.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from statements_practice import EXECUTOR, MARKS, SESSION, TASK, night  # noqa: E402

PLANNER = "claude -p --tools Read,Grep,Glob --strict-mcp-config --model sonnet --max-budget-usd 1.5"
MORE = (
    "Every report and figure that adds up money must be per currency too, never adding two currencies: "
    "the fees, aging, dunning letters, reconciliation, the CSV statement, the month-end figures, the "
    "tax-year interest and the audit, each with its tests."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--tool", required=True)
    ap.add_argument("--python", required=True)
    ap.add_argument("--every", type=float, default=120.0)
    a = ap.parse_args()
    if night.cap() is None:
        sys.exit(f"{night.OPENING} is not set")
    env = os.environ | {
        "PATH": f"{a.tool}{os.pathsep}{os.environ['PATH']}",
        night.PURPOSE: "statements-practice",
    }
    made = subprocess.run(
        ["bash", str(HERE / "newrun.sh"), str(a.out), "statements", "practice", "wide", "1"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    run = Path(next(line.split()[1] for line in made.splitlines() if line.startswith("run ")))
    repo, tmp = run / "repo", run / "tmp"
    me = {k: v for k, v in env.items() if k not in MARKS} | {
        "TMPDIR": str(tmp),
        "GRAPHENE_AS": f"person:{os.environ['USER']}",
    }

    def sh(*argv: str, who: dict = me, out: Path | None = None, timeout: int = 3600) -> str:
        with open(out, "w") if out else open(os.devnull, "w") as sink:
            done = subprocess.run(
                argv,
                cwd=repo,
                env=who,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                text=True,
                stdout=subprocess.PIPE if out is None else sink,
                stderr=subprocess.STDOUT,
            )
        return (done.stdout or "").rstrip() if out is None else out.read_text()

    def log(*what: str, stdin: str | None = None) -> None:
        subprocess.run(
            [sys.executable, str(HERE / "logline.py"), str(run / "runlog.jsonl"), "person", *what],
            input=stdin,
            text=True,
            capture_output=True,
            env=me,
        )

    sh("graphene", "plan", "first", "on")
    paragraph = (TASK / "paragraph.md").read_text()
    log("clock", "start")
    log("prompt", stdin=paragraph)
    started = time.time()
    held = night.reserve("claude:sonnet", 3.0, "statements-practice: the wide run plans", "claude code")
    sh("claude", "-p", paragraph, *SESSION, who=env | {"TMPDIR": str(tmp)}, out=run / "e1.json", timeout=1800)
    try:
        said = json.loads((run / "e1.json").read_text())
    except ValueError:
        said = {}
    night.settle(held, "claude:sonnet", float(said.get("total_cost_usd") or 3.0), {})
    board = sh("graphene", "board")
    log("prompt", stdin=MORE)
    held = night.reserve(
        "claude:sonnet planner", 1.5, "statements-practice: the wide run asks for more", "claude code"
    )
    more = sh("graphene", "ask", MORE, "--with", PLANNER, timeout=1800)
    night.settle(held, "claude:sonnet planner", 1.5, {})  # a text answer says no cost: its worst case
    log("accept", stdin="as_me graphene plan accept")
    accepted = sh("graphene", "plan", "accept")
    tree = sh("graphene", "plan", "--text", "--all")
    planned = time.time()
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
    (run / "practice.txt").write_text(
        "\n\n".join(
            [
                f"planned in {planned - started:.0f} s; the run took {(ended - planned) / 60:.1f} min",
                "$ graphene board",
                board,
                f"$ graphene ask {MORE!r}",
                more,
                "$ graphene plan accept",
                accepted,
                "$ graphene plan --text --all",
                tree,
                "$ graphene run --parallel 3 (last 40 lines)",
                "\n".join(text.splitlines()[-40:]),
                "$ prove.py count",
                counted.stdout + counted.stderr,
            ]
        )
        + "\n"
    )
    bill = next((line for line in reversed(text.splitlines()) if line.startswith("run")), "")
    print(json.dumps({"run": run.name, "run_min": round((ended - planned) / 60, 1), "bill": bill}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
