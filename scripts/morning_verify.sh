#!/bin/bash
# Re-run the night's verification in review order and print the proof table.
#
#   scripts/morning_verify.sh [--quick]
#
# Steps: locked env -> full credential-free matrix (skipped with --quick) ->
# ruff/compileall/diff-check -> location-only secret scan -> store.verify on the
# night's mission store -> capsule cold-verify from a fresh clone in a temp dir
# -> watcher tests -> proof-table status from contracts/product_proof.json.
# Spends nothing and contacts no provider. Prints only identifiers and counts.
# Every interpreter here is the locked one: a verification whose own verdict
# is computed by whatever `python3` the developer's PATH yields is not locked.
set -uo pipefail
cd "$(dirname "$0")/.."
QUICK=0; [ "${1:-}" = "--quick" ] && QUICK=1
# The convergence store holds the 2026-08-23 completion-gate missions. The
# night store (~/.graphene/north-star-state) predates the final-bundle
# verification receipt the store now issues at registration, so its two
# bundle-carrying missions fail the new cold audit BY DESIGN — the store could
# not have recomputed a bundle it had no authority over. Their durable record
# is the committed capsule, cold-verified below.
STATE="${GRAPHENE_STATE_DIR:-$HOME/.graphene/convergence-state}"
fail=0
skipped=0
step() { printf '\n== %s\n' "$1"; }
ok()   { printf 'PASS %s\n' "$1"; }
bad()  { printf 'FAIL %s\n' "$1"; fail=1; }
# Never swallow a step: on failure the captured output is printed, so a FAIL
# always arrives with its diagnostic. That is the whole point of this script.
run() { local label=$1; shift; local out; if out=$("$@" 2>&1); then ok "$label"; else
  printf 'FAIL %s\n--- output of: %s\n%s\n--- end output\n' "$label" "$*" "$out"; fail=1; fi; }

# A parity check is the one step whose OUTPUT matters when it passes: both
# scripts exit 0 when the topology they need is absent, so `run` would report a
# SKIP as PASS -- the exact shape this script exists to stop. Print the output
# either way, and count a skip as a skip.
parity() {
  local label=$1; shift; local out rc
  out=$("$@" 2>&1); rc=$?
  printf '%s\n' "$out" | sed 's/^/  /'
  if [ "$rc" -ne 0 ]; then bad "$label"
  elif printf '%s\n' "$out" | grep -q '^SKIP'; then
    printf 'SKIP %s (unchecked here; see the lines above)\n' "$label"; skipped=$((skipped + 1))
  else ok "$label"; fi
}

step "locked environment"
run "uv lock --check" uv lock --check
run "uv sync --frozen" uv sync --frozen

# pytest already exits non-zero on failure; run() prints the whole run when it does.
if [ "$QUICK" = 0 ]; then
  step "full credential-free matrix (~5 min)"
  run "matrix" uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial \
        --ignore=tests/process/test_mcp_stdio.py -p no:cacheprovider
  step "MCP STDIO process tests"
  run "mcp" uv run --frozen pytest -q tests/process/test_mcp_stdio.py -p no:cacheprovider
fi

step "parity: the two topologies this host is not"
# Until now MORNING VERIFY: ALL PASS was a macOS/Anaconda result BY
# CONSTRUCTION, and it printed on four consecutive commits while Linux CI was
# red on every one of them. Both defects that caused it were invisible to
# every command above: SQLite 3.46 in the deployment image, and python.org's
# re-exec'ing framework launcher on the GitHub macOS runner.
if [ "$QUICK" = 1 ]; then
  parity "macOS parity (framework interpreter, quick scope)" scripts/macos_parity_check.sh --quick
  echo "  linux parity not run in --quick: it is a container build, minutes not seconds."
  echo "  SKIP linux parity (unchecked here; run scripts/linux_parity_check.sh)"
  skipped=$((skipped + 1))
else
  parity "macOS parity (framework interpreter)" scripts/macos_parity_check.sh
  parity "linux parity (pinned deployment image)" scripts/linux_parity_check.sh
fi

step "ruff / compileall / git diff --check"
run "ruff (locked)" uv run --frozen ruff check .
run "compileall" uv run --frozen python -m compileall -q backend scripts tests
# --check catches whitespace errors; --exit-code is what actually proves a
# generated file did not drift. CI runs both under the same step name.
git diff --check && git diff --exit-code && ok "git diff clean" || bad "git diff clean"

