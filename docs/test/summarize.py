#!/usr/bin/env python3
"""Every number in results-2026-09-21.md and results-2026-09-23.md, computed from the runs. Nothing
here is typed by hand.

    python3 docs/test/summarize.py <runs-dir> [--out runs-2026-09-23.json]
    python3 docs/test/summarize.py --json runs-2026-09-23.json

<runs-dir> holds one directory per run named <task>-<style>-<arm>-<rep>, each with repo/ and
runlog.jsonl. A run with a `void.txt` beside its runlog is printed in the per-run table with
`valid` = NO and its reason, and is left out of every median.

`style` is how the stand-in wrote (`dense` or `tuesday`); `arm` is `prompt`, `graphene` (21
September) or `tree` (23 September, whose attention numbers come from attention.py and are
MODELLED person-seconds, printed beside the raw counts they are made of). A run directory from the
20 September test, named <task>-<arm>-<rep>, still reads: its style is recorded as `dense`, which
is what those stand-ins wrote.

Two numbers are computed here that tally.py does not print, and each says where it comes from:

  spec_chars           how much of the person's specification reached an executor: the opening
                       prompt plus corrections in the paragraph arm; the opening prompt plus every
                       surviving node's title, goal, scope and check in the plan arm, which is what
                       `graphene run` hands the executor verbatim.
  handoff              spec_chars per person action: how much specification the person got in front
                       of an executor for each thing they did. The directive's measure, as close as
                       this harness can get to it.
  unforced             how many times the person had to speak to an executor, other than the change
                       of mind the card forces on them: every `prompt` plus every `correction` not
                       marked `mandated`. `restarts` asks a stand-in to decide whether what they
                       typed was a correction or a next step, and on 21 September two runs of the
                       same cell called the identical event by the two different names. This one
                       asks nobody anything: it counts messages.

Everything else — including `quality`, the held-out checks, and both restart counts — comes
straight out of tally.py.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from attention import attention  # noqa: E402

TASKS = ("feeds", "report", "inventory", "logs")
ARMS = ("prompt", "graphene", "tree")
COLUMNS = [
    ("files_changed_final_n", "files"),
    ("files_outside_intent_final_n", "outside (final)"),
    ("files_written_outside_intent_ever_n", "outside (ever)"),
    ("refused_writes", "refused"),
    ("restarts", "restarts"),
    ("restarts_unmandated", "restarts (real)"),
    ("unforced_messages", "unforced"),
    ("rework_lines", "rework"),
    ("rework_recorded_lines", "churn"),
    ("churn_double_counted_lines", "double-counted"),
    ("final_diff_lines", "diff lines"),
    ("recorded_write_events", "write events"),
    ("checks_passed", "accept"),
    ("quality_passed", "held-out"),
    ("person_actions", "acts"),
    ("person_chars", "person chars"),
    ("spec_chars", "spec chars"),
    ("handoff", "spec/act"),
    ("typed_chars", "typed"),
    ("read_words", "read words"),
    ("modelled_seconds", "person-s (model)"),
    ("to_run_seconds", "to run (model)"),
    ("caught_before_code_n", "caught"),
    ("executor_cost_usd", "cost $"),
    ("executor_turns", "turns"),
    ("wall_seconds", "wall s"),
]


def spec_chars(db: Path, entries: list[dict], arm: str) -> int:
    """How many characters of the person's specification an executor was handed."""
    total = sum(
        len(str(e.get("text") or ""))
        for e in entries
        if e.get("who") == "person" and e.get("type") in ("prompt", "correction")
    )
    if arm in ("graphene", "tree") and db.exists():
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


def name_of(run: Path) -> tuple[str, str, str, int] | None:
    """<task>-<style>-<arm>-<rep>, or the 20 September <task>-<arm>-<rep>."""
    parts = run.name.split("-")
    if len(parts) == 4:
        task, style, arm, rep = parts
    elif len(parts) == 3:
        task, arm, rep = parts
        style = "dense"
    else:
        return None
    if arm not in ARMS or not rep.isdigit():
        return None
    return task, style, arm, int(rep)


