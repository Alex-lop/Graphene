# Predictions, then what happened

Each prediction was written before the measurement it predicts was run. The "What happened" line under
each was written after. Times are local (EDT, UTC-4).

What I had seen before writing these (2026-09-30 00:50–00:53 EDT): the shape of one ClinVar esummary record
(VCV000012366, TP53 R273H), the ClinVar search counts per gene (TP53 1463, KRAS 225, BRAF 665, PIK3CA 763,
EGFR 1968, PTEN 1316 missense single-nucleotide variants), the AlphaFold DB API entry for TP53 (model v6,
global pLDDT 75.06, 40.2% of residues below 70), the AlphaMissense CSV header for TP53, and UniProt's KRAS
entry, whose canonical sequence is isoform 2A (K-Ras4A, 189 aa) while the MANE Select transcript
NM_004985.5 encodes isoform 2B (K-Ras4B, 188 aa). I had not run any check.

## P0. Slice size — written 2026-09-30 00:53 EDT

- I expect about 6,400 ClinVar records in total and that at least 97% of them carry a parsable
  single-residue protein change `p.Xaa<n>Yaa` in their title. No cap is needed at this size.

**What happened (00:56).** 6,400 records (TP53 1,463, KRAS 225, BRAF 665, PIK3CA 763, EGFR 1,968, PTEN
1,316); 6,227 (97.3%) parsed, just above my bar. No cap was applied. The 173 that did not parse are not
junk: ClinVar's own `protein_change` field shows each is missense only on an isoform other than the
transcript in its title (for example `NM_004985.5(KRAS):c.451-5642A>T` is intronic on K-Ras4B and E153V on
K-Ras4A; PTEN's 112 `c.-N` records are 5' UTR on NM_000314.8 and missense in the longer PTEN-L). Eight
more are titled on an overlapping gene (WRAP53, KCNMB3, KLLN), one is a nonsense change and one a compound
allele. I did not foresee the isoform reason; I expected malformed titles.

## P1. Wild-type residue check — written 2026-09-30 00:53 EDT

- Overall I expect fewer than 3% of variants to fail (stated wild-type residue differs from UniProt
  canonical or from the AlphaFold model at that position).
- I expect almost all failures in KRAS, in the C-terminal region (about residue 151 onward) where K-Ras4B
  (ClinVar's MANE transcript) differs from K-Ras4A (UniProt canonical): somewhere between 5% and 25% of KRAS
  variants.
- I expect zero or near-zero failures in TP53, PIK3CA, PTEN, EGFR and BRAF, because I believe their MANE
  Select RefSeq proteins equal the UniProt canonical sequence. Guess: a handful of records titled against
  a non-MANE transcript (for example BRAF NM_001374258.1, 807 aa) may fail.
- I expect the AlphaFold v6 model sequence to equal the current UniProt canonical sequence for all six
  proteins, so no failure caused by the structure alone.

**What happened (00:56).** 17 of 6,227 checkable variants fail (0.27%), under the 3% bound. KRAS: 16 of 213
(7.5%, inside the 5–25% range), every one at residues 153–188 and every one explained: ClinVar numbers on
NM_004985.5/NP_004976.2 (K-Ras4B) while UniProt P01116 canonical and the AlphaFold model are K-Ras4A. BRAF:
1 (K807T on NM_001374258.1, an 807-residue RefSeq isoform, past the end of the 766-residue canonical), as
guessed. TP53, PIK3CA, EGFR, PTEN: 0. No failure came from the AlphaFold model alone (0 cases where UniProt
matched and the model did not). All predictions in P1 held.

## P2. Controls — written 2026-09-30 00:53 EDT

Method: AlphaMissense class as served by AlphaFold DB (likely pathogenic above 0.564, likely benign below
0.34, ambiguous between, per Cheng et al. 2023; to be confirmed from the paper).

- I expect all eight positive controls (KRAS G12D, BRAF V600E, TP53 R175H, R248Q, R273H, PIK3CA H1047R,
  EGFR L858R, PTEN R130Q) to be classed likely pathogenic. If one misses, I guess it is a gain-of-function
  activating hotspot (PIK3CA H1047R or EGFR L858R) scored ambiguous, because a conservation-driven model
  has less to say about activating mutations than about loss of function.
- I expect the negative control TP53 P72R (a common polymorphism) to be classed likely benign, with the
  caveat, to be checked, that AlphaMissense's benign training labels include common human variants, so
  this control is partly circular.
- So I expect the controls check to exit 0.

**What happened (01:00).** Wrong on the exit code: the check exits 1. Ten of eleven controls pass; PIK3CA
H1047R, the most frequent PIK3CA hotspot (537 tumours in cancerhotspots.org), scores 0.538 and is classed
ambiguous, just under the 0.564 line. My guess about which control would miss was right. All three
negative controls are likely benign (TP53 P72R 0.072, PIK3CA I391M 0.081, EGFR R521K 0.061). Separately,
the first version of my own threshold precondition was wrong: it flagged 6 of 76,551 AlphaMissense rows
whose published score is exactly 0.34 or 0.564; they are rounding artefacts (scores are published to four
decimals and classed before rounding), so I added a half-unit tolerance and recorded it.

## P3. Confidence at the site (pLDDT >= 70) — written 2026-09-30 00:53 EDT

- Overall I expect 10–15% of variants to sit at a residue with pLDDT below 70.
- Per gene, guesses: TP53 about 15% (its disordered N-terminal transactivation region and C-terminus are
  about 40% of residues, but ClinVar variants cluster in the DNA-binding domain); BRAF about 20%
  (disordered N-terminus and linker); EGFR about 15% (C-terminal tail); PTEN about 10% (C-terminal tail);
  PIK3CA about 5%; KRAS about 5% (the hypervariable region at the C-terminus).
- So I expect the pLDDT check to exit 1 (some sites fail) on every gene.

**What happened (01:01).** Exit 1 on every gene, as predicted, but the size was badly wrong: 1,672 of
6,210 sites (26.9%) are below 70, about double my 10–15%. Per gene: TP53 31.3% (predicted 15%), BRAF 50.7%
(20%), EGFR 33.1% (15%), PTEN 15.9% (10%), PIK3CA 5.7% (5%), KRAS 3.0% (5%). I underestimated how evenly
ClinVar's germline-panel variants spread over disordered regions (EGFR's C-terminal tail, residues
985–1210, alone holds 414 sites). The surprise that matters: BRAF V600 (pLDDT 49.1) and EGFR L858 (51.2),
two of the best-known actionable cancer variants, sit in low-confidence activation segments and fail this
check, while TP53 R175/R248/R273, KRAS G12, PIK3CA H1047 and PTEN R130 pass.

