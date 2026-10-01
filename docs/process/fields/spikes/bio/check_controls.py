"""Check 2: known controls come out as the method says they should.

Method: AlphaMissense's class for the substitution, from AlphaFold DB's per-protein file. Thresholds (Cheng et
al. 2023; Zenodo record 10813168): likely benign below 0.34, likely pathogenic above 0.564, ambiguous between.
A control counts only if its own evidence is in the data, independent of the method:
- positive: a cancerhotspots.org single-residue hotspot allele seen in at least MIN_TUMORS tumours;
- negative: ClinVar germline classification benign or likely benign.
Exit 0 if every control's evidence holds and its class is the expected one, 1 otherwise, 2 if it cannot run.
Also reports (without gating) the class of every hotspot allele in the genes seen in >= SWEEP_TUMORS tumours.

Usage: python3 check_controls.py [GENE ...]   (default: all six genes)
"""

import json
import re
from collections import Counter

from common import DATA, FAIL, GENES, PASS, alphamissense, clinvar, reference, run, uniprot

LBEN, LPATH = 0.34, 0.564
MIN_TUMORS, SWEEP_TUMORS = 20, 5
POSITIVE = [("KRAS", "G12D"), ("BRAF", "V600E"), ("TP53", "R175H"), ("TP53", "R248Q"), ("TP53", "R273H"),
            ("PIK3CA", "H1047R"), ("EGFR", "L858R"), ("PTEN", "R130Q")]  # fmt: skip
NEGATIVE = [("TP53", "P72R"), ("PIK3CA", "I391M"), ("EGFR", "R521K")]


def expected_class(score: float) -> str:
    return "LBen" if score < LBEN else "LPath" if score > LPATH else "Amb"


def consistent(score: float, cls: str) -> bool:
    """Scores are published rounded to 4 decimals and classed before rounding, so a score shown as exactly
    0.34 or 0.564 may carry the class of either side (the first version of this check missed that)."""
    return cls in {expected_class(score - 5e-5), expected_class(score + 5e-5)}


def hotspot_alleles(genes: list[str]) -> dict[tuple[str, str], int]:
    """(gene, 'H1047R') -> number of tumours with that allele, for single-residue missense hotspots."""
    alleles = {}
    for h in json.loads((DATA / "hotspots.json").read_text()):
        if h["hugoSymbol"] in genes and re.fullmatch(r"[A-Z]\d+", h["residue"]):
            for alt, n in h["variantAminoAcid"].items():
                if re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]", alt) and alt != h["residue"][0]:
                    alleles[(h["hugoSymbol"], h["residue"] + alt)] = n
    return alleles


def main(genes: list[str]) -> int:
    ok = True
    for gene in genes:  # the method is what we say it is: every class in the file follows the thresholds
        bad = [(k, s, c) for k, (s, c) in alphamissense(GENES[gene]).items() if not consistent(s, c)]
        rows = len(alphamissense(GENES[gene]))
        print(f"{gene}: {rows} AlphaMissense rows, {len(bad)} off-threshold {bad[:3]}")
        ok &= not bad

    hotspots = hotspot_alleles(genes)
    records = {(v["gene"], v["change"]): v for g in genes for v in clinvar(g)[0]}
    print("\nkind\tgene\tvariant\tevidence\tam_score\tam_class\texpected\tverdict")
    for kind, controls, want in (("positive", POSITIVE, "LPath"), ("negative", NEGATIVE, "LBen")):
        for gene, change in controls:
            if gene not in genes:
                continue
            wt, pos = change[0], int(change[1:-1])
            cv = records.get((gene, change))
            if kind == "positive":
                n = hotspots.get((gene, change), 0)
                evidence, holds = f"{n} tumours (cancerhotspots)", n >= MIN_TUMORS
            else:
                evidence = f"ClinVar {cv['accession']} {cv['germline']}" if cv else "not in ClinVar slice"
                holds = bool(cv) and reference(cv) == "B"
            if uniprot(GENES[gene])[pos - 1 : pos] != wt:
                score, cls, verdict = float("nan"), "-", "FAIL: wild type does not match UniProt"
            else:
                score, cls = alphamissense(GENES[gene])[change]
                verdict = "FAIL: evidence missing" if not holds else "pass" if cls == want else "FAIL"
            ok &= verdict == "pass"
            print(f"{kind}\t{gene}\t{change}\t{evidence}\t{score:.3f}\t{cls}\t{want}\t{verdict}")

    print(f"\nSweep (reported, not gating): hotspot alleles seen in >= {SWEEP_TUMORS} tumours")
    sweep = Counter()
    for (gene, change), n in sorted(hotspots.items()):
        if n < SWEEP_TUMORS:
            continue
        pos = int(change[1:-1])
        if uniprot(GENES[gene])[pos - 1 : pos] != change[0]:
            sweep[gene, "wt-mismatch"] += 1
            print(f"  {gene} {change} ({n} tumours): wild type does not match UniProt canonical")
            continue
        score, cls = alphamissense(GENES[gene])[change]
        sweep[gene, cls] += 1
        if cls != "LPath":
            print(f"  {gene} {change} ({n} tumours): {cls} {score:.3f}")
    for gene in genes:
        row = {c: sweep[gene, c] for c in ("LPath", "Amb", "LBen", "wt-mismatch")}
        print(f"  {gene}\t{row}")
    total = {c: sum(sweep[g, c] for g in genes) for c in ("LPath", "Amb", "LBen", "wt-mismatch")}
    print(f"  total\t{total}")
    return PASS if ok else FAIL


if __name__ == "__main__":
    run(main)
