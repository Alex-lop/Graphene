#!/usr/bin/env bash
# X6 · three README-order walks on one build, as the person, in the shape of the loop night's thirty.md:
# the replay's last lines, a fresh report repo, init, ask, plan, accept, run, node show, plan record.
#
#   dev/process/prove/walks.sh BIN OUT [REPS]      REPS default 3; FAKE=1 spends nothing
#
# Per walk: OUT/walk-<i>.txt (every command with what it printed, timestamps), OUT/runs/report-sealed-walk-<i>/
# (the repo). Then deadends.py counts the refusals and dead ends by regex and the minutes to the first
# landed leaf, into OUT/walks.json.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 2 ] || { sed -n '2,10p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2/runs" && cd "$2" && pwd); REPS=${3:-3}
PLANNER="claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model sonnet --max-budget-usd 1.5 $ISO"
WITH=$("$TOOLPY" -c 'from graphene_map.run import DEFAULT_WITH; print(DEFAULT_WITH)')
for flag in "--model sonnet" "--max-budget-usd 2" "--strict-mcp-config" "--setting-sources project,local"; do
  case " $WITH " in *" ${flag%% *} "*) ;; *) WITH="$WITH $flag" ;; esac
done
for i in $(seq 1 "$REPS"); do
  W="$OUT/walk-$i.txt"; RUN="$OUT/runs/report-sealed-walk-$i"
  [ -e "$RUN" ] && { echo "$RUN exists; skipped"; continue; }
  stamp "walk $i start"
  step() { echo "\$ $*" >> "$W"; { eval "$*"; } >> "$W" 2>&1 || echo "exit=$?" >> "$W"; }
  echo "started at $(now) on $BIN" > "$W"
  date +%s > "$OUT/walk-$i.t0"
  step 'me graphene --version'
  step 'me graphene demo --once | tail -3'
  bash "$TEST/newrun.sh" "$OUT/runs" report sealed walk "$i" >> "$W" 2>&1
  (
    . "$RUN/env.sh"
    step 'as_me graphene init --planner "$PLANNER" --executor "$WITH"'
    step 'as_me graphene ask --with "$PLANNER" "$(cat "$TEST/tasks/report/paragraph.md")"'
    step 'as_me graphene plan'
    step 'as_me graphene plan accept'
    step 'as_me graphene run --parallel 2'
    first=$(sed -n 's/^proposed \([^:]*\):.*/\1/p' "$W" | head -1)
    step "as_me graphene node show ${first:-nothing}"
    step 'as_me graphene plan record'
    step 'git log --merges --format="%h %s"'
  )
  echo "ended at $(now)" >> "$W"
  stamp "walk $i done"
done
python3 "$PROVE/deadends.py" --walks "$OUT" | tee "$OUT/walks.md"