def collect(runs_dir: Path) -> list[dict]:
    out = []
    for run in sorted(p for p in runs_dir.iterdir() if (p / "runlog.jsonl").exists()):
        named = name_of(run)
        if named is None:
            continue
        task, style, arm, rep = named
        repo = run / "repo"
        base = (run / "base.sha").read_text().strip()
        quality = HERE / "tasks" / task / "quality.py"
        argv = [
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
        ]
        if quality.exists():
            argv += ["--quality", str(quality)]
        done = subprocess.run(argv, capture_output=True, text=True, check=True)
        tally = json.loads(done.stdout)
        entries = [json.loads(ln) for ln in (run / "runlog.jsonl").read_text().splitlines() if ln.strip()]
        db = repo / ".graphene" / "graphene.db"
        spec = spec_chars(db, entries, arm)
        acc, qua = tally["acceptance"], tally.get("quality")
        unforced = sum(
            1
            for e in entries
            if e.get("who") == "person"
            and (e.get("type") == "prompt" or (e.get("type") == "correction" and not e.get("mandated")))
            and str(e.get("text") or "").strip()
        )
        seen = attention(run, arm)
        tally.update(
            typed_chars=seen["typed_chars"],
            read_words=seen["read_words"],
            modelled_seconds=seen["modelled_seconds"],
            to_run_seconds=seen["to_run"]["modelled_seconds"],
            caught_before_code_n=seen["caught_before_code_n"],
            caught_before_code=seen["caught_before_code"],
            attention_notes=seen["notes"],
        )
        void = run / "void.txt"
        tally.update(
            unforced_messages=unforced,
            valid=not void.exists(),
            void_reason=void.read_text().strip() if void.exists() else "",
            run=run.name,
            task=task,
            style=style,
            rep=rep,
            spec_chars=spec,
            handoff=round(spec / tally["person_actions"], 1) if tally["person_actions"] else None,
            cost_complete=not tally["executor_calls_unpriced"],
            checks_passed=f"{acc['passed']}/{acc['passed'] + acc['failed']}",
            accept_rate=round(acc["passed"] / max(1, acc["passed"] + acc["failed"]), 3),
            quality_passed=f"{qua['passed']}/{qua['passed'] + qua['failed']}" if qua else None,
            quality_rate=round(qua["passed"] / max(1, qua["passed"] + qua["failed"]), 3) if qua else None,
        )
        out.append(tally)
    return out


def cell(run: dict, key: str) -> str:
    value = run.get(key)
    if value is None:
        return "-"
    if key == "executor_cost_usd":
        return f"{value:.3f}" + ("" if run.get("cost_complete") else "+")
    return str(value)


def table(runs: list[dict]) -> str:
    head = ["run", "valid"] + [label for _, label in COLUMNS]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for run in runs:
        row = [run["run"], "yes" if run.get("valid", True) else "NO"]
        row += [cell(run, key) for key, _ in COLUMNS]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def medians(runs: list[dict], by: str) -> str:
    """Medians per `by` per arm, plus every run of that arm. `by` is 'task' or 'style'."""
    numeric = [(k, label) for k, label in COLUMNS if k not in ("checks_passed", "quality_passed")]
    numeric += [("accept_rate", "accept rate"), ("quality_rate", "held-out rate")]
    groups: dict[tuple[str, str], list[dict]] = {}
    for run in runs:
        if not run.get("valid", True):
            continue  # a void run is printed in the table above and never averaged into anything
        groups.setdefault((run[by], run["arm"]), []).append(run)
        groups.setdefault(("all", run["arm"]), []).append(run)
    head = [by, "arm", "n"] + [label for _, label in numeric]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    keys = [
        k
        for k in (TASKS if by == "task" else ("dense", "tuesday"))
        if any((k, arm) in groups for arm in ARMS)
    ]
    for key in [*keys, "all"]:
        for arm in ARMS:
            group = groups.get((key, arm), [])
            if not group:
                continue
            row = [key, arm, str(len(group))]
            for name, _ in numeric:
                values = [r[name] for r in group if r.get(name) is not None]
                row.append(f"{statistics.median(values):g}" if values else "-")
            lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--json":
        runs = json.loads(Path(argv[2]).read_text())
    elif len(argv) > 1:
        runs = collect(Path(argv[1]).expanduser().resolve())
        out = Path(argv[3]) if len(argv) > 3 and argv[2] == "--out" else HERE / "runs-2026-09-23.json"
        out.write_text(json.dumps(runs, indent=1))
    else:
        print(__doc__)
        return 2
    print(table(runs))
    print()
    print(medians(runs, "task"))
    print()
    print(medians(runs, "style"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
