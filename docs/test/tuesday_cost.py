#!/usr/bin/env python3
"""What a plan in force costs on a change too small to plan.

    docs/test/tuesday_cost.py run <runs-dir> <rep>     # both arms, one at a time
    docs/test/tuesday_cost.py <runs-dir>               # the numbers

The tree directive's second item says a plan in force must feel like nothing on a small attended
task: *a one-file change under a plan costs the person zero keystrokes more than the paragraph
did*. This is that claim, with the keystrokes counted.

Both arms get the same repository, the same one-line request, character for character — the
request is a constant in this file, so neither arm can be typed more carefully than the other.
They differ in one thing: in the `plan` arm a plan is already in force, with a leaf that has
nothing to do with what is about to be asked for.

Setting the plan up is not part of the comparison; it happened yesterday. It is logged as `shape`
and reported on its own line, so the price of having a plan at all is visible and is not confused
with the price of using one.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The whole request, in both arms, exactly. An ordinary Tuesday errand, nothing to do with the
# plan's leaf and nothing to do with the `feeds` card.
ASK = "give read_json in ingest/jsonfeed.py a one line docstring saying what it returns"

GOAL = "get the northwind xml feed loading like the other two"
LEAF = "drop nought-priced products, every source"
LEAF_SCOPE = "validate/rules.py"
LEAF_CHECK = "python3 -m unittest discover -q tests"

FLAGS = [
    "--model", "sonnet", "--permission-mode", "acceptEdits", "--output-format", "json",
    "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep", "Bash(graphene *)",
    "Bash(python3 *)", "Bash(git *)", "Bash(ls *)", "Bash(cat *)", "Bash(mkdir *)",
]  # fmt: skip


def as_me(env: dict) -> dict:
    hidden = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_NODE")
    out = {k: v for k, v in env.items() if k not in hidden}
    out["GRAPHENE_AS"] = f"person:{os.environ.get('USER', 'me')}"
    return out


def log(runlog: Path, who: str, kind: str, text: str, **extra) -> None:
    entry = {"t": time.time(), "who": who, "type": kind, "text": text, "chars": len(text), **extra}
    with runlog.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def one(runs: Path, arm: str, rep: int) -> None:
    run = runs / f"tuesday-{arm}-{rep}"
    if run.exists():
        raise SystemExit(f"{run} exists already; a run is never redone in place")
    tmp = run / "tmp"
    tmp.mkdir(parents=True)
    repo, runlog = run / "repo", run / "runlog.jsonl"
    subprocess.run(
        [sys.executable, str(HERE / "make_task.py"), "feeds", str(repo)], check=True, capture_output=True
    )
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    (run / "base.sha").write_text(base + "\n")
    runlog.write_text("")

    env = {**os.environ, "TMPDIR": str(tmp)}
    mine = as_me(env)
    subprocess.run(["graphene", "init"], cwd=repo, env=mine, check=True, capture_output=True)

    if arm == "plan":
        for argv in (
            ["graphene", "plan", "goal", GOAL],
            ["graphene", "node", "add", LEAF, "--scope", LEAF_SCOPE, "--check", LEAF_CHECK],
        ):
            subprocess.run(argv, cwd=repo, env=mine, check=True, capture_output=True)
            log(runlog, "person", "shape", " ".join(argv), setup=True)

    # The one thing the person does today, identical in both arms.
    log(runlog, "person", "prompt", ASK)
    started = time.time()
    done = subprocess.run(
        ["claude", "-p", ASK, *FLAGS],
        cwd=repo,
        env={k: v for k, v in env.items() if k != "GRAPHENE_AS"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    (run / "executor.json").write_text(done.stdout + done.stderr)
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        result = {"result": (done.stdout + done.stderr)[-500:]}
    log(
        runlog,
        "executor",
        "result",
        str(result.get("result") or "")[:2000],
        cost_usd=result.get("total_cost_usd", result.get("cost_usd")),
        turns=result.get("num_turns"),
        session_id=result.get("session_id"),
        seconds=round(time.time() - started, 1),
    )
    print(f"{run.name}: exit {done.returncode} in {round(time.time() - started, 1)}s")


def measure(run: Path) -> dict:
    repo = run / "repo"
    entries = [json.loads(ln) for ln in (run / "runlog.jsonl").read_text().splitlines() if ln.strip()]
    setup = [e for e in entries if e.get("setup")]
    person = [e for e in entries if e.get("who") == "person" and not e.get("setup")]
    results = [e for e in entries if e.get("type") == "result"]
    db = repo / ".graphene" / "graphene.db"
    refusals, asides, scopes = 0, 0, []
    if db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        refusals = conn.execute(
            "SELECT COUNT(*) FROM node_log WHERE kind IN ('denied','refused','stop_refused','breach')"
        ).fetchone()[0]
        for (data,) in conn.execute("SELECT data FROM nodes"):
            node = json.loads(data)
            if node.get("aside"):
                asides += 1
                scopes.append(",".join(node.get("scope") or []))
        conn.close()
    text = (repo / "ingest" / "jsonfeed.py").read_text(encoding="utf-8")
    changed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", (run / "base.sha").read_text().strip()],
        capture_output=True,
        text=True,
    ).stdout.split()
    return {
        "run": run.name,
        "arm": run.name.split("-")[1],
        "person_actions": len(person),
        "person_chars": sum(int(e.get("chars") or 0) for e in person),
        "setup_actions": len(setup),
        "setup_chars": sum(int(e.get("chars") or 0) for e in setup),
        "refused_writes": refusals,
        "leaves_made_from_the_prompt": asides,
        "their_scope": "; ".join(scopes) or "-",
        "the_change_happened": "def read_json" in text and text.count('"""') >= 4,
        "files_changed": len(changed),
        "files": " ".join(changed),
        "cost_usd": round(sum(float(e.get("cost_usd") or 0) for e in results), 4),
        "turns": sum(int(e.get("turns") or 0) for e in results),
        "seconds": round(sum(float(e.get("seconds") or 0) for e in results), 1),
    }


ROWS = (
    "person_actions", "person_chars", "setup_actions", "setup_chars", "refused_writes",
    "leaves_made_from_the_prompt", "their_scope", "the_change_happened", "files_changed",
    "files", "cost_usd", "turns", "seconds",
)  # fmt: skip


def main(argv: list[str]) -> int:
    if len(argv) > 3 and argv[1] == "run":
        runs, rep = Path(argv[2]).expanduser().resolve(), int(argv[3])
        if not shutil.which("graphene") or not shutil.which("claude"):
            raise SystemExit("graphene and claude must both be on PATH")
        for arm in ("noplan", "plan"):  # one at a time, never overlapping
            one(runs, arm, rep)
        return 0
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    where = Path(argv[1]).expanduser().resolve()
    found = sorted(p for p in where.glob("tuesday-*-*") if (p / "repo").is_dir())
    rows = [measure(p) for p in found]
    if not rows:
        sys.stderr.write("no tuesday-<plan|noplan>-<rep> runs there\n")
        return 1
    width = max(len(r) for r in ROWS) + 2
    print(f"{'':{width}}" + "".join(f"{r['run']:>26}" for r in rows))
    for key in ROWS:
        print(f"{key:{width}}" + "".join(f"{str(r[key])[:25]:>26}" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
