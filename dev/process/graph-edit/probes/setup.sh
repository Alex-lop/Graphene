#!/bin/bash
# Makes a fresh fixture repo in /tmp/gc-NAME, installs Graphene's hooks, and holds one task for a chosen session.
# usage: setup.sh NAME SESSION_UUID      (the lane's clone's venv is first on PATH)
set -euo pipefail
for v in $(env | grep -E "^(CLAUDE|CODEX|AI_AGENT|CURSOR_AGENT|GEMINI_CLI)" | cut -d= -f1); do unset "$v"; done  # we are a person here, not an agent
CLONE=/private/tmp/claude-501/-Users-alexlopez-Desktop-AllThingsAgenticHackathon/d0298f2f-47d2-4a13-a6a8-4813257b026f/scratchpad/c
export PATH="$CLONE/.venv/bin:$PATH"
export ZDOTDIR=$(mktemp -d) NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off GRAPHENE_TOKENFACTORY_URL=http://127.0.0.1:9
R=/tmp/gc-$1
rm -rf "$R" && mkdir -p "$R" && cd "$R"
git init -q && echo a > a.txt && echo i > inside.txt
git add -A && git -c user.email=t@e.com -c user.name=T commit -qm start
graphene init --planner claude --executor claude </dev/null
git add -A && git -c user.email=t@e.com -c user.name=T commit -qm "graphene init" || true
graphene plan first off >/dev/null 2>&1 || true
# one task, files = inside.txt, held by SESSION as `graphene run` holds a Claude Code leaf
python - "$2" <<'EOF'
import sys
from pathlib import Path
from graphene_map import plan
from graphene_map.plan import Caller
from graphene_map.store import Store
root = Path.cwd()
with Store.open(root) as store:
    plan.propose(store, [{"title": "inside only", "scope": ["inside.txt"], "check": "true"}], Caller("alex", True))
    [n] = [n for n in plan.nodes(store)]
    plan.start(store, n.id, Caller("claude:" + sys.argv[1][:8], False, sys.argv[1]), root)
    print("holding", n.id, n.scope)
EOF
