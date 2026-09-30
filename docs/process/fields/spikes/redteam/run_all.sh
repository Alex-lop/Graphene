#!/usr/bin/env bash
# run_all.sh: the red team. For each exploits/<nn>-<name>/, make a fresh copy-on-write clone of the
# clean core-Lean project, overlay the exploit's files, and run every layer, recording which rejects it.
#
# Layers, in the order a gate would run them:
#   SCOPE       Graphene's boundary (leaf scope = Proofs/Target.lean only). Computed from the overlay's
#               file set here; validated against the real `graphene node done` in ../redteam-graphene
#               (see README "The scope layer"). R iff the exploit changes any file but Proofs/Target.lean.
#   build       lake build Proofs.Target
#   check-leaf  the fast per-leaf check: type assertion + #print axioms, via GateCheck (clean/check-leaf.sh)
#   leanchecker kernel replay (ships with the toolchain)
#   comparator  challenge (Spec) vs solution (Proofs), fake-landrun shim (macOS) — the comparison, not its sandbox
#   safeverify  challenge vs solution, whole-env replay
#   paranoia    reference-free source+replay scan (--trust-modules Init,Std,Lean)
#
# Exploits that would fetch another toolchain or dependency (lean-toolchain, lake-manifest.json) are not
# built: their Lean layers are n/a with that reason, and SCOPE is what refuses them. Core Lean, no
# Mathlib, so every runnable layer takes seconds and there is no memory pressure (see README for why core).
#
# Rerun:  export PATH=$HOME/.elan/bin:$PATH; ./run_all.sh    (writes logs/ and prints the matrix)
set -uo pipefail
export PATH="$HOME/.elan/bin:$PATH"
here=$(cd "$(dirname "$0")" && pwd)
S=${GRAPHENE_SCRATCH:-$(cd "$here/../../../../../.." && pwd)}   # scratchpad/fields root's parent chain
TOOLS=${REDTEAM_TOOLS:-$S/tools}
SV=$TOOLS/SafeVerify/.lake/build/bin/safe_verify
CMP=$TOOLS/comparator/.lake/build/bin/comparator
PARA=$TOOLS/LeanParanoia/.lake/build/bin/paranoia
export COMPARATOR_LANDRUN=$TOOLS/comparator/scripts/fake-landrun.sh
export COMPARATOR_LEAN4EXPORT=$TOOLS/comparator/.lake/packages/lean4export/.lake/build/bin/lean4export
work=${REDTEAM_WORK:-$S/tmp/redteam-run}
logs=$here/logs
rm -rf "$work" && mkdir -p "$work" "$logs"

# Build the clean project once so its .lake carries a warm build the clones share (APFS copy-on-write).
( cd "$here/clean" && lake build >/dev/null 2>&1 )

matrix=$logs/matrix.tsv
: > "$matrix"
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  exploit SCOPE build check-leaf leanchecker comparator safeverify paranoia >> "$matrix"

cmpjson='{"challenge_module":"Spec.Target","solution_module":"Proofs.Target","theorem_names":["target"],"permitted_axioms":["propext","Quot.sound","Classical.choice"]}'

