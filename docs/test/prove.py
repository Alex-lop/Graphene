#!/usr/bin/env python3
"""The statements experiment's runs, counted and put in one table. PROVE.md says when to run what.

    python3 docs/test/prove.py count <run-dir>              tally one run into <run-dir>/tally.json
    python3 docs/test/prove.py table <runs-dir> [--out F]   every counted run under it, as markdown
    python3 docs/test/prove.py rehearse <runs-dir> [--out F]

<run-dir> is what newrun.sh made: statements-<style>-<arm>-<rep>, with repo/, base.sha and
runlog.jsonl. `count` runs tally.py with the task's accept.py, quality.py and traps.py. It adds
three numbers from the plan's store that PREREG-statements.md's loss rules read: the agent's board
items, how many of them name one of the conflicts (CONFLICT), and the minutes from the tree's
proposal to the first accept, which is how long the tree took to read and prune.

`rehearse` plays four runs with no model at all. A script stands in for the person, the planner
and the executors, and applies the task's own patches. The tree arm proposes a tree, answers the
board, accepts, and runs three executors at once with `graphene run --parallel 3`. The paragraph
arm applies its changes in three steps and takes a snapshot after each. One run per arm trips
every trap (reference.patch then tripall.patch); the other trips none (reference.patch alone).
It proves the counters measure what they claim: 5 and 0 traps, and a time for each wrong inference.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE / "tasks" / "statements"
PATCHES = {"none": ["reference.patch"], "all": ["reference.patch", "tripall.patch"]}

# The scripted planner's tree: leaf -> (title, scope, check, needs). The trip-all tree adds a leaf
# that fixes the vendored library, and its tests leaf reaches the protected test.
NEW = "migrations/0005_posting_currency.sql"
SUITE = "python3 -m unittest discover -q tests && sh scripts/close_month.sh 2026-09"
LEAVES = {
    "migration": ("the migration that adds currency and backfills USD", NEW, f"test -f {NEW}", ""),
    "money": ("half-even for what people read", "core/money.py",
              'python3 -c "from core.money import to_cents"', ""),
    "model": ("postings, balances and interest per currency",
              "core/models.py, core/ledger.py, core/balances.py, core/interest.py",
              'python3 -c "from core.ledger import currencies"', "migration, money"),
    "printers": ("the command line, the statement and v1", "api/**",
                 'python3 -c "from api.export import V1_FIELDS"', "model"),
    "tests": ("tests and the README", "tests/**, !tests/test_legacy_contract.py, README.md",
              SUITE, "printers"),
}  # fmt: skip
TRIPPING = {
    "migration": ("the migrations", f"{NEW}, migrations/0007_postings_by_currency.sql", f"test -f {NEW}", ""),
    "decimalfmt": ("fix decimalfmt's half_even", "vendor/decimalfmt/**",
                   'python3 -c "from vendor.decimalfmt import format_amount"', ""),
    "tests": ("tests and the README", "tests/**, README.md", SUITE, "printers"),
}  # fmt: skip
BOARD = """assume: half-even everywhere includes the monthly totals file  [rounding]
  default: yes, legacy/monthly.py rounds half-even too
"""
# A board item that names one of the task's conflicts says one of these words, in any case.
CONFLICT = re.compile(r"round|half|legacy|monthly|v1|export|shape|vendor|decimalfmt|migrat", re.I)
# The paragraph arm's three steps: the files each one writes.
STEPS = [("migrations/", "core/", "api/"), ("vendor/", "tests/"), ("README.md",)]


def tree(trips: str) -> dict:
    return {**LEAVES, **TRIPPING} if trips == "all" else dict(LEAVES)


def plan_text(trips: str) -> str:
    lines = [
        "goal: statements in more than one currency",
        "",
        BOARD,
        "- a currency on every posting  [currency]",
    ]
    for leaf, (title, scope, check, needs) in tree(trips).items():
        lines += [f"  - {title}  [{leaf}]", f"      scope: {scope}", f"      check: {check}"]
        lines += [f"      needs: {needs}"] if needs else []
    return "\n".join(lines) + "\n"


def touched(patch: str) -> list[str]:
    return re.findall(r"^diff --git a/(\S+) b/", (TASK / patch).read_text(encoding="utf-8"), re.M)


def apply(where: Path, trips: str, wanted) -> None:
    """Apply this run's patches, for the files `wanted` takes, in the order the patches go."""
    for patch in PATCHES[trips]:
        files = [f for f in touched(patch) if wanted(f)]
        if files:
            argv = ["git", "-C", str(where), "apply", *(f"--include={f}" for f in files), str(TASK / patch)]
            subprocess.run(argv, check=True)


