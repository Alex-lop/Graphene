#!/usr/bin/env bash
# SafeVerify on ONE leaf of a gate build directory, with a watchdog (the integrator's rule after the
# parallel gate run filled swap): it is stopped if swap use rises more than 4 GB above where it began,
# if free disk falls under 16 GB, or after 900 s.
#   one-safeverify.sh BUILD_DIR LEAF SAFE_VERIFY_BINARY
set -uo pipefail
b=$1 leaf=$2 sv=$3
export PATH="$HOME/.elan/bin:$PATH"
swap() { sysctl -n vm.swapusage | sed -E 's/.*used = ([0-9.]+)M.*/\1/'; }
disk() { df -k "$HOME" | tail -1 | awk '{print int($4/1048576)}'; }
s0=$(swap); peak=$s0; t0=$SECONDS
echo "start $(date +%T): swap used ${s0} MB, disk free $(disk) GB"
[ "$(disk)" -ge 16 ] || { echo "disk under 16 GB: not started"; exit 3; }
(cd "$b" && exec lake env "$sv" ".lake/build/lib/lean/Spec/$leaf.olean" ".lake/build/lib/lean/Proofs/$leaf.olean") &
pid=$!
why=""
while kill -0 $pid 2>/dev/null; do
  sleep 5
  s=$(swap); peak=$(echo "$s $peak" | awk '{print ($1>$2)?$1:$2}')
  if awk -v s="$s" -v s0="$s0" 'BEGIN{exit !(s - s0 > 4096)}'; then why="swap rose more than 4 GB"; fi
  [ "$(disk)" -ge 16 ] || why="disk under 16 GB"
  [ $((SECONDS - t0)) -lt 900 ] || why="900 s"
  if [ -n "$why" ]; then pkill -P $pid; kill $pid; echo "stopped: $why"; break; fi
done
wait $pid; code=$?
echo "end $(date +%T): exit $code after $((SECONDS - t0)) s; swap peak ${peak} MB (start ${s0}), disk free $(disk) GB"
exit $code
