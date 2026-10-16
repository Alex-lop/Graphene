#!/bin/sh
# The live-note probe: does a note a hook adds while an agent works change what it does next?
# One real `claude -p` run on Haiku, about half a cent. It writes only into a folder under /tmp (not under
# .claude: writes there are "sensitive" and Claude Code stops to ask).
#
# Expected, and what 15 October 2026 gave in five runs: a.txt: x, b.txt: x, c.txt: y. The note rides the second
# write and the third follows it. (A sixth run, with no instruction to go one call at a time, batched all three
# writes into one message and got x, x, x: a note is read on the next model request.)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d /tmp/probe-live.XXXXXX)
git -C "$work" init -q
cat > "$work/settings.json" <<EOF
{"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "python3 $here/hook.py $work/count"}]}]}}
EOF
cd "$work"
claude -p "Create three files, a.txt then b.txt then c.txt, each containing the single letter x. Make exactly one tool call per message: write a.txt, wait for its result, then write b.txt, wait for its result, then write c.txt. Do not explain." \
  --model haiku --permission-mode acceptEdits --allowedTools Write \
  --settings "$work/settings.json" --setting-sources project,local --max-budget-usd 0.30 > /dev/null < /dev/null
for f in a.txt b.txt c.txt; do echo "$f: $(cat "$f" 2>/dev/null || echo missing)"; done
