from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.lineage.reducer import reduce_events
from graphene.lineage.service import (
    EvidenceItem,
    RuntimeAccessDenied,
    RuntimeIdentityError,
    RuntimeIntegrityError,
    RuntimeOperationError,
    RuntimeTerminalError,
    ScopedApplicationService,
    ToolCallIdentity,
)
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    EventInput,
    EvidenceKind,
    EvidenceReference,
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


class ArtifactLedger:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], bytes] = {}

    def __call__(
        self,
        kind: EvidenceKind,
        record: Mapping[str, Any],
    ) -> EvidenceReference:
        raw = canonical_json_bytes(record)
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.records[(kind.value, artifact_id)] = raw
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def bytes_ref(self, kind: EvidenceKind, raw: bytes) -> EvidenceReference:
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.records[(kind.value, artifact_id)] = raw
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def source(self, kind: SourceKind, record: Mapping[str, Any]) -> SourceReference:
        raw = canonical_json_bytes(record)
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.records[(kind.value, artifact_id)] = raw
        return SourceReference(kind=kind, id=artifact_id, sha256=digest)

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        exact = self.records.get((kind, artifact_id))
        if exact is not None:
            return exact
        matches = [
            raw for (_, item_id), raw in self.records.items() if item_id == artifact_id
        ]
        return matches[0] if len(matches) == 1 else None


def seed_run(store: SQLiteLineageStore, ledger: ArtifactLedger, run_id: str) -> None:
    source = ledger.source(
        SourceKind.LIFECYCLE_REQUEST,
        {"schema_version": 2, "run_id": run_id, "action": "start"},
    )
    store.append(
        run_id,
        VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0),
        f"{run_id}_start_key",
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
            source_ref=source,
            payload={"state": "STARTING"},
        ),
    )


def runtime(
    tmp_path: Path,
    *,
    run_id: str = "run_service_001",
):
    checkout = tmp_path / "fixture"
    shutil.copytree(ROOT / GOLDEN.fixture.root, checkout)
    ledger = ArtifactLedger()
    store = SQLiteLineageStore(
        tmp_path / "lineage.sqlite3",
        artifact_resolver=ledger.resolve,
    )
    seed_run(store, ledger, run_id)
    evidence_content = "approved memory evidence"
    evidence_ref = ledger.bytes_ref(
        EvidenceKind.EVIDENCE_BLOB, evidence_content.encode()
    )
    service = ScopedApplicationService(store, ledger)
    read_scope = tuple(
        sorted(set(GOLDEN.fixture.tracked_paths) | set(GOLDEN.fixture.mutable_paths))
    )
    handle = service.create_handle(
        run_id=run_id,
        repo_id="graphene-demo",
        base_sha=BASE_SHA,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
        session_id="session_service_001",
        invocation_id="invocation_service_001",
        model_id="fake-runtime-model",
        read_scope=read_scope,
        write_scope=GOLDEN.fixture.mutable_paths,
        tools=tuple(LineageOperation),
        evidence=(
            EvidenceItem(
                reference=evidence_ref,
                content=evidence_content,
                content_sha256=sha256_hex(evidence_content.encode()),
            ),
        ),
        fixed_test_profile="fixture_pytest",
        fixture_policy=GOLDEN.fixture,
        checkout_root=checkout,
    )
    return service, handle, store, ledger, evidence_ref


def call(handle, number: int, *, adapter_kind: str = "adk") -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=handle.session_id,
        invocation_id=handle.invocation_id,
        model_id=handle.model_id,
        tool_call_id=f"tool_call_{number:03d}",
        agent_name="graphene_agent",
        adapter_kind=adapter_kind,
    )


