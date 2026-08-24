#!/bin/bash
# One bounded run of the exact CI full-matrix command, with hang forensics.
#
#   .nightwatch/matrix_run.sh <label> <iteration> [extra pytest args...]
#
# Records: start/end, duration, exit code, timed-out flag, and on timeout a
# `sample` stack dump of the pytest process before it is killed. Spends nothing:
# every live-service credential is removed from the subprocess environment.
set -uo pipefail
cd "$(dirname "$0")/../.."
LABEL="${1:?label}"; ITER="${2:?iteration}"; shift 2
HARD_TIMEOUT="${HARD_TIMEOUT:-1500}"
LOGDIR=".nightwatch/logs/$LABEL"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(printf '%03d' "$ITER").log"
META="$LOGDIR/$(printf '%03d' "$ITER").json"
. scripts/reliability/zero_spend_env.sh

start=$(date +%s); started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
uv run --frozen pytest -q \
  tests/unit tests/integration tests/process tests/adversarial \
  --ignore=tests/process/test_mcp_stdio.py "$@" >"$LOG" 2>&1 &
pid=$!
timed_out=0
( sleep "$HARD_TIMEOUT"; kill -0 "$pid" 2>/dev/null && {
    echo "=== HARD TIMEOUT ${HARD_TIMEOUT}s: sampling $pid ===" >>"$LOG"
    /usr/bin/sample "$pid" 8 -f "$LOGDIR/$(printf '%03d' "$ITER").sample.txt" >/dev/null 2>&1
    # SIGABRT makes CPython dump every thread stack via faulthandler if enabled.
    kill -ABRT "$pid" 2>/dev/null; sleep 5; kill -9 "$pid" 2>/dev/null
  } ) & watchdog=$!
wait "$pid"; rc=$?
kill "$watchdog" 2>/dev/null; wait "$watchdog" 2>/dev/null
end=$(date +%s)
grep -q "HARD TIMEOUT" "$LOG" && timed_out=1
summary=$(tail -1 "$LOG" | tr -d '\r')
printf '{"label":"%s","iteration":%s,"started":"%s","duration_s":%s,"exit":%s,"timed_out":%s,"log":"%s","summary":%s}\n' \
  "$LABEL" "$ITER" "$started" "$((end-start))" "$rc" "$timed_out" "$LOG" \
  "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$summary")" | tee "$META"
exit "$rc"
