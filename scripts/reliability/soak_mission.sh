#!/bin/bash
# Credential-free mission soak: the only $0 command that drives the runner,
# scheduler, SQLiteMissionStore, SQLiteAttemptEvidenceStore, real sandbox-exec
# check subprocesses and _execute_scripted_batch's ThreadPoolExecutor at once.
#
#   .nightwatch/soak_mission.sh <ordinary|fault> <iterations>
#
# Each run: a fresh disposable git repository, an isolated GRAPHENE_STATE_DIR,
# the fixture's exact frozen goal, a hard timeout, and a store verification
# afterwards. One NDJSON record per run. A failure stops the loop and is kept.
set -uo pipefail
cd "$(dirname "$0")/../.."
MODE="${1:?ordinary|fault}"; ITERS="${2:?iterations}"
HARD_TIMEOUT="${HARD_TIMEOUT:-180}"
GOAL="Add redacted JSON and Markdown status reports to the fixture CLI."
OUT=".nightwatch/logs/soak-mission-$MODE"; mkdir -p "$OUT"
. scripts/reliability/zero_spend_env.sh
FAULT=(); [ "$MODE" = fault ] && FAULT=(--inject-check-fault)
bounded() { perl -e 'alarm shift; exec @ARGV' "$HARD_TIMEOUT" "$@"; }

for i in $(seq 1 "$ITERS"); do
  N=$(printf '%03d' "$i"); LOG="$OUT/$N.log"
  # /private/tmp, not /tmp: the store refuses a state path containing symlinks.
  D=$(mktemp -d "/private/tmp/graphene-mission-$MODE.XXXXXX")
  export GRAPHENE_STATE_DIR="$D/state"
  mkdir -p "$D/repo"; git -C "$D/repo" init -q
  printf 'fixture\n' > "$D/repo/README.md"
  git -C "$D/repo" add -A
  git -C "$D/repo" -c user.email=soak@graphene.invalid -c user.name=soak commit -qm init
  bounded uv run --frozen graphene init --repo "$D/repo" >>"$LOG" 2>&1
  git -C "$D/repo" add -A
  git -C "$D/repo" -c user.email=soak@graphene.invalid -c user.name=soak commit -qm policy
  before_procs=$(pgrep -f "graphene-mission-$MODE" 2>/dev/null | wc -l | tr -d ' ')
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ); s=$(date +%s)
  bounded uv run --frozen graphene --json mission start --repo "$D/repo" \
      --goal "$GOAL" --driver scripted-local --auto-approve ${FAULT[@]+"${FAULT[@]}"} \
      --max-workers 2 >"$D/start.json" 2>>"$LOG"
  rc=$?; d=$(( $(date +%s) - s ))
  cat "$D/start.json" >>"$LOG"
  bounded uv run --frozen graphene --json mission db verify >"$D/verify.json" 2>>"$LOG"
  vrc=$?
  MID=$(uv run --frozen python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("mission_id",""))' "$D/start.json" 2>/dev/null)
  bounded uv run --frozen graphene --json mission status "$MID" >"$D/status.json" 2>>"$LOG" || true
  after_procs=$(pgrep -f "graphene-mission-$MODE" 2>/dev/null | wc -l | tr -d ' ')
  repo_dirty=$(git status --porcelain=v1 | grep -cv nightwatch || true)
  uv run --frozen python scripts/reliability/soak_record.py "$MODE" "$i" "$started" "$d" "$rc" "$vrc" \
      "$D/start.json" "$D/verify.json" "$D/status.json" "$LOG" \
      "$((after_procs-before_procs))" "$repo_dirty" | tee -a "$OUT/records.ndjson"
  ok=$(tail -1 "$OUT/records.ndjson" | uv run --frozen python -c 'import json,sys; print(json.load(sys.stdin)["ok"])')
  if [ "$ok" != "True" ]; then
    echo "SOAK FAILURE at mission-$MODE/$i — evidence kept at $D and $LOG"; exit 9
  fi
  rm -rf "$D"
done
echo "mission-$MODE: $ITERS/$ITERS consecutive"
