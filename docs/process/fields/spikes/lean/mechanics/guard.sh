#!/bin/bash
# Runs CMD, and kills it (and its process group) if free disk on $HOME falls under MIN_FREE_GB or it
# runs longer than MAX_SECONDS. Every 30 s it prints free disk, swap used and the command's resident
# memory; it polls every 2 s. Usage: guard.sh MIN_FREE_GB MAX_SECONDS CMD [ARGS...]
set -u
min=$1 max=$2; shift 2
set -m # the command gets its own process group, so the kill reaches lake's children
"$@" &
pid=$!
start=$(date +%s) last=0
while kill -0 $pid 2>/dev/null; do
  sleep 2
  free=$(df -k "$HOME" | awk 'NR==2{printf "%d", $4/1024}') # MB
  el=$(($(date +%s) - start))
  if [ "$free" -lt $((min * 1024)) ] || [ "$el" -gt "$max" ]; then
    echo "guard: killing after ${el}s (free ${free} MB, limit ${min} GB; time limit ${max}s)"
    kill -TERM -$pid 2>/dev/null; sleep 5; kill -KILL -$pid 2>/dev/null
    wait $pid; exit 124
  fi
  if [ $((el - last)) -ge 30 ]; then
    last=$el
    rss=$(ps -o rss= -p "$(pgrep -g $pid | paste -sd, -)" 2>/dev/null | awk '{s+=$1} END{printf "%d", s/1024}')
    echo "guard: ${el}s free=${free}MB swap_used=$(sysctl -n vm.swapusage | awk '{print $6}') rss=${rss}MB"
  fi
done
wait $pid
