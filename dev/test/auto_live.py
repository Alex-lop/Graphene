#!/usr/bin/env python3
"""Plan first auto, live: each message in a fresh feeds repo, one Claude Code session each.

    dev/test/auto_live.py OUT [--rounds 2] [--only NAME ...] [--graphene BIN_DIR]

Each run gets OUT/<name>-r<round>/: the repo, the session's stream (`stream.jsonl`), and `run.txt`
with the plan, its log, the board, `git status` and the hidden checks. OUT/summary.md is the table.
The five sessions of a round run at once, as on 5 October (dev/process/cut/lane5-evidence.md).

The person's acts (`graphene init`, reading the plan) run with no agent's mark, as there. The session
is the 23 September study's: Sonnet and its tool list (standin.py). graphene comes from --graphene, a
wheel installed as a tool, never editable, so the hooks run the code under test.

Every session is on the night's ledger, purpose `auto`: it reserves its --max-budget-usd before it
starts and settles at the `total_cost_usd` its result reports. It needs GRAPHENE_AGENT_LIVE_USD.

The four Tuesday messages were written on 6 October from their one-line descriptions in
lane5-evidence.md. The 23 September originals live only in Claude Code's transcript store, which this
script does not read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from graphene_map.nemotron import night  # noqa: E402

TASKS = HERE / "tasks" / "feeds"
MESSAGES = {
    "tuesday-1": "Northwind send their price feed as XML, there's a sample in samples/. Make it load like "
    "the csv and json feeds do, same command, same output.",
    "tuesday-2": "Northwind's price feed comes as XML, sample in samples/. Make it load the way the csv and "
    "json feeds load, same command and output. Their prices are already in cents.",
    "tuesday-3": "We have a new supplier, Northwind, whose feed is XML (see samples/). Load it like csv and "
    "json, with the same command and output. Their prices are already in cents.",
    "tuesday-4": "Add Northwind's XML feed from samples/ as a source: same load command and same output as "
    "the csv and json feeds. The prices in it are in cents.",
    "paragraph": (TASKS / "paragraph.md").read_text().strip(),
}
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
]
BUDGET = 1.5  # dollars a session may spend: --max-budget-usd, and what it reserves


def person(path: str) -> dict:
    """The person's shell: no agent's mark, as `env -i` gives it."""
    return {"PATH": path, "HOME": os.environ["HOME"], "LANG": "C.UTF-8", "TERM": "dumb"}


def sh(argv: list[str], cwd: Path, env: dict, timeout: int = 600) -> str:
    done = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    return (done.stdout + done.stderr).rstrip()


def one(name: str, rnd: int, out: Path, path: str) -> dict:
    here = out / f"{name}-r{rnd}"
    repo = here / "repo"
    here.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(HERE / "make_task.py"), "feeds", str(repo)], check=True, capture_output=True
    )
    me = person(path)
    init = ["graphene", "init", "--planner", "claude", "--executor", "claude"]
    said = [f"$ {' '.join(init)}\n{sh(init, repo, me)}"]
    argv = [
        "claude",
        "-p",
        MESSAGES[name],
        "--model",
        "sonnet",
        "--permission-mode",
        "acceptEdits",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        "25",
        "--setting-sources",
        "project,local",
        "--max-budget-usd",
        str(BUDGET),
        "--allowedTools",
        *TOOLS,
    ]
    os.environ[night.PURPOSE] = "auto"
    held = night.reserve("claude:sonnet", BUDGET, f"auto: {name} r{rnd}", "claude code")
    started = time.monotonic()
    with open(here / "stream.jsonl", "w") as f:
        subprocess.run(
            argv,
            cwd=repo,
            env=os.environ | {"PATH": path},
            stdout=f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=1800,
        )
    seconds = time.monotonic() - started
    result = {}
    for line in (here / "stream.jsonl").read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            result = ev
    cost = float(result.get("total_cost_usd") or 0)
    usage = result.get("usage") or {}
    night.settle(
        held,
        "claude:sonnet",
        cost,
        {
            "prompt_tokens": sum(
                usage.get(k, 0)
                for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            ),
            "completion_tokens": usage.get("output_tokens", 0),
        },
    )
    plan = sh(["graphene", "plan", "--text", "--all"], repo, me)
    log = sh(["graphene", "plan", "log"], repo, me)
    board = sh(["graphene", "board"], repo, me)
    status = sh(["git", "status", "--short"], repo, me)
    nodes = json.loads(sh(["graphene", "plan", "--json", "--all"], repo, me) or "{}").get("nodes", [])
    checks = {}
    for check in ("accept", "quality"):
        got = sh([sys.executable, str(TASKS / f"{check}.py"), str(repo)], repo, me | {"PATH": path})
        try:
            checks[check] = json.loads(got[got.index("{") :])
        except ValueError:
            checks[check] = {"passed": "?", "failed": "?"}
    leaves = [n for n in nodes if not any(m.get("parent") == n["id"] for m in nodes)]
    row = {
        "name": name,
        "round": rnd,
        "leaves": len(leaves),
        "nodes": len(nodes),
        "board": int(m.group(1)) if (m := re.search(r"the board: (\d+) open", board)) else 0,
        "states": sorted({n["state"] for n in nodes}),
        "widths": [len(n.get("scope") or []) for n in leaves],
        "taken": "by their prompt" in log or "one-line ask" in log,
        "wrote": bool([s for s in status.splitlines() if s.strip()]),
        "accept": f"{checks['accept'].get('passed')}/{_total(checks['accept'])}",
        "quality": f"{checks['quality'].get('passed')}/{_total(checks['quality'])}",
        "turns": result.get("num_turns"),
        "dollars": round(cost, 4),
        "seconds": round(seconds),
    }
    said += [
        f"$ claude -p <{name}> ... ({row['turns']} turns, ${cost:.2f}, {seconds:.0f} s)",
        "reply: " + str(result.get("result") or "")[:1200],
        f"$ graphene plan --text --all\n{plan}",
        f"$ graphene board\n{board}",
        f"$ graphene plan log\n{log}",
        f"$ git status --short\n{status}",
        f"hidden checks: accept {row['accept']}, quality {row['quality']}",
    ]
    (here / "run.txt").write_text("\n\n".join(said) + "\n")
    return row


def _total(got: dict) -> object:
    p, f = got.get("passed"), got.get("failed")
    return p + f if isinstance(p, int) and isinstance(f, int) else "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--only", nargs="*", default=list(MESSAGES))
    ap.add_argument("--graphene", help="the bin directory of a graphene installed as a tool")
    a = ap.parse_args()
    if night.cap() is None:
        sys.exit(f"{night.OPENING} is not set: these sessions spend, and the night's ledger must count them")
    path = os.pathsep.join(p for p in (a.graphene, os.environ["PATH"]) if p)
    rows = []
    for rnd in range(1, a.rounds + 1):
        with ThreadPoolExecutor(len(a.only)) as pool:
            rows += list(pool.map(lambda n, r=rnd: one(n, r, a.out, path), a.only))
    head = (
        "| message | round | nodes | leaves | board | taken at once | wrote code | accept | quality "
        "| turns | $ | s |"
    )
    lines = [head, "|" + "---|" * 12]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['round']} | {r['nodes']} | {r['leaves']} {r['widths']} "
            f"| {r['board']} | "
            f"{'yes' if r['taken'] else 'no'} | {'yes' if r['wrote'] else 'no'} | {r['accept']} | "
            f"{r['quality']} | {r['turns']} | {r['dollars']} | {r['seconds']} |"
        )
    (a.out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
