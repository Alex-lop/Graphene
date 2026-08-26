#!/bin/bash
# Run the CI Linux job's scope in the image the product actually deploys to.
#
#   scripts/linux_parity_check.sh
#
# Why this exists. `scripts/morning_verify.sh` is a macOS result by
# construction, and on 2026-08-24 it printed ALL PASS on four consecutive
# commits while the Linux CI job was red on every one of them. The defect was
# a SQL `LIKE` against a BLOB column: it matches on the SQLite that ships with
# macOS (3.51) and matches nothing on the SQLite in the Debian base (3.46).
# Nothing runnable on the development host could see it.
#
# That base is not incidental. Three of this repository's four Dockerfiles pin
# `python:3.13-slim` by digest, and that digest carries SQLite 3.46 — so the
# deployment base is OLDER than the development base, by pin, and stays that
# way until someone deliberately repins. Version-sensitive SQL in the mission
# store is a shipping hazard, not a CI annoyance: a store that cannot find an
# approval refuses every dispatch, and the deployed product does nothing.
#
# Spends nothing, contacts no provider, and writes nothing into the working
# tree: the repository is exported with `git archive` into a scratch copy and
# the container's virtualenv lives inside the container.
set -uo pipefail
cd "$(dirname "$0")/.."

# The digest the deployment Dockerfiles pin. Read from the tree rather than
# written down twice, so this cannot drift away from what actually ships.
IMAGE=$(grep -ohm1 'FROM python:3.13-slim@sha256:[0-9a-f]*' \
  deploy/cloudrun/Dockerfile docker/executor.Dockerfile 2>/dev/null \
  | head -1 | sed 's/^FROM //')
IMAGE=${IMAGE:-python:3.13-slim}

if ! docker info >/dev/null 2>&1; then
  echo "SKIP linux parity: docker is not available on this host"
  echo "  CI is then the only thing that sees Linux; read the job log before trusting a push."
  exit 0
fi

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
git archive HEAD | tar -x -C "$scratch"
# Uncommitted work is the point of a pre-push check, so overlay it. `install
# -D` is GNU-only and fails silently on BSD/macOS, which would leave this
# checking HEAD while appearing to check the working tree — the exact kind of
# check-that-cannot-fail this script exists to prevent.
# `git diff` lists modifications only, so a brand-new test file would be
# checked at HEAD — that is, not checked at all. `git status --porcelain`
# includes untracked paths and still honours .gitignore.
overlaid=0
while IFS= read -r path; do
  [ -n "$path" ] && [ -f "$path" ] || continue
  mkdir -p "$scratch/$(dirname "$path")"
  cp "$path" "$scratch/$path"
  overlaid=$((overlaid + 1))
done < <(git status --porcelain --untracked-files=all | sed 's/^...//')
echo "  overlaid $overlaid uncommitted file(s) onto $(git rev-parse --short HEAD)"

echo "== linux parity against $IMAGE"
docker run --rm -v "$scratch":/work -w /work -e UV_PROJECT_ENVIRONMENT=/tmp/venv \
  "$IMAGE" bash -lc '
set -uo pipefail
# `git` is absent from the slim image. Tests that shell out to it are not part
# of this job and are deselected rather than left to fail confusingly.
apt-get -qq update >/dev/null 2>&1 && apt-get -qq install -y --no-install-recommends git >/dev/null 2>&1
pip install -q uv >/dev/null 2>&1
uv sync --frozen -q || { echo "FAIL locked environment"; exit 1; }
python -c "import sqlite3; print(\"  sqlite\", sqlite3.sqlite_version)"
fail=0
run() { local label=$1; shift; local out; if out=$("$@" 2>&1); then echo "PASS $label"; else
  printf "FAIL %s\n%s\n" "$label" "$out"; fail=1; fi; }
run "unsupported executor fails closed" uv run --frozen pytest -q \
  tests/unit/execution/test_adapter.py::test_fixed_tests_cannot_read_ambient_checkout_files \
  tests/unit/execution/test_adapter.py::test_fixed_tests_cannot_read_or_write_host_files_or_use_network
run "owned process polling and cleanup" uv run --frozen pytest -q \
  tests/unit/orchestration/test_process_control.py
run "verified replay stays read-only" uv run --frozen pytest -q \
  tests/process/test_verified_replay.py
run "demo --driver verified-replay" uv run --frozen graphene demo \
  --driver verified-replay --no-open --exit-after-demo
run "mission replay taskmaster" uv run --frozen graphene mission replay \
  taskmaster --no-open --exit-after-replay
run "terminal ui renders the replay read-only" uv run --frozen pytest -q tests/unit/ui
run "graphene ui --replay taskmaster --once" uv run --frozen graphene ui --replay taskmaster --once
# Not part of the CI job, but this is where a store that cannot read its own
# approvals shows up first, so it is worth the seconds.
run "approval and revision authority" uv run --frozen pytest -q \
  tests/adversarial/test_plan_revision.py tests/unit/orchestration/test_store.py
run "plan CLI surface" uv run --frozen pytest -q tests/unit/cli/test_plan_cli.py
exit $fail
'
status=$?
[ $status -eq 0 ] && echo "LINUX PARITY: ALL PASS" || echo "LINUX PARITY: FAILED"
exit $status
