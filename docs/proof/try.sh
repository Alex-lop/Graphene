#!/usr/bin/env bash
# A repository to try Graphene on, in a place you will recognise: paragraph in, tree out, prune, run.
#
#   docs/proof/try.sh [dir]        (default: ~/graphene-try)
#
# It builds the `feeds` task from the tests (a small loader: csv and json load, the new supplier's XML
# does not yet) as a git repository at <dir>, installs Graphene's hooks there, and prints what to do
# next. Nothing else is touched. Delete <dir> when you are done with it.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=${1:-$HOME/graphene-try}
[ -e "$DIR" ] && { echo "$DIR exists already; name another directory, or delete it first" >&2; exit 1; }
command -v graphene >/dev/null || { echo "graphene is not on PATH: uv tool install git+https://github.com/Alex-lop/Graphene" >&2; exit 1; }
python3 "$HERE/../test/make_task.py" feeds "$DIR" > /dev/null
( cd "$DIR" && env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT graphene init > /dev/null )
cat <<EOF
A repository to try it on: $DIR

1. Two panes. In WezTerm, in a new tab:
     cd $DIR
     wezterm cli split-pane --right --percent 50 --cwd "\$PWD" -- graphene watch
     claude

2. Say this on the left (or anything you want done here, in a paragraph):
     Look at this repo. I want the new Northwind XML feed to load the same way csv and json
     already do: same load command, same JSONL out. Prices in that feed are already in cents. The
     summary line at the end is not a product. A price of 0 means skip it, for every supplier.
     Don't touch vendored or legacy files that aren't ours this week.

3. On the right, the tree appears, every line a proposal (?). Read it. Prune:
     j k move · Enter everything about a node · d drop · e edit its contract in \$EDITOR
     y accept (V and j to select several, then y) · u undo

4. R runs what is ready. A leaf that comes back says why, with its fix: w widen · b sibling.
   ? on it asks the planner. When it is done: git log --graph --oneline
EOF
