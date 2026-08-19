from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from google.api_core.exceptions import Aborted, AlreadyExists, Conflict
from google.cloud import firestore

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from .models import (
    Lease,
    MissionEvent,
    MissionEventInput,
    MissionHead,
    MissionSnapshot,
)
from .store import (
    MissionConflict,
    MissionNotFound,
    MissionStoreError,
    StaleWorker,
)

_EVENTS = "events"
_COMMANDS = "commands"
_MATERIALIZED = "materialized"
_LEASE_SLOTS = "lease_slots"
_LEASES = "leases"
_CURRENT = "current"
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_COMMAND_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_MAX_LEASE_SECONDS = 3_600
_MAX_MATERIALIZED_JSON_BYTES = 900_000


class FirestoreMissionError(MissionStoreError):
    """Base error for rejected or malformed Firestore mission state."""


class LeaseFenceRejected(StaleWorker):
    """A missing, expired, released, or superseded lease rejected an effect."""


class MissionStateInvalid(FirestoreMissionError):
    """Stored mission state did not validate against the frozen domain model."""


def _now() -> datetime:
    return datetime.now(UTC)


def _document_data(snapshot: Any) -> dict[str, Any] | None:
    if not snapshot.exists:
        return None
    value = snapshot.to_dict()
    if not isinstance(value, dict):
        raise MissionStateInvalid("Firestore document is not an object")
    return value


def _sequence_id(seq: int) -> str:
    return f"{seq:020d}"


def _command_ref_id(command_id: str) -> str:
    if not isinstance(command_id, str) or _COMMAND_ID.fullmatch(command_id) is None:
        raise ValueError("command_id must be a valid idempotency key")
    return sha256_hex(command_id.encode())


def _event(
    mission_id: str,
    head: MissionHead,
    command_id: str,
    draft: MissionEventInput,
    *,
    event_id: str,
    recorded_at: datetime,
) -> MissionEvent:
    fields = {
        **{name: getattr(draft, name) for name in MissionEventInput.model_fields},
        "schema_version": 1,
        "event_id": event_id,
        "mission_id": mission_id,
        "seq": head.seq + 1,
        "server_recorded_at": recorded_at,
        "command_id": command_id,
        "payload_sha256": canonical_json_sha256(draft.payload),
        "previous_event_sha256": head.event_sha256,
    }
    canonical = MissionEvent.model_construct(
        **fields, event_sha256="0" * 64
    ).model_dump(mode="json", exclude={"event_sha256"})
    return MissionEvent.model_validate(
        {**canonical, "event_sha256": canonical_json_sha256(canonical)}
    )


def _lease_identity(lease: Lease) -> tuple[object, ...]:
    return (
        lease.lease_id,
        lease.mission_id,
        lease.plan_revision,
        lease.task_id,
        lease.attempt_id,
        lease.owner,
        lease.capability,
        lease.write_paths,
        lease.fencing_token,
        lease.issued_at,
    )


def _lease_fence_request(lease: Lease) -> dict[str, object]:
    return {
        "lease_id": lease.lease_id,
        "mission_id": lease.mission_id,
        "plan_revision": lease.plan_revision,
        "task_id": lease.task_id,
        "attempt_id": lease.attempt_id,
        "owner": lease.owner,
        "capability": lease.capability,
        "write_paths": list(lease.write_paths),
        "fencing_token": lease.fencing_token,
        "issued_at": lease.issued_at.isoformat(),
    }


