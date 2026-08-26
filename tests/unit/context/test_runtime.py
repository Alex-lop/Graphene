from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from graphene.context.handoff import (
    AUTH_CAPABILITIES,
    CompiledHandoff,
    HandoffCandidate,
    compile_handoff,
    render_fresh_prompt,
    source_candidate_set_sha256,
)
from graphene.context.context_runtime import RuntimeBindingError, bind_and_dispatch
from graphene.hashing import canonical_json_bytes, canonical_json_sha256
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.sqlite_lineage_store import LineageConflict, SQLiteLineageStore
from graphene.core_models import (
    BriefEvidence,
    ContextBrief,
    EventInput,
    EvidenceKind,
    GoldenContract,
    GraphMvpContract,
    HumanDecision,
    LineageAuthority,
    LineageEventType,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    ScopeId,
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
NOW = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
BASE_SHA = "a" * 40
EXCLUDED_CANARY = "FORBIDDEN_WORK_DATA_CANARY"
ENVELOPE_CANARY = "SERVER_ONLY_ARTIFACT_ENVELOPE_CANARY"


def _profile(profile_id: str):
    return next(item for item in GRAPH.catalog if item.agent_profile_id == profile_id)


def _head(run_id: str) -> VerifiedHead:
    return VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0)


def _event_head(event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _artifact_count(path: Path) -> int:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT count(*) FROM lineage_artifacts").fetchone()[0]


def _memory(source_run_id: str) -> MemoryRevision:
    spec = GOLDEN.memory
    proposed = MemoryRevision(
        memory_id=spec.memory_id,
        revision=spec.revision,
        state=MemoryState.PROPOSED,
        rule=spec.rule,
        repo_id=spec.repo_id,
        scope_id=ScopeId.ALL_AUTH,
        path_globs=spec.path_globs,
        task_tags=spec.task_tags,
        required_test_path=spec.required_test_path,
        required_check=spec.required_check,
        evidence_run_id=source_run_id,
        feedback_id="feedback_runtime_001",
    )
    decision = HumanDecision(
        decision_id="memory_decision_runtime_001",
        value=MemoryDecisionValue.APPROVE,
        purpose="memory",
        bound_digest=canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        ),
        occurred_at=NOW,
    )
    return MemoryRevision.model_validate(
        {
            **proposed.model_dump(mode="json"),
            "state": MemoryState.APPROVED,
            "decision": decision,
        }
    )


def _seed_source(
    store: SQLiteLineageStore,
    artifacts: SQLiteArtifactStore,
    run_id: str,
) -> VerifiedHead:
    request = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "action": "run.started", "run_id": run_id},
    )
    event = store.append(
        run_id,
        _head(run_id),
        f"seed_{run_id}_0001",
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
                id=request.id,
                sha256=request.sha256,
            ),
            payload={"state": "STARTING"},
        ),
    )
    return _event_head(event)


def _compile(
    *,
    artifacts: SQLiteArtifactStore,
    source_run_id: str,
    source_head: VerifiedHead,
    target_profile_id: str = "auth-maintainer@1",
) -> tuple[CompiledHandoff, str, str]:
    selected = artifacts(
        EvidenceKind.HUNK,
        {
            "schema_version": 2,
            "content": "The earlier run observed the bounded Auth hunk.",
            "server_only_note": ENVELOPE_CANARY,
        },
    )
    excluded = artifacts(
        EvidenceKind.HUNK,
        {"schema_version": 2, "content": EXCLUDED_CANARY},
    )
    candidates = (
        HandoffCandidate(
            candidate_kind="source_artifact",
            id=selected.id,
            sha256=selected.sha256,
            evidence=BriefEvidence(
                evidence_id=selected.id,
                summary="Observed the bounded Auth hunk.",
                reference=selected,
            ),
        ),
        HandoffCandidate(
            candidate_kind="source_artifact",
            id=excluded.id,
            sha256=excluded.sha256,
            evidence=BriefEvidence(
                evidence_id=excluded.id,
                summary=EXCLUDED_CANARY,
                reference=excluded,
            ),
        ),
    )
    compiled = compile_handoff(
        decision_id=f"decision_{source_run_id}",
        brief_id=f"brief_{source_run_id}",
        source_run_id=source_run_id,
        source_session_id=f"session_{source_run_id}",
        source_head=source_head,
        source_graph_sha256="f" * 64,
        repo_id=GOLDEN.repo_id,
        base_sha=BASE_SHA,
        task=GOLDEN.tasks[1],
        target_profile=_profile(target_profile_id),
        target_profile_revision=1,
        policy_revision=1,
        source_candidates=candidates,
        expected_source_candidate_set_sha256=source_candidate_set_sha256(candidates),
        selected_evidence_ids=(selected.id,),
        approved_memories=(_memory(source_run_id),),
        policy_required_paths=(GOLDEN.memory.required_test_path,),
        read_scope=("app/auth/limiter.py", "tests/test_security_policy.py"),
        write_scope=GOLDEN.tasks[1].expected_changed_paths,
        capabilities=AUTH_CAPABILITIES if target_profile_id == "auth-maintainer@1" else (),
        fixed_test_profile=GRAPH.required_test_profile,
        byte_caps={"read": 32_768, "write": 32_768},
        event_caps={"run": 256},
        server_recorded_at=NOW,
    )
    return compiled, selected.id, excluded.id


