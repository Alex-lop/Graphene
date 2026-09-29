#!/usr/bin/env bash
# The Nemotron path, end to end on the feeds task: from nothing to `git log --graph` reading as the
# tree, and the bill. Nemotron 3 Ultra plans, Nemotron executors do the leaves (in Token Factory
# Sandboxes when ConTree is configured, else in local worktrees), and the check decides.
#
#   docs/proof/nemotron.sh [dir]        (default: ~/graphene-nemotron; it must not exist)
#
# Needs: graphene on PATH (for Sandboxes: uv tool install 'graphene-map[sandbox]'), NEBIUS_API_KEY in
# the environment, and for Sandboxes NEBIUS_PROJECT_ID. Spends real tokens at Token Factory's list
# price; the bill is the last thing it prints. EXECUTOR overrides the executor spec (the frozen
# configuration), e.g. EXECUTOR='nemotron --model <nano id> --model <super id>'. MAKE_REPO, PARAGRAPH and
# PRUNE replace the feeds task, its paragraph and its scripted prune (the tests run it on a tiny repo).
# RECORD=<file> records the plan's store over the whole run, for `graphene demo <file>` to replay.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=${1:-$HOME/graphene-nemotron}
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

${MAKE_REPO:-python3 $HERE/../test/make_task.py feeds} "$DIR" > /dev/null
cd "$DIR"
if [ -n "${RECORD:-}" ]; then   # it waits for the store `graphene init` makes, and stops when this ends
  graphene demo --record "$RECORD" & recorder=$!
  trap 'kill -TERM $recorder; wait $recorder' EXIT
fi
step graphene init --planner nemotron --executor "${EXECUTOR:-nemotron}"

step graphene ask "${PARAGRAPH:-Look at this repo. I want the new Northwind XML feed to load the same way \
csv and json already do: same load command, same JSONL out. Prices in that feed are already in cents. The \
summary line at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch \
vendored or legacy files that aren't ours this week.}"

# The board, scripted: each line of BOARD is the `graphene board` command a person's one key runs on an
# item in `graphene watch` (y takes its default, 1-9 picks an option). Unset, the board stays as asked.
while read -r answer; do [ -z "$answer" ] || step graphene board $answer; done <<< "${BOARD:-}"

# The prune, scripted: cli/main.py leaves every scope (a person would type it), so a leaf that needs it
# comes back with its fix. Then everything proposed is accepted.
EDITOR="${PRUNE:-sed -i.bak -e 's#, cli/main.py##' -e 's#cli/main.py, ##'}" step graphene plan edit
step graphene plan accept

step graphene run --parallel 4

# A leaf that came back offers its fix; take `w` (widen its scope to what it asked for), as a person
# pressing w in `graphene watch` would, and run again. A leaf whose check kept failing asked for no
# path: there is nothing to widen, and it stays open for a person to read.
came_back() {  # the ids whose note in the plan's text says they came back (a note follows its node's line)
  graphene plan --text | awk '/\[[a-z0-9-]+\]/ { match($0, /\[[a-z0-9-]+\]/); id = substr($0, RSTART + 1, RLENGTH - 2) }
                              /^ *# came back/ { print id }'
}
widened=
for id in $(came_back); do
  if step graphene node widen "$id"; then widened=1; else echo "($id asked for no path outside its scope)"; fi
done
if [ -n "$widened" ]; then   # with nothing widened, a second run has nothing new to run
  step graphene run --parallel 4
fi

step git log --graph --oneline
step graphene plan record
