#!/usr/bin/env bash
# Two real agents at once, a worktree each, on one tree. About two minutes, some cents.
#
#   docs/proof/parallel.sh [dir]        (needs: graphene, claude, git, python3)
#
# The plan is a tree: a goal; under it a sub-goal with two leaves that touch different files and an
# integration check of its own; and a leaf that waits on the sub-goal. `graphene run --parallel 2`
# is started and the person does nothing else. What must then be true, from Graphene's log and git:
#   1. the two leaves were running at the same time, each in its own worktree;
#   2. each was told why: the path from the goal to its leaf was in what it was handed;
#   3. each landed in the person's checkout as a merge, and the worktrees and branches are gone;
#   4. the sub-goal is done because its own check passed HERE, after both had landed;
#   5. the leaf that waited on the sub-goal ran only then, on top of both.
set -euo pipefail
DIR="${1:-$(mktemp -d)/toy}"
ME="person:$(id -un)"
as_me() { env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT GRAPHENE_AS="$ME" "$@"; }

mkdir -p "$DIR/src" "$DIR/tests" && cd "$DIR"
git init -q
printf '__pycache__/\n*.pyc\n.graphene/\n' > .gitignore
printf 'USERS = [{"name": "Ada", "email": "Ada@Example.com"}, {"name": "Lin", "email": "LIN@example.COM"}]\n' > src/seed.py
printf 'from src.seed import USERS\n\n\ndef emails():\n    return [u["email"] for u in USERS]\n' > src/emails.py
printf 'from src.seed import USERS\n\n\ndef names():\n    return [u["name"] for u in USERS]\n' > src/names.py
cat > tests/test_all.py <<'PY'
import unittest

from src.emails import emails
from src.names import names


class Together(unittest.TestCase):
    def test_both(self):
        self.assertEqual(emails(), ["ada@example.com", "lin@example.com"])
        self.assertEqual(names(), ["ADA", "LIN"])
PY
touch src/__init__.py tests/__init__.py
graphene init >/dev/null
git add -A
git -c user.email=proof@example.com -c user.name=proof commit -qm "toy service"
git config user.email proof@example.com && git config user.name proof

cat > ../tree.json <<'JSON'
{"nodes": [
  {"id": "clean", "title": "the listing functions return clean values",
   "goal": "emails() lower-case and names() upper-case, and the two agree with tests/test_all.py",
   "check": "python3 -m unittest -q tests.test_all",
   "children": [
     {"id": "emails", "title": "emails() returns lower-case emails", "scope": ["src/emails.py"],
      "check": "python3 -c \"from src.emails import emails; assert emails() == ['ada@example.com', 'lin@example.com']\""},
     {"id": "names", "title": "names() returns upper-case names", "scope": ["src/names.py"],
      "check": "python3 -c \"from src.names import names; assert names() == ['ADA', 'LIN']\""}
   ]},
  {"id": "readme", "title": "say what the two functions return", "scope": ["README.md"], "needs": ["clean"],
   "goal": "README.md: one line each for emails() and names(), saying what they return now.",
   "check": "grep -qi lower README.md && grep -qi upper README.md"}
]}
JSON
as_me graphene plan goal "a toy service whose listings are safe to show to a customer"
as_me graphene plan propose ../tree.json >/dev/null
echo "--- the tree as the person left it:"; as_me graphene plan

echo; echo "--- graphene run --parallel 2, and the person does nothing else:"
START=$(date +%s)
as_me graphene run --parallel 2 --with "claude -p --model sonnet --permission-mode acceptEdits --allowedTools Read Edit Write Glob Grep Bash(graphene:*) Bash(python3:*) Bash(git:*) Bash(ls:*) Bash(cat:*)" || true
echo "($(( $(date +%s) - START )) s)"

fail=0
say() { if [ "$2" = yes ]; then echo "  ok    $1"; else echo "  FALSE $1"; fail=1; fi; }
has() { if grep -q -- "$2" <<<"$1"; then echo yes; else echo no; fi; }
PLAN=$(as_me graphene plan --all); LOG=$(as_me graphene plan log)
echo; echo "--- the tree afterwards:"; echo "$PLAN"
echo; echo "--- everything that happened on it:"; echo "$LOG"
echo; echo "--- what must be true:"
at() { grep -- " $1 *$2 " <<<"$LOG" | head -1 | awk '{print $1}'; }
both=$(python3 - "$(at emails started)" "$(at emails finished)" "$(at names started)" "$(at names finished)" <<'PY'
import sys
es, ef, ns, nf = sys.argv[1:5]
print("yes" if es and ns and ef and nf and es < nf and ns < ef else "no")
PY
)
say "the two leaves were running at the same time" "$both"
say "each in its own worktree" "$(sqlite3 .graphene/graphene.db "select count(distinct json_extract(detail,'\$.checkout')) from node_log where kind='started' and node_id in ('emails','names')" | sed 's/^2$/yes/;s/^[0-9]*$/no/')"
say "each leaf's contract carries the path from the goal down (what run hands over, word for word)" "$(has "$(as_me graphene node show emails)" 'why: *a toy service whose listings are safe')"
say "the hooks ran inside the worktrees: both executor sessions are on record, from there" "$([ "$(sqlite3 .graphene/graphene.db "select count(distinct session_id) from tool_events where cwd like '%.graphene/worktrees/%'")" -ge 2 ] && echo yes || echo no)"
say "both landed here as merges" "$([ "$(git log --merges --format=%s | grep -c -e '(emails)' -e '(names)')" = 2 ] && echo yes || echo no)"
say "the worktrees and branches are gone" "$([ -z "$(git branch --list 'graphene/*')" ] && [ ! -e .graphene/worktrees/emails ] && echo yes || echo no)"
say "the sub-goal is done by its own check, run here after both landed" "$(has "$LOG" 'clean .*rolled_up')"
say "and the leaf that waited on it ran only then" "$(python3 - "$(at clean rolled_up)" "$(at readme started)" <<'PY'
import sys
print("yes" if sys.argv[1] and sys.argv[2] and sys.argv[1] <= sys.argv[2] else "no")
PY
)"
say "the integration check passes in the person's checkout now" "$(python3 -m unittest -q tests.test_all >/dev/null 2>&1 && echo yes || echo no)"
echo; git log --graph --oneline | head -12
echo; echo "repo: $DIR"
exit $fail
