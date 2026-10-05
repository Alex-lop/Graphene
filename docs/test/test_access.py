"""docs/test/access.py against the recorded fake and the Docker sandbox: what it says about the live
list, a tool call per Nemotron model and a misfire, and the sandbox's steps, each timed."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import access  # noqa: E402
from fake_tokenfactory import Fake, call  # noqa: E402

from graphene_map.nemotron import tokenfactory as tf  # noqa: E402


def test_it_names_the_ids_and_which_model_misfires(tmp_path, monkeypatch, capsys):
    def reply(body):
        if "Ultra" in body["model"]:
            return {"content": "It is 85 degrees in Dallas."}  # answers in words: a misfire
        return call("get_current_weather", city="Dallas", unit="fahrenheit")

    with Fake([reply] * 5) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        code = access.main(["--sandbox", "none", "--out", str(tmp_path / "a.json")])
    said = capsys.readouterr().out
    assert code == 1  # a misfire is a failure
    assert "`nvidia/Nemotron-3-Nano-fake` (nano): $0.05 in, $0.20 out per million tokens" in said
    assert "one tool call to `nvidia/Nemotron-3-Super-fake`: a tool call, as asked" in said
    assert "one tool call to `nvidia/Nemotron-3-Ultra-fake`: MISFIRE: no tool call" in said
    report = json.loads((tmp_path / "a.json").read_text())
    assert report["roles"]["ultra"] == "nvidia/Nemotron-3-Ultra-fake" and "fake-key" not in json.dumps(report)
    assert f.requests[0]["tools"][0]["function"]["name"] == "get_current_weather"


def test_a_project_sandboxes_refuse_is_one_line_saying_what_to_do_and_token_factory_still_passes(
    tmp_path, monkeypatch, capsys
):
    """What rung 1 met live (2026-09-29): Token Factory answered and Sandboxes refused the project. From a
    stub SDK raising its own ForbiddenError (nothing sent to ConTree): the refusal is one line saying
    what the key lacks and where access is asked for, the report marks it refused, and the check passes
    on Token Factory's answers."""
    contree_sdk = pytest.importorskip("contree_sdk")
    from fake_faults import Forbidding, persons_shell

    persons_shell(monkeypatch)
    monkeypatch.setattr(contree_sdk, "ContreeSync", Forbidding)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "project-fake")
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "off")
    with Fake([call("get_current_weather", city="Dallas", unit="fahrenheit")] * 3) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        code = access.main(["--sandbox", "contree", "--out", str(tmp_path / "a.json")])
    said = capsys.readouterr().out
    assert code == 0
    assert ("\n- Sandboxes refused this project (403): its key lacks import, spawn there; request access at "
            "tokenfactory.nebius.com/sandboxes/about\n") in said  # fmt: skip
    assert "ForbiddenError" not in said and "FAILED" not in said
    box = json.loads((tmp_path / "a.json").read_text())["sandbox"]
    assert box["ok"] is False and box["refused"] is True


def test_the_docs_suite_never_reaches_the_real_keychain(monkeypatch):
    from graphene_map.nemotron import keys

    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setattr(keys.subprocess, "run", lambda *a, **k: pytest.fail("the keychain was asked"))
    assert keys.find() is None


def test_without_a_key_nothing_is_sent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    assert access.main(["--sandbox", "none", "--out", str(tmp_path / "a.json")]) == 1
    said = capsys.readouterr().out
    assert "NEBIUS_API_KEY is not set in this shell and no key is in the keychain; nothing was sent" in said


@pytest.mark.skipif(subprocess.run(["docker", "info"], capture_output=True).returncode != 0
                    if Path("/usr/local/bin/docker").exists() or Path("/usr/bin/docker").exists() else True,
                    reason="needs a running Docker")  # fmt: skip
def test_the_sandbox_steps_are_timed(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    access.main(["--sandbox", "docker", "--out", str(tmp_path / "a.json")])
    report = json.loads((tmp_path / "a.json").read_text())
    assert report["sandbox"]["ok"] is True
    steps = {"make and run (import the image if needed)", "fork from the image it made", "two forks at once"}
    assert set(report["sandbox"]["steps"]) == steps
    assert "Sandboxes (docker): works; make and run" in capsys.readouterr().out


def test_a_stop_during_the_sandbox_smoke_removes_its_container(tmp_path):
    """The ladder stops access.py as it stops every command, with a TERM to its process group: the
    container the smoke was running is removed on the way out. The docker here is a stand-in that holds
    `start` and writes down every call; no key, so nothing is sent."""
    import os
    import signal
    import time

    calls, held = tmp_path / "calls", tmp_path / "held"
    docker = tmp_path / "bin" / "docker"
    docker.parent.mkdir()
    docker.write_text(f'#!/bin/sh\necho "$@" >> {calls}\n'
                      f'[ "$1" = start ] && touch {held} && exec sleep 60\necho made\n')  # fmt: skip
    docker.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEBIUS_", "GRAPHENE_", "CONTREE_"))}
    env |= {"PATH": f"{docker.parent}{os.pathsep}{env['PATH']}", "GRAPHENE_KEYCHAIN": "off"}
    here = Path(__file__).resolve().parent
    smoke = subprocess.Popen([sys.executable, str(here / "access.py"), "--sandbox", "docker", "--out",
                              str(tmp_path / "a.json")], env=env, start_new_session=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # fmt: skip
    deadline = time.monotonic() + 60
    while not held.exists():
        assert smoke.poll() is None and time.monotonic() < deadline, smoke.communicate()
        time.sleep(0.05)
    os.killpg(smoke.pid, signal.SIGTERM)
    smoke.communicate(timeout=60)
    said = calls.read_text().splitlines()
    box = next(ln.split()[3] for ln in said if ln.startswith("create "))
    assert f"rm -f {box}" in said, said
