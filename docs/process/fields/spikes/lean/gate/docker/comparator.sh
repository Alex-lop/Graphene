#!/bin/bash
# Runs leanprover/comparator on each LEAF inside a linux/arm64 Docker container, with landrun
# (Landlock) as comparator's sandbox.
#
#   DOCKER_WORK=<dir> comparator.sh PROJECT_DIR LEAF [LEAF...]
#
# PROJECT_DIR is a Lake project in the layout (Challenge.lean, Spec/, Proofs/) with no dependencies:
# on Docker Desktop, Landlock denies every read, write and exec on the bind-mounted host directory
# (a "fakeowner" filesystem), so the toolchain, comparator and the project are copied into a tmpfs
# inside the container, and a Mathlib .lake (7.6 GB) does not fit there. DOCKER_WORK keeps the
# downloaded toolchain and the built comparator between runs (/work in the container).
# Prints "comparator <Leaf>: pass|FAIL <seconds>s" per leaf; exits 0 only if every leaf passes.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
W=${DOCKER_WORK:?set DOCKER_WORK to a directory for the toolchain and comparator cache}
mkdir -p "$W"
W=$(cd "$W" && pwd -P)
proj=$(cd "$1" && pwd -P); shift
if grep -q '"url"' "$proj/lake-manifest.json" 2>/dev/null; then
  echo "comparator.sh: $proj has Lake dependencies (Mathlib?); they do not fit in the container's tmpfs" >&2
  exit 2
fi
img=graphene-comparator:v4.34.1
docker image inspect $img >/dev/null 2>&1 || docker build -q --platform linux/arm64 -t $img "$here" >/dev/null
exec docker run --rm --platform linux/arm64 --tmpfs /sandbox:rw,exec,size=6g \
  -v "$W":/work -v "$here/..":/gate:ro -v "$proj":/project:ro $img bash /gate/docker/inside.sh "$@"
