#!/usr/bin/env bash
# The same hijack, in ../../../gate's layout (Spec/, camelCase theorem), through ../../../gate/gate.sh.
# Core Lean only, so it needs no Mathlib: a copy in a new git repository under $1 (default: a temp dir),
# the trusted tree committed, the hijacking proof added as the candidate, an empty trusted .lake.
#   run-gate.sh [WORKDIR]      (GATE_TOOLS as for gate.sh)
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
w=${1:-$(mktemp -d "${TMPDIR:-/tmp}/hijack-gate.XXXXXX")}
# The project sits one directory down: gate.sh (as of 02:08) fails with the project at the repository
# root ("fatal: empty string is not a valid pathspec" from `git ls-tree -- ""`).
mkdir -p "$w/repo/proj" "$w/lake"
cd "$w/repo"
git init -q
cp -R "$here/Challenge.lean" "$here/lakefile.toml" "$here/Spec" "$here/Gate" proj/
cp "$here/../lean-toolchain" proj/
printf '.lake/\n' > .gitignore
git add -A && git -c user.name=gate -c user.email=gate@localhost commit -qm "trusted tree"
ref=$(git rev-parse HEAD)
cp -R "$here/Proofs" proj/
GATE_TRUSTED_REF=$ref GATE_TRUSTED_LAKE=$w/lake GATE_WORK=$w/work GATE_KEEP=1 \
  "$here/../../../gate/gate.sh" "$w/repo/proj" FalseLeaf
