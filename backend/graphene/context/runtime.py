from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from ..hashing import sha256_hex
from ..lineage.artifacts import SQLiteArtifactStore
from ..lineage.service import EvidenceItem, RuntimeHandle
from ..lineage.store import SQLiteLineageStore
from ..models import (
    ContextBrief,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    FixturePolicy,
    HandoffDenied,
    HunkEvidence,
    LineageAuthority,
    LineageEventType,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from .handoff import (
    CompiledHandoff,
    build_injection_receipt,
    render_fresh_prompt,
)


class RuntimeBindingError(RuntimeError):
    pass


def _runtime_checkout(value: Path, consumer_run_id: str) -> Path:
    if not value.is_absolute() or value.is_symlink():
        raise RuntimeBindingError("runtime checkout is not a fresh absolute directory")
    try:
        checkout = value.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise RuntimeBindingError("runtime checkout is unavailable") from error
    root = Path(checkout.anchor)
    if (
        not checkout.is_dir()
        or checkout.name != consumer_run_id
        or checkout.parent == root
        or checkout in {Path.cwd().resolve(), Path.home().resolve()}
    ):
        raise RuntimeBindingError("runtime checkout identity is unsafe")
    return checkout


def _quarantine_checkout(checkout: Path, consumer_run_id: str) -> None:
    quarantine = checkout.parent / (
        ".graphene-injection-failed-"
        + sha256_hex(f"{consumer_run_id}\0{checkout}".encode())[:24]
    )
    if quarantine.exists() or quarantine.is_symlink():
        raise RuntimeBindingError("runtime checkout quarantine is unavailable")
    parent_fd = os.open(
        checkout.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.rename(
            checkout.name,
            quarantine.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except OSError as error:
        raise RuntimeBindingError("runtime checkout quarantine failed") from error
    finally:
        os.close(parent_fd)


def _source_ref(kind: SourceKind, reference) -> SourceReference:
    return SourceReference(kind=kind, id=reference.id, sha256=reference.sha256)


def _head(event: Event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _runtime_evidence(
    brief: ContextBrief,
    artifacts: SQLiteArtifactStore,
) -> tuple[EvidenceItem, ...]:
    evidence: list[EvidenceItem] = []
    for item in brief.selected_evidence:
        reference = item.reference
        raw = artifacts.resolve(reference.kind.value, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise RuntimeBindingError("selected evidence artifact is unresolved")
        try:
            record = json.loads(raw)
            content = record.get("content")
            if content is None and reference.kind == EvidenceKind.HUNK:
                content = HunkEvidence.model_validate(record).unified_diff
        except (AttributeError, TypeError, ValueError, UnicodeError) as error:
            raise RuntimeBindingError(
                "selected evidence artifact has no authorized content"
            ) from error
        if not isinstance(record, dict) or not isinstance(content, str):
            raise RuntimeBindingError(
                "selected evidence artifact has no authorized content"
            )
        evidence.append(
            EvidenceItem(
                reference=reference,
                content=content,
                content_sha256=sha256_hex(content.encode()),
            )
        )
    return tuple(evidence)


_T = TypeVar("_T")


def bind_and_dispatch(
    *,
    compiled: CompiledHandoff,
    store: SQLiteLineageStore,
    artifacts: SQLiteArtifactStore,
    source_expected_head: VerifiedHead,
    expected_decision_sha256: str,
    expected_brief_sha256: str | None,
    consumer_run_id: str | None,
    session_id: str | None,
    invocation_id: str | None,
    model_id: str | None,
    injection_receipt_id: str | None,
    prompt: bytes | None,
    fixture_policy: FixturePolicy | None,
    checkout_factory: Callable[[str], Path] | None,
    dispatch_callback: Callable[[bytes, RuntimeHandle], _T] | None,
    context_compiled_idempotency_key: str,
    consumer_started_idempotency_key: str,
    context_injected_idempotency_key: str,
    injected_at: datetime,
) -> _T | HandoffDenied:
    """Commit an included-only handoff before exposing it to a fresh runtime."""

    decision = compiled.decision
    if compiled.denial is not None:
        denial = compiled.denial
        if (
            compiled.brief is not None
            or decision.decision != "denied"
            or decision.decision_sha256 != expected_decision_sha256
            or expected_brief_sha256 is not None
            or denial.source_run_id != decision.source_run_id
            or denial.target_profile_id != decision.target_profile_id
            or denial.task_id != decision.task_id
            or denial.reason_code not in decision.safe_reason_codes
        ):
            raise RuntimeBindingError("denied handoff compilation is inconsistent")
        if source_expected_head != decision.source_head:
            raise RuntimeBindingError("source expected head does not match the compilation")
        source_events = store.tail(decision.source_run_id, 0, 1)
        if not source_events:
            raise RuntimeBindingError("source run has no identity event")
        source_identity = source_events[0]
        if (
            source_identity.repo_id != decision.repo_id
            or source_identity.base_sha != decision.base_sha
            or source_identity.policy_revision != decision.policy_revision
        ):
            raise RuntimeBindingError("source run identity does not match the compilation")
        decision_ref = artifacts(
            EvidenceKind.HANDOFF_DECISION,
            decision.model_dump(mode="json"),
        )
        store.append(
            decision.source_run_id,
            source_expected_head,
            context_compiled_idempotency_key,
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=decision.repo_id,
                base_sha=decision.base_sha,
                agent_profile_id=source_identity.agent_profile_id,
                policy_revision=decision.policy_revision,
                event_type=LineageEventType.HANDOFF_DENIED,
                truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                authority=LineageAuthority.CONTEXT_COMPILER,
                references=(decision_ref,),
                source_ref=_source_ref(
                    SourceKind.CONTEXT_COMPILER_RECEIPT,
                    decision_ref,
                ),
                payload={
                    "reason_code": denial.reason_code,
                    "target_profile_id": denial.target_profile_id,
                    "task_id": denial.task_id,
                    "memory_count": denial.memory_count,
                    "evidence_count": denial.evidence_count,
                    "source_path_count": denial.source_path_count,
                    "tool_count": denial.tool_count,
                    "model_dispatch_count": denial.model_dispatch_count,
                    "status": "denied",
                },
            ),
        )
        return denial

    brief = compiled.brief
    if compiled.denial is not None or brief is None or decision.decision != "allowed":
        raise RuntimeBindingError("allowed handoff compilation is inconsistent")
    if (
        decision.decision_sha256 != expected_decision_sha256
        or brief.brief_sha256 != expected_brief_sha256
    ):
        raise RuntimeBindingError("compiled decision or brief was substituted")
    if prompt is None or prompt != render_fresh_prompt(brief):
        raise RuntimeBindingError("fresh-agent prompt was substituted")
    if any(
        value is None
        for value in (
            consumer_run_id,
            session_id,
            invocation_id,
            model_id,
            injection_receipt_id,
            fixture_policy,
            checkout_factory,
            dispatch_callback,
        )
    ):
        raise RuntimeBindingError("allowed handoff is missing runtime inputs")

    assert consumer_run_id is not None
    assert session_id is not None
    assert invocation_id is not None
    assert model_id is not None
    assert injection_receipt_id is not None
    assert fixture_policy is not None
    assert checkout_factory is not None
    assert dispatch_callback is not None

    try:
        injection = build_injection_receipt(
            receipt_id=injection_receipt_id,
            consumer_run_id=consumer_run_id,
            decision=decision,
            brief=brief,
            prompt=prompt,
            session_id=session_id,
            invocation_id=invocation_id,
            model_id=model_id,
            injected_at=injected_at,
        )
    except ValueError as error:
        raise RuntimeBindingError("fresh runtime or compilation binding is invalid") from error
    if source_expected_head != decision.source_head:
        raise RuntimeBindingError("source expected head does not match the compilation")

    actual_source_head = store.verify(decision.source_run_id)
    if isinstance(actual_source_head, EvidenceInvalidState):
        raise RuntimeBindingError("source evidence is invalid")
    if actual_source_head != source_expected_head:
        raise RuntimeBindingError("source head is stale")
    empty_consumer_head = store.verify(consumer_run_id)
    if isinstance(empty_consumer_head, EvidenceInvalidState):
        raise RuntimeBindingError("consumer evidence is invalid")
    expected_empty = VerifiedHead(
        run_id=consumer_run_id,
        seq=0,
        event_sha256=None,
        event_count=0,
    )
    if empty_consumer_head != expected_empty:
        raise RuntimeBindingError("consumer run ID already exists")

    source_events = store.tail(decision.source_run_id, 0, 1)
    if not source_events:
        raise RuntimeBindingError("source run has no identity event")
    source_identity = source_events[0]
    if (
        source_identity.repo_id != decision.repo_id
        or source_identity.base_sha != decision.base_sha
        or source_identity.policy_revision != decision.policy_revision
    ):
        raise RuntimeBindingError("source run identity does not match the compilation")

    runtime_evidence = _runtime_evidence(brief, artifacts)
    decision_ref = artifacts(
        EvidenceKind.HANDOFF_DECISION,
        decision.model_dump(mode="json"),
    )
    brief_ref = artifacts(
        EvidenceKind.CONTEXT_BRIEF,
        brief.model_dump(mode="json"),
    )
    compiled_source = _source_ref(
        SourceKind.CONTEXT_COMPILER_RECEIPT,
        decision_ref,
    )
    compiled_event = store.append(
        decision.source_run_id,
        source_expected_head,
        context_compiled_idempotency_key,
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=decision.repo_id,
            base_sha=decision.base_sha,
            agent_profile_id=source_identity.agent_profile_id,
            policy_revision=decision.policy_revision,
            event_type=LineageEventType.CONTEXT_COMPILED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.CONTEXT_COMPILER,
            references=(decision_ref, brief_ref),
            source_ref=compiled_source,
            payload={
                "candidate_set_sha256": decision.candidate_set_sha256,
                "decision_sha256": decision.decision_sha256,
                "brief_sha256": brief.brief_sha256,
                "decision_artifact_sha256": decision_ref.sha256,
                "brief_artifact_sha256": brief_ref.sha256,
                "source_graph_sha256": brief.source_graph_sha256,
            },
        ),
    )

    started_artifact = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {
            "schema_version": 2,
            "action": "run.started",
            "consumer_run_id": consumer_run_id,
            "context_compiled_event_sha256": compiled_event.event_sha256,
        },
    )
    started_source = _source_ref(SourceKind.LIFECYCLE_REQUEST, started_artifact)
    started_event = store.append(
        consumer_run_id,
        expected_empty,
        consumer_started_idempotency_key,
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=brief.repo_id,
            base_sha=brief.base_sha,
            agent_profile_id=brief.target_profile_id,
            policy_revision=brief.policy_revision,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=started_source,
            payload={
                "state": "STARTING",
                "source_run_id": brief.source_run_id,
                "context_compiled_event_sha256": compiled_event.event_sha256,
            },
        ),
    )

    injection_ref = artifacts(
        EvidenceKind.INJECTION_RECEIPT,
        injection.model_dump(mode="json"),
    )
    injected_source = _source_ref(
        SourceKind.CONTEXT_COMPILER_RECEIPT,
        injection_ref,
    )
    checkout_root = _runtime_checkout(
        checkout_factory(consumer_run_id),
        consumer_run_id,
    )
    try:
        injected_event = store.append(
            consumer_run_id,
            _head(started_event),
            context_injected_idempotency_key,
            EventInput(
                session_id=session_id,
                invocation_id=invocation_id,
                model_id=model_id,
                tool_call_id=None,
                repo_id=brief.repo_id,
                base_sha=brief.base_sha,
                agent_profile_id=brief.target_profile_id,
                policy_revision=brief.policy_revision,
                event_type=LineageEventType.CONTEXT_INJECTED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.CONTEXT_COMPILER,
                references=(decision_ref, brief_ref, injection_ref),
                source_ref=injected_source,
                payload={
                    "decision_sha256": injection.decision_sha256,
                    "brief_sha256": injection.brief_sha256,
                    "prompt_sha256": injection.prompt_sha256,
                    "injection_receipt_sha256": injection.receipt_sha256,
                    "prior_message_count": injection.prior_message_count,
                    "source_run_id": brief.source_run_id,
                    "source_head_seq": brief.source_head.seq,
                },
            ),
        )

        handle = RuntimeHandle(
            run_id=consumer_run_id,
            repo_id=brief.repo_id,
            base_sha=brief.base_sha,
            agent_profile_id=brief.target_profile_id,
            policy_revision=brief.policy_revision,
            session_id=session_id,
            invocation_id=invocation_id,
            model_id=model_id,
            read_scope=brief.read_scope,
            write_scope=brief.write_scope,
            tools=brief.tools,
            evidence=runtime_evidence,
            fixed_test_profile=brief.fixed_test_profile,
            fixture_policy=fixture_policy,
            checkout_root=checkout_root,
            initial_head=_head(injected_event),
            max_result_bytes=min(brief.byte_caps.values()),
            max_search_matches=min(12, min(brief.event_caps.values())),
        )
    except Exception:
        _quarantine_checkout(checkout_root, consumer_run_id)
        raise
    return dispatch_callback(prompt, handle)
