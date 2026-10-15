#!/usr/bin/env bash
# The held bench, one run: one arm on one task, one seed (rules.md). Run it under `uv run` from the clone,
# so python3 is the one that imports graphene_map, and graphene is the build on the PATH.
#
#   dev/held/run.sh ARM TASK SEED OUT      ARM: P, P+ or G; TASK: a directory of dev/held/tasks/
#
# FAKE=1 puts dev/process/prove/fake/claude first on the PATH and spends nothing. Live, it spends Claude
# Code on the person's login: it refuses to start until they set GRAPHENE_AGENT_LIVE_USD, and prints the
# ceiling rules.md sets. Under OUT/<task>-<arm>-<seed>/: repo/, base.sha, the arm's own output (ledger.py
# reads its cost), said.txt (the session's result, or `graphene run`'s output), rc, seconds, score.json.
set -euo pipefail
HELD=$(cd "$(dirname "$0")" && pwd)
. "$HELD/../process/prove/common.sh"
[ $# -eq 4 ] || { sed -n '2,10p' "$0"; exit 2; }
ARM=$1 TASK=$2 SEED=$3
case "$ARM" in P | P+ | G) ;; *) echo "ARM is P, P+ or G, not $ARM" >&2; exit 2 ;; esac
[ -f "$HELD/tasks/$TASK/prompt.md" ] || { echo "no task $TASK in $HELD/tasks" >&2; exit 2; }
CEILING=$(grep -o 'Ceiling \$[0-9]*' "$HELD/rules.md")
if [ "${FAKE:-}" = 1 ]; then
  export PATH="$PROVE/fake:$PATH"
elif [ -z "${GRAPHENE_AGENT_LIVE_USD:-}" ]; then
  echo "A live run spends Claude Code on your login. rules.md: $CEILING. Set GRAPHENE_AGENT_LIVE_USD to open it." >&2
  exit 2
fi
MODEL=claude-sonnet-5-5  # the one pinned id, frozen with the tag: a run on another model is void (rules.md)
CAP=3                    # dollars, on every session's command line
echo "held: $ARM on $TASK, seed $SEED, $MODEL, \$$CAP a session; rules.md: $CEILING${FAKE:+ (FAKE=1: \$0)}"
RUN="$4/$TASK-$ARM-$SEED"
[ -e "$RUN" ] && { echo "$RUN exists; a seed runs once" >&2; exit 2; }
mkdir -p "$RUN/tmp" && RUN=$(cd "$RUN" && pwd)
cp -R "$HELD/tasks/$TASK/base" "$RUN/repo"
git -C "$RUN/repo" init -q
git -C "$RUN/repo" add -A
git -C "$RUN/repo" commit -q --no-verify -m base
git -C "$RUN/repo" rev-parse HEAD > "$RUN/base.sha"
PROMPT=$(cat "$HELD/tasks/$TASK/prompt.md")  # the same for every arm
DENY=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from scripted import DENY; print(",".join(DENY[sys.argv[2]]))' "$HELD" "$TASK")

t0=$(date +%s)
set +e
cd "$RUN/repo"
export TMPDIR="$RUN/tmp"
if [ "$ARM" = G ]; then
  # run.py's DEFAULT_WITH, with the pinned model, the cap and the isolation flags of common.sh
  PLANNER="claude -p --tools Read,Grep,Glob --output-format stream-json --verbose --model $MODEL --max-budget-usd 1.5 $ISO"
  WITH="claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' 'Bash(graphene plan *)' --output-format stream-json --verbose --model $MODEL --max-budget-usd $CAP $ISO"
  {
    me graphene init --planner "$PLANNER" --executor "$WITH"
    if [ -n "$DENY" ]; then
      printf 'protected: %s\n' "$DENY" > "$RUN/settings.txt"
      me env EDITOR="cp $RUN/settings.txt" graphene config edit
    fi
    me graphene ask --with "$PLANNER" "$PROMPT"
    me graphene plan accept
  } > "$RUN/setup.txt" 2>&1
  me graphene run --parallel 3 > "$RUN/said.txt" 2>&1
  echo $? > "$RUN/rc"
else
  if [ "$ARM" = P+ ]; then  # Claude Code's Edit rules cover every tool that edits a file
    python3 - "$DENY" > /dev/null <<'PY'
import json, pathlib, sys
deny = [f"Edit({glob})" for glob in sys.argv[1].split(",") if glob]
pathlib.Path(".claude").mkdir(exist_ok=True)
pathlib.Path(".claude/settings.json").write_text(json.dumps({"permissions": {"deny": deny}}, indent=2) + "\n")
PY
  fi
  plain_claude -p "$PROMPT" --model "$MODEL" --permission-mode acceptEdits --output-format json \
    --max-budget-usd "$CAP" $ISO --allowedTools Read Edit Write Glob Grep 'Bash(python3 *)' 'Bash(git *)' \
    'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)' > "$RUN/session.json" 2> "$RUN/session.err"
  echo $? > "$RUN/rc"
  json_field "$RUN/session.json" result > "$RUN/said.txt"
fi
set -e
echo $(($(date +%s) - t0)) > "$RUN/seconds"
python3 "$HELD/score.py" "$TASK" "$RUN/repo" "$(cat "$RUN/base.sha")" "$ARM" "$RUN/said.txt" | tee "$RUN/score.json"
