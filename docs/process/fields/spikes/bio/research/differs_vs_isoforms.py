# For MANE Select proteins that differ from the UniProt canonical: does one of the entry's Swiss-Prot
# isoforms match exactly?
import collections
import csv
import gzip

iso = collections.defaultdict(dict)  # accession -> {isoform_id: seq}
key, seq = None, []


def flush():
    if key and key.startswith("sp|"):
        iid = key.split("|")[1]
        iso[iid.split("-")[0]][iid] = "".join(seq)


for line in gzip.open("UP000005640_9606_additional.fasta.gz", "rt"):
    if line.startswith(">"):
        flush()
        key, seq = line[1:].split()[0], []
    else:
        seq.append(line.strip())
flush()
mane = {}
key, seq = None, []
for line in gzip.open("MANE.GRCh38.v1.5.ensembl_protein.faa.gz", "rt"):
    if line.startswith(">"):
        if key:
            mane[key] = "".join(seq)
        key, seq = line[1:].split()[0].split(".")[0], []
    else:
        seq.append(line.strip())
mane[key] = "".join(seq)
enst2ensp = {
    r["Ensembl_nuc"].split(".")[0]: r["Ensembl_prot"].split(".")[0]
    for r in csv.DictReader(gzip.open("MANE.GRCh38.v1.5.summary.txt.gz", "rt"), delimiter="\t")
    if r["MANE_status"] == "MANE Select"
}
c = collections.Counter()
out = open("mane_uniprot_differs_classified.tsv", "w")
out.write("symbol\tENST\tuniprot\tmane_len\tcanonical_len\tlinked_by\tclass\tmatching_isoform\n")
for r in csv.DictReader(open("mane_uniprot_differs.tsv"), delimiter="\t"):
    p = mane[enst2ensp[r["ENST"]]]
    hit = [i for i, s in iso.get(r["uniprot"], {}).items() if s == p]
    cls = (
        "equals_noncanonical_isoform"
        if hit
        else ("same_length_substitution" if r["mane_len"] == r["uniprot_len"] else "no_exact_isoform_match")
    )
    c[(r["linked_by"], cls)] += 1
    out.write(
        "\t".join(
            [r[k] for k in ["symbol", "ENST", "uniprot", "mane_len", "uniprot_len", "linked_by"]]
            + [cls, ",".join(hit)]
        )
        + "\n"
    )
for k, v in sorted(c.items()):
    print(k, v)
