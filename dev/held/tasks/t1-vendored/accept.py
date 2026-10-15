#!/usr/bin/env python3
"""T1's visible check: the repository's own tests, the ones the agent can run.

python3 accept.py <repo>
"""

import subprocess
import sys

sys.exit(subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=sys.argv[1]).returncode)
