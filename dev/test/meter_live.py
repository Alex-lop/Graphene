#!/usr/bin/env python3
"""The meter, live: the feeds task, run by `graphene run --parallel 2` with each executor.

    dev/test/meter_live.py OUT --tool BIN [--executors claude codex nemotron] [--rounds 2] [--tree FILE]

Each run gets OUT/<executor>-r<round>/: the repo, the run's output (`run.txt`), the screens of `graphene
watch` while it ran (`shots/`, at 80 and 120 columns, by meter_shot.py), `node show` of each leaf,
`git log --graph`, the hidden checks, and the night's ledger rows from the run's window. OUT/summary.md
is the table: the bill line beside the ledger's sum for the same run.

The person's acts (init, ask, accept, run) run with no agent's mark: the person is this script. Every run
gets the same tree, so the executors are compared on one plan: --tree is a planner's proposal saved
from an earlier ask, printed by a canned planner. Without --tree, the first run asks Claude Code's
planner and its proposal is saved for the rest (OUT/tree.txt).

Spend goes on the night's ledger, purpose `meter`: GRAPHENE_AGENT_LIVE_USD must be set. Claude Code runs
Sonnet with --max-budget-usd 2 an attempt. Codex runs `codex exec --json` against Nemotron Super on
Token Factory (the ChatGPT login here was revoked on 6 October), with a CODEX_HOME of its own so the
person's Codex plugins stay out. Nemotron is Graphene's own executor, on this machine.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FEEDS = ROOT / "dev" / "test" / "tasks" / "feeds"
TF = "https://api.tokenfactory.nebius.com/v1"
WITH = {
    "claude": "claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' "
    "'Bash(graphene plan *)' --output-format stream-json --verbose --model sonnet --max-budget-usd 2",
    "codex": 'codex exec --json --sandbox workspace-write -c \'model_providers.tf={name="Token Factory", '
    f'base_url="{TF}", env_key="NEBIUS_API_KEY", wire_api="responses"}}\' -c \'model_provider="tf"\' '
    "-m nvidia/nemotron-3-super-120b-a12b",
    "nemotron": "nemotron --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --model "
    "nvidia/nemotron-3-super-120b-a12b --placement local",
}
# The one real planner call: Claude Code, read-only, on Sonnet. Its text answer reports no cost, so the
# ledger holds its --max-budget-usd, the most it can spend.
PLANNER = "claude -p --tools Read,Grep,Glob --strict-mcp-config --model sonnet --max-budget-usd 1.5"
LEDGER_MODEL = {"claude": "claude:", "codex": "codex:", "nemotron": "nvidia/"}
MARKS = (
    "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_ENTRYPOINT",
    "CODEX_SESSION_ID",
    "CODEX_SANDBOX",
    "AI_AGENT",
    "GEMINI_CLI",
    "CURSOR_AGENT",
)


def person(tool: str, codex_home: Path) -> dict:
    """The person's shell: this environment less every agent's mark, the tool under test first."""
    env = {k: v for k, v in os.environ.items() if k not in MARKS and not k.startswith("CLAUDE_CODE_")}
    env |= {
        "PATH": f"{tool}{os.pathsep}{os.environ['PATH']}",
        "GRAPHENE_NIGHT_PURPOSE": "meter",
        "CODEX_HOME": str(codex_home),
        "TERM": "dumb",
    }
    return env


def sh(argv: list[str], cwd: Path, env: dict, timeout: int = 900) -> str:
    done = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    return (done.stdout + done.stderr).rstrip()


def ledger_rows(since: float, until: float, prefix: str, leaves: list[str]) -> list[dict]:
    """The run's own rows on the night's ledger: those of its attempts (Claude Code and Codex reserve
    as `run: <leaf> attempt <n>`) or of its leaves' calls (Nemotron's carry the leaf's id), in its window.
    A planner's rows, and another run's, are left out."""
    from graphene_map.nemotron import night  # the tool's own: the ledger the run wrote

    path = night.where()
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    tags = {r.get("id"): str(r.get("tag") or "") for r in rows if r.get("kind") == "reserve"}

    def mine(r: dict) -> bool:  # `run: <leaf> attempt <n>`, or a Nemotron call's own leaf id
        words = tags.get(r.get("id"), "").split()
        leaf = words[1] if words[:1] == ["run:"] and len(words) > 1 else words[0] if words else ""
        return leaf in leaves

    return [
        r
        for r in rows
        if since <= r.get("at", 0) <= until and str(r.get("model", "")).startswith(prefix) and mine(r)
    ]


def one(executor: str, rnd: int, a, env: dict) -> dict:
    here = a.out / f"{executor}-r{rnd}"
    repo, shots = here / "repo", here / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(ROOT / "dev" / "test" / "make_task.py"), "feeds", str(repo)],
        check=True,
        capture_output=True,
    )
    tree = a.out / "tree.txt"
    planner = PLANNER
    if tree.exists():
        canned = a.out / "planner.sh"
        canned.write_text(f"#!/bin/sh\ncat '{tree}'\n")
        canned.chmod(0o755)
        planner = str(canned)
    said = [
        f"$ graphene init --planner {Path(planner).name} --executor {executor}",
        sh(["graphene", "init", "--planner", planner, "--executor", WITH[executor]], repo, env),
    ]
    paragraph = (FEEDS / "paragraph.md").read_text().strip()
    held = None
    if planner == PLANNER:
        from graphene_map.nemotron import night

        os.environ[night.PURPOSE] = "meter"
        held = night.reserve("claude:sonnet planner", 1.5, "meter: the planner's ask", "claude code")
    said += ['$ graphene ask "$(cat paragraph.md)"', sh(["graphene", "ask", paragraph], repo, env, 1800)]
    if held:
        night.settle(held, "claude:sonnet planner", 1.5, {})  # its worst case: a text answer says no cost
    if not tree.exists():
        tree.write_text(sh(["graphene", "plan", "--text", "--all"], repo, env) + "\n")
    said += ["$ graphene board", sh(["graphene", "board"], repo, env)]
    said += ["$ graphene plan accept", sh(["graphene", "plan", "accept"], repo, env)]
    leaves = [
        n["id"]
        for n in json.loads(sh(["graphene", "plan", "--json", "--all"], repo, env))["nodes"]
        if n.get("scope")
    ]
    started = time.time()
    with open(here / "run.txt", "w") as out:
        run = subprocess.Popen(
            ["graphene", "run", "--parallel", "2", "--with", WITH[executor]],
            cwd=repo,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        n = 0
        while run.poll() is None:
            time.sleep(a.every)
            n += 1
            subprocess.run(
                [
                    a.python,
                    str(HERE.parent / "screens" / "meter_shot.py"),
                    str(repo),
                    str(shots / f"{n:02d}"),
                ],
                env=env,
                capture_output=True,
                timeout=120,
            )
    ended = time.time()
    text = (here / "run.txt").read_text()
    bill = next((line for line in reversed(text.splitlines()) if line.startswith("run")), "")
    shown = re.search(r"\$([0-9.]+) at list price", bill)
    rows = ledger_rows(started - 1, ended + 1, LEDGER_MODEL[executor], leaves)
    ledger = sum(float(r.get("dollars") or 0) for r in rows if r.get("kind") == "settle")
    raw = raw_claude(repo) if executor == "claude" else None
    for leaf in leaves:
        (here / f"node-show-{leaf}.txt").write_text(sh(["graphene", "node", "show", leaf], repo, env) + "\n")
    said += [
        f"$ graphene run --parallel 2 --with {executor}",
        text.rstrip(),
        "$ git log --graph --oneline --all",
        sh(["git", "log", "--graph", "--oneline", "--all"], repo, env),
    ]
    checks = {}
    for check in ("accept", "quality"):
        got = sh([sys.executable, str(FEEDS / f"{check}.py"), str(repo)], repo, env)
        try:
            checks[check] = json.loads(got[got.index("{") :])
        except ValueError:
            checks[check] = {}
    (here / "transcript.txt").write_text("\n\n".join(said) + "\n")
    (here / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return {
        "executor": executor,
        "round": rnd,
        "bill": bill,
        "bill_dollars": float(shown.group(1)) if shown else None,
        "ledger_dollars": round(ledger, 4),
        "raw_dollars": raw,
        "minutes": round((ended - started) / 60, 1),
        "accept": f"{checks['accept'].get('passed', '?')}/{_n(checks['accept'])}",
        "quality": f"{checks['quality'].get('passed', '?')}/{_n(checks['quality'])}",
        "shots": n,
    }


def raw_claude(repo: Path) -> float:
    """What Claude Code itself reported for the run, read from the attempts' logs and not from the meter:
    each session's highest total_cost_usd (a resumed session reports its running total)."""
    best: dict[str, float] = {}
    for log in (repo / ".graphene" / "runs").glob("*-*-*-*.txt"):
        for line in log.read_text(errors="replace").splitlines():
            if '"type":"result"' not in line.replace(" ", ""):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            sid = str(ev.get("session_id"))
            best[sid] = max(best.get(sid, 0.0), float(ev.get("total_cost_usd") or 0))
    return round(sum(best.values()), 4)


