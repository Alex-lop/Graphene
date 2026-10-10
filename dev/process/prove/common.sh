# Sourced by every script of the night (dev/process/prove/*.sh). Nothing here runs on its own.
#
# Every `claude -p` the night starts is isolated from this machine's account: no GitHub (gh here is
# logged in as Alex), no user-level plugins or MCP servers (ISO), a spend cap on its command line.
# Every build under test is a uv tool in its own directory; use_build puts its bin first on PATH, and
# FAKE=1 puts fake/claude (a stand-in that spends nothing) in front of the real one.
PROVE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CLONE=$(cd "$PROVE/../../.." && pwd)
TEST="$CLONE/dev/test"
ISO='--setting-sources project,local --strict-mcp-config'
UNMARK="-u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_ENTRYPOINT -u AI_AGENT -u GRAPHENE_NODE -u GRAPHENE_PLANNER"
export GH_CONFIG_DIR="${GH_CONFIG_DIR:-$(mktemp -d)}" GH_TOKEN= GITHUB_TOKEN=
export GIT_AUTHOR_NAME=person GIT_AUTHOR_EMAIL=person@localhost
export GIT_COMMITTER_NAME=person GIT_COMMITTER_EMAIL=person@localhost
# the person's shell: none of the marks an agent's shell carries (as newrun.sh's env.sh has it)
me() { env $UNMARK GRAPHENE_AS="person:$(id -un)" "$@"; }
# a claude -p the harness itself starts (a plain session, a stranger, a reader): not inside this one
plain_claude() { env $UNMARK claude "$@"; }
use_build() {
  BIN=$(cd "$1" && pwd)
  [ -x "$BIN/graphene" ] || { echo "no graphene in $BIN" >&2; exit 2; }
  export PATH="$BIN:$PATH"
  [ "${FAKE:-}" = 1 ] && export PATH="$PROVE/fake:$PATH"
  TOOLPY="$(dirname "$BIN")/graphene-map/bin/python"  # the build's own interpreter: its DEFAULT_WITH
  return 0
}
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
stamp() { echo "$(now)  $*" >> "$OUT/times.txt"; }  # every script sets OUT before its first stamp
# one field of a `claude -p` result: --output-format json's object, or stream-json's last result line
json_field() { python3 "$PROVE/claude_json.py" "$1" "$2"; }
# a 95% Wilson interval, two decimals: wilson x n
wilson() { python3 - "$1" "$2" <<'PY'
import math, sys
x, n = int(sys.argv[1]), int(sys.argv[2])
if n == 0:
    print("n=0"); raise SystemExit
z, p = 1.96, x / n
d = 1 + z * z / n
c = (p + z * z / (2 * n)) / d
h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
print(f"{x}/{n} = {p:.2f} [{max(0.0, c - h):.2f}, {min(1.0, c + h):.2f}]")
PY
}
