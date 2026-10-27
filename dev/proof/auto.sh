#!/usr/bin/env bash
# Auto mode on the Nemotron path, end to end: one goal in, tested commits out. Nemotron 3 Ultra plans the
# goal as tasks that can run at once. Three Nemotron 3 Nano agents race each task in its own copy. The rule
# keeps one fork a task, and what passes lands. Then the goal's own check runs, the whole test suite. When it
# is red, Ultra plans the fix and the race goes again, inside the envelope the flags set.
#
#   dev/proof/auto.sh [dir]        (default: ~/graphene-auto; it must not exist)
#
# Needs graphene on PATH with the Nemotron extra, and NEBIUS_API_KEY in the environment. It spends real
# tokens at Token Factory's list price, at most BUDGET dollars (2 unset). The bill is the last thing it
# prints. The knobs, one each:
#   ENDPOINT=standin   the same take, free, against dev/proof/standin.py: no key, no network, no model. The
#                      stand-in says so on every screen. Its first line is its URL. A stand-in that is
#                      missing or dies is a refusal, never a fallback to Token Factory.
#   ENDPOINT=ollama    the same take on this machine's Ollama, no key (`ollama pull nemotron-3-nano:4b` first).
#   ENDPOINT=nim       the same take on NVIDIA's API catalog (NVIDIA_API_KEY).
#   PAUSE=1            wait after `graphene init`, so you can open the folder in VS Code and start recording
#                      before the race. Press Enter to go on. Unset, it never waits (CI, the tests).
#   RECORD=<file>      record the plan's store over the whole run, for `graphene demo <file>` to replay.
#                      tests/test_demo_auto.py makes the one `graphene demo --auto` ships this way.
#   PLANNER, EXECUTOR  the specs `graphene init` takes (nemotron, nemotron).
#   MAKE_REPO, GOAL    the repository and the goal instead of wordkit and its three wishes.
#   FORKS, ROUNDS, CHECK  the envelope's forks a task (3), fix rounds (2) and the goal's check (unittest).
#   STANDIN=<command>  what serves the stand-in instead of standin.py (the tests make it die).
# The first thing it prints is how to install the night's extension in your own editor. It prints the line
# and never runs it: your VS Code and Cursor are yours.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
DIR=${1:-$HOME/graphene-auto}
[ -e "$DIR" ] && { echo "$DIR exists already; name another directory, or delete it first" >&2; exit 1; }
ENDPOINT=${ENDPOINT:-tokenfactory}
case $ENDPOINT in
  tokenfactory) [ -n "${NEBIUS_API_KEY:-}" ] || { echo "NEBIUS_API_KEY is not set: Token Factory needs a key" >&2; exit 1; } ;;
  nim) [ -n "${NVIDIA_API_KEY:-}" ] || { echo "NVIDIA_API_KEY is not set: NVIDIA's API catalog needs a key" >&2; exit 1; } ;;
  ollama|standin) ;;
  *) echo "ENDPOINT is tokenfactory, nim, ollama or standin, not $ENDPOINT" >&2; exit 1 ;;
esac
# this checkout's own graphene first, when `uv sync` made it: the take runs this branch, and the stand-in needs
# its python (an installed tool's `graphene` has no python beside it, and no pytest for the stand-in's script)
[ -x "$ROOT/.venv/bin/graphene" ] && PATH=$ROOT/.venv/bin:$PATH
command -v graphene >/dev/null || { echo "graphene is not on PATH" >&2; exit 1; }
# spending is the person's: an agent's shell runs this on Token Factory only when the person opened it
if [ "$ENDPOINT" != ollama ] && [ "$ENDPOINT" != standin ] && [ -z "${GRAPHENE_TOKENFACTORY_URL:-}" ] && [ -z "${GRAPHENE_AGENT_LIVE_USD:-}" ]; then
  for mark in CLAUDECODE CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT CODEX_SESSION_ID CODEX_SANDBOX \
              AI_AGENT GEMINI_CLI CURSOR_AGENT; do
    [ -n "${!mark:-}" ] && { echo "refused: this spends on the person's key, and this shell carries an agent's mark ($mark) with no GRAPHENE_AGENT_LIVE_USD: nothing was sent" >&2; exit 1; }
  done
