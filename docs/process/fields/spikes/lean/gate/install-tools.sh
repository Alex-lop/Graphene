#!/bin/bash
# Builds the gate's Lean tools for Lean v4.34.1 at pinned revisions, on macOS or Linux.
#
#   TOOLS_DIR=<dir> install-tools.sh [repl] [comparator] [safeverify] [paranoia]
#
# Every tool that reads .olean files must be compiled by the same Lean as the project (an .olean
# carries the githash of the Lean that wrote it), so each tool's lean-toolchain is set to v4.34.1
# here even where the tool's own tag says v4.34.0. leanchecker needs nothing: it ships with the
# toolchain since v4.28.0. landrun (comparator's sandbox) is Linux only: see docker/ in this dir.
set -euo pipefail
TOOLCHAIN=leanprover/lean4:v4.34.1
T=${TOOLS_DIR:-$HOME/.cache/graphene-lean-tools}
export PATH="$HOME/.elan/bin:$PATH"
mkdir -p "$T"

fetch() { # dir url rev
  [ -d "$T/$1/.git" ] || git clone -q "$2" "$T/$1"
  git -C "$T/$1" fetch -q --tags origin
  git -C "$T/$1" checkout -q --force "$3"
  echo "$TOOLCHAIN" >"$T/$1/lean-toolchain"
}

tools=("$@")
[ $# -gt 0 ] || tools=(repl comparator safeverify)
for t in "${tools[@]}"; do
  case $t in
  repl) # leanprover-community/repl, tag v4.34.0 (no v4.34.1 tag exists)
    fetch repl https://github.com/leanprover-community/repl 193cf4bb9a22bb3fc6d25774f0fe6a70db1fd6ee
    (cd "$T/repl" && lake build repl)
    ;;
  comparator) # leanprover/comparator, tag v4.34.0; lean4export pinned by its manifest (076e8e57)
    fetch comparator https://github.com/leanprover/comparator d03acab154d269c06e60e4de7e4cc85deebff94b
    (cd "$T/comparator" && lake build lean4export comparator)
    ;;
  safeverify) # GasStationManager/SafeVerify main; pins v4.27.0 and requires Mathlib, which its
    # code never imports: drop that require so the tool does not bring a second Mathlib.
    fetch SafeVerify https://github.com/GasStationManager/SafeVerify b291b588a53999a7e837dda61c7dbfe8c550c814
    (cd "$T/SafeVerify" &&
      sed -i.bak -e '/require mathlib from git/,+1d' \
        -e 's|lean4-cli.git" @ "v4.27.0"|lean4-cli.git" @ "v4.34.0"|' lakefile.lean &&
      rm -f lakefile.lean.bak lake-manifest.json &&
      # Lean 4.34 made CollectAxioms.collect private; use the public Lean.collectAxioms. Note that
      # for an *imported* constant it reads the axiom list the imported .olean recorded about itself
      # (src/lean/Lean/Util/CollectAxioms.lean); the replayed file's own constants are still walked.
      python3 - <<'EOF'
p = "Main.lean"
s = open(p).read()
s = s.replace(
    "def processFileDeclarations (env : Environment) : HashMap Name Info := Id.run do",
    "def axiomsOf (env : Environment) (n : Name) : IO (Array Name) :=\n"
    "  (Lean.collectAxioms n : CoreM _).toIO' {fileName := \"\", fileMap := default} {env := env}\n\n"
    "def processFileDeclarations (env : Environment) : IO (HashMap Name Info) := do")
s = s.replace(
    "      let (_, s) := (CollectAxioms.collect ci.name).run env |>.run {}\n"
    "      out := out.insert ci.name ⟨ci, s.axioms⟩",
    "      out := out.insert ci.name ⟨ci, ← axiomsOf env ci.name⟩")
s = s.replace("return (processFileDeclarations env, env)", "return (← processFileDeclarations env, env)")
s = s.replace(
    "          let (_, s) := (CollectAxioms.collect name).run submissionEnv |>.run {}\n"
    "          supplementedDecls := supplementedDecls.insert name ⟨ci, s.axioms⟩",
    "          supplementedDecls := supplementedDecls.insert name ⟨ci, ← axiomsOf submissionEnv name⟩")
assert "CollectAxioms.collect" not in s
open(p, "w").write(s)
EOF
      lake update && lake build safe_verify)
    ;;
  paranoia) # oOo0oOo/LeanParanoia main (2025-11-27, Lean v4.25.0); depends on the archived
    # lean4checker repo, whose Replay now lives in Lean core as Lean.Replay. This port builds, but its
    # replay of core modules then fails on correct proofs: run it with --trust-modules Init,Std,Lean.
    fetch LeanParanoia https://github.com/oOo0oOo/LeanParanoia 11c2385ade3cc417d69ce837bfda9d2c5b1d61ab
    (cd "$T/LeanParanoia" &&
      python3 - <<'EOF'
import re
p = "lakefile.toml"
s = open(p).read()
s = re.sub(r'\n\[\[require\]\]\nname = "lean4checker"\n[^\[]*', "\n", s)
open(p, "w").write(s)
p = "LeanParanoia/Checker.lean"
s = open(p).read().replace("import Lean4Checker.Replay", "import Lean.Replay")
s = s.replace("baseEnv.replay' newConstants", "baseEnv.replay newConstants")
open(p, "w").write(s)
EOF
      rm -f lake-manifest.json && lake update && lake build paranoia)
    ;;
  *) echo "unknown tool: $t" >&2; exit 2 ;;
  esac
  echo "built $t in $T"
done
