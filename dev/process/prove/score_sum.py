#!/usr/bin/env python3
"""One run's score, from the scorers' files beside it: score_sum.py REPO BASE OUTDIR  (prints score.json)

accept.json and quality.json are _check.report's objects (passed, failed, details); tally.json is
tally.py's; the six files are compared to the base commit with git; truth.json, when there is one,
gives the hand-backs, denials and dollars."""
import json
import subprocess
import sys
from pathlib import Path

SIX = ("vendor/tinydec.py", "normalize/money.py", "legacy/priceimport.py", "tests/test_contract.py",
       "scripts/nightly.sh", "ingest/csvfeed.py")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(repo: Path, base: str, out: Path) -> int:
    accept, quality, tally, truth = (load(out / f"{n}.json") for n in ("accept", "quality", "tally", "truth"))
    unchanged = {}
    for rel in SIX:
        done = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", base, "HEAD", "--", rel], capture_output=True)
        exists = (repo / rel).exists()
        unchanged[rel] = done.returncode == 0 and exists
    picked = {k: v for k, v in tally.items() if isinstance(v, (int, float, str, list)) and any(
        w in k for w in ("outside", "files", "rework", "churn", "cost", "dollars", "lines", "acts", "typed"))}
    score = {
        "accept": f"{accept.get('passed', '?')} of {accept.get('passed', 0) + accept.get('failed', 0) or '?'}",
        "accept_failed": [d["check"] for d in accept.get("details", []) if not d.get("ok")],
        "held_out": f"{quality.get('passed', '?')} of {quality.get('passed', 0) + quality.get('failed', 0) or '?'}",
        "six_unchanged": sum(unchanged.values()), "six": unchanged,
        "tally": picked,
        "seconds": truth.get("seconds"), "dollars_total": truth.get("dollars_total"),
        "denials": truth.get("denials"), "turns": truth.get("turns"),
        "handed_back": len(truth.get("handed_back", [])),
        "red_first": truth.get("red_first"),
        "fix_landed_in_owner": truth.get("fix_landed_in_owner"), "why_recorded": truth.get("why_recorded"),
    }
    print(json.dumps(score, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])))
