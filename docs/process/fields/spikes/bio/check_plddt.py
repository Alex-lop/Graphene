"""Check 3: the AlphaFold model is confident enough at each variant's site to interpret it structurally.

Threshold: pLDDT >= 70. AlphaFold DB's bands are >= 90 very high, 70-90 confident ("usually corresponds to a
correct backbone prediction"), 50-70 low, < 50 very low (Varadi et al. 2022; EMBL-EBI AlphaFold course).
Only variants that pass check 1 are considered: a site whose numbering is wrong has no meaningful pLDDT.
Exit 0 if every site is at or above the threshold, 1 if any is below, 2 if it cannot run.

Usage: python3 check_plddt.py [GENE ...]   (default: all six genes)
"""

from itertools import groupby

from common import FAIL, GENES, PASS, alphafold, matched, run

THRESHOLD = 70.0


def low_segments(acc: str) -> list[tuple[int, int]]:
    """Maximal runs of residues below the threshold, to say where the failing sites sit."""
    model = alphafold(acc)
    runs = [list(g) for low, g in groupby(sorted(model), key=lambda p: model[p][1] < THRESHOLD) if low]
    return [(r[0], r[-1]) for r in runs]


def main(genes: list[str]) -> int:
    below_total = 0
    print("gene\tsites\tbelow70\tfraction\t>=90\t70-90\t50-70\t<50")
    details = []
    for gene in genes:
        acc = GENES[gene]
        model = alphafold(acc)
        scores = [(v, model[v["pos"]][1]) for v in matched(gene)]
        below = [(v, s) for v, s in scores if s < THRESHOLD]
        below_total += len(below)
        bands = [sum(lo <= s < hi for _, s in scores) for lo, hi in ((90, 101), (70, 90), (50, 70), (0, 50))]
        frac = len(below) / max(len(scores), 1)
        print(f"{gene}\t{len(scores)}\t{len(below)}\t{frac:.3f}\t" + "\t".join(map(str, bands)))
        for a, b in low_segments(acc):
            n = sum(a <= v["pos"] <= b for v, _ in below)
            if n:
                details.append(f"  {gene} residues {a}-{b} (pLDDT < 70): {n} variant sites")
    print("\n".join(details))
    return FAIL if below_total else PASS


if __name__ == "__main__":
    run(main)
