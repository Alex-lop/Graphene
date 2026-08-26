from __future__ import annotations

import json
import os
import pty
import re
import select
import shutil
import sqlite3
import stat
import subprocess
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest

from graphene.cli.main import _load
from graphene.lineage import SQLiteArtifactStore, SQLiteLineageStore
from graphene.core_models import (
    EvidenceKind,
    LineageEventType,
    LineageRunState,
    MemoryRevision,
    VerifiedHead,
)
from graphene.viewer import build_snapshot
from graphene.viewer.viewer_replay import REPLAY_TRUTH_LABEL

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"


def _run_demo_in_pty(*decisions: str) -> tuple[int, str]:
    master, slave = pty.openpty()
    try:
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
            ],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
    finally:
        os.close(slave)
    os.write(master, ("\n".join(decisions) + "\n").encode())
    output = bytearray()
    deadline = time.monotonic() + 60
    try:
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                raise AssertionError("PTY demo timed out")
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                try:
                    output.extend(os.read(master, 64 * 1024))
                except OSError:
                    break
        while True:
            try:
                chunk = os.read(master, 64 * 1024)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    return process.returncode, output.decode(errors="replace").replace("\r\n", "\n")


def _runtime_from_output(output: str) -> Path:
    return Path(
        next(
            line.removeprefix("Private runtime: ")
            for line in output.splitlines()
            if line.startswith("Private runtime: ")
        )
    )


def _database_events(database: Path):
    with closing(sqlite3.connect(database)) as connection:
        run_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT run_id FROM run_heads ORDER BY run_id"
            )
        )
    return tuple(
        event for run_id in run_ids for event in _load(database, run_id)[0]
    ), run_ids


def _approved_memory(database: Path, events) -> MemoryRevision:
    approved = next(
        event
        for event in events
        if event.event_type == LineageEventType.MEMORY_APPROVED
    )
    reference = next(
        item
        for item in approved.references
        if item.kind == EvidenceKind.MEMORY_REVISION
        and item.sha256 == approved.payload["memory_sha256"]
    )
    raw = SQLiteArtifactStore(database, read_only=True).resolve(
        reference.kind.value, reference.id
    )
    assert raw is not None
    return MemoryRevision.model_validate_json(raw)


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
    assert output.count("DECISION PACKET —") == 4
    assert output.index("DECISION PACKET — SCOPE") < output.index("SCOPE GATE:")
    assert output.index("DECISION PACKET — MEMORY") < output.index("MEMORY GATE:")
    assert output.index("DECISION PACKET — HANDOFF PROOF") < output.index(
        "DECISION PACKET — PROMOTION"
    )
    assert output.index("DECISION PACKET — PROMOTION") < output.index("CANDIDATE GATE:")
    assert (
        "Correction: When security-sensitive authentication behavior changes" in output
    )
    assert "Scope: all_auth (app/auth/**)" in output
    assert "Hunk: app/auth/limiter.py:" in output
    assert "Rule: Auth changes require a regression test" in output
    assert "Revision: 1" in output
    assert "Billing: denied (scope_intersection_empty); model dispatches=0" in output
    assert "Approved Context: scope=all_auth; brief_sha256=" in output
    assert "Consumer Reference: event=" in output and "opened_evidence=" in output
    assert "Proof Limit: Delivery and opening were observed; causality was not established." in output
    assert "Changed Paths: app/auth/limiter.py, tests/test_security_policy.py" in output
    assert "Test Receipt:" in output and " passed=true" in output
    assert output.count("Digest:") == 2
    assert output.count("Why:") == 3
    assert len(re.findall(r"\b[0-9a-f]{64}\b", output)) >= 3
    assert all(len(line) <= 600 for line in output.splitlines())
    assert "Promotion state: PROMOTED" in output
    assert "Outcome: local_isolated_commit" in output
    assert "Checkout: " in output
    assert "Verify: git -C " in output and " show --stat --oneline " in output
    assert "Local isolated commit — not pushed / no PR / no deployment" in output

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
        assert all(
            event.truth_kind.value == "simulated_fixture" for event in gate_events
        )
        assert all(
            event.authority.value == "simulated_fixture" for event in gate_events
        )
        assert all(
            event.source_ref.kind.value == "simulated_fixture" for event in gate_events
        )
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
            LineageEventType.LOCAL_RESULT_RECORDED,
        } <= event_types
        assert any(projection.state.value == "PROMOTED" for projection in projections)
        local_result = next(
            event
            for run_id in run_ids
            for event in _load(database, run_id)[0]
            if event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
        )
        assert all(
            local_result.payload[name] is False
            for name in ("pushed", "pull_request_created", "deployed")
        )
        consumer_checkout = runtime / "checkouts" / local_result.run_id
        subprocess.run(
            (
                "git",
                "-C",
                str(consumer_checkout),
                "cat-file",
                "-e",
                f"{local_result.payload['local_commit_sha']}^{{commit}}",
            ),
            check=True,
            capture_output=True,
        )
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


