# Agreement between AlphaMissense class (developer thresholds; and ClinGen-calibrated PP3/BP4 bands) and
# ClinVar germline classification, KRAS SNVs joined by genomic position.
import collections
import csv
import json
import re

am = {(int(r["POS"]), r["ALT"]): r for r in csv.DictReader(open("am_P01116_hg38.csv"))}
plddt = json.load(open("afdb_P01116_conf.json"))["confidenceScore"]
d = json.load(open("kras_esummary.json"))["result"]
t = collections.Counter()
lowp = 0


def cv(c):
    c = c.lower()
    if c in ("pathogenic", "likely pathogenic", "pathogenic/likely pathogenic"):
        return "P/LP"
    if c in ("benign", "likely benign", "benign/likely benign"):
        return "B/LB"
    return "other(VUS/conflicting/none)"


def clingen(s):  # Bergquist et al. 2025 Table 1 AlphaMissense intervals
    return "PP3" if s >= 0.792 else ("BP4" if s <= 0.169 else "indeterminate")


for u in d["uids"]:
    s = re.match(
        r"NC_000012\.12:(\d+):([ACGT]):([ACGT])$", d[u]["variation_set"][0].get("canonical_spdi", "")
    )
    if not s:
        continue
    r = am.get((int(s.group(1)) + 1, s.group(3)))
    if not r:
        continue
    pos = int(re.match(r"[A-Z](\d+)", r["protein_variant"]).group(1))
    lowp += plddt[pos - 1] < 70
    t[
        (
            cv(d[u]["germline_classification"]["description"]),
            r["am_class"],
            clingen(float(r["am_pathogenicity"])),
        )
    ] += 1
tot = sum(t.values())
print("joined SNVs:", tot, "| site pLDDT<70:", lowp)
for k, v in sorted(t.items()):
    print(v, *k)
