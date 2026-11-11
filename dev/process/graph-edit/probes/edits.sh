#!/bin/bash
# What does `graphene node set` do to a task in each state? A fixture repo under /tmp, a person and an agent
# told apart by their environment, and each edit's own answer. `uv sync` first; it writes nothing in this repo.
#   bash dev/process/graph-edit/probes/edits.sh
set -u
G=$(cd "$(dirname "$0")/../../../.." && pwd)
BIN=$G/.venv/bin
D=$(mktemp -d /tmp/gp-XXXX)/wk
Z=$(mktemp -d /tmp/gp-z-XXXX)
BASE="env -i HOME=$HOME PATH=$BIN:/usr/bin:/bin:/opt/homebrew/bin USER=alex ZDOTDIR=$Z NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off GRAPHENE_TOKENFACTORY_URL=http://127.0.0.1:9"
me() { (cd "$D" && $BASE graphene "$@" 2>&1); }
agent() { (cd "$D" && $BASE CLAUDECODE=1 CLAUDE_CODE_SESSION_ID=probe-sess-1 graphene "$@" 2>&1); }
say() { printf '\n--- %s\n' "$*"; }

python3 $G/dev/proof/make_wordkit.py "$D" >/dev/null
cd "$D" || exit 1
say init; me init --planner claude --executor claude | tail -3
say "add n1 (person)"; me node add --scope wordkit/clean.py --check "python3 -m unittest -q" -- "tidy clean"
say "add by agent (suggested)"; agent node add --scope wordkit/count.py --check "python3 -m unittest -q" -- "count faster"
say "plan --json"; me plan --json | head -40
say "state --json tasks"; me state --json | python3 -c "import json,sys; s=json.load(sys.stdin); [print(t['id'], t['state'], t.get('forks')) for t in s['tasks']]"

edits() { # every field, on task $1
  say "[$2] title";   me node set "$1" --title "$2 title"
  say "[$2] files";   me node set "$1" --add-scope "notes-$1.txt"
  say "[$2] check";   me node set "$1" --check "python3 -m unittest"
  say "[$2] attempts"; me node set "$1" --forks 3
  say "[$2] approval on"; me node set "$1" --signoff
  say "[$2] mine";    me node set "$1" --owner me
  say "[$2] back to an agent"; me node set "$1" --owner agent
  say "[$2] state now"; me state --json | python3 -c "import json,sys; s=json.load(sys.stdin); [print(t['id'], t['state'], len(t['forks'])) for t in s['tasks']]"
}
edits n2 suggested
edits n1 ready
say "attempts with no check"; me node add --scope docs.txt --signoff -- "write docs"; me node set n3 --forks 2
say "clear the check, approval on"; me node set n1 --check ""
me node set n1 --check "python3 -m unittest -q" >/dev/null
me node set n1 --no-signoff --forks 1 >/dev/null

say "agent starts n1"; agent node start n1 | head -5
edits n1 working
say "narrow the files under a working task"; me node set n1 --scope wordkit/clean.py
say "agent done n1 (approval on: to review)"; (cd "$D" && printf '\n# tidy\n' >> wordkit/clean.py); agent node done n1 | tail -4
say "state"; me state --json | python3 -c "import json,sys; s=json.load(sys.stdin); [print(t['id'], t['state']) for t in s['tasks']]"
edits n1 review
say "approve"; me node signoff n1 | tail -2
say "state"; me state --json | python3 -c "import json,sys; s=json.load(sys.stdin); [print(t['id'], t['state']) for t in s['tasks']]"
say "[done] title"; me node set n1 --title "done title"
say "[done] attempts"; me node set n1 --forks 2
say "node add output"; me node add --scope a.txt --check true --needs n3 -- "an added one"
say "timing of plan --json"; ( time me plan --json >/dev/null ) 2>&1 | tail -3
rm -rf "$(dirname "$D")" "$Z"
