"""Fetch the public slice the checks read: ClinVar, UniProt, AlphaFold DB, AlphaMissense, cancerhotspots.

Files land in data/ and are reused if already there (delete data/ to refetch). Every file's endpoint,
release header and sha256 go into data/manifest.json. NCBI E-utilities are called without a key, at most
three requests a second.
"""

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from common import DATA, GENES

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "graphene-bio-spike"
HEADERS = {"User-Agent": f"{TOOL} (public-data check spike)"}
TERM = (
    '{gene}[gene] AND "missense variant"[molecular consequence]'
    ' AND "single nucleotide variant"[Type of variation]'
)
BATCH = 200
MANIFEST = DATA / "manifest.json"
# The manifest describes what was downloaded and when; cached files keep the entry of their first fetch.
manifest: dict = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}, "sources": {}}
_last_ncbi = 0.0


def get(url: str, data: dict | None = None) -> tuple[bytes, dict]:
    global _last_ncbi
    if url.startswith(EUTILS):  # without an API key NCBI allows 3 requests/s; stay under it
        time.sleep(max(0.0, 0.34 - (time.monotonic() - _last_ncbi)))
        _last_ncbi = time.monotonic()
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), dict(r.headers)
        except OSError as e:  # URLError/HTTPError/timeouts: retry with backoff, then give up loudly
            if attempt == 3:
                raise
            print(f"  retry {url[:90]}: {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def save(path: Path, url: str, content: bytes, headers: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    keep = {k: v for k, v in (headers or {}).items() if k.lower().startswith(("x-uniprot", "last-modified"))}
    manifest["files"][str(path.relative_to(DATA))] = {
        "url": url,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        **({"headers": keep} if keep else {}),
    }


def fetch(path: Path, url: str) -> bytes:
    if not path.exists():
        print(f"  GET {url}")
        save(path, url, *get(url))
    return path.read_bytes()


def fetch_uniprot_and_alphafold(gene: str, acc: str) -> None:
    fetch(DATA / "uniprot" / f"{acc}.fasta", f"https://rest.uniprot.org/uniprotkb/{acc}.fasta")
    api = json.loads(
        fetch(DATA / "alphafold" / f"{acc}.api.json", f"https://alphafold.ebi.ac.uk/api/prediction/{acc}")
    )
    entry = next(e for e in api if e["uniprotAccession"] == acc)  # the canonical model, not an isoform model
    keys = ("modelEntityId", "latestVersion", "modelCreatedDate", "sequenceVersionDate", "toolUsed")
    manifest["sources"][f"alphafold:{acc}"] = {k: entry[k] for k in keys}
    fetch(DATA / "alphafold" / f"{acc}.pdb", entry["pdbUrl"])
    fetch(DATA / "alphafold" / f"{acc}.am.csv", entry["amAnnotationsUrl"])


def fetch_clinvar(gene: str) -> None:
    path = DATA / "clinvar" / f"{gene}.json"
    url = f"{EUTILS}/esummary.fcgi?db=clinvar (POST, ids from esearch: {TERM.format(gene=gene)})"
    if path.exists():
        return
    if "clinvar" not in manifest["sources"]:
        info = json.loads(get(f"{EUTILS}/einfo.fcgi?db=clinvar&retmode=json&tool={TOOL}")[0])
        db = info["einforesult"]["dbinfo"][0]
        manifest["sources"]["clinvar"] = {k: db[k] for k in ("dbbuild", "lastupdate", "count")}
    q = {"db": "clinvar", "term": TERM.format(gene=gene), "retmax": 10000, "retmode": "json", "tool": TOOL}
    ids = json.loads(get(f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(q))[0])["esearchresult"]["idlist"]
    print(f"  ClinVar {gene}: {len(ids)} ids")
    records = {}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i : i + BATCH]
        body = {"db": "clinvar", "id": ",".join(chunk), "retmode": "json", "tool": TOOL}
        result = json.loads(get(f"{EUTILS}/esummary.fcgi", body)[0])["result"]
        records.update({uid: result[uid] for uid in result["uids"]})
    if len(records) != len(ids):
        sys.exit(f"ClinVar {gene}: asked for {len(ids)} summaries, got {len(records)}")
    save(path, url, json.dumps(records, indent=0).encode())


def fetch_refseq_proteins() -> None:
    """The RefSeq protein behind each transcript ClinVar numbers against, to explain any mismatch."""
    transcripts = set()
    for gene in GENES:
        for rec in json.loads((DATA / "clinvar" / f"{gene}.json").read_text()).values():
            transcripts.update(re.findall(r"^(NM_\d+\.\d+)\(", rec["title"]))
    for nm in sorted(transcripts):
        q = {"db": "nuccore", "id": nm, "rettype": "fasta_cds_aa", "retmode": "text", "tool": TOOL}
        fetch(DATA / "refseq" / f"{nm}.fasta", f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(q))


def main() -> None:
    for gene, acc in GENES.items():
        print(f"{gene} ({acc})")
        fetch_uniprot_and_alphafold(gene, acc)
        fetch_clinvar(gene)
    fetch_refseq_proteins()
    # Independent evidence for the positive controls: recurrent tumour hotspots (Chang et al.; ODbL).
    fetch(DATA / "hotspots.json", "https://www.cancerhotspots.org/api/hotspots/single")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
