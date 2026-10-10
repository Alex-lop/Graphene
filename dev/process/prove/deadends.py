#!/usr/bin/env python3
"""Refusals and dead ends in what a person (or a stand-in) saw, counted by regex, with no model.

    deadends.py --walks OUT          every OUT/walk-<i>.txt; minutes to the first merge from its repo;
                                     writes OUT/walks.json and prints a table
    deadends.py FILE...              the counts for each file (a stranger's stream), as JSON

The patterns are the lines Graphene prints when it stops someone: a refusal (plan.py), a person-only
act (plan.py:1046), a hook error, nothing to run / no proposal / could not read the proposal (run.py,
ask.py), an init that chose nothing (cli.py:308), an empty plan (plan_cli.py)."""
import json
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    # not the record's "0 writes refused; 0 `done` refused" counts, nor node show's "is refused, and blocks"
    "refused": re.compile(r"(?<!0 writes )(?<!0 `done` )\brefused\b(?!, and blocks)", re.I),
    "is the person's": re.compile(r"is the person's"),
    "hook error": re.compile(r"hook error", re.I),
    "nothing to run": re.compile(r"nothing to run"),
    "no proposal": re.compile(r"no proposal"),
    "could not read": re.compile(r"could not read the proposal"),
    "not chosen": re.compile(r"not chosen"),
    "nothing is planned": re.compile(r"nothing is planned"),
    "cannot start": re.compile(r"cannot start"),
    "came back": re.compile(r"came back|handed back"),
    "exit!=0": re.compile(r"^exit=\d+", re.M),
}


def counts(text: str) -> dict:
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items()}


def walk(out: Path, path: Path) -> dict:
    i = path.stem.split("-")[-1]
    text = path.read_text(encoding="utf-8", errors="replace")
    repo = out / "runs" / f"report-sealed-walk-{i}" / "repo"
    t0_file = out / f"walk-{i}.t0"
    merges = subprocess.run(["git", "-C", str(repo), "log", "--merges", "--reverse", "--format=%ct %s"],
                            capture_output=True, text=True).stdout.splitlines() if repo.exists() else []
    minutes = None
    if merges and t0_file.exists():
        minutes = round((int(merges[0].split()[0]) - int(t0_file.read_text().strip())) / 60, 1)
    return {"walk": path.name, "landed": len(merges), "minutes_to_first_merge": minutes,
            "dead_ends": counts(text), "dead_end_total": sum(counts(text).values())}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--walks"]:
        out = Path(argv[1])
        rows = [walk(out, p) for p in sorted(out.glob("walk-*.txt"))]
        (out / "walks.json").write_text(json.dumps(rows, indent=2))
        names = list(PATTERNS)
        print(f"# walks in {out.name}\n")
        print("| walk | landed | min to 1st merge | " + " | ".join(names) + " |")
        print("|---|---|---|" + "---|" * len(names))
        for r in rows:
            print(f"| {r['walk']} | {r['landed']} | {r['minutes_to_first_merge']} | "
                  + " | ".join(str(r["dead_ends"][n]) for n in names) + " |")
        return 0
    print(json.dumps({p: counts(Path(p).read_text(encoding="utf-8", errors="replace")) for p in argv}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
