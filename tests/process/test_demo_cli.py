from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest

from graphene.cli.main import _load
from graphene.lineage import SQLiteArtifactStore, SQLiteLineageStore
from graphene.models import LineageEventType, VerifiedHead
from graphene.viewer import build_snapshot

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the production fixed-test demo is macOS-only",
)
def test_scripted_local_demo_is_one_private_verified_process() -> None:
    environment = os.environ.copy()
    environment.pop("GRAPHENE_LINEAGE_DB", None)
    environment.update(
        {
            "GOOGLE_API_KEY": "must-not-be-used",
            "GOOGLE_CLOUD_PROJECT": "must-not-be-used",
        }
    )
    process = subprocess.Popen(
        [
            str(GRAPHENE),
            "demo",
            "--driver",
            "scripted-local",
            "--no-open",
            "--speed",
            "1000",
            "--exit-after-demo",
            "--automated-fixture",
        ],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    banner_lines = []
    while not any(line.startswith("Private runtime: ") for line in banner_lines):
        raw = process.stdout.readline()
        assert raw, (process.stderr.read() if process.stderr else b"").decode(
            errors="replace"
        )
        banner_lines.append(raw.decode(errors="replace").rstrip("\n"))
    viewer_url = next(
        line.removeprefix("Viewer: ")
        for line in banner_lines
        if line.startswith("Viewer: ")
    )
    with urllib.request.urlopen(viewer_url, timeout=5) as response:
        assert response.status == 200
        page = response.read()
        assert b"Graphene" in page
        assert b"NOT HUMAN ATTESTATION" in page
    process.wait(timeout=60)
    remainder = process.stdout.read()
    errors = process.stderr.read() if process.stderr else b""
    output = "\n".join(banner_lines) + "\n" + remainder.decode(errors="replace")
    assert process.returncode == 0, errors.decode(errors="replace")
    assert errors == b""
    assert output.index("SCRIPTED LOCAL") < output.index("DEMO COMPLETE")
    assert "Google ADK Runner: not used" in output
    assert "Gemini calls: 0" in output
    assert "AUTOMATED FIXTURE MODE" in output
    assert output.count("SIMULATED OPERATOR — NOT HUMAN ATTESTATION") == 4
    assert "No human decision proof may be claimed from this run." in output
    assert output.count(" GATE:") == 3
    assert output.count("DECISION PACKET —") == 3
    assert output.index("DECISION PACKET — SCOPE") < output.index("SCOPE GATE:")
    assert output.index("DECISION PACKET — MEMORY") < output.index("MEMORY GATE:")
    assert output.index("DECISION PACKET — PROMOTION") < output.index(
        "PROMOTION GATE:"
    )
    assert "Correction: When security-sensitive authentication behavior changes" in output
    assert "Proposed Scope: all_auth (app/auth/**)" in output
    assert "Hunk: app/auth/limiter.py:" in output
    assert "Rule: Auth changes require a regression test" in output
    assert "Revision: 1" in output
    assert "Changed Paths: app/auth/limiter.py, tests/test_security_policy.py" in output
    assert "Test Receipt:" in output and " passed=true" in output
    assert output.count("Digest:") == 2
    assert output.count("Why:") == 3
    assert len(re.findall(r"\b[0-9a-f]{64}\b", output)) >= 3
    assert all(len(line) <= 600 for line in output.splitlines())
    assert "Promotion state: PROMOTED" in output

    runtime = Path(
        next(
            line.removeprefix("Private runtime: ")
            for line in output.splitlines()
            if line.startswith("Private runtime: ")
        )
    )
    database = runtime / "lineage.sqlite3"
    try:
        assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        with closing(sqlite3.connect(database)) as connection:
            run_ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM run_heads ORDER BY run_id"
                )
            )
        assert len(run_ids) == 2 and len(set(run_ids)) == 2

        event_types = set()
        model_ids = set()
        operations = set()
        projections = []
        gate_events = []
        artifacts = SQLiteArtifactStore(database, read_only=True)
        store = SQLiteLineageStore(
            database, artifact_resolver=artifacts.resolve, read_only=True
        )
        for run_id in run_ids:
            head = store.verify(run_id)
            assert isinstance(head, VerifiedHead)
            events, projection = _load(database, run_id)
            assert events[-1].event_sha256 == head.event_sha256
            assert _load(database, run_id)[1] == projection
            event_types.update(event.event_type for event in events)
            gate_events.extend(
                event
                for event in events
                if event.event_type
                in {
                    LineageEventType.CLARIFICATION_ANSWERED,
                    LineageEventType.FEEDBACK_RECORDED,
                    LineageEventType.MEMORY_APPROVED,
                    LineageEventType.PROMOTION_APPROVED,
                }
            )
            model_ids.update(event.model_id for event in events if event.model_id)
            operations.update(
                str(event.payload.get("operation"))
                for event in events
                if event.payload.get("operation")
            )
            projections.append(projection)
        assert {
            "read_file",
            "open_evidence",
            "write_file",
            "run_fixed_test",
            "request_completion",
        } <= operations
        assert model_ids == {"graphene-local-scripted"}
        assert {event.event_type for event in gate_events} == {
            LineageEventType.CLARIFICATION_ANSWERED,
            LineageEventType.FEEDBACK_RECORDED,
            LineageEventType.MEMORY_APPROVED,
            LineageEventType.PROMOTION_APPROVED,
        }
        assert all(event.truth_kind.value == "simulated_fixture" for event in gate_events)
        assert all(event.authority.value == "simulated_fixture" for event in gate_events)
        assert all(event.source_ref.kind.value == "simulated_fixture" for event in gate_events)
        assert not any(
            event.truth_kind.value == "human_attested"
            for run_id in run_ids
            for event in _load(database, run_id)[0]
        )
        assert {
            LineageEventType.CLARIFICATION_ASKED,
            LineageEventType.CLARIFICATION_ANSWERED,
            LineageEventType.FEEDBACK_RECORDED,
            LineageEventType.MEMORY_APPROVED,
            LineageEventType.HANDOFF_DENIED,
            LineageEventType.CONTEXT_COMPILED,
            LineageEventType.CONTEXT_INJECTED,
            LineageEventType.PROMOTION_COMPLETED,
        } <= event_types
        assert any(projection.state.value == "PROMOTED" for projection in projections)
        public_view = json.dumps(
            build_snapshot(database, run_ids[0]).model_dump(mode="json"),
            sort_keys=True,
        ).lower()
        assert all(
            forbidden not in public_view
            for forbidden in (
                str(runtime).lower(),
                "max_attempts = 4",
                "window_seconds = 90",
                "when security-sensitive authentication behavior changes",
                "unified_diff",
                "test stdout",
                "must-not-be-used",
                "google_api_key",
            )
        )
        assert '"truth_kind": "simulated_fixture"' in public_view
        assert "human_attested" not in public_view
    finally:
        shutil.rmtree(runtime)


