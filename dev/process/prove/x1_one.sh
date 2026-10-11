#!/usr/bin/env bash
# One X1 ask, in a fresh newrun.sh repo: x1_one.sh BIN OUT TASK I   (x1.sh runs these four at a time)
set -euo pipefail
. "$(dirname "$0")/common.sh"
use_build "$1"; OUT=$2; task=$3; i=$4
PLANNER="claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model sonnet --max-budget-usd 1.5 $ISO"
EXEC="claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' 'Bash(graphene plan *)' --output-format stream-json --verbose --model sonnet --max-budget-usd 2 $ISO"
RUN="$OUT/runs/$task-sealed-x1-$i"
[ -e "$RUN" ] && { echo "$RUN exists; skipped" >&2; exit 0; }
bash "$TEST/newrun.sh" "$OUT/runs" "$task" sealed x1 "$i" > "$OUT/runs/.newrun-$task-$i.txt" 2>&1 \
  || { echo "newrun failed for $task $i:" >&2; cat "$OUT/runs/.newrun-$task-$i.txt" >&2; exit 1; }
. "$RUN/env.sh"
as_me graphene init --planner "$PLANNER" --executor "$EXEC" > "$RUN/init.txt" 2>&1 || true
printf '%s' "$(cat "$TEST/tasks/$task/paragraph.md")" | log prompt > /dev/null
t0=$(date +%s)
set +e
as_me graphene ask --with "$PLANNER" "$(cat "$TEST/tasks/$task/paragraph.md")" > "$RUN/ask.out" 2> "$RUN/ask.err"
echo $? > "$RUN/ask.rc"
set -e
echo $(( $(date +%s) - t0 )) > "$RUN/ask.seconds"
as_me graphene plan --text > "$RUN/plan.txt" 2>&1 || true
as_me graphene plan record > "$RUN/record.txt" 2>&1 || true
as_me graphene plan log > "$RUN/log.txt" 2>&1 || true
echo "$task $i: exit $(cat "$RUN/ask.rc") in $(cat "$RUN/ask.seconds") s"
