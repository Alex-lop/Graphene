#!/usr/bin/env python3
"""Study 2 of the 28 September shaping study: one proposal per task, shaped twice, never run.

    docs/test/shape_only.py setup TASK          a fresh task repo, `graphene init` as the person
    docs/test/shape_only.py fork TASK ARM       a copy of it, once proposed, for one arm to shape
    docs/test/shape_only.py brief TASK ARM      the stand-in's brief for that copy

ARM is `outline` or `board` (results-2026-09-28-shaping.md, "Study 2"); SHAPE_STUDY=4 gives the board
arm study 4's text (results-2026-09-29-board.md). `setup` makes
$SHAPE_RUNS/TASK-shape-planned (default ~/graphene-shaping-runs) in newrun.sh's layout (repo/, base.sha,
runlog.jsonl, tmp/, env.sh) and prints that path; the coordinator then runs `graphene ask` in its
repo/, once. `fork` copies the whole directory to TASK-shape-ARM-1, so both arms start from the same
proposal byte for byte, and gives the copy an empty run log and its own env.sh. `brief` pastes the
paragraph the person wrote and their card, both read here, so whoever prepares a run never opens them.

env.sh is newrun.sh's own text, read out of newrun.sh and expanded by bash, so a shaping run logs
through the same `as_me`, `did` and `seen` as every other run, and attention.py reads it the same way.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_task import build  # noqa: E402
from standin import card  # noqa: E402

# Study 3 sets SHAPE_RUNS and SHAPE_BIN to its own runs directory and venv; unset, they are study 2's.
RUNS = Path(os.environ.get("SHAPE_RUNS", Path.home() / "graphene-shaping-runs"))
BIN = Path(os.environ.get("SHAPE_BIN", Path.home() / "graphene-shaping-venv" / "bin"))
NEWRUN = (HERE / "newrun.sh").read_text(encoding="utf-8")
UNMARK = re.search(r"^UNMARK=.*$", NEWRUN, re.M).group(0)
ENV_SH = re.search(r'^cat > "\$DIR/env\.sh" <<EOF\n.*?^EOF$', NEWRUN, re.M | re.S).group(0)

PRUNE = """Prune it with these, and nothing else:
       did accept "as_me graphene plan accept <id>"      it, what is above it and under it
       did drop "as_me graphene node drop <id>"          it, and everything under it
       did edit "as_me graphene node set <id> --title '…' --goal '…' --scope '…' --check '…'"
                                                         one node's contract, any of those; --scope
                                                         replaces the scope, repeat it for each path
     A proposal nobody accepts never runs."""

ARMS = {
    "outline": f"""There is a plan, and it is a tree: the root is what you want, its children are
  how it will be done, the leaves are work an agent does.

  1. Read the tree: `seen as_me graphene plan --text` and `seen as_me graphene plan` (a proposal
     is marked). The plan may show board items; leave them alone.
  2. {PRUNE}""",
    "board": f"""There is a plan, and it is a tree: the root is what you want, its children are
  how it will be done, the leaves are work an agent does. Before the tree there is a board: the
  planner's questions, each with the answer it would assume if you said nothing, its options where
  it sees more than one way, its assumptions, its risks, and what it would leave out.

  1. Read the board: `seen as_me graphene board`.
  2. Answer every open item on the board before you look at the tree, each with one of these and
     nothing else:
       did board "as_me graphene board take <id>"              the answer it would assume
       did board "as_me graphene board pick <id> <n>"          its option n
       did board "as_me graphene board drop <id>"              not wanted
       did board "as_me graphene board park <id>"              not now
       did board "as_me graphene board answer <id> '<words>'"  your own answer, in your words
       did board "as_me graphene board note '<words>'"         a note of your own, on no item
  3. Read the tree as a graph: `seen as_me graphene plan --view auto` (a proposal is marked).
  4. {PRUNE}""",
}

# Study 4 (results-2026-09-29-board.md): the board shows only what is open, and accepting the plan takes
# every default left, as the person, so the board arm answers only what it would change. The outline
# arm is study 2's, byte for byte. SHAPE_STUDY=4 selects it; unset, 2 or 3, the briefs are study 2's.
STUDY = os.environ.get("SHAPE_STUDY", "2")
STUDY4 = {
    **ARMS,
    "board": f"""There is a plan, and it is a tree: the root is what you want, its children are
  how it will be done, the leaves are work an agent does. Before the tree there is a board: the
  planner's questions, each with the answer it would assume if you said nothing, its options where
  it sees more than one way, its assumptions, its risks, and what it would leave out.

  1. Read the board: `seen as_me graphene board`.
  2. Answer only the items whose default you would change, before you look at the tree, each with
     one of these and nothing else:
       did board "as_me graphene board pick <id> <n>"          its option n
       did board "as_me graphene board drop <id>"              not wanted
       did board "as_me graphene board park <id>"              not now
       did board "as_me graphene board answer <id> '<words>'"  your own answer, in your words
       did board "as_me graphene board note '<words>'"         a note of your own, on no item
     Leave the others: accepting the plan takes their defaults, as you.
  3. Read the tree as a graph: `seen as_me graphene plan --view auto` (a proposal is marked).
  4. {PRUNE}""",
}
ARMS_OF = {"2": ARMS, "3": ARMS, "4": STUDY4}

BRIEF = """You are the person who wants a change made to a small codebase. Earlier you wrote a
paragraph saying what you want, from your card; both are at the bottom. A planner has read your
paragraph and proposed a plan. You shape that plan until it is one you would let run, the moment you
would press R, and there you stop. Play the person, not an assistant. You decide what good looks
like; nobody is marking your work.