def _runtime_args(compiled: CompiledHandoff, **updates):
    assert compiled.brief is not None
    values = {
        "compiled": compiled,
        "source_expected_head": compiled.decision.source_head,
        "expected_decision_sha256": compiled.decision.decision_sha256,
        "expected_brief_sha256": compiled.brief.brief_sha256,
        "consumer_run_id": "consumer_runtime_001",
        "session_id": "consumer_session_001",
        "invocation_id": "consumer_invocation_001",
        "model_id": "fake-runtime-model",
        "injection_receipt_id": "injection_runtime_001",
        "prompt": render_fresh_prompt(compiled.brief),
        "fixture_policy": GOLDEN.fixture,
        "context_compiled_idempotency_key": "context_compiled_0001",
        "consumer_started_idempotency_key": "consumer_started_0001",
        "context_injected_idempotency_key": "context_injected_0001",
        "injected_at": NOW,
    }
    values.update(updates)
    return values


def test_runtime_binding_commits_before_dispatch_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    source_run_id = "source_runtime_001"
    source_head = _seed_source(store, artifacts, source_run_id)
    billing, _, _ = _compile(
        artifacts=artifacts,
        source_run_id=source_run_id,
        source_head=source_head,
        target_profile_id="billing-observer@1",
    )
    assert billing.denial is not None

    calls = {"factory": 0, "dispatch": 0}

    def forbidden_factory(_run_id: str) -> Path:
        calls["factory"] += 1
        raise AssertionError("Billing created a consumer checkout")

    def forbidden_dispatch(_prompt, _handle):
        calls["dispatch"] += 1
        raise AssertionError("Billing dispatched a model")

    count_before_denial = _artifact_count(database)
    billing_args = {
        "compiled": billing,
        "store": store,
        "artifacts": artifacts,
        "source_expected_head": source_head,
        "expected_decision_sha256": billing.decision.decision_sha256,
        "expected_brief_sha256": None,
        "consumer_run_id": None,
        "session_id": None,
        "invocation_id": None,
        "model_id": None,
        "injection_receipt_id": None,
        "prompt": None,
        "fixture_policy": None,
        "checkout_factory": forbidden_factory,
        "dispatch_callback": forbidden_dispatch,
        "context_compiled_idempotency_key": "billing_compiled_0001",
        "consumer_started_idempotency_key": "billing_started_0001",
        "context_injected_idempotency_key": "billing_injected_0001",
        "injected_at": NOW,
    }
    denied = bind_and_dispatch(**billing_args)
    denial_events = store.tail(source_run_id, source_head.seq, 256)
    assert denied is billing.denial
    assert len(denial_events) == 1
    assert denial_events[0].event_type == LineageEventType.HANDOFF_DENIED
    assert denial_events[0].payload["model_dispatch_count"] == 0
    assert tuple(item.kind for item in denial_events[0].references) == (
        EvidenceKind.HANDOFF_DECISION,
    )
    assert calls == {"factory": 0, "dispatch": 0}
    assert _artifact_count(database) == count_before_denial + 1
    assert store.verify("billing_consumer_001") == _head("billing_consumer_001")
    assert bind_and_dispatch(**billing_args) is billing.denial
    assert store.tail(source_run_id, source_head.seq, 256) == denial_events
    assert _artifact_count(database) == count_before_denial + 1
    assert calls == {"factory": 0, "dispatch": 0}

    source_head = store.verify(source_run_id)
    assert isinstance(source_head, VerifiedHead)
    auth, selected_id, excluded_id = _compile(
        artifacts=artifacts,
        source_run_id=source_run_id,
        source_head=source_head,
    )
    assert auth.brief is not None

    checkout = tmp_path / "consumer_runtime_001"

    def checkout_factory(run_id: str) -> Path:
        calls["factory"] += 1
        assert run_id == "consumer_runtime_001"
        shutil.copytree(ROOT / GOLDEN.fixture.root, checkout)
        return checkout

    def dispatch(prompt: bytes, handle):
        calls["dispatch"] += 1
        source_events = store.tail(source_run_id, 0, 256)
        consumer_events = store.tail(handle.run_id, 0, 256)
        assert source_events[-1].event_type == LineageEventType.CONTEXT_COMPILED
        assert source_events[-1].payload["memory_scopes"] == [
            {
                "memory_id": GOLDEN.memory.memory_id,
                "revision": GOLDEN.memory.revision,
                "scope_id": "all_auth",
                "path_globs": ["app/auth/**"],
            }
        ]
        assert tuple(item.event_type for item in consumer_events) == (
            LineageEventType.RUN_STARTED,
            LineageEventType.CONTEXT_INJECTED,
        )
        assert handle.head == store.verify(handle.run_id)
        assert prompt == render_fresh_prompt(auth.brief)
        assert EXCLUDED_CANARY.encode() not in prompt
        assert ENVELOPE_CANARY.encode() not in prompt
        assert handle.read_scope == auth.brief.read_scope
        assert handle.write_scope == auth.brief.write_scope
        assert handle.tools == auth.brief.tools
        assert tuple(item.reference.id for item in handle.evidence) == (
            selected_id,
        ) == auth.open_evidence_allowlist
        assert handle.evidence[0].content == (
            "The earlier run observed the bounded Auth hunk."
        )
        assert EXCLUDED_CANARY not in handle.evidence[0].content
        assert ENVELOPE_CANARY not in handle.evidence[0].content
        assert excluded_id not in auth.open_evidence_allowlist

        injected = consumer_events[-1]
        assert (injected.session_id, injected.invocation_id, injected.model_id) == (
            handle.session_id,
            handle.invocation_id,
            handle.model_id,
        )
        assert {handle.run_id, handle.session_id, handle.invocation_id}.isdisjoint(
            {source_run_id, auth.brief.source_session_id}
        )
        injection_ref = next(
            item
            for item in injected.references
            if item.kind == EvidenceKind.INJECTION_RECEIPT
        )
        raw_injection = artifacts.resolve(injection_ref.kind.value, injection_ref.id)
        assert raw_injection is not None
        receipt = json.loads(raw_injection)
        assert receipt["prior_message_count"] == 0
        assert receipt["persisted_before_dispatch"] is True
        assert receipt["prompt_sha256"] == injected.payload["prompt_sha256"]

        decision_ref = next(
            item
            for item in source_events[-1].references
            if item.kind == EvidenceKind.HANDOFF_DECISION
        )
        brief_ref = next(
            item
            for item in source_events[-1].references
            if item.kind == EvidenceKind.CONTEXT_BRIEF
        )
        assert artifacts.resolve(decision_ref.kind.value, decision_ref.id) == (
            canonical_json_bytes(auth.decision.model_dump(mode="json"))
        )
        assert artifacts.resolve(brief_ref.kind.value, brief_ref.id) == (
            canonical_json_bytes(auth.brief.model_dump(mode="json"))
        )
        return "dispatched_after_commit"

    result = bind_and_dispatch(
        store=store,
        artifacts=artifacts,
        checkout_factory=checkout_factory,
        dispatch_callback=dispatch,
        **_runtime_args(auth),
    )
    assert result == "dispatched_after_commit"
    assert calls == {"factory": 1, "dispatch": 1}

    artifacts_after_success = _artifact_count(database)
    for changes, match in (
        (
            {
                "consumer_run_id": "consumer_stale_001",
                "session_id": "session_stale_001",
                "invocation_id": "invocation_stale_001",
                "injection_receipt_id": "injection_stale_001",
            },
            "source head is stale",
        ),
        (
            {
                "consumer_run_id": "consumer_prompt_001",
                "session_id": "session_prompt_001",
                "invocation_id": "invocation_prompt_001",
                "injection_receipt_id": "injection_prompt_001",
                "prompt": render_fresh_prompt(auth.brief) + b"substitution",
            },
            "prompt was substituted",
        ),
        (
            {
                "consumer_run_id": "consumer_duplicate_001",
                "session_id": "consumer_duplicate_001",
                "invocation_id": "invocation_duplicate_001",
                "injection_receipt_id": "injection_duplicate_001",
            },
            "fresh runtime",
        ),
    ):
        with pytest.raises(RuntimeBindingError, match=match):
            bind_and_dispatch(
                store=store,
                artifacts=artifacts,
                checkout_factory=checkout_factory,
                dispatch_callback=dispatch,
                **_runtime_args(auth, **changes),
            )
    assert calls == {"factory": 1, "dispatch": 1}
    assert _artifact_count(database) == artifacts_after_success

    substituted_payload = auth.brief.model_dump(mode="json", exclude={"brief_sha256"})
    substituted_payload["task_text"] = "Substituted task text."
    substituted = ContextBrief.model_validate(
        {
            **substituted_payload,
            "brief_sha256": canonical_json_sha256(substituted_payload),
        }
    )
    with pytest.raises(RuntimeBindingError, match="compiled decision or brief"):
        bind_and_dispatch(
            store=store,
            artifacts=artifacts,
            checkout_factory=checkout_factory,
            dispatch_callback=dispatch,
            **_runtime_args(
                CompiledHandoff(auth.decision, substituted, None),
                expected_brief_sha256=auth.brief.brief_sha256,
            ),
        )
    assert calls == {"factory": 1, "dispatch": 1}
    assert _artifact_count(database) == artifacts_after_success

    failure_database = tmp_path / "failure.sqlite3"
    failure_artifacts = SQLiteArtifactStore(failure_database)
    failure_store = SQLiteLineageStore(
        failure_database,
        artifact_resolver=failure_artifacts.resolve,
    )
    failure_source = "source_runtime_failure"
    failure_head = _seed_source(failure_store, failure_artifacts, failure_source)
    failure_compiled, _, _ = _compile(
        artifacts=failure_artifacts,
        source_run_id=failure_source,
        source_head=failure_head,
    )
    failed_checkout = tmp_path / "consumer_failure_001"

    def failure_factory(_run_id: str) -> Path:
        shutil.copytree(ROOT / GOLDEN.fixture.root, failed_checkout)
        return failed_checkout

    original_append = failure_store.append

    def fail_injection(run_id, expected_head, key, draft):
        if draft.event_type == LineageEventType.CONTEXT_INJECTED:
            raise LineageConflict("injected append failed")
        return original_append(run_id, expected_head, key, draft)

    monkeypatch.setattr(failure_store, "append", fail_injection)
    with pytest.raises(LineageConflict, match="injected append failed"):
        bind_and_dispatch(
            store=failure_store,
            artifacts=failure_artifacts,
            checkout_factory=failure_factory,
            dispatch_callback=forbidden_dispatch,
            **_runtime_args(
                failure_compiled,
                consumer_run_id="consumer_failure_001",
                session_id="session_failure_001",
                invocation_id="invocation_failure_001",
                injection_receipt_id="injection_failure_001",
            ),
        )
    assert not failed_checkout.exists()
    assert len(tuple(tmp_path.glob(".graphene-injection-failed-*"))) == 1
    assert calls["dispatch"] == 1