def test_demo_runtimes_never_collide_and_viewer_failure_keeps_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene import demo

    first, _ = demo._runtime()
    second, _ = demo._runtime()
    try:
        assert first != second
    finally:
        shutil.rmtree(first)
        shutil.rmtree(second)

    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    monkeypatch.setattr(demo, "_preflight", lambda: None)
    monkeypatch.setattr(demo, "_runtime", lambda: (runtime, database))
    monkeypatch.setattr(
        demo,
        "_start_viewer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            demo.DemoError("viewer unavailable")
        ),
    )
    with pytest.raises(demo.DemoError, match="viewer unavailable"):
        demo.run_demo(speed=1000, no_open=True, cleanup=False, keep_open=False)

    with closing(sqlite3.connect(database)) as connection:
        run_id = connection.execute("SELECT run_id FROM run_heads").fetchone()[0]
    events, _ = _load(database, run_id)
    assert [event.event_type for event in events] == [LineageEventType.RUN_STARTED]


def test_scripted_local_preflight_fails_closed_off_macos(monkeypatch) -> None:
    from graphene import demo

    monkeypatch.setattr(demo.platform, "system", lambda: "Linux")
    with pytest.raises(demo.DemoError, match="requires macOS"):
        demo._preflight()


def test_normal_gate_still_requires_interactive_operator_input() -> None:
    from graphene import demo

    prompts = []
    demo._gate(
        "PROMOTION GATE",
        "promote",
        lambda prompt: prompts.append(prompt) or "promote",
        automated_fixture=False,
    )
    assert prompts and "press Enter" in prompts[0]


def test_automated_fixture_is_process_only(monkeypatch) -> None:
    from graphene import demo

    monkeypatch.setattr(demo, "_preflight", lambda: None)
    with pytest.raises(demo.DemoError, match="requires --exit-after-demo"):
        demo.run_demo(
            speed=1,
            no_open=True,
            cleanup=False,
            automated_fixture=True,
        )
