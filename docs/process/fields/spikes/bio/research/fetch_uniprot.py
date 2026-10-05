# Page through UniProt REST (no key) for reviewed human entries: accession, gene, sequence, MANE-Select xref.
import re
import time
import urllib.request

url = (
    "https://rest.uniprot.org/uniprotkb/search?format=tsv&size=500"
    "&fields=accession,gene_primary,length,sequence,xref_mane-select"
    "&query=(organism_id:9606)+AND+(reviewed:true)"
)
out = open("uniprot_human_reviewed.tsv", "w")
first = True
n = 0
while url:
    for attempt in range(5):
        try:
            r = urllib.request.urlopen(url, timeout=120)
            break
        except Exception as e:
            print("retry", attempt, e)
            time.sleep(5)
    body = r.read().decode()
    rel = r.headers.get("X-UniProt-Release")
    lines = body.splitlines()
    out.write("\n".join(lines if first else lines[1:]) + "\n")
    first = False
    n += len(lines) - 1
    m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link") or "")
    url = m.group(1) if m else None
print("rows", n, "release", rel)
