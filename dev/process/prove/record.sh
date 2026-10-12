#!/usr/bin/env bash
# A real recording for `graphene demo`: one feeds run on one build, recorded as it happens, then replayed once and
# checked for leaks, so the README's first command can show a run that happened rather than a scripted stand-in.
#
#   dev/process/prove/record.sh BIN OUT [MODEL]      MODEL default sonnet; FAKE=1 spends nothing
#
# Under OUT/: the fresh feeds repo (newrun.sh), demo.jsonl (what `graphene demo --record` wrote while the person
# asked, accepted and ran), replay.txt (`graphene demo demo.jsonl --once`), leaks.txt (demo.leaks on the file:
# every count must be 0), and the run's own outputs. The recorder is the person's `graphene demo --record`, stopped
# with SIGINT once the run has ended, as a person's Ctrl-C would.
. "$(dirname "$0")/common.sh"
[ $# -ge 2 ] || { sed -n '2,10p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2/runs" && cd "$2" && pwd); MODEL=${3:-sonnet}
PLANNER="claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model $MODEL --max-budget-usd 3 $ISO"
WITH=$("$TOOLPY" -c 'from graphene_map.run import DEFAULT_WITH; print(DEFAULT_WITH)')
for flag in "--model $MODEL" "--strict-mcp-config" "--setting-sources project,local"; do
  case " $WITH " in *" ${flag%% *} "*) ;; *) WITH="$WITH $flag" ;; esac
done
stamp "record start: $BIN, $MODEL"
bash "$TEST/newrun.sh" "$OUT/runs" feeds sealed record 1 > "$OUT/runs/.newrun.txt" 2>&1
RUN="$OUT/runs/feeds-sealed-record-1"
(
  . "$RUN/env.sh"
  as_me graphene init --planner "$PLANNER" --executor "$WITH" > "$OUT/init.txt" 2>&1 || true
  as_me graphene demo --record "$OUT/demo.jsonl" > "$OUT/recorder.txt" 2>&1 &
  REC=$!
  sleep 2
  as_me graphene ask "$(cat "$TEST/tasks/feeds/paragraph.md")" > "$OUT/ask.txt" 2>&1 || true
  as_me graphene plan accept > "$OUT/accept.txt" 2>&1 || true
  as_me graphene run --parallel 2 > "$OUT/run.txt" 2>&1 || true
  as_me graphene plan record > "$OUT/record.txt" 2>&1 || true
  sleep 3
  # the recorder is the grandchild (as_me is a function in a subshell): the INT goes to its children, as a
  # person's Ctrl-C reaches the foreground process group; bounded, so a recorder that ignores it cannot hang this
  pkill -INT -P "$REC" 2>/dev/null || kill -INT "$REC" 2>/dev/null || true
  for _ in $(seq 60); do kill -0 "$REC" 2>/dev/null || break; sleep 0.5; done
  pkill -TERM -P "$REC" 2>/dev/null || true
  wait "$REC" 2>/dev/null || true
)
graphene demo "$OUT/demo.jsonl" --once > "$OUT/replay.txt" 2>&1 || true
"$TOOLPY" - "$OUT/demo.jsonl" > "$OUT/leaks.txt" <<'PY'
import sys
from graphene_map import demo
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
counts = demo.leaks(text)
for k, v in counts.items():
    print(f"{k}: {v}")
print("rows:", sum(1 for line in text.splitlines() if line.strip()))
print("clean" if not any(counts.values()) else "LEAKS")
PY
stamp "record done"
cat "$OUT/leaks.txt"; tail -3 "$OUT/replay.txt"; tail -2 "$OUT/run.txt"
