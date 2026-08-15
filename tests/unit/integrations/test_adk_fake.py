from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path

import pytest
from graphene.demo_adk import (
    ADK_FAKE_PROOF_LABEL,
    AdkFakeError,
    AdkFakeToolCall,
    run_adk_fake,
    validate_distinct_adk_fake_runtimes,
)
from graphene.execution.adapter import TestRun as _TestRun
from graphene.hashing import sha256_hex
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.service import EvidenceItem, ScopedApplicationService
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    EventInput,
    EvidenceKind,
    GoldenContract,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
BASE_SHA = "a" * 40


def _handle(
    store: SQLiteLineageStore,
    artifacts: SQLiteArtifactStore,
    checkout: Path,
    *,
    role: str,
    evidence: tuple[EvidenceItem, ...] = (),
):
    run_id = f"run_adk_fake_{role}_001"
    source_artifact = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "action": "start", "role": role},
    )
    store.append(
        run_id,
        VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0),
        f"adk_fake_{role}_start_key_001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=source_artifact.id,
                sha256=source_artifact.sha256,
            ),
            payload={"state": "STARTING"},
        ),
    )
    service = ScopedApplicationService(store, artifacts)
    handle = service.create_handle(
        run_id=run_id,
        repo_id="graphene-demo",
        base_sha=BASE_SHA,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
        session_id=f"session_adk_fake_{role}_001",
        invocation_id=f"invocation_adk_fake_{role}_001",
        model_id="graphene-local-scripted",
        read_scope=("app/auth/limiter.py",),
        write_scope=("app/auth/limiter.py",),
        tools=tuple(LineageOperation),
        evidence=evidence,
        fixed_test_profile="fixture_pytest",
        fixture_policy=GOLDEN.fixture,
        checkout_root=checkout,
    )
    return service, handle


def test_real_adk_fake_source_and_consumer_are_distinct_and_offline(
    tmp_path: Path,
    monkeypatch,
):
    database = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    source_checkout = tmp_path / "source"
    consumer_checkout = tmp_path / "consumer"
    shutil.copytree(ROOT / GOLDEN.fixture.root, source_checkout)
    shutil.copytree(ROOT / GOLDEN.fixture.root, consumer_checkout)
    evidence_reference = artifacts(
        EvidenceKind.HUNK,
        {"schema_version": 2, "content": "approved correction"},
    )
    evidence = EvidenceItem(
        reference=evidence_reference,
        content="approved correction",
        content_sha256=sha256_hex(b"approved correction"),
    )
    source_service, source_handle = _handle(
        store, artifacts, source_checkout, role="source"
    )
    consumer_service, consumer_handle = _handle(
        store,
        artifacts,
        consumer_checkout,
        role="consumer",
        evidence=(evidence,),
    )
    with pytest.raises(AdkFakeError, match="one final completion request"):
        run_adk_fake(
            source_service,
            source_handle,
            role="source",
            calls=(
                AdkFakeToolCall(
                    call_id="invalid_nonterminal_read_001",
                    operation=LineageOperation.READ_FILE,
                    arguments={"path": "app/auth/limiter.py"},
                ),
            ),
        )
    assert len(store.tail(source_handle.run_id, 0, 256)) == 1
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-be-used")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "must-not-be-used")
    outbound_attempts = []

    def reject_outbound(_socket, address):
        outbound_attempts.append(address)
        raise AssertionError(f"ADK fake attempted outbound network: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", reject_outbound)
    monkeypatch.setattr(
        "graphene.lineage.service.run_fixture_tests",
        lambda *_: _TestRun(
            exit_code=0,
            timed_out=False,
            output="1 passed",
            output_truncated=False,
        ),
    )

    source = run_adk_fake(
        source_service,
        source_handle,
        role="source",
        calls=(
            AdkFakeToolCall(
                call_id="source_read_001",
                operation=LineageOperation.READ_FILE,
                arguments={"path": "app/auth/limiter.py"},
            ),
            AdkFakeToolCall(
                call_id="source_write_001",
                operation=LineageOperation.WRITE_FILE,
                arguments={
                    "path": "app/auth/limiter.py",
                    "content": (source_checkout / "app/auth/limiter.py")
                    .read_text()
                    .replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"),
                },
            ),
            AdkFakeToolCall(
                call_id="source_test_001",
                operation=LineageOperation.RUN_FIXED_TEST,
            ),
            AdkFakeToolCall(
                call_id="source_completion_001",
                operation=LineageOperation.REQUEST_COMPLETION,
            ),
        ),
    )
    consumer = run_adk_fake(
        consumer_service,
        consumer_handle,
        role="consumer",
        calls=(
            AdkFakeToolCall(
                call_id="consumer_evidence_001",
                operation=LineageOperation.OPEN_EVIDENCE,
                arguments={"evidence_id": evidence_reference.id},
            ),
            AdkFakeToolCall(
                call_id="consumer_read_001",
                operation=LineageOperation.READ_FILE,
                arguments={"path": "app/auth/limiter.py"},
            ),
            AdkFakeToolCall(
                call_id="consumer_write_001",
                operation=LineageOperation.WRITE_FILE,
                arguments={
                    "path": "app/auth/limiter.py",
                    "content": (consumer_checkout / "app/auth/limiter.py")
                    .read_text()
                    .replace("WINDOW_SECONDS = 60", "WINDOW_SECONDS = 90"),
                },
            ),
            AdkFakeToolCall(
                call_id="consumer_test_001",
                operation=LineageOperation.RUN_FIXED_TEST,
            ),
            AdkFakeToolCall(
                call_id="consumer_completion_001",
                operation=LineageOperation.REQUEST_COMPLETION,
            ),
        ),
    )

    validate_distinct_adk_fake_runtimes(source, consumer)
    assert source.proof_label == consumer.proof_label == ADK_FAKE_PROOF_LABEL
    assert source.external_model_dispatch_count == consumer.external_model_dispatch_count == 0
    assert outbound_attempts == []
    assert source.fake_model_turn_count == 4
    assert consumer.fake_model_turn_count == 5
    assert os.environ["GOOGLE_API_KEY"] == "must-not-be-used"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "must-not-be-used"
    for run_id in (source.run_id, consumer.run_id):
        lineage = store.tail(run_id, 0, 256)
        started = next(
            event
            for event in lineage
            if event.event_type == LineageEventType.INVOCATION_STARTED
        )
        assert started.payload == {
            "adapter_kind": "adk",
            "framework": "google_adk",
            "framework_version": "2.5.0",
            "status": "started",
        }
        assert lineage[-1].event_type == LineageEventType.COMPLETION_DENIED
