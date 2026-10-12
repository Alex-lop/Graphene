#!/usr/bin/env python3
"""Score X1's asks, with no model: x1_score.py OUT   (reads OUT/runs/*/, writes OUT/x1.json, prints x1.md)

Per ask: by ask (ask.rc == 0 and a `proposed ` line), by first answer (by ask and no "asking the
planner (…) again" line), lost (ask.rc != 0), the first refusal's class, `repaired:` lines, checks two
leaves share (plan.txt), checks by runner, seconds, and the planner's dollars (record.txt's "the
planner's bill"). Per task and in all, with 95% Wilson intervals.

The first refusal is the first line holding "could not read the proposal:" in ask.out (attempt 1's,
said as it happened, ask.py:487) or, when there was none, the refusal in ask.err's last line. Its
class, by the strings Graphene prints (src/graphene_map at 907a7d0):

  class             regex                                                  printed by
  one-writer        both write .* A path has one leaf                      plan.py:1296
  board-as-node     '(question|risk|assume|note|leave out):.*' is a new leaf with no scope and no check
                                                                           plan_text.py:757
  check-runs-later  its check runs .*, which .* writes after it            plan.py:1297
  then-about        \\b(then|about): .*(is not read|not a node|names no node|not read)
                    (plan_text.py:260, board then: lines)
  option-risk       option: is a question's                                board.py:284
  no-answer         no proposal \\(exit                                     ask.py:456 (nothing printed)
  other             any other "could not read the proposal:" line
"""

import json
import re
import statistics
import sys
from pathlib import Path

CLASSES = [
    ("one-writer", re.compile(r"both write .* A path has one leaf")),
    (
        "board-as-node",
        re.compile(r"'(question|risk|assume|note|leave out):[^']*' is a new leaf with no scope and no check"),
    ),
    ("check-runs-later", re.compile(r"its check runs .*, which .* writes after it")),
    ("then-about", re.compile(r"\b(then|about): .*(is not read|not a node|names no node|not read)")),
    ("option-risk", re.compile(r"option: is a question's")),
    ("no-answer", re.compile(r"no proposal \(exit")),
]
RUNNERS = [
    ("python3 -m pytest", re.compile(r"python3? -m pytest|^pytest\b")),
    ("uv run", re.compile(r"^uv run\b")),
    ("python3 -m unittest", re.compile(r"python3? -m unittest")),
    ("other", re.compile(r".")),
]


def wilson(x: int, n: int) -> str:
    if not n:
        return "n=0"
    import math

    z, p = 1.96, x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{x}/{n} = {p:.2f} [{max(0.0, c - h):.2f}, {min(1.0, c + h):.2f}]"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def classify(refusal: str) -> str:
    for name, rx in CLASSES:
        if rx.search(refusal):
            return name
    return "other"


def one(run: Path) -> dict:
    out, err = read(run / "ask.out"), read(run / "ask.err")
    rc = int(read(run / "ask.rc").strip() or -1)
    secs = float(read(run / "ask.seconds").strip() or 0)
    by_ask = rc == 0 and bool(re.search(r"^proposed ", out, re.M))
    again = bool(re.search(r"^asking the planner \([^)]*\) again", out, re.M))
    refusal = next(
        (line for line in (out + "\n" + err).splitlines() if "could not read the proposal:" in line), ""
    )
    if not refusal and rc != 0:
        tail = [line for line in err.splitlines() if line.strip()]
        refusal = tail[-1] if tail else "(nothing on stderr)"
    plan = read(run / "plan.txt")
    checks = [c.strip() for c in re.findall(r"^\s*check: (.+)$", plan, re.M)]
    shared = sum(1 for c in set(checks) if checks.count(c) >= 2)
    runners = {}
    for check in checks:
        name = next(n for n, rx in RUNNERS if rx.search(check))
        runners[name] = runners.get(name, 0) + 1
    bill = re.search(r"the planner's bill: \$([0-9.]+)", read(run / "record.txt"))
    return {
        "run": run.name,
        "task": run.name.split("-")[0],
        "rc": rc,
        "seconds": secs,
        "by_ask": by_ask,
        "by_first_answer": by_ask and not again,
        "again": again,
        "lost": rc != 0,
        "first_refusal": refusal[:300],
        "class": classify(refusal) if refusal else None,
        "repaired": len(re.findall(r"^repaired:", out, re.M)),
        "leaves": len(checks),
        "shared_checks": shared,
        "runners": runners,
        "dollars": float(bill.group(1)) if bill else None,
    }


def table(rows: list[dict], name: str) -> tuple[dict, list[str]]:
    n = len(rows)
    by_ask = sum(r["by_ask"] for r in rows)
    first = sum(r["by_first_answer"] for r in rows)
    lost = sum(r["lost"] for r in rows)
    classes: dict[str, int] = {}
    for r in rows:
        if r["class"]:
            classes[r["class"]] = classes.get(r["class"], 0) + 1
    runners: dict[str, int] = {}
    for r in rows:
        for k, v in r["runners"].items():
            runners[k] = runners.get(k, 0) + v
    secs = [r["seconds"] for r in rows if r["seconds"] is not None]
    dollars = [r["dollars"] for r in rows if r["dollars"] is not None]
    summary = {
        "n": n,
        "by_ask": by_ask,
        "by_first_answer": first,
        "lost": lost,
        "by_ask_wilson": wilson(by_ask, n),
        "by_first_answer_wilson": wilson(first, n),
        "lost_wilson": wilson(lost, n),
        "first_refusal_classes": classes,
        "repaired_lines": sum(r["repaired"] for r in rows),
        "asks_with_a_shared_check": sum(1 for r in rows if r["shared_checks"]),
        "checks_by_runner": runners,
        "median_seconds": statistics.median(secs) if secs else None,
        "median_dollars": round(statistics.median(dollars), 4) if dollars else None,
    }
    lines = [
        f"### {name} (n = {n})",
        "",
        f"- proposals by ask: {summary['by_ask_wilson']}",
        f"- proposals by first answer: {summary['by_first_answer_wilson']}",
        f"- asks lost: {summary['lost_wilson']}",
        f"- first refusal classes: {classes or 'none'}",
        f"- `repaired:` lines: {summary['repaired_lines']}; asks with a check two leaves share: "
        f"{summary['asks_with_a_shared_check']}; checks by runner: {runners or 'none'}",
        f"- median seconds: {summary['median_seconds']}; median planner dollars: {summary['median_dollars']}",
        "",
    ]
    return summary, lines


def main(out: Path) -> int:
    runs = sorted(p for p in (out / "runs").iterdir() if p.is_dir() and "-x1-" in p.name)
    rows = [one(r) for r in runs]
    report: dict = {"runs": rows, "summary": {}}
    lines = [f"# X1 · the first ask ({out})", ""]
    for task in sorted({r["task"] for r in rows}):
        report["summary"][task], said = table([r for r in rows if r["task"] == task], task)
        lines += said
    report["summary"]["all"], said = table(rows, "all")
    lines += said
    lines += ["### every refusal, first line", ""]
    lines += [f"- {r['run']}: [{r['class']}] {r['first_refusal']}" for r in rows if r["first_refusal"]]
    (out / "x1.json").write_text(json.dumps(report, indent=2))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
