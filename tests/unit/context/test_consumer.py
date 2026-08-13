from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from graphene.context.consumer import (
    ConsumerStartError,
    FreshConsumer,
    resume_fresh_consumer,
    start_fresh_consumer,
)
from graphene.context.handoff import (
    AUTH_CAPABILITIES,
    HandoffCandidate,
    compile_handoff,
    render_fresh_prompt,
    source_candidate_set_sha256,
)
from graphene.execution import fixture_base_sha
from graphene.execution.adapter import _initialize_repository
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    BriefEvidence,
    EventInput,
    EvidenceKind,
    GoldenContract,
    GraphMvpContract,
    HandoffDenied,
    LineageAuthority,
    LineageEventType,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
GRAPH = GraphMvpContract.model_validate_json(
    (ROOT / "contracts/graph_mvp.json").read_text()
)
NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)
BASE_SHA = fixture_base_sha(GOLDEN, ROOT / GOLDEN.fixture.root)
INCLUDED = "INCLUDED_EVIDENCE_CONTENT"
EXCLUDED = "EXCLUDED_EVIDENCE_CANARY"


def _profile(profile_id: str):
    return next(item for item in GRAPH.catalog if item.agent_profile_id == profile_id)


def _source(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    database.touch(mode=0o600)
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    source = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "action": "run.started"},
    )
    run_id = "source_consumer_001"
    started = store.append(
        run_id,
        VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0),
        "source_consumer_started_001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=GOLDEN.repo_id,
            base_sha=BASE_SHA,
            agent_profile_id="platform-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=source.id,
                sha256=source.sha256,
            ),
            payload={"state": "STARTING"},
        ),
    )
    head = VerifiedHead(
        run_id=run_id,
        seq=started.seq,
        event_sha256=started.event_sha256,
        event_count=started.seq,
    )
    selected = artifacts(
        EvidenceKind.HUNK,
        {"schema_version": 2, "content": INCLUDED, "summary": "Selected hunk."},
    )
    excluded = artifacts(
        EvidenceKind.HUNK,
        {"schema_version": 2, "content": EXCLUDED, "summary": EXCLUDED},
    )
    candidates = tuple(
        HandoffCandidate(
            candidate_kind="source_artifact",
            id=reference.id,
            sha256=reference.sha256,
            evidence=BriefEvidence(
                evidence_id=reference.id,
                summary=summary,
                reference=reference,
            ),
        )
        for reference, summary in (
            (selected, "Selected hunk."),
            (excluded, EXCLUDED),
        )
    )
    return database, artifacts, store, run_id, head, selected, excluded, candidates


def _compiled(tmp_path: Path, *, billing: bool = False):
    database, artifacts, store, run_id, head, selected, excluded, candidates = _source(
        tmp_path
    )
    profile_id = "billing-observer@1" if billing else "auth-maintainer@1"
    compiled = compile_handoff(
        decision_id="consumer_handoff_decision_001",
        brief_id="consumer_brief_001",
        source_run_id=run_id,
        source_session_id="source_session_001",
        source_head=head,
        source_graph_sha256="f" * 64,
        repo_id=GOLDEN.repo_id,
        base_sha=BASE_SHA,
        task=GOLDEN.tasks[1],
        target_profile=_profile(profile_id),
        target_profile_revision=1,
        policy_revision=1,
        source_candidates=candidates,
        expected_source_candidate_set_sha256=source_candidate_set_sha256(candidates),
        selected_evidence_ids=(selected.id,),
        approved_memories=(),
        policy_required_paths=(GOLDEN.memory.required_test_path,),
        read_scope=("app/auth/limiter.py", "tests/test_security_policy.py"),
        write_scope=GOLDEN.tasks[1].expected_changed_paths,
        capabilities=AUTH_CAPABILITIES if not billing else (),
        fixed_test_profile=GRAPH.required_test_profile,
        byte_caps={"read": 32_768, "write": 32_768},
        event_caps={"run": 256},
        server_recorded_at=NOW,
    )
    return database, artifacts, store, selected, excluded, compiled


def _consumer_run_id(database: Path, compiled) -> str:
    namespace = canonical_json_sha256(
        {
            "database_path": str(database),
            "decision_sha256": compiled.decision.decision_sha256,
            "brief_sha256": compiled.brief.brief_sha256,
        }
    )
    return "consumer_" + sha256_hex(f"consumer\0{namespace}".encode())[:24]


