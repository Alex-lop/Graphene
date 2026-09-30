#!/bin/bash
# Runs inside the container (see comparator.sh): Lean and comparator into the tmpfs /sandbox, the
# project copied there without its .lake, then comparator once per leaf.
set -euo pipefail
now() { date +%s.%N; }
since() { awk -v a="$1" -v b="$(now)" 'BEGIN{printf "%.1f", b-a}'; }
t0=$(now)
tc=/work/lean-4.34.1-linux_aarch64.tar.zst
[ -f $tc ] || curl -sSfL -o $tc https://releases.lean-lang.org/lean4/v4.34.1/lean-4.34.1-linux_aarch64.tar.zst
tar --zstd -xf $tc -C /sandbox
export HOME=/sandbox/home PATH=/sandbox/lean-4.34.1-linux_aarch64/bin:$PATH
mkdir -p $HOME /sandbox/bin
if ! [ -x /work/bin/comparator ]; then
  TOOLS_DIR=/sandbox/tools bash /gate/install-tools.sh comparator >&2
  mkdir -p /work/bin
  cp /sandbox/tools/comparator/.lake/build/bin/comparator \
    /sandbox/tools/comparator/.lake/packages/lean4export/.lake/build/bin/lean4export /work/bin/
fi
cp /work/bin/comparator /work/bin/lean4export /sandbox/bin/
export COMPARATOR_LEAN4EXPORT=/sandbox/bin/lean4export
mkdir /sandbox/proj && (cd /project && tar --exclude=.lake -cf - .) | tar -xf - -C /sandbox/proj
cd /sandbox/proj
echo "setup (toolchain into tmpfs, comparator, project): $(since "$t0")s" >&2
rc=0
for leaf in "$@"; do
  thm="$(printf %s "${leaf:0:1}" | tr '[:upper:]' '[:lower:]')${leaf:1}"
  cfg=/sandbox/comparator-$leaf.json
  printf '{"challenge_module":"Spec.%s","solution_module":"Proofs.%s","theorem_names":["%s"],"permitted_axioms":["propext","Quot.sound","Classical.choice"]}\n' \
    "$leaf" "$leaf" "$thm" >"$cfg"
  t0=$(now)
  if lake env /sandbox/bin/comparator "$cfg" >&2; then v=pass; else v=FAIL; rc=1; fi
  echo "comparator $leaf: $v $(since "$t0")s"
done
exit $rc
