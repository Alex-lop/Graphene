from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from graphene.integrations import stdio
from graphene.orchestration import supervisor


def test_mission_stdio_scrubs_unrelated_credentials_before_serving(monkeypatch) -> None:
    observed: dict[str, str] = {}

    class Server:
        def run(self, transport: str) -> None:
            assert transport == "stdio"
            observed.update(os.environ)

    monkeypatch.setattr(supervisor, "recover_supervisors", lambda: 0)
    monkeypatch.setattr(stdio, "create_mission_mcp_server", Server)
    with patch.dict(
        os.environ,
        {
            "GRAPHENE_STATE_DIR": "/tmp/graphene-test-state",
            "GOOGLE_API_KEY": "required-model-credential",
            "GRAPHENE_GITHUB_TOKEN": "must-not-cross-boundary",
            "AWS_SECRET_ACCESS_KEY": "must-not-cross-boundary",
        },
        clear=True,
    ):
        assert stdio._serve_missions() == 0

    assert observed["GRAPHENE_STATE_DIR"] == "/tmp/graphene-test-state"
    assert observed["GOOGLE_API_KEY"] == "required-model-credential"
    assert "GRAPHENE_GITHUB_TOKEN" not in observed
    assert "AWS_SECRET_ACCESS_KEY" not in observed


def test_ready_does_not_wait_for_slow_multi_owner_cancellation_cleanup(
    tmp_path, monkeypatch
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    owners = (
        state / "missions" / "mission-slow-owner",
        state / "scripted" / "scripted-slow-owner",
    )
    for owner in owners:
        owner.mkdir(mode=0o700, parents=True)
        journal = owner / "cancellation-request.json"
        journal.write_text("{}\n", encoding="utf-8")
        journal.chmod(0o600)

    cleanup_started = threading.Event()
    release_cleanup = threading.Event()
    cleanup_finished = threading.Event()
    launches: list[tuple[str, ...]] = []
    diagnostics: list[str] = []

    def detached_cleanup(arguments, **_kwargs):
        launches.append(tuple(arguments))

        def slow_multi_owner_cleanup() -> None:
            cleanup_started.set()
            release_cleanup.wait(5)
            cleanup_finished.set()

        threading.Thread(target=slow_multi_owner_cleanup, daemon=True).start()
        return SimpleNamespace()

    class Server:
        def run(self, transport: str) -> None:
            assert transport == "stdio"
            assert cleanup_started.wait(1)
            assert not cleanup_finished.is_set()
            assert all(
                (owner / "cancellation-request.json").is_file()
                for owner in owners
            )

    def unexpected_spawn(*_args, **_kwargs) -> None:
        raise AssertionError("pending cancellation owner was respawned")

    monkeypatch.setattr(supervisor.subprocess, "Popen", detached_cleanup)
    monkeypatch.setattr(supervisor, "_spawn", unexpected_spawn)
    monkeypatch.setattr(stdio, "create_mission_mcp_server", Server)
    monkeypatch.setattr(stdio, "_diagnostic", diagnostics.append)
    with patch.dict(os.environ, {"GRAPHENE_STATE_DIR": str(state)}, clear=True):
        started = time.monotonic()
        assert stdio._serve_missions() == 0, diagnostics
        assert time.monotonic() - started < 1

    assert diagnostics == [stdio._READY]
    assert len(launches) == 1
    assert "--recover-cancellations" in launches[0]
    release_cleanup.set()
    assert cleanup_finished.wait(1)