def test_six_operations_commit_before_return_and_completion_is_terminal(tmp_path: Path):
    service, handle, store, ledger, evidence_ref = runtime(tmp_path)
    invocation = service.ensure_invocation_started(
        handle,
        session_id=handle.session_id,
        invocation_id=handle.invocation_id,
        model_id=handle.model_id,
        adk_version="2.5.0",
    )
    assert (
        service.ensure_invocation_started(
            handle,
            session_id=handle.session_id,
            invocation_id=handle.invocation_id,
            model_id=handle.model_id,
            adk_version="2.5.0",
        )
        == invocation
    )
    with pytest.raises(RuntimeIdentityError, match="identity"):
        service.complete_invocation(
            handle,
            session_id=handle.session_id,
            invocation_id=handle.invocation_id,
            returned_model_id="provider-controlled-value",
        )
    assert handle.head.event_sha256 == invocation.event_sha256

    search = service.search_repo(handle, call(handle, 1), query="MAX_ATTEMPTS")
    assert search.paths == ("app/auth/limiter.py", "tests/test_rate_limit.py")
    assert store.verify(handle.run_id) == handle.head

    read = service.read_file(handle, call(handle, 2), path="app/auth/limiter.py")
    assert "MAX_ATTEMPTS" in read.content
    assert read.artifact_sha256 == next(
        item.sha256
        for item in store.tail(handle.run_id, 0, 256)[-1].references
        if item.kind == EvidenceKind.FILE_VERSION
    )

    opened = service.open_evidence(
        handle,
        call(handle, 3),
        evidence_id=evidence_ref.id,
    )
    assert opened.content == "approved memory evidence"

    write = service.write_file(
        handle,
        call(handle, 4),
        path="app/auth/limiter.py",
        content=read.content + "\n# service lineage test\n",
    )
    assert write.state == "EDITED"
    assert handle.changed_paths == ("app/auth/limiter.py",)

    tested = service.run_fixed_test(handle, call(handle, 5))
    assert tested.passed is True
    assert tested.bound_paths == handle.changed_paths

    denied = service.request_completion(handle, call(handle, 6))
    assert denied.state == "NEEDS_HUMAN"
    assert handle.needs_human is True
    final_count = handle.head.event_count
    with pytest.raises(RuntimeTerminalError, match="terminal"):
        service.read_file(handle, call(handle, 7), path="app/auth/limiter.py")
    assert store.verify(handle.run_id).event_count == final_count

    events = store.tail(handle.run_id, 0, 256)
    assert [event.event_type for event in events] == [
        LineageEventType.RUN_STARTED,
        LineageEventType.INVOCATION_STARTED,
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_COMPLETED,
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_COMPLETED,
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_COMPLETED,
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_COMPLETED,
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_COMPLETED,
        LineageEventType.COMPLETION_ATTEMPTED,
        LineageEventType.COMPLETION_DENIED,
    ]
    write_event = events[9]
    assert write_event.payload["baseline_bytes"] == read.byte_count
    assert write_event.payload["baseline_lines"] == read.line_count
    assert events[11].payload["bound_paths"] == ["app/auth/limiter.py"]
    assert (
        json.dumps([event.model_dump(mode="json") for event in events]).find(
            "service lineage test"
        )
        == -1
    )
    artifact_refs = (
        item
        for event in events
        for item in (*event.references, event.source_ref)
        if item.kind != EvidenceKind.EVENT
    )
    assert all(ledger.resolve(item.kind.value, item.id) for item in artifact_refs)
    projection = reduce_events(events)
    assert projection.state == "NEEDS_HUMAN"
    limiter = next(
        item for item in projection.files if item.path == "app/auth/limiter.py"
    )
    assert limiter.bound_test_pass is True


def test_scope_denial_is_the_only_event_and_does_not_disclose_requested_path(
    tmp_path: Path,
):
    service, handle, store, ledger, _ = runtime(tmp_path)
    before = handle.head.seq
    requested = "private/secret-token.txt"
    with pytest.raises(RuntimeAccessDenied):
        service.read_file(handle, call(handle, 1), path=requested)

    events = store.tail(handle.run_id, before, 256)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == LineageEventType.SCOPE_DENIED
    assert event.references == ()
    assert requested not in json.dumps(event.model_dump(mode="json"))
    receipt = ledger.resolve(event.source_ref.kind.value, event.source_ref.id)
    assert receipt is not None and requested.encode() not in receipt


def test_absent_read_allows_only_atomic_first_write(tmp_path: Path):
    service, handle, store, _, _ = runtime(tmp_path)
    path = "tests/test_security_policy.py"

    observed = service.read_file(handle, call(handle, 1), path=path)
    assert observed.state == "ABSENT"
    assert observed.content == ""
    written = service.write_file(
        handle,
        call(handle, 2),
        path=path,
        content="def test_policy():\n    assert True\n",
    )

    assert written.state == "NEW"
    assert (handle.checkout_root / path).is_file()
    read_event = next(
        event
        for event in store.tail(handle.run_id, 0, 256)
        if event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == "read_file"
    )
    assert read_event.payload["state"] == "ABSENT"
    assert tuple(reference.kind for reference in read_event.references) == (
        EvidenceKind.EVIDENCE_BLOB,
    )