fi
unset CLAUDECODE CLAUDE_CODE_SESSION_ID AI_AGENT GRAPHENE_AS   # the person runs this, not an agent
step() { printf '\n\033[1m$ %s\033[0m\n' "$*"; "$@"; }
case ${RECORD:-} in ''|/*) ;; *) RECORD=$PWD/$RECORD ;; esac   # from where this was started

# the night's extension, for your own editor: printed, never run
vsix=$(ls -t "$ROOT"/editors/vscode/*.vsix 2>/dev/null | head -1 || true)   # the newest, not the last by name
[ -n "$vsix" ] || vsix="$ROOT/editors/vscode/graphene-VERSION.vsix   (none built yet: cd editors/vscode && npm ci && npm run package)"
printf 'to watch this take in your own editor, install the extension first (this script never does):\n'
printf '  code --install-extension %s\n  cursor --install-extension %s\n\n' "$vsix" "$vsix"

stop() { :; }
trap 'stop' EXIT
if [ "$ENDPOINT" = standin ]; then   # the stand-in speaks Token Factory's JSON; its URL replaces the real one
  export GRAPHENE_ENDPOINT=tokenfactory NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off
  py=$(dirname "$(command -v graphene)")/python; [ -x "$py" ] || py=python3
  [ -e "$HERE/standin.py" ] || { echo "refused: $HERE/standin.py is missing, and ENDPOINT=standin never reaches Token Factory" >&2; exit 1; }
  pipe=$(mktemp -d)/standin; mkfifo "$pipe"
  ${STANDIN:-$py $HERE/standin.py} > "$pipe" & standin=$!
  # read-write, so the open never waits on the stand-in: on macOS a stand-in that dies at once can leave a
  # read-only open asleep, and its SIGCHLD then fails it with "Interrupted system call". Our own write end means
  # no EOF, so the stand-in's death is read from the process, a second at a time.
  exec 3<> "$pipe"
  url=""; waited=0
  until IFS= read -r -t 1 url <&3; do
    waited=$((waited + 1)); kill -0 $standin 2>/dev/null && [ $waited -lt 60 ] || break
  done
  rm -rf "${pipe%/standin}"
  if [ -z "$url" ]; then
    kill -TERM $standin 2>/dev/null || true
    echo "refused: the stand-in died before it said its URL, and ENDPOINT=standin never reaches Token Factory" >&2; exit 1
  fi
  export GRAPHENE_TOKENFACTORY_URL=$url
  stop() { kill -TERM $standin 2>/dev/null; wait $standin 2>/dev/null || true; }
  echo "stand-in at $url: a script answers, no model runs, nothing is spent"
else
  export GRAPHENE_ENDPOINT=$ENDPOINT
fi

${MAKE_REPO:-python3 $HERE/make_wordkit.py} "$DIR" > /dev/null
cd "$DIR"
if [ -n "${RECORD:-}" ]; then   # it waits for the store `graphene init` makes, and stops when this ends
  graphene demo --record "$RECORD" & recorder=$!
  trap 'kill -TERM $recorder; wait $recorder; stop' EXIT
fi
step graphene init --planner "${PLANNER:-nemotron}" --executor "${EXECUTOR:-nemotron}"
if [ -n "${PAUSE:-}" ]; then
  printf '\nopen %s in VS Code and start recording, then press Enter ' "$DIR"
  IFS= read -r _
fi

step graphene auto "${GOAL:-wordkit grows three things at once: a --top N option on the CLI that prints the N \
most common words with their counts; a reading time in whole minutes, rounded up, at 200 words a minute; and \
hyphenated words like well-known counted as one word.}" \
  --budget "${BUDGET:-2}" --forks "${FORKS:-3}" --rounds "${ROUNDS:-2}" --parallel 4 \
  --check "${CHECK:-python3 -m unittest}"

step git log --graph --oneline
step graphene plan record
