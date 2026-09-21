#!/usr/bin/env python3
"""Every number in results-2026-09-20.md, computed from the runs. Nothing here is typed by hand.

    python3 docs/test/summarize.py <runs-dir>          # re-runs tally.py per run, writes the json
    python3 docs/test/summarize.py --json runs.json    # tabulates a json written earlier

<runs-dir> holds one directory per run named <task>-<arm>-<rep>, each with repo/ and runlog.jsonl.
Three numbers are computed here that tally.py does not print, and each says where it comes from:

  rework_code_only     rework_lines with the plan scratch files (.plan*.json, which an executor
                       writes only to feed `graphene plan propose` and then deletes) left out of
                       recorded churn. tally counts them twice - once for the write, once for the
                       rm - and they are not the task's code.
  spec_chars           how much of the person's specification reached an executor: the opening
                       prompt plus corrections in the paragraph arm; the opening prompt plus every
                       surviving node's title, goal, scope and check in the plan arm, which is what
                       `graphene run` hands the executor verbatim.
  cost_complete        whether every executor call in the run log carried a cost. `graphene run`
                       discards its executor's stdout, so some plan-arm runs report a lower bound.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = [
    ("files_changed_final_n", "files"),
    ("files_outside_intent_final_n", "outside (final)"),
    ("files_written_outside_intent_ever_n", "outside (ever)"),
    ("refused_writes", "refused"),
    ("restarts", "restarts"),
    ("rework_lines", "rework"),
    ("rework_code_only", "rework (code)"),
    ("rework_recorded_lines", "churn"),
    ("final_diff_lines", "diff lines"),
    ("recorded_write_events", "write events"),
    ("checks_passed", "checks"),
    ("person_actions", "acts"),
    ("person_chars", "person chars"),
    ("spec_chars", "spec chars"),
    ("executor_cost_usd", "cost $"),
    ("executor_turns", "turns"),
    ("wall_seconds", "wall s"),
]
SCRATCH = ".plan"  # a plan file an executor writes in the repo and deletes in the same command


def churn_without_scratch(db: Path) -> int | None:
    """Recorded churn with the plan scratch files taken out, or None when there is no store."""
    if not db.exists():
        return None
    sys.path.insert(0, str(HERE.parents[1] / "src"))
    import difflib

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    total = 0
    for row in conn.execute(
        "SELECT file_path, old_content, new_content FROM tool_events "
        "WHERE tool IN ('Edit','Write','MultiEdit','NotebookEdit') AND new_content IS NOT NULL"
    ):
        name = Path(row["file_path"] or "").name
        if name.startswith(SCRATCH) or (row["file_path"] or "").startswith("/"):
            continue
        diff = difflib.unified_diff(
            (row["old_content"] or "").splitlines(), row["new_content"].splitlines(), n=0, lineterm=""
        )
        total += sum(1 for ln in diff if ln[:1] in "+-" and not ln.startswith(("+++", "---")))
    for (raw,) in conn.execute("SELECT response FROM tool_events WHERE tool = 'Bash'"):
        try:
            entries = (json.loads(raw) or {}).get("bashEditDiff", {}).get("files") or []
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
        for entry in entries:
            if Path(entry.get("filePath") or "").name.startswith(SCRATCH):
                continue
            total += sum(
                1
                for hunk in entry.get("hunks") or []
                for ln in hunk.get("lines") or []
                if str(ln)[:1] in "+-"
            )
    conn.close()
    return total


def spec_chars(db: Path, entries: list[dict], arm: str) -> int:
    """How many characters of the person's specification an executor was handed."""
    total = sum(
        len(str(e.get("text") or ""))
        for e in entries
        if e.get("who") == "person" and e.get("type") in ("prompt", "correction")
    )
    if arm == "graphene" and db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for state, data in conn.execute("SELECT state, data FROM nodes"):
            if state == "dropped":
                continue
            node = json.loads(data)
            if node.get("owner") != "agent":
                continue  # the person's own node; no executor is ever handed its contract
            total += len(
                " ".join(
                    [node.get("title") or "", node.get("goal") or "", node.get("check") or ""]
                    + (node.get("scope") or [])
                )
            )
        conn.close()
    return total


def collect(runs_dir: Path) -> list[dict]:
    out = []
    for run in sorted(p for p in runs_dir.iterdir() if (p / "runlog.jsonl").exists()):
        task, arm, rep = run.name.rsplit("-", 2)
        if arm not in ("prompt", "graphene"):
            continue
        repo = run / "repo"
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        done = subprocess.run(
            [
                sys.executable,
                str(HERE / "tally.py"),
                str(repo),
                "--base",
                base,
                "--intent",
                str(HERE / "tasks" / task / "intent_globs.txt"),
                "--accept",
                str(HERE / "tasks" / task / "accept.py"),
                "--arm",
                arm,
                "--runlog",
                str(run / "runlog.jsonl"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        tally = json.loads(done.stdout)
        entries = [json.loads(ln) for ln in (run / "runlog.jsonl").read_text().splitlines() if ln.strip()]
        results = [e for e in entries if e.get("type") == "result"]
        db = repo / ".graphene" / "graphene.db"
        without = churn_without_scratch(db)
        tally.update(
            run=run.name,
            task=task,
            rep=int(rep),
            rework_code_only=None if without is None else max(0, without - tally["final_diff_lines"]),
            spec_chars=spec_chars(db, entries, arm),
            cost_complete=bool(results) and all(e.get("cost_usd") for e in results),
            executor_calls=len(results),
            checks_passed=f"{tally['acceptance']['passed']}/"
            f"{tally['acceptance']['passed'] + tally['acceptance']['failed']}",
        )
        out.append(tally)
    return out


def cell(run: dict, key: str) -> str:
    value = run.get(key)
    if value is None:
        return "-"
    if key == "executor_cost_usd":
        return f"{value:.3f}" + ("" if run["cost_complete"] else "+")
    return str(value)


def table(runs: list[dict]) -> str:
    head = ["run", "valid"] + [label for _, label in COLUMNS]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for run in runs:
        row = [run["run"], "yes" if run.get("valid", True) else "NO"]
        row += [cell(run, key) for key, _ in COLUMNS]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def medians(runs: list[dict]) -> str:
    numeric = [(k, label) for k, label in COLUMNS if k != "checks_passed"]
    groups = {}
    for run in runs:
        groups.setdefault((run["task"], run["arm"]), []).append(run)
        groups.setdefault(("all", run["arm"]), []).append(run)
    head = ["task", "arm", "n"] + [label for _, label in numeric]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for task in ("report", "inventory", "logs", "all"):
        for arm in ("prompt", "graphene"):
            group = groups.get((task, arm), [])
            if not group:
                continue
            row = [task, arm, str(len(group))]
            for key, _ in numeric:
                values = [r[key] for r in group if r.get(key) is not None]
                row.append(f"{statistics.median(values):g}" if values else "-")
            lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--json":
        runs = json.loads(Path(argv[2]).read_text())
    elif len(argv) > 1:
        runs = collect(Path(argv[1]).expanduser().resolve())
        Path(HERE / "runs-2026-09-20.json").write_text(json.dumps(runs, indent=1))
    else:
        print(__doc__)
        return 2
    print(table(runs))
    print()
    print(medians(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
