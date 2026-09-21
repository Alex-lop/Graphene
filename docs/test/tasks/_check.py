"""What the three accept.py files share: run checks in a finished repo, print the same JSON.

A check is (name, callable). The callable returns a bool, or (bool, note). An exception is a
failure and its text is the note, so a check that cannot even import counts as failed and says why.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # docs/test, so `make_task` imports

from make_task import TASKS  # noqa: E402


def run(repo, *argv, timeout=180):
    """Run python3 with these arguments inside the repo. Returns (exit code, output)."""
    done = subprocess.run(
        [sys.executable, *argv], cwd=str(repo), capture_output=True, text=True, timeout=timeout
    )
    return done.returncode, (done.stdout + done.stderr).strip()


def unchanged(repo, task, rel):
    """Is this file byte-identical to the one make_task.py laid down?"""
    path = Path(repo) / rel
    if not path.exists():
        return False, f"{rel} is gone"
    if path.read_text(encoding="utf-8") != TASKS[task][rel]:
        return False, f"{rel} was edited"
    return True, ""


def passes(repo, module):
    code, out = run(repo, "-m", "unittest", "-q", module)
    return code == 0, "" if code == 0 else out[-400:]


def report(checks):
    details = []
    for name, fn in checks:
        try:
            got = fn()
        except Exception as exc:  # a check that blew up is a check that failed
            got = (False, f"{type(exc).__name__}: {exc}")
        ok, note = got if isinstance(got, tuple) else (got, "")
        details.append({"check": name, "ok": bool(ok), "note": "" if ok else str(note)[:400]})
    print(
        json.dumps(
            {
                "passed": sum(1 for d in details if d["ok"]),
                "failed": sum(1 for d in details if not d["ok"]),
                "details": details,
            },
            indent=2,
        )
    )
    return 0


def repo_arg(argv):
    if len(argv) != 2:
        sys.stderr.write(f"usage: {Path(argv[0]).name} <repo>\n")
        raise SystemExit(2)
    return Path(argv[1]).expanduser().resolve()
