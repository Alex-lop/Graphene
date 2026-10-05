#!/usr/bin/env bash
# The bio check spike end to end: fetch the public slice (skipped for files already in data/), compare the
# inputs with the ones pinned on 2026-09-30, self-test the checks, then run every check on all six genes and
# on each gene alone. Check exit codes: 0 pass, 1 fail, 2 could not run, 3 needs a scientist's sign-off.
# Full output of each all-gene run lands in data/out_<check>.txt.
set -u
cd "$(dirname "$0")"
GENES="TP53 KRAS BRAF PIK3CA EGFR PTEN"
python3 fetch.py || exit 2
if (cd data && shasum -a 256 -c --quiet ../inputs.sha256); then
  echo "inputs: identical to the ones pinned in inputs.sha256"
else
  echo "inputs: DIFFER from inputs.sha256 (a source changed since 2026-09-30); numbers will differ from README.md"
fi
python3 selftest.py || { echo "selftest failed: the checks cannot be trusted"; exit 2; }
printf '\n%-18s %-4s' "exit codes" all; printf ' %-6s' $GENES; echo
for check in wt controls plddt agreement; do
  python3 "check_$check.py" > "data/out_$check.txt"
  printf '%-18s %-4s' "check_$check.py" "$?"
  for gene in $GENES; do python3 "check_$check.py" "$gene" > /dev/null; printf ' %-6s' "$?"; done
  echo
done