step "secret scan (locations + pattern names only; tests/ fixtures are expected)"
uv run --frozen python scripts/secret_scan.py --commits 40 | tail -1 && ok "secret scan: nothing outside tests/" || bad "secret scan"

step "mission store ($STATE)"
if [ -d "$STATE" ]; then
  out=$(GRAPHENE_STATE_DIR="$STATE" uv run --frozen graphene --json mission db verify 2>/dev/null)
  echo "$out"
  uv run --frozen python - "$out" <<'PY' && ok "store.verify on every mission in the store" || bad "store.verify"
import json, sys
d = json.loads(sys.argv[1]); assert d["status"] == "current" and d["verified_missions"] == d["mission_count"] > 0
PY
  for m in mission_start_b0b61fac3a6b1b3279329462 mission_start_b6be7f35ba803c6dc34597b1; do
    st=$(GRAPHENE_STATE_DIR="$STATE" uv run --frozen graphene --json mission status "$m" 2>/dev/null | uv run --frozen python -c 'import json,sys; d=json.load(sys.stdin); print(d["mission"]["status"], d["head"]["seq"], d["head"]["event_sha256"][:16])')
    echo "  $m -> $st"
  done
else
  echo "  (state dir absent: skipped — the committed capsules below are the durable record)"
fi

step "capsule cold-verify from a fresh clone (temp dir, no mission store)"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
git clone -q "$PWD" "$tmp/clone" || bad "clone"
(cd "$tmp/clone" && run "fresh clone uv sync --frozen" uv sync --frozen) || fail=1
for c in evidence/north_star/2026-08-23-mission1/mission_start_5291caad50a8ee7a222a9221.graphene-capsule \
         evidence/north_star/2026-08-23-mission4-failure-lab/mission_start_38129f17add65609de1c3388.graphene-capsule; do
  v=$(cd "$tmp/clone" && env -u GRAPHENE_STATE_DIR uv run --frozen python -m graphene.orchestration.capsule verify "$c" 2>/dev/null | uv run --frozen python -c 'import json,sys; d=json.load(sys.stdin); print(d["verified"], d["mission_id"])')
  echo "  $v  manifest $(shasum -a 256 "$c/manifest.json" | cut -c1-16)…"
  [ "${v%% *}" = "True" ] && ok "cold verify $(basename "$c")" || bad "cold verify $(basename "$c")"
done

step "watcher tests (inbox + GitHub poller, no network)"
if [ -f tests/unit/cli/test_watch.py ]; then
  run "watcher tests" uv run --frozen pytest -q tests/unit/cli/test_watch.py tests/unit/orchestration/test_mission_trigger.py -p no:cacheprovider
else
  bad "tests/unit/cli/test_watch.py missing"
fi

step "proof table (contracts/product_proof.json)"
uv run --frozen python - <<'PY'
import json
d = json.load(open("contracts/product_proof.json"))
rows = [
    ("live Gemini (gemini-adk-planner)", d["mission_paths"]["gemini-adk-planner"]["status"]),
    ("delivery_gates.live_gemini", d["delivery_gates"]["live_gemini"]["status"]),
    ("north_star", d["north_star"]["status"]),
    ("  two real workers", d["north_star"]["legs"]["coordinates_two_real_gemini_workers"].split(" — ")[0]),
    ("  survives one failing", d["north_star"]["legs"]["survives_one_of_them_failing"].split(" — ")[0]),
    ("  proves why", d["north_star"]["legs"]["proves_exactly_why"].split(" — ")[0]),
    ("mission_capsule", d["mission_capsule"]["status"]),
    ("watch (trigger)", d.get("watch", {}).get("status", "absent")),
    ("docker-executor", d["mission_paths"]["docker-executor"]["status"]),
    ("cloud-run-firestore", d["mission_paths"]["cloud-run-firestore"]["status"]),
]
for name, status in rows:
    print(f"  {name:36s} {status}")
PY

printf '\n'
# "ALL PASS" is reserved for a run that actually saw both other topologies. A
# grep for it must not match a run where one of them was never checked.
if [ "$fail" != 0 ]; then echo "MORNING VERIFY: FAILURES ABOVE"
elif [ "$skipped" != 0 ]; then
  echo "MORNING VERIFY: PASS ON THIS HOST ONLY — $skipped parity check(s) SKIPPED"
else echo "MORNING VERIFY: ALL PASS"; fi
exit $fail