for dir in "$here"/exploits/*/; do
  name=$(basename "$dir")
  # the files this exploit overlays (its scope footprint), relative to the exploit dir, minus README.md
  files=()
  while IFS= read -r f; do files+=("$f"); done < <(cd "$dir" && find . -type f ! -name README.md | sed 's|^\./||' | sort)
  # SCOPE: rejected iff any changed file is not exactly Proofs/Target.lean
  scope=R; [ "${files[*]:-}" = "Proofs/Target.lean" ] && scope=P
  L=$logs/$name; mkdir -p "$L"

  # config exploits that would fetch a toolchain/dependency: do not build them
  if printf '%s\n' "${files[@]}" | grep -qxE 'lean-toolchain|lake-manifest.json'; then
    reason="n/a(would fetch)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$scope" "$reason" "$reason" "$reason" "$reason" "$reason" "$reason" >> "$matrix"
    continue
  fi

  # fresh copy-on-write clone, then overlay the exploit
  W=$work/$name
  cp -cR "$here/clean" "$W" 2>/dev/null || cp -R "$here/clean" "$W"
  rm -rf "$W/.lake/build/lib/lean/Proofs" "$W/.lake/build/ir/Proofs"
  ( cd "$dir" && find . -type f ! -name README.md -exec sh -c 'mkdir -p "$2/$(dirname "$1")"; cp "$1" "$2/$1"' _ {} "$W" \; )
  # if Challenge changed, its .olean and Spec must be rebuilt against it
  if printf '%s\n' "${files[@]}" | grep -qx 'Challenge.lean'; then
    rm -rf "$W/.lake/build/lib/lean/Challenge.olean" "$W/.lake/build/lib/lean/Spec"
  fi

  cd "$W"
  # build (Challenge + Spec + the proof)
  lake build Challenge Spec.Target > "$L/build.log" 2>&1; rc=$?
  lake build Proofs.Target >> "$L/build.log" 2>&1; brc=$?
  build=P; [ $brc -ne 0 ] && build=R
  # if the proof did not build, the later layers cannot run
  if [ $brc -ne 0 ]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$scope" "$build" "n/a(no build)" "n/a(no build)" "n/a(no build)" "n/a(no build)" "n/a(no build)" >> "$matrix"
    continue
  fi

  # check-leaf (type + axioms via GateCheck)
  ./check-leaf.sh Target > "$L/check-leaf.log" 2>&1; rc=$?; cl=P; [ $rc -ne 0 ] && cl=R
  # leanchecker (kernel replay)
  lake env leanchecker Proofs.Target > "$L/leanchecker.log" 2>&1; rc=$?; lc=P; [ $rc -ne 0 ] && lc=R
  # comparator
  printf '%s\n' "$cmpjson" > "$W/cmp.json"
  lake env "$CMP" "$W/cmp.json" > "$L/comparator.log" 2>&1; cm=P
  grep -qi 'okay' "$L/comparator.log" || cm=R
  # safeverify
  lake env "$SV" .lake/build/lib/lean/Spec/Target.olean .lake/build/lib/lean/Proofs/Target.olean > "$L/safeverify.log" 2>&1
  sv=P; grep -qi 'check passed' "$L/safeverify.log" || sv=R
  # paranoia (reference-free; --trust-modules per mechanics finding 7)
  lake env "$PARA" --trust-modules Init,Std,Lean Proofs.Target.target > "$L/paranoia.log" 2>&1
  pa=P; grep -q '"success":true' "$L/paranoia.log" || pa=R

  # compile-time-io: also run the build under macOS sandbox-exec to show the write is denied there,
  # and record whether the unsandboxed build wrote outside .lake (PWNED / changed Challenge.lean).
  if [ "$name" = 15-compile-time-io ]; then
    { echo "unsandboxed: PWNED exists? $( [ -f PWNED ] && echo yes || echo no )"
      echo "unsandboxed: Challenge.lean changed? $(cmp -s Challenge.lean "$here/clean/Challenge.lean" && echo no || echo yes)"; } > "$L/sandbox.log"
    W2=$work/$name-sandboxed
    cp -cR "$here/clean" "$W2" 2>/dev/null || cp -R "$here/clean" "$W2"
    rm -rf "$W2/.lake/build/lib/lean/Proofs" "$W2/.lake/build/ir/Proofs"
    cp "$dir/Proofs/Target.lean" "$W2/Proofs/Target.lean"
    ( cd "$W2" && sandbox-exec -p "(version 1)(allow default)(deny network*)(deny file-write*)
        (allow file-write* (subpath \"$W2/.lake\") (subpath \"/dev\") (subpath \"${TMPDIR:-/tmp}\"))" \
        lake build Proofs.Target ) > "$L/sandboxed-build.log" 2>&1
    echo "sandboxed build rc=$? ; PWNED under sandbox? $( [ -f "$W2/PWNED" ] && echo yes || echo no )" >> "$L/sandbox.log"
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$scope" "$build" "$cl" "$lc" "$cm" "$sv" "$pa" >> "$matrix"
done

echo
column -t -s $'\t' "$matrix"
echo
echo "per-layer logs: $logs/<exploit>/  ;  matrix: $matrix"
