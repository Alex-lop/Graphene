"""The faults the fault tests put under a real `graphene run`. Its executors are processes of their
own, and so is each `graphene node done` they run, where monkeypatch does not reach: ``everywhere``
writes a sitecustomize onto PYTHONPATH (the way coverage.py follows subprocesses) that calls
``install`` in every Python process started after it, and calls it here too, with monkeypatch.
``install`` changes nothing of the product's code: as the environment says (FAULTS_…), no wait through
a backoff, a shorter time limit for a completion or a check, this test's own slots for sandbox
operations, and the sandbox's box."""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from graphene_map import sandbox

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
    put(sandbox, "POOL", Path(os.environ["FAULTS"]) / "pool")  # this test's slots, not the machine's
    if os.environ.get("FAULTS_BOX"):
        box = Killed if os.environ["FAULTS_BOX"] == "killed" else Box
        put(sandbox, "choose", lambda name=None, image=None: box())


def _holds(script: str, name: str) -> bool:
    return bool(os.environ.get(name)) and os.environ[name] in script


class Box:
    """A sandbox that is nowhere: every command exits 0 and changes nothing, and each operation takes
    FAULTS_OP seconds, marked in FAULTS/inflight while it runs, so that the most at once can be counted
    across processes (FAULTS/counts). A script holding FAULTS_RAISE raises, as a box that went away
    does; one holding FAULTS_KILL ends as a killed one does: exit 137, and no list of files."""

    image = sandbox.IMAGE
    ops = 0  # the box's count of its operations, as Contree and Docker keep it

    def _op(self, script: str = "") -> None:
        self.ops += 1
        if _holds(script, "FAULTS_RAISE"):
            raise ConnectionResetError("the sandbox went away")
        inflight = Path(os.environ["FAULTS"]) / "inflight"
        inflight.mkdir(exist_ok=True)
        mark = inflight / uuid.uuid4().hex
        mark.touch()
        try:
            with open(inflight.parent / "counts", "a") as counts:
                counts.write(f"{len(os.listdir(inflight))}\n")
            time.sleep(float(os.environ.get("FAULTS_OP") or 0))
        finally:
            mark.unlink()

    def start(self, tar, script, timeout):
        return self.run(self.image, script, {}, timeout)

    def run(self, image, script, files, timeout):
        self._op(script)
        killed = _holds(script, "FAULTS_KILL")
        return f"{'killed' if killed else 'image'}-{uuid.uuid4().hex[:12]}", 137 if killed else 0, ""

    def read(self, image, path):
        self._op()
        return b"" if image.startswith("killed") else f"0\n{sandbox.END}\n".encode()


class Killed(sandbox.Docker):
    """Docker, whose container for a script holding FAULTS_KILL is killed a second after it starts
    (exit 137), as a sandbox operation killed mid-leaf is. What it makes is listed in FAULTS
    (containers, images), so a test can ask Docker what is left, and clear it."""

    def _docker(self, *args, data=None):
        done = super()._docker(*args, data=data)
        made = {"create": "containers", "commit": "images"}.get(args[0])
        if made and done.returncode == 0:
            with open(Path(os.environ["FAULTS"]) / made, "a") as f:
                f.write(done.stdout.decode().strip() + "\n")
        if args[0] == "create" and _holds(args[-1], "FAULTS_KILL"):
            threading.Thread(target=self._kill, args=(done.stdout.decode().strip(),), daemon=True).start()
        return done

    def _kill(self, box: str) -> None:
        until = time.monotonic() + 60
        while super()._docker("inspect", "-f", "{{.State.Running}}", box).stdout.strip() != b"true":
            if time.monotonic() > until:
                return
            time.sleep(0.2)
        time.sleep(1)
        super()._docker("kill", box)
