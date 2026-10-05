"""Check 4: agreement between AlphaMissense's class and ClinVar's germline classification is reported,
and every disagreement is flagged for a scientist's sign-off rather than counted as a failure.

Reference: ClinVar germline classification, collapsed to P (pathogenic, likely pathogenic, or both) and B
(benign, likely benign, or both); uncertain, conflicting and other classifications are reported, not compared.
Flagged: P or B where AlphaMissense says the opposite class (discordant) or ambiguous.
ClinVar's somatic oncogenicity axis is reported beside it, not gated on.
Only variants that pass check 1 are considered.
Exit 0 if nothing is flagged, 3 if anything needs sign-off, 2 if it cannot run. It never exits 1.

Usage: python3 check_agreement.py [GENE ...]   (default: all six genes)
"""

from collections import Counter

from common import BENIGN, GENES, PASS, SIGNOFF, alphafold, alphamissense, matched, reference, run

ONCO = {"Oncogenic": "P", "Likely oncogenic": "P", **dict.fromkeys(BENIGN, "B")}  # uncertain: not compared
AGREE = {("P", "LPath"), ("B", "LBen")}


def main(genes: list[str]) -> int:
    flagged = []
    print(
        "gene\tsites\tP\tB\tunclassified\tagree\tdiscordant\tam_ambiguous\tflagged\tonco_agree/onco_classified"
    )
    for gene in genes:
        acc = GENES[gene]
        rows = []
        for v in matched(gene):
            score, cls = alphamissense(acc)[v["change"]]
            rows.append((v, reference(v), score, cls))
        c = Counter(ref for _, ref, _, _ in rows)
        agree = [r for r in rows if (r[1], r[3]) in AGREE]
        amb = [r for r in rows if r[1] and r[3] == "Amb"]
        disc = [r for r in rows if r[1] and r[3] != "Amb" and (r[1], r[3]) not in AGREE]
        onco = [(ONCO[v["oncogenicity"]], cls) for v, _, _, cls in rows if v["oncogenicity"] in ONCO]
        onco_agree = sum(pair in AGREE for pair in onco)
        print(f"{gene}\t{len(rows)}\t{c['P']}\t{c['B']}\t{c['']}\t{len(agree)}\t{len(disc)}\t{len(amb)}\t"
              f"{len(disc) + len(amb)}\t{onco_agree}/{len(onco)}")  # fmt: skip
        flagged += [("discordant", *r) for r in disc] + [("am-ambiguous", *r) for r in amb]
    print("\nFlagged for sign-off (kind, variant, ClinVar, review status, AlphaMissense, pLDDT):")
    for kind, v, _, score, cls in flagged:
        plddt = alphafold(GENES[v["gene"]])[v["pos"]][1]
        print(f"  {kind}\t{v['gene']} {v['change']}\t{v['accession']}\t{v['germline']}\t{v['review']}\t"
              f"{cls} {score:.3f}\tpLDDT {plddt:.1f}")  # fmt: skip
    return SIGNOFF if flagged else PASS


if __name__ == "__main__":
    run(main)
