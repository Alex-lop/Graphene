#!/usr/bin/env python3
"""Do the paragraph's cross-cutting conditions reach every executor? One tree-arm planning session on a
fresh `statements` repo (a Claude Code session with plan first on, as PREREG-statements.md's tree arm
plans), then each leaf's contract exactly as `graphene run` would send it, searched for the conditions.

    dev/test/standing_check.py OUT --graphene BIN_DIR [--model sonnet]

On the night's ledger, purpose `statements-practice` unless GRAPHENE_NIGHT_PURPOSE names another: the
session reserves its --max-budget-usd and settles at the total_cost_usd it reports. Needs
GRAPHENE_AGENT_LIVE_USD.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEST = HERE
sys.path.insert(0, str(ROOT / "src"))
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
CONDITIONS = {
    "half-even": ("half-even", "half even", "banker"),
    "vendor": ("vendor",),
    "legacy byte for byte": ("byte for byte", "byte-for-byte", "legacy/monthly"),
    "v1 shape": ("v1",),
}
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--graphene", required=True)
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    if night.cap() is None:
        sys.exit(f"{night.OPENING} is not set")
    repo = a.out / "repo"
    subprocess.run(
        [sys.executable, str(TEST / "make_task.py"), "statements", str(repo)], check=True, capture_output=True
    )
    path = f"{a.graphene}{os.pathsep}{os.environ['PATH']}"
    me = {k: v for k, v in os.environ.items() if k not in MARKS} | {"PATH": path}

    def sh(*argv: str, env: dict = me) -> str:
        done = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, timeout=1800)
        return (done.stdout + done.stderr).rstrip()

    said = [
        sh("graphene", "init", "--planner", "claude", "--executor", "claude"),
        sh("graphene", "plan", "first", "on"),
    ]
    paragraph = (TEST / "tasks" / "statements" / "paragraph.md").read_text().strip()
    os.environ[night.PURPOSE] = os.environ.get(night.PURPOSE) or "statements-practice"
    held = night.reserve(f"claude:{a.model}", 2.0, "statements-practice: the tree arm plans", "claude code")
    out = sh(
        "claude",
        "-p",
        paragraph,
        "--model",
        a.model,
        "--permission-mode",
        "acceptEdits",
        "--output-format",
        "json",
        "--max-turns",
        "40",
        "--max-budget-usd",
        "2",
        "--setting-sources",
        "project,local",
        "--allowedTools",
        *TOOLS,
        env=os.environ | {"PATH": path},
    )
    try:
        result = json.loads(out[out.index("{") :])
    except ValueError:
        result = {}
    night.settle(held, f"claude:{a.model}", float(result.get("total_cost_usd") or 0), {})
    said += [
        f"session: {result.get('num_turns')} turns, ${result.get('total_cost_usd')}",
        str(result.get("result"))[:3000],
    ]
    said += [
        sh("graphene", "plan", "--text", "--all"),
        sh("graphene", "board"),
        sh("graphene", "plan", "accept"),
    ]
    told = sh(sys.executable, "-c", PROMPTS, env=me | {"PYTHONPATH": str(ROOT / "src")})
    (a.out / "contracts.txt").write_text(told + "\n")
    leaves = told.split("\n=== ")
    lines = ["| leaf | " + " | ".join(CONDITIONS) + " |", "|---|" + "---|" * len(CONDITIONS)]
    for leaf in leaves[1:]:
        name, body = leaf.split("\n", 1)
        low = body.lower()
        cells = ["yes" if any(w in low for w in words) else "no" for words in CONDITIONS.values()]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    said.append("\n".join(lines))
    (a.out / "standing.txt").write_text("\n\n".join(said) + "\n")
    print("\n".join(lines))
    return 0


PROMPTS = """
from graphene_map import plan as P, board as B, run as R
from graphene_map.store import Store
from pathlib import Path
with Store.open(Path.cwd()) as store:
    for n in P.nodes(store):
        if n.scope:
            print('\\n=== ' + n.id)
            print(R.prompt_for(n, [], None, P.trail(store, n), B.decided(store, n)))
"""

if __name__ == "__main__":
    sys.exit(main())
