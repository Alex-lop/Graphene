# Two measurements behind the biology section (M1 and M2)

The fields run's biology researcher ran these on 2026-09-30, beside the check spike one directory up.
They used public data only, with no key and no account. Linted by the integrator; `ruff format` changed
the layout only. Standard library only. Each script reads and writes files in the directory it runs in.
The data is not committed.

## M1: how often MANE Select differs from the UniProt canonical protein

- **Data**
  - `MANE.GRCh38.v1.5.summary.txt.gz` and `MANE.GRCh38.v1.5.ensembl_protein.faa.gz` from
    https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/
  - `UP000005640_9606_additional.fasta.gz` (the isoforms), from UniProt's reference-proteome FTP for release
    2026_03.
  - `python3 fetch_uniprot.py` pages UniProt REST for every reviewed human entry and writes
    `uniprot_human_reviewed.tsv`.
- **Run**
  - `python3 mane_vs_uniprot.py` writes `mane_uniprot_differs.tsv`.
  - `python3 differs_vs_isoforms.py` writes `mane_uniprot_differs_classified.tsv`.
- **Result**
  - Of 18,599 MANE Select transcripts that a reviewed UniProt entry cross-references, **1,017 (5.47%)**
    encode a protein different from that entry's canonical sequence.
  - 1,006 of those equal one of the entry's named isoforms.
  - KRAS and EZH2 are among them.
  - The researcher wrote no prediction beforehand. Their prior, from a 2024 paper's "92% agreed with MANE",
    was about 8%.

## M2: KRAS, ClinVar against the AlphaFold DB model and AlphaMissense

- **Data**
  - A ClinVar `esearch` for `KRAS[gene] AND "missense variant"[molecular consequence] AND single_gene[prop]`,
    then one `esummary`, saved as `kras_esearch.json` and `kras_esummary.json`.
  - `https://alphafold.ebi.ac.uk/api/prediction/P01116`, saved as `afdb_P01116.json`.
  - `https://alphafold.ebi.ac.uk/files/AF-P01116-F1-hg38.csv`, saved as `am_P01116_hg38.csv`.
  - `https://alphafold.ebi.ac.uk/files/AF-P01116-F1-confidence_v6.json`, saved as `afdb_P01116_conf.json`.
- **Run:** `python3 wt_check_kras.py`, `python3 join_check_kras.py`, `python3 kras_checks_combined.py`,
  `python3 kras_agreement.py`.
- **Result**
  - 32 of 213 KRAS missense SNVs sit where the K-Ras4B numbering ClinVar uses and the K-Ras4A model and
    AlphaMissense file disagree.
  - A wild-type residue check against the model catches **16 of the 32**.
  - A join by the protein-change string gives **13 of 213 another codon's score, with no error**. Four of
    those 13 are pathogenic in ClinVar.
  - A join on genomic position, or a check that the numbering protein equals the model's sequence, catches
    **all 32**.
- **Prediction** (the researcher's working notes, not timestamped): the wild-type check would catch the
  isoform problem. It caught half.

The check spike one directory up counts records differently: 16 KRAS records fail its check 1. Its
README explains its counting.
