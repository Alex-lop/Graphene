#!/usr/bin/env bash
# The rough cut: film the demo run scene by scene with VHS, in real time, and assemble it with the
# narration as subtitles. docs/demo/build.py says how; docs/demo/STORYBOARD.md is what it films.
#   docs/demo/build.sh [--rehearsal] [--take DIR] [--size 80x24]
exec python3 "$(dirname "$0")/build.py" "$@"
