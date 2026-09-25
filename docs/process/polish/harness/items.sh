#!/usr/bin/env bash
# items.sh <graphene> <dir>: each message item of the polish directive, in a fresh repo of its own
G=$1; D=$2; rm -rf "$D"; mkdir -p "$D"
person() { echo "\$ graphene $*   # the person"; env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT -u CLAUDE_CODE_ENTRYPOINT GRAPHENE_PERSON=alex "$G" "$@" 2>&1 | sed "s|$D|<repo>|g"; echo; }
agent()  { echo "\$ graphene $*   # an agent"; CLAUDECODE=1 CLAUDE_CODE_SESSION_ID=agent-session-1 "$G" "$@" 2>&1 | sed "s|$D|<repo>|g"; echo; }
sh_()    { echo "\$ $*"; eval "$@" 2>&1; echo; }
fresh() { R=$D/$1; mkdir -p $R/tests && cd $R && git init -q -b main . && git config user.email t@example.com && git config user.name T
  printf 'def add(a, b):\n    return a + b\n' > calc.py
  printf 'import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n' > tests/test_calc.py
  touch tests/__init__.py; printf '# calc\n' > README.md; git add -A && git commit -qm base; }
leaves() { person node add "sub is added" --id sub --scope calc.py --scope tests/test_calc.py --check 'python3 -m unittest -q' >/dev/null
  person node add "mul is added" --id mul --scope calc.py --scope tests/test_calc.py --check 'python3 -m unittest -q' --needs sub >/dev/null; }
echo "### 1. parent: places or is refused"; fresh parent
agent plan propose - <<'T'
goal: calc does subtraction
- wire it in  [wire]
  - add is kept  [keep]
      scope: calc.py
      check: python3 -m unittest -q
- sub is added  [sub]
    parent: wire
    scope: calc.py, tests/test_calc.py
    check: python3 -m unittest -q
T
person plan --text
echo "### 2. the check's own leftovers (a Python repo with no .gitignore)"; fresh leftovers; leaves
agent node start sub > /dev/null
sh_ "printf 'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n' > calc.py; python3 -m unittest -q 2>&1 | tail -1; git status --short"
agent node done sub
echo "### 3. a person's commit is not a loose change"; fresh commit; leaves
agent node start sub > /dev/null; printf 'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n' > calc.py; rm -rf __pycache__ tests/__pycache__
agent node done sub > /dev/null
sh_ "printf '__pycache__/\n' > .gitignore && git add .gitignore && git commit -qm 'ignore caches' && git log --oneline | head -1"
agent node start mul
echo "### 4. a refusal, said the first time and the second"; fresh refusal; leaves
agent node start sub > /dev/null; printf 'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n' > calc.py; echo "notes" > NOTES.txt
agent node done sub
agent node done sub
echo "### 5. start and done on a leaf that waits on a running one"; fresh waiting; leaves
agent node start sub > /dev/null
CLAUDECODE=1 CLAUDE_CODE_SESSION_ID=agent-session-2 "$G" node start mul 2>&1 | sed 's/^/(a second agent) /'; echo
CLAUDECODE=1 CLAUDE_CODE_SESSION_ID=agent-session-2 "$G" node done mul 2>&1 | sed 's/^/(a second agent) /'; echo
echo "### 6. next: after a hand-back, with nothing else ready"; fresh next; leaves
person node add "docs say so" --id docs --scope README.md --check 'grep -q sub README.md' --needs mul > /dev/null
person node add "the changelog" --id log --scope CHANGELOG.md --check 'test -f CHANGELOG.md' --needs mul > /dev/null
agent node start sub > /dev/null
agent node release sub --why 'the spec is ambiguous about floats'
echo "### 7. reopen with no note"; fresh reopen; leaves
person node start sub > /dev/null; printf 'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n' > calc.py; rm -rf __pycache__ tests/__pycache__
person node done sub > /dev/null
person node reopen sub
echo "### 8. which repository, on every write"; fresh where
person plan goal 'calc does subtraction'
person node add 'sub is added' --id sub --scope calc.py --check true
person node set sub --check 'python3 -m unittest -q'
person node drop sub
person plan undo
echo "### 9. graphene, with no plan"; fresh empty
person
echo "### 10. graphene plan: the row grammar"; fresh rows; leaves
person node add "docs say so" --id docs --scope README.md --check 'grep -q sub README.md' --needs mul > /dev/null
person plan
echo "### 11. a missing option or argument"; cd $D/rows
person node show
person node release sub
