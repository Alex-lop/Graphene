from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from google.api_core.exceptions import Aborted, AlreadyExists, Conflict
from google.cloud import firestore

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..core_models import (
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceReference,
    HeadCheckpoint,
    LineageEventType,
    SourceReference,
    VerifiedHead,
)
from .sqlite_lineage_store import _NO_APPEND_AFTER, EvidenceInvalid, LineageConflict

ArtifactResolver = Callable[[str, str], bytes | None]
CheckpointReader = Callable[[str], Iterable[HeadCheckpoint]]

_RUNS = "graphene_lineage_runs"
_GLOBAL_EVENTS = "graphene_lineage_event_ids"
_EVENTS = "events"
_IDEMPOTENCY = "idempotency"
_EVENT_INPUT_FIELDS = set(EventInput.model_fields)
_HEAD_FIELDS = {
    "schema_version",
    "run_id",
    "seq",
    "event_sha256",
    "event_count",
    "repo_id",
    "base_sha",
    "agent_profile_id",
    "policy_revision",
}
_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "run_id",
    "seq",
    "idempotency_sha256",
    "payload_sha256",
    "previous_event_sha256",
    "event_sha256",
    "event_bytes",
}
_IDEMPOTENCY_FIELDS = {
    "schema_version",
    "run_id",
    "idempotency_sha256",
    "request_sha256",
    "event_id",
    "event_seq",
    "event_sha256",
}
_GLOBAL_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "run_id",
    "event_seq",
    "event_sha256",
}


def _new_event_id() -> str:
    return f"event_{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)


def _invalid(run_id: str, reason: str, seq: int | None = None) -> EvidenceInvalidState:
    return EvidenceInvalidState(run_id=run_id, first_invalid_seq=seq, reason=reason)


def _sequence_id(seq: int) -> str:
    return f"{seq:020d}"


def _idempotency_sha256(key: str) -> str:
    return sha256_hex(key.encode())


def _snapshot_data(snapshot: Any) -> object:
    return snapshot.to_dict() if snapshot.exists else None


def _canonical_object(raw: object) -> dict[str, object]:
    if not isinstance(raw, bytes):
        raise TypeError("stored event is not bytes")
    value = json.loads(raw)
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise ValueError("stored event bytes are not canonical JSON")
    return value


def _request_sha256(
    run_id: str,
    expected_head: VerifiedHead,
    idempotency_key: str,
    draft: EventInput,
) -> str:
    return canonical_json_sha256(
        {
            "draft": draft.model_dump(mode="json"),
            "expected_head": expected_head.model_dump(mode="json"),
            "idempotency_key": idempotency_key,
            "run_id": run_id,
        }
    )


def _event(
    run_id: str,
    head: VerifiedHead,
    idempotency_key: str,
    draft: EventInput,
    *,
    event_id: str,
    recorded_at: datetime,
) -> Event:
    fields = {
        **{name: getattr(draft, name) for name in _EVENT_INPUT_FIELDS},
        "schema_version": 2,
        "event_id": event_id,
        "run_id": run_id,
        "seq": head.seq + 1,
        "server_recorded_at": recorded_at,
        "idempotency_key": idempotency_key,
        "payload_sha256": canonical_json_sha256(draft.payload),
        "previous_event_sha256": head.event_sha256,
    }
    canonical = Event.model_construct(
        **fields,
        event_sha256="0" * 64,
    ).model_dump(mode="json", exclude={"event_sha256"})
    return Event.model_validate(
        {**canonical, "event_sha256": canonical_json_sha256(canonical)}
    )


