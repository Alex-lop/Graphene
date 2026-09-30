"""The checks' own check: each must say no when it should, and a crash must never read as a verdict.
Needs data/ (run fetch.py first). Exit 0 if every assertion holds, 1 otherwise.
"""

import subprocess
import sys
from pathlib import Path

from check_controls import consistent
from common import ERROR, wt_problem


def variant(gene: str, transcript: str, change: str) -> dict:
    wt, pos, alt = change[0], int(change[1:-1]), change[-1]
    return {"gene": gene, "transcript": transcript, "wt": wt, "pos": pos, "alt": alt}


assert wt_problem(variant("TP53", "NM_000546.6", "R175H")) is None
assert "differs from its own RefSeq" in wt_problem(variant("TP53", "NM_000546.6", "K175H"))
assert "RefSeq isoform" in wt_problem(variant("KRAS", "NM_004985.5", "D153V"))  # K-Ras4B vs 4A canonical
assert "too short" in wt_problem(variant("BRAF", "NM_001374258.1", "K807T"))  # 807-aa isoform; canonical 766
assert consistent(0.34, "LBen") and consistent(0.34, "Amb") and not consistent(0.34, "LPath")
assert consistent(0.9, "LPath") and not consistent(0.9, "LBen") and not consistent(0.5, "LPath")
here = Path(__file__).resolve().parent
for check in ("check_wt.py", "check_controls.py", "check_plddt.py", "check_agreement.py"):
    code = subprocess.run([sys.executable, here / check, "NOSUCHGENE"], capture_output=True).returncode
    assert code == ERROR, f"{check} exited {code} on a crash, expected {ERROR}"
print("selftest: all assertions hold")
