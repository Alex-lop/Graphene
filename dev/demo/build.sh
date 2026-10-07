#!/usr/bin/env bash
# The rough cut: film the demo run scene by scene with VHS, in real time, and assemble it with the
# narration as subtitles. dev/demo/build.py says how; dev/demo/STORYBOARD.md is what it films.
#   dev/demo/build.sh [--rehearsal] [--take DIR] [--size 80x24]
exec python3 "$(dirname "$0")/build.py" "$@"