def test_adk_fake_runner_failure_has_no_scripted_fallback(monkeypatch) -> None:
    from graphene import demo

    class Viewer:
        url = "http://127.0.0.1:1/viewer/test"

        def close(self):
            pass

    monkeypatch.setattr(demo, "_preflight", lambda: None)
    monkeypatch.setattr(demo, "_start_viewer", lambda *_args, **_kwargs: Viewer())
    monkeypatch.setattr(
        demo,
        "run_adk_fake",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("runner failed")),
    )

    with pytest.raises(demo.DemoError, match="no fallback was used"):
        demo.run_demo(
            driver="adk-fake",
            speed=1000,
            no_open=True,
            cleanup=True,
            keep_open=False,
            automated_fixture=True,
        )


def test_verified_replay_command_creates_no_runtime_or_authoritative_state() -> None:
    process = subprocess.run(
        [
            str(GRAPHENE),
            "demo",
            "--driver",
            "verified-replay",
            "--no-open",
            "--exit-after-demo",
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=20,
    )
    output = process.stdout.decode(errors="replace")
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    assert REPLAY_TRUTH_LABEL in output
    assert "Authoritative lineage writes: 0" in output
    assert "Human-attested decisions: 0" in output
    assert "Private runtime:" not in output
    assert "No authoritative state was created." in output


def test_normal_gate_requires_tty_and_collects_bounded_operator_attribution() -> None:
    from graphene import demo

    prompts = []
    answers = iter(("promote", "reviewer-a", "verified exact candidate"))
    decision = demo._gate(
        "PROMOTION GATE",
        (("promote", "promote the exact candidate"),),
        lambda prompt: prompts.append(prompt) or next(answers),
        automated_fixture=False,
        automated_value="promote",
        default=None,
        tty_check=lambda: True,
    )
    assert decision == demo._Decision(
        "promote", "reviewer-a", "verified exact candidate", True
    )
    assert len(prompts) == 3 and "required" in prompts[0]

    with pytest.raises(demo.DemoError, match="requires a real terminal"):
        demo._gate(
            "MEMORY GATE",
            (("approve", "approve the revision"),),
            lambda _prompt: pytest.fail("non-TTY input must not be read"),
            automated_fixture=False,
            automated_value="approve",
            default="approve",
            tty_check=lambda: False,
        )


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the production fixed-test demo is macOS-only",
)
def test_piped_input_cannot_create_human_attested_lineage() -> None:
    process = subprocess.run(
        [
            str(GRAPHENE),
            "demo",
            "--driver",
            "scripted-local",
            "--no-open",
            "--speed",
            "1000",
            "--exit-after-demo",
        ],
        cwd=ROOT,
        input=b"all_auth\nreviewer-a\nthis is piped\n",
        capture_output=True,
        timeout=60,
    )
    output = process.stdout.decode(errors="replace")
    assert process.returncode == 1
    assert b"human attestation requires a real terminal" in process.stderr
    runtime = Path(
        next(
            line.removeprefix("Private runtime: ")
            for line in output.splitlines()
            if line.startswith("Private runtime: ")
        )
    )
    try:
        with closing(sqlite3.connect(runtime / "lineage.sqlite3")) as connection:
            rows = connection.execute("SELECT event_bytes FROM events").fetchall()
        events = [json.loads(row[0]) for row in rows]
        assert not any(event["truth_kind"] == "human_attested" for event in events)
        assert not any(
            event["event_type"] == "clarification.answered" for event in events
        )
    finally:
        shutil.rmtree(runtime)


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the production fixed-test demo is macOS-only",
)
def test_real_pty_approval_records_only_explicit_human_attestation() -> None:
    returncode, output = _run_demo_in_pty(
        "all_auth",
        "reviewer-a",
        "the correction applies across auth policy",
        "approve",
        "reviewer-a",
        "the scoped revision is exact",
        "commit",
        "reviewer-a",
        "the candidate and receipt match",
    )
    runtime = _runtime_from_output(output)
    try:
        assert returncode == 0, output
        assert "DEMO COMPLETE" in output
        assert "SIMULATED OPERATOR" not in output
        events, _ = _database_events(runtime / "lineage.sqlite3")
        decisions = tuple(
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
        assert {event.event_type for event in decisions} == {
            LineageEventType.CLARIFICATION_ANSWERED,
            LineageEventType.FEEDBACK_RECORDED,
            LineageEventType.MEMORY_APPROVED,
            LineageEventType.PROMOTION_APPROVED,
        }
        assert all(event.truth_kind.value == "human_attested" for event in decisions)
        assert all(
            event.payload["operator_label"] == "reviewer-a" for event in decisions
        )
        assert _approved_memory(runtime / "lineage.sqlite3", events).path_globs == (
            "app/auth/**",
        )
    finally:
        shutil.rmtree(runtime)


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the production fixed-test demo is macOS-only",
)
def test_real_pty_memory_rejection_is_terminal_and_stops_before_handoff() -> None:
    returncode, output = _run_demo_in_pty(
        "all_auth",
        "reviewer-a",
        "reviewed broad scope",
        "reject",
        "reviewer-a",
        "the memory rule needs revision",
    )
    runtime = _runtime_from_output(output)
    try:
        assert returncode == 0, output
        assert "MEMORY REJECTED — branch complete and inspectable" in output
        assert "State: REJECTED" in output
        assert "Consumer runtime created: no" in output
        database = runtime / "lineage.sqlite3"
        events, run_ids = _database_events(database)
        assert len(run_ids) == 1
        assert _load(database, run_ids[0])[1].state == LineageRunState.REJECTED
        assert LineageEventType.MEMORY_REJECTED in {
            event.event_type for event in events
        }
        assert LineageEventType.RUN_ENDED in {event.event_type for event in events}
        assert not any(
            event.event_type
            in {
                LineageEventType.CONTEXT_COMPILED,
                LineageEventType.CONTEXT_INJECTED,
                LineageEventType.CANDIDATE_CREATED,
            }
            for event in events
        )
    finally:
        shutil.rmtree(runtime)


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the production fixed-test demo is macOS-only",
)
def test_real_pty_narrow_scope_and_candidate_rejection_are_durable() -> None:
    returncode, output = _run_demo_in_pty(
        "rate_limiter_only",
        "reviewer-b",
        "only the limiter path is justified",
        "approve",
        "reviewer-b",
        "the narrow memory is exact",
        "reject",
        "reviewer-b",
        "candidate needs another bounded edit",
    )
    runtime = _runtime_from_output(output)
    try:
        assert returncode == 0, output
        assert "CANDIDATE REJECTED — branch complete and inspectable" in output
        assert "Scope: rate_limiter_only" in output
        assert "Local commit created: no" in output
        database = runtime / "lineage.sqlite3"
        events, run_ids = _database_events(database)
        assert len(run_ids) == 2
        projections = tuple(_load(database, run_id)[1] for run_id in run_ids)
        assert any(item.state == LineageRunState.REJECTED for item in projections)
        rejected = next(
            event
            for event in events
            if event.event_type == LineageEventType.CANDIDATE_REJECTED
        )
        assert rejected.truth_kind.value == "human_attested"
        assert rejected.payload["operator_label"] == "reviewer-b"
        assert _approved_memory(database, events).path_globs == ("app/auth/limiter.py",)
        assert LineageEventType.PROMOTION_COMPLETED not in {
            event.event_type for event in events
        }
    finally:
        shutil.rmtree(runtime)


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