class FirestoreLineageStore:
    """Firestore adapter for the frozen append/tail/verify lineage surface."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        artifact_resolver: ArtifactResolver,
        checkpoint_reader: CheckpointReader | None = None,
    ) -> None:
        self._client = client or firestore.Client()
        self._artifact_resolver = artifact_resolver
        self._checkpoint_reader = checkpoint_reader or (lambda _run_id: ())
        self._runs = self._client.collection(_RUNS)
        self._global_events = self._client.collection(_GLOBAL_EVENTS)

    def _run(self, run_id: str):
        return self._runs.document(run_id)

    def _artifact(self, kind: str, artifact_id: str) -> bytes | None:
        try:
            value = self._artifact_resolver(kind, artifact_id)
        except Exception:  # noqa: BLE001 - resolver failure is invalid evidence
            return None
        return value if isinstance(value, bytes) else None

    def _reference_resolves(
        self,
        reference: EvidenceReference | SourceReference,
        events: tuple[Event, ...],
    ) -> bool:
        if reference.kind.value == "event":
            return any(
                item.event_id == reference.id and item.event_sha256 == reference.sha256
                for item in events
            )
        artifact = self._artifact(reference.kind.value, reference.id)
        return artifact is not None and sha256_hex(artifact) == reference.sha256

    def _read_documents(
        self,
        transaction: Any,
        run_id: str,
        *,
        candidate_event_id: str | None = None,
        idempotency_sha256: str | None = None,
    ) -> tuple[
        VerifiedHead | EvidenceInvalidState,
        tuple[Event, ...],
        Any | None,
        Any | None,
        Any | None,
    ]:
        run = self._run(run_id)
        event_collection = run.collection(_EVENTS)
        idempotency_collection = run.collection(_IDEMPOTENCY)

        # ponytail: full per-run scans preserve the frozen MVP semantics; add
        # verified-prefix checkpoints before raising the bounded run-size ceiling.
        head_snapshot = run.get(transaction=transaction)
        event_snapshots = tuple(event_collection.stream(transaction=transaction))
        idempotency_snapshots = tuple(
            idempotency_collection.stream(transaction=transaction)
        )

        global_snapshots: dict[str, Any] = {}
        for snapshot in event_snapshots:
            data = _snapshot_data(snapshot)
            event_id = data.get("event_id") if isinstance(data, dict) else None
            if isinstance(event_id, str) and event_id not in global_snapshots:
                global_snapshots[event_id] = self._global_events.document(event_id).get(
                    transaction=transaction
                )

        head_data = _snapshot_data(head_snapshot)
        head_seq = head_data.get("seq") if isinstance(head_data, dict) else 0
        next_seq = head_seq + 1 if type(head_seq) is int and head_seq >= 0 else 1
        candidate_event_snapshot = (
            event_collection.document(_sequence_id(next_seq)).get(
                transaction=transaction
            )
            if candidate_event_id is not None
            else None
        )
        idempotency_snapshot = (
            idempotency_collection.document(idempotency_sha256).get(
                transaction=transaction
            )
            if idempotency_sha256 is not None
            else None
        )
        candidate_global_snapshot = (
            self._global_events.document(candidate_event_id).get(
                transaction=transaction
            )
            if candidate_event_id is not None
            else None
        )

        state, events = self._verify_documents(
            run_id,
            head_snapshot,
            event_snapshots,
            idempotency_snapshots,
            global_snapshots,
        )
        return (
            state,
            events,
            idempotency_snapshot,
            candidate_event_snapshot,
            candidate_global_snapshot,
        )

    def _verify_documents(
        self,
        run_id: str,
        head_snapshot: Any,
        event_snapshots: tuple[Any, ...],
        idempotency_snapshots: tuple[Any, ...],
        global_snapshots: dict[str, Any],
    ) -> tuple[VerifiedHead | EvidenceInvalidState, tuple[Event, ...]]:
        head_data = _snapshot_data(head_snapshot)
        if head_data is None:
            if event_snapshots or idempotency_snapshots:
                return _invalid(run_id, "indexes exist without a run head"), ()
            return VerifiedHead(
                run_id=run_id,
                seq=0,
                event_sha256=None,
                event_count=0,
            ), ()
        if not isinstance(head_data, dict) or set(head_data) != _HEAD_FIELDS:
            return _invalid(run_id, "run head metadata is malformed"), ()
        if not event_snapshots:
            return _invalid(run_id, "run head exists without events"), ()

        idempotency_by_id: dict[str, dict[str, object]] = {}
        for snapshot in idempotency_snapshots:
            data = _snapshot_data(snapshot)
            if (
                not isinstance(data, dict)
                or set(data) != _IDEMPOTENCY_FIELDS
                or snapshot.id in idempotency_by_id
            ):
                return _invalid(run_id, "idempotency index is malformed"), ()
            idempotency_by_id[snapshot.id] = data

        events: list[Event] = []
        previous_sha256: str | None = None
        identity: tuple[object, ...] | None = None
        event_ids: set[str] = set()
        ordered = sorted(event_snapshots, key=lambda item: item.id)
        for expected_seq, snapshot in enumerate(ordered, 1):
            data = _snapshot_data(snapshot)
            if (
                snapshot.id != _sequence_id(expected_seq)
                or not isinstance(data, dict)
                or set(data) != _EVENT_FIELDS
            ):
                return _invalid(
                    run_id,
                    "event sequence or document metadata is malformed",
                    expected_seq,
                ), ()
            try:
                value = _canonical_object(data["event_bytes"])
                event = Event.model_validate(value)
                event_bytes = canonical_json_bytes(event.model_dump(mode="json"))
            except (KeyError, TypeError, ValueError, UnicodeError):
                return _invalid(
                    run_id, "stored event bytes are malformed", expected_seq
                ), ()

            idempotency_digest = _idempotency_sha256(event.idempotency_key)
            expected_event_data = {
                "schema_version": 2,
                "event_id": event.event_id,
                "run_id": event.run_id,
                "seq": event.seq,
                "idempotency_sha256": idempotency_digest,
                "payload_sha256": event.payload_sha256,
                "previous_event_sha256": event.previous_event_sha256,
                "event_sha256": event.event_sha256,
                "event_bytes": event_bytes,
            }
            if (
                data != expected_event_data
                or event.run_id != run_id
                or event.seq != expected_seq
            ):
                return _invalid(
                    run_id,
                    "event document does not match its canonical bytes",
                    expected_seq,
                ), ()
            if event.previous_event_sha256 != previous_sha256:
                return _invalid(
                    run_id, "event digest chain is broken", expected_seq
                ), ()
            if expected_seq == 1 and event.event_type != LineageEventType.RUN_STARTED:
                return _invalid(
                    run_id, "first event is not run.started", expected_seq
                ), ()
            current_identity = (
                event.repo_id,
                event.base_sha,
                event.agent_profile_id,
                event.policy_revision,
            )
            identity = identity or current_identity
            if current_identity != identity:
                return _invalid(
                    run_id,
                    "run identity changed within the event stream",
                    expected_seq,
                ), ()
            if event.event_id in event_ids:
                return _invalid(run_id, "event ID is duplicated", expected_seq), ()
            for reference in (*event.references, event.source_ref):
                if not self._reference_resolves(reference, tuple(events)):
                    return _invalid(
                        run_id, "event reference is unresolved", expected_seq
                    ), ()

            prior_head = VerifiedHead(
                run_id=run_id,
                seq=expected_seq - 1,
                event_sha256=previous_sha256,
                event_count=expected_seq - 1,
            )
            draft = EventInput.model_validate(
                event.model_dump(mode="json", include=_EVENT_INPUT_FIELDS)
            )
            expected_idempotency = {
                "schema_version": 2,
                "run_id": run_id,
                "idempotency_sha256": idempotency_digest,
                "request_sha256": _request_sha256(
                    run_id,
                    prior_head,
                    event.idempotency_key,
                    draft,
                ),
                "event_id": event.event_id,
                "event_seq": event.seq,
                "event_sha256": event.event_sha256,
            }
            if idempotency_by_id.get(idempotency_digest) != expected_idempotency:
                return _invalid(
                    run_id,
                    "idempotency index is not reciprocal",
                    expected_seq,
                ), ()

            global_snapshot = global_snapshots.get(event.event_id)
            global_data = (
                None if global_snapshot is None else _snapshot_data(global_snapshot)
            )
            expected_global = {
                "schema_version": 2,
                "event_id": event.event_id,
                "run_id": run_id,
                "event_seq": event.seq,
                "event_sha256": event.event_sha256,
            }
            if (
                global_snapshot is None
                or global_snapshot.id != event.event_id
                or global_data != expected_global
                or not isinstance(global_data, dict)
                or set(global_data) != _GLOBAL_EVENT_FIELDS
            ):
                return _invalid(
                    run_id,
                    "global event index is not reciprocal",
                    expected_seq,
                ), ()

            events.append(event)
            event_ids.add(event.event_id)
            previous_sha256 = event.event_sha256

        if len(idempotency_by_id) != len(events):
            return _invalid(run_id, "idempotency index count does not match events"), ()
        verified = VerifiedHead(
            run_id=run_id,
            seq=len(events),
            event_sha256=previous_sha256,
            event_count=len(events),
        )
        expected_head = {
            "schema_version": 2,
            "run_id": run_id,
            "seq": verified.seq,
            "event_sha256": verified.event_sha256,
            "event_count": verified.event_count,
            "repo_id": identity[0] if identity else None,
            "base_sha": identity[1] if identity else None,
            "agent_profile_id": identity[2] if identity else None,
            "policy_revision": identity[3] if identity else None,
        }
        if head_data != expected_head:
            return _invalid(
                run_id, "stored run head does not match the event stream"
            ), ()

        by_seq = {event.seq: event for event in events}
        try:
            checkpoints = tuple(self._checkpoint_reader(run_id))
        except Exception:  # noqa: BLE001 - reader failure is invalid evidence
            return _invalid(run_id, "checkpoint reader failed"), ()
        for raw_checkpoint in checkpoints:
            try:
                checkpoint = HeadCheckpoint.model_validate(raw_checkpoint)
            except (TypeError, ValueError):
                return _invalid(run_id, "checkpoint is malformed"), ()
            artifact = self._artifact(
                checkpoint.bound_artifact_kind.value,
                checkpoint.bound_artifact_id,
            )
            if (
                checkpoint.run_id != run_id
                or checkpoint.expected_seq not in by_seq
                or by_seq[checkpoint.expected_seq].event_sha256
                != checkpoint.event_head_sha256
                or artifact is None
                or sha256_hex(artifact) != checkpoint.bound_artifact_sha256
            ):
                return _invalid(run_id, "checkpointed prefix is unresolved"), ()
        try:
            from .lineage_reducer import (
                ProjectionError,
                reduce_events,
                validate_semantic_artifacts,
            )

            validate_semantic_artifacts(tuple(events), self._artifact)
            reduce_events(tuple(events))
        except ProjectionError as error:
            return _invalid(
                run_id,
                f"event stream is semantically invalid: {error}",
                error.first_invalid_seq,
            ), ()
        return verified, tuple(events)

    def _read_verified(
        self,
        run_id: str,
    ) -> tuple[VerifiedHead | EvidenceInvalidState, tuple[Event, ...]]:
        @firestore.transactional
        def read(transaction):
            state, events, _, _, _ = self._read_documents(transaction, run_id)
            return state, events

        return read(self._client.transaction(read_only=True))

    def append(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        idempotency_key: str,
        draft: EventInput,
    ) -> Event:
        if not isinstance(expected_head, VerifiedHead) or not isinstance(
            draft, EventInput
        ):
            raise TypeError(
                "append requires validated EventInput and VerifiedHead values"
            )
        if expected_head.run_id != run_id:
            raise LineageConflict("expected head belongs to a different run")
        if not isinstance(idempotency_key, str):
            raise TypeError("idempotency_key must be a string")

        request_digest = _request_sha256(
            run_id,
            expected_head,
            idempotency_key,
            draft,
        )
        idempotency_digest = _idempotency_sha256(idempotency_key)
        event_id = _new_event_id()
        recorded_at = _now()

        @firestore.transactional
        def apply(transaction):
            state, events, idempotency_snapshot, event_snapshot, global_snapshot = (
                self._read_documents(
                    transaction,
                    run_id,
                    candidate_event_id=event_id,
                    idempotency_sha256=idempotency_digest,
                )
            )
            if isinstance(state, EvidenceInvalidState):
                raise EvidenceInvalid(state)
            assert idempotency_snapshot is not None
            existing_index = _snapshot_data(idempotency_snapshot)
            if existing_index is not None:
                existing = next(
                    (
                        event
                        for event in events
                        if _idempotency_sha256(event.idempotency_key)
                        == idempotency_digest
                    ),
                    None,
                )
                if existing is None:
                    raise EvidenceInvalid(
                        _invalid(run_id, "idempotency index is not reciprocal")
                    )
                exact_index = {
                    "schema_version": 2,
                    "run_id": run_id,
                    "idempotency_sha256": idempotency_digest,
                    "request_sha256": request_digest,
                    "event_id": existing.event_id,
                    "event_seq": existing.seq,
                    "event_sha256": existing.event_sha256,
                }
                if existing_index != exact_index:
                    raise LineageConflict(
                        "idempotency key was reused for another request"
                    )
                return existing
            if state != expected_head:
                raise LineageConflict("expected head does not match the committed head")
            if events and events[-1].event_type in _NO_APPEND_AFTER:
                raise LineageConflict("interrupted runs cannot accept later events")
            for reference in (*draft.references, draft.source_ref):
                if not self._reference_resolves(reference, events):
                    raise EvidenceInvalid(
                        _invalid(run_id, "event reference is unresolved", state.seq + 1)
                    )
            if state.seq == 0:
                if draft.event_type != LineageEventType.RUN_STARTED:
                    raise LineageConflict("the first event must be run.started")
            else:
                first = events[0]
                if draft.event_type == LineageEventType.RUN_STARTED or (
                    draft.repo_id,
                    draft.base_sha,
                    draft.agent_profile_id,
                    draft.policy_revision,
                ) != (
                    first.repo_id,
                    first.base_sha,
                    first.agent_profile_id,
                    first.policy_revision,
                ):
                    raise LineageConflict(
                        "event does not match the frozen run identity"
                    )
            assert event_snapshot is not None and global_snapshot is not None
            if event_snapshot.exists or global_snapshot.exists:
                raise LineageConflict("event uniqueness constraint rejected the append")

            event = _event(
                run_id,
                state,
                idempotency_key,
                draft,
                event_id=event_id,
                recorded_at=recorded_at,
            )
            try:
                from .lineage_reducer import (
                    ProjectionError,
                    reduce_events,
                    validate_semantic_artifacts,
                )

                validate_semantic_artifacts((*events, event), self._artifact)
                reduce_events((*events, event))
            except ProjectionError as error:
                raise EvidenceInvalid(
                    _invalid(
                        run_id,
                        f"event stream is semantically invalid: {error}",
                        error.first_invalid_seq or event.seq,
                    )
                ) from error
            event_bytes = canonical_json_bytes(event.model_dump(mode="json"))
            run = self._run(run_id)
            event_ref = run.collection(_EVENTS).document(_sequence_id(event.seq))
            idempotency_ref = run.collection(_IDEMPOTENCY).document(idempotency_digest)
            global_ref = self._global_events.document(event.event_id)
            transaction.create(
                event_ref,
                {
                    "schema_version": 2,
                    "event_id": event.event_id,
                    "run_id": run_id,
                    "seq": event.seq,
                    "idempotency_sha256": idempotency_digest,
                    "payload_sha256": event.payload_sha256,
                    "previous_event_sha256": event.previous_event_sha256,
                    "event_sha256": event.event_sha256,
                    "event_bytes": event_bytes,
                },
            )
            transaction.create(
                idempotency_ref,
                {
                    "schema_version": 2,
                    "run_id": run_id,
                    "idempotency_sha256": idempotency_digest,
                    "request_sha256": request_digest,
                    "event_id": event.event_id,
                    "event_seq": event.seq,
                    "event_sha256": event.event_sha256,
                },
            )
            transaction.create(
                global_ref,
                {
                    "schema_version": 2,
                    "event_id": event.event_id,
                    "run_id": run_id,
                    "event_seq": event.seq,
                    "event_sha256": event.event_sha256,
                },
            )
            head = {
                "schema_version": 2,
                "run_id": run_id,
                "seq": event.seq,
                "event_sha256": event.event_sha256,
                "event_count": event.seq,
                "repo_id": event.repo_id,
                "base_sha": event.base_sha,
                "agent_profile_id": event.agent_profile_id,
                "policy_revision": event.policy_revision,
            }
            if state.seq == 0:
                transaction.create(run, head)
            else:
                transaction.set(run, head)
            return event

        try:
            return apply(self._client.transaction())
        except (Aborted, AlreadyExists, Conflict) as error:
            raise LineageConflict(
                "Firestore transaction rejected the append"
            ) from error
        except ValueError as error:
            if isinstance(error.__cause__, Aborted):
                raise LineageConflict(
                    "Firestore transaction retry limit was exhausted"
                ) from error
            raise

    def verify(self, run_id: str) -> VerifiedHead | EvidenceInvalidState:
        state, _ = self._read_verified(run_id)
        return state

    def tail(
        self,
        run_id: str,
        after_seq: int,
        limit: int,
    ) -> tuple[Event, ...]:
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        state, events = self._read_verified(run_id)
        if isinstance(state, EvidenceInvalidState):
            raise EvidenceInvalid(state)
        return tuple(event for event in events if event.seq > after_seq)[:limit]
