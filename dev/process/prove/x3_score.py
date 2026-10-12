#!/usr/bin/env python3
"""Score X3's readers against truth.json, by script, for the eight factual questions; print the two others.

    x3_score.py OUT     (x3.sh's directory: <run>/truth.json, fix.json, armA.json, armB.json)

Exact for ids, shas (7-character prefix) and counts, within one cent for dollars, a set match for the files.
Questions 2 (why) and 8 (what waits) are not scored: the reader's words are printed for a person to read.
"""

import json
import re
import sys
from pathlib import Path

FACTUAL = ("q1", "q3", "q4", "q5", "q6", "q7", "q9", "q10")


def answers(path: Path) -> dict:
    if not path.exists() or not path.stat().st_size:
        return {}
    try:
        d = json.loads(path.read_text())
    except ValueError:
        return {}
    return d.get("structured_output") or {}


def truth_of(d: Path) -> dict:
    t = json.loads((d / "truth.json").read_text())
    fix = json.loads((d / "fix.json").read_text()) if (d / "fix.json").exists() else {}
    base_pass = [
        re.match(r"([a-z0-9-]+): its check \(`.*`\) passes before any work", line)
        for line in t.get("red_first", [])
    ]
    bills = t.get("bills") or {}
    return {
        "q1": set(fix.get("files") or []),
        "q3_count": t.get("denials"),
        "q3_examples": {c for a in t.get("attempts", []) for c in a.get("denied", [])},
        "q4": next((m.group(1) for m in base_pass if m), None),
        "q5_planner": bills.get("the planner's bill"),
        "q5_total": t.get("dollars_total"),
        "q6": (t.get("width") or {}).get("peak"),
        "q7_came_back": (t.get("came_back") or [{}])[0].get("node") if t.get("came_back") else None,
        "q7_reopened": (t.get("reopened") or [{}])[0].get("node") if t.get("reopened") else None,
        "q9": (fix.get("sha") or "")[:7] or None,
        "q10": len(t.get("added_after_acceptance") or []),
    }


def near(a, b, tol=0.011):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def score(a: dict, t: dict) -> dict:
    s = {}
    s["q1"] = set(a.get("q1_files_changed_by_fix") or []) == t["q1"] and bool(t["q1"])
    s["q3"] = a.get("q3_refused_commands_count") == t["q3_count"] and (
        t["q3_count"] == 0
        or any((a.get("q3_refused_command_example") or "").strip()[:40] in c for c in t["q3_examples"])
    )
    s["q4"] = (a.get("q4_check_passed_at_base_leaf") or None) == t["q4"]
    s["q5"] = near(a.get("q5_planner_dollars"), t["q5_planner"]) and near(
        a.get("q5_total_dollars"), t["q5_total"]
    )
    s["q6"] = a.get("q6_max_leaves_at_once") == t["q6"]
    s["q7"] = (a.get("q7_came_back_leaf") or None) == t["q7_came_back"] and (
        a.get("q7_reopened_leaf") or None
    ) == t["q7_reopened"]
    s["q9"] = bool(t["q9"]) and (a.get("q9_fix_merge_sha") or "")[:7] == t["q9"]
    s["q10"] = a.get("q10_leaves_added_after_accept") == t["q10"]
    return s


def main(out: Path) -> int:
    print(f"# X3 · ten questions, the record against git ({out})\n")
    print(
        "| run | arm | score of 8 | "
        + " | ".join(FACTUAL)
        + " | q2 why (the reader's words) | q8 waits (the reader's words) |"
    )
    print("|---|---|---|" + "---|" * len(FACTUAL) + "---|---|")
    totals = {"A": [], "B": []}
    for d in sorted(p for p in out.iterdir() if p.is_dir() and (p / "truth.json").exists()):
        t = truth_of(d)
        for arm in ("A", "B"):
            a = answers(d / f"arm{arm}.json")
            if not a:
                print(f"| {d.name} | {arm} | no answer | " + " | ".join("–" for _ in FACTUAL) + " | | |")
                continue
            s = score(a, t)
            n = sum(s.values())
            totals[arm].append(n)
            marks = " | ".join("✓" if s[q] else "✗" for q in FACTUAL)
            q2 = (a.get("q2_why_in_agents_words") or "null").replace("|", "/").replace("\n", " ")[:160]
            q8 = (a.get("q8_waits_on_person") or "null").replace("|", "/").replace("\n", " ")[:120]
            print(f"| {d.name} | {arm} | {n} | {marks} | {q2} | {q8} |")
    for arm in ("A", "B"):
        xs = totals[arm]
        if xs:
            xs.sort()
            print(f"\narm {arm}: median {xs[len(xs) // 2]} of 8 over {len(xs)} readers ({xs})")
    print(
        "\nTruth per run is in <run>/truth.json and fix.json; the readers' full answers in armA.json "
        "and armB.json."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
