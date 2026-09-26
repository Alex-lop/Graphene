"""The faults the fault tests put under a real `graphene run`. Its executors are processes of their
own, and so is each `graphene node done` they run, where monkeypatch does not reach: ``everywhere``
writes a sitecustomize onto PYTHONPATH (the way coverage.py follows subprocesses) that calls
``install`` in every Python process started after it, and calls it here too, with monkeypatch.
``install`` changes nothing of the product's code: as the environment says (FAULTS_…), no wait through
a backoff, a shorter time limit for a completion or a check, and the sandbox's box."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

SITE = "try:\n    import fake_faults\nexcept ImportError:  # a python that is not the test's\n    pass\n" \
       "else:\n    fake_faults.install(setattr)\n"  # fmt: skip


def everywhere(monkeypatch, tmp_path: Path, **env) -> Path:
    """Install in this process and in every Python process started from now on; ``env`` names the
    faults (FAULTS_TIMEOUT=1, FAULTS_BOX=fake, …). Returns the directory the fakes write to."""
    site, here = tmp_path / "site", tmp_path / "faults"
    site.mkdir(exist_ok=True)
    here.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(SITE)
    path = [str(site), str(Path(__file__).parent), os.environ.get("PYTHONPATH", "")]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in path if p))
    monkeypatch.setenv("FAULTS", str(here))
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    install(monkeypatch.setattr)
    return here


def install(put) -> None:
    if not os.environ.get("FAULTS"):
        return
    from graphene_map import plan
    from graphene_map import tokenfactory as tf

    put(tf, "time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic, time=time.time))
    if os.environ.get("FAULTS_TIMEOUT"):
        put(tf, "TIMEOUT", float(os.environ["FAULTS_TIMEOUT"]))
    if os.environ.get("FAULTS_CHECK_TIMEOUT"):
        put(plan, "CHECK_TIMEOUT", float(os.environ["FAULTS_CHECK_TIMEOUT"]))
