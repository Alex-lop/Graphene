#!/usr/bin/env bash
# X2 · the price of the contract, arm (a): feeds through Graphene on one build, each run planted.
#
#   dev/process/prove/x2.sh BIN OUT [REPS]      REPS default 3; FAKE=1 spends nothing
#
# Per run, under OUT/runs/feeds-sealed-x2-<i>/: init.txt, ask.out/err/rc, accept.txt, run1.txt (the
# main run, --parallel 3), then plant.sh's plant.txt/run2.txt/run3.txt, truth.json (truth.py),
# score.json (score.sh) and seconds.txt (the main round's and the plant round's wall clock). The
# planner is X1's; the executor is this build's own DEFAULT_WITH plus Sonnet, a $2 cap and the
# isolation flags where it lacks them (OUT/executor.txt says what ran). x2_table.py OUT ends it.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 2 ] || { sed -n '2,11p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2/runs" && cd "$2" && pwd); REPS=${3:-3}
PLANNER="claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model sonnet --max-budget-usd 1.5 $ISO"
WITH=$("$TOOLPY" -c 'from graphene_map.run import DEFAULT_WITH; print(DEFAULT_WITH)')
for flag in "--model sonnet" "--max-budget-usd 2" "--strict-mcp-config" "--setting-sources project,local"; do
  case " $WITH " in *" ${flag%% *} "*) ;; *) WITH="$WITH $flag" ;; esac
done
echo "executor: $WITH" | tee "$OUT/executor.txt"
for i in $(seq 1 "$REPS"); do
  RUN="$OUT/runs/feeds-sealed-x2-$i"
  [ -e "$RUN" ] && { echo "$RUN exists; skipped"; continue; }
  stamp "x2 run $i start"
  bash "$TEST/newrun.sh" "$OUT/runs" feeds sealed x2 "$i" > "$OUT/runs/.newrun-x2-$i.txt" 2>&1
  (
    . "$RUN/env.sh"
    as_me graphene init --planner "$PLANNER" --executor "$WITH" > "$RUN/init.txt" 2>&1 || true
    printf '%s' "$(cat "$TEST/tasks/feeds/paragraph.md")" | log prompt > /dev/null
    t0=$(date +%s)
    set +e
    as_me graphene ask --with "$PLANNER" "$(cat "$TEST/tasks/feeds/paragraph.md")" > "$RUN/ask.out" 2> "$RUN/ask.err"
    echo $? > "$RUN/ask.rc"
    set -e
    log read < "$RUN/ask.out" > /dev/null
    printf 'as_me graphene plan accept' | log accept > /dev/null
    as_me graphene plan accept > "$RUN/accept.txt" 2>&1 || true
    printf 'as_me graphene run --parallel 3' | log run > /dev/null
    as_me graphene run --parallel 3 > "$RUN/run1.txt" 2>&1 || true
    echo "main $(( $(date +%s) - t0 ))" >> "$RUN/seconds.txt"
  )
  "$PROVE/plant.sh" "$RUN"
  "$TOOLPY" "$PROVE/check_rows.py" "$RUN/repo" > "$RUN/checks.txt" 2>&1 || true
  python3 "$PROVE/truth.py" "$RUN" > "$RUN/truth.json"
  "$PROVE/score.sh" "$RUN/repo" "$(cat "$RUN/base.sha")" "$RUN/runlog.jsonl" graphene "$RUN" > /dev/null
  stamp "x2 run $i done"
done
python3 "$PROVE/x2_table.py" "$OUT" | tee "$OUT/x2.md"
