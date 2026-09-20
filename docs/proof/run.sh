#!/usr/bin/env bash
# `graphene run` on real agents: Graphene takes the nodes, one executor per node, and a person's
# node in the middle. About two minutes, a few cents.
#
#   docs/proof/run.sh [dir]        (needs: graphene, claude, git, python3)
#
# What must be true at the end: the agent nodes are done by Graphene's own check, the run stopped at
# the person's node and said who it waits for, and after the person did theirs by hand (same gate,
# same record) a second run picked up what had been waiting.
set -euo pipefail
DIR="${1:-$(mktemp -d)/toy}"
as_me() { env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT GRAPHENE_AS="person:$(id -un)" "$@"; }
WITH='claude -p --model sonnet --permission-mode acceptEdits --allowedTools Read Edit Write Glob Grep "Bash(graphene *)" "Bash(python3 *)" "Bash(git *)" "Bash(ls *)" "Bash(cat *)"'

mkdir -p "$DIR/app" "$DIR/tests" && cd "$DIR" && git init -q
printf '__pycache__/\n*.pyc\n' > .gitignore
printf 'def slug(text):\n    raise NotImplementedError\n' > app/text.py
printf 'RATE = None  # the person decides this number\n' > app/pricing.py
touch app/__init__.py tests/__init__.py
cat > tests/test_text.py <<'PY'
import unittest

from app.text import slug


class Slug(unittest.TestCase):
    def test_words(self):
        self.assertEqual(slug("Hello World"), "hello-world")

    def test_punctuation_goes(self):
        self.assertEqual(slug("Hello, World!"), "hello-world")
PY
git add -A && git -c user.email=proof@example.com -c user.name=proof commit -qm "toy app"
graphene init >/dev/null

as_me graphene node add "slug() turns a title into a url slug" --id slug --scope 'app/text.py' \
  --goal "app/text.py: slug(text) lower-cases and joins the words with '-'." \
  --check "python3 -m unittest -q tests.test_text"
as_me graphene node add "set the rate" --id rate --owner me --scope app/pricing.py \
  --goal "Decide RATE. Mine: an agent does not pick prices." --check "python3 -c 'from app.pricing import RATE; assert RATE'"
as_me graphene node add "price() uses the rate" --id price --needs rate --scope 'app/pricing.py' \
  --goal "app/pricing.py: add price(units) returning units * RATE. Leave RATE as the person set it." \
  --check "python3 -c 'from app.pricing import price, RATE; assert price(3) == 3 * RATE'"

echo "--- the plan, and what the person is told before the run:"; as_me graphene plan accept 2>&1 | tail -3; as_me graphene plan
echo; echo "--- graphene run:"; as_me graphene run --with "$WITH"
echo; echo "--- the person does theirs, by hand, through the same gate:"
as_me graphene node start rate >/dev/null
printf 'RATE = 7  # the person decides this number\n' > app/pricing.py
as_me graphene node done rate
echo; echo "--- graphene run, again:"; as_me graphene run --with "$WITH"

PLAN=$(as_me graphene plan); LOG=$(as_me graphene plan log)
echo; echo "$PLAN"; echo; echo "$LOG"; echo; echo "--- what must be true:"
fail=0
say() { if grep -q -- "$2" <<<"$3"; then echo "  ok    $1"; else echo "  FALSE $1"; fail=1; fi; }
say "slug is done, by Graphene's check" "slug .*check_passed" "$LOG"
say "the person's node was done by the person" "rate .*finished *$(id -un)" "$LOG"
say "price started only after the person's node was finished" "price *done" "$PLAN"
python3 -c 'from app.pricing import price, RATE; assert RATE == 7 and price(3) == 21' && echo "  ok    RATE is still the person's 7, and price(3) == 21" || { echo "  FALSE RATE/price"; fail=1; }
echo; echo "repo: $DIR"; exit $fail