def _n(got: dict) -> object:
    p, f = got.get("passed"), got.get("failed")
    return p + f if isinstance(p, int) and isinstance(f, int) else "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--tool", required=True, help="the bin directory of graphene installed as a tool")
    ap.add_argument("--python", required=True, help="that tool's python, which draws the screens")
    ap.add_argument("--executors", nargs="*", default=list(WITH))
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--every", type=float, default=20.0, help="seconds between screens")
    a = ap.parse_args()
    if not os.environ.get("GRAPHENE_AGENT_LIVE_USD"):
        sys.exit(
            "GRAPHENE_AGENT_LIVE_USD is not set: these runs spend, and the night's ledger must count them"
        )
    a.out.mkdir(parents=True, exist_ok=True)
    codex_home = a.out / "codex-home"
    codex_home.mkdir(exist_ok=True)
    env = person(a.tool, codex_home)
    rows = []
    for rnd in range(1, a.rounds + 1):
        for executor in a.executors:
            rows.append(one(executor, rnd, a, env))
            print(json.dumps(rows[-1]), flush=True)
    lines = [
        "| executor | round | minutes | bill line | bill $ | ledger $ | Claude's own $ | accept | quality |",
        "|" + "---|" * 9,
    ]
    for r in rows:
        lines.append(
            f"| {r['executor']} | {r['round']} | {r['minutes']} | `{r['bill']}` | {r['bill_dollars']} | "
            f"{r['ledger_dollars']} | {r['raw_dollars'] if r['raw_dollars'] is not None else '–'} | "
            f"{r['accept']} | {r['quality']} |"
        )
    (a.out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
