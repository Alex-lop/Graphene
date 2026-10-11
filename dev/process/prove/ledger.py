#!/usr/bin/env python3
"""ledger.py OUT... : the spend under each directory, from the sessions' own results (see ledger.sh)."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

UNMARK = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT", "GRAPHENE_NODE",
          "GRAPHENE_PLANNER")


def results(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "total_cost_usd" in obj:
            yield obj
        return
    except ValueError:
        pass
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result" and "total_cost_usd" in event:
            yield event


def sessions(root: Path) -> tuple[float, int]:
    best: dict[str, float] = {}
    n = 0
    for path in root.rglob("*"):
        if path.suffix not in (".json", ".jsonl", ".txt") or not path.is_file():
            continue
        if path.suffix == ".txt" and path.parent.name != "runs":
            continue
        for event in results(path):
            cost = event.get("total_cost_usd")
            if not isinstance(cost, (int, float)):
                continue
            sid = event.get("session_id") or str(path)
            best[sid] = max(best.get(sid, 0.0), float(cost))
            n += 1
    return round(sum(best.values()), 4), n


def planner_bills(root: Path) -> tuple[float, int]:
    env = {k: v for k, v in os.environ.items() if k not in UNMARK}
    env["GRAPHENE_AS"] = f"person:{os.environ.get('USER', 'person')}"
    total, n = 0.0, 0
    for db in root.rglob(".graphene/graphene.db"):
        repo = db.parent.parent
        done = subprocess.run(["graphene", "plan", "record"], cwd=repo, env=env, capture_output=True, text=True)
        for m in re.finditer(r"the planner's bill: \$([0-9.]+) at list price", done.stdout):
            total += float(m.group(1))
            n += 1
    return round(total, 4), n


def main(dirs: list[str]) -> int:
    stamp = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())
    print(f"\n## ledger at {stamp}\n")
    print("| directory | sessions ($, max per session id) | results read | planner bills ($) | plans | total ($) |")
    print("|---|---|---|---|---|---|")
    grand = 0.0
    for d in dirs:
        root = Path(d)
        s, sn = sessions(root)
        p, pn = planner_bills(root)
        grand += s + p
        print(f"| {root} | {s:.4f} | {sn} | {p:.4f} | {pn} | {s + p:.4f} |")
    print(f"| **all** | | | | | **{grand:.4f}** |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
