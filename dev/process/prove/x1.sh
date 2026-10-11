#!/usr/bin/env bash
# X1 · the first ask: N asks per task (feeds, report), four at a time, each in a fresh repo, as the person.
#
#   dev/process/prove/x1.sh BIN OUT [N]       N asks per task (default 20); FAKE=1 spends nothing
#
# Per ask, under OUT/runs/<task>-sealed-x1-<i>/: ask.out, ask.err, ask.rc, ask.seconds, plan.txt
# (graphene plan --text), record.txt (graphene plan record), log.txt (graphene plan log). Then
# x1_score.py OUT writes OUT/x1.json and prints OUT/x1.md. The planner is Sonnet with a $1.50 cap and
# the isolation flags; two tries, as shipped.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 2 ] || { sed -n '2,10p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2/runs" && cd "$2" && pwd); N=${3:-20}
stamp "x1 start: $BIN, $N asks a task"
for task in feeds report; do for i in $(seq 1 "$N"); do echo "$task $i"; done; done |
  xargs -P 4 -L 1 "$PROVE/x1_one.sh" "$BIN" "$OUT"
stamp "x1 asks done"
python3 "$PROVE/x1_score.py" "$OUT" | tee "$OUT/x1.md"
stamp "x1 scored"
