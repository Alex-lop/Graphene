#!/usr/bin/env bash
# Score one finished feeds repo: accept.py and quality.py (JSON), tally.py (files outside the intent
# globs, churn, cost), the six do-not-touch files against the base commit, and, when OUTDIR holds a
# truth.json, its hand-backs and denials. Writes OUTDIR/accept.json, quality.json, tally.json, score.json.
#
#   dev/process/prove/score.sh REPO BASE RUNLOG ARM OUTDIR      ARM: graphene | prompt
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -eq 5 ] || { sed -n '2,6p' "$0"; exit 2; }
REPO=$1 BASE=$2 RUNLOG=$3 ARM=$4 OUTDIR=$5
T="$TEST/tasks/feeds"
python3 "$T/accept.py" "$REPO" > "$OUTDIR/accept.json" 2> "$OUTDIR/accept.err" || true
python3 "$T/quality.py" "$REPO" > "$OUTDIR/quality.json" 2> "$OUTDIR/quality.err" || true
"$CLONE/.venv/bin/python" "$TEST/tally.py" "$REPO" --base "$BASE" --intent "$T/intent_globs.txt" \
  --accept "$T/accept.py" --quality "$T/quality.py" --arm "$ARM" --runlog "$RUNLOG" \
  > "$OUTDIR/tally.json" 2> "$OUTDIR/tally.err" || true
python3 "$PROVE/score_sum.py" "$REPO" "$BASE" "$OUTDIR" | tee "$OUTDIR/score.json"