## P4. Agreement with ClinVar — written 2026-09-30 00:53 EDT

- Among variants ClinVar classes pathogenic or likely pathogenic (germline classification), I expect
  85–90% classed likely pathogenic by AlphaMissense, 5–10% ambiguous, and under 5% likely benign.
- Among variants ClinVar classes benign or likely benign, I expect about 60–70% classed likely benign by
  AlphaMissense, and the rest ambiguous or likely pathogenic (TP53 and PTEN benign calls often rest on
  population frequency, which a structure-and-conservation model may disagree with).
- Overall I expect 15–25% of the ClinVar-classified variants flagged for sign-off (AlphaMissense disagrees
  or is ambiguous), and that most records in the slice (about 70%) are variants of uncertain significance
  or conflicting, so they are reported but not compared.
- So I expect the agreement check to exit 3 (needs a scientist's sign-off) on every gene.

**What happened (01:02).** Exit 3 on every gene, as predicted. ClinVar pathogenic: 764 of 805 (94.9%)
likely pathogenic, 21 (2.6%) ambiguous, 20 (2.5%) likely benign: better than my 85–90%. ClinVar benign:
198 of 233 (85.0%) likely benign, 14 ambiguous, 21 likely pathogenic: better than my 60–70%. Flagged for
sign-off: 76 of 1,038 classified sites (7.3%), well under my 15–25%. Unclassified: 5,172 of 6,210 (83.3%;
4,218 uncertain significance, 841 conflicting), above my 70%. On ClinVar's separate oncogenicity axis,
216 of 227 compared sites agree (95.2%). My first version of that oncogenicity column counted 55
"Uncertain significance" records as benign; I fixed it before recording these numbers.

## P2b. More controls, added before check 2 ran — written 2026-09-30 01:00 EDT

Seen since P2: the ClinVar classifications of the candidate controls (not their AlphaMissense scores).
TP53 P72R and PIK3CA I391M are Benign (expert panel); EGFR R521K is Benign/Likely benign. BRAF V600E's
germline classification is "Conflicting classifications of pathogenicity" and EGFR L858R's is "drug
response"; both are "Oncogenic" on ClinVar's oncogenicity axis.

- I expect the two added negative controls, PIK3CA I391M and EGFR R521K (common polymorphisms), to be
  classed likely benign, like TP53 P72R. Guess: one of the three lands in ambiguous.
- Hotspot sweep (reported, not gating): of every missense allele at a cancerhotspots.org single-residue
  hotspot in the six genes seen in at least 5 tumors, I expect at least 90% classed likely pathogenic by
  AlphaMissense, with the misses concentrated in gain-of-function oncogene alleles (PIK3CA, EGFR) rather
  than TP53 and PTEN.
- I expect every hotspot residue letter in cancerhotspots to match UniProt canonical at that position.

**What happened (01:00).** Negative controls: all three likely benign, so the "one lands in ambiguous"
guess was wrong. Sweep: 349 of 362 hotspot alleles (96.4%) likely pathogenic, 8 ambiguous, 5 likely
benign, meeting the 90% bound. By rate the misses are in the oncogenes as predicted (PIK3CA 5 of 58, EGFR 2
of 18), but by count TP53 has the most (6 of 234: R110L, R110C, K132R, L130V, P152L, Q331H); KRAS 21/21,
BRAF 13/13 and PTEN 18/18 are all likely pathogenic. Every hotspot residue matched UniProt canonical (0 of
362), as predicted.
