from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import graphene.cli.mission as mission_cli
from graphene.cli.main import main
from graphene.cli.mission import (
    _count_tokens as real_count_tokens,  # bound before the offline fixture patches it
)
from graphene.cli.mission import build_parser, doctor, handle, initialize
from graphene.orchestration.adk_planner import LIVE_GEMINI_MODEL


CANARY = "doctor-probe-canary-4b1e"
CREDENTIAL_NAMES = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_GENAI_USE_VERTEXAI",
)


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_AUTHOR_EMAIL": "fixture@graphene.invalid",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_EMAIL": "fixture@graphene.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(("git", "init", "-q", "-b", "main"), cwd=repository, check=True)
    (repository / "README.md").write_text("# Fixture\n")
    subprocess.run(("git", "add", "--all", "--"), cwd=repository, check=True)
    subprocess.run(
        ("git", "commit", "-q", "-m", "base"),
        cwd=repository,
        env=environment,
        check=True,
    )
    initialize(repository)
    return repository


def _unexpected_call(model: str) -> None:
    raise AssertionError(f"the probe reached the network for {model}")


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ambient credentials, and no route out of the test process."""
    for name in CREDENTIAL_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(mission_cli, "_count_tokens", _unexpected_call)


def _vertex(monkeypatch: pytest.MonkeyPatch, location: str) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", CANARY)
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", location)


def _raise(error: BaseException):
    def _stub(model: str) -> None:
        raise error

    return _stub


def test_probe_reports_the_model_available_after_one_count_tokens_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    _vertex(monkeypatch, "global")
    calls: list[str] = []
    monkeypatch.setattr(mission_cli, "_count_tokens", calls.append)

    report = doctor(repository, probe=True)
    preflight = report["gemini_preflight"]

    assert calls == [LIVE_GEMINI_MODEL]
    assert preflight["model_available"] == {
        "status": "available",
        "model": LIVE_GEMINI_MODEL,
        "location": "global",
        "reason": "one free count_tokens request succeeded",
    }
    assert preflight["proof"] == (
        "one free count_tokens request succeeded; "
        "model identity and output are not proven"
    )
    assert preflight["connectivity_proven"] is True
    assert preflight["live_provider_proven"] is False
    assert report["modes"]["gemini-adk"]["proof"] == (
        "bounded local runtime configured; "
        "connectivity probed once, see gemini_preflight.model_available"
    )
    assert CANARY not in json.dumps(report, sort_keys=True)


def test_probe_reports_an_api_key_model_as_available_without_a_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setenv("GOOGLE_API_KEY", CANARY)
    # Inert in API-key mode, so it must not be echoed as if it routed the call.
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setattr(mission_cli, "_count_tokens", lambda model: None)

    report = doctor(repository, probe=True)
    probe = report["gemini_preflight"]["model_available"]

    assert probe["status"] == "available"
    assert probe["location"] is None
    assert CANARY not in json.dumps(report, sort_keys=True)


def test_the_one_request_is_bounded_by_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doctor must terminate even when the provider never answers."""
    from google import genai

    recorded: dict[str, object] = {}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            recorded.update(kwargs)
            self.models = self

        def count_tokens(self, *, model: str, contents: str) -> None:
            recorded["model"] = model

    monkeypatch.setattr(genai, "Client", _Client)

    real_count_tokens(LIVE_GEMINI_MODEL)

    assert recorded["model"] == LIVE_GEMINI_MODEL
    assert recorded["http_options"] == {"timeout": 10_000}


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (404, "model is not served in the configured GOOGLE_CLOUD_LOCATION"),
        (429, "provider rate limited"),
        (401, "credentials rejected by the provider"),
        (403, "credentials rejected by the provider"),
        (503, "provider unavailable"),
        (400, "provider rejected the request"),
    ],
)
def test_probe_maps_provider_status_codes_to_fixed_reasons(
    code: int, reason: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.genai.errors import APIError

    repository = _repository(tmp_path)
    _vertex(monkeypatch, "us-central1")
    monkeypatch.setattr(
        mission_cli,
        "_count_tokens",
        _raise(APIError(code, {"error": {"message": CANARY, "status": CANARY}})),
    )

    report = doctor(repository, probe=True)
    probe = report["gemini_preflight"]["model_available"]

    assert probe["status"] == "unavailable"
    assert probe["reason"] == reason
    # Only a Vertex region miss earns the `global` hint that fixed 2026-08-23.
    assert ("global" in str(probe.get("hint", ""))) is (code == 404)
    assert report["gemini_preflight"]["connectivity_proven"] is False
    assert CANARY not in json.dumps(report, sort_keys=True)


def test_probe_does_not_blame_the_location_when_an_api_key_model_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.genai.errors import APIError

    repository = _repository(tmp_path)
    monkeypatch.setenv("GOOGLE_API_KEY", CANARY)
    monkeypatch.setattr(
        mission_cli, "_count_tokens", _raise(APIError(404, {"error": {}}))
    )

    probe = doctor(repository, probe=True)["gemini_preflight"]["model_available"]

    assert probe == {
        "status": "unavailable",
        "model": LIVE_GEMINI_MODEL,
        "location": None,
        "reason": "provider rejected the request",
    }


def test_probe_reports_unknown_when_the_request_fails_before_a_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    _vertex(monkeypatch, "us-central1")
    monkeypatch.setattr(mission_cli, "_count_tokens", _raise(OSError(CANARY)))

    report = doctor(repository, probe=True)
    probe = report["gemini_preflight"]["model_available"]

    assert probe["status"] == "unknown"
    assert probe["reason"] == "provider request failed before a response"
    assert "hint" not in probe
    # This branch can fire before any request leaves the process, so the proof
    # line must not claim one was made.
    assert report["gemini_preflight"]["proof"] == (
        "a count_tokens request was attempted but no provider answer arrived; "
        "model availability is not proven"
    )
    assert CANARY not in json.dumps(report, sort_keys=True)


def test_probe_makes_no_request_when_no_credentials_are_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(mission_cli, "_count_tokens", calls.append)

    report = doctor(repository, probe=True)
    preflight = report["gemini_preflight"]

    assert calls == []
    assert preflight["model_available"] == {
        "status": "not_checked",
        "model": LIVE_GEMINI_MODEL,
        "location": None,
        "reason": "no provider request was made",
    }
    assert preflight["connectivity_proven"] is False
    assert preflight["proof"] == "local configuration only; no provider request was made"
    # Unchanged when no request was made: tests/unit/cli/test_mission.py pins it.
    assert report["modes"]["gemini-adk"]["proof"].endswith("connectivity not probed")


def test_the_doctor_command_probes_by_default_when_credentials_are_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)
    _vertex(monkeypatch, "us-central1")
    calls: list[str] = []
    monkeypatch.setattr(mission_cli, "_count_tokens", calls.append)

    args = build_parser().parse_args(["doctor", "--repo", str(repository), "--json"])

    assert handle(args) == 0
    assert calls == [LIVE_GEMINI_MODEL]
    payload = json.loads(capsys.readouterr().out)
    assert payload["gemini_preflight"]["model_available"]["status"] == "available"


