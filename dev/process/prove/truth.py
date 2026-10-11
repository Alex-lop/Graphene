#!/usr/bin/env python3
"""truth.json for one planted X2 run, written by script before any reader exists.

    truth.py RUN     (a newrun.sh directory: repo/, base.sha, plant.txt, run1.txt, run2.txt, run3.txt)

Every value says where it came from: git (the merges since the base), the plan's log (graphene plan
log: released, reopened, proposed rows), the plan's record (graphene plan record: bills, width,
checks), the executors' own result events (.graphene/runs/*.txt: permission_denials, total_cost_usd,
turns) and the run outputs (red first's lines, hand-backs). Prints the JSON."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

UNMARK = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT", "GRAPHENE_NODE",
          "GRAPHENE_PLANNER")


def me(repo: Path, *argv: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in UNMARK}
    env["GRAPHENE_AS"] = f"person:{os.environ.get('USER', 'person')}"
    done = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True)
    return done.stdout + done.stderr


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def merges(repo: Path, base: str) -> list[dict]:
    out = subprocess.run(["git", "-C", str(repo), "log", "--merges", "--reverse", "--format=%H%x09%ct%x09%s", f"{base}..HEAD"],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        sha, at, subject = line.split("\t", 2)
        m = re.search(r"\(([^(),]+)(?:, reopened)?\)\s*$", subject)
        rows.append({"sha": sha, "at": int(at), "subject": subject, "id": m.group(1) if m else None,
                     "reopened": ", reopened)" in subject})
    return rows


def log_rows(text: str) -> list[dict]:
    """plan_cli.log_line's columns, two or more spaces apart: time, node, kind, who (which may hold one
    space: 'alexlopez (no terminal)'), then what was said."""
    rows = []
    for line in text.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 4 and parts[0].endswith("Z"):
            rows.append({"at": parts[0], "node": parts[1], "kind": parts[2], "who": parts[3],
                         "said": " ".join(parts[4:]).strip()})
    return rows


def run_logs(repo: Path) -> list[dict]:
    out = []
    for path in sorted((repo / ".graphene" / "runs").glob("*.txt")):
        m = re.match(r"(.+)-(\d{8}T\d{6})-([0-9a-f]{8})-(\d+)\.txt$", path.name)
        if not m:
            continue
        result, turns = None, set()
        for line in read(path).splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "assistant":
                turns.add((event.get("message") or {}).get("id"))
            elif event.get("type") == "result":
                result = event
        out.append({"node": m.group(1), "attempt": int(m.group(4)), "file": path.name, "turns": len(turns),
                    "denials": len((result or {}).get("permission_denials") or []),
                    "denied": [((d.get("tool_input") or {}).get("command") or d.get("tool_name") or "?")[:120]
                               for d in (result or {}).get("permission_denials") or []],
                    "total_cost_usd": (result or {}).get("total_cost_usd"),
                    "subtype": (result or {}).get("subtype")})
    return out


def main(run: Path) -> int:
    repo = run / "repo"
    base = read(run / "base.sha").strip()
    record = me(repo, "graphene", "plan", "record")
    log = log_rows(me(repo, "graphene", "plan", "log"))
    plant = read(run / "plant.txt").splitlines()
    accepted_at = next((i for i, r in enumerate(log) if r["kind"] == "accepted"), None)
    outputs = {name: read(run / f"{name}.txt") for name in ("run1", "run2", "run3")}
    lines = [line for text in outputs.values() for line in text.splitlines()]
    bills = {m.group(1): float(m.group(2)) for m in re.finditer(r"(the planner's bill|bill): \$([0-9.]+) at list price", record)}
    width = re.search(r"width (\d+) of (\d+)", record)
    logs = run_logs(repo)
    planted = next((p for p in plant if re.fullmatch(r"[0-9a-f]{40}", p)), None)
    planted_at = int(subprocess.run(["git", "-C", str(repo), "show", "-s", "--format=%ct", planted],
                                    capture_output=True, text=True).stdout.strip() or 0) if planted else None
    # a leaf reopened for a reason (the r offer's note), not a sub-goal reopened because a leaf under it is
    reopened = [{"node": r["node"], "note": r["said"], "by": r["who"]} for r in log
                if r["kind"] == "reopened" and not r["said"].startswith("a node under it")]
    truth = {
        "run": run.name, "base": base,
        "merges": merges(repo, base),
        "planted_commit": planted, "planted_at": planted_at,
        "plant": plant[0] if plant else None,
        "r_offer": next((p[len("r offer: "):] for p in plant if p.startswith("r offer: ")), None),
        "came_back": [{"node": r["node"], "why": r["said"], "by": r["who"]} for r in log if r["kind"] == "released"],
        "reopened": reopened,
        "added_after_acceptance": sorted({r["node"] for r in log[accepted_at + 1:] if r["kind"] in ("proposed", "added")})
        if accepted_at is not None else [],
        "bills": bills, "dollars_total": round(sum(bills.values()), 4),
        "width": {"peak": int(width.group(1)), "of": int(width.group(2))} if width else None,
        "checks_line": next((line.strip() for line in record.splitlines() if "checks run by Graphene itself" in line), None),
        "attempts": logs,
        "denials": sum(a["denials"] for a in logs), "turns": sum(a["turns"] for a in logs),
        "red_first": [line.strip() for line in lines if line.startswith("red first:") or ": its check " in line],
        "handed_back": [line.strip() for line in lines if "handed back by" in line],
        "run_lines": [line.strip() for line in lines if line.startswith(("run:", "run stopped:"))],
        "seconds": {k: int(v) for k, v in (line.split() for line in read(run / "seconds.txt").splitlines()
                                          if len(line.split()) == 2)},
    }
    # the fix landed in the owner's file when a merge after the plant is the leaf that was reopened for it
    after = [m for m in truth["merges"] if planted_at and m["at"] >= planted_at]
    truth["merges_after_plant"] = [m["id"] for m in after]
    truth["fix_landed_in_owner"] = any(m["id"] in {r["node"] for r in reopened} for m in after)
    truth["why_recorded"] = any(r["note"].startswith("came back from") for r in reopened)
    print(json.dumps(truth, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
