# For ClinVar KRAS missense SNVs: which checks catch the KRAS4A/4B numbering mismatch against the AFDB
# canonical (4A) model + AlphaMissense per-protein file?
import csv
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
af = {e["uniprotAccession"]: e for e in json.load(open("afdb_P01116.json"))}["P01116"]["sequence"]
am_g = {(int(r["POS"]), r["ALT"]) for r in csv.DictReader(open("am_P01116_hg38.csv"))}
d = json.load(open("kras_esummary.json"))["result"]
n = wrong = wt_catches = 0
for u in d["uids"]:
    m = re.search(r"^(NM_\d+\.\d+)\(KRAS\):\S+ \(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)$", d[u]["title"])
    s = re.match(
        r"NC_000012\.12:(\d+):([ACGT]):([ACGT])$", d[u]["variation_set"][0].get("canonical_spdi", "")
    )
    if not m or not s or m.group(2) not in three or m.group(4) not in three:
        continue
    n += 1
    pos = int(m.group(3))
    mis = (
        int(s.group(1)) + 1,
        s.group(3),
    ) not in am_g  # genomic position not on the 4A transcript the model/AM use
    if mis:
        wrong += 1
        wt_catches += af[pos - 1 : pos] != three[m.group(2)]
print(
    f"SNVs {n}; numbered on a residue that is not the model's residue (by genomic position): {wrong}; wild-type check against the model sequence flags {wt_catches}/{wrong}"  # noqa: E501
)
