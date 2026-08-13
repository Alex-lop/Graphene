from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from graphene.hashing import sha256_hex
from graphene.lineage import (
    EvidenceInvalid,
    LineageConflict,
    SQLiteArtifactStore,
    SQLiteLineageStore,
)
from graphene.lineage.recovery import (
    RecoveryCheckoutError,
    RecoveryEvidenceError,
    RecoveryTerminalError,
    recover_interrupted_run,
)
from graphene.lineage.reducer import reduce_events
from graphene.models import (
    Event,
    EventInput,
    EvidenceKind,
    EvidenceReference,
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

BASE_SHA = "a" * 40


class _Run:
    def __init__(self, tmp_path: Path, run_id: str) -> None:
        self.run_id = run_id
        self.path = tmp_path / "lineage.sqlite3"
        self.artifacts = SQLiteArtifactStore(self.path)
        self.store = SQLiteLineageStore(
            self.path,
            artifact_resolver=self.artifacts.resolve,
        )
        self.checkout = tmp_path / "checkout"
        self.checkout.mkdir()
        (self.checkout / "candidate.txt").write_text("recoverable candidate")
        self._number = 0
        self.append(LineageEventType.RUN_STARTED, {"state": "STARTING"})

    def source(self, record) -> SourceReference:
        reference = self.artifacts(EvidenceKind.OPERATOR_REQUEST, record)
        return SourceReference(
            kind=SourceKind.LIFECYCLE_REQUEST,
            id=reference.id,
            sha256=reference.sha256,
        )

    def draft(
        self,
        event_type: LineageEventType,
        payload: dict[str, object],
        *,
        tool_call_id: str | None = None,
        invocation_id: str | None = None,
        references: tuple[EvidenceReference, ...] = (),
    ) -> EventInput:
        if event_type in {
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_FAILED,
        }:
            truth = TruthKind.RUNTIME_OBSERVED
            authority = LineageAuthority.SCOPED_TOOL_WRAPPER
            artifact_kind = EvidenceKind.TOOL_RECEIPT
            source_kind = SourceKind.TOOL_RECEIPT
        elif event_type in {
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
        }:
            truth = TruthKind.RUNTIME_OBSERVED
            authority = LineageAuthority.ADK_ADAPTER
            artifact_kind = EvidenceKind.ADK_EVENT_RECEIPT
            source_kind = SourceKind.ADK_EVENT_RECEIPT
        elif event_type == LineageEventType.COMPLETION_ATTEMPTED:
            truth = TruthKind.MODEL_PROPOSED
            authority = LineageAuthority.ADK_ADAPTER
            artifact_kind = EvidenceKind.ADK_EVENT_RECEIPT
            source_kind = SourceKind.ADK_EVENT_RECEIPT
        elif event_type == LineageEventType.COMPLETION_DENIED:
            truth = TruthKind.POLICY_AUTHORITATIVE
            authority = LineageAuthority.POLICY_ENGINE
            artifact_kind = EvidenceKind.POLICY_RECEIPT
            source_kind = SourceKind.POLICY_EVALUATION
        else:
            truth = TruthKind.SERVER_DERIVED
            authority = LineageAuthority.LIFECYCLE_SERVICE
            artifact_kind = EvidenceKind.OPERATOR_REQUEST
            source_kind = SourceKind.LIFECYCLE_REQUEST
        source_record = {
            "schema_version": 2,
            "run_id": self.run_id,
            "event_type": event_type.value,
            "ordinal": self._number + 1,
        }
        source_artifact = self.artifacts(artifact_kind, source_record)
        invocation_event = event_type in {
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
            LineageEventType.COMPLETION_ATTEMPTED,
            LineageEventType.COMPLETION_DENIED,
        }
        return EventInput(
            session_id="session_recovery_001" if invocation_event else None,
            invocation_id=invocation_id if invocation_event else None,
            model_id="recovery-test-model" if invocation_event else None,
            tool_call_id=tool_call_id,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=event_type,
            truth_kind=truth,
            authority=authority,
            references=references,
            source_ref=SourceReference(
                kind=source_kind,
                id=source_artifact.id,
                sha256=source_artifact.sha256,
            ),
            payload=payload,
        )

    def append(
        self,
        event_type: LineageEventType,
        payload: dict[str, object],
        **identity,
    ) -> Event:
        self._number += 1
        head = self.store.verify(self.run_id)
        assert isinstance(head, VerifiedHead)
        return self.store.append(
            self.run_id,
            head,
            f"fixture_event_key_{self._number:04d}",
            self.draft(event_type, payload, **identity),
        )

    def events(self) -> tuple[Event, ...]:
        return self.store.tail(self.run_id, 0, 256)


def _tool_started(run: _Run, call_id: str = "tool_call_recovery_001") -> Event:
    return run.append(
        LineageEventType.TOOL_STARTED,
        {"operation": "search_repo", "status": "started"},
        tool_call_id=call_id,
    )


def _tool_completed(run: _Run, call_id: str = "tool_call_recovery_001") -> Event:
    return run.append(
        LineageEventType.TOOL_COMPLETED,
        {
            "operation": "search_repo",
            "status": "completed",
            "paths": [],
        },
        tool_call_id=call_id,
    )


def test_unmatched_starts_persist_one_interrupt_then_quarantine_checkout(tmp_path: Path):
    run = _Run(tmp_path, "run_recovery_001")
    invocation = run.append(
        LineageEventType.INVOCATION_STARTED,
        {"status": "started"},
        invocation_id="invocation_recovery_001",
    )
    tool = _tool_started(run)

    interrupted = recover_interrupted_run(
        run.store,
        run_id=run.run_id,
        checkout_path=run.checkout,
        record_source=run.source,
    )

    assert interrupted is not None
    assert interrupted.event_type == LineageEventType.RUN_INTERRUPTED
    assert interrupted.payload == {
        "status": "INTERRUPTED",
        "state": "INTERRUPTED",
        "reason_code": "uncertain_dispatch",
        "recovery_kind": "uncertain_dispatch",
        "checkout_binding_sha256": sha256_hex(str(run.checkout.resolve()).encode()),
        "unmatched_tool_starts": 1,
        "unmatched_invocations": 1,
    }
    assert [(item.id, item.sha256) for item in interrupted.references] == [
        (invocation.event_id, invocation.event_sha256),
        (tool.event_id, tool.event_sha256),
    ]
    assert not run.checkout.exists()
    quarantine = tuple(tmp_path.glob(".graphene-interrupted-*"))
    assert len(quarantine) == 1
    assert (quarantine[0] / "candidate.txt").read_text() == "recoverable candidate"
    assert reduce_events(run.events()).state == LineageRunState.INTERRUPTED
    assert run.artifacts.resolve(
        interrupted.source_ref.kind.value,
        interrupted.source_ref.id,
    ) is not None

    before = run.events()
    assert recover_interrupted_run(
        run.store,
        run_id=run.run_id,
        checkout_path=run.checkout,
        record_source=run.source,
    ) == interrupted
    assert run.events() == before

    other_checkout = tmp_path / "other-checkout"
    other_checkout.mkdir()
    with pytest.raises(RecoveryTerminalError, match="terminal"):
        recover_interrupted_run(
            run.store,
            run_id=run.run_id,
            checkout_path=other_checkout,
            record_source=run.source,
        )
    assert other_checkout.is_dir()

    with pytest.raises(LineageConflict, match="interrupted"):
        _tool_completed(run)
    assert reduce_events(run.events()).state == LineageRunState.INTERRUPTED


@pytest.mark.parametrize("with_invocation", [False, True])
def test_matched_tool_pair_without_invocation_uncertainty_is_a_noop(
    tmp_path: Path,
    with_invocation: bool,
):
    run = _Run(tmp_path, f"run_matched_{int(with_invocation)}")
    if with_invocation:
        run.append(
            LineageEventType.INVOCATION_STARTED,
            {"status": "started"},
            invocation_id="invocation_matched_001",
        )
    _tool_started(run)
    _tool_completed(run)
    if with_invocation:
        run.append(
            LineageEventType.INVOCATION_COMPLETED,
            {"status": "completed"},
            invocation_id="invocation_matched_001",
        )
    before = run.events()

    assert recover_interrupted_run(
        run.store,
        run_id=run.run_id,
        checkout_path=run.checkout,
        record_source=run.source,
    ) is None
    assert run.events() == before
    assert run.checkout.is_dir()


def test_matched_tool_does_not_hide_an_open_invocation(tmp_path: Path):
    run = _Run(tmp_path, "run_open_invocation_001")
    invocation = run.append(
        LineageEventType.INVOCATION_STARTED,
        {"status": "started"},
        invocation_id="invocation_open_001",
    )
    _tool_started(run)
    _tool_completed(run)

    interrupted = recover_interrupted_run(
        run.store,
        run_id=run.run_id,
        checkout_path=run.checkout,
        record_source=run.source,
    )

    assert interrupted is not None
    assert [item.id for item in interrupted.references] == [invocation.event_id]
    assert interrupted.payload["unmatched_tool_starts"] == 0
    assert interrupted.payload["unmatched_invocations"] == 1


def test_completion_denial_explicitly_closes_invocation_uncertainty(tmp_path: Path):
    run = _Run(tmp_path, "run_completion_denied_001")
    run.append(
        LineageEventType.INVOCATION_STARTED,
        {"status": "started"},
        invocation_id="invocation_denied_001",
    )
    attempted = run.append(
        LineageEventType.COMPLETION_ATTEMPTED,
        {"operation": "request_completion", "status": "attempted"},
        invocation_id="invocation_denied_001",
        tool_call_id="completion_call_001",
    )
    run.append(
        LineageEventType.COMPLETION_DENIED,
        {
            "operation": "request_completion",
            "status": "denied",
            "state": "NEEDS_HUMAN",
        },
        invocation_id="invocation_denied_001",
        tool_call_id="completion_call_001",
        references=(
            EvidenceReference(
                kind=EvidenceKind.EVENT,
                id=attempted.event_id,
                sha256=attempted.event_sha256,
            ),
        ),
    )
    before = run.events()

    assert recover_interrupted_run(
        run.store,
        run_id=run.run_id,
        checkout_path=run.checkout,
        record_source=run.source,
    ) is None
    assert run.events() == before
    assert run.checkout.exists()


def test_stale_cas_conflict_never_discards_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    run = _Run(tmp_path, "run_recovery_race_001")
    _tool_started(run)
    concurrent = run.draft(
        LineageEventType.TOOL_STARTED,
        {"operation": "read_file", "status": "started"},
        tool_call_id="tool_call_concurrent_001",
    )
    append = run.store.append

    def race(run_id, expected_head, idempotency_key, draft):
        if draft.event_type == LineageEventType.RUN_INTERRUPTED:
            append(run_id, expected_head, "concurrent_event_key_001", concurrent)
        return append(run_id, expected_head, idempotency_key, draft)

    monkeypatch.setattr(run.store, "append", race)
    with pytest.raises(LineageConflict, match="committed head"):
        recover_interrupted_run(
            run.store,
            run_id=run.run_id,
            checkout_path=run.checkout,
            record_source=run.source,
        )

    assert run.checkout.is_dir()
    assert all(
        event.event_type != LineageEventType.RUN_INTERRUPTED for event in run.events()
    )


def test_malformed_append_and_evidence_invalid_stream_fail_closed(tmp_path: Path):
    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    malformed = _Run(malformed_root, "run_malformed_001")
    with pytest.raises(EvidenceInvalid, match="semantically invalid"):
        _tool_completed(malformed)
    assert malformed.checkout.exists()

    denial_root = tmp_path / "unpaired-denial"
    denial_root.mkdir()
    unpaired = _Run(denial_root, "run_unpaired_denial_001")
    unpaired.append(
        LineageEventType.INVOCATION_STARTED,
        {"status": "started"},
        invocation_id="invocation_unpaired_001",
    )
    with pytest.raises(EvidenceInvalid, match="one attempt"):
        unpaired.append(
            LineageEventType.COMPLETION_DENIED,
            {
                "operation": "request_completion",
                "status": "denied",
                "state": "NEEDS_HUMAN",
            },
            invocation_id="invocation_unpaired_001",
            tool_call_id="completion_unpaired_001",
        )
    assert unpaired.checkout.exists()

    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    invalid = _Run(invalid_root, "run_invalid_001")
    _tool_started(invalid)
    with sqlite3.connect(invalid.path) as connection:
        connection.execute(
            "UPDATE events SET request_sha256 = ? WHERE run_id = ? AND seq = 2",
            ("0" * 64, invalid.run_id),
        )
    with pytest.raises(RecoveryEvidenceError, match="evidence is invalid"):
        recover_interrupted_run(
            invalid.store,
            run_id=invalid.run_id,
            checkout_path=invalid.checkout,
            record_source=invalid.source,
        )
    assert invalid.checkout.exists()


def test_other_terminal_runs_and_broad_paths_fail_without_deletion(tmp_path: Path):
    run = _Run(tmp_path, "run_terminal_001")
    _tool_started(run)
    run.append(LineageEventType.RUN_FAILED, {"status": "FAILED"})
    before = run.events()
    with pytest.raises(RecoveryTerminalError, match="terminal"):
        recover_interrupted_run(
            run.store,
            run_id=run.run_id,
            checkout_path=run.checkout,
            record_source=run.source,
        )
    assert run.events() == before
    assert run.checkout.exists()

    for unsafe in (Path("relative-checkout"), Path("/"), Path.cwd()):
        with pytest.raises(RecoveryCheckoutError):
            recover_interrupted_run(
                run.store,
                run_id=run.run_id,
                checkout_path=unsafe,
                record_source=run.source,
            )
    symlink = tmp_path / "checkout-link"
    symlink.symlink_to(run.checkout, target_is_directory=True)
    with pytest.raises(RecoveryCheckoutError, match="symlink"):
        recover_interrupted_run(
            run.store,
            run_id=run.run_id,
            checkout_path=symlink,
            record_source=run.source,
        )
    assert Path.cwd().exists()
    assert run.checkout.exists()
    assert "recoverable candidate" in json.dumps(
        {"checkout": (run.checkout / "candidate.txt").read_text()}
    )
