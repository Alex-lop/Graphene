#!/usr/bin/env bash
# X6 · one stranger transcript on one build: a Sonnet session that has only that build's README (its
# install line pointing at that build's wheel), a fresh copy of the X4 repository with no remote, and
# the issue, told to narrate every command and stop at a landed leaf or when stuck. Reported as the
# list of dead ends it met, never as a rate.
#
#   dev/process/prove/x6_transcript.sh BIN OUT REPO_DIR ISSUE_FILE [WHEEL]    FAKE=1 spends nothing
#
# codex is hidden from its PATH (so init picks claude), gh and git push are denied, GitHub is
# unreachable (common.sh), and the whole process group is killed at 30 minutes. Writes OUT/prompt.txt,
# OUT/stream.jsonl, OUT/result.txt, OUT/deadends.json, OUT/merges.txt.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 4 ] || { sed -n '2,12p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2" && cd "$2" && pwd); SRC=$3; ISSUE=$4
WHEEL=${5:-$(ls "$CLONE"/dist/graphene_map-*.whl 2>/dev/null | head -1)}
stamp "x6 transcript start on $BIN"
rm -rf "$OUT/repo"; cp -R "$SRC" "$OUT/repo"
git -C "$OUT/repo" remote remove origin 2> /dev/null || true
[ -z "$(git -C "$OUT/repo" remote)" ] || { echo "the repo still has a remote" >&2; exit 2; }
cat > "$OUT/repo/me" <<EOF
#!/bin/sh
# your terminal: runs what you give it as you, the developer
exec env $UNMARK GRAPHENE_AS="person:\$(id -un)" "\$@"
EOF
chmod +x "$OUT/repo/me"
# that build's README, as its wheel carries it: this clone's own is the branch's, whichever build runs
if [ -f "$WHEEL" ]; then unzip -p "$WHEEL" '*.dist-info/METADATA' | sed '1,/^$/d'; else cat "$CLONE/README.md"; fi \
  | sed "s#git+https://github.com/Alex-lop/Graphene#'$WHEEL'#g" > "$OUT/README.md"
{
  echo "You are a developer at a terminal who has never seen Graphene. You want this done in the repository you are in:"
  echo; cat "$ISSUE"; echo
  echo "Someone told you \"use Graphene for it\" and gave you its README, below. Install it as the README says and use it to get one leaf landed for this ask."
  echo "Run every shell command through ./me (for example: ./me graphene init). It is your terminal. Before each command say what you are about to do and why; after it, say what you make of what it printed."
  echo "Stop when \`./me git log --merges\` shows a landed leaf, or when you cannot see a next step; say which happened and why."
  echo; echo "--- the README ---"; cat "$OUT/README.md"
} > "$OUT/prompt.txt"
TB=$(mktemp -d); ln -s "$(command -v claude)" "$TB/claude"; ln -s "$(command -v uv)" "$TB/uv"
[ "${FAKE:-}" = 1 ] && ln -sf "$PROVE/fake/claude" "$TB/claude"
t0=$(date +%s); echo "$t0" > "$OUT/t0"
(
  cd "$OUT/repo"
  export PATH="$TB:$BIN:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
  command -v codex > /dev/null && { echo "codex is still on PATH" >&2; exit 2; }
  python3 "$PROVE/pgtimeout.py" 1800 env $UNMARK claude -p "$(cat "$OUT/prompt.txt")" --model sonnet \
    --permission-mode acceptEdits --allowedTools Read Glob Grep 'Bash(*)' \
    --disallowedTools 'Bash(gh *)' 'Bash(git push *)' $ISO \
    --output-format stream-json --verbose --max-budget-usd 3 > "$OUT/stream.jsonl" 2> "$OUT/stream.err" \
    || echo "exit $?" >> "$OUT/stream.err"
)
echo "$(( $(date +%s) - t0 ))" > "$OUT/seconds"
json_field "$OUT/stream.jsonl" result > "$OUT/result.txt" || true
echo "total_cost_usd: $(json_field "$OUT/stream.jsonl" total_cost_usd || echo none)" >> "$OUT/result.txt"
git -C "$OUT/repo" log --merges --format='%h %ct %s' > "$OUT/merges.txt" 2>&1 || true
python3 "$PROVE/deadends.py" "$OUT/stream.jsonl" | tee "$OUT/deadends.json"
stamp "x6 transcript done in $(cat "$OUT/seconds") s, $(wc -l < "$OUT/merges.txt") merges"
