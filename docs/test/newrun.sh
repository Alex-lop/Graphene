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
#
# It also writes <run>/env.sh, which every shell in the run sources first (23 September): a shell
# function defined in one Bash call is gone in the next, and on 21 September a stand-in that did
# not re-export PATH ran part of its run on the wrong build. The file pins that build's bin first.
set -euo pipefail
RUNS=$1; TASK=$2; STYLE=$3; ARM=$4; REP=$5
DIR="$RUNS/$TASK-$STYLE-$ARM-$REP"
[ -e "$DIR" ] && { echo "$DIR exists already; a run is never redone in place" >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=$(dirname "$(command -v graphene)")
mkdir -p "$DIR/tmp"
python3 "$HERE/make_task.py" "$TASK" "$DIR/repo" | sed -n 's/^base  //p' > "$DIR/base.sha"
: > "$DIR/runlog.jsonl"
UNMARK="-u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_ENTRYPOINT -u AI_AGENT -u GRAPHENE_NODE -u GRAPHENE_PLANNER"
env $UNMARK TMPDIR="$DIR/tmp" GRAPHENE_AS="person:$(id -un)" \
  sh -c "cd '$DIR/repo' && graphene init" > /dev/null
cat > "$DIR/env.sh" <<EOF
# source this first in every shell of the run
export PATH="$BIN:\$PATH"
export TMPDIR="$DIR/tmp"
cd "$DIR/repo"
R="$DIR/runlog.jsonl"
BASE=$(cat "$DIR/base.sha")
# a command run as the person: none of the marks an agent's shell carries
as_me() { env $UNMARK GRAPHENE_AS="person:\$(id -un)" "\$@"; }
# log something the person did; the text on standard input when it has quotes or newlines in it
log() { python3 "$HERE/logline.py" "\$R" person "\$@"; }
# run a command as typed, log that whole line as the act (did edit "as_me graphene node set …"),
# and what it printed as read
did() {
  local kind=\$1 rc; shift
  printf '%s' "\$*" | log "\$kind" > /dev/null || { echo "not run: it could not be logged" >&2; return 2; }
  eval "\$*" > "\$TMPDIR/.did" 2>&1; rc=\$?; cat "\$TMPDIR/.did"
  [ -s "\$TMPDIR/.did" ] && log read < "\$TMPDIR/.did" > /dev/null; return \$rc
}
# show what a command prints, and log it as read
seen() { "\$@" > "\$TMPDIR/.seen" 2>&1; cat "\$TMPDIR/.seen"; log read < "\$TMPDIR/.seen" > /dev/null; }
# what an executor said back, out of its JSON, logged as read
reply() { seen python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("result") or "")' "\$1"; }
# the working tree as a commit under refs/snap/, with HEAD and the index left alone: tally.py --traps
# reads from these when a trap first showed in the diff. \`snaps &\` takes one a minute (kill %1 stops it)
snap() {
  local i="$DIR/tmp/.snap-index" t c
  rm -f "\$i"
  GIT_INDEX_FILE="\$i" git -C "$DIR/repo" add -A && t=\$(GIT_INDEX_FILE="\$i" git -C "$DIR/repo" write-tree) || return
  [ "\$t" = "\$(cat "$DIR/tmp/.snap-tree" 2>/dev/null)" ] && return 0
  c=\$(git -C "$DIR/repo" -c user.name=snap -c user.email=snap@localhost commit-tree "\$t" -p HEAD -m snap) || return
  git -C "$DIR/repo" update-ref "refs/snap/\$(date +%s)" "\$c" && echo "\$t" > "$DIR/tmp/.snap-tree"
}
snaps() { while :; do snap; sleep 60; done; }
EOF
cat <<EOF
run       $DIR
repo      $DIR/repo
base      $(cat "$DIR/base.sha")
runlog    $DIR/runlog.jsonl
TMPDIR    $DIR/tmp
env       $DIR/env.sh
graphene  $(command -v graphene)
version   $(graphene --version 2>&1 | tail -1)
EOF