def test_fresh_consumer_persists_exact_context_before_runtime_exposure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database, artifacts, store, selected, excluded, compiled = _compiled(tmp_path)
    run_id = _consumer_run_id(database, compiled)
    from graphene.context import consumer

    original_checkout = consumer._checkout
    original_service = consumer.ScopedApplicationService

    def observed_checkout(*args, **kwargs):
        source_events = store.tail(compiled.decision.source_run_id, 0, 256)
        assert source_events[-1].event_type == LineageEventType.CONTEXT_COMPILED
        references = {item.kind: item for item in source_events[-1].references}
        assert json.loads(
            artifacts.resolve(
                EvidenceKind.HANDOFF_DECISION.value,
                references[EvidenceKind.HANDOFF_DECISION].id,
            )
        ) == compiled.decision.model_dump(mode="json")
        assert json.loads(
            artifacts.resolve(
                EvidenceKind.CONTEXT_BRIEF.value,
                references[EvidenceKind.CONTEXT_BRIEF].id,
            )
        ) == compiled.brief.model_dump(mode="json")
        assert [event.event_type for event in store.tail(run_id, 0, 256)] == [
            LineageEventType.RUN_STARTED
        ]
        with sqlite3.connect(database) as connection:
            rows = connection.execute(
                "SELECT artifact_bytes FROM lineage_artifacts WHERE kind = ?",
                (EvidenceKind.INJECTION_RECEIPT.value,),
            ).fetchall()
        assert len(rows) == 1
        injection = json.loads(rows[0][0])
        assert injection["prior_message_count"] == 0
        assert injection["persisted_before_dispatch"] is True
        assert injection["prompt_sha256"] == sha256_hex(
            render_fresh_prompt(compiled.brief)
        )
        return original_checkout(*args, **kwargs)

    monkeypatch.setattr(consumer, "_checkout", observed_checkout)

    def observed_service(*args, **kwargs):
        assert [event.event_type for event in store.tail(run_id, 0, 256)] == [
            LineageEventType.RUN_STARTED,
            LineageEventType.CONTEXT_INJECTED,
        ]
        return original_service(*args, **kwargs)

    monkeypatch.setattr(consumer, "ScopedApplicationService", observed_service)

    result = start_fresh_consumer(
        compiled,
        database,
        repository_root=ROOT,
        injected_at=NOW,
    )
    assert isinstance(result, FreshConsumer)
    assert result.store is not store
    assert result.handle.head == result.store.verify(result.run_id)
    assert result.checkout_root.is_dir()
    assert {result.run_id, result.session_id, result.invocation_id}.isdisjoint(
        {compiled.decision.source_run_id, compiled.brief.source_session_id}
    )
    assert result.handle.base_sha == compiled.brief.base_sha
    assert result.handle.read_scope == compiled.brief.read_scope
    assert result.handle.write_scope == compiled.brief.write_scope
    assert result.handle.tools == compiled.brief.tools
    assert result.prompt.endswith(
        canonical_json_bytes(compiled.brief.model_dump(mode="json"))
    )
    assert INCLUDED.encode() not in result.prompt
    assert EXCLUDED.encode() not in result.prompt
    assert tuple(item.reference.id for item in result.handle.evidence) == (selected.id,)
    assert result.handle.evidence[0].content == INCLUDED
    assert excluded.id not in {item.reference.id for item in result.handle.evidence}

    source_events = result.store.tail(compiled.decision.source_run_id, 0, 256)
    consumer_events = result.store.tail(result.run_id, 0, 256)
    assert source_events[-1].event_type == LineageEventType.CONTEXT_COMPILED
    assert [event.event_type for event in consumer_events] == [
        LineageEventType.RUN_STARTED,
        LineageEventType.CONTEXT_INJECTED,
    ]
    injected = consumer_events[-1]
    assert injected.payload["prior_message_count"] == 0
    assert injected.payload["decision_sha256"] == compiled.decision.decision_sha256
    assert injected.payload["brief_sha256"] == compiled.brief.brief_sha256
    assert injected.payload["prompt_sha256"] == sha256_hex(result.prompt)
    assert (injected.session_id, injected.invocation_id) == (
        result.session_id,
        result.invocation_id,
    )
    kinds = {reference.kind for reference in injected.references}
    assert kinds == {
        EvidenceKind.HANDOFF_DECISION,
        EvidenceKind.CONTEXT_BRIEF,
        EvidenceKind.INJECTION_RECEIPT,
    }
    injection_ref = next(
        item
        for item in injected.references
        if item.kind == EvidenceKind.INJECTION_RECEIPT
    )
    raw = result.artifacts.resolve(injection_ref.kind.value, injection_ref.id)
    assert raw is not None
    receipt = json.loads(raw)
    assert receipt["prior_message_count"] == 0
    assert receipt["persisted_before_dispatch"] is True
    assert receipt["prompt_sha256"] == sha256_hex(result.prompt)

    monkeypatch.setattr(consumer, "_checkout", original_checkout)
    monkeypatch.setattr(consumer, "ScopedApplicationService", original_service)
    resumed = resume_fresh_consumer(
        database,
        result.run_id,
        repository_root=ROOT,
    )
    assert resumed.prompt == result.prompt
    assert resumed.handle.head == result.handle.head
    assert resumed.handle.read_scope == result.handle.read_scope
    assert resumed.handle.write_scope == result.handle.write_scope
    assert resumed.handle.tools == result.handle.tools
    assert resumed.handle.evidence == result.handle.evidence
    assert resumed.checkout_root == result.checkout_root


