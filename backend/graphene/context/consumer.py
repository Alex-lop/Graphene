from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..bootstrap import (
    LOCAL_MODEL_ID,
    BootstrapConfigurationError,
    BootstrapConflict,
    _checkout,
    _database,
    _expected_checkout_files,
    _repository,
    _stable_id,
)
from ..hashing import canonical_json_sha256, sha256_hex
from ..lineage.artifacts import SQLiteArtifactStore
from ..lineage.service import (
    RuntimeHandle,
    RuntimeIntegrityError,
    ScopedApplicationService,
)
from ..lineage.store import LineageStoreError, SQLiteLineageStore
from ..models import (
    ContextBrief,
    ContextInjectionReceipt,
    EvidenceInvalidState,
    EvidenceKind,
    HandoffDecision,
    HandoffDenied,
    LineageEventType,
)
from .handoff import CompiledHandoff, render_fresh_prompt
from .runtime import RuntimeBindingError, _runtime_evidence, bind_and_dispatch


class ConsumerStartError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FreshConsumer:
    database_path: Path
    checkout_root: Path
    prompt: bytes = field(repr=False)
    artifacts: SQLiteArtifactStore = field(repr=False, compare=False)
    store: SQLiteLineageStore = field(repr=False, compare=False)
    service: ScopedApplicationService = field(repr=False, compare=False)
    handle: RuntimeHandle = field(repr=False, compare=False)

    @property
    def run_id(self) -> str:
        return self.handle.run_id

    @property
    def session_id(self) -> str:
        return self.handle.session_id

    @property
    def invocation_id(self) -> str:
        return self.handle.invocation_id


def _frozen_binding(brief, decision, golden, graph, base_sha) -> None:
    task = next(
        (item for item in golden.tasks if item.task_id.value == brief.task_id),
        None,
    )
    profile = next(
        (
            item
            for item in graph.catalog
            if item.agent_profile_id == brief.target_profile_id
        ),
        None,
    )
    binding = next(
        (item for item in graph.task_profiles if item.task_id.value == brief.task_id),
        None,
    )
    if (
        brief.repo_id != golden.repo_id
        or brief.base_sha != base_sha
        or brief.fixed_test_profile != graph.required_test_profile
        or task is None
        or profile is None
        or binding is None
        or binding.agent_profile_id != profile.agent_profile_id
        or not binding.fresh_session
        or profile.policy_revision != brief.policy_revision
        or brief.repo_id not in profile.repo_ids
        or tuple(task.expected_changed_paths) != brief.write_scope
        or brief.source_head != decision.source_head
        or decision.decision != "allowed"
        or decision.source_run_id != brief.source_run_id
        or decision.repo_id != brief.repo_id
        or decision.base_sha != brief.base_sha
        or decision.task_id != brief.task_id
        or decision.target_profile_id != brief.target_profile_id
        or decision.target_profile_revision != brief.target_profile_revision
        or decision.policy_revision != brief.policy_revision
    ):
        raise ConsumerStartError("consumer brief does not match the frozen repository")


def _record(artifacts, reference, model):
    try:
        raw = artifacts.resolve(reference.kind.value, reference.id)
    except (LineageStoreError, OSError, sqlite3.Error) as error:
        raise ConsumerStartError("consumer context artifact is unresolved") from error
    if raw is None or sha256_hex(raw) != reference.sha256:
        raise ConsumerStartError("consumer context artifact is unresolved")
    try:
        return model.model_validate_json(raw)
    except ValueError as error:
        raise ConsumerStartError("consumer context artifact is malformed") from error


def _verified_events(store, run_id, head):
    events = []
    after_seq = 0
    try:
        while after_seq < head.seq:
            page = store.tail(run_id, after_seq, min(256, head.seq - after_seq))
            if not page or page[0].seq != after_seq + 1:
                raise ConsumerStartError("consumer lineage is incomplete")
            events.extend(page)
            after_seq = page[-1].seq
        stable_head = store.verify(run_id)
    except ConsumerStartError:
        raise
    except (LineageStoreError, OSError, sqlite3.Error, ValueError) as error:
        raise ConsumerStartError("consumer lineage cannot be verified") from error
    if (
        isinstance(stable_head, EvidenceInvalidState)
        or stable_head != head
        or len(events) != head.event_count
        or (events and events[-1].event_sha256 != head.event_sha256)
    ):
        raise ConsumerStartError("consumer lineage changed during resume")
    return tuple(events)


