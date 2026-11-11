#!/bin/bash
# usage: probe.sh NAME "prompt"   -- one Haiku call in a fresh fixture (/tmp/gc-NAME) that holds inside.txt
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SID=$(python3 -c 'import uuid; print(uuid.uuid4())')
"$HERE/setup.sh" "$1" "$SID" >/dev/null 2>&1 || { echo "setup failed"; exit 1; }
for v in $(env | grep -E "^(CLAUDE|CODEX|AI_AGENT|CURSOR_AGENT|GEMINI_CLI)" | cut -d= -f1); do unset "$v"; done
export PATH="$HERE/../../../../.venv/bin:$PATH" ZDOTDIR=$(mktemp -d) NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off GRAPHENE_TOKENFACTORY_URL=http://127.0.0.1:9
cd /tmp/gc-$1
~/.local/bin/claude -p --model haiku --max-turns 6 --session-id "$SID" --permission-mode acceptEdits \
  --setting-sources project,local ${PROBE_ARGS:-} --output-format stream-json --verbose -- "$2" > /tmp/gc-$1.stream.jsonl 2>/tmp/gc-$1.err
echo "exit $?"
echo "--- files:"; ls
echo "--- git status:"; git status --short
echo "--- plan log (denied rows):"
graphene plan log --json | python3 -c '
import json,sys
d=[json.loads(l) for l in sys.stdin if l.strip()]
rows=d if isinstance(d,list) else d.get("log") or d.get("rows") or d
for r in rows:
    if r.get("kind") in ("denied","breach","stop_refused"): print(json.dumps({k:r.get(k) for k in ("kind","node","agent_id","session","detail") if k in r}))
'
