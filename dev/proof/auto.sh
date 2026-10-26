#!/usr/bin/env bash
# Auto mode on the Nemotron path, end to end: one goal in, tested commits out. Nemotron 3 Ultra plans the
# goal as tasks that can run at once, three Nemotron 3 Nano agents race each task in its own copy, the rule
# keeps one fork a task, what passes lands, then the goal's own check (the whole test suite) runs; when it is
# red, Ultra plans the fix and the race goes again, inside the envelope the flags set.
#
#   dev/proof/auto.sh [dir]        (default: ~/graphene-auto; it must not exist)
#
# Needs: graphene on PATH with the Nemotron extra, NEBIUS_API_KEY in the environment. Spends real tokens at
# Token Factory's list price, at most BUDGET dollars (2 unset) by the envelope; the bill is the last thing it
# prints. PLANNER and EXECUTOR override the specs; MAKE_REPO and GOAL replace wordkit and its goal; FORKS,
# ROUNDS and CHECK the envelope's forks, fix rounds and the goal's check. RECORD=<file> records the plan's
# store over the whole run, for `graphene demo <file>` to replay (tests/test_demo_auto.py makes the one
# `graphene demo --auto` ships this way, against a scripted stand-in).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=${1:-$HOME/graphene-auto}
[ -e "$DIR" ] && { echo "$DIR exists already; name another directory, or delete it first" >&2; exit 1; }
[ -n "${NEBIUS_API_KEY:-}" ] || { echo "NEBIUS_API_KEY is not set: Token Factory needs a key" >&2; exit 1; }
command -v graphene >/dev/null || { echo "graphene is not on PATH" >&2; exit 1; }
# spending is the person's: an agent's shell runs this on Token Factory only when the person opened it
if [ -z "${GRAPHENE_TOKENFACTORY_URL:-}" ] && [ -z "${GRAPHENE_AGENT_LIVE_USD:-}" ]; then
  for mark in CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT CODEX_SESSION_ID CODEX_SANDBOX \
              AI_AGENT GEMINI_CLI CURSOR_AGENT; do
    [ -n "${!mark:-}" ] && { echo "refused: this spends on the person's key, and this shell carries an agent's mark ($mark) with no GRAPHENE_AGENT_LIVE_USD: nothing was sent" >&2; exit 1; }
  done
fi
unset CLAUDECODE CLAUDE_CODE_SESSION_ID AI_AGENT GRAPHENE_AS   # the person runs this, not an agent
step() { printf '\n\033[1m$ %s\033[0m\n' "$*"; "$@"; }
case ${RECORD:-} in ''|/*) ;; *) RECORD=$PWD/$RECORD ;; esac   # from where this was started

${MAKE_REPO:-python3 $HERE/make_wordkit.py} "$DIR" > /dev/null
cd "$DIR"
if [ -n "${RECORD:-}" ]; then   # it waits for the store `graphene init` makes, and stops when this ends
  graphene demo --record "$RECORD" & recorder=$!
  trap 'kill -TERM $recorder; wait $recorder' EXIT
fi
step graphene init --planner "${PLANNER:-nemotron}" --executor "${EXECUTOR:-nemotron}"

step graphene auto "${GOAL:-wordkit grows three things at once: a --top N option on the CLI that prints the N \
most common words with their counts; a reading time in whole minutes, rounded up, at 200 words a minute; and \
hyphenated words like well-known counted as one word.}" \
  --budget "${BUDGET:-2}" --forks "${FORKS:-3}" --rounds "${ROUNDS:-2}" --parallel 4 \
  --check "${CHECK:-python3 -m unittest}"

step git log --graph --oneline
step graphene plan record
