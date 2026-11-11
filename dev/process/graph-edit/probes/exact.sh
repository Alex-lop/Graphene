#!/bin/bash
# What do board: on, review: every and auto: off cover? A plan with a question and a risk, each with a default,
# accepted whole as Home's Start does, under board: auto and then board: on. `uv sync` first; it writes under /tmp.
#   bash dev/process/graph-edit/probes/exact.sh
set -u
G=$(cd "$(dirname "$0")/../../../.." && pwd)
BIN=$G/.venv/bin
Z=$(mktemp -d /tmp/gp-z-XXXX)
BASE="env -i HOME=$HOME PATH=$BIN:/usr/bin:/bin:/opt/homebrew/bin USER=alex ZDOTDIR=$Z NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off GRAPHENE_TOKENFACTORY_URL=http://127.0.0.1:9"
say() { printf '\n--- %s\n' "$*"; }
qs() { me state --json | python3 -c "import json,sys; s=json.load(sys.stdin); print('questions:', [(q['kind'], q['text'][:30], q['default']) for q in s['questions']]); print('tasks:', [(t['id'], t['state'], t['scope']) for t in s['tasks']]); print('envelope:', s['envelope']['auto'], s['envelope']['review'])"; }
for BOARD in auto on; do
  D=$(mktemp -d /tmp/gp-XXXX)/wk
  me() { (cd "$D" && $BASE graphene "$@" 2>&1); }
  agent() { (cd "$D" && $BASE CLAUDECODE=1 CLAUDE_CODE_SESSION_ID=probe-sess-1 graphene "$@" 2>&1); }
  python3 $G/dev/proof/make_wordkit.py "$D" >/dev/null
  me init --planner claude --executor claude >/dev/null
  say "board: $BOARD"; me config set board $BOARD | head -2
  agent plan propose - <<'PLAN' | tail -4
goal: wordkit prints the top words
question: how many words by default?  [q-n]
    default: ten
    option: five
risk: the old hyphen test may break  [r-hyphen]
    default: keep the old test as it is
- print the top words  [top]
    scope: wordkit/cli.py, tests/test_top.py
    check: python3 -m unittest -q
PLAN
  say "what the snapshot shows ($BOARD)"; qs
  say "graphene config"; me config | head -12
  say "plan accept (all), as Home's Start does"; me plan accept | tail -4
  say "after accept ($BOARD)"; qs
  me board 2>&1 | head -8
  rm -rf "$(dirname "$D")"
done
rm -rf "$Z"
