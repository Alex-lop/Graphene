# How often does the MANE Select protein differ from the UniProt canonical sequence? (MANE v1.5 vs UniProt
# 2026_03, reviewed human)
import collections
import csv
import gzip

mane = {}  # ENSP(unversioned) -> seq
seq, key = [], None
for line in gzip.open("MANE.GRCh38.v1.5.ensembl_protein.faa.gz", "rt"):
    if line.startswith(">"):
        if key:
            mane[key] = "".join(seq)
        key, seq = line[1:].split()[0].split(".")[0], []
    else:
        seq.append(line.strip())
mane[key] = "".join(seq)
sel = []  # (symbol, ENST, ENSP)
for r in csv.DictReader(gzip.open("MANE.GRCh38.v1.5.summary.txt.gz", "rt"), delimiter="\t"):
    if r["MANE_status"] == "MANE Select":
        sel.append((r["symbol"], r["Ensembl_nuc"].split(".")[0], r["Ensembl_prot"].split(".")[0]))
up_by_enst, up_by_gene = collections.defaultdict(list), collections.defaultdict(list)
for r in csv.DictReader(open("uniprot_human_reviewed.tsv"), delimiter="\t"):
    for x in filter(None, (r["MANE-Select"] or "").replace(" ", "").split(";")):
        up_by_enst[x.split(".")[0]].append(r)
    if r["Gene Names (primary)"]:
        up_by_gene[r["Gene Names (primary)"]].append(r)
c = collections.Counter()
diffs = []
for sym, enst, ensp in sel:
    p = mane.get(ensp)
    if p is None:
        c["mane_protein_missing"] += 1
        continue
    ups = up_by_enst.get(enst)
    how = "xref"
    if not ups:
        ups = up_by_gene.get(sym)
        how = "gene"
    if not ups:
        c["no_uniprot_reviewed"] += 1
        continue
    c["linked_" + how] += 1
    if any(u["Sequence"] == p for u in ups):
        c["identical_" + how] += 1
    else:
        c["differs_" + how] += 1
        u = ups[0]
        diffs.append((sym, enst, u["Entry"], len(p), len(u["Sequence"]), how))
print("MANE Select transcripts:", len(sel))
[print(f"  {k}: {v}") for k, v in sorted(c.items())]
lin = c["linked_xref"] + c["linked_gene"]
dif = c["differs_xref"] + c["differs_gene"]
print(
    f"differ: {dif}/{lin} = {100 * dif / lin:.2f}%  (xref-linked only: {c['differs_xref']}/{c['linked_xref']} = {100 * c['differs_xref'] / c['linked_xref']:.2f}%)"  # noqa: E501
)
with open("mane_uniprot_differs.tsv", "w") as f:
    f.write("symbol\tENST\tuniprot\tmane_len\tuniprot_len\tlinked_by\n")
    for d in diffs:
        f.write("\t".join(map(str, d)) + "\n")
same_len = sum(1 for d in diffs if d[3] == d[4])
print("differing with same length (substitution-level):", same_len)
