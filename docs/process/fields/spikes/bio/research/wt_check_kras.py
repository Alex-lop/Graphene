# Check: each ClinVar KRAS missense variant's stated wild-type residue matches the residue at that position
# in (a) the MANE Select protein and (b) the AlphaFold DB canonical model sequence (UniProt P01116 canonical).
import gzip
import json
import re

three = dict(
    Ala="A",
    Arg="R",
    Asn="N",
    Asp="D",
    Cys="C",
    Gln="Q",
    Glu="E",
    Gly="G",
    His="H",
    Ile="I",
    Leu="L",
    Lys="K",
    Met="M",
    Phe="F",
    Pro="P",
    Ser="S",
    Thr="T",
    Trp="W",
    Tyr="Y",
    Val="V",
)
afdb = {e["uniprotAccession"]: e for e in json.load(open("afdb_P01116.json"))}
af = afdb["P01116"]["sequence"]
mane = None
key = None
seq = []
for line in gzip.open("MANE.GRCh38.v1.5.ensembl_protein.faa.gz", "rt"):
    if line.startswith(">"):
        if key == "ENST00000311936":
            break
        key = re.search(r"transcript:(\S+)", line).group(1).split(".")[0]
        seq = []
    else:
        seq.append(line.strip())
mane = "".join(seq)
plddt = json.load(open("afdb_P01116_conf.json"))["confidenceScore"]
print(
    "AFDB model",
    afdb["P01116"]["modelEntityId"],
    "len",
    len(af),
    "| MANE len",
    len(mane),
    "| isoforms in AFDB:",
    sorted(afdb),
)
d = json.load(open("kras_esummary.json"))["result"]
rows = []
for u in d["uids"]:
    t = d[u]["title"]
    m = re.search(r"^(NM_\d+\.\d+)\(KRAS\):\S+ \(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)$", t)
    if not m:
        continue
    tx, wt, pos, alt = m.group(1), three.get(m.group(2)), int(m.group(3)), m.group(4)
    if wt is None or alt not in three:
        continue
    rows.append(
        (
            u,
            tx,
            wt,
            pos,
            mane[pos - 1 : pos] == wt,
            af[pos - 1 : pos] == wt,
            plddt[pos - 1] if pos <= len(plddt) else None,
            d[u]["germline_classification"]["description"],
        )
    )
n = len(rows)
print("parsed missense rows:", n, "transcripts:", sorted({r[1] for r in rows}))
print("WT matches MANE protein:", sum(r[4] for r in rows), "/", n)
print("WT matches AFDB canonical model:", sum(r[5] for r in rows), "/", n)
bad = [r for r in rows if r[4] and not r[5]]
print("match MANE but NOT AFDB canonical:", len(bad), "positions", sorted({r[3] for r in bad}))
print("pLDDT<70 at site (AFDB canonical):", sum(1 for r in rows if r[6] is not None and r[6] < 70), "/", n)
first_diff = next(i for i, (a, b) in enumerate(zip(mane, af, strict=False)) if a != b) + 1
print("first differing residue MANE vs AFDB canonical:", first_diff)
