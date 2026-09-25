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

from graphene_map import tokenfactory as tf  # noqa: E402


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


def test_without_a_key_nothing_is_sent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    assert access.main(["--sandbox", "none", "--out", str(tmp_path / "a.json")]) == 1
    assert "NEBIUS_API_KEY is not set in this shell; nothing was sent" in capsys.readouterr().out


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
