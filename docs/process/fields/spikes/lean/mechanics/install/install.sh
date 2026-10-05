#!/bin/bash
# Records each step's command, time and result to install.log
set -u
LOG=$(dirname "$0")/install.log
step() { echo "=== $(date '+%F %T') \$ $*" >>"$LOG"; local t0=$(python3 -c 'import time;print(time.time())'); "$@" >>"$LOG" 2>&1; local rc=$?; local t1=$(python3 -c 'import time;print(time.time())'); echo "=== rc=$rc elapsed=$(python3 -c "print(round($t1-$t0,1))")s" >>"$LOG"; return $rc; }
: >"$LOG"
step curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -o elan-init.sh
step sh elan-init.sh -y --default-toolchain none --no-modify-path
export PATH="$HOME/.elan/bin:$PATH"
step elan --version
step elan toolchain install leanprover/lean4:v4.34.1
step du -sh "$HOME/.elan/toolchains"
mkdir -p base && cd base
printf 'leanprover/lean4:v4.34.1\n' > lean-toolchain
cat > lakefile.toml <<'T'
name = "spike"
defaultTargets = ["Spike"]

[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4.git"
rev = "v4.34.1"

[[lean_lib]]
name = "Spike"
T
mkdir -p Spike && printf 'import Mathlib\n\ntheorem hello : 2 + 2 = 4 := by norm_num\n\n#print axioms hello\n' > Spike/Basic.lean
printf 'import Spike.Basic\n' > Spike.lean
step lake update
step du -sh .lake/packages
step lake exe cache get
step du -sh .lake/packages "$HOME/.cache/mathlib"
step lake build
step lake build
echo DONE >>"$LOG"
