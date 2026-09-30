# The biology check spike

A test, with no compute and no spend, of whether the checks a careful bioinformatician puts on a variant
pipeline can be written as commands whose exit code is the verdict, and what they catch on real public data.
It uses six cancer genes (TP53, KRAS, BRAF, PIK3CA, EGFR, PTEN), all 6,400 of their ClinVar missense
single-nucleotide records, UniProt canonical sequences, AlphaFold DB v6 models (per-residue pLDDT),
AlphaMissense scores from AlphaFold DB, and cancerhotspots.org as independent evidence for the controls. Run
2026-09-30, 00:50–01:15 EDT, on a laptop. No GPU, no model call, no account and no key.

Written for FIELDS_DIRECTIVE.md §2 ("A check spike with no compute"). Predictions were written before each
measurement, with timestamps, in [PREDICTIONS.md](PREDICTIONS.md); what happened is recorded under each one.

## Run it

```
./run.sh
```

It fetches the slice into `data/` (63.8 s cold, 22 MB; files already present are reused), compares every
input with the SHA-256 hashes pinned in `inputs.sha256`, runs `selftest.py` (the checks' own check), then
runs each check on all six genes and on each gene alone and prints the exit codes. It needs `python3` (3.10
or later, standard library only; tested on 3.13.9), network access to the endpoints below, and `shasum`. The full
output of each all-gene run goes to `data/out_<check>.txt`. To run one check: `python3 check_wt.py [GENE ...]`.

**Exit codes, the same for every check:** `0` pass, `1` fail, `2` could not run (missing or unreadable
input; `common.run` maps any crash to 2, because Python's own crash code is 1 and would read as a fail),
`3` needs a scientist's sign-off.

| File | What it is |
|---|---|
| `fetch.py` | downloads the slice and writes `data/manifest.json` (URL, time, SHA-256, release headers) |
| `common.py` | the gene list, the exit codes, readers for each source, and the wild-type comparison |
| `check_wt.py` | check 1: stated wild-type residue = UniProt canonical = AlphaFold model at that position |
| `check_controls.py` | check 2: named controls come out as AlphaMissense says; also a hotspot sweep, reported only |
| `check_plddt.py` | check 3: pLDDT >= 70 at each site that passed check 1 |
| `check_agreement.py` | check 4: AlphaMissense class vs ClinVar germline classification; disagreement exits 3 |
| `selftest.py` | the checks fail when they should (a wrong residue, an isoform, a boundary score, a crash) |
| `inputs.sha256` | the hashes of the 47 input files as fetched on 2026-09-30 |
| `run.sh` | all of the above, end to end |

## Results

Counts are ClinVar records (VCV accessions). Two records can name the same protein change through different
nucleotide changes: the 6,227 checkable records are 6,005 distinct protein changes.

| Gene | ClinVar records | Checkable | Check 1: wild-type mismatch | Check 3: sites (passed 1) | Check 3: pLDDT < 70 | Check 4: ClinVar P / B / other | Check 4: agree | Check 4: flagged (discordant + ambiguous) | Check 2: controls |
|---|---|---|---|---|---|---|---|---|---|
| TP53 | 1,463 | 1,443 | 0 (0.0%) | 1,443 | 452 (31.3%) | 243 / 157 / 1,043 | 362 | 38 (22 + 16) | 4 of 4 |
| KRAS | 225 | 213 | 16 (7.5%) | 197 | 6 (3.0%) | 72 / 1 / 124 | 68 | 5 (2 + 3) | 1 of 1 |
| BRAF | 665 | 660 | 1 (0.2%) | 659 | 334 (50.7%) | 119 / 13 / 527 | 130 | 2 (1 + 1) | 1 of 1 |
| PIK3CA | 763 | 761 | 0 (0.0%) | 761 | 43 (5.7%) | 91 / 8 / 662 | 81 | 18 (8 + 10) | 1 of 2 (H1047R fails) |
| EGFR | 1,968 | 1,951 | 0 (0.0%) | 1,951 | 646 (33.1%) | 13 / 45 / 1,893 | 54 | 4 (3 + 1) | 2 of 2 |
| PTEN | 1,316 | 1,199 | 0 (0.0%) | 1,199 | 191 (15.9%) | 267 / 9 / 923 | 267 | 9 (5 + 4) | 1 of 1 |
| **Total** | **6,400** | **6,227** | **17 (0.27%)** | **6,210** | **1,672 (26.9%)** | **805 / 233 / 5,172** | **962 (92.7% of 1,038)** | **76 (7.3% of 1,038)** | **10 of 11** |

"Checkable": the record's title names a protein substitution `p.Xaa<n>Yaa` on the queried gene; the other
173 (2.7%) are explained below. "P" is ClinVar germline Pathogenic, Likely pathogenic or both; "B" is Benign,
Likely benign or both; "other" is uncertain significance (4,218), conflicting (841), none (88) and a few
others (25: 10 "not provided", 10 "drug response", and 5 compound labels such as "Pathogenic; drug
response", 4 of which the strict mapping leaves out of the comparison). On ClinVar's
separate somatic oncogenicity axis (reported, not gated on), 216 of the 227 sites with an oncogenic or
benign call agree with AlphaMissense (95.2%).

Exit codes printed by `./run.sh` (identical in the cold rerun at 01:04):

```
exit codes         all  TP53   KRAS   BRAF   PIK3CA EGFR   PTEN
check_wt.py        1    0      1      1      0      0      0
check_controls.py  1    0      0      0      1      0      0
check_plddt.py     1    1      1      1      1      1      1
check_agreement.py 3    3      3      3      3      3      3
```

Controls (method: AlphaMissense class; likely benign below 0.34, likely pathogenic above 0.564, ambiguous
between, per [the AlphaMissense Zenodo record](https://zenodo.org/records/10813168), read 2026-09-30). A
positive control counts only if cancerhotspots.org has it as a single-residue hotspot allele in at least 20
tumours; a negative control only if ClinVar's germline classification is benign or likely benign. The check
verifies that evidence from the downloaded data, so a control cannot be asserted into existence.

| Kind | Variant | Evidence the check verified | AlphaMissense | Verdict |
|---|---|---|---|---|
| positive | KRAS G12D | 757 tumours; ClinVar VCV000012582 P/LP | 0.998 likely pathogenic | pass |
| positive | BRAF V600E | 833 tumours; ClinVar germline: conflicting | 0.993 likely pathogenic | pass |
| positive | TP53 R175H | 386 tumours; VCV000012374 Pathogenic (expert panel) | 0.986 likely pathogenic | pass |
| positive | TP53 R248Q | 292 tumours; VCV000012356 Pathogenic (expert panel) | 0.996 likely pathogenic | pass |
| positive | TP53 R273H | 251 tumours; VCV000012366 Pathogenic (expert panel) | 0.989 likely pathogenic | pass |
| positive | PIK3CA H1047R | 537 tumours; VCV000013652 Pathogenic (expert panel) | **0.538 ambiguous** | **fail** |
| positive | EGFR L858R | 144 tumours; ClinVar germline: "drug response" | 0.997 likely pathogenic | pass |
| positive | PTEN R130Q | 72 tumours; VCV000007829 Pathogenic (expert panel) | 1.000 likely pathogenic | pass |
| negative | TP53 P72R | VCV000012351 Benign (expert panel) | 0.072 likely benign | pass |
| negative | PIK3CA I391M | VCV000135038 Benign (expert panel) | 0.081 likely benign | pass |
| negative | EGFR R521K | VCV000134021 Benign/Likely benign | 0.061 likely benign | pass |

Hotspot sweep (not gating, not hand-picked): of the 362 missense alleles at cancerhotspots.org single-residue
hotspots in the six genes seen in at least 5 tumours, 349 (96.4%) are likely pathogenic, 8 ambiguous and 5
likely benign; every hotspot residue matches UniProt canonical.

## Why the failures happen (a look at each)

**Check 1, wild-type mismatch: 17 of 6,227, every one explained, none an error in the data.** All 16 KRAS
mismatches sit at residues 153–188. ClinVar numbers KRAS on NM_004985.5 / NP_004976.2, which is K-Ras4B
(188 aa, the MANE Select transcript), while UniProt P01116's canonical sequence and the AlphaFold model
AF-P01116-F1 are K-Ras4A (189 aa); the two isoforms differ from residue 151 on. Example: VCV000012587
`p.Asp153Val` states D153, and UniProt canonical and the model have E. The BRAF one is VCV004881354
`p.Lys807Thr` on NM_001374258.1, an 807-residue RefSeq isoform, past the end of the 766-residue canonical.
Without check 1, a pipeline would have scored these 17 with the wrong residue's AlphaMissense row and the
wrong pLDDT, silently. The remedy is a scientist's choice of isoform: AlphaFold DB v6 does serve a K-Ras4B
model (AF-P01116-2-F1) but no AlphaMissense file for it (only canonical entries carry `amAnnotationsUrl`,
checked in the API responses for KRAS, BRAF, PTEN and TP53).

**Not checkable: 173 records (2.7%), most of them missense only on another isoform.** 159 are titled as
intronic (40), 5' UTR (115) or 3' UTR (4) on their transcript, yet the search required a missense consequence;
ClinVar's own `protein_change` field shows why, checked on one example of each kind: KRAS `NM_004985.5:c.451-5642A>T` is intronic on K-Ras4B and E153V on K-Ras4A (the UniProt
canonical); PTEN's 112 `c.-N` records are 5' UTR on NM_000314.8 and missense in the longer PTEN-L; TP53's
and EGFR's records are intronic (or, for 3 TP53 records, 5' UTR) on the titled transcript and missense on
others; KRAS's `c.*N` records are 3' UTR on K-Ras4A and missense on K-Ras4B. Eight records are
titled on an overlapping gene (WRAP53, KCNMB3, KLLN), one is a nonsense change (BRAF p.Gly393Ter) and one a
compound allele, and 4 are titled in genomic coordinates (`NC_...:g.`) with protein changes on
non-canonical BRAF and PTEN isoforms. The check reports all of these by reason rather than dropping them.

**Check 2, controls: 1 of 11 fails.** PIK3CA H1047R, the most frequent PIK3CA hotspot, scores 0.538, just
under the 0.564 line. The sweep shows the same pattern for other PIK3CA hotspot alleles (H1047L 0.438,
H1047Y 0.230, E970K 0.529, M1V 0.130). *Inference, not verified:* AlphaMissense is "fine-tuned on human and primate
variant population frequency databases" ([abstract, PMID 37733863](https://pubmed.ncbi.nlm.nih.gov/37733863/)),
which may say more about loss of function than about gain-of-function activation. The check is right to
fail: the method, applied as stated, does not reproduce this control, and only a scientist can say whether
the method is fit for activating oncogene variants. My own first version of this check was wrong too: its
precondition (every AlphaMissense class follows the thresholds) flagged 6 of 76,551 rows whose published
score is exactly 0.34 or 0.564. Scores are published to four decimals and classed before rounding, so those
six are consistent; the check now allows half a unit at the boundary, and `selftest.py` pins that.

**Check 3, pLDDT below 70: 1,672 of 6,210 sites (26.9%).** The low sites sit in runs of low-confidence
residues: TP53 1–19 and 26–93 (250 sites), 293–323 and 356–393 (198 sites); EGFR 985–1210 (414 sites); BRAF
1–43, 104–154 and 281–448 (263 sites); PTEN 282–313 and 352–403 (173 sites). *Inference:* these are the disordered termini and linkers
of each protein; ClinVar's germline-panel variants spread over them because panel sequencing sees every
residue. The finding that matters is narrower: **BRAF V600 (pLDDT 49.1) and EGFR L858 (51.2), two of the
best-known actionable cancer variants, fail this check**, because both sit in runs the AlphaFold monomer
model leaves at low confidence (BRAF 595–615, EGFR 856–875; that these are the kinases' activation
segments is my reading, not checked tonight). TP53 R175/R248/R273 (96.6
to 98.6), KRAS G12 (93.9), PIK3CA H1047 (83.1) and PTEN R130 (98.4) pass.

**Check 4, flagged for sign-off: 76 of 1,038 classified sites (7.3%); 41 discordant, 35 ambiguous.**
ClinVar P sites: 764 of 805 (94.9%) likely pathogenic. ClinVar B sites: 198 of 233 (85.0%) likely benign.
What the 76 flags are, from reading all of them:
- 20 rest on expert-panel records. Eight are TP53 variants ClinVar calls likely benign that AlphaMissense
  calls likely pathogenic (V122M, T118I, M160I, E171K, G262S, R283C, T284I, L289P); *inference:* the TP53
  expert panel's benign calls draw on evidence AlphaMissense does not see, such as functional assays. I did
  not open the panel's evidence.
- 17 are PIK3CA variants ClinVar calls pathogenic or likely pathogenic, mostly for PIK3CA-related
  overgrowth, megalencephaly or Cowden syndromes, scored ambiguous or likely benign. They include the
  hotspot alleles H1047R, H1047L and H1047Y and neighbours in the same stretch (M1043L, N1044S, H1048R,
  G1050S): the same pattern as the failed control.
- 3 are start-codon changes (PTEN M1V, and M1L in two records) ClinVar calls pathogenic and AlphaMissense
  likely benign. These are not a disagreement about the variant: the effect is loss of the start codon,
  while AlphaMissense scores a residue substitution. The two sources answer different questions here.
- 43 rest on weak references: 33 single-submitter records and 10 with no assertion criteria.
- 12 of the 76 sit below pLDDT 70.

## What this shows about Graphene's second and third conditions in biology

The directive's conditions: (2) each piece has a cheap check that cannot be faked; (3) passing the checks
means what the person meant, or the gap between the two is small and visible.

**Condition 2, cheap: yes.** Four checks over 6,400 records run in 2.5 s with data cached; the whole spike,
cold, in about 65 s and 22 MB, with no compute. Check 1 flagged 17 isoform mismatches and reported the 173
records it could not check (most of them missense only on another isoform) at the cost of a string
comparison, before anything downstream could have used the wrong residue. A numbering error that happens to land on the same
residue would pass it; none was seen, and the spike cannot measure how many there are.

**Condition 2, cannot be faked: only with inputs pinned outside the agent's reach.** In a copy of the spike
(`scratchpad/notes/bio-cold`, not committed) I deleted the 16 KRAS records that fail check 1 from
`data/clinvar/KRAS.json`: `check_wt.py KRAS` then exited 0. Only `shasum -a 256 -c inputs.sha256` caught it
(`clinvar/KRAS.json: FAILED`, exit 1). Changing TP53 residue 175 in the UniProt file was caught by both
check 1 (5 mismatches, exit 1) and the pins. So a check over data is only as honest as its inputs, and the
inputs need a check of their own that the executor cannot edit. In Graphene that is the leaf's scope (the
pins and the checks outside it) plus a pin check in the check command. What stays gameable: the choice of
slice and thresholds. Here the controls' evidence comes from a source independent of the method and every
prediction was written before its run, which is the biological version of a pre-registration.

**Condition 3, passing means what the scientist meant: no, and this spike shows where it breaks.** Every
check here is correct as written, and still:
- Check 3 would tell a pipeline not to interpret BRAF V600E and EGFR L858R structurally. That is true of the
  model and wrong for the biology: a run that passes this check drops two of the variants a cancer
  biologist cares most about. Whether a low-confidence activation loop disqualifies a site is a judgment, not a threshold.
- Check 4's verdict depends on which ClinVar axis is the reference. On the germline axis, BRAF V600E is
  "conflicting" and EGFR L858R is "drug response", so neither is compared at all; on the oncogenicity axis
  both are "Oncogenic". On the germline axis, the most frequent named traits of the pathogenic BRAF and
  KRAS records are RASopathies (RASopathy, cardiofaciocutaneous and Noonan syndromes), and of PIK3CA
  overgrowth syndromes; a cancer trait such as non-small cell lung carcinoma is on 11 of 119 pathogenic
  BRAF records. A scientist picks the axis; the check cannot.
- Check 2 fails on the method, not the data. What to do next (change method, threshold, or scope of the
  claim) is the scientist's call.
- 83% of the slice is uncertain or conflicting in ClinVar, so "agreement with the reference" speaks for 17%
  of the variants; for the rest there is no reference, which is where a pipeline like this is meant to be
  used.

So in biology the gap between passing and meaning is wide, and it is visible only if the checks report
counts, causes and flags rather than one bit. That is the directive's hypothesis ("struggles with the
second and third") confirmed on the third and qualified on the second: the second holds for invariants
(numbering, controls against independent evidence, input pins), not for interpretation.

**What it does not show.** Nothing here was a pipeline Alex ran, or ran on a cluster, or used a GPU; there
was no long job, no SLURM, no reference-build question (every source was protein-level, so GRCh37 vs GRCh38
never arose), and no NetSurfP. It does not measure a person's attention or whether a scientist would sign
off faster with these flags than without. Six genes are among the best-studied proteins there are; less
studied genes would have fewer controls and more uncertain records.

**What it means for today's Graphene** (from the code, not tested with Graphene):
- Graphene refuses any non-zero exit (`src/graphene_map/plan.py:854`, `run_check` returns `code == 0`), so
  exit 3 is just a fail today. Expressible now: have check 4 exit 0 once it has run, write its flag list to a
  file in the leaf's scope, and give the node `signoff:` so it stops in `review` (docs/HOW_IT_WORKS.md, the
  states table; DIRECTION.md decision 6). In this slice all six genes had flags, so an unconditional sign-off
  would have asked for nothing extra; a conditional one (exit 3 = review) is not yet earned by evidence.
- The log keeps the last 2,000 characters of a check's output (`TAIL`, plan.py:35); check 4's list of 76
  flags is 8,459, so the sign-off evidence must be a file, not the log.
- Graphene runs a check in a worktree cut from the node's committed state, and what git ignores is not
  there (docs/HOW_IT_WORKS.md, P2 step 3). This spike's `data/` is git-ignored, so under Graphene the checks
  would find no data and exit 2. The check would have to fetch (65 s and a network, with sources that
  change weekly) or read from a path outside the repository that no scope covers (reads are never scoped,
  DIRECTION.md decision 8). The pins in `inputs.sha256` make the second option honest: the data can live
  anywhere as long as the check verifies it against hashes committed in the repository.

## Sources, versions and licenses

All read or fetched 2026-09-30.

| Source | Endpoint | Version got | License / terms |
|---|---|---|---|
| ClinVar (NCBI) | `esearch.fcgi?db=clinvar` with `<GENE>[gene] AND "missense variant"[molecular consequence] AND "single nucleotide variant"[Type of variation]`, then `esummary.fcgi` (POST, 200 ids a request) | einfo `dbbuild` Build260929-0200.1, `lastupdate` 2026/09/29 05:12 | NCBI "places no restrictions on the use or distribution of the data" but submitters may claim rights ([NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)); ClinVar asks for attribution and says it is "not intended for direct diagnostic use" ([ClinVar docs](https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/)). Rate limit without a key: "no more than 3 requests every 1 second"; fetch.py waits 0.34 s between calls |
| RefSeq proteins (NCBI) | `efetch.fcgi?db=nuccore&id=<NM_>&rettype=fasta_cds_aa` for the 16 transcripts ClinVar titles use | as served | as ClinVar (NCBI) |
| UniProtKB | `https://rest.uniprot.org/uniprotkb/<acc>.fasta` | release 2026_03 (2 September 2026), from the `X-UniProt-Release` header | CC BY 4.0 ([UniProt license](https://rest.uniprot.org/help/license)) |
| AlphaFold DB | `https://alphafold.ebi.ac.uk/api/prediction/<acc>`, then its `pdbUrl` | model v6 (`latestVersion` 6), `modelCreatedDate` 2025-08-01, "AlphaFold Monomer v2.0 pipeline" | CC BY 4.0, stated in each model file ("AVAILABLE FOR ACADEMIC AND COMMERCIAL PURPOSES, UNDER CC-BY 4.0 LICENCE") |
| AlphaMissense | AlphaFold DB `amAnnotationsUrl`, e.g. `https://alphafold.ebi.ac.uk/files/AF-P04637-F1-aa-substitutions.csv` | files last modified 30 September 2025; the Zenodo record is v3 (19 September 2023), and nothing I read says which release AlphaFold DB's files derive from | CC BY 4.0 for the predictions; "has not been validated for, and is not approved for, any clinical use" ([GitHub](https://github.com/google-deepmind/alphamissense), [Zenodo 10813168](https://zenodo.org/records/10813168)) |
| cancerhotspots.org | `https://www.cancerhotspots.org/api/hotspots/single` | 1,165 single-residue hotspots, the set the site attributes to Chang et al. 2016 and 2017 (24,592 tumours) | ODC Open Database License (ODbL), share-alike (site source, [cBioPortal/cancerhotspots](https://github.com/cBioPortal/cancerhotspots) `index.html`); code AGPL-3.0 |

None of these licenses stops the spike or its code from being committed. The downloaded data is not
committed (`data/` is ignored); if it ever were, the ODbL share-alike and each CC BY attribution would apply.

Other sources used for thresholds and interpretation:
- pLDDT bands: Varadi et al., *AlphaFold Protein Structure Database*, Nucleic Acids Research 50(D1), 2022
  ([PMC8728224](https://pmc.ncbi.nlm.nih.gov/articles/PMC8728224/)): >= 90 "very high", 70–90 "confident",
  50–70 "low", < 50 "very low". EMBL-EBI's AlphaFold course: 70–90 "usually corresponds to a correct
  backbone prediction with misplacement of some side chains"
  ([pLDDT page](https://www.ebi.ac.uk/training/online/courses/alphafold/inputs-and-outputs/evaluating-alphafolds-predicted-structures-using-confidence-scores/plddt-understanding-local-confidence/)).
  AlphaFold DB's own FAQ is a JavaScript page that the fetch tool could not read.
- AlphaMissense: Cheng et al., Science 381, eadg7492 (2023), PMID 37733863, abstract via Europe PMC.
- Hotspot references: Chang et al., Nature Biotechnology 34, 155–163 (2016), PMID 26619011; Chang et al.,
  Cancer Discovery (2017), PMID 29247016.

Machine and tools: macOS 26.5.2 (arm64), Python 3.13.9 (standard library only), uv 0.11.29, ruff 0.16.8
(`uv run ruff check docs/process/fields/spikes/bio`: "All checks passed!"; `ruff format --check` clean),
shasum 6.02.

## Commands run, in order (EDT, 2026-09-30)

| Time | Command | Result |
|---|---|---|
| 00:50 | `curl` of the AlphaFold DB API for P04637, the AlphaMissense CSV, a ClinVar esummary, UniProt KRAS | shapes of the sources; KRAS isoform difference seen; no measurement |
| 00:52 | `esearch` counts for the six genes; `einfo` | 6,400 records; Build260929-0200.1 |
| 00:53 | wrote PREDICTIONS.md P0–P4 | |
| 00:55 | `python3 fetch.py` | 63 s, 21 MB, 46 files |
| 00:56 | `python3 check_wt.py` (all, then each gene) | exit 1; per gene 0 1 1 0 0 0 |
| 01:00 | wrote P2b; added cancerhotspots to fetch.py; `python3 fetch.py` | 1 more file |
| 01:00 | `python3 check_controls.py` | exit 1; 6 off-threshold rows (my rounding bug) and H1047R |
| 01:01 | fixed the boundary tolerance; `python3 check_controls.py` (all, each gene) | exit 1; only PIK3CA exits 1 |
| 01:01 | `python3 check_plddt.py` (all, each gene) | exit 1 on every gene |
| 01:02 | `python3 check_agreement.py` (all, each gene) | exit 3 on every gene |
| 01:03 | fixed the oncogenicity column (it had counted 55 "uncertain" as benign); reran check 4 | exit 3; numbers above |
| 01:03 | `uv run ruff check` / `ruff format` | clean after wrapping long lines and fixing an undefined name in `check_plddt.py` |
| 01:04 | `python3 selftest.py`; wrote `inputs.sha256`; `./run.sh` | selftest holds; 2.5 s; codes as above |
| 01:04 | `./run.sh` in a clean copy (`scratchpad/notes/bio-cold`) | 63.8 s; all 47 inputs identical to the pins; same exit codes |
| 01:06 | tamper tests in that copy (see condition 2 above) | pin check exit 1 both times; `check_wt.py KRAS` fooled (exit 0) |
| 01:11 | after the last edits: `./run.sh`; `uv run ruff check` (spike and whole repo); `ruff format --check` | same numbers and exit codes; all clean |

## Limits and what I could not find

- ClinVar changes weekly (web data updated on Mondays, per ClinVar's docs); a rerun after 2026-10-05 will
  likely fail the pin check for the ClinVar files, and `run.sh` says so rather than stopping. To pin a new
  fetch: `cd data && shasum -a 256 hotspots.json uniprot/* alphafold/* clinvar/* refseq/* > ../inputs.sha256`.
- No cap was needed: all 6,400 records were used.
- I did not check the AlphaMissense isoforms file (Zenodo lists "60k non-canonical transcripts", "used with
  caution"), which might score the 16 K-Ras4B variants; nor the PTEN-L model for the 112 PTEN records.
- The strict ClinVar mapping leaves 4 records with compound classifications ("Pathogenic; drug response"
  and similar) out of the comparison.
- I could not read AlphaFold DB's FAQ or API documentation pages (client-side rendered); the license comes
  from the model files themselves and the bands from the database's paper and EMBL-EBI's course.
- Why AlphaMissense under-calls activating PIK3CA alleles and why some TP53 hotspots (R110L, R110C) score
  benign is inference or unknown; I did not look for literature on either.
