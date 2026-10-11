#!/usr/bin/env bash
# The night's spend, added up from what the sessions themselves reported, never typed by hand.
#
#   dev/process/prove/ledger.sh OUT...        prints a table and appends it to dev/process/prove/ledger.md
#
# Two sources: every `claude -p` result under the given directories (a `--output-format json` object or
# a stream's last result line, in *.json, *.jsonl and the stores' runs/*.txt; a session that was resumed
# reports its running total, so the largest figure per session id is taken), and each repo's
# `graphene plan record`, whose "the planner's bill" is the one cost no session file holds (the
# executors' bills are in both, so only the planner's is added from the record).
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 1 ] || { sed -n '2,11p' "$0"; exit 2; }
python3 "$PROVE/ledger.py" "$@" | tee -a "$PROVE/ledger.md"
