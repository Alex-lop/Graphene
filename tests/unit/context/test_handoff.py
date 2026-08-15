from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from graphene.context import (
    AUTH_CAPABILITIES,
    HandoffCandidate,
    HandoffCompileError,
    build_injection_receipt,
    compile_handoff,
    render_fresh_prompt,
    source_candidate_set_sha256,
    start_handoff,
)
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.models import (
    BriefEvidence,
    EvidenceReference,
    GoldenContract,
    GraphMvpContract,
    HandoffDenied,
    HumanDecision,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    ScopeId,
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
HEAD = VerifiedHead(
    run_id="source_run",
    seq=7,
    event_sha256="b" * 64,
    event_count=7,
)
FORBIDDEN_CANARY = "FORBIDDEN_WORK_DATA_CANARY"


def _profile(profile_id: str):
    return next(item for item in GRAPH.catalog if item.agent_profile_id == profile_id)


def _memory(
    *,
    memory_id: str = "mem_auth_review",
    rule: str | None = None,
    path_globs: tuple[str, ...] | None = None,
    task_tags: tuple[str, ...] | None = None,
    scope_id: ScopeId = ScopeId.ALL_AUTH,
) -> MemoryRevision:
    spec = GOLDEN.memory
    proposed = MemoryRevision(
        memory_id=memory_id,
        revision=spec.revision,
        state=MemoryState.PROPOSED,
        rule=rule or spec.rule,
        repo_id=spec.repo_id,
        scope_id=scope_id,
        path_globs=path_globs or spec.path_globs,
        task_tags=task_tags or spec.task_tags,
        required_test_path=spec.required_test_path,
        required_check=spec.required_check,
        evidence_run_id="source_run",
        feedback_id="feedback_1",
    )
    decision = HumanDecision(
        decision_id="memory_decision_1",
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


def _evidence(evidence_id: str, summary: str, digest: str) -> HandoffCandidate:
    reference = EvidenceReference(kind="hunk", id=evidence_id, sha256=digest)
    return HandoffCandidate(
        candidate_kind="source_artifact",
        id=evidence_id,
        sha256=digest,
        evidence=BriefEvidence(
            evidence_id=evidence_id,
            summary=summary,
            reference=reference,
        ),
    )


def _sources() -> tuple[HandoffCandidate, ...]:
    return (
        _evidence("hunk_selected", "Observed the bounded Auth hunk.", "c" * 64),
        _evidence("hunk_excluded", FORBIDDEN_CANARY, "d" * 64),
        HandoffCandidate(
            candidate_kind="source_event",
            id="event_unselected",
            sha256="e" * 64,
        ),
    )


def _compile(**updates):
    values = {
        "decision_id": "handoff_decision_1",
        "brief_id": "brief_auth_1",
        "source_run_id": "source_run",
        "source_session_id": "source_session",
        "source_head": HEAD,
        "source_graph_sha256": "f" * 64,
        "repo_id": GOLDEN.repo_id,
        "base_sha": BASE_SHA,
        "task": GOLDEN.tasks[1],
        "target_profile": _profile("auth-maintainer@1"),
        "target_profile_revision": 1,
        "policy_revision": 1,
        "source_candidates": _sources(),
        "expected_source_candidate_set_sha256": source_candidate_set_sha256(
            _sources()
        ),
        "selected_evidence_ids": ("hunk_selected",),
        "approved_memories": (
            _memory(),
            _memory(
                memory_id="mem_billing_only",
                rule=FORBIDDEN_CANARY,
                path_globs=("billing/**",),
                task_tags=("billing",),
            ),
        ),
        "policy_required_paths": (GOLDEN.memory.required_test_path,),
        "read_scope": (
            "tests/test_security_policy.py",
            "app/auth/limiter.py",
        ),
        "write_scope": GOLDEN.tasks[1].expected_changed_paths,
        "capabilities": AUTH_CAPABILITIES,
        "fixed_test_profile": GRAPH.required_test_profile,
        "byte_caps": {"read": 32_768, "write": 32_768},
        "event_caps": {"run": 256},
        "server_recorded_at": NOW,
    }
    values.update(updates)
    return compile_handoff(**values)


def test_auth_compiler_is_order_deterministic_complete_and_included_only():
    sources = _sources()
    first = _compile(source_candidates=sources)
    second = _compile(
        source_candidates=reversed(sources),
        read_scope=reversed(
            ("tests/test_security_policy.py", "app/auth/limiter.py")
        ),
        policy_required_paths=iter((GOLDEN.memory.required_test_path,)),
        capabilities=iter(AUTH_CAPABILITIES),
    )

    assert first == second
    assert first.brief is not None and first.denial is None
    assert first.decision.schema_version == first.brief.schema_version == 2
    assert tuple(
        (item.candidate_kind, item.id) for item in first.decision.entries
    ) == tuple(
        sorted((item.candidate_kind, item.id) for item in first.decision.entries)
    )
    assert len(first.decision.entries) == len(
        {(item.candidate_kind, item.id) for item in first.decision.entries}
    )
    assert {item.candidate_kind for item in first.decision.entries} >= {
        "source_artifact",
        "source_event",
        "memory_revision",
        "task_target",
        "policy_required_path",
        "read_scope",
        "write_scope",
        "capability",
        "fixed_test_profile",
    }
    assert FORBIDDEN_CANARY not in first.brief.model_dump_json()
    assert FORBIDDEN_CANARY.encode() not in render_fresh_prompt(first.brief)
    memory_entries = [
        item for item in first.decision.entries if item.candidate_kind == "memory_revision"
    ]
    assert sorted(item.reason_code for item in memory_entries) == [
        "approved_memory_applies",
        "memory_not_applicable",
    ]
    assert tuple(item.memory_id for item in first.brief.approved_memories) == (
        "mem_auth_review",
    )

    with pytest.raises(HandoffCompileError, match="source candidate set digest"):
        _compile(source_candidates=sources[:-1])


def test_selected_evidence_changes_decision_brief_prompt_and_open_allowlist():
    first = _compile(selected_evidence_ids=("hunk_selected",))
    second = _compile(selected_evidence_ids=("hunk_excluded",))
    assert first.brief is not None and second.brief is not None

    assert first.decision.candidate_set_sha256 == second.decision.candidate_set_sha256
    assert first.decision.decision_sha256 != second.decision.decision_sha256
    assert first.brief.brief_sha256 != second.brief.brief_sha256
    assert render_fresh_prompt(first.brief) != render_fresh_prompt(second.brief)
    assert first.open_evidence_allowlist == ("hunk_selected",)
    assert second.open_evidence_allowlist == ("hunk_excluded",)


def test_broad_and_narrow_memory_scopes_change_included_context():
    broad = _compile(approved_memories=(_memory(),))
    narrow = _compile(
        approved_memories=(
            _memory(
                scope_id=ScopeId.RATE_LIMITER_ONLY,
                path_globs=("app/auth/limiter.py",),
                task_tags=("authentication", "security", "rate-limiter"),
            ),
        )
    )
    assert broad.brief is not None and narrow.brief is not None

    broad_memory = broad.brief.approved_memories[0]
    narrow_memory = narrow.brief.approved_memories[0]
    assert (broad_memory.scope_id, broad_memory.path_globs) == (
        ScopeId.ALL_AUTH,
        ("app/auth/**",),
    )
    assert (narrow_memory.scope_id, narrow_memory.path_globs) == (
        ScopeId.RATE_LIMITER_ONLY,
        ("app/auth/limiter.py",),
    )
    assert broad.brief.brief_sha256 != narrow.brief.brief_sha256
    assert render_fresh_prompt(broad.brief) != render_fresh_prompt(narrow.brief)


def test_billing_returns_only_safe_zero_context_and_never_starts():
    billing = _compile(
        target_profile=_profile("billing-observer@1"),
        capabilities=(),
    )
    calls = []
    visible = start_handoff(billing, lambda brief: calls.append(brief))

    assert calls == []
    assert billing.brief is None
    assert isinstance(visible, HandoffDenied)
    assert visible.model_dump(mode="json") == {
        "schema_version": 2,
        "source_run_id": "source_run",
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
    assert FORBIDDEN_CANARY not in visible.model_dump_json()


def test_prompt_embeds_full_canonical_brief_and_receipt_binds_fresh_identity():
    compiled = _compile()
    assert compiled.brief is not None
    brief = compiled.brief
    prompt = render_fresh_prompt(brief)
    marker = (
        f"CONTEXT BRIEF (canonical JSON; sha256:{brief.brief_sha256})\n".encode()
    )
    embedded = prompt.split(marker, 1)[1]

    assert embedded == canonical_json_bytes(brief.model_dump(mode="json"))
    parsed = json.loads(embedded)
    assert parsed == brief.model_dump(mode="json")
    assert brief.brief_sha256 == canonical_json_sha256(
        brief.model_dump(mode="json", exclude={"brief_sha256"})
    )

    receipt = build_injection_receipt(
        receipt_id="injection_receipt_1",
        consumer_run_id="consumer_run",
        decision=compiled.decision,
        brief=brief,
        prompt=prompt,
        session_id="fresh_session",
        invocation_id="fresh_invocation",
        model_id="gemini-3.5-flash",
        injected_at=NOW,
    )
    assert receipt.prompt_sha256 == sha256_hex(prompt)
    assert receipt.brief_sha256 == brief.brief_sha256
    assert receipt.target_profile_revision == receipt.policy_revision == 1
    assert receipt.prior_message_count == 0
    assert receipt.persisted_before_dispatch is True
    assert {receipt.consumer_run_id, receipt.session_id, receipt.invocation_id}.isdisjoint(
        {brief.source_run_id, brief.source_session_id}
    )

    with pytest.raises(HandoffCompileError, match="distinct"):
        build_injection_receipt(
            receipt_id="injection_receipt_2",
            consumer_run_id="consumer_run",
            decision=compiled.decision,
            brief=brief,
            prompt=prompt,
            session_id="source_session",
            invocation_id="fresh_invocation_2",
            model_id="gemini-3.5-flash",
            injected_at=NOW,
        )
    with pytest.raises(HandoffCompileError, match="distinct"):
        build_injection_receipt(
            receipt_id="injection_receipt_3",
            consumer_run_id="fresh_session",
            decision=compiled.decision,
            brief=brief,
            prompt=prompt,
            session_id="fresh_session",
            invocation_id="fresh_invocation_3",
            model_id="gemini-3.5-flash",
            injected_at=NOW,
        )


def test_auth_rejects_non_frozen_capabilities_and_unverified_selection():
    with pytest.raises(HandoffCompileError, match="capabilities"):
        _compile(capabilities=AUTH_CAPABILITIES[:-1])
    with pytest.raises(HandoffCompileError, match="absent"):
        _compile(selected_evidence_ids=("not_verified",))


def test_selected_evidence_dependency_closure_is_verified_and_included():
    selected, excluded, event = _sources()
    selected = HandoffCandidate(
        candidate_kind=selected.candidate_kind,
        id=selected.id,
        sha256=selected.sha256,
        evidence=selected.evidence,
        dependency_ids=(event.id,),
    )
    sources = (selected, excluded, event)
    compiled = _compile(
        source_candidates=sources,
        expected_source_candidate_set_sha256=source_candidate_set_sha256(sources),
    )
    dependency = next(item for item in compiled.decision.entries if item.id == event.id)
    assert dependency.include is True
    assert dependency.reason_code == "selected_evidence_dependency"

    broken = (
        HandoffCandidate(
            candidate_kind=selected.candidate_kind,
            id=selected.id,
            sha256=selected.sha256,
            evidence=selected.evidence,
            dependency_ids=("missing_event",),
        ),
        excluded,
        event,
    )
    with pytest.raises(HandoffCompileError, match="dependency is absent"):
        _compile(
            source_candidates=broken,
            expected_source_candidate_set_sha256=source_candidate_set_sha256(broken),
        )
