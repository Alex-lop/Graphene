#!/usr/bin/env python3
"""Arm B′ of the live pre-registration (results-2026-09-28-live-prereg.md): Graphene without the prune.

    uv run python docs/test/arm_bprime.py <task> --paragraph-file P [--change-file C] --executor SPEC
        [--planner nemotron] [--parallel 4] [--run 1] [--rounds 3] [--timeout 3600]
        [--tasks DIR] [--out DIR] [--ledger FILE]

The person here decides nothing. In order:

1. builds the task's repo fresh with make_task.py, outside this repository (by default in
   ~/graphene-bench/<date>/<task>-bprime-<run>/repo), and runs `graphene init` there;
2. logs the paragraph as the person's `prompt`, asks the planner for a tree from it as it is
   (`graphene ask --with PLANNER`, the path arm B's paragraph takes), and accepts every proposal
   whole (`graphene plan accept`, logged as `accept`);
3. runs the tree as bench.py does (`bench.play_rounds`): offers are taken by the bench's mechanical
   rule (decision 65), a refused leaf is not run again, at most --rounds rounds;
4. with --change-file, once that is over: logs the change of mind as a mandated `correction`, asks
   the planner with it as it is, accepts every proposal whole, and runs what is new the same way.

No edit, no drop, no correction of its own and no reopen. The spend is bench.py's: one ledger for
the night (--ledger), no new run at 80% of GRAPHENE_SPEND_CAP_USD (30 if unset), and a run that hits
the cap stops between rounds. The run log ends with a line of its own (`who: harness`, no act), so
its wall time reaches the last round's end. It counts nothing itself: `evidence.py add <run-dir>
--task T --arm B′` counts this run as it counts every arm.

Written before any board existed on this branch: a build whose planner puts up a board leaves every
item on it unanswered here, and what B′ should do with a board is not decided.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402
import tally  # noqa: E402

from graphene_map import tokenfactory as tf  # noqa: E402


def part(repo: Path, env: dict, log, text: str, planner: str) -> None:
    """Send the words to the planner as they are and accept every proposal whole."""
    bench.graphene(repo, env, "ask", "--with", planner, text)
    bench.graphene(repo, env, "plan", "accept")
    log("accept", "graphene plan accept")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--paragraph-file", type=Path, required=True, help="the task's paragraph, sent as it is")
    ap.add_argument("--change-file", type=Path, help="the card's change of mind, sent as it is")
    ap.add_argument("--executor", required=True, help="as `graphene run --with` takes it: 'nemotron …'")
    ap.add_argument("--planner", default="nemotron", help="as `graphene ask --with` takes it")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=3, help="`graphene run`s at most, in each part")
    ap.add_argument("--timeout", type=float, default=3600, help="seconds a round may take")
    ap.add_argument("--tasks", type=Path, default=HERE / "tasks", help="where <task>/intent_globs.txt is")
    ap.add_argument("--out", type=Path, default=Path.home() / "graphene-bench" / time.strftime("%Y-%m-%d"))
    ap.add_argument("--ledger", type=Path, default=bench.LEDGER, help="the night's Token Factory ledger")
    args = ap.parse_args(argv)

    intent_file = (args.tasks / args.task / "intent_globs.txt").resolve()
    for need in (intent_file, args.paragraph_file, *([args.change_file] if args.change_file else [])):
        if not need.is_file():
            print(f"no {need}")
            return 2
    if args.parallel < 2:
        print("--parallel 1 works in place and merges nothing, so no leaf could land: use 2 or more")
        return 2
    if "nemotron" in (args.executor.split()[:1] + args.planner.split()[:1]):
        unreached = tf.reach()
        if unreached:
            print(f"no run: {unreached}")
            return 2
    cap = float(os.environ.get("GRAPHENE_SPEND_CAP_USD") or bench.CAP)
    os.environ["GRAPHENE_LEDGER"] = str(args.ledger.resolve())
    os.environ["GRAPHENE_SPEND_CAP_USD"] = str(cap)
    if tf.spent() >= 0.8 * cap:
        print(f"no new run: the ledger ({args.ledger}) is at ${tf.spent():.2f} of ${cap:.2f}, 80% or more")
        return 3
    run_dir = (args.out / f"{args.task}-bprime-{args.run}").resolve()
    if run_dir.is_relative_to(bench.ROOT):
        print(f"{run_dir} is inside this repository; a task repo is built outside it (--out)")
        return 2
    if run_dir.exists():
        print(f"{run_dir} exists already; a run is never redone in place")
        return 2

    runlog = run_dir / "runlog.jsonl"
    log = bench.logger(runlog)
    repo, base, env = bench.prepare(run_dir, args.task, None, log)
    print(f"repo  {repo}  (base {base[:12]})")
    intent = tally.intent_globs(intent_file)
    # sent and logged as a stand-in sends a written file, MSG=$(cat FILE), which drops final newlines
    paragraph = args.paragraph_file.read_text(encoding="utf-8").rstrip("\n")
    was = signal.signal(signal.SIGTERM, signal.default_int_handler)  # a kill stops the round, as Ctrl-C does
    try:
        log("prompt", paragraph)
        part(repo, env, log, paragraph, args.planner)
        done, stopped, _, _ = bench.play_rounds(repo, env, log, run_dir, intent, args, cap)
        if args.change_file and not stopped:
            change = args.change_file.read_text(encoding="utf-8").rstrip("\n")
            before = set(bench.left_to_run(repo))
            log("correction", change, mandated=True)
            part(repo, env, log, change, args.planner)
            new = [n for n in bench.left_to_run(repo) if n not in before]
            if new:
                more, stopped, _, _ = bench.play_rounds(repo, env, log, run_dir, intent, args, cap, new, done)
                done += more
            else:
                print("the change of mind added no leaf to run")
    finally:
        signal.signal(signal.SIGTERM, was)
        with runlog.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "who": "harness", "type": "end", "text": ""}) + "\n")
    print(
        f"{done} rounds{f'; stopped by {stopped}' if stopped else ''}. Count it: uv run python "
        f"docs/test/evidence.py add {run_dir} --task {args.task} --arm B′"
    )
    return 3 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
