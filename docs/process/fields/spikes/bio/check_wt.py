"""Check 1: each variant's stated wild-type residue is the residue at that position in UniProt canonical AND
in the AlphaFold model. Exit 0 if every checkable variant matches, 1 if any does not, 2 if it cannot run.

Usage: python3 check_wt.py [GENE ...]   (default: all six genes)
"""

from collections import Counter

from common import FAIL, PASS, clinvar, run, wt_problem


def main(genes: list[str]) -> int:
    failed = 0
    print("gene\tchecked\tmismatch\tfraction\tnot_checkable")
    details = []
    for gene in genes:
        parsed, skipped = clinvar(gene)
        problems = [(v, p) for v in parsed if (p := wt_problem(v))]
        failed += len(problems)
        frac = len(problems) / max(len(parsed), 1)
        print(f"{gene}\t{len(parsed)}\t{len(problems)}\t{frac:.3f}\t{len(skipped)}")
        details += [f"MISMATCH {v['accession']} {v['title']} :: {p}" for v, p in problems]
        details += [f"NOT CHECKABLE {acc} {title} :: {why}" for acc, title, why in skipped]
        causes = Counter(p.rsplit(": ", 1)[1] for _, p in problems)
        causes.update(f"not checkable: {why.split(' (')[0]}" for *_, why in skipped)
        details += [f"  {gene} cause x{n}: {c}" for c, n in causes.most_common()]
    print("\n".join(details))
    return FAIL if failed else PASS


if __name__ == "__main__":
    run(main)
