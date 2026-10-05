#!/bin/bash
# The gate for a Lean tree in Graphene's layout (Challenge.lean, Spec/, Proofs/, Gate/; see README.md).
#
#   GATE_TRUSTED_REF=<commit> GATE_TRUSTED_LAKE=<dir> gate.sh PROJECT_DIR LEAF [LEAF...]
#
# PROJECT_DIR  the candidate: a Lake project inside a git repository (Graphene's check worktree).
# LEAF         a file stem under Proofs/ (SqMod4 -> Proofs/SqMod4.lean, theorem sqMod4).
# GATE_TRUSTED_REF   the commit that holds the approved tree. Every read-only file (lean-toolchain,
#                    lakefile, lake-manifest.json, Challenge.lean, Spec/, Gate/) is taken from it with
#                    `git show`, never from the candidate; only Proofs/ comes from the candidate.
# GATE_TRUSTED_LAKE  a .lake made from that commit alone (`lake exe cache get`, `lake build Challenge
#                    Spec`), never by a candidate's build. It is cloned, never written.
# GATE_TOOLS         where install-tools.sh built its tools (default ~/.cache/graphene-lean-tools).
# GATE_COMPARATOR    local (default: comparator on this machine with its fake-landrun shim, i.e. no
#                    sandbox of its own), docker (real landrun in Docker; projects with no Lake
#                    dependencies only, see docker/comparator.sh) or off.
# GATE_SAFEVERIFY    on (default) or off. With Mathlib it loads four Mathlib environments per leaf.
# GATE_WORK          scratch directory (default: a new one under $TMPDIR, removed unless GATE_KEEP=1).
#
# Everything that loads candidate code (b-e) runs under macOS sandbox-exec: no network, and no file
# writes except the proof modules' build outputs and a private tmp. Elsewhere it runs unsandboxed and
# the lines say so.
# Prints one line per layer, "(x) name  verdict  seconds  detail", then "gate: PASS" or "gate: FAIL".
# Exits 0 only if every layer passed (a skipped layer fails the gate unless GATE_ALLOW_SKIP=1);
# 1 otherwise; 2 on a usage error.
set -uo pipefail
export PATH="$HOME/.elan/bin:$PATH"
ALLOWED="propext Classical.choice Quot.sound"
[ $# -ge 2 ] || { sed -n '2,24p' "$0"; exit 2; }
here=$(cd "$(dirname "$0")" && pwd)
proj=$(cd "$1" && pwd -P) || exit 2
shift
leaves=("$@")
ref=${GATE_TRUSTED_REF:?set GATE_TRUSTED_REF to the commit that holds the approved tree}
tlake=${GATE_TRUSTED_LAKE:?set GATE_TRUSTED_LAKE to a .lake built from the trusted commit only}
tools=${GATE_TOOLS:-$HOME/.cache/graphene-lean-tools}
work=${GATE_WORK:-$(mktemp -d "${TMPDIR:-/tmp}/gate.XXXXXX")}
[ -n "${GATE_WORK:-}" ] || [ "${GATE_KEEP:-0}" = 1 ] || trap 'rm -rf "$work"' EXIT
b=$work/build
logs=$work/logs
rm -rf "$b" "$logs" "$work/tmp" && mkdir -p "$b" "$logs" "$work/tmp"
now() { perl -MTime::HiRes=time -e 'printf "%.1f", time'; }
since() { perl -e 'printf "%.1f", $ARGV[1] - $ARGV[0]' "$1" "$(now)"; }
failed=0
skipped=0
line() { # layer verdict t0 detail
  printf '%-20s %-5s %7ss  %s\n' "$1" "$2" "$(since "$3")" "$4"
  [ "$2" = FAIL ] && failed=1
  [ "$2" = skip ] && skipped=1
  return 0
}
thm() { printf '%s%s' "$(printf %s "${1:0:1}" | tr '[:upper:]' '[:lower:]')" "${1:1}"; }
if command -v sandbox-exec >/dev/null; then
  sandboxed="sandboxed"
  sbx() {
    sandbox-exec -p "(version 1)(allow default)(deny network*)(deny file-write*)
      (allow file-write* (subpath \"$b/.lake/build/lib/lean/Proofs\") (subpath \"$b/.lake/build/ir/Proofs\")
        (subpath \"$work/tmp\") (subpath \"/dev\"))" env TMPDIR="$work/tmp" "$@"
  }
else
  sandboxed="UNSANDBOXED"
  sbx() { "$@"; }
fi
# Runs "$@" once per leaf, one leaf at a time, with {} replaced by the leaf; output in
# $logs/<tag>.<leaf>; leaves whose command failed are left in $bad. Never in parallel: with
# `import Mathlib` every run holds one or more Mathlib environments, and on this 18 GiB Mac three at
# once pushed swap past 29 GB and free disk under 12 GB (../mechanics/README.md, the memory incident).
per_leaf() {
  local tag=$1; shift
  local leaf
  bad=()
  for leaf in "${leaves[@]}"; do
    (cd "$b" && "${@//\{\}/$leaf}") >"$logs/$tag.$leaf" 2>&1 || bad+=("$leaf")
  done
}

# (a) Trusted inputs: the read-only files from the trusted commit, the trusted .lake cloned.
t0=$(now)
repo=$(git -C "$proj" rev-parse --show-toplevel) || exit 2
prefix=$(git -C "$proj" rev-parse --show-prefix)
git -C "$repo" rev-parse --verify -q "$ref^{commit}" >/dev/null || { echo "unknown GATE_TRUSTED_REF $ref"; exit 2; }
trusted=$(git -C "$repo" ls-tree -r --name-only "$ref" -- "$prefix" | sed "s|^$prefix||" |
  grep -E '^(lean-toolchain|lakefile\.(toml|lean)|lake-manifest\.json|Challenge\.lean|(Spec|Gate)/.*\.lean)$')
differ=()
for f in $trusted; do
  mkdir -p "$b/$(dirname "$f")"
  git -C "$repo" show "$ref:$prefix$f" >"$b/$f"
  cmp -s "$b/$f" "$proj/$f" || differ+=("$f")
done
# A file the tree does not know, next to the read-only ones, is also a change to them.
for f in $(cd "$proj" && ls lakefile.* Challenge.lean Spec/*.lean Gate/*.lean 2>/dev/null); do
  [ -f "$b/$f" ] || differ+=("$f (not in the trusted tree)")
done
mkdir -p "$b/Proofs" && cp "$proj"/Proofs/*.lean "$b/Proofs/"
for leaf in "${leaves[@]}"; do
  [ -f "$b/Proofs/$leaf.lean" ] && [ -f "$b/Spec/$leaf.lean" ] && [ -f "$b/Gate/$leaf.lean" ] ||
    differ+=("$leaf: a Proofs/Spec/Gate file is missing")
done
cp -cR "$tlake" "$b/.lake" 2>/dev/null || cp -R "$tlake" "$b/.lake" # APFS clone where it can
rm -rf "$b/.lake/build/lib/lean/Proofs" "$b/.lake/build/ir/Proofs"
mkdir -p "$b/.lake/build/lib/lean/Proofs" "$b/.lake/build/ir/Proofs"
if [ ${#differ[@]} -eq 0 ]; then
  line "(a) trusted inputs" pass "$t0" "$(echo $trusted | wc -w | tr -d ' ') files from $ref; none differed; .lake cloned"
else
  line "(a) trusted inputs" FAIL "$t0" "differ from $ref (the trusted copies are used): ${differ[*]:-}"
fi

# The trusted modules are built before any candidate code runs.
t0=$(now)
tb=1
for m in Challenge $(printf 'Spec.%s ' "${leaves[@]}"); do
  (cd "$b" && lake build "$m") >>"$logs/trusted-build" 2>&1 || { tb=0; break; }
done
if [ $tb = 1 ]; then
  line "    trusted build" pass "$t0" "Challenge, Spec.* (reused from the trusted .lake when unchanged)"
else
  line "    trusted build" FAIL "$t0" "$(grep -m1 error: "$logs/trusted-build")"
fi

# (b) lake build of the proof modules.
t0=$(now)
# One leaf per `lake build`: Lake builds the modules it is given in parallel and has no jobs flag.
built=1
for leaf in "${leaves[@]}"; do
  (cd "$b" && sbx lake build "Proofs.$leaf") >>"$logs/build" 2>&1 || { built=0; break; }
done
if [ $built = 1 ]; then
  n=$(grep -c "declaration uses .sorry." "$logs/build")
  line "(b) lake build" pass "$t0" "$(printf 'Proofs.%s ' "${leaves[@]}")($sandboxed; sorry warnings: $n)"
else
  line "(b) lake build" FAIL "$t0" "($sandboxed) $(grep -m1 -E '^error' "$logs/build")"
  echo "gate: FAIL (nothing was built, so the other layers did not run; logs in $logs)"
  exit 1
fi

# (c) Per leaf: the Gate file's type assertion, and #print axioms within the allowed three.
t0=$(now)
per_leaf gate sbx lake env lean Gate/{}.lean
detail=""
for leaf in "${leaves[@]}"; do
  t=$(thm "$leaf")
  # `lean` prints the Gate file's own messages only (an import's are not replayed), and prints an
  # info message bare: 'sqMod4' depends on axioms: [propext]
  axline="^'$t' (depends on axioms: \[.*\]|does not depend on any axioms)$"
  ax=$(grep -E "$axline" "$logs/gate.$leaf" | tail -1 |
    sed -E 's/.*depends on axioms: \[(.*)\]$/\1/; s/.*does not depend on any axioms$//; s/,//g')
  verdict=ok
  if [[ " ${bad[*]:-} " == *" $leaf "* ]]; then
    verdict="type: $(grep -m1 -E 'error' "$logs/gate.$leaf" | cut -c1-140)"
  elif ! grep -qE "$axline" "$logs/gate.$leaf"; then
    verdict="no #print axioms line for $t"
  else
    for a in $ax; do [[ " $ALLOWED " == *" $a "* ]] || verdict="axiom not allowed: $a"; done
  fi
  [ "$verdict" = ok ] || bad+=("$leaf")
  detail+="$t: ${verdict/ok/[${ax// /, }]}; "
done
if [ ${#bad[@]} -eq 0 ]; then line "(c) type + axioms" pass "$t0" "$detail"; else line "(c) type + axioms" FAIL "$t0" "$detail"; fi

# (d) Kernel replay of each proof module (leanchecker, shipped with Lean since v4.28.0).
t0=$(now)
per_leaf leanchecker sbx lake env leanchecker Proofs.{}
if [ ${#bad[@]} -eq 0 ]; then
  line "(d) kernel replay" pass "$t0" "leanchecker $(printf 'Proofs.%s ' "${leaves[@]}")"
else
  line "(d) kernel replay" FAIL "$t0" "leanchecker rejected ${bad[*]:-}: $(head -2 "$logs/leanchecker.${bad[0]}" | tr '\n' ' ' | cut -c1-160)"
fi

# (e) Challenge against solution: SafeVerify, then comparator.
t0=$(now)
sv=$tools/SafeVerify/.lake/build/bin/safe_verify
if [ "${GATE_SAFEVERIFY:-on}" = off ]; then
  line "(e) SafeVerify" skip "$t0" "GATE_SAFEVERIFY=off"
elif [ -x "$sv" ]; then
  per_leaf safeverify sbx lake env "$sv" .lake/build/lib/lean/Spec/{}.olean .lake/build/lib/lean/Proofs/{}.olean
  if [ ${#bad[@]} -eq 0 ]; then
    line "(e) SafeVerify" pass "$t0" "Spec.<leaf>.olean against Proofs.<leaf>.olean"
  else
    line "(e) SafeVerify" FAIL "$t0" "rejected ${bad[*]:-}: $(grep -h -m1 -E 'Found a problem|error|uncaught' "$logs/safeverify.${bad[0]}" | cut -c1-160)"
  fi
else
  line "(e) SafeVerify" skip "$t0" "not built: run install-tools.sh safeverify"
fi

t0=$(now)
mode=${GATE_COMPARATOR:-local}
cmp=$tools/comparator/.lake/build/bin/comparator
for leaf in "${leaves[@]}"; do
  printf '{"challenge_module":"Spec.%s","solution_module":"Proofs.%s","theorem_names":["%s"],"permitted_axioms":["propext","Quot.sound","Classical.choice"]}\n' \
    "$leaf" "$leaf" "$(thm "$leaf")" >"$work/tmp/comparator-$leaf.json"
done
if [ "$mode" = local ] && [ -x "$cmp" ]; then
  # comparator's own sandbox (landrun) is Linux only; its repository ships this shim for macOS.
  export COMPARATOR_LANDRUN=$tools/comparator/scripts/fake-landrun.sh
  export COMPARATOR_LEAN4EXPORT=$tools/comparator/.lake/packages/lean4export/.lake/build/bin/lean4export
  per_leaf comparator sbx lake env "$cmp" "$work/tmp/comparator-{}.json"
  if [ ${#bad[@]} -eq 0 ]; then
    line "(e) comparator" pass "$t0" "no landrun (fake-landrun shim; $sandboxed by this script)"
  else
    line "(e) comparator" FAIL "$t0" "rejected ${bad[*]:-}: $(grep -h -m1 -E 'uncaught|error' "$logs/comparator.${bad[0]}" | cut -c1-160)"
  fi
elif [ "$mode" = docker ]; then
  if DOCKER_WORK=${DOCKER_WORK:-$work/docker} "$here/docker/comparator.sh" "$b" "${leaves[@]}" \
    >"$logs/comparator" 2>"$logs/comparator.err"; then
    line "(e) comparator" pass "$t0" "landrun in Docker: $(tr '\n' ' ' <"$logs/comparator")"
  else
    line "(e) comparator" FAIL "$t0" "landrun in Docker: $(tr '\n' ' ' <"$logs/comparator") $(grep -m1 -E 'uncaught|error|comparator.sh' "$logs/comparator.err" | cut -c1-160)"
  fi
else
  line "(e) comparator" skip "$t0" "GATE_COMPARATOR=$mode (or not built: install-tools.sh comparator)"
fi

if [ $failed = 1 ]; then
  echo "gate: FAIL (logs in $logs)"
elif [ $skipped = 1 ] && [ "${GATE_ALLOW_SKIP:-0}" != 1 ]; then
  echo "gate: FAIL (a layer was skipped; GATE_ALLOW_SKIP=1 accepts that)"; failed=1
else
  echo "gate: PASS$([ $skipped = 1 ] && echo ' (with a layer skipped)')"
fi
exit $failed
