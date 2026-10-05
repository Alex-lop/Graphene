#!/usr/bin/env bash
# The practice ladder, one rung at a time: docs/test/PRACTICE.md says what to type, practice.py what each
# rung does.   practice.sh [N | status] [--dry]
cd "$(dirname "$0")/../.." || exit 1
extra="--extra nemotron"   # live, ConTree's SDK; the dry run's sandbox is Docker and needs none
case " $* " in *" --dry "*) extra="" ;; esac
[ "${PRACTICE_DRY:-}" = 1 ] && extra=""
exec uv run --frozen $extra python docs/test/practice.py "$@"