def start_fresh_consumer(
    compiled: CompiledHandoff,
    database_path: str | Path,
    *,
    repository_root: str | Path | None = None,
    injected_at: datetime | None = None,
) -> FreshConsumer | HandoffDenied:
    """Persist and return a fresh deterministic runtime; never dispatch a model."""

    if compiled.denial is not None:
        return compiled.denial
    brief = compiled.brief
    if brief is None or compiled.decision.decision != "allowed":
        raise ConsumerStartError("allowed handoff compilation is inconsistent")

    try:
        repository, golden, graph, fixture, base_sha = _repository(repository_root)
        database = _database(database_path, repository)
    except (BootstrapConfigurationError, BootstrapConflict) as error:
        raise ConsumerStartError("consumer runtime configuration is invalid") from error
    _frozen_binding(brief, compiled.decision, golden, graph, base_sha)

    namespace = canonical_json_sha256(
        {
            "database_path": str(database),
            "decision_sha256": compiled.decision.decision_sha256,
            "brief_sha256": brief.brief_sha256,
        }
    )
    run_id = _stable_id("consumer", namespace)
    session_id = _stable_id("session", namespace)
    invocation_id = _stable_id("invocation", namespace)
    if len({run_id, session_id, invocation_id, brief.source_run_id}) != 4 or (
        brief.source_session_id is not None
        and brief.source_session_id in {run_id, session_id, invocation_id}
    ):
        raise ConsumerStartError("fresh consumer identities overlap the source")

    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    checkout = database.parent / "checkouts" / run_id

    def checkout_factory(expected_run_id: str) -> Path:
        if expected_run_id != run_id:
            raise ConsumerStartError("consumer checkout identity changed")
        _checkout(
            checkout,
            checkout.parent,
            golden=golden,
            fixture=fixture,
            expected_base_sha=base_sha,
            expected_files=_expected_checkout_files(
                golden=golden,
                fixture=fixture,
                events=(),
                artifacts=artifacts,
            ),
            max_file_bytes=golden.fixture.max_write_bytes,
        )
        return checkout

    def constructed(prompt: bytes, handle: RuntimeHandle) -> FreshConsumer:
        return FreshConsumer(
            database_path=database,
            checkout_root=checkout,
            prompt=prompt,
            artifacts=artifacts,
            store=store,
            service=ScopedApplicationService(store, artifacts),
            handle=handle,
        )

    key = canonical_json_sha256(
        {
            "consumer_run_id": run_id,
            "decision_sha256": compiled.decision.decision_sha256,
            "brief_sha256": brief.brief_sha256,
        }
    )
    try:
        return bind_and_dispatch(
            compiled=compiled,
            store=store,
            artifacts=artifacts,
            source_expected_head=compiled.decision.source_head,
            expected_decision_sha256=compiled.decision.decision_sha256,
            expected_brief_sha256=brief.brief_sha256,
            consumer_run_id=run_id,
            session_id=session_id,
            invocation_id=invocation_id,
            model_id=LOCAL_MODEL_ID,
            injection_receipt_id=_stable_id("injection", namespace),
            prompt=render_fresh_prompt(brief),
            fixture_policy=golden.fixture,
            checkout_factory=checkout_factory,
            dispatch_callback=constructed,
            context_compiled_idempotency_key="compiled_" + key[:32],
            consumer_started_idempotency_key="consumer_" + key[:32],
            context_injected_idempotency_key="injected_" + key[:32],
            injected_at=(injected_at or datetime.now(UTC)),
        )
    except (BootstrapConflict, LineageStoreError, RuntimeBindingError) as error:
        raise ConsumerStartError("fresh consumer start failed") from error


