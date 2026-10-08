#!/usr/bin/env python3
"""Graphene building Graphene, with plan first on and the meter on itself: one step at a time.

    dogfood.py DIR init|ask|board|accept|run|shot|bill   (DIR: a clone of the branch, made first)

The person here is the agent that ran the night: every step runs with no agent's mark, as a person's
shell does, and the `you` clock counts its acts. The planner is Claude Code, read-only, on Sonnet; the
executors are Claude Code on Opus, their stream on, so the meter reads them. Every live call is on the
night's ledger, purpose `dogfood`: `graphene ask` holds the planner as `graphene run` holds an executor,
and settles it at what its stream says it cost. The ask is `ask.md` beside this file.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLANNER = (
    "claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose "
    "--model sonnet --max-budget-usd 1.5"
)
EXECUTOR = (
    "claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' 'Bash(graphene plan *)' "
    "--output-format stream-json --verbose --model opus --max-budget-usd 6"
)
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT")


def main() -> int:
    repo, step = Path(sys.argv[1]).resolve(), sys.argv[2]
    env = {k: v for k, v in os.environ.items() if k not in MARKS and not k.startswith("CLAUDE_CODE_")}
    env["GRAPHENE_NIGHT_PURPOSE"] = "dogfood"

    def sh(*argv: str) -> int:
        print("$ " + " ".join(argv[:4]) + (" …" if len(argv) > 4 else ""), flush=True)
        return subprocess.run(argv, cwd=repo, env=env).returncode

    if step == "init":
        sh("graphene", "init", "--planner", PLANNER, "--executor", EXECUTOR)
        return sh("graphene", "plan", "first", "on")
    if step == "ask":
        return sh("graphene", "ask", (HERE / "ask.md").read_text().strip())
    if step == "board":
        return sh("graphene", "board")
    if step == "accept":
        return sh("graphene", "plan", "accept")
    if step == "run":  # `run --node ID` runs a leaf that came back again
        return sh("graphene", "run", "--parallel", "2", "--with", EXECUTOR, *sys.argv[3:])
    if step == "shot":
        return sh(sys.executable, str(repo / "dev" / "screens" / "meter_shot.py"), str(repo), sys.argv[3])
    return sh("graphene", *sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
