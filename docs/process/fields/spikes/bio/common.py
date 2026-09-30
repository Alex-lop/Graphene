"""What the checks share: the slice, the exit codes, and readers for the raw files fetch.py saved.

Exit codes of every check: 0 pass, 1 fail, 2 could not run (missing or unreadable input; a crash must
never read as a verdict), 3 needs a scientist's sign-off.
"""

import csv
import json
import re
import sys
import traceback
from collections.abc import Callable
from functools import cache
from pathlib import Path

PASS, FAIL, ERROR, SIGNOFF = 0, 1, 2, 3
DATA = Path(__file__).resolve().parent / "data"
GENES = {  # gene -> UniProt accession of the canonical entry
    "TP53": "P04637", "KRAS": "P01116", "BRAF": "P15056",
    "PIK3CA": "P42336", "EGFR": "P00533", "PTEN": "P60484",
}  # fmt: skip
AA3 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C", "Gln": "Q", "Glu": "E", "Gly": "G",
    "His": "H", "Ile": "I", "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P", "Ser": "S",
    "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}  # fmt: skip
TITLE = re.compile(r"^(NM_\d+\.\d+)\(([\w-]+)\):c\.\S+ \(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)$")
PATHOGENIC = {"Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic"}
BENIGN = {"Benign", "Likely benign", "Benign/Likely benign"}


def run(main: Callable[[list[str]], int]) -> None:
    """Exit with main's verdict; a crash exits 2 so it cannot pass for a fail (Python's default is 1)."""
    try:
        code = main(sys.argv[1:] or list(GENES))
    except Exception:
        traceback.print_exc()
        code = ERROR
    sys.exit(code)


@cache
def uniprot(acc: str) -> str:
    return "".join((DATA / "uniprot" / f"{acc}.fasta").read_text().splitlines()[1:])


@cache
def refseq(nm: str) -> tuple[str, str] | None:
    """(NP accession, protein sequence) encoded by a RefSeq transcript, if fetched."""
    path = DATA / "refseq" / f"{nm}.fasta"
    if not path.exists():
        return None
    head, *body = path.read_text().splitlines()
    return re.search(r"protein_id=([\w.]+)", head).group(1), "".join(body)


@cache
def alphafold(acc: str) -> dict[int, tuple[str, float]]:
    """Residue number -> (one-letter residue, pLDDT) from the model's CA atoms; pLDDT is the B-factor."""
    residues = {}
    for line in (DATA / "alphafold" / f"{acc}.pdb").read_text().splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            residues[int(line[22:26])] = (AA3[line[17:20].title()], float(line[60:66]))
    return residues


@cache
def alphamissense(acc: str) -> dict[str, tuple[float, str]]:
    """'R175H' -> (am_pathogenicity, am_class), from AlphaFold DB's per-protein AlphaMissense file."""
    with open(DATA / "alphafold" / f"{acc}.am.csv", newline="") as f:
        rows = csv.DictReader(f)
        return {r["protein_variant"]: (float(r["am_pathogenicity"]), r["am_class"]) for r in rows}


@cache
def clinvar(gene: str) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Parsed missense records, and (accession, title, reason) for the records that cannot be checked."""
    parsed, skipped = [], []
    for rec in json.loads((DATA / "clinvar" / f"{gene}.json").read_text()).values():
        title, acc = rec["title"], rec["accession"]
        m = TITLE.match(title)
        if not m:
            skipped.append((acc, title, "title is not NM_(gene):c. (p.XaaNYaa)"))
        elif m[2] != gene:
            skipped.append((acc, title, f"titled on another gene ({m[2]})"))
        elif m[3] not in AA3 or m[5] not in AA3:
            skipped.append((acc, title, "not a substitution between two standard residues"))
        else:
            germ = rec.get("germline_classification") or {}
            onco = rec.get("oncogenicity_classification") or {}
            parsed.append({
                "gene": gene, "accession": acc, "title": title, "transcript": m[1],
                "wt": AA3[m[3]], "pos": int(m[4]), "alt": AA3[m[5]],
                "change": f"{AA3[m[3]]}{m[4]}{AA3[m[5]]}",
                "germline": germ.get("description", ""), "review": germ.get("review_status", ""),
                "traits": "; ".join(t["trait_name"] for t in germ.get("trait_set", [])),
                "oncogenicity": onco.get("description", ""),
            })  # fmt: skip
    return parsed, skipped


def wt_problem(v: dict) -> str | None:
    """None if the stated wild-type residue matches UniProt canonical and the AlphaFold model, else why."""
    acc = GENES[v["gene"]]
    seq, model = uniprot(acc), alphafold(acc)
    pos, wt = v["pos"], v["wt"]
    up = seq[pos - 1] if pos <= len(seq) else None
    af = model.get(pos, (None,))[0]
    if up == wt and af == wt:
        return None
    rs = refseq(v["transcript"])
    ref = rs[1][pos - 1] if rs and pos <= len(rs[1]) else None
    where = f"ClinVar {wt}{pos} on {v['transcript']}" + (f"/{rs[0]}" if rs else "")
    found = f"UniProt {acc} has {up or 'nothing (too short)'}, AlphaFold model has {af or 'nothing'}"
    if up == wt:
        cause = "AlphaFold model sequence differs from current UniProt canonical"
    elif rs and ref == wt and rs[1] != seq:
        cause = "numbered on a RefSeq isoform that differs from UniProt canonical here"
    elif rs and ref != wt:
        cause = "ClinVar's stated residue differs from its own RefSeq protein"
    else:
        cause = "unexplained"
    return f"{where}; {found}: {cause}"


def matched(gene: str) -> list[dict]:
    """The variants that pass the wild-type check: the only ones the later checks may interpret."""
    return [v for v in clinvar(gene)[0] if wt_problem(v) is None]


def reference(v: dict) -> str:
    """ClinVar's germline classification collapsed to P, B, or '' (uncertain, conflicting or unclassified)."""
    return "P" if v["germline"] in PATHOGENIC else "B" if v["germline"] in BENIGN else ""
