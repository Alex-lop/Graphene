#!/bin/bash
# Run the CI macOS job's scope under the interpreter topology the runner has.
#
#   scripts/macos_parity_check.sh [--quick]
#
# Why this exists. On 2026-08-25 the macOS CI job failed one test that no local
# run could reproduce: python.org's framework build ships `bin/python3.x` as a
# launcher that execs `Resources/Python.app/Contents/MacOS/Python` in place, so
# the owned-process registry saw its child change executable and refused every
# later validate/signal. `actions/setup-python` installs exactly that build on
# `macos-15`. Anaconda, Homebrew and uv interpreters do not re-exec, so the full
# matrix was green on every development machine and red in Actions — the same
# shape as the SQLite-3.46 defect that `scripts/linux_parity_check.sh` exists
# for, one layer down: not a different OS, a different interpreter on the same
# OS. Nothing in this repository ran the macOS job under that topology.
#
# Spends nothing, contacts no provider, and writes nothing into the working
# tree: the locked environment is built in a scratch directory via
# UV_PROJECT_ENVIRONMENT and pytest runs with `-p no:cacheprovider`.
#
# What this CANNOT see, stated because a check whose blind spots are invisible
# is the thing it is guarding against:
#   * the runner, only its interpreter. macos-15's OS version, its sandbox
#     policy, its architecture and its toolcache copy of the framework are all
#     different; this is the same python.org layout, not the same binary.
#   * `--quick` is two files. It prints "MACOS PARITY (quick)", which a grep for
#     "MACOS PARITY: ALL PASS" deliberately does not match.
#   * two CI steps are not run here: "Generated files leave a clean diff"
#     (interpreter-independent) and the CLI/NDJSON smoke.
#   * the environment is REUSED across runs unless the lock forces a rebuild;
#     the line below says which, and `rm -rf` on the path forces a fresh one.
set -uo pipefail
cd "$(dirname "$0")/.."

QUICK=0; [ "${1:-}" = "--quick" ] && QUICK=1

# The version CI installs, read from the tree rather than written down twice.
PYVER=$(tr -d ' \n' < .python-version)
FRAMEWORK="/Library/Frameworks/Python.framework/Versions/$PYVER/bin/python$PYVER"

if [ ! -x "$FRAMEWORK" ]; then
  echo "SKIP macOS parity: no python.org framework interpreter at $FRAMEWORK"
  echo "  CI is then the only thing that runs this job's scope on a re-exec'ing"
  echo "  launcher; read the \"Python 3.13 / macOS sandbox\" job log before trusting a push."
  echo "  Install it from python.org (or \`uv python install --preview cpython-$PYVER-macos\`)"
  echo "  to make this host able to reproduce that failure."
  exit 0
fi

VENV=${GRAPHENE_PARITY_VENV:-${TMPDIR:-/tmp}/graphene-macos-parity-$PYVER}
built=reused; [ -x "$VENV/bin/python" ] || built=built
unset VIRTUAL_ENV
export UV_PROJECT_ENVIRONMENT="$VENV"
if ! out=$(uv sync --frozen --python "$FRAMEWORK" 2>&1); then
  printf 'FAIL locked environment on %s\n%s\n' "$FRAMEWORK" "$out"
  echo "MACOS PARITY: FAILED"
  exit 1
fi

# The whole point is the topology, so prove it rather than assume it: a venv
# that silently landed on the ambient interpreter would run every step below
# and print PASS without ever exercising the launcher this script is about.
base=$("$VENV/bin/python" -c 'import sys; print(sys.base_prefix)' 2>&1)
case "$base" in
  */Python.framework/Versions/*) ;;
  *) echo "FAIL topology: parity venv base_prefix is $base, not a framework build"
     echo "MACOS PARITY: FAILED"; exit 1 ;;
esac

echo "== macOS parity for the \"Python 3.13 / macOS sandbox\" job"
echo "  interpreter   $FRAMEWORK"
echo "  base_prefix   $base"
echo "  app binary    $(ls "$base"/Resources/Python.app/Contents/MacOS/Python 2>/dev/null || echo '(absent — this launcher may not re-exec)')"
echo "  environment   $VENV ($built)"
echo "  tree          $(git rev-parse --short HEAD) + $(git status --porcelain --untracked-files=all | wc -l | tr -d ' ') uncommitted file(s)"

fail=0
run() { local label=$1; shift; local out; if out=$("$@" 2>&1); then echo "PASS $label"; else
  printf "FAIL %s\n%s\n" "$label" "$out"; fail=1; fi; }

run "the supported host sandbox is present" test -x /usr/bin/sandbox-exec
if [ "$QUICK" = 1 ]; then
  run "quick: owned process control and the mission CLI" uv run --frozen pytest -q \
    -p no:cacheprovider tests/unit/orchestration/test_process_control.py \
    tests/process/test_mission_cli.py
  [ $fail -eq 0 ] && echo "MACOS PARITY (quick): ALL PASS" || echo "MACOS PARITY (quick): FAILED"
  exit $fail
fi
run "lint with the locked ruff" uv run --frozen ruff check .
run "unit, integration, process, and adversarial tests" uv run --frozen pytest -q \
  -p no:cacheprovider tests/unit tests/integration tests/process tests/adversarial \
  --ignore=tests/process/test_mcp_stdio.py
run "MCP STDIO process tests" uv run --frozen pytest -q -p no:cacheprovider \
  tests/process/test_mcp_stdio.py
[ $fail -eq 0 ] && echo "MACOS PARITY: ALL PASS" || echo "MACOS PARITY: FAILED"
exit $fail