def test_billing_returns_before_repository_database_or_runtime_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database, _, store, _, _, compiled = _compiled(tmp_path, billing=True)
    head = store.verify(compiled.decision.source_run_id)
    impossible = tmp_path / "missing" / "lineage.sqlite3"
    from graphene.context import consumer

    calls = 0

    def exploding(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("Billing constructed consumer state")

    for name in (
        "_repository",
        "_database",
        "_stable_id",
        "SQLiteArtifactStore",
        "SQLiteLineageStore",
        "ScopedApplicationService",
        "bind_and_dispatch",
    ):
        monkeypatch.setattr(consumer, name, exploding)

    denied = start_fresh_consumer(
        compiled,
        impossible,
        repository_root=tmp_path / "missing-repository",
        injected_at=NOW,
    )
    assert isinstance(denied, HandoffDenied)
    assert denied is compiled.denial
    assert calls == 0
    assert store.verify(compiled.decision.source_run_id) == head
    assert not impossible.exists()
    assert database.exists()
    assert not (database.parent / "checkouts").exists()
    assert denied.model_dump(mode="json") == {
        "schema_version": 2,
        "source_run_id": "source_consumer_001",
        "target_profile_id": "billing-observer@1",
        "task_id": GOLDEN.tasks[1].task_id.value,
        "reason_code": "scope_intersection_empty",
        "memory_count": 0,
        "evidence_count": 0,
        "source_path_count": 0,
        "tool_count": 0,
        "consumer_run_id": None,
        "session_id": None,
        "invocation_id": None,
        "model_dispatch_count": 0,
    }


def test_consumer_checkout_substitution_and_replay_fail_closed(tmp_path: Path):
    database, _, store, _, _, compiled = _compiled(tmp_path)
    run_id = _consumer_run_id(database, compiled)
    checkout = database.parent / "checkouts" / run_id
    checkout.parent.mkdir(mode=0o700)
    assert (
        _initialize_repository(GOLDEN, ROOT / GOLDEN.fixture.root, checkout) == BASE_SHA
    )
    target = checkout / "app/auth/limiter.py"
    target.write_text(target.read_text() + "\n# substituted\n")
    source_before = store.verify(compiled.decision.source_run_id)

    with pytest.raises(ConsumerStartError, match="consumer"):
        start_fresh_consumer(
            compiled,
            database,
            repository_root=ROOT,
            injected_at=NOW,
        )
    assert "substituted" in target.read_text()
    source_events = store.tail(
        compiled.decision.source_run_id,
        source_before.seq,
        256,
    )
    consumer_events = store.tail(run_id, 0, 256)
    assert [event.event_type for event in source_events] == [
        LineageEventType.CONTEXT_COMPILED
    ]
    assert [event.event_type for event in consumer_events] == [
        LineageEventType.RUN_STARTED
    ]


def test_consumer_resume_rejects_checkout_substitution(tmp_path: Path):
    database, _, _, _, _, compiled = _compiled(tmp_path)
    consumer = start_fresh_consumer(
        compiled,
        database,
        repository_root=ROOT,
        injected_at=NOW,
    )
    assert isinstance(consumer, FreshConsumer)
    target = consumer.checkout_root / "app/auth/limiter.py"
    target.write_text(target.read_text() + "\n# RESUME_PRIVATE_CANARY\n")

    with pytest.raises(ConsumerStartError, match="rehydrated"):
        resume_fresh_consumer(
            database,
            consumer.run_id,
            repository_root=ROOT,
        )

    assert "RESUME_PRIVATE_CANARY" in target.read_text()
