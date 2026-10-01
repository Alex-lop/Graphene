# Join ClinVar KRAS missense SNVs to AlphaMissense (AFDB per-protein hg38 file) two ways:
# (1) by protein-change string, as a pipeline keyed on "G12D" would; (2) by GRCh38 position + alt allele
# (ground truth).
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
am_by_str, am_by_g = {}, {}
for r in csv.DictReader(open("am_P01116_hg38.csv")):
    am_by_str[r["protein_variant"]] = r
    am_by_g[(int(r["POS"]), r["ALT"])] = r
d = json.load(open("kras_esummary.json"))["result"]
tot = agree = str_missing = wrong_join = no_g = 0
examples = []
for u in d["uids"]:
    t = d[u]["title"]
    m = re.search(r"^(NM_\d+\.\d+)\(KRAS\):\S+ \(p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})\)$", t)
    if not m or m.group(2) not in three or m.group(4) not in three:
        continue
    spdi = d[u]["variation_set"][0].get("canonical_spdi", "")
    s = re.match(r"NC_000012\.12:(\d+):([ACGT]):([ACGT])$", spdi)
    if not s:
        continue  # SNVs only
    tot += 1
    pv = three[m.group(2)] + m.group(3) + three[m.group(4)]
    g = am_by_g.get((int(s.group(1)) + 1, s.group(3)))  # SPDI is 0-based
    st = am_by_str.get(pv)
    if g is None:
        no_g += 1
        continue
    if st is None:
        str_missing += 1
        examples.append(
            (
                m.group(1),
                pv,
                "string join: no row",
                "genomic join:",
                g["protein_variant"],
                g["am_pathogenicity"],
            )
        )
    elif st is g or st["protein_variant"] == g["protein_variant"]:
        agree += 1
    else:
        wrong_join += 1
        examples.append(
            (
                m.group(1),
                pv,
                "string join ->",
                st["am_pathogenicity"],
                st["am_class"],
                "genomic join ->",
                g["protein_variant"],
                g["am_pathogenicity"],
                g["am_class"],
            )
        )
print(f"ClinVar KRAS missense SNVs: {tot}; not in AM hg38 file by position: {no_g}")
print(
    f"string join agrees with genomic join: {agree}; string join finds no row: {str_missing}; string join returns a DIFFERENT variant's score: {wrong_join}"  # noqa: E501
)
for e in examples:
    print("  ", *e)
