#!/bin/bash
# One bounded run of the targeted SQLite/concurrency selection, with forensics.
#   targeted_run.sh <label> <iteration>
# Same forensics as matrix_run.sh: on hard timeout, `sample` the process, then
# SIGABRT so faulthandler dumps every thread, then SIGKILL.
set -uo pipefail
cd "$(dirname "$0")/../.."
LABEL="${1:?label}"; ITER="${2:?iteration}"
HARD_TIMEOUT="${HARD_TIMEOUT:-420}"
SEL="${SEL:-tests/unit/orchestration/test_runner.py tests/unit/orchestration/test_store.py tests/unit/orchestration/test_process_control.py tests/process/test_mission_cli.py}"
LOGDIR=".nightwatch/logs/$LABEL"; mkdir -p "$LOGDIR"
N=$(printf '%03d' "$ITER"); LOG="$LOGDIR/$N.log"; META="$LOGDIR/$N.json"
. scripts/reliability/zero_spend_env.sh
load1=$(/usr/bin/uptime | sed -E 's/.*averages?: ([0-9.]+).*/\1/' | tr -d ' ')
concurrent=$(pgrep -f "bin/pytest -q tests/unit tests/integration" 2>/dev/null | wc -l | tr -d ' ')
start=$(date +%s); started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
uv run --frozen pytest -q $SEL >"$LOG" 2>&1 &
pid=$!
( sleep "$HARD_TIMEOUT"; kill -0 "$pid" 2>/dev/null && {
    echo "=== HARD TIMEOUT ${HARD_TIMEOUT}s: sampling $pid ===" >>"$LOG"
    /usr/bin/sample "$pid" 8 -f "$LOGDIR/$N.sample.txt" >/dev/null 2>&1
    ps -M "$pid" >>"$LOG" 2>&1
    kill -ABRT "$pid" 2>/dev/null; sleep 5; kill -9 "$pid" 2>/dev/null
  } ) & watchdog=$!
wait "$pid"; rc=$?
kill "$watchdog" 2>/dev/null; wait "$watchdog" 2>/dev/null
end=$(date +%s); timed_out=0; grep -q "HARD TIMEOUT" "$LOG" && timed_out=1
printf '{"label":"%s","iteration":%s,"started":"%s","load1":%s,"concurrent_matrices":%s,"duration_s":%s,"exit":%s,"timed_out":%s,"summary":%s}\n' \
  "$LABEL" "$ITER" "$started" "$load1" "$concurrent" "$((end-start))" "$rc" "$timed_out" \
  "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$(tail -1 "$LOG" | tr -d '\r')")" | tee "$META"
exit "$rc"