def test_no_probe_skips_the_request_when_credentials_are_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)
    _vertex(monkeypatch, "us-central1")
    calls: list[str] = []
    monkeypatch.setattr(mission_cli, "_count_tokens", calls.append)

    args = build_parser().parse_args(
        ["doctor", "--repo", str(repository), "--no-probe", "--json"]
    )

    assert handle(args) == 0
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["gemini_preflight"]["model_available"]["status"] == "not_checked"


def test_text_mode_names_the_region_miss_the_probe_just_paid_to_find(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default output, no --json: the verdict is why the user ran doctor."""
    from google.genai.errors import APIError

    repository = _repository(tmp_path)
    _vertex(monkeypatch, "us-central1")
    monkeypatch.setattr(
        mission_cli, "_count_tokens", _raise(APIError(404, {"error": {}}))
    )

    args = build_parser().parse_args(["doctor", "--repo", str(repository)])

    assert handle(args) == 0
    status, model, _ = capsys.readouterr().out.split("\n")
    assert status == "GRAPHENE status=ok"
    assert model.startswith(f"MODEL {LIVE_GEMINI_MODEL} unavailable ")
    assert "global" in model
    assert CANARY not in model


def test_text_mode_reports_not_checked_without_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)

    assert main(["doctor", "--repo", str(repository)]) == 0

    assert capsys.readouterr().out.splitlines()[1] == (
        f"MODEL {LIVE_GEMINI_MODEL} not_checked reason=no provider request was made"
    )


def test_doctor_json_after_the_verb_prints_the_probe_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)

    assert main(["doctor", "--repo", str(repository), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["gemini_preflight"]["model_available"]["status"] == "not_checked"
