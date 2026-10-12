#!/usr/bin/env python3
"""Run a command in a session of its own and kill its whole process group after N seconds.

pgtimeout.py N command [args...]      exit: the command's, or 124 when it was killed"""

import os
import signal
import subprocess
import sys

seconds = float(sys.argv[1])
proc = subprocess.Popen(sys.argv[2:], start_new_session=True)
try:
    sys.exit(proc.wait(timeout=seconds))
except subprocess.TimeoutExpired:
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    print(f"pgtimeout: killed after {seconds:.0f} s", file=sys.stderr)
    sys.exit(124)