def execute(trips: str) -> int:
    """The scripted executor `graphene run` starts: its leaf's files, from the patches, and nothing else."""
    sys.path.insert(0, str(HERE.parents[1] / "src"))
    from graphene_map.plan import in_scope

    scope = [g.strip() for g in tree(trips)[os.environ["GRAPHENE_NODE"]][1].split(",")]
    apply(Path.cwd(), trips, lambda f: in_scope(f, scope))
    return 0


REHEARSED = """# Rehearsal: the statements task, scripted, no model

`docs/test/prove.py rehearse` on {day}, at {sha}, with {version} first on PATH. No model ran. A script
played the person, the planner and three executors, and applied the task's own patches: trip-all
is reference.patch then tripall.patch, trip-none is reference.patch alone. The minutes are near zero
because a script waits seconds, not hours. Each run's whole count is its tally.json.

"""


# -- one run, as the person -----------------------------------------------------------------------


def sh(run: Path, line: str) -> str:
    """One line in a shell that sourced the run's env.sh, as every shell of a run does."""
    done = subprocess.run(["bash", "-c", f"source {shlex.quote(str(run / 'env.sh'))} && {line}"],
                          capture_output=True, text=True, timeout=900)  # fmt: skip
    if done.returncode:
        raise SystemExit(f"failed: {line}\n{(done.stdout + done.stderr)[-1500:]}")
    return done.stdout


def play(runs: Path, arm: str, trips: str, rep: int) -> Path:
    style = f"trip{trips}"
    subprocess.run(
        ["bash", str(HERE / "newrun.sh"), str(runs), "statements", style, arm, str(rep)], check=True
    )
    run = runs / f"statements-{style}-{arm}-{rep}"
    sh(run, f"log clock start && snap && log prompt < {shlex.quote(str(TASK / 'paragraph.md'))}")
    if arm == "tree":
        (run / "tmp" / "tree.plan").write_text(plan_text(trips), encoding="utf-8")
        marks = "-u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_ENTRYPOINT -u GRAPHENE_AS"
        sh(run, f'env {marks} AI_AGENT=planner graphene plan propose "$TMPDIR/tree.plan" > /dev/null')
        time.sleep(2)  # the person reads the board and the tree
        board = "take rounding" if trips == "all" else "answer rounding 'no: the monthly file keeps half up'"
        sh(run, f'did board "as_me graphene board {board}" > /dev/null')
        sh(run, 'did accept "as_me graphene plan accept" > /dev/null')
        executor = f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__)))} exec {trips}"
        sh(run, "log clock away && log run R")
        sh(run, f'as_me graphene run --parallel 3 --with {shlex.quote(executor)} > "$TMPDIR/run-1.txt" 2>&1')
    else:
        sh(run, "log clock away")
        for files in STEPS:
            time.sleep(2)  # the executor works
            apply(run / "repo", trips, lambda f, files=files: f.startswith(files))
            sh(run, "snap")
        sh(run, "printf 'scripted stand-in: no model' | python3 " + shlex.quote(str(HERE / "logline.py"))
           + ' "$R" executor result')  # fmt: skip
    time.sleep(1)
    sh(run, 'log clock back && snap && seen git diff --stat "$BASE" > /dev/null')
    sh(run, "log review done && log clock done")
    return run


# -- counting -------------------------------------------------------------------------------------


