#!/usr/bin/env python3
"""The X2 table from an OUT directory's runs: x2_table.py OUT

(reads OUT/runs/*/score.json, prints markdown)"""

import json
import sys
from pathlib import Path

COLS = (
    "accept",
    "held_out",
    "six_unchanged",
    "seconds",
    "dollars_total",
    "denials",
    "turns",
    "handed_back",
    "fix_landed_in_owner",
    "why_recorded",
)


def main(out: Path) -> int:
    rows = []
    for run in sorted((out / "runs").iterdir() if (out / "runs").exists() else []):
        path = run / "score.json"
        if path.exists():
            try:
                rows.append((run.name, json.loads(path.read_text(encoding="utf-8"))))
            except ValueError:
                rows.append((run.name, {}))
    print(f"# X2 · {out.name}: {len(rows)} scored run{'s' * (len(rows) != 1)}\n")
    print("| run | " + " | ".join(COLS) + " | outside intent |")
    print("|---|" + "---|" * (len(COLS) + 1))
    for name, s in rows:
        outside = next((v for k, v in (s.get("tally") or {}).items() if "outside" in k), "?")
        cells = [str(s.get(c, "?")) for c in COLS]
        print(f"| {name} | " + " | ".join(cells) + f" | {outside} |")
    for name, s in rows:
        if s.get("red_first"):
            print(f"\n{name} red first:")
            print("\n".join(f"  {line}" for line in s["red_first"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
