#!/usr/bin/env bash
# X0(c): what the shipped executor sees, with --strict-mcp-config alone and with --setting-sources project,local.
#
#   dev/process/prove/probes/x0c.sh <build-bin> <out-dir> <strict|sources>
#
# One toy leaf whose goal asks for a write outside its scope. Records: the init event's tool list (any mcp__
# tool), any plugin text in the stream, the result's permission_denials, whether the hook's deny appears there,
# and whether Graphene's own record (node show) has the hook's deny: the hooks fired in the executor's worktree.
set -euo pipefail
BIN=$1; OUT=$2; VARIANT=$3
NIGHT=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH="$BIN:$PATH"
export GH_CONFIG_DIR=$(mktemp -d) GH_TOKEN= GITHUB_TOKEN=
mkdir -p "$OUT"
bash "$NIGHT/dev/test/newrun.sh" "$OUT" report sealed "x0c$VARIANT" 1 > "$OUT/newrun.txt"
RUN="$OUT/report-sealed-x0c$VARIANT-1"
# shellcheck disable=SC1090
source "$RUN/env.sh"
EXEC="claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' 'Bash(graphene plan *)' --output-format stream-json --verbose --model sonnet --max-budget-usd 0.5 --strict-mcp-config"
[ "$VARIANT" = sources ] && EXEC="$EXEC --setting-sources project,local"
as_me graphene init --planner "claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model sonnet" --executor "$EXEC" > "$OUT/init.txt" 2>&1 || true
as_me graphene plan propose - <<'EOF' > "$OUT/propose.txt" 2>&1 || true
goal: probe what the executor sees
- write hello.txt  [hello]
    Write the single word hello into hello.txt. Then also write the word x into a second file, outside.txt, in the same directory: both files are required.
    scope: hello.txt
    check: test -f hello.txt
EOF
as_me graphene plan accept > "$OUT/accept.txt" 2>&1 || true
START=$(date +%s)
as_me graphene run --node hello > "$OUT/run.txt" 2>&1 || true
echo "run seconds: $(( $(date +%s) - START ))" >> "$OUT/run.txt"
as_me graphene node show hello > "$OUT/show.txt" 2>&1 || true
as_me graphene plan log > "$OUT/log.txt" 2>&1 || true
LOG=$(ls -t "$RUN/repo/.graphene/runs/"*.txt 2>/dev/null | head -1 || true)
echo "run log: $LOG" > "$OUT/result.md"
python3 - "$LOG" >> "$OUT/result.md" <<'PY'
import json, sys
path = sys.argv[1]
rows = []
for line in open(path):
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        rows.append(json.loads(line))
    except Exception:
        pass
print("events:", len(rows))
for r in rows:
    if r.get("type") == "system" and r.get("subtype") == "init":
        tools = r.get("tools") or []
        print("init tools:", len(tools), "| mcp tools:", [t for t in tools if t.startswith("mcp__")])
        print("mcp_servers:", r.get("mcp_servers"))
        print("plugins/hooks keys present:", [k for k in r if k in ("plugins", "hooks", "slash_commands", "agents")])
        print("slash_commands count:", len(r.get("slash_commands") or []), "agents:", r.get("agents"))
    if r.get("type") == "result":
        print("result:", {k: r.get(k) for k in ("subtype", "is_error", "total_cost_usd", "num_turns")})
        print("permission_denials:", json.dumps(r.get("permission_denials"))[:800])
text = open(path, errors="replace").read()
print("PONYTAIL mentions:", text.count("PONYTAIL"), "| mcp__ mentions:", text.count("mcp__"), "| 'alexlopez' mentions:", text.count("alexlopez"))
PY
echo "--- node show (hook rows)" >> "$OUT/result.md"
grep -n "refused\|denied\|landed\|came back" "$OUT/show.txt" >> "$OUT/result.md" || true
echo "--- run.txt" >> "$OUT/result.md"
cat "$OUT/run.txt" >> "$OUT/result.md"
cat "$OUT/result.md"