def resume_fresh_consumer(
    database_path: str | Path,
    run_id: str,
    *,
    repository_root: str | Path | None = None,
) -> FreshConsumer:
    """Rehydrate one already-injected fresh consumer; never dispatch a model."""

    try:
        if not Path(database_path).exists():
            raise ConsumerStartError("consumer resume database is unavailable")
        repository, golden, graph, fixture, base_sha = _repository(repository_root)
        database = _database(database_path, repository)
        artifacts = SQLiteArtifactStore(database)
        store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    except (
        BootstrapConfigurationError,
        BootstrapConflict,
        LineageStoreError,
        OSError,
        sqlite3.Error,
        ConsumerStartError,
    ) as error:
        raise ConsumerStartError("consumer resume configuration is invalid") from error

    try:
        head = store.verify(run_id)
    except (LineageStoreError, OSError, sqlite3.Error, ValueError) as error:
        raise ConsumerStartError("consumer run cannot be verified") from error
    if isinstance(head, EvidenceInvalidState) or head.seq < 2:
        raise ConsumerStartError("consumer run is absent or invalid")
    events = _verified_events(store, run_id, head)
    if (
        len(events) != head.event_count
        or events[-1].event_sha256 != head.event_sha256
        or events[0].event_type != LineageEventType.RUN_STARTED
        or events[0].payload.get("source_run_id") is None
        or set(events[0].payload)
        != {"state", "source_run_id", "context_compiled_event_sha256"}
        or events[0].payload.get("state") != "STARTING"
    ):
        raise ConsumerStartError("consumer run is not a fresh injected runtime")
    injected = tuple(
        event
        for event in events
        if event.event_type == LineageEventType.CONTEXT_INJECTED
    )
    if len(injected) != 1:
        raise ConsumerStartError("consumer run lacks one context injection")
    injected_event = injected[0]
    references = {reference.kind: reference for reference in injected_event.references}
    if (
        injected_event.seq != 2
        or len(injected_event.references) != 3
        or set(references)
        != {
            EvidenceKind.HANDOFF_DECISION,
            EvidenceKind.CONTEXT_BRIEF,
            EvidenceKind.INJECTION_RECEIPT,
        }
        or set(injected_event.payload)
        != {
            "decision_sha256",
            "brief_sha256",
            "prompt_sha256",
            "injection_receipt_sha256",
            "prior_message_count",
            "source_run_id",
            "source_head_seq",
        }
        or injected_event.source_ref.id != references[EvidenceKind.INJECTION_RECEIPT].id
        or injected_event.source_ref.sha256
        != references[EvidenceKind.INJECTION_RECEIPT].sha256
    ):
        raise ConsumerStartError("consumer injection references are not exact")
    decision = _record(
        artifacts,
        references[EvidenceKind.HANDOFF_DECISION],
        HandoffDecision,
    )
    brief = _record(
        artifacts,
        references[EvidenceKind.CONTEXT_BRIEF],
        ContextBrief,
    )
    injection = _record(
        artifacts,
        references[EvidenceKind.INJECTION_RECEIPT],
        ContextInjectionReceipt,
    )
    namespace = canonical_json_sha256(
        {
            "database_path": str(database),
            "decision_sha256": decision.decision_sha256,
            "brief_sha256": brief.brief_sha256,
        }
    )
    expected_run_id = _stable_id("consumer", namespace)
    expected_session_id = _stable_id("session", namespace)
    expected_invocation_id = _stable_id("invocation", namespace)
    identities = {
        expected_run_id,
        expected_session_id,
        expected_invocation_id,
        brief.source_run_id,
    }
    if (
        run_id != expected_run_id
        or injection.session_id != expected_session_id
        or injection.invocation_id != expected_invocation_id
        or injection.receipt_id != _stable_id("injection", namespace)
        or len(identities) != 4
        or brief.source_session_id in identities
    ):
        raise ConsumerStartError("consumer fresh identity binding changed")
    prompt = render_fresh_prompt(brief)
    if (
        decision.decision_sha256 != injected_event.payload.get("decision_sha256")
        or brief.brief_sha256 != injected_event.payload.get("brief_sha256")
        or injection.receipt_sha256
        != injected_event.payload.get("injection_receipt_sha256")
        or injection.consumer_run_id != run_id
        or injection.decision_sha256 != decision.decision_sha256
        or injection.brief_sha256 != brief.brief_sha256
        or injection.prompt_sha256 != sha256_hex(prompt)
        or injection.target_profile_id != brief.target_profile_id
        or injection.target_profile_revision != brief.target_profile_revision
        or injection.policy_revision != brief.policy_revision
        or injected_event.payload.get("prompt_sha256") != injection.prompt_sha256
        or injected_event.payload.get("prior_message_count") != 0
        or injection.session_id != injected_event.session_id
        or injection.invocation_id != injected_event.invocation_id
        or injection.model_id != injected_event.model_id
        or injection.prior_message_count != 0
        or not injection.persisted_before_dispatch
        or injected_event.payload.get("source_run_id") != brief.source_run_id
        or injected_event.payload.get("source_head_seq") != brief.source_head.seq
        or events[0].payload.get("source_run_id") != brief.source_run_id
        or events[0].repo_id != brief.repo_id
        or events[0].base_sha != brief.base_sha
        or events[0].agent_profile_id != brief.target_profile_id
        or events[0].policy_revision != brief.policy_revision
    ):
        raise ConsumerStartError("consumer injection binding changed")
    _frozen_binding(brief, decision, golden, graph, base_sha)

    try:
        source_head = store.verify(brief.source_run_id)
    except (LineageStoreError, OSError, sqlite3.Error, ValueError) as error:
        raise ConsumerStartError(
            "consumer source lineage cannot be verified"
        ) from error
    if (
        isinstance(source_head, EvidenceInvalidState)
        or brief.source_head.seq < 1
        or source_head.seq < brief.source_head.seq
    ):
        raise ConsumerStartError("consumer source lineage is unavailable")
    source_events = _verified_events(store, brief.source_run_id, source_head)
    compiled = tuple(
        event
        for event in source_events[brief.source_head.seq :]
        if event.event_type == LineageEventType.CONTEXT_COMPILED
        and event.seq == brief.source_head.seq + 1
        and len(event.references) == 2
        and references[EvidenceKind.HANDOFF_DECISION] in event.references
        and references[EvidenceKind.CONTEXT_BRIEF] in event.references
        and event.payload.get("decision_sha256") == decision.decision_sha256
        and event.payload.get("brief_sha256") == brief.brief_sha256
        and event.payload.get("decision_artifact_sha256")
        == references[EvidenceKind.HANDOFF_DECISION].sha256
        and event.payload.get("brief_artifact_sha256")
        == references[EvidenceKind.CONTEXT_BRIEF].sha256
        and event.source_ref.id == references[EvidenceKind.HANDOFF_DECISION].id
        and event.source_ref.sha256 == references[EvidenceKind.HANDOFF_DECISION].sha256
    )
    try:
        started_raw = artifacts.resolve(
            events[0].source_ref.kind.value,
            events[0].source_ref.id,
        )
        started_record = None if started_raw is None else json.loads(started_raw)
    except (LineageStoreError, OSError, sqlite3.Error, ValueError) as error:
        raise ConsumerStartError("consumer start binding is unavailable") from error
    if (
        len(source_events) != source_head.event_count
        or source_events[brief.source_head.seq - 1].event_sha256
        != brief.source_head.event_sha256
        or len(compiled) != 1
        or events[0].payload.get("context_compiled_event_sha256")
        != compiled[0].event_sha256
        or started_record
        != {
            "action": "run.started",
            "consumer_run_id": run_id,
            "context_compiled_event_sha256": compiled[0].event_sha256,
            "schema_version": 2,
        }
    ):
        raise ConsumerStartError("consumer source binding is not retained")

    checkout = database.parent / "checkouts" / run_id
    try:
        _checkout(
            checkout,
            checkout.parent,
            golden=golden,
            fixture=fixture,
            expected_base_sha=base_sha,
            expected_files=_expected_checkout_files(
                golden=golden,
                fixture=fixture,
                events=events,
                artifacts=artifacts,
            ),
            max_file_bytes=golden.fixture.max_write_bytes,
        )
        service = ScopedApplicationService(store, artifacts)
        handle = service.create_handle(
            run_id=run_id,
            repo_id=brief.repo_id,
            base_sha=brief.base_sha,
            agent_profile_id=brief.target_profile_id,
            policy_revision=brief.policy_revision,
            session_id=injection.session_id,
            invocation_id=injection.invocation_id,
            model_id=injection.model_id,
            read_scope=brief.read_scope,
            write_scope=brief.write_scope,
            tools=brief.tools,
            evidence=_runtime_evidence(brief, artifacts),
            fixed_test_profile=brief.fixed_test_profile,
            fixture_policy=golden.fixture,
            checkout_root=checkout,
            max_result_bytes=min(brief.byte_caps.values()),
            max_search_matches=min(12, min(brief.event_caps.values())),
        )
    except (
        BootstrapConflict,
        LineageStoreError,
        OSError,
        RuntimeBindingError,
        RuntimeIntegrityError,
        sqlite3.Error,
        ValueError,
    ) as error:
        raise ConsumerStartError("consumer runtime could not be rehydrated") from error
    if handle.closed or handle.needs_human or handle.head != head:
        raise ConsumerStartError("consumer runtime is not resumable")
    return FreshConsumer(
        database_path=database,
        checkout_root=checkout,
        prompt=prompt,
        artifacts=artifacts,
        store=store,
        service=service,
        handle=handle,
    )


__all__ = [
    "ConsumerStartError",
    "FreshConsumer",
    "resume_fresh_consumer",
    "start_fresh_consumer",
]
