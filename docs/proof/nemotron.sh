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
# configuration), e.g. EXECUTOR='nemotron --model <nano id> --model <super id>'.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=${1:-$HOME/graphene-nemotron}
[ -e "$DIR" ] && { echo "$DIR exists already; name another directory, or delete it first" >&2; exit 1; }
[ -n "${NEBIUS_API_KEY:-}" ] || { echo "NEBIUS_API_KEY is not set: Token Factory needs a key" >&2; exit 1; }
command -v graphene >/dev/null || { echo "graphene is not on PATH" >&2; exit 1; }
unset CLAUDECODE CLAUDE_CODE_SESSION_ID AI_AGENT GRAPHENE_AS   # the person runs this, not an agent
step() { printf '\n\033[1m$ %s\033[0m\n' "$*"; "$@"; }

python3 "$HERE/../test/make_task.py" feeds "$DIR" > /dev/null
cd "$DIR"
step graphene init --planner nemotron --executor "${EXECUTOR:-nemotron}"

step graphene ask "Look at this repo. I want the new Northwind XML feed to load the same way csv and \
json already do: same load command, same JSONL out. Prices in that feed are already in cents. The summary \
line at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch vendored or \
legacy files that aren't ours this week."

# The prune, scripted: cli/main.py leaves every scope (a person would type it), so a leaf that needs it
# comes back with its fix. Then everything proposed is accepted.
EDITOR="sed -i.bak -e 's#, cli/main.py##' -e 's#cli/main.py, ##'" step graphene plan edit
step graphene plan accept

step graphene run --parallel 4

# A leaf that came back offers its fix; take `w` (widen its scope to what it asked for), as a person
# pressing w in `graphene watch` would, and run again.
for id in $(graphene plan --text | sed -n 's/^ *- .*\[\([a-z0-9-]*\)\].*#.*came back.*/\1/p'); do
  step graphene node widen "$id"
done
step graphene run --parallel 4

step git log --graph --oneline
step graphene plan record