def count(run: Path) -> dict:
    arm = run.name.split("-")[-2]
    base = (run / "base.sha").read_text().strip()
    argv = [sys.executable, str(HERE / "tally.py"), str(run / "repo"), "--base", base,
            "--intent", str(TASK / "intent_globs.txt"), "--accept", str(TASK / "accept.py"),
            "--quality", str(TASK / "quality.py"), "--traps", str(TASK / "traps.py"),
            "--arm", "prompt" if arm == "prompt" else "tree",
            "--runlog", str(run / "runlog.jsonl")]  # fmt: skip
    done = subprocess.run(argv, capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise SystemExit(f"tally failed on {run}: {done.stderr[-800:]}")
    out = {**json.loads(done.stdout), **from_the_plan(run / "repo" / ".graphene" / "graphene.db")}
    (run / "tally.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def from_the_plan(db: Path) -> dict:
    """The agent's board items, those that name a conflict, and the tree's reading time in minutes."""
    sys.path.insert(0, str(HERE))
    from tally import seconds

    if not db.exists():
        return {"board_items": None, "board_naming_a_conflict": None, "tree_read_minutes": None}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    meta = conn.execute("SELECT value FROM plan_meta WHERE key = 'board'").fetchone()
    rows = conn.execute("SELECT timestamp, kind FROM node_log ORDER BY id").fetchall()
    conn.close()
    items = [i for i in (json.loads(meta[0]) if meta else []) if i.get("agent")]
    said = [
        " ".join([i["text"], i.get("default") or "", *(o["text"] for o in i.get("options", []))])
        for i in items
    ]
    proposed = next((seconds(at) for at, kind in rows if kind == "proposed"), None)
    accepted = next((seconds(at) for at, kind in rows if kind == "accepted"), None)
    return {
        "board_items": len(items),
        "board_naming_a_conflict": sum(bool(CONFLICT.search(s)) for s in said),
        "tree_read_minutes": round((accepted - proposed) / 60, 1) if proposed and accepted else None,
    }


def checks(said: dict | None) -> str:
    return "—" if not said else f"{said.get('passed', 0)}/{said.get('passed', 0) + said.get('failed', 0)}"


def table(runs: Path) -> str:
    head = ("| run | traps | tripped | first wrong (min) | at (UTC) | how it showed "
            "| person min (start, end) | tree read min | board (naming a conflict) "
            "| accept | held-out | cost $ | wall min |")  # fmt: skip
    rows = [head, "|" + "---|" * head.count(" | ") + "---|"]
    for path in sorted(runs.glob("*/tally.json")):
        t = {k: "—" if v is None else v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
        # a run with an unpriced call cost an unknown amount, never $0
        dollars = "unknown" if t["executor_calls_unpriced"] else t["executor_cost_usd"]
        rows.append(
            f"| {path.parent.name} | {t['traps']} | {', '.join(t['traps_tripped']) or '—'} "
            f"| {t['first_wrong_minutes']} | {t['first_wrong_at']} | {t['first_wrong_how']} "
            f"| {t['person_minutes_start']}, {t['person_minutes_end']} | {t['tree_read_minutes']} "
            f"| {t['board_items']} ({t['board_naming_a_conflict']}) "
            f"| {checks(t['acceptance'])} | {checks(t['quality'])} | {dollars} "
            f"| {round(t['wall_seconds'] / 60, 1)} |"
        )
    return "\n".join(rows) + "\n"


def main(argv: list[str]) -> int:
    if argv[1:2] == ["exec"]:
        return execute(argv[2])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("count", "table", "rehearse"))
    ap.add_argument("dir", type=Path)
    ap.add_argument("--out", type=Path, help="write the table here as well as printing it")
    args = ap.parse_args(argv[1:])
    where = args.dir.expanduser().resolve()
    if args.what == "count":
        print(
            json.dumps(
                {k: v for k, v in count(where).items() if k.startswith(("traps", "first", "person_m"))}
            )
        )
        return 0
    if args.what == "rehearse":
        where.mkdir(parents=True, exist_ok=True)
        for arm, trips in (("tree", "all"), ("tree", "none"), ("prompt", "all"), ("prompt", "none")):
            count(play(where, arm, trips, 1))
    text = table(where)
    if args.what == "rehearse":
        sha = subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        )
        version = subprocess.run(["graphene", "--version"], capture_output=True, text=True).stdout.strip()
        text = REHEARSED.format(day=time.strftime("%Y-%m-%d"), sha=sha.stdout.strip(), version=version) + text
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