WHERE THINGS ARE
  repo          {repo}
  run log       {runlog}
  your TMPDIR   {tmp}          every temporary file anything makes goes in here
  notes         {run}/notes.md

BEFORE YOU TYPE ANYTHING

  Every shell you open, and every script you write, starts with this line:

    source {run}/env.sh

  It puts {venv} first on PATH, sets TMPDIR, goes to the repo, and gives you:

    as_me <command>            run a command as you, the person
    did <type> "<command>"     run a command as you, log the whole line as that act, and
                               what it printed as read
    seen <command>             run a command, show you what it printed, and log that as read

  Check `command -v graphene` prints a path under {venv}. If it does not, stop and say so: the
  wrong build is on PATH and the run is void.

HOW YOU WORK

  You are a busy, competent person. You read what you are shown. You change what is wrong by your
  card and leave alone what is already right. Anything you type is short and plain, in your own
  words.

WHAT YOU DO

  {arm}

LOGGING — as you go, never afterwards from memory

  Every command you run as the person goes through `did`, with the whole command as its text.
  Every screen you read goes through `seen`, including a file you open, so what you read is in the
  log. Log the FULL text of every command, not an abbreviation of it.

WHAT YOU MUST NOT DO

  - run anything: no `graphene run`, no `graphene ask`, no `claude`, no executor or session, and
    not the repo's tests. Stop when you would press R; do not run anything.
  - read any file under docs/test/.
  - write anything outside {repo} and {tmp}.
  - `git commit` by hand.

WHEN YOU WOULD PRESS R

  Stop, without pressing it. Write {run}/notes.md: what you did in order, what surprised you, and
  what you still think is wrong with the plan. Be blunt. Then hand back a report of at most ten
  lines.

========================= THE PARAGRAPH YOU WROTE =========================

{paragraph}
================================ YOUR CARD ================================

{card}
"""


def brief(task: str, arm: str, runs: Path = RUNS, tasks: Path = HERE / "tasks", study: str = STUDY) -> str:
    run = runs / f"{task}-shape-{arm}-1"
    return BRIEF.format(
        repo=run / "repo",
        runlog=run / "runlog.jsonl",
        tmp=run / "tmp",
        run=run,
        venv=BIN,
        arm=ARMS_OF[study][arm],
        paragraph=(tasks / task / "paragraph.md").read_text(encoding="utf-8"),
        card=card(task, tasks),
    )


def bash(script: str, **env: str) -> None:
    """Run newrun.sh's lines with its own variables set; BIN is the build's bin, first on PATH."""
    path = f"{env['BIN']}:{os.environ['PATH']}"
    full = f"set -euo pipefail\nHERE='{HERE}'\n{UNMARK}\n{script}\n"
    subprocess.run(["bash", "-c", full], env={**os.environ, **env, "PATH": path}, check=True)


# nothing a stand-in runs can reach Token Factory: the key the coordinator's shell may hold is not the
# stand-in's, and the keychain is off, as in the tests (DIRECTION 96)
NO_KEY = "\nunset NEBIUS_API_KEY NEBIUS_PROJECT_ID\nexport GRAPHENE_KEYCHAIN=off\n"


def write_env(run: Path, bin_dir: Path = BIN) -> None:
    (run / "runlog.jsonl").write_text("")
    (run / "tmp").mkdir(exist_ok=True)
    bash(ENV_SH, DIR=str(run), BIN=str(bin_dir))
    with open(run / "env.sh", "a", encoding="utf-8") as env:
        env.write(NO_KEY)


def setup(task: str, runs: Path = RUNS) -> Path:
    run = runs / f"{task}-shape-planned"
    if run.exists():
        raise FileExistsError(f"{run} exists already; a run is never redone in place")
    (run / "tmp").mkdir(parents=True)
    (run / "base.sha").write_text(build(task, run / "repo") + "\n")
    bash(
        'env $UNMARK TMPDIR="$DIR/tmp" GRAPHENE_AS="person:$(id -un)" '
        "sh -c \"cd '$DIR/repo' && graphene init --planner claude --executor claude\" > /dev/null",
        DIR=str(run),
        BIN=str(BIN),
    )
    write_env(run)
    return run


def fork(task: str, arm: str, runs: Path = RUNS, bin_dir: Path = BIN) -> Path:
    planned, run = runs / f"{task}-shape-planned", runs / f"{task}-shape-{arm}-1"
    if not planned.is_dir():
        raise FileNotFoundError(f"no {planned}: run `shape_only.py setup {task}` first")
    if run.exists():
        raise FileExistsError(f"{run} exists already; a run is never redone in place")
    subprocess.run(["cp", "-R", str(planned), str(run)], check=True)
    shutil.rmtree(run / "tmp")
    write_env(run, bin_dir)
    return run


def main(argv: list[str]) -> int:
    ok = len(argv) == 3 and argv[1] == "setup" or len(argv) == 4 and argv[1] in ("fork", "brief")
    if not ok or (len(argv) == 4 and argv[3] not in ARMS) or STUDY not in ARMS_OF:
        sys.stderr.write(__doc__)
        return 2
    try:
        if argv[1] == "setup":
            print(setup(argv[2]))
        elif argv[1] == "fork":
            print(fork(argv[2], argv[3]))
        else:
            print(brief(argv[2], argv[3]))
    except (FileExistsError, FileNotFoundError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
