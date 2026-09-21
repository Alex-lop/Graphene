#!/usr/bin/env bash
# Free on a Tuesday, on a real agent, in a throwaway repo. About a minute, a few cents.
#
#   docs/proof/tuesday.sh [dir]        (needs: graphene, claude, git, python3)
#
# A plan is in force. The person types an ordinary one-line request into a session, exactly what
# they would have typed with no plan, and runs no graphene command at all. What must then be true:
#   1. the edit happened, and no write was refused on the way;
#   2. it is on the plan as a leaf made from the prompt, done, and its record names the file;
# Then the agent is asked for something and told to propose it instead of doing it. The person
# answers "yes" in the same session and nothing else:
#   3. the proposal is accepted by that prompt (the log says so), and the same session does it.
set -euo pipefail
DIR="${1:-$(mktemp -d)/toy}"
ME="person:$(id -un)"
as_me() { env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT GRAPHENE_AS="$ME" "$@"; }

mkdir -p "$DIR/src" && cd "$DIR"
git init -q
printf '# Seed data. Emails are stored as they were typd in.\nUSERS = []\n' > src/seed.py
printf 'def emails():\n    return []\n' > src/users.py
git add -A && git -c user.email=proof@example.com -c user.name=proof commit -qm "toy"
graphene init >/dev/null
as_me graphene plan goal "a toy service that lists its users' emails"
as_me graphene node add "emails() returns lower-case emails" --scope 'src/users.py' --check "python3 -c 'import src.users'"
echo "--- the plan in force:"; as_me graphene plan

agent() {
  env -u GRAPHENE_AS claude -p "$1" --model sonnet --permission-mode acceptEdits --output-format json "${@:2}" \
    --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "Bash(graphene *)" "Bash(python3 *)" "Bash(git *)" "Bash(ls *)" "Bash(cat *)" \
    < /dev/null > .graphene/agent.json || true
  python3 -c 'import json; r = json.load(open(".graphene/agent.json")); print(r.get("result") or r)'
  SESSION=$(python3 -c 'import json; print(json.load(open(".graphene/agent.json"))["session_id"])')
}
fail=0
say() { if [ "$2" = yes ]; then echo "  ok    $1"; else echo "  FALSE $1"; fail=1; fi; }
has() { if grep -q -- "$2" <<<"$1"; then echo yes; else echo no; fi; }

ONE="fix the typo in the comment at the top of src/seed.py"
echo; echo "--- the person types, and nothing else: $ONE"; agent "$ONE"
PLAN=$(as_me graphene plan --all); LOG=$(as_me graphene plan log)
echo; echo "$PLAN"; echo; echo "$LOG"; echo; echo "--- what must be true:"
say "the typo is fixed" "$(grep -q typd src/seed.py && echo no || echo yes)"
say "no write was refused on the way" "$(has "$LOG" ' denied ' | sed 's/yes/x/;s/no/yes/;s/x/no/')"
say "it is a leaf made from the prompt, and it is done" "$(has "$PLAN" 'done .*fix the typo in the comment')"
say "and its record names the file it changed" "$(has "$LOG" 'finished .*changed: src/seed.py')"

TWO="I want a README.md with one line saying what emails() returns. Do not write it yet: propose a node for it with graphene node add (scope README.md, check 'test -s README.md'), then stop and ask me."
echo; echo "--- the person asks for a proposal:"; agent "$TWO"
echo; echo "--- and answers in the same session, with one word: yes"; agent "yes" --resume "$SESSION"
PLAN=$(as_me graphene plan --all); LOG=$(as_me graphene plan log)
echo; echo "$PLAN"; echo; echo "$LOG"; echo; echo "--- what must be true:"
say "the proposal was accepted by the prompt, as the person" "$(has "$LOG" "accepted .*$(id -un | tr A-Z a-z)")"
say "the same session did it: README.md exists and its node is done" "$([ -s README.md ] && has "$PLAN" 'done .*README' )"
echo; echo "repo: $DIR"
exit $fail
