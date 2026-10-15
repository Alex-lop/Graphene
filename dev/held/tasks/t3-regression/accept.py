#!/usr/bin/env python3
"""T3's visible check: the unit tests, the fast loop the repository's AGENTS.md names.

python3 accept.py <repo>
"""

import subprocess
import sys

unit = [sys.executable, "-m", "unittest", "discover", "-q", "-s", "tests/unit"]
sys.exit(subprocess.run(unit, cwd=sys.argv[1]).returncode)
