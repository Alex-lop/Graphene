#!/usr/bin/env bash
# One run directory, fresh: the task repo, its base sha, its own TMPDIR, graphene's hooks.
#
#   docs/test/newrun.sh <runs-dir> <task> <style> <arm> <rep>
#
# Its own TMPDIR is the point of the third argument: on 20 September two executors wrote their
# plan JSON to /tmp and a later task read a stale one, so two runs were not independent.
#
# The `graphene` this uses is whatever is first on PATH. Build a wheel from the checkout under
# test and put that venv's bin first, or the run measures whatever working copy is installed.
set -euo pipefail
RUNS=$1; TASK=$2; STYLE=$3; ARM=$4; REP=$5
DIR="$RUNS/$TASK-$STYLE-$ARM-$REP"
[ -e "$DIR" ] && { echo "$DIR exists already; a run is never redone in place" >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$DIR/tmp"
python3 "$HERE/make_task.py" "$TASK" "$DIR/repo" | sed -n 's/^base  //p' > "$DIR/base.sha"
: > "$DIR/runlog.jsonl"
env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT -u GRAPHENE_NODE \
  TMPDIR="$DIR/tmp" GRAPHENE_AS="person:$(id -un)" \
  sh -c "cd '$DIR/repo' && graphene init" > /dev/null
cat <<EOF
run       $DIR
repo      $DIR/repo
base      $(cat "$DIR/base.sha")
runlog    $DIR/runlog.jsonl
TMPDIR    $DIR/tmp
graphene  $(command -v graphene)
version   $(graphene --version 2>&1 | tail -1)
EOF
