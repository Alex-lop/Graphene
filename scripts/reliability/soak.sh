#!/bin/bash
# Credential-free demo soak. One NDJSON record per run on stdout.
#
#   .nightwatch/soak.sh <mode> <iterations>
#     modes: fixture | adk-fake | replay | taskmaster
#
# Every run gets a fresh disposable state directory, a hard timeout, and its own
# private runtime which --cleanup removes. Spends nothing: provider credentials
# are stripped from the subprocess environment. Records exit status, duration,
# the declared semantic invariants (never the run ids, SHAs or timestamps that
# are designed to differ), the repository's changed-path set, and whether the
# run leaked a runtime directory or a child process.
set -uo pipefail
cd "$(dirname "$0")/../.."
MODE="${1:?mode}"; ITERS="${2:?iterations}"
HARD_TIMEOUT="${HARD_TIMEOUT:-300}"
OUT=".nightwatch/logs/soak-$MODE"; mkdir -p "$OUT"
. scripts/reliability/zero_spend_env.sh

case "$MODE" in
  fixture)    ARGS=(demo --driver scripted-local --automated-fixture --no-open --exit-after-demo --cleanup)
              WANT=("DEMO COMPLETE — committed lineage verified" "Promotion state: PROMOTED" "Outcome: local_isolated_commit" "passed=true") ;;
  adk-fake)   ARGS=(demo --driver adk-fake --automated-fixture --no-open --exit-after-demo --cleanup)
              WANT=("DEMO COMPLETE — committed lineage verified" "Promotion state: PROMOTED" "Outcome: local_isolated_commit" "passed=true") ;;
  replay)     ARGS=(demo --driver verified-replay --no-open --exit-after-demo)
              WANT=("No authoritative state was created.") ;;
  taskmaster) ARGS=(mission replay taskmaster --no-open --exit-after-replay)
              WANT=("Mission Control:") ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac

demo_dirs() { ls -d "${TMPDIR%/}"/graphene-demo-* 2>/dev/null | wc -l | tr -d ' '; }

for i in $(seq 1 "$ITERS"); do
  N=$(printf '%03d' "$i"); LOG="$OUT/$N.log"
  state=$(mktemp -d "/private/tmp/graphene-soak-$MODE.XXXXXX")
  before_dirs=$(demo_dirs); before_paths=$(git status --porcelain=v1 | sort | md5)
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ); s=$(date +%s)
  GRAPHENE_STATE_DIR="$state/state" \
    perl -e 'alarm shift; exec @ARGV' "$HARD_TIMEOUT" \
    uv run --frozen graphene "${ARGS[@]}" >"$LOG" 2>&1
  rc=$?; d=$(( $(date +%s) - s ))
  [ "$rc" = 142 ] && to=1 || to=0     # perl alarm -> SIGALRM
  missing=""
  for w in "${WANT[@]}"; do grep -qF "$w" "$LOG" || missing="$missing|$w"; done
  after_paths=$(git status --porcelain=v1 | sort | md5)
  [ "$before_paths" = "$after_paths" ] && clean=1 || clean=0
  orphan_dirs=$(( $(demo_dirs) - before_dirs ))
  orphan_procs=$(pgrep -P $$ 2>/dev/null | wc -l | tr -d ' ')
  rm -rf "$state"
  python3 -c '
import json,sys
print(json.dumps({"mode":sys.argv[1],"iteration":int(sys.argv[2]),"started":sys.argv[3],
 "duration_s":int(sys.argv[4]),"exit":int(sys.argv[5]),"timed_out":bool(int(sys.argv[6])),
 "invariants_ok":sys.argv[7]=="","missing_invariants":[x for x in sys.argv[7].split("|") if x],
 "repo_unchanged":bool(int(sys.argv[8])),"orphan_runtime_dirs":int(sys.argv[9]),
 "orphan_child_procs":int(sys.argv[10]),"log":sys.argv[11]}))' \
    "$MODE" "$i" "$started" "$d" "$rc" "$to" "$missing" "$clean" "$orphan_dirs" "$orphan_procs" "$LOG" \
    | tee -a "$OUT/records.ndjson"
  if [ "$rc" != 0 ] || [ -n "$missing" ] || [ "$clean" != 1 ]; then
    echo "SOAK FAILURE at $MODE/$i — preserved, consecutive count reset" ; exit 9
  fi
done
