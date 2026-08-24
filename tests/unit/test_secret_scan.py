"""``scripts/secret_scan.py`` must never report a clean scan it did not run.

The scanner's whole job is to be believed. It shells out to git for the file
list, the staged diff and the recent log; if those calls fail and the failure
is swallowed, the scan finds nothing, prints "0 finding(s)" and exits 0 --
and ``scripts/morning_verify.sh`` prints PASS for a step that inspected
nothing. Proven here: git failing is reported as unavailable, not as clean.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "secret_scan.py"


def _load() -> ModuleType:
    name = "graphene_test_secret_scan"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_a_failing_git_is_unavailable_not_empty() -> None:
    module = _load()
    with pytest.raises(module.ScanUnavailable, match="git ls-files failed"):
        module._git("ls-files", "--definitely-not-a-real-flag")


def test_the_scan_refuses_to_pass_where_git_cannot_answer(tmp_path: Path) -> None:
    # tmp_path is outside any repository, so every git call fails. At the
    # baseline this exited 0 with "0 finding(s)" -- a clean bill of health for
    # a directory the scanner never looked at.
    result = subprocess.run(
        (sys.executable, str(SCRIPT), "--commits", "5"),
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert "UNAVAILABLE" in result.stderr, result.stderr
    assert "0 finding(s)" not in result.stdout, result.stdout