def test_absent_read_race_cannot_overwrite_appearing_file(tmp_path: Path):
    service, handle, store, _, _ = runtime(tmp_path)
    path = "tests/test_security_policy.py"
    service.read_file(handle, call(handle, 1), path=path)
    target = handle.checkout_root / path
    target.write_text("DO_NOT_OVERWRITE\n")

    with pytest.raises(RuntimeAccessDenied):
        service.write_file(
            handle,
            call(handle, 2),
            path=path,
            content="replacement\n",
        )

    assert target.read_text() == "DO_NOT_OVERWRITE\n"
    assert store.tail(handle.run_id, 0, 256)[-1].payload["reason_code"] == (
        "stale_file_version"
    )


def test_operation_error_commits_exactly_one_failed_terminal_event(tmp_path: Path):
    service, handle, store, _, _ = runtime(tmp_path)
    before = handle.head.seq
    with pytest.raises(RuntimeOperationError, match="search_repo failed"):
        service.search_repo(handle, call(handle, 1), query="")
    assert [event.event_type for event in store.tail(handle.run_id, before, 256)] == [
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_FAILED,
    ]


def test_post_write_persistence_failure_interrupts_and_quarantines_checkout(
    tmp_path: Path,
):
    service, handle, store, _, _ = runtime(tmp_path)
    read = service.read_file(handle, call(handle, 1), path="app/auth/limiter.py")
    record = service.record_artifact

    def fail_completion(kind, payload):
        if (
            kind == EvidenceKind.TOOL_RECEIPT
            and payload.get("phase") == "tool.completed"
        ):
            raise OSError("simulated receipt outage")
        return record(kind, payload)

    service.record_artifact = fail_completion
    with pytest.raises(RuntimeIntegrityError, match="run interrupted"):
        service.write_file(
            handle,
            call(handle, 2),
            path="app/auth/limiter.py",
            content=read.content + "\n# uncertain mutation\n",
        )

    assert handle.closed is True
    assert not handle.checkout_root.exists()
    quarantines = tuple(tmp_path.glob(".graphene-interrupted-*"))
    assert len(quarantines) == 1
    assert "uncertain mutation" in (quarantines[0] / "app/auth/limiter.py").read_text()
    events = store.tail(handle.run_id, 0, 256)
    assert events[-2].event_type == LineageEventType.TOOL_STARTED
    assert events[-1].event_type == LineageEventType.RUN_INTERRUPTED
    assert reduce_events(events).state == "INTERRUPTED"
    with pytest.raises(RuntimeTerminalError, match="terminal"):
        service.read_file(handle, call(handle, 3), path="app/auth/limiter.py")


def test_ambiguous_write_error_also_interrupts_and_quarantines_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    service, handle, store, _, _ = runtime(tmp_path)
    read = service.read_file(handle, call(handle, 1), path="app/auth/limiter.py")
    replace = __import__("graphene.execution.adapter", fromlist=["os"]).os.replace

    def replace_then_fail(*args, **kwargs):
        replace(*args, **kwargs)
        raise OSError("simulated post-replace durability failure")

    monkeypatch.setattr("graphene.execution.adapter.os.replace", replace_then_fail)
    with pytest.raises(RuntimeIntegrityError, match="run interrupted"):
        service.write_file(
            handle,
            call(handle, 2),
            path="app/auth/limiter.py",
            content=read.content + "\n# ambiguous mutation\n",
        )

    assert handle.closed is True
    assert not handle.checkout_root.exists()
    assert store.tail(handle.run_id, 0, 256)[-1].event_type == (
        LineageEventType.RUN_INTERRUPTED
    )


def test_absent_operation_is_denied_before_tool_started(tmp_path: Path):
    service, original, store, _, _ = runtime(tmp_path)
    handle = type(original)(
        run_id=original.run_id,
        repo_id=original.repo_id,
        base_sha=original.base_sha,
        agent_profile_id=original.agent_profile_id,
        policy_revision=original.policy_revision,
        session_id=original.session_id,
        invocation_id=original.invocation_id,
        model_id=original.model_id,
        read_scope=original.read_scope,
        write_scope=original.write_scope,
        tools=(LineageOperation.REQUEST_COMPLETION,),
        evidence=original.evidence,
        fixed_test_profile=original.fixed_test_profile,
        fixture_policy=original.fixture_policy,
        checkout_root=original.checkout_root,
        initial_head=original.head,
    )
    before = handle.head.seq
    with pytest.raises(RuntimeAccessDenied):
        service.read_file(handle, call(handle, 1), path="app/auth/limiter.py")
    events = store.tail(handle.run_id, before, 256)
    assert [event.event_type for event in events] == [LineageEventType.SCOPE_DENIED]
