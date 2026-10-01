#!/bin/bash
# Runs one command from the current directory and appends to logs/<name>.log: the time, the command,
# its combined output, its exit code, wall seconds and peak memory of the largest process (macOS
# /usr/bin/time -l; for `lake`, that is lake's own process, not always the `lean` it starts).
# Usage: run.sh NAME CMD [ARGS...]
set -u
name=$1; shift
log="$(cd "$(dirname "$0")" && pwd)/logs/$name.log"
mkdir -p "$(dirname "$log")"
t=$(mktemp)
echo "=== $(date '+%F %T %Z') cwd=$(pwd) load=[$(sysctl -n vm.loadavg)] swap=[$(sysctl -n vm.swapusage)]" >>"$log"
echo "\$ $*" >>"$log"
/usr/bin/time -l -o "$t" "$@" >>"$log" 2>&1
rc=$?
wall=$(awk '/ real /{print $1}' "$t")
rss=$(awk '/maximum resident set size/{printf "%.0f", $1/1048576}' "$t")
echo "=== rc=$rc wall=${wall}s maxrss=${rss}MB" >>"$log"
rm -f "$t"
echo "rc=$rc wall=${wall}s maxrss=${rss}MB"
exit $rc