class FirestoreMissionStore:
    """Transactional Firestore adapter for mission heads, views, and leases.

    Event appends read a head and one command index, while normal projection polls
    read one materialized snapshot and an indexed, bounded event tail. They never
    scan every event in a mission.

    The lease methods are internal persistence primitives, not a scheduler or a
    public claim service. Their caller remains responsible for policy, mission
    concurrency, task readiness, cross-task write-scope conflict checks, and
    appending the domain event that publishes a lease transition. Lease records
    deliberately do not mutate the event-head-bound materialized snapshot.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        namespace: str,
        clock: Callable[[], datetime] = _now,
        max_lease_seconds: int = 300,
    ) -> None:
        if not isinstance(namespace, str) or _NAMESPACE.fullmatch(namespace) is None:
            raise ValueError("namespace must match ^[a-z][a-z0-9_-]{0,31}$")
        if (
            type(max_lease_seconds) is not int
            or not 1 <= max_lease_seconds <= _MAX_LEASE_SECONDS
        ):
            raise ValueError("max_lease_seconds must be between 1 and 3600")
        self._client = client or firestore.Client()
        self._clock = clock
        self._max_lease_seconds = max_lease_seconds
        self._missions = self._client.collection(f"{namespace}_missions")

    def _mission(self, mission_id: str):
        # MissionHead provides the shared Identifier validation without a second
        # identifier grammar in this adapter.
        MissionHead(mission_id=mission_id, seq=0, event_sha256=None, event_count=0)
        return self._missions.document(mission_id)

    @staticmethod
    def empty_head(mission_id: str) -> MissionHead:
        return MissionHead(
            mission_id=mission_id, seq=0, event_sha256=None, event_count=0
        )

    @staticmethod
    def _materialized_ref(mission: Any):
        return mission.collection(_MATERIALIZED).document(_CURRENT)

    def _head_from_snapshot(self, mission_id: str, snapshot: Any) -> MissionHead:
        data = _document_data(snapshot)
        if data is None:
            return self.empty_head(mission_id)
        try:
            head = MissionHead.model_validate(data["head"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored mission head is malformed") from error
        if head.mission_id != mission_id:
            raise MissionStateInvalid("stored mission head belongs to another mission")
        return head

    def _transact(self, callback: Callable[[Any], Any]) -> Any:
        try:
            return firestore.transactional(callback)(self._client.transaction())
        except (Aborted, AlreadyExists, Conflict) as error:
            raise MissionConflict("Firestore transaction rejected the write") from error
        except ValueError as error:
            if isinstance(error.__cause__, Aborted):
                raise MissionConflict(
                    "Firestore transaction retry limit was exhausted"
                ) from error
            raise

    @staticmethod
    def _command_result(
        snapshot: Any, *, kind: str, request_sha256: str
    ) -> dict[str, Any] | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        if (
            data.get("schema_version") != 1
            or data.get("kind") != kind
            or data.get("request_sha256") != request_sha256
            or not isinstance(data.get("result"), dict)
        ):
            raise MissionConflict("command id was reused for another request")
        return data["result"]

    def head(self, mission_id: str) -> MissionHead:
        mission = self._mission(mission_id)
        snapshot = mission.get()
        if not snapshot.exists:
            raise MissionNotFound(mission_id)
        return self._head_from_snapshot(mission_id, snapshot)

    def append(
        self,
        mission_id: str,
        expected_head: MissionHead,
        command_id: str,
        draft: MissionEventInput,
        *,
        lease: Lease | None = None,
    ) -> MissionEvent:
        if not isinstance(expected_head, MissionHead) or not isinstance(
            draft, MissionEventInput
        ):
            raise TypeError(
                "append requires validated MissionHead and MissionEventInput values"
            )
        if expected_head.mission_id != mission_id:
            raise MissionConflict("expected head belongs to another mission")
        if lease is not None and (
            not isinstance(lease, Lease) or lease.mission_id != mission_id
        ):
            raise LeaseFenceRejected("lease belongs to another mission")
        if lease is not None and (
            draft.payload.get("task_id") != lease.task_id
            or draft.payload.get("attempt_id") != lease.attempt_id
        ):
            raise LeaseFenceRejected(
                "fenced effect is not bound to the lease task and attempt"
            )

        command_ref_id = _command_ref_id(command_id)
        request_sha256 = canonical_json_sha256(
            {
                "command_id": command_id,
                "draft": draft.model_dump(mode="json"),
                "expected_head": expected_head.model_dump(mode="json"),
                "lease_fence": _lease_fence_request(lease) if lease else None,
                "mission_id": mission_id,
            }
        )
        event_id = f"event_{uuid.uuid4().hex}"
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(command_ref_id)

        def apply(transaction: Any) -> MissionEvent:
            command_snapshot = command_ref.get(transaction=transaction)
            result = self._command_result(
                command_snapshot, kind="event", request_sha256=request_sha256
            )
            if result is not None:
                try:
                    return MissionEvent.model_validate(result)
                except (TypeError, ValueError) as error:
                    raise MissionStateInvalid(
                        "stored command result is malformed"
                    ) from error
            recorded_at = self._clock()

            head_snapshot = mission.get(transaction=transaction)
            materialized_ref = self._materialized_ref(mission)
            materialized_snapshot = materialized_ref.get(transaction=transaction)
            current = self._head_from_snapshot(mission_id, head_snapshot)
            if current != expected_head:
                raise MissionConflict(
                    "expected head does not match the committed mission head"
                )
            if lease is not None:
                self._require_fence(transaction, lease, recorded_at)

            event = _event(
                mission_id,
                current,
                command_id,
                draft,
                event_id=event_id,
                recorded_at=recorded_at,
            )
            event_value = event.model_dump(mode="json")
            event_ref = mission.collection(_EVENTS).document(_sequence_id(event.seq))
            next_head = MissionHead(
                mission_id=mission_id,
                seq=event.seq,
                event_sha256=event.event_sha256,
                event_count=event.seq,
            )
            materialized = _document_data(materialized_snapshot)
            if materialized is not None and (
                materialized.get("schema_version") != 1
                or (
                    "value" in materialized
                    and not isinstance(materialized["value"], dict)
                )
            ):
                raise MissionStateInvalid("stored materialized snapshot is malformed")
            transaction.create(
                event_ref,
                {
                    "schema_version": 1,
                    "seq": event.seq,
                    "event_sha256": event.event_sha256,
                    "value": event_value,
                },
            )
            transaction.set(
                mission,
                {"schema_version": 1, "head": next_head.model_dump(mode="json")},
            )
            transaction.set(
                materialized_ref,
                {
                    "schema_version": 1,
                    "committed_head": next_head.model_dump(mode="json"),
                    "materialization_pending": True,
                    **(
                        {"value": materialized["value"]}
                        if materialized is not None and "value" in materialized
                        else {}
                    ),
                },
            )
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "event",
                    "request_sha256": request_sha256,
                    "result": event_value,
                },
            )
            return event

        return self._transact(apply)

    def tail(
        self, mission_id: str, after_seq: int, limit: int = 256
    ) -> tuple[MissionEvent, ...]:
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        mission = self._mission(mission_id)
        if not mission.get().exists:
            raise MissionNotFound(mission_id)
        query = (
            mission.collection(_EVENTS)
            .where(filter=firestore.FieldFilter("seq", ">", after_seq))
            .order_by("seq")
            .limit(limit)
        )
        events: list[MissionEvent] = []
        for snapshot in query.stream():
            data = _document_data(snapshot)
            try:
                event = MissionEvent.model_validate(data["value"] if data else None)
            except (KeyError, TypeError, ValueError) as error:
                raise MissionStateInvalid(
                    "stored mission event is malformed"
                ) from error
            if event.mission_id != mission_id:
                raise MissionStateInvalid("stored event belongs to another mission")
            expected_seq = after_seq + len(events) + 1
            if event.seq != expected_seq:
                raise MissionStateInvalid("mission event tail is not contiguous")
            if events and event.previous_event_sha256 != events[-1].event_sha256:
                raise MissionStateInvalid("mission event tail hash link is broken")
            events.append(event)
        return tuple(events)

    def snapshot(self, mission_id: str) -> MissionSnapshot:
        mission = self._mission(mission_id)
        snapshot = self._materialized_ref(mission).get()
        data = _document_data(snapshot)
        if data is None or "value" not in data:
            raise MissionNotFound(mission_id)
        try:
            committed_head = MissionHead.model_validate(data["committed_head"])
            value = MissionSnapshot.model_validate(data["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid(
                "stored materialized snapshot is malformed"
            ) from error
        if value.mission.mission_id != mission_id:
            raise MissionStateInvalid("stored snapshot belongs to another mission")
        if committed_head != value.head:
            raise MissionStateInvalid(
                "materialized snapshot is behind the committed mission head"
            )
        if data.get("materialization_pending") is not False:
            raise MissionStateInvalid("committed mission state is not materialized")
        return value

    def save_snapshot(self, snapshot: MissionSnapshot) -> MissionSnapshot:
        if not isinstance(snapshot, MissionSnapshot):
            raise TypeError("save_snapshot requires a validated MissionSnapshot")
        mission_id = snapshot.mission.mission_id
        mission = self._mission(mission_id)
        snapshot_ref = self._materialized_ref(mission)
        value = snapshot.model_dump(mode="json")
        document = {
            "schema_version": 1,
            "committed_head": snapshot.head.model_dump(mode="json"),
            "materialization_pending": False,
            "value": value,
        }
        if len(canonical_json_bytes(document)) > _MAX_MATERIALIZED_JSON_BYTES:
            raise ValueError("materialized snapshot exceeds the Firestore size bound")

        def apply(transaction: Any) -> MissionSnapshot:
            head_snapshot = mission.get(transaction=transaction)
            stored_snapshot = snapshot_ref.get(transaction=transaction)
            current = self._head_from_snapshot(mission_id, head_snapshot)
            if current != snapshot.head:
                raise MissionConflict(
                    "materialized snapshot does not match the committed mission head"
                )
            existing = _document_data(stored_snapshot)
            if existing is not None:
                try:
                    committed_head = MissionHead.model_validate(
                        existing["committed_head"]
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise MissionStateInvalid(
                        "stored materialized head is malformed"
                    ) from error
                if committed_head != current:
                    raise MissionStateInvalid(
                        "materialized head marker does not match the mission head"
                    )
            if existing is not None and "value" in existing:
                try:
                    previous = MissionSnapshot.model_validate(existing["value"])
                except (KeyError, TypeError, ValueError) as error:
                    raise MissionStateInvalid(
                        "stored materialized snapshot is malformed"
                    ) from error
                if previous.head == snapshot.head:
                    if previous != snapshot:
                        raise MissionConflict(
                            "mission head already has another materialized snapshot"
                        )
                    return previous
            transaction.set(snapshot_ref, document)
            return snapshot

        return self._transact(apply)

    # Scheduler call sites can use either name without another adapter layer.
    materialize = save_snapshot

    def _lease_slot(self, lease: Lease):
        mission = self._mission(lease.mission_id)
        slot_id = f"{lease.plan_revision:020d}--{lease.task_id}"
        return mission.collection(_LEASE_SLOTS).document(slot_id)

    def _stored_lease(self, snapshot: Any) -> Lease | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        try:
            return Lease.model_validate(data["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored lease is malformed") from error

    def _require_fence(
        self, transaction: Any, lease: Lease, observed_at: datetime
    ) -> Lease:
        current = self._stored_lease(
            self._lease_slot(lease).get(transaction=transaction)
        )
        if (
            current is None
            or _lease_identity(current) != _lease_identity(lease)
            or current.released_at is not None
            or current.issued_at > observed_at
            or current.expires_at <= observed_at
        ):
            raise LeaseFenceRejected("lease fencing token is not current and active")
        return current

    def assert_fence(self, lease: Lease) -> None:
        if not isinstance(lease, Lease):
            raise TypeError("assert_fence requires a validated Lease")
        current = self._stored_lease(self._lease_slot(lease).get())
        when = self._clock()
        if (
            current is None
            or _lease_identity(current) != _lease_identity(lease)
            or current.released_at is not None
            or current.issued_at > when
            or current.expires_at <= when
        ):
            raise LeaseFenceRejected("lease fencing token is not current and active")

    def claim_lease(self, lease: Lease, command_id: str) -> Lease:
        if not isinstance(lease, Lease):
            raise TypeError("claim_lease requires a validated Lease")
        if lease.released_at is not None:
            raise ValueError("a new lease claim cannot already be released")
        mission = self._mission(lease.mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )
        slot_ref = self._lease_slot(lease)
        history_ref = mission.collection(_LEASES).document(lease.lease_id)
        request_sha256 = canonical_json_sha256(
            {
                "action": "lease.claim",
                "command_id": command_id,
                "lease": lease.model_dump(mode="json"),
            }
        )

        def apply(transaction: Any) -> Lease:
            command_snapshot = command_ref.get(transaction=transaction)
            result = self._command_result(
                command_snapshot, kind="lease.claim", request_sha256=request_sha256
            )
            if result is not None:
                return Lease.model_validate(result)
            observed_at = self._clock()
            if (
                lease.issued_at > observed_at
                or lease.heartbeat_at != lease.issued_at
                or lease.expires_at <= observed_at
                or (lease.expires_at - observed_at).total_seconds()
                > self._max_lease_seconds
                or (lease.expires_at - lease.issued_at).total_seconds()
                > self._max_lease_seconds
            ):
                raise LeaseFenceRejected(
                    "lease claim timestamps are not server-current"
                )

            head_snapshot = mission.get(transaction=transaction)
            slot_snapshot = slot_ref.get(transaction=transaction)
            history_snapshot = history_ref.get(transaction=transaction)
            if self._head_from_snapshot(lease.mission_id, head_snapshot).seq == 0:
                raise MissionConflict("cannot claim a lease for an unknown mission")
            current = self._stored_lease(slot_snapshot)
            if (
                current is not None
                and current.released_at is None
                and current.expires_at > observed_at
            ):
                raise LeaseFenceRejected("task already has an active lease")
            expected_token = 1 if current is None else current.fencing_token + 1
            if lease.fencing_token != expected_token:
                raise LeaseFenceRejected(
                    f"lease claim requires fencing token {expected_token}"
                )
            if history_snapshot.exists:
                raise MissionConflict("lease_id was already used")
            value = lease.model_dump(mode="json")
            document = {
                "schema_version": 1,
                "fencing_token": lease.fencing_token,
                "task_id": lease.task_id,
                "value": value,
            }
            transaction.set(slot_ref, document)
            transaction.create(history_ref, document)
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "lease.claim",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return lease

        return self._transact(apply)

    def heartbeat_lease(self, lease: Lease, command_id: str) -> Lease:
        if not isinstance(lease, Lease):
            raise TypeError("heartbeat_lease requires a validated Lease")
        if lease.released_at is not None:
            raise ValueError("a heartbeat cannot release a lease")
        return self._update_lease(lease, command_id, action="lease.heartbeat")

    def release_lease(self, lease: Lease, command_id: str) -> Lease:
        if not isinstance(lease, Lease):
            raise TypeError("release_lease requires a validated Lease")
        if lease.released_at is None:
            raise ValueError("a released lease requires release fields")
        return self._update_lease(lease, command_id, action="lease.release")

    def _update_lease(self, lease: Lease, command_id: str, *, action: str) -> Lease:
        mission = self._mission(lease.mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )
        slot_ref = self._lease_slot(lease)
        history_ref = mission.collection(_LEASES).document(lease.lease_id)
        request_sha256 = canonical_json_sha256(
            {
                "action": action,
                "command_id": command_id,
                "lease": lease.model_dump(mode="json"),
            }
        )

        def apply(transaction: Any) -> Lease:
            command_snapshot = command_ref.get(transaction=transaction)
            result = self._command_result(
                command_snapshot, kind=action, request_sha256=request_sha256
            )
            if result is not None:
                return Lease.model_validate(result)
            observed_at = self._clock()

            slot_snapshot = slot_ref.get(transaction=transaction)
            history_snapshot = history_ref.get(transaction=transaction)
            current = self._stored_lease(slot_snapshot)
            history = self._stored_lease(history_snapshot)
            if (
                current is None
                or history is None
                or _lease_identity(current) != _lease_identity(lease)
                or _lease_identity(history) != _lease_identity(lease)
                or current.released_at is not None
                or current.expires_at <= observed_at
            ):
                raise LeaseFenceRejected("lease fencing token is not current")

            if action == "lease.heartbeat":
                if (
                    lease.heartbeat_at <= current.heartbeat_at
                    or lease.heartbeat_at >= current.expires_at
                    or lease.heartbeat_at > observed_at
                    or lease.expires_at <= observed_at
                    or lease.expires_at < current.expires_at
                    or (lease.expires_at - observed_at).total_seconds()
                    > self._max_lease_seconds
                    or (lease.expires_at - lease.issued_at).total_seconds()
                    > self._max_lease_seconds
                ):
                    raise LeaseFenceRejected(
                        "heartbeat is stale, expired, or outside the TTL bound"
                    )
            else:
                assert lease.released_at is not None
                if (
                    lease.heartbeat_at != current.heartbeat_at
                    or lease.expires_at != current.expires_at
                    or lease.released_at < current.heartbeat_at
                    or lease.released_at > observed_at
                    or lease.released_at >= current.expires_at
                ):
                    raise LeaseFenceRejected("lease release is stale or inconsistent")

            value = lease.model_dump(mode="json")
            document = {
                "schema_version": 1,
                "fencing_token": lease.fencing_token,
                "task_id": lease.task_id,
                "value": value,
            }
            transaction.set(slot_ref, document)
            transaction.set(history_ref, document)
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": action,
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return lease

        return self._transact(apply)


__all__ = [
    "FirestoreMissionError",
    "FirestoreMissionStore",
    "LeaseFenceRejected",
    "MissionConflict",
    "MissionStateInvalid",
]
