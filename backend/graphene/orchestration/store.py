from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import TypeAdapter

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..models import GitSha, IdempotencyKey, Sha256, TruthKind, UtcDateTime
from .models import (
    ArtifactPublication,
    Attempt,
    AttemptResult,
    AttemptState,
    Dispatch,
    EvidenceReference,
    Gate,
    GenericEvidenceLink,
    Lease,
    LegacyEvidenceLink,
    Mission,
    MissionAuthority,
    MissionEvent,
    MissionEventInput,
    MissionEventType,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    Plan,
    ProjectPolicy,
    ProjectPolicySummary,
    PublicationState,
    ResourceReceipt,
    Task,
    TaskKind,
    TaskState,
)
from .reducer import TransitionError, reduce_events, transition_mission, transition_task
from .validation import require_valid_plan

if TYPE_CHECKING:
    from .adk import PlanProposalReceipt

_COMMAND_ID = TypeAdapter(IdempotencyKey)
_GIT_SHA = TypeAdapter(GitSha)
_SHA256 = TypeAdapter(Sha256)
_UTC_TIME = TypeAdapter(UtcDateTime)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mission_policies (
    policy_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    policy_sha256 TEXT NOT NULL,
    policy_bytes BLOB NOT NULL,
    PRIMARY KEY (policy_id, revision)
);

CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_revision INTEGER NOT NULL,
    plan_revision INTEGER NOT NULL CHECK (plan_revision >= 1),
    status TEXT NOT NULL,
    final_outcome TEXT,
    mission_bytes BLOB NOT NULL,
    FOREIGN KEY (policy_id, policy_revision)
        REFERENCES mission_policies(policy_id, revision)
);

CREATE TABLE IF NOT EXISTS mission_plans (
    mission_id TEXT NOT NULL REFERENCES missions(mission_id),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    plan_sha256 TEXT NOT NULL,
    plan_bytes BLOB NOT NULL,
    PRIMARY KEY (mission_id, revision)
);

CREATE TABLE IF NOT EXISTS mission_tasks (
    mission_id TEXT NOT NULL,
    plan_revision INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    priority INTEGER NOT NULL,
    attempt_limit INTEGER NOT NULL CHECK (attempt_limit >= 1),
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
    fencing_counter INTEGER NOT NULL CHECK (fencing_counter >= 0),
    retry_at TEXT,
    blocker TEXT,
    accepted_attempt_id TEXT,
    task_bytes BLOB NOT NULL,
    task_contract_event_sha256 TEXT,
    PRIMARY KEY (mission_id, plan_revision, task_id),
    FOREIGN KEY (mission_id, plan_revision)
        REFERENCES mission_plans(mission_id, revision)
);

CREATE INDEX IF NOT EXISTS idx_mission_tasks_ready
ON mission_tasks(mission_id, plan_revision, state, priority DESC, task_id);

CREATE TABLE IF NOT EXISTS mission_dependencies (
    mission_id TEXT NOT NULL,
    plan_revision INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    dependency_id TEXT NOT NULL,
    satisfied_attempt_id TEXT,
    PRIMARY KEY (mission_id, plan_revision, task_id, dependency_id),
    FOREIGN KEY (mission_id, plan_revision, task_id)
        REFERENCES mission_tasks(mission_id, plan_revision, task_id),
    FOREIGN KEY (mission_id, plan_revision, dependency_id)
        REFERENCES mission_tasks(mission_id, plan_revision, task_id)
);

CREATE TABLE IF NOT EXISTS mission_attempts (
    attempt_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    plan_revision INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    state TEXT NOT NULL,
    dispatch_command_id TEXT NOT NULL UNIQUE,
    attempt_bytes BLOB NOT NULL,
    UNIQUE (mission_id, plan_revision, task_id, attempt_number),
    FOREIGN KEY (mission_id, plan_revision, task_id)
        REFERENCES mission_tasks(mission_id, plan_revision, task_id)
);

CREATE INDEX IF NOT EXISTS idx_mission_attempts_recovery
ON mission_attempts(mission_id, state, task_id);

CREATE TABLE IF NOT EXISTS mission_leases (
    lease_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    plan_revision INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    fencing_token INTEGER NOT NULL CHECK (fencing_token >= 1),
    expires_at TEXT NOT NULL,
    released_at TEXT,
    lease_bytes BLOB NOT NULL,
    UNIQUE (mission_id, plan_revision, task_id, fencing_token),
    FOREIGN KEY (attempt_id) REFERENCES mission_attempts(attempt_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_active_task_lease
ON mission_leases(mission_id, plan_revision, task_id)
WHERE released_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_mission_lease_expiry
ON mission_leases(mission_id, released_at, expires_at);

CREATE TABLE IF NOT EXISTS mission_publications (
    publication_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    plan_revision INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    output_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    publication_bytes BLOB NOT NULL,
    UNIQUE (attempt_id, output_name),
    FOREIGN KEY (attempt_id) REFERENCES mission_attempts(attempt_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_accepted_output
ON mission_publications(mission_id, plan_revision, task_id, output_name)
WHERE state = 'accepted';

CREATE INDEX IF NOT EXISTS idx_mission_publication_consumers
ON mission_publications(mission_id, plan_revision, task_id, state);

CREATE TABLE IF NOT EXISTS mission_gates (
    gate_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    resolution TEXT,
    gate_bytes BLOB NOT NULL,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
);

CREATE INDEX IF NOT EXISTS idx_mission_open_gates
ON mission_gates(mission_id, resolution, gate_id);

CREATE TABLE IF NOT EXISTS mission_heads (
    mission_id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL CHECK (seq >= 0),
    event_sha256 TEXT,
    event_count INTEGER NOT NULL CHECK (event_count >= 0)
);

CREATE TABLE IF NOT EXISTS mission_events (
    event_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission_heads(mission_id),
    seq INTEGER NOT NULL CHECK (seq >= 1),
    command_id TEXT NOT NULL,
    event_sha256 TEXT NOT NULL,
    event_bytes BLOB NOT NULL,
    UNIQUE (mission_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_mission_event_tail
ON mission_events(mission_id, seq);

CREATE TRIGGER IF NOT EXISTS mission_events_no_update
BEFORE UPDATE ON mission_events BEGIN
    SELECT RAISE(ABORT, 'mission events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS mission_events_no_delete
BEFORE DELETE ON mission_events BEGIN
    SELECT RAISE(ABORT, 'mission events are append-only');
END;

CREATE TABLE IF NOT EXISTS mission_commands (
    mission_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    result_bytes BLOB NOT NULL,
    PRIMARY KEY (mission_id, command_id)
);
"""


class MissionStoreError(RuntimeError):
    pass


class MissionNotFound(MissionStoreError):
    pass


class MissionConflict(MissionStoreError):
    pass


class LeaseConflict(MissionConflict):
    pass


class StaleWorker(LeaseConflict):
    pass


class ArtifactResolver(Protocol):
    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...


class LocalCommitVerifier(Protocol):
    def __call__(self, receipt_bytes: bytes) -> bool: ...


def _json_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return canonical_json_bytes(value)


def _iso(value: datetime) -> str:
    return value.isoformat()


class SQLiteMissionStore:
    """Mission authority backed by an append-only stream and indexed views."""

    def __init__(
        self,
        path: str | Path,
        *,
        artifact_resolver: ArtifactResolver | None = None,
        local_commit_verifier: LocalCommitVerifier | None = None,
    ) -> None:
        if str(path) == ":memory:":
            raise ValueError("mission state requires a durable SQLite path")
        self.path = str(path)
        self.artifact_resolver = artifact_resolver
        self.local_commit_verifier = local_commit_verifier
        with closing(self._connect()) as connection:
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise MissionStoreError("SQLite WAL mode is required")
            connection.executescript(_SCHEMA)

    def bind_artifact_resolver(self, resolver: ArtifactResolver) -> None:
        """Bind the evidence artifact authority before worker results arrive."""

        if (
            self.artifact_resolver is not None
            and self.artifact_resolver is not resolver
        ):
            raise MissionConflict("mission artifact resolver is already bound")
        self.artifact_resolver = resolver

    def bind_local_commit_verifier(self, verifier: LocalCommitVerifier) -> None:
        """Bind the trusted Git/result-ref checker used by local result creation."""

        if (
            self.local_commit_verifier is not None
            and self.local_commit_verifier is not verifier
        ):
            raise MissionConflict("mission local commit verifier is already bound")
        self.local_commit_verifier = verifier

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def empty_head(mission_id: str) -> MissionHead:
        return MissionHead(
            mission_id=mission_id, seq=0, event_sha256=None, event_count=0
        )

    @staticmethod
    def _request_sha256(operation: str, values: object) -> str:
        # Recording time is server metadata, not part of a command's semantic
        # identity. A transport retry must return the first committed result.
        if isinstance(values, dict):
            values = {
                key: value for key, value in values.items() if key != "recorded_at"
            }
        return canonical_json_sha256({"operation": operation, "values": values})

    @staticmethod
    def _time(value: datetime) -> datetime:
        return _UTC_TIME.validate_python(value)

    @staticmethod
    def _event(
        mission_id: str,
        head: MissionHead,
        command_id: str,
        draft: MissionEventInput,
        recorded_at: datetime,
    ) -> MissionEvent:
        seq = head.seq + 1
        event_id = (
            "mission_event_"
            + canonical_json_sha256(
                {
                    "command_id": command_id,
                    "event_type": draft.event_type.value,
                    "mission_id": mission_id,
                    "payload": draft.payload,
                    "seq": seq,
                }
            )[:32]
        )
        core = {
            **{name: getattr(draft, name) for name in MissionEventInput.model_fields},
            "schema_version": 1,
            "event_id": event_id,
            "mission_id": mission_id,
            "seq": seq,
            "server_recorded_at": recorded_at,
            "command_id": command_id,
            "payload_sha256": canonical_json_sha256(draft.payload),
            "previous_event_sha256": head.event_sha256,
        }
        canonical = MissionEvent.model_construct(
            **core, event_sha256="0" * 64
        ).model_dump(mode="json", exclude={"event_sha256"})
        return MissionEvent.model_validate(
            {**canonical, "event_sha256": canonical_json_sha256(canonical)}
        )

    @staticmethod
    def _head(connection: sqlite3.Connection, mission_id: str) -> MissionHead:
        row = connection.execute(
            "SELECT seq, event_sha256, event_count FROM mission_heads WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        return (
            SQLiteMissionStore.empty_head(mission_id)
            if row is None
            else MissionHead(
                mission_id=mission_id,
                seq=row["seq"],
                event_sha256=row["event_sha256"],
                event_count=row["event_count"],
            )
        )

    def _append(
        self,
        connection: sqlite3.Connection,
        mission_id: str,
        command_id: str,
        drafts: tuple[MissionEventInput, ...],
        recorded_at: datetime,
    ) -> MissionHead:
        head = self._head(connection, mission_id)
        if head.seq == 0:
            connection.execute(
                "INSERT INTO mission_heads VALUES (?, 0, NULL, 0)", (mission_id,)
            )
        for draft in drafts:
            event = self._event(mission_id, head, command_id, draft, recorded_at)
            connection.execute(
                "INSERT INTO mission_events VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    mission_id,
                    event.seq,
                    command_id,
                    event.event_sha256,
                    _json_bytes(event),
                ),
            )
            updated = connection.execute(
                "UPDATE mission_heads SET seq = ?, event_sha256 = ?, "
                "event_count = event_count + 1 WHERE mission_id = ? AND seq = ? "
                "AND event_count = ? AND event_sha256 IS ?",
                (
                    event.seq,
                    event.event_sha256,
                    mission_id,
                    head.seq,
                    head.event_count,
                    head.event_sha256,
                ),
            )
            if updated.rowcount != 1:
                raise MissionConflict("mission head changed during append")
            head = MissionHead(
                mission_id=mission_id,
                seq=event.seq,
                event_sha256=event.event_sha256,
                event_count=event.seq,
            )
        return head

    @staticmethod
    def _existing_command(
        connection: sqlite3.Connection,
        mission_id: str,
        command_id: str,
        request_sha256: str,
    ) -> dict[str, object] | None:
        row = connection.execute(
            "SELECT request_sha256, result_bytes FROM mission_commands "
            "WHERE mission_id = ? AND command_id = ?",
            (mission_id, command_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != request_sha256:
            raise MissionConflict("mission command id was reused with another request")
        value = json.loads(row["result_bytes"])
        if (
            not isinstance(value, dict)
            or canonical_json_bytes(value) != row["result_bytes"]
        ):
            raise MissionStoreError("stored mission command result is invalid")
        return value

    @staticmethod
    def _record_command(
        connection: sqlite3.Connection,
        mission_id: str,
        command_id: str,
        request_sha256: str,
        result: dict[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO mission_commands VALUES (?, ?, ?, ?)",
            (mission_id, command_id, request_sha256, canonical_json_bytes(result)),
        )

    @staticmethod
    def _head_result(head: MissionHead) -> dict[str, object]:
        return {"kind": "head", "value": head.model_dump(mode="json")}

    @staticmethod
    def _result_head(value: dict[str, object]) -> MissionHead:
        if value.get("kind") != "head":
            raise MissionStoreError("stored command result kind is invalid")
        return MissionHead.model_validate(value["value"])

    @staticmethod
    def _draft(
        event_type: MissionEventType,
        payload: dict[str, object],
        *,
        truth_kind: TruthKind = TruthKind.SERVER_DERIVED,
        authority: MissionAuthority = MissionAuthority.SCHEDULER,
        references: tuple[EvidenceReference, ...] = (),
    ) -> MissionEventInput:
        return MissionEventInput(
            event_type=event_type,
            truth_kind=truth_kind,
            authority=authority,
            references=references,
            payload=payload,
        )

    def _validate_plan_proposal_receipt(
        self,
        reference: EvidenceReference | None,
        *,
        policy: ProjectPolicy,
        mission: Mission,
        plan: Plan,
        plan_sha256: str,
    ) -> PlanProposalReceipt | None:
        if reference is None:
            return None
        if mission.creation_source != "operator":
            raise MissionConflict("fixture missions cannot claim planner provenance")
        if reference.kind != "plan-proposal-receipt":
            raise MissionConflict("plan proposal receipt kind is invalid")
        if self.artifact_resolver is None:
            raise MissionConflict("plan proposal receipt resolver is unavailable")
        raw = self.artifact_resolver.resolve(reference.kind, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise MissionConflict("plan proposal receipt is unavailable")
        try:
            from .adk import PlanProposalReceipt, planning_input_sha256

            proposal = PlanProposalReceipt.model_validate_json(raw)
        except (ImportError, ValueError) as error:
            raise MissionConflict("plan proposal receipt is invalid") from error
        if (
            proposal.mission_id != mission.mission_id
            or proposal.revision != plan.revision
            or proposal.plan_sha256 != plan_sha256
            or proposal.planning_input_sha256
            != planning_input_sha256(
                policy,
                mission_id=mission.mission_id,
                revision=plan.revision,
                goal=mission.goal,
                success_criteria=mission.success_criteria,
            )
            or proposal.requested_model != proposal.returned_model
        ):
            raise MissionConflict("plan proposal receipt bindings changed")
        return proposal

    def create_mission(
        self,
        policy: ProjectPolicy,
        mission: Mission,
        plan: Plan,
        command_id: str,
        *,
        plan_proposal_receipt: EvidenceReference | None = None,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        require_valid_plan(policy, plan)
        if (
            mission.status != MissionStatus.PROPOSED
            or mission.mission_id != plan.mission_id
            or mission.policy_id != policy.policy_id
            or mission.policy_revision != policy.revision
            or mission.repo_id != policy.repo_id
            or mission.base_sha != policy.base_sha
            or mission.plan_revision != plan.revision
            or mission.resource_budget != policy.resource_budget
        ):
            raise MissionConflict("mission, plan, and policy bindings do not match")
        plan_sha = canonical_json_sha256(plan.model_dump(mode="json"))
        request = {
            "mission": mission.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "plan_proposal_receipt": (
                None
                if plan_proposal_receipt is None
                else plan_proposal_receipt.model_dump(mode="json")
            ),
            "policy": policy.model_dump(mode="json"),
            "recorded_at": recorded_at.isoformat(),
        }
        request_sha = self._request_sha256("create_mission", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission.mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                if connection.execute(
                    "SELECT 1 FROM missions WHERE mission_id = ?", (mission.mission_id,)
                ).fetchone():
                    raise MissionConflict("mission already exists")
                proposal = self._validate_plan_proposal_receipt(
                    plan_proposal_receipt,
                    policy=policy,
                    mission=mission,
                    plan=plan,
                    plan_sha256=plan_sha,
                )

                policy_bytes = _json_bytes(policy)
                policy_sha = canonical_json_sha256(policy.model_dump(mode="json"))
                connection.execute(
                    "INSERT OR IGNORE INTO mission_policies VALUES (?, ?, ?, ?)",
                    (policy.policy_id, policy.revision, policy_sha, policy_bytes),
                )
                stored_policy = connection.execute(
                    "SELECT policy_sha256, policy_bytes FROM mission_policies "
                    "WHERE policy_id = ? AND revision = ?",
                    (policy.policy_id, policy.revision),
                ).fetchone()
                if stored_policy is None or (
                    stored_policy["policy_sha256"],
                    stored_policy["policy_bytes"],
                ) != (policy_sha, policy_bytes):
                    raise MissionConflict(
                        "policy revision already has different content"
                    )

                fixture_truth = mission.creation_source in {
                    "scripted_fixture",
                    "replay",
                }
                auto_approve = mission.creation_source == "replay"
                status = (
                    MissionStatus.RUNNING if auto_approve else MissionStatus.PROPOSED
                )
                connection.execute(
                    "INSERT INTO missions VALUES (?, ?, ?, ?, ?, NULL, ?)",
                    (
                        mission.mission_id,
                        policy.policy_id,
                        policy.revision,
                        plan.revision,
                        status.value,
                        _json_bytes(mission),
                    ),
                )
                plan_bytes = _json_bytes(plan)
                connection.execute(
                    "INSERT INTO mission_plans VALUES (?, ?, ?, ?)",
                    (mission.mission_id, plan.revision, plan_sha, plan_bytes),
                )
                for task in plan.tasks:
                    connection.execute(
                        "INSERT INTO mission_tasks VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?, NULL)",
                        (
                            mission.mission_id,
                            plan.revision,
                            task.task_id,
                            task.kind.value,
                            task.state.value,
                            task.priority,
                            task.attempt_limit,
                            task.attempt_count,
                            _json_bytes(task),
                        ),
                    )
                # The dependency FK points back to mission_tasks, so populate the
                # complete task set before adding edges.  Canonical task order is
                # deliberately unrelated to topological order.
                for task in plan.tasks:
                    for dependency in task.dependencies:
                        connection.execute(
                            "INSERT INTO mission_dependencies VALUES (?, ?, ?, ?, NULL)",
                            (
                                mission.mission_id,
                                plan.revision,
                                task.task_id,
                                dependency,
                            ),
                        )

                drafts = [
                    self._draft(
                        MissionEventType.PROJECT_CREATED,
                        {
                            "base_sha": policy.base_sha,
                            "policy_id": policy.policy_id,
                            "policy_revision": policy.revision,
                            "policy_sha256": policy_sha,
                            "repo_id": policy.repo_id,
                        },
                        truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                        authority=MissionAuthority.POLICY_ENGINE,
                    ),
                    self._draft(
                        MissionEventType.MISSION_CREATED,
                        {
                            "creation_source": mission.creation_source,
                            "goal_sha256": canonical_json_sha256(mission.goal),
                            "mission_sha256": canonical_json_sha256(
                                mission.model_dump(mode="json")
                            ),
                            "plan_revision": plan.revision,
                            "status": MissionStatus.PROPOSED.value,
                            "success_criteria_count": len(mission.success_criteria),
                        },
                        authority=MissionAuthority.MISSION_SERVICE,
                    ),
                    self._draft(
                        MissionEventType.PLAN_PROPOSED,
                        {
                            "plan_revision": plan.revision,
                            "plan_sha256": plan_sha,
                            **(
                                {}
                                if proposal is None or plan_proposal_receipt is None
                                else {
                                    "plan_proposal_driver": proposal.driver,
                                    "plan_proposal_receipt_id": plan_proposal_receipt.id,
                                    "plan_proposal_receipt_sha256": (
                                        plan_proposal_receipt.sha256
                                    ),
                                    "planning_input_sha256": (
                                        proposal.planning_input_sha256
                                    ),
                                    "requested_model": proposal.requested_model,
                                    "returned_model": proposal.returned_model,
                                }
                            ),
                            "task_count": len(plan.tasks),
                        },
                        truth_kind=(
                            TruthKind.SIMULATED_FIXTURE
                            if fixture_truth
                            else (
                                TruthKind.MODEL_PROPOSED
                                if proposal is not None
                                else TruthKind.SERVER_DERIVED
                            )
                        ),
                        authority=(
                            MissionAuthority.SIMULATED_FIXTURE
                            if fixture_truth
                            else (
                                MissionAuthority.PLANNER
                                if proposal is not None
                                else MissionAuthority.MISSION_SERVICE
                            )
                        ),
                        references=(
                            ()
                            if plan_proposal_receipt is None
                            else (plan_proposal_receipt,)
                        ),
                    ),
                    self._draft(
                        MissionEventType.PLAN_VALIDATED,
                        {
                            "plan_revision": plan.revision,
                            "plan_sha256": plan_sha,
                            "status": "valid",
                        },
                        truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                        authority=MissionAuthority.VALIDATOR,
                    ),
                ]
                if auto_approve:
                    drafts.append(
                        self._draft(
                            MissionEventType.PLAN_APPROVED,
                            {
                                "operator_label": "scripted-fixture",
                                "plan_revision": plan.revision,
                                "plan_sha256": plan_sha,
                                "status": "approved",
                            },
                            truth_kind=TruthKind.SIMULATED_FIXTURE,
                            authority=MissionAuthority.SIMULATED_FIXTURE,
                        )
                    )
                head = self._append(
                    connection,
                    mission.mission_id,
                    command_id,
                    tuple(drafts),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission.mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def approve_plan(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_revision: int,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected revision must be a positive integer")
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        return self._mission_status_command(
            mission_id,
            command_id,
            recorded_at=recorded_at,
            operation="approve_plan",
            expected=MissionStatus.PROPOSED,
            target=MissionStatus.RUNNING,
            event_type=MissionEventType.PLAN_APPROVED,
            payload={
                "operator_label": operator_label,
                "operator_rationale": rationale,
                "plan_revision": expected_revision,
                "status": "approved",
            },
            truth_kind=truth_kind,
            authority=self._authority_for_truth(truth_kind),
            expected_plan_revision=expected_revision,
        )

    def _mission_row(
        self, connection: sqlite3.Connection, mission_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            raise MissionNotFound(mission_id)
        return row

    def _plan(
        self, connection: sqlite3.Connection, mission_id: str, revision: int
    ) -> Plan:
        row = connection.execute(
            "SELECT plan_bytes, plan_sha256 FROM mission_plans "
            "WHERE mission_id = ? AND revision = ?",
            (mission_id, revision),
        ).fetchone()
        if row is None:
            raise MissionStoreError("mission plan is unavailable")
        plan = Plan.model_validate_json(row["plan_bytes"])
        digest = canonical_json_sha256(plan.model_dump(mode="json"))
        contract_rows = connection.execute(
            "SELECT event_bytes FROM mission_events WHERE mission_id = ? "
            "AND seq IN (3, 4) ORDER BY seq",
            (mission_id,),
        ).fetchall()
        contract_events = tuple(
            MissionEvent.model_validate_json(item["event_bytes"])
            for item in contract_rows
        )
        if (
            digest != row["plan_sha256"]
            or len(contract_events) != 2
            or contract_events[0].event_type != MissionEventType.PLAN_PROPOSED
            or contract_events[1].event_type != MissionEventType.PLAN_VALIDATED
            or contract_events[0].payload.get("plan_sha256") != digest
            or contract_events[1].payload.get("plan_sha256") != digest
            or contract_events[0].payload.get("plan_revision") != revision
            or contract_events[1].payload.get("plan_revision") != revision
            or contract_events[0].payload.get("task_count") != len(plan.tasks)
        ):
            raise MissionStoreError("mission plan digest does not match its content")
        return plan

    def _policy(
        self,
        connection: sqlite3.Connection,
        policy_id: str,
        revision: int,
        *,
        mission_id: str,
    ) -> tuple[ProjectPolicy, str]:
        row = connection.execute(
            "SELECT policy_bytes, policy_sha256 FROM mission_policies "
            "WHERE policy_id = ? AND revision = ?",
            (policy_id, revision),
        ).fetchone()
        if row is None:
            raise MissionStoreError("mission policy is unavailable")
        policy = ProjectPolicy.model_validate_json(row["policy_bytes"])
        digest = canonical_json_sha256(policy.model_dump(mode="json"))
        event_row = connection.execute(
            "SELECT event_bytes FROM mission_events WHERE mission_id = ? AND seq = 1",
            (mission_id,),
        ).fetchone()
        event = (
            None
            if event_row is None
            else MissionEvent.model_validate_json(event_row["event_bytes"])
        )
        if (
            digest != row["policy_sha256"]
            or event is None
            or event.event_type != MissionEventType.PROJECT_CREATED
            or event.payload
            != {
                "base_sha": policy.base_sha,
                "policy_id": policy.policy_id,
                "policy_revision": policy.revision,
                "policy_sha256": digest,
                "repo_id": policy.repo_id,
            }
        ):
            raise MissionStoreError("mission policy digest does not match its content")
        return policy, digest

    @staticmethod
    def _initial_mission(
        connection: sqlite3.Connection, mission_row: sqlite3.Row
    ) -> Mission:
        mission = Mission.model_validate_json(mission_row["mission_bytes"])
        event_row = connection.execute(
            "SELECT event_bytes FROM mission_events WHERE mission_id = ? AND seq = 2",
            (mission.mission_id,),
        ).fetchone()
        event = (
            None
            if event_row is None
            else MissionEvent.model_validate_json(event_row["event_bytes"])
        )
        if (
            event is None
            or event.event_type != MissionEventType.MISSION_CREATED
            or event.payload.get("mission_sha256")
            != canonical_json_sha256(mission.model_dump(mode="json"))
        ):
            raise MissionStoreError(
                "mission contract digest does not match its content"
            )
        return mission

    def _task_from_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> Task:
        plan = self._plan(connection, row["mission_id"], row["plan_revision"])
        expected = tuple(task for task in plan.tasks if task.task_id == row["task_id"])
        if len(expected) != 1:
            raise MissionStoreError("materialized task is absent from its bound plan")
        initial = Task.model_validate_json(row["task_bytes"])
        normalized = initial.model_copy(
            update={
                "assigned_role": expected[0].assigned_role,
                "priority": expected[0].priority,
            }
        )
        if (
            normalized != expected[0]
            or row["kind"] != expected[0].kind.value
            or row["attempt_limit"] != expected[0].attempt_limit
            or row["priority"] != initial.priority
        ):
            raise MissionStoreError(
                "materialized task contract differs from its bound plan"
            )
        mutation_sha256 = row["task_contract_event_sha256"]
        if initial != expected[0] or mutation_sha256 is not None:
            event_row = connection.execute(
                "SELECT event_bytes FROM mission_events WHERE mission_id = ? "
                "AND event_sha256 = ?",
                (row["mission_id"], mutation_sha256),
            ).fetchone()
            event = (
                None
                if event_row is None
                else MissionEvent.model_validate_json(event_row["event_bytes"])
            )
            if (
                event is None
                or event.event_type
                not in {
                    MissionEventType.OPERATOR_REASSIGNED,
                    MissionEventType.OPERATOR_REPRIORITIZED,
                }
                or event.payload.get("task_id") != initial.task_id
                or event.payload.get("task_sha256")
                != canonical_json_sha256(initial.model_dump(mode="json"))
                or event.payload.get("assigned_role") != initial.assigned_role
                or event.payload.get("priority") != initial.priority
            ):
                raise MissionStoreError(
                    "materialized task mutation lacks a committed operator event"
                )
        return Task.model_validate(
            {
                **initial.model_dump(mode="json"),
                "attempt_count": row["attempt_count"],
                "blocker": row["blocker"],
                "retry_at": row["retry_at"],
                "state": row["state"],
            }
        )

    def _task_row(
        self,
        connection: sqlite3.Connection,
        mission_id: str,
        revision: int,
        task_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM mission_tasks WHERE mission_id = ? AND plan_revision = ? "
            "AND task_id = ?",
            (mission_id, revision, task_id),
        ).fetchone()
        if row is None:
            raise MissionConflict("task is unavailable")
        return row

    @staticmethod
    def _update_task(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        task: Task,
        *,
        fencing_counter: int | None = None,
        accepted_attempt_id: str | None = None,
    ) -> None:
        connection.execute(
            "UPDATE mission_tasks SET state = ?, attempt_count = ?, retry_at = ?, "
            "blocker = ?, fencing_counter = ?, accepted_attempt_id = COALESCE(?, accepted_attempt_id) "
            "WHERE mission_id = ? AND plan_revision = ? AND task_id = ?",
            (
                task.state.value,
                task.attempt_count,
                None if task.retry_at is None else _iso(task.retry_at),
                task.blocker,
                row["fencing_counter"] if fencing_counter is None else fencing_counter,
                accepted_attempt_id,
                row["mission_id"],
                row["plan_revision"],
                row["task_id"],
            ),
        )

    def _assert_dispatch_materialization(
        self, connection: sqlite3.Connection, mission_id: str
    ) -> None:
        """Fail closed before dispatch if indexed state diverges from committed events."""

        mission_row = self._mission_row(connection, mission_id)
        initial_mission = self._initial_mission(connection, mission_row)
        revision = mission_row["plan_revision"]
        plan = self._plan(connection, mission_id, revision)
        task_rows = connection.execute(
            "SELECT * FROM mission_tasks WHERE mission_id = ? AND plan_revision = ? "
            "ORDER BY task_id",
            (mission_id, revision),
        ).fetchall()
        tasks = tuple(self._task_from_row(connection, row) for row in task_rows)
        gates = tuple(
            Gate.model_validate_json(row["gate_bytes"])
            for row in connection.execute(
                "SELECT gate_bytes FROM mission_gates WHERE mission_id = ? "
                "ORDER BY gate_id",
                (mission_id,),
            ).fetchall()
        )
        head = self._head(connection, mission_id)
        # ponytail: bounded replay is simplest for v1; persist a verified reducer
        # digest if missions outgrow Mission Control's 16,384-event ceiling.
        if head.seq > 16_384:
            raise MissionStoreError("mission exceeds the dispatch replay bound")
        events = tuple(
            MissionEvent.model_validate_json(row["event_bytes"])
            for row in connection.execute(
                "SELECT event_bytes FROM mission_events WHERE mission_id = ? ORDER BY seq",
                (mission_id,),
            ).fetchall()
        )
        try:
            reduced = reduce_events(initial_mission, plan.tasks, events)
        except TransitionError as error:
            raise MissionStoreError(
                "dispatch materialization failed committed event replay"
            ) from error
        requests = {
            str(event.payload.get("gate_id")): event
            for event in events
            if event.event_type == MissionEventType.GATE_REQUESTED
        }
        decisions = {
            str(event.payload.get("gate_id")): event
            for event in events
            if event.event_type == MissionEventType.GATE_DECIDED
        }
        gate_ids = {str(gate.gate_id) for gate in gates}
        gates_match = (
            len(requests)
            == sum(
                event.event_type == MissionEventType.GATE_REQUESTED for event in events
            )
            and len(decisions)
            == sum(
                event.event_type == MissionEventType.GATE_DECIDED for event in events
            )
            and set(requests) == gate_ids
            and set(decisions).issubset(gate_ids)
        )
        if gates_match:
            for gate in gates:
                gate_id = str(gate.gate_id)
                requested_gate = gate.model_copy(
                    update={
                        "operator_label": None,
                        "rationale": None,
                        "resolution": None,
                    }
                )
                request = requests[gate_id]
                decision = decisions.get(gate_id)
                if (
                    request.payload.get("gate_sha256")
                    != canonical_json_sha256(requested_gate.model_dump(mode="json"))
                    or request.references != gate.evidence
                    or (gate.resolution is None) != (decision is None)
                    or (
                        decision is not None
                        and (
                            decision.payload.get("gate_sha256")
                            != canonical_json_sha256(gate.model_dump(mode="json"))
                            or decision.payload.get("choice") != gate.resolution
                            or decision.references != gate.evidence
                        )
                    )
                ):
                    gates_match = False
                    break
        if (
            len(events) != head.event_count
            or (events[-1].event_sha256 if events else None) != head.event_sha256
            or reduced.status != MissionStatus(mission_row["status"])
            or reduced.task_states != {task.task_id: task.state for task in tasks}
            or reduced.attempt_counts
            != {task.task_id: task.attempt_count for task in tasks}
            or not gates_match
        ):
            raise MissionStoreError(
                "dispatch materialization does not match committed events"
            )

    def _dependencies_satisfied(
        self,
        connection: sqlite3.Connection,
        mission_id: str,
        revision: int,
        task: Task,
    ) -> bool:
        if not task.dependencies:
            return True
        dependency_rows = connection.execute(
            "SELECT dependency_id, satisfied_attempt_id FROM mission_dependencies "
            "WHERE mission_id = ? AND plan_revision = ? AND task_id = ?",
            (mission_id, revision, task.task_id),
        ).fetchall()
        if len(dependency_rows) != len(task.dependencies) or any(
            row["satisfied_attempt_id"] is None for row in dependency_rows
        ):
            return False
        for requirement in task.inputs:
            if (
                connection.execute(
                    "SELECT 1 FROM mission_publications WHERE mission_id = ? "
                    "AND plan_revision = ? AND task_id = ? AND output_name = ? "
                    "AND kind = ? AND state = ?",
                    (
                        mission_id,
                        revision,
                        requirement.producer_task_id,
                        requirement.name,
                        requirement.kind,
                        PublicationState.ACCEPTED.value,
                    ),
                ).fetchone()
                is None
            ):
                return False
        return True

    @staticmethod
    def _accepted_input_references(
        connection: sqlite3.Connection,
        mission_id: str,
        revision: int,
        task: Task,
    ) -> tuple[EvidenceReference, ...]:
        references: list[EvidenceReference] = []
        for requirement in task.inputs:
            row = connection.execute(
                "SELECT publication_bytes FROM mission_publications "
                "WHERE mission_id = ? AND plan_revision = ? AND task_id = ? "
                "AND output_name = ? AND kind = ? AND state = ?",
                (
                    mission_id,
                    revision,
                    requirement.producer_task_id,
                    requirement.name,
                    requirement.kind,
                    PublicationState.ACCEPTED.value,
                ),
            ).fetchone()
            if row is None:
                raise MissionConflict("accepted task input is unavailable")
            publication = ArtifactPublication.model_validate_json(
                row["publication_bytes"]
            )
            if task.task_id not in publication.consumers:
                raise MissionConflict("accepted task input does not name its consumer")
            references.append(
                EvidenceReference(
                    kind=publication.kind,
                    id=publication.publication_id,
                    sha256=publication.sha256,
                )
            )
        return tuple(
            sorted(references, key=lambda item: (item.kind, item.id, item.sha256))
        )

    def refresh_ready(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> tuple[str, ...]:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        request = {"mission_id": mission_id, "recorded_at": recorded_at.isoformat()}
        request_sha = self._request_sha256("refresh_ready", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    if existing.get("kind") != "task_ids":
                        raise MissionStoreError("stored ready result is invalid")
                    return tuple(existing["value"])
                self._assert_dispatch_materialization(connection, mission_id)
                mission_row = self._mission_row(connection, mission_id)
                if MissionStatus(mission_row["status"]) != MissionStatus.RUNNING:
                    raise MissionConflict("mission is not dispatchable")
                revision = mission_row["plan_revision"]
                rows = connection.execute(
                    "SELECT * FROM mission_tasks WHERE mission_id = ? AND plan_revision = ? "
                    "AND state IN (?, ?, ?) ORDER BY priority DESC, task_id",
                    (
                        mission_id,
                        revision,
                        TaskState.QUEUED.value,
                        TaskState.RETRYING.value,
                        TaskState.BLOCKED.value,
                    ),
                ).fetchall()
                ready: list[str] = []
                drafts: list[MissionEventInput] = []
                for row in rows:
                    task = self._task_from_row(connection, row)
                    if (
                        connection.execute(
                            "SELECT 1 FROM mission_gates WHERE mission_id = ? "
                            "AND task_id = ? AND resolution IS NULL",
                            (mission_id, task.task_id),
                        ).fetchone()
                        is not None
                    ):
                        continue
                    if task.retry_at is not None and task.retry_at > recorded_at:
                        continue
                    if not self._dependencies_satisfied(
                        connection, mission_id, revision, task
                    ):
                        continue
                    target = transition_task(task.state, TaskState.READY)
                    updated = Task.model_validate(
                        {
                            **task.model_dump(mode="json"),
                            "blocker": None,
                            "retry_at": None,
                            "state": target,
                        }
                    )
                    self._update_task(connection, row, updated)
                    ready.append(task.task_id)
                    drafts.append(
                        self._draft(
                            MissionEventType.TASK_READY,
                            {"state": target.value, "task_id": task.task_id},
                        )
                    )
                self._append(
                    connection, mission_id, command_id, tuple(drafts), recorded_at
                )
                result = {"kind": "task_ids", "value": ready}
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return tuple(ready)
            except Exception:
                connection.rollback()
                raise

    def ready_tasks(self, mission_id: str) -> tuple[Task, ...]:
        with closing(self._connect()) as connection:
            mission_row = self._mission_row(connection, mission_id)
            rows = connection.execute(
                "SELECT * FROM mission_tasks WHERE mission_id = ? AND plan_revision = ? "
                "AND state = ? ORDER BY priority DESC, task_id",
                (mission_id, mission_row["plan_revision"], TaskState.READY.value),
            ).fetchall()
            return tuple(self._task_from_row(connection, row) for row in rows)

    @staticmethod
    def _reserved_worker_seconds(
        connection: sqlite3.Connection,
        mission_id: str,
        *,
        replacement_attempt_id: str | None = None,
        replacement_expires_at: datetime | None = None,
    ) -> float:
        rows = connection.execute(
            "SELECT a.attempt_bytes, l.lease_bytes FROM mission_attempts a "
            "LEFT JOIN mission_leases l ON l.attempt_id = a.attempt_id "
            "WHERE a.mission_id = ?",
            (mission_id,),
        ).fetchall()
        total = 0.0
        for row in rows:
            attempt = Attempt.model_validate_json(row["attempt_bytes"])
            if attempt.ended_at is not None:
                until = attempt.ended_at
            else:
                if row["lease_bytes"] is None:
                    raise MissionStoreError("running attempt lease is unavailable")
                lease = Lease.model_validate_json(row["lease_bytes"])
                until = (
                    replacement_expires_at
                    if attempt.attempt_id == replacement_attempt_id
                    else lease.expires_at
                )
            if until is None or until < attempt.started_at:
                raise MissionStoreError("mission worker-time interval is invalid")
            total += (until - attempt.started_at).total_seconds()
        return total

    def claim_task(
        self,
        mission_id: str,
        task_id: str,
        worker_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        ttl_seconds: int,
    ) -> Dispatch:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3_600:
            raise ValueError("lease TTL must be between 1 and 3600 seconds")
        request = {
            "mission_id": mission_id,
            "task_id": task_id,
            "worker_id": worker_id,
            "recorded_at": recorded_at.isoformat(),
            "ttl_seconds": ttl_seconds,
        }
        request_sha = self._request_sha256("claim_task", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    if existing.get("kind") != "dispatch":
                        raise MissionStoreError("stored dispatch result is invalid")
                    return Dispatch.model_validate(existing["value"])
                self._assert_dispatch_materialization(connection, mission_id)
                mission_row = self._mission_row(connection, mission_id)
                if MissionStatus(mission_row["status"]) != MissionStatus.RUNNING:
                    raise LeaseConflict("mission is not dispatchable")
                revision = mission_row["plan_revision"]
                mission_contract = Mission.model_validate_json(
                    mission_row["mission_bytes"]
                )
                attempt_count = connection.execute(
                    "SELECT COUNT(*) FROM mission_attempts WHERE mission_id = ?",
                    (mission_id,),
                ).fetchone()[0]
                if attempt_count >= mission_contract.resource_budget.max_attempts:
                    raise LeaseConflict("mission attempt budget is exhausted")
                worker_seconds = self._reserved_worker_seconds(connection, mission_id)
                if (
                    worker_seconds + ttl_seconds
                    > mission_contract.resource_budget.max_worker_seconds
                ):
                    raise LeaseConflict("mission worker-time budget is exhausted")
                plan = self._plan(connection, mission_id, revision)
                active_count = connection.execute(
                    "SELECT COUNT(*) FROM mission_leases WHERE mission_id = ? "
                    "AND plan_revision = ? AND released_at IS NULL AND expires_at > ?",
                    (mission_id, revision, _iso(recorded_at)),
                ).fetchone()[0]
                if active_count >= plan.max_concurrency:
                    raise LeaseConflict("mission concurrency is exhausted")
                row = self._task_row(connection, mission_id, revision, task_id)
                task = self._task_from_row(connection, row)
                if task.state != TaskState.READY:
                    raise LeaseConflict("task is not ready")
                if (
                    connection.execute(
                        "SELECT 1 FROM mission_gates WHERE mission_id = ? "
                        "AND task_id = ? AND resolution IS NULL",
                        (mission_id, task_id),
                    ).fetchone()
                    is not None
                ):
                    raise LeaseConflict("task has an unresolved gate")
                active = connection.execute(
                    "SELECT lease_bytes FROM mission_leases WHERE mission_id = ? "
                    "AND plan_revision = ? AND released_at IS NULL AND expires_at > ?",
                    (mission_id, revision, _iso(recorded_at)),
                ).fetchall()
                for lease_row in active:
                    lease = Lease.model_validate_json(lease_row["lease_bytes"])
                    if set(task.write_paths) & set(lease.write_paths):
                        raise LeaseConflict(
                            "task write scope conflicts with an active lease"
                        )
                if task.attempt_count >= task.attempt_limit:
                    raise LeaseConflict("task attempt limit is exhausted")

                input_publications = self._accepted_input_references(
                    connection, mission_id, revision, task
                )

                number = task.attempt_count + 1
                token = row["fencing_counter"] + 1
                namespace = f"{mission_id}\0{revision}\0{task_id}\0{number}\0{token}"
                digest = canonical_json_sha256(namespace)
                attempt_id = f"attempt_{digest[:32]}"
                lease_id = f"lease_{digest[:32]}"
                workspace_id = f"workspace_{digest[:24]}"
                dispatch_command_id = f"dispatch_{digest[:32]}"
                expires_at = recorded_at + timedelta(seconds=ttl_seconds)
                target = (
                    TaskState.VERIFYING
                    if task.kind == TaskKind.VERIFICATION
                    else TaskState.RUNNING
                )
                transition_task(task.state, target)
                updated_task = Task.model_validate(
                    {
                        **task.model_dump(mode="json"),
                        "attempt_count": number,
                        "state": target,
                    }
                )
                attempt = Attempt(
                    attempt_id=attempt_id,
                    mission_id=mission_id,
                    plan_revision=revision,
                    task_id=task_id,
                    attempt_number=number,
                    worker_id=worker_id,
                    workspace_id=workspace_id,
                    lease_id=lease_id,
                    fencing_token=token,
                    dispatch_command_id=dispatch_command_id,
                    state=AttemptState.RUNNING,
                    started_at=recorded_at,
                    input_publications=input_publications,
                )
                lease = Lease(
                    lease_id=lease_id,
                    mission_id=mission_id,
                    plan_revision=revision,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    owner=worker_id,
                    write_paths=task.write_paths,
                    fencing_token=token,
                    issued_at=recorded_at,
                    heartbeat_at=recorded_at,
                    expires_at=expires_at,
                )
                connection.execute(
                    "INSERT INTO mission_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt_id,
                        mission_id,
                        revision,
                        task_id,
                        number,
                        attempt.state.value,
                        dispatch_command_id,
                        _json_bytes(attempt),
                    ),
                )
                connection.execute(
                    "INSERT INTO mission_leases VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                    (
                        lease_id,
                        mission_id,
                        revision,
                        task_id,
                        attempt_id,
                        worker_id,
                        token,
                        _iso(expires_at),
                        _json_bytes(lease),
                    ),
                )
                self._update_task(connection, row, updated_task, fencing_counter=token)
                drafts = [
                    self._draft(
                        MissionEventType.TASK_LEASED,
                        {
                            "attempt_id": attempt_id,
                            "attempt_number": number,
                            "fencing_token": token,
                            "lease_id": lease_id,
                            "task_id": task_id,
                            "worker_id": worker_id,
                        },
                    ),
                    self._draft(
                        MissionEventType.TASK_STARTED,
                        {
                            "attempt_id": attempt_id,
                            "state": target.value,
                            "task_id": task_id,
                            "worker_id": worker_id,
                        },
                    ),
                ]
                if task.kind == TaskKind.ASSEMBLY:
                    drafts.append(
                        self._draft(
                            MissionEventType.ASSEMBLY_STARTED,
                            {"attempt_id": attempt_id, "task_id": task_id},
                        )
                    )
                elif task.kind == TaskKind.VERIFICATION:
                    drafts.append(
                        self._draft(
                            MissionEventType.VERIFICATION_STARTED,
                            {"attempt_id": attempt_id, "task_id": task_id},
                        )
                    )
                self._append(
                    connection, mission_id, command_id, tuple(drafts), recorded_at
                )
                dispatch = Dispatch(
                    mission_id=mission_id,
                    plan_revision=revision,
                    task_id=task_id,
                    task_kind=task.kind,
                    attempt_id=attempt_id,
                    attempt_number=number,
                    worker_id=worker_id,
                    workspace_id=workspace_id,
                    lease_id=lease_id,
                    fencing_token=token,
                    dispatch_command_id=dispatch_command_id,
                    write_paths=task.write_paths,
                    allowed_commands=task.allowed_commands,
                    acceptance_checks=task.acceptance_checks,
                    input_publications=input_publications,
                    expires_at=expires_at,
                )
                result = {"kind": "dispatch", "value": dispatch.model_dump(mode="json")}
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return dispatch
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _attempt_and_lease(
        connection: sqlite3.Connection, attempt_id: str
    ) -> tuple[Attempt, Lease]:
        attempt_row = connection.execute(
            "SELECT attempt_bytes FROM mission_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        lease_row = connection.execute(
            "SELECT lease_bytes FROM mission_leases WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if attempt_row is None or lease_row is None:
            raise StaleWorker("attempt lease is unavailable")
        return (
            Attempt.model_validate_json(attempt_row["attempt_bytes"]),
            Lease.model_validate_json(lease_row["lease_bytes"]),
        )

    @staticmethod
    def _require_fresh(
        attempt: Attempt,
        lease: Lease,
        *,
        owner: str,
        lease_id: str,
        fencing_token: int,
        recorded_at: datetime,
    ) -> None:
        if (
            attempt.state != AttemptState.RUNNING
            or type(fencing_token) is not int
            or fencing_token < 1
            or lease.released_at is not None
            or lease.lease_id != lease_id
            or lease.owner != owner
            or lease.fencing_token != fencing_token
            or attempt.fencing_token != fencing_token
            or recorded_at < lease.heartbeat_at
            or recorded_at >= lease.expires_at
        ):
            raise StaleWorker("worker lease is stale or expired")

    def heartbeat(
        self,
        mission_id: str,
        attempt_id: str,
        owner: str,
        lease_id: str,
        fencing_token: int,
        command_id: str,
        *,
        recorded_at: datetime,
        ttl_seconds: int,
    ) -> Lease:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3_600:
            raise ValueError("lease TTL must be between 1 and 3600 seconds")
        request = {
            "attempt_id": attempt_id,
            "fencing_token": fencing_token,
            "lease_id": lease_id,
            "owner": owner,
            "recorded_at": recorded_at.isoformat(),
            "ttl_seconds": ttl_seconds,
        }
        request_sha = self._request_sha256("heartbeat", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    if existing.get("kind") != "lease":
                        raise MissionStoreError("stored heartbeat result is invalid")
                    return Lease.model_validate(existing["value"])
                attempt, lease = self._attempt_and_lease(connection, attempt_id)
                if attempt.mission_id != mission_id:
                    raise StaleWorker("attempt belongs to another mission")
                self._require_fresh(
                    attempt,
                    lease,
                    owner=owner,
                    lease_id=lease_id,
                    fencing_token=fencing_token,
                    recorded_at=recorded_at,
                )
                proposed_expiry = recorded_at + timedelta(seconds=ttl_seconds)
                mission_row = self._mission_row(connection, mission_id)
                mission_contract = Mission.model_validate_json(
                    mission_row["mission_bytes"]
                )
                reserved = self._reserved_worker_seconds(
                    connection,
                    mission_id,
                    replacement_attempt_id=attempt_id,
                    replacement_expires_at=proposed_expiry,
                )
                if reserved > mission_contract.resource_budget.max_worker_seconds:
                    raise LeaseConflict("mission worker-time budget is exhausted")
                updated = Lease.model_validate(
                    {
                        **lease.model_dump(mode="json"),
                        "heartbeat_at": recorded_at,
                        "expires_at": proposed_expiry,
                    }
                )
                connection.execute(
                    "UPDATE mission_leases SET expires_at = ?, lease_bytes = ? "
                    "WHERE lease_id = ? AND released_at IS NULL",
                    (_iso(updated.expires_at), _json_bytes(updated), lease_id),
                )
                self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            MissionEventType.TASK_HEARTBEAT,
                            {
                                "attempt_id": attempt_id,
                                "fencing_token": fencing_token,
                                "lease_id": lease_id,
                                "task_id": attempt.task_id,
                                "worker_id": owner,
                            },
                            truth_kind=TruthKind.RUNTIME_OBSERVED,
                            authority=MissionAuthority.WORKER_ADAPTER,
                        ),
                    ),
                    recorded_at,
                )
                result = {"kind": "lease", "value": updated.model_dump(mode="json")}
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _release_lease(
        connection: sqlite3.Connection,
        lease: Lease,
        recorded_at: datetime,
        reason: str,
    ) -> Lease:
        released = Lease.model_validate(
            {
                **lease.model_dump(mode="json"),
                "released_at": recorded_at,
                "release_reason": reason,
            }
        )
        connection.execute(
            "UPDATE mission_leases SET released_at = ?, lease_bytes = ? WHERE lease_id = ?",
            (_iso(recorded_at), _json_bytes(released), lease.lease_id),
        )
        return released

    @staticmethod
    def _update_attempt(connection: sqlite3.Connection, attempt: Attempt) -> None:
        connection.execute(
            "UPDATE mission_attempts SET state = ?, attempt_bytes = ? WHERE attempt_id = ?",
            (attempt.state.value, _json_bytes(attempt), attempt.attempt_id),
        )

    def _require_attempt_evidence(
        self, attempt: Attempt, result: AttemptResult
    ) -> dict[tuple[str, str, str], bytes]:
        if result.evidence_link is None:
            if result.evidence_refs or result.publications:
                raise MissionConflict("attempt evidence link is unavailable")
            return {}
        if self.artifact_resolver is None:
            raise MissionConflict("attempt artifact resolver is unavailable")
        if isinstance(result.evidence_link, GenericEvidenceLink):
            verifier = getattr(self.artifact_resolver, "verify_attempt", None)
            if not callable(verifier) or not verifier(
                result.evidence_link.evidence_id,
                mission_id=attempt.mission_id,
                task_id=attempt.task_id,
                attempt_id=attempt.attempt_id,
                succeeded=result.succeeded,
                references=result.evidence_refs,
            ):
                raise MissionConflict("generic attempt evidence is not completed")
        elif isinstance(result.evidence_link, LegacyEvidenceLink):
            verifier = getattr(self.artifact_resolver, "verify_legacy_attempt", None)
            if not callable(verifier) or not verifier(
                result.evidence_link.run_id,
                mission_id=attempt.mission_id,
                task_id=attempt.task_id,
                attempt_id=attempt.attempt_id,
                succeeded=result.succeeded,
                references=result.evidence_refs,
            ):
                raise MissionConflict("legacy attempt evidence is not valid")
        contents: dict[tuple[str, str, str], bytes] = {}
        for reference in result.evidence_refs:
            content = self.artifact_resolver.resolve(reference.kind, reference.id)
            if content is None or sha256_hex(content) != reference.sha256:
                raise MissionConflict("attempt evidence artifact is unavailable")
            contents[(reference.kind, reference.id, reference.sha256)] = content
        for publication in result.publications:
            matches = tuple(
                reference
                for reference in result.evidence_refs
                if reference.kind == publication.kind
                and reference.sha256 == publication.sha256
            )
            if len(matches) != 1:
                raise MissionConflict(
                    "each publication requires one exact attempt artifact reference"
                )
        return contents

    @staticmethod
    def _require_bound_check_receipt(
        task: Task,
        attempt: Attempt,
        contents: dict[tuple[str, str, str], bytes],
    ) -> None:
        receipts = tuple(
            content
            for (kind, _artifact_id, _sha256), content in contents.items()
            if kind == "test-receipt"
        )
        if len(receipts) != 1:
            raise MissionConflict("successful attempt requires one test receipt")
        try:
            receipt = json.loads(receipts[0])
        except (TypeError, ValueError, UnicodeDecodeError) as error:
            raise MissionConflict("attempt test receipt is invalid") from error
        expected_inputs = [item.sha256 for item in attempt.input_publications]
        accepted_inputs = (
            receipt.get("accepted_input_sha256") if isinstance(receipt, dict) else None
        )
        if (
            not isinstance(receipt, dict)
            or canonical_json_bytes(receipt) != receipts[0]
            or not isinstance(accepted_inputs, list)
            or len(accepted_inputs) != len(expected_inputs)
            or any(not isinstance(item, str) for item in accepted_inputs)
            or sorted(accepted_inputs) != sorted(expected_inputs)
            or receipt.get("template_id") not in task.acceptance_checks
            or type(receipt.get("exit_code")) is not int
            or receipt.get("exit_code") != 0
            or receipt.get("timed_out") is not False
        ):
            raise MissionConflict(
                "attempt test receipt is not bound to accepted inputs"
            )
        if task.kind == TaskKind.VERIFICATION and (
            len(expected_inputs) != 1
            or receipt.get("candidate_patch_sha256") != expected_inputs[0]
        ):
            raise MissionConflict("verification receipt is not bound to the candidate")

    def _artifact_bytes_used(
        self,
        connection: sqlite3.Connection,
        mission_id: str,
        new_contents: dict[tuple[str, str, str], bytes],
    ) -> int:
        # ponytail: bounded mission scan; materialize unique-byte totals if the
        # validated 50-task ceiling becomes a measured completion bottleneck.
        contents = dict(new_contents)
        rows = connection.execute(
            "SELECT attempt_bytes FROM mission_attempts WHERE mission_id = ?",
            (mission_id,),
        ).fetchall()
        for row in rows:
            attempt = Attempt.model_validate_json(row["attempt_bytes"])
            for reference in attempt.evidence_refs:
                key = (reference.kind, reference.id, reference.sha256)
                if key in contents:
                    continue
                if self.artifact_resolver is None:
                    raise MissionStoreError(
                        "stored attempt artifact resolver is unavailable"
                    )
                content = self.artifact_resolver.resolve(reference.kind, reference.id)
                if content is None or sha256_hex(content) != reference.sha256:
                    raise MissionStoreError("stored attempt artifact is unavailable")
                contents[key] = content
        return sum(len(content) for content in contents.values())

    def complete_attempt(
        self,
        mission_id: str,
        attempt_id: str,
        owner: str,
        lease_id: str,
        fencing_token: int,
        result: AttemptResult,
        command_id: str,
        *,
        recorded_at: datetime,
        retry_backoff_seconds: int,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        if (
            type(retry_backoff_seconds) is not int
            or not 0 <= retry_backoff_seconds <= 3_600
        ):
            raise ValueError("retry backoff must be between 0 and 3600 seconds")
        request = {
            "attempt_id": attempt_id,
            "fencing_token": fencing_token,
            "lease_id": lease_id,
            "owner": owner,
            "recorded_at": recorded_at.isoformat(),
            "result": result.model_dump(mode="json"),
            "retry_backoff_seconds": retry_backoff_seconds,
        }
        request_sha = self._request_sha256("complete_attempt", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                attempt, lease = self._attempt_and_lease(connection, attempt_id)
                if attempt.mission_id != mission_id:
                    raise StaleWorker("attempt belongs to another mission")
                self._require_fresh(
                    attempt,
                    lease,
                    owner=owner,
                    lease_id=lease_id,
                    fencing_token=fencing_token,
                    recorded_at=recorded_at,
                )
                task_row = self._task_row(
                    connection, mission_id, attempt.plan_revision, attempt.task_id
                )
                task = self._task_from_row(connection, task_row)
                if isinstance(result.evidence_link, LegacyEvidenceLink) and (
                    task.evidence_adapter != "legacy_auth_v2"
                ):
                    raise MissionConflict(
                        "legacy v2 evidence is not valid for this task"
                    )
                if isinstance(result.evidence_link, GenericEvidenceLink) and (
                    task.evidence_adapter != "generic_v1"
                ):
                    raise MissionConflict("generic evidence is not valid for this task")
                contents = self._require_attempt_evidence(attempt, result)
                drafts: list[MissionEventInput] = []

                if result.succeeded:
                    expected = {
                        (item.name, item.kind): item for item in task.expected_outputs
                    }
                    actual = {
                        (item.output_name, item.kind): item
                        for item in result.publications
                    }
                    if set(actual) != set(expected):
                        raise MissionConflict(
                            "attempt publications do not match task outputs"
                        )
                    if any(
                        actual[key].paths != expected[key].paths for key in expected
                    ):
                        raise MissionConflict("attempt publication paths changed")
                    self._require_bound_check_receipt(task, attempt, contents)
                    mission_contract = Mission.model_validate_json(
                        self._mission_row(connection, mission_id)["mission_bytes"]
                    )
                    if (
                        self._artifact_bytes_used(connection, mission_id, contents)
                        > mission_contract.resource_budget.max_artifact_bytes
                    ):
                        raise MissionConflict("mission artifact budget is exhausted")
                    publication_models: list[ArtifactPublication] = []
                    for key in sorted(actual):
                        publication = actual[key]
                        publication_id = (
                            "publication_"
                            + canonical_json_sha256(
                                {
                                    "attempt_id": attempt_id,
                                    "kind": publication.kind,
                                    "output_name": publication.output_name,
                                    "sha256": publication.sha256,
                                }
                            )[:32]
                        )
                        consumer_rows = connection.execute(
                            "SELECT task_id, task_bytes FROM mission_tasks WHERE mission_id = ? "
                            "AND plan_revision = ? ORDER BY task_id",
                            (mission_id, attempt.plan_revision),
                        ).fetchall()
                        consumers = tuple(
                            row["task_id"]
                            for row in consumer_rows
                            if any(
                                item.producer_task_id == task.task_id
                                and item.name == publication.output_name
                                and item.kind == publication.kind
                                for item in Task.model_validate_json(
                                    row["task_bytes"]
                                ).inputs
                            )
                        )
                        accepted = ArtifactPublication(
                            **publication.model_dump(mode="json"),
                            publication_id=publication_id,
                            mission_id=mission_id,
                            plan_revision=attempt.plan_revision,
                            task_id=task.task_id,
                            attempt_id=attempt_id,
                            state=PublicationState.ACCEPTED,
                            consumers=consumers,
                        )
                        connection.execute(
                            "INSERT INTO mission_publications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                publication_id,
                                mission_id,
                                attempt.plan_revision,
                                task.task_id,
                                attempt_id,
                                accepted.output_name,
                                accepted.kind,
                                accepted.state.value,
                                _json_bytes(accepted),
                            ),
                        )
                        publication_models.append(accepted)
                        reference = EvidenceReference(
                            kind=accepted.kind,
                            id=publication_id,
                            sha256=accepted.sha256,
                        )
                        common = {
                            "attempt_id": attempt_id,
                            "kind": accepted.kind,
                            "output_name": accepted.output_name,
                            "publication_id": publication_id,
                            "sha256": accepted.sha256,
                            "task_id": task.task_id,
                        }
                        drafts.extend(
                            (
                                self._draft(
                                    MissionEventType.ARTIFACT_PUBLISHED,
                                    {**common, "status": "published"},
                                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                                    authority=MissionAuthority.WORKER_ADAPTER,
                                    references=(reference,),
                                ),
                                self._draft(
                                    MissionEventType.ARTIFACT_ACCEPTED,
                                    {**common, "status": "accepted"},
                                    truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                                    authority=MissionAuthority.POLICY_ENGINE,
                                    references=(reference,),
                                ),
                            )
                        )

                    committed = Attempt.model_validate(
                        {
                            **attempt.model_dump(mode="json"),
                            "ended_at": recorded_at,
                            "evidence_link": result.evidence_link,
                            "evidence_refs": result.evidence_refs,
                            "result_code": result.result_code,
                            "state": AttemptState.COMMITTED,
                        }
                    )
                    self._update_attempt(connection, committed)
                    self._release_lease(connection, lease, recorded_at, "completed")
                    target = transition_task(task.state, TaskState.DONE)
                    completed_task = Task.model_validate(
                        {**task.model_dump(mode="json"), "state": target}
                    )
                    self._update_task(
                        connection,
                        task_row,
                        completed_task,
                        accepted_attempt_id=attempt_id,
                    )
                    drafts.append(
                        self._draft(
                            MissionEventType.TASK_COMPLETED,
                            {
                                "attempt_id": attempt_id,
                                "evidence_kind": result.evidence_link.kind,
                                "result_code": result.result_code,
                                "state": target.value,
                                "task_id": task.task_id,
                            },
                        )
                    )
                    if task.kind == TaskKind.ASSEMBLY:
                        drafts.append(
                            self._draft(
                                MissionEventType.ASSEMBLY_COMPLETED,
                                {"attempt_id": attempt_id, "task_id": task.task_id},
                            )
                        )
                    elif task.kind == TaskKind.VERIFICATION:
                        drafts.append(
                            self._draft(
                                MissionEventType.VERIFICATION_COMPLETED,
                                {"attempt_id": attempt_id, "task_id": task.task_id},
                            )
                        )
                    dependents = connection.execute(
                        "SELECT task_id FROM mission_dependencies WHERE mission_id = ? "
                        "AND plan_revision = ? AND dependency_id = ? ORDER BY task_id",
                        (mission_id, attempt.plan_revision, task.task_id),
                    ).fetchall()
                    for dependent in dependents:
                        connection.execute(
                            "UPDATE mission_dependencies SET satisfied_attempt_id = ? "
                            "WHERE mission_id = ? AND plan_revision = ? AND task_id = ? "
                            "AND dependency_id = ? AND satisfied_attempt_id IS NULL",
                            (
                                attempt_id,
                                mission_id,
                                attempt.plan_revision,
                                dependent["task_id"],
                                task.task_id,
                            ),
                        )
                        drafts.append(
                            self._draft(
                                MissionEventType.DEPENDENCY_SATISFIED,
                                {
                                    "attempt_id": attempt_id,
                                    "dependency_id": task.task_id,
                                    "task_id": dependent["task_id"],
                                },
                            )
                        )
                else:
                    if result.publications:
                        raise MissionConflict("failed attempts cannot publish outputs")
                    failed = Attempt.model_validate(
                        {
                            **attempt.model_dump(mode="json"),
                            "ended_at": recorded_at,
                            "evidence_link": result.evidence_link,
                            "evidence_refs": result.evidence_refs,
                            "result_code": result.result_code,
                            "state": AttemptState.FAILED,
                        }
                    )
                    self._update_attempt(connection, failed)
                    self._release_lease(connection, lease, recorded_at, "failed")
                    if result.retryable and task.attempt_count < task.attempt_limit:
                        target = transition_task(task.state, TaskState.RETRYING)
                        retry_at = recorded_at + timedelta(
                            seconds=retry_backoff_seconds
                        )
                        retried = Task.model_validate(
                            {
                                **task.model_dump(mode="json"),
                                "retry_at": retry_at,
                                "state": target,
                            }
                        )
                        self._update_task(connection, task_row, retried)
                        drafts.append(
                            self._draft(
                                MissionEventType.TASK_RETRIED,
                                {
                                    "attempt_id": attempt_id,
                                    "result_code": result.result_code,
                                    "retry_at": retry_at.isoformat(),
                                    "state": target.value,
                                    "task_id": task.task_id,
                                },
                            )
                        )
                    else:
                        target = transition_task(task.state, TaskState.FAILED)
                        failed_task = Task.model_validate(
                            {**task.model_dump(mode="json"), "state": target}
                        )
                        self._update_task(connection, task_row, failed_task)
                        drafts.append(
                            self._draft(
                                MissionEventType.TASK_FAILED,
                                {
                                    "attempt_id": attempt_id,
                                    "result_code": result.result_code,
                                    "state": target.value,
                                    "task_id": task.task_id,
                                },
                            )
                        )
                        kind_event = {
                            TaskKind.ASSEMBLY: MissionEventType.ASSEMBLY_FAILED,
                            TaskKind.VERIFICATION: MissionEventType.VERIFICATION_FAILED,
                        }.get(task.kind)
                        if kind_event is not None:
                            drafts.append(
                                self._draft(
                                    kind_event,
                                    {
                                        "attempt_id": attempt_id,
                                        "result_code": result.result_code,
                                        "task_id": task.task_id,
                                    },
                                )
                            )
                        mission_row = self._mission_row(connection, mission_id)
                        current = MissionStatus(mission_row["status"])
                        if current not in {
                            MissionStatus.FAILED,
                            MissionStatus.CANCELLED,
                        }:
                            target_status = transition_mission(
                                current, MissionStatus.FAILED
                            )
                            connection.execute(
                                "UPDATE missions SET status = ? WHERE mission_id = ?",
                                (target_status.value, mission_id),
                            )

                head = self._append(
                    connection, mission_id, command_id, tuple(drafts), recorded_at
                )
                result_record = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result_record
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def expire_leases(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        retry_backoff_seconds: int,
    ) -> tuple[str, ...]:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        if (
            type(retry_backoff_seconds) is not int
            or not 0 <= retry_backoff_seconds <= 3_600
        ):
            raise ValueError("retry backoff must be between 0 and 3600 seconds")
        request = {
            "mission_id": mission_id,
            "recorded_at": recorded_at.isoformat(),
            "retry_backoff_seconds": retry_backoff_seconds,
        }
        request_sha = self._request_sha256("expire_leases", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    if existing.get("kind") != "attempt_ids":
                        raise MissionStoreError("stored expiry result is invalid")
                    return tuple(existing["value"])
                mission_row = self._mission_row(connection, mission_id)
                rows = connection.execute(
                    "SELECT lease_bytes FROM mission_leases WHERE mission_id = ? "
                    "AND released_at IS NULL AND expires_at <= ? ORDER BY task_id",
                    (mission_id, _iso(recorded_at)),
                ).fetchall()
                expired: list[str] = []
                drafts: list[MissionEventInput] = []
                mission_failed = False
                for row in rows:
                    lease = Lease.model_validate_json(row["lease_bytes"])
                    attempt, _ = self._attempt_and_lease(connection, lease.attempt_id)
                    if attempt.state != AttemptState.RUNNING:
                        raise MissionStoreError("active lease attempt is not running")
                    abandoned = Attempt.model_validate(
                        {
                            **attempt.model_dump(mode="json"),
                            "ended_at": recorded_at,
                            "result_code": "lease_expired",
                            "state": AttemptState.ABANDONED,
                        }
                    )
                    self._update_attempt(connection, abandoned)
                    self._release_lease(connection, lease, recorded_at, "expired")
                    task_row = self._task_row(
                        connection,
                        mission_id,
                        attempt.plan_revision,
                        attempt.task_id,
                    )
                    task = self._task_from_row(connection, task_row)
                    if task.attempt_count < task.attempt_limit:
                        target = transition_task(task.state, TaskState.RETRYING)
                        retry_at = recorded_at + timedelta(
                            seconds=retry_backoff_seconds
                        )
                        updated = Task.model_validate(
                            {
                                **task.model_dump(mode="json"),
                                "retry_at": retry_at,
                                "state": target,
                            }
                        )
                        event_type = MissionEventType.TASK_RETRIED
                        payload = {
                            "attempt_id": attempt.attempt_id,
                            "result_code": "lease_expired",
                            "retry_at": retry_at.isoformat(),
                            "state": target.value,
                            "task_id": task.task_id,
                        }
                    else:
                        target = transition_task(task.state, TaskState.FAILED)
                        updated = Task.model_validate(
                            {**task.model_dump(mode="json"), "state": target}
                        )
                        event_type = MissionEventType.TASK_FAILED
                        payload = {
                            "attempt_id": attempt.attempt_id,
                            "result_code": "lease_expired",
                            "state": target.value,
                            "task_id": task.task_id,
                        }
                        mission_failed = True
                    self._update_task(connection, task_row, updated)
                    expired.append(attempt.attempt_id)
                    drafts.append(self._draft(event_type, payload))
                if mission_failed:
                    current = MissionStatus(mission_row["status"])
                    if current not in {MissionStatus.FAILED, MissionStatus.CANCELLED}:
                        target = transition_mission(current, MissionStatus.FAILED)
                        connection.execute(
                            "UPDATE missions SET status = ? WHERE mission_id = ?",
                            (target.value, mission_id),
                        )
                self._append(
                    connection, mission_id, command_id, tuple(drafts), recorded_at
                )
                result = {"kind": "attempt_ids", "value": expired}
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return tuple(expired)
            except Exception:
                connection.rollback()
                raise

    def recover_dispatches(
        self, mission_id: str, *, recorded_at: datetime
    ) -> tuple[Dispatch, ...]:
        recorded_at = self._time(recorded_at)
        with closing(self._connect()) as connection:
            self._mission_row(connection, mission_id)
            rows = connection.execute(
                "SELECT a.attempt_bytes, l.lease_bytes, t.task_bytes "
                "FROM mission_attempts a JOIN mission_leases l ON l.attempt_id = a.attempt_id "
                "JOIN mission_tasks t ON t.mission_id = a.mission_id "
                "AND t.plan_revision = a.plan_revision AND t.task_id = a.task_id "
                "WHERE a.mission_id = ? AND a.state = ? AND l.released_at IS NULL "
                "AND l.expires_at > ? ORDER BY a.task_id",
                (mission_id, AttemptState.RUNNING.value, _iso(recorded_at)),
            ).fetchall()
        result: list[Dispatch] = []
        for row in rows:
            attempt = Attempt.model_validate_json(row["attempt_bytes"])
            lease = Lease.model_validate_json(row["lease_bytes"])
            task = Task.model_validate_json(row["task_bytes"])
            result.append(
                Dispatch(
                    mission_id=mission_id,
                    plan_revision=attempt.plan_revision,
                    task_id=task.task_id,
                    task_kind=task.kind,
                    attempt_id=attempt.attempt_id,
                    attempt_number=attempt.attempt_number,
                    worker_id=attempt.worker_id,
                    workspace_id=attempt.workspace_id,
                    lease_id=lease.lease_id,
                    fencing_token=lease.fencing_token,
                    dispatch_command_id=attempt.dispatch_command_id,
                    write_paths=task.write_paths,
                    allowed_commands=task.allowed_commands,
                    acceptance_checks=task.acceptance_checks,
                    input_publications=attempt.input_publications,
                    expires_at=lease.expires_at,
                )
            )
        return tuple(result)

    def pause(
        self,
        mission_id: str,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        return self._mission_status_command(
            mission_id,
            command_id,
            recorded_at=recorded_at,
            operation="pause",
            expected=MissionStatus.RUNNING,
            target=MissionStatus.PAUSED,
            event_type=MissionEventType.OPERATOR_PAUSED,
            payload={
                "operator_label": operator_label,
                "operator_rationale": rationale,
                "status": "paused",
            },
            truth_kind=truth_kind,
            authority=self._authority_for_truth(truth_kind),
        )

    def resume(
        self,
        mission_id: str,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        return self._mission_status_command(
            mission_id,
            command_id,
            recorded_at=recorded_at,
            operation="resume",
            expected=MissionStatus.PAUSED,
            target=MissionStatus.RUNNING,
            event_type=MissionEventType.OPERATOR_RESUMED,
            payload={
                "operator_label": operator_label,
                "operator_rationale": rationale,
                "status": "running",
            },
            truth_kind=truth_kind,
            authority=self._authority_for_truth(truth_kind),
        )

    def request_replan(
        self,
        mission_id: str,
        command_id: str,
        *,
        reason: str,
        operator_label: str,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        self._validate_operator_truth(truth_kind, operator_label, reason)
        request = {
            "operator_label": operator_label,
            "reason": reason,
            "truth_kind": truth_kind.value,
        }
        request_sha = self._request_sha256("request_replan", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                current = MissionStatus(mission_row["status"])
                if current not in {MissionStatus.RUNNING, MissionStatus.PAUSED}:
                    raise MissionConflict("mission cannot request a replan now")
                if current == MissionStatus.RUNNING:
                    transition_mission(current, MissionStatus.PAUSED)
                    connection.execute(
                        "UPDATE missions SET status = ? WHERE mission_id = ?",
                        (MissionStatus.PAUSED.value, mission_id),
                    )
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            MissionEventType.OPERATOR_REPLAN_REQUESTED,
                            {
                                "current_plan_revision": mission_row["plan_revision"],
                                "operator_label": operator_label,
                                "operator_rationale": reason,
                                "status": MissionStatus.PAUSED.value,
                            },
                            truth_kind=truth_kind,
                            authority=self._authority_for_truth(truth_kind),
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def reassign_task(
        self,
        mission_id: str,
        task_id: str,
        assigned_role: str,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        return self._update_task_operator_field(
            mission_id,
            task_id,
            command_id,
            field="assigned_role",
            value=assigned_role,
            event_type=MissionEventType.OPERATOR_REASSIGNED,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
        )

    def reprioritize_task(
        self,
        mission_id: str,
        task_id: str,
        priority: int,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        if type(priority) is not int or not -1_000 <= priority <= 1_000:
            raise ValueError("task priority must be between -1000 and 1000")
        return self._update_task_operator_field(
            mission_id,
            task_id,
            command_id,
            field="priority",
            value=priority,
            event_type=MissionEventType.OPERATOR_REPRIORITIZED,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
        )

    def _update_task_operator_field(
        self,
        mission_id: str,
        task_id: str,
        command_id: str,
        *,
        field: str,
        value: str | int,
        event_type: MissionEventType,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        request = {
            "field": field,
            "operator_label": operator_label,
            "rationale": rationale,
            "task_id": task_id,
            "truth_kind": truth_kind.value,
            "value": value,
        }
        request_sha = self._request_sha256(event_type.value, request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                task_row = self._task_row(
                    connection, mission_id, mission_row["plan_revision"], task_id
                )
                task = self._task_from_row(connection, task_row)
                if task.state in {
                    TaskState.RUNNING,
                    TaskState.VERIFYING,
                    TaskState.DONE,
                    TaskState.FAILED,
                    TaskState.CANCELLED,
                }:
                    raise MissionConflict("task cannot be changed in its current state")
                if field == "assigned_role":
                    policy, _ = self._policy(
                        connection,
                        mission_row["policy_id"],
                        mission_row["policy_revision"],
                        mission_id=mission_id,
                    )
                    if value not in policy.agent_roles:
                        raise MissionConflict("assigned role is not allowed by policy")
                initial = Task.model_validate_json(task_row["task_bytes"])
                updated = Task.model_validate(
                    {**initial.model_dump(mode="json"), field: value}
                )
                encoded = _json_bytes(updated)
                payload = {
                    field: value,
                    "assigned_role": updated.assigned_role,
                    "operator_label": operator_label,
                    "operator_rationale": rationale,
                    "priority": updated.priority,
                    "task_id": task_id,
                    "task_sha256": canonical_json_sha256(
                        updated.model_dump(mode="json")
                    ),
                }
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            event_type,
                            payload,
                            truth_kind=truth_kind,
                            authority=self._authority_for_truth(truth_kind),
                        ),
                    ),
                    recorded_at,
                )
                connection.execute(
                    "UPDATE mission_tasks SET priority = ?, task_bytes = ?, "
                    "task_contract_event_sha256 = ? WHERE mission_id = ? "
                    "AND plan_revision = ? AND task_id = ?",
                    (
                        updated.priority,
                        encoded,
                        head.event_sha256,
                        mission_id,
                        mission_row["plan_revision"],
                        task_id,
                    ),
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def _mission_status_command(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        operation: str,
        expected: MissionStatus,
        target: MissionStatus,
        event_type: MissionEventType,
        payload: dict[str, object],
        truth_kind: TruthKind,
        authority: MissionAuthority,
        expected_plan_revision: int | None = None,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        request = {"recorded_at": recorded_at.isoformat(), **payload}
        request_sha = self._request_sha256(operation, request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                row = self._mission_row(connection, mission_id)
                if (
                    expected_plan_revision is not None
                    and row["plan_revision"] != expected_plan_revision
                ):
                    raise MissionConflict("plan revision changed")
                current = MissionStatus(row["status"])
                if current != expected:
                    raise MissionConflict(f"mission is not {expected.value}")
                transition_mission(current, target)
                connection.execute(
                    "UPDATE missions SET status = ? WHERE mission_id = ?",
                    (target.value, mission_id),
                )
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            event_type,
                            payload,
                            truth_kind=truth_kind,
                            authority=authority,
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def cancel(
        self,
        mission_id: str,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        request = {
            "mission_id": mission_id,
            "operator_label": operator_label,
            "rationale": rationale,
            "recorded_at": recorded_at.isoformat(),
            "truth_kind": truth_kind.value,
        }
        request_sha = self._request_sha256("cancel", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                current = MissionStatus(mission_row["status"])
                target = transition_mission(current, MissionStatus.CANCELLED)
                connection.execute(
                    "UPDATE missions SET status = ? WHERE mission_id = ?",
                    (target.value, mission_id),
                )
                drafts = [
                    self._draft(
                        MissionEventType.OPERATOR_CANCELLED,
                        {
                            "operator_label": operator_label,
                            "operator_rationale": rationale,
                            "status": target.value,
                        },
                        truth_kind=truth_kind,
                        authority=self._authority_for_truth(truth_kind),
                    )
                ]
                task_rows = connection.execute(
                    "SELECT * FROM mission_tasks WHERE mission_id = ? AND state NOT IN (?, ?, ?)",
                    (
                        mission_id,
                        TaskState.DONE.value,
                        TaskState.FAILED.value,
                        TaskState.CANCELLED.value,
                    ),
                ).fetchall()
                for task_row in task_rows:
                    task = self._task_from_row(connection, task_row)
                    cancelled = Task.model_validate(
                        {
                            **task.model_dump(mode="json"),
                            "blocker": None,
                            "retry_at": None,
                            "state": transition_task(task.state, TaskState.CANCELLED),
                        }
                    )
                    self._update_task(connection, task_row, cancelled)
                    drafts.append(
                        self._draft(
                            MissionEventType.TASK_CANCELLED,
                            {
                                "state": TaskState.CANCELLED.value,
                                "task_id": task.task_id,
                            },
                        )
                    )
                lease_rows = connection.execute(
                    "SELECT lease_bytes FROM mission_leases WHERE mission_id = ? "
                    "AND released_at IS NULL",
                    (mission_id,),
                ).fetchall()
                for lease_row in lease_rows:
                    lease = Lease.model_validate_json(lease_row["lease_bytes"])
                    attempt, _ = self._attempt_and_lease(connection, lease.attempt_id)
                    cancelled_attempt = Attempt.model_validate(
                        {
                            **attempt.model_dump(mode="json"),
                            "ended_at": recorded_at,
                            "result_code": "mission_cancelled",
                            "state": AttemptState.CANCELLED,
                        }
                    )
                    self._update_attempt(connection, cancelled_attempt)
                    self._release_lease(connection, lease, recorded_at, "cancelled")
                head = self._append(
                    connection, mission_id, command_id, tuple(drafts), recorded_at
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _authority_for_truth(truth_kind: TruthKind) -> MissionAuthority:
        return {
            TruthKind.HUMAN_ATTESTED: MissionAuthority.OPERATOR,
            TruthKind.MODEL_PROPOSED: MissionAuthority.PLANNER,
            TruthKind.POLICY_AUTHORITATIVE: MissionAuthority.POLICY_ENGINE,
            TruthKind.RUNTIME_OBSERVED: MissionAuthority.WORKER_ADAPTER,
            TruthKind.SERVER_DERIVED: MissionAuthority.MISSION_SERVICE,
            TruthKind.SIMULATED_FIXTURE: MissionAuthority.SIMULATED_FIXTURE,
        }[truth_kind]

    @staticmethod
    def _validate_operator_truth(
        truth_kind: TruthKind, operator_label: str, rationale: str | None
    ) -> None:
        if truth_kind not in {
            TruthKind.HUMAN_ATTESTED,
            TruthKind.SERVER_DERIVED,
            TruthKind.SIMULATED_FIXTURE,
        }:
            raise ValueError(
                "operator commands require human, server-derived, or fixture truth"
            )
        if not 1 <= len(operator_label) <= 64 or (
            rationale is not None and not 1 <= len(rationale) <= 280
        ):
            raise ValueError("operator attribution must be bounded")

    def request_gate(
        self,
        gate: Gate,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        if gate.resolution is not None:
            raise MissionConflict("new gates must be unresolved")
        request = {
            "gate": gate.model_dump(mode="json"),
            "recorded_at": recorded_at.isoformat(),
        }
        request_sha = self._request_sha256("request_gate", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, gate.mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, gate.mission_id)
                if MissionStatus(mission_row["status"]) in {
                    MissionStatus.COMPLETED,
                    MissionStatus.REJECTED,
                    MissionStatus.CANCELLED,
                }:
                    raise MissionConflict("terminal mission cannot request a gate")
                blocked_task: Task | None = None
                if gate.task_id is not None:
                    task_row = self._task_row(
                        connection,
                        gate.mission_id,
                        mission_row["plan_revision"],
                        gate.task_id,
                    )
                    task = self._task_from_row(connection, task_row)
                    if task.state not in {TaskState.QUEUED, TaskState.READY}:
                        raise MissionConflict(
                            "gate can only block queued or ready work"
                        )
                    blocked_task = Task.model_validate(
                        {
                            **task.model_dump(mode="json"),
                            "blocker": f"gate:{gate.gate_id}",
                            "state": transition_task(task.state, TaskState.BLOCKED),
                        }
                    )
                    self._update_task(connection, task_row, blocked_task)
                connection.execute(
                    "INSERT INTO mission_gates VALUES (?, ?, ?, NULL, ?)",
                    (gate.gate_id, gate.mission_id, gate.task_id, _json_bytes(gate)),
                )
                drafts = [
                    self._draft(
                        MissionEventType.GATE_REQUESTED,
                        {
                            "allowed_decisions": [
                                item.value for item in gate.allowed_decisions
                            ],
                            "gate_id": gate.gate_id,
                            "gate_sha256": canonical_json_sha256(
                                gate.model_dump(mode="json")
                            ),
                            "reason_sha256": canonical_json_sha256(gate.reason),
                            "status": "needs_input",
                            "task_id": gate.task_id,
                        },
                        truth_kind=gate.truth_kind,
                        authority=self._authority_for_truth(gate.truth_kind),
                        references=gate.evidence,
                    )
                ]
                if blocked_task is not None:
                    drafts.append(
                        self._draft(
                            MissionEventType.TASK_BLOCKED,
                            {
                                "blocker": f"gate:{gate.gate_id}",
                                "gate_id": gate.gate_id,
                                "state": TaskState.BLOCKED.value,
                                "task_id": gate.task_id,
                            },
                        )
                    )
                head = self._append(
                    connection,
                    gate.mission_id,
                    command_id,
                    tuple(drafts),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, gate.mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def record_resource_summary(
        self,
        receipt: ResourceReceipt,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        request = {
            "receipt": receipt.model_dump(mode="json"),
            "recorded_at": recorded_at.isoformat(),
        }
        request_sha = self._request_sha256("record_resource_summary", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, receipt.mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                self._mission_row(connection, receipt.mission_id)
                receipt_sha = canonical_json_sha256(receipt.model_dump(mode="json"))
                threshold_crossed = (
                    receipt.value is not None
                    and receipt.threshold is not None
                    and receipt.value >= receipt.threshold
                )
                event_type = (
                    MissionEventType.RESOURCE_BUDGET_CROSSED
                    if threshold_crossed
                    else MissionEventType.RESOURCE_SUMMARY_RECORDED
                )
                head = self._append(
                    connection,
                    receipt.mission_id,
                    command_id,
                    (
                        self._draft(
                            event_type,
                            {
                                "action": receipt.action,
                                "attribution_quality": receipt.attribution_quality,
                                "observed_from": receipt.observed_from.isoformat(),
                                "observed_until": receipt.observed_until.isoformat(),
                                "platform": receipt.platform,
                                "receipt_id": receipt.receipt_id,
                                "receipt_sha256": receipt_sha,
                                "source": receipt.source,
                                "scope": receipt.scope,
                                "semantics": receipt.semantics,
                                "subject": receipt.subject,
                                "threshold": receipt.threshold,
                                "threshold_crossed": threshold_crossed,
                                "units": receipt.units,
                                "value": receipt.value,
                            },
                            truth_kind=TruthKind.RUNTIME_OBSERVED,
                            authority=MissionAuthority.MISSION_SERVICE,
                            references=(
                                EvidenceReference(
                                    kind="resource_receipt",
                                    id=receipt.receipt_id,
                                    sha256=receipt_sha,
                                ),
                            ),
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, receipt.mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def decide_gate(
        self,
        mission_id: str,
        gate_id: str,
        choice: str,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        request = {
            "choice": choice,
            "gate_id": gate_id,
            "operator_label": operator_label,
            "rationale": rationale,
            "recorded_at": recorded_at.isoformat(),
            "truth_kind": truth_kind.value,
        }
        request_sha = self._request_sha256("decide_gate", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                self._mission_row(connection, mission_id)
                row = connection.execute(
                    "SELECT gate_bytes, resolution FROM mission_gates "
                    "WHERE mission_id = ? AND gate_id = ?",
                    (mission_id, gate_id),
                ).fetchone()
                if row is None:
                    raise MissionConflict("gate is unavailable")
                if row["resolution"] is not None:
                    raise MissionConflict("gate is already resolved")
                gate = Gate.model_validate_json(row["gate_bytes"])
                selected = next(
                    (item for item in gate.allowed_decisions if item.value == choice),
                    None,
                )
                if selected is None:
                    raise MissionConflict("gate choice is not allowed")
                decided = Gate.model_validate(
                    {
                        **gate.model_dump(mode="json"),
                        "operator_label": operator_label,
                        "rationale": rationale,
                        "resolution": choice,
                    }
                )
                connection.execute(
                    "UPDATE mission_gates SET resolution = ?, gate_bytes = ? "
                    "WHERE gate_id = ? AND resolution IS NULL",
                    (choice, _json_bytes(decided), gate_id),
                )
                task_state: TaskState | None = None
                if gate.task_id is not None:
                    mission_row = self._mission_row(connection, mission_id)
                    task_row = self._task_row(
                        connection,
                        mission_id,
                        mission_row["plan_revision"],
                        gate.task_id,
                    )
                    task = self._task_from_row(connection, task_row)
                    if task.state != TaskState.BLOCKED:
                        raise MissionConflict("gated task is no longer blocked")
                    target = task.state
                    blocker = task.blocker
                    if selected.task_effect == "cancelled":
                        target = TaskState.CANCELLED
                        blocker = None
                    elif selected.task_effect == "needs_input":
                        target = TaskState.NEEDS_INPUT
                        blocker = None
                    else:
                        other = connection.execute(
                            "SELECT gate_id FROM mission_gates WHERE mission_id = ? "
                            "AND task_id = ? AND resolution IS NULL AND gate_id != ? "
                            "ORDER BY gate_id LIMIT 1",
                            (mission_id, gate.task_id, gate_id),
                        ).fetchone()
                        if other is not None:
                            blocker = f"gate:{other['gate_id']}"
                        elif self._dependencies_satisfied(
                            connection,
                            mission_id,
                            mission_row["plan_revision"],
                            task,
                        ):
                            target = TaskState.READY
                            blocker = None
                        else:
                            blocker = "dependencies"
                    updated = Task.model_validate(
                        {
                            **task.model_dump(mode="json"),
                            "blocker": blocker,
                            "state": (
                                transition_task(task.state, target)
                                if target != task.state
                                else target
                            ),
                        }
                    )
                    self._update_task(connection, task_row, updated)
                    task_state = target if target != task.state else None
                payload = {
                    "choice": choice,
                    "gate_id": gate_id,
                    "gate_sha256": canonical_json_sha256(
                        decided.model_dump(mode="json")
                    ),
                    "operator_label": operator_label,
                    "operator_rationale": rationale,
                    "status": "decided",
                    "task_id": gate.task_id,
                }
                if task_state is not None:
                    payload["task_state"] = task_state.value
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            MissionEventType.GATE_DECIDED,
                            payload,
                            truth_kind=truth_kind,
                            authority=self._authority_for_truth(truth_kind),
                            references=gate.evidence,
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _final_publications(
        connection: sqlite3.Connection, mission_id: str, revision: int
    ) -> tuple[ArtifactPublication, ArtifactPublication]:
        rows = connection.execute(
            "SELECT t.kind AS task_kind, p.publication_bytes FROM mission_publications p "
            "JOIN mission_tasks t ON t.mission_id = p.mission_id "
            "AND t.plan_revision = p.plan_revision AND t.task_id = p.task_id "
            "WHERE p.mission_id = ? AND p.plan_revision = ? AND t.kind IN (?, ?) "
            "AND p.state = ? ORDER BY t.kind, p.publication_id",
            (
                mission_id,
                revision,
                TaskKind.ASSEMBLY.value,
                TaskKind.VERIFICATION.value,
                PublicationState.ACCEPTED.value,
            ),
        ).fetchall()
        by_kind: dict[str, list[ArtifactPublication]] = {}
        for row in rows:
            by_kind.setdefault(row["task_kind"], []).append(
                ArtifactPublication.model_validate_json(row["publication_bytes"])
            )
        if any(
            len(by_kind.get(kind.value, ())) != 1
            for kind in (TaskKind.ASSEMBLY, TaskKind.VERIFICATION)
        ):
            raise MissionConflict(
                "one accepted assembly candidate and verification receipt are required"
            )
        return (
            by_kind[TaskKind.ASSEMBLY.value][0],
            by_kind[TaskKind.VERIFICATION.value][0],
        )

    @staticmethod
    def _publication_evidence_reference(
        connection: sqlite3.Connection, publication: ArtifactPublication
    ) -> EvidenceReference:
        row = connection.execute(
            "SELECT attempt_bytes FROM mission_attempts WHERE attempt_id = ?",
            (publication.attempt_id,),
        ).fetchone()
        if row is None:
            raise MissionStoreError("publication attempt is unavailable")
        attempt = Attempt.model_validate_json(row["attempt_bytes"])
        matches = tuple(
            reference
            for reference in attempt.evidence_refs
            if reference.kind == publication.kind
            and reference.sha256 == publication.sha256
        )
        if len(matches) != 1:
            raise MissionConflict("publication evidence authority is ambiguous")
        return matches[0]

    def enter_awaiting_result(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        request = {"mission_id": mission_id, "recorded_at": recorded_at.isoformat()}
        request_sha = self._request_sha256("enter_awaiting_result", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                current = MissionStatus(mission_row["status"])
                if current != MissionStatus.RUNNING:
                    raise MissionConflict("mission is not ready for final review")
                unfinished = connection.execute(
                    "SELECT COUNT(*) FROM mission_tasks WHERE mission_id = ? "
                    "AND plan_revision = ? AND state != ?",
                    (mission_id, mission_row["plan_revision"], TaskState.DONE.value),
                ).fetchone()[0]
                if unfinished:
                    raise MissionConflict("all mission tasks must be done")
                candidate, verification = self._final_publications(
                    connection, mission_id, mission_row["plan_revision"]
                )
                target = transition_mission(current, MissionStatus.AWAITING_RESULT)
                connection.execute(
                    "UPDATE missions SET status = ? WHERE mission_id = ?",
                    (target.value, mission_id),
                )
                references = tuple(
                    EvidenceReference(
                        kind=item.kind,
                        id=item.publication_id,
                        sha256=item.sha256,
                    )
                    for item in (candidate, verification)
                )
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            MissionEventType.FINAL_CANDIDATE_READY,
                            {
                                "candidate_publication_id": candidate.publication_id,
                                "candidate_sha256": candidate.sha256,
                                "status": target.value,
                                "verification_publication_id": verification.publication_id,
                                "verification_sha256": verification.sha256,
                            },
                            references=references,
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def approve_final_result(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_candidate_sha256: str,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        return self._final_decision(
            mission_id,
            command_id,
            expected_candidate_sha256=expected_candidate_sha256,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
            approved=True,
        )

    def reject_final_result(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_candidate_sha256: str,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        return self._final_decision(
            mission_id,
            command_id,
            expected_candidate_sha256=expected_candidate_sha256,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
            approved=False,
        )

    def _final_decision(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_candidate_sha256: str,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
        approved: bool,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        expected_candidate_sha256 = _SHA256.validate_python(expected_candidate_sha256)
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        operation = "approve_final_result" if approved else "reject_final_result"
        request = {
            "expected_candidate_sha256": expected_candidate_sha256,
            "operator_label": operator_label,
            "rationale": rationale,
            "recorded_at": recorded_at.isoformat(),
            "truth_kind": truth_kind.value,
        }
        request_sha = self._request_sha256(operation, request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                current = MissionStatus(mission_row["status"])
                if current != MissionStatus.AWAITING_RESULT:
                    raise MissionConflict("mission is not awaiting a final decision")
                if mission_row["final_outcome"] is not None:
                    raise MissionConflict("a final decision is already committed")
                candidate, verification = self._final_publications(
                    connection, mission_id, mission_row["plan_revision"]
                )
                if candidate.sha256 != expected_candidate_sha256:
                    raise MissionConflict("final candidate digest changed")
                target = (
                    current
                    if approved
                    else transition_mission(current, MissionStatus.REJECTED)
                )
                outcome = "approved" if approved else "rejected"
                stored_outcome = "approved_pending_commit" if approved else outcome
                connection.execute(
                    "UPDATE missions SET status = ?, final_outcome = ? WHERE mission_id = ?",
                    (target.value, stored_outcome, mission_id),
                )
                references = tuple(
                    EvidenceReference(
                        kind=item.kind,
                        id=item.publication_id,
                        sha256=item.sha256,
                    )
                    for item in (candidate, verification)
                )
                event_type = (
                    MissionEventType.FINAL_CANDIDATE_APPROVED
                    if approved
                    else MissionEventType.FINAL_CANDIDATE_REJECTED
                )
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            event_type,
                            {
                                "candidate_sha256": candidate.sha256,
                                "operator_label": operator_label,
                                "operator_rationale": rationale,
                                "outcome": outcome,
                                "status": target.value,
                                "verification_sha256": verification.sha256,
                            },
                            truth_kind=truth_kind,
                            authority=self._authority_for_truth(truth_kind),
                            references=references,
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def record_isolated_commit(
        self,
        mission_id: str,
        commit_sha: str,
        receipt: EvidenceReference,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        commit_sha = _GIT_SHA.validate_python(commit_sha)
        request = {
            "commit_sha": commit_sha,
            "receipt": receipt.model_dump(mode="json"),
            "recorded_at": recorded_at.isoformat(),
        }
        request_sha = self._request_sha256("record_isolated_commit", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                if (
                    MissionStatus(mission_row["status"]) == MissionStatus.COMPLETED
                    and mission_row["final_outcome"] == "approved"
                ):
                    raise MissionConflict("mission isolated commit is already recorded")
                if (
                    MissionStatus(mission_row["status"])
                    != MissionStatus.AWAITING_RESULT
                    or mission_row["final_outcome"] != "approved_pending_commit"
                ):
                    raise MissionConflict("only an approved result can be committed")
                # ponytail: one terminal full-stream check; add an event-type
                # index if the bounded mission history ceiling grows.
                existing_events = connection.execute(
                    "SELECT event_bytes FROM mission_events WHERE mission_id = ?",
                    (mission_id,),
                ).fetchall()
                if any(
                    MissionEvent.model_validate_json(row["event_bytes"]).event_type
                    == MissionEventType.ISOLATED_COMMIT_CREATED
                    for row in existing_events
                ):
                    raise MissionConflict("mission isolated commit is already recorded")
                if receipt.kind != "local-result-receipt":
                    raise MissionConflict("isolated commit receipt kind is invalid")
                if self.artifact_resolver is None:
                    raise MissionConflict(
                        "isolated commit receipt resolver is unavailable"
                    )
                raw = self.artifact_resolver.resolve(receipt.kind, receipt.id)
                if raw is None or sha256_hex(raw) != receipt.sha256:
                    raise MissionConflict("isolated commit receipt is unavailable")
                try:
                    from .local_result import LocalResultReceipt

                    local_receipt = LocalResultReceipt.model_validate_json(raw)
                except (ImportError, ValueError) as error:
                    raise MissionConflict(
                        "isolated commit receipt is invalid"
                    ) from error
                candidate, verification = self._final_publications(
                    connection, mission_id, mission_row["plan_revision"]
                )
                verification_reference = self._publication_evidence_reference(
                    connection, verification
                )
                mission_contract = Mission.model_validate_json(
                    mission_row["mission_bytes"]
                )
                approvals = tuple(
                    event
                    for event in (
                        MissionEvent.model_validate_json(row["event_bytes"])
                        for row in existing_events
                    )
                    if event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
                )
                if len(approvals) != 1:
                    raise MissionConflict("final approval authority is ambiguous")
                approval = approvals[0]
                approval_rationale = approval.payload.get("operator_rationale")
                rationale_sha256 = (
                    None
                    if approval_rationale is None
                    else sha256_hex(str(approval_rationale).encode())
                )
                if (
                    local_receipt.mission_id != mission_id
                    or local_receipt.decision != "approve"
                    or local_receipt.outcome != "isolated_local_commit"
                    or local_receipt.local_commit_sha != commit_sha
                    or local_receipt.base_sha != mission_contract.base_sha
                    or local_receipt.candidate_patch_sha256 != candidate.sha256
                    or local_receipt.verification_id != verification_reference.id
                    or local_receipt.verification_sha256 != verification.sha256
                    or local_receipt.truth_kind != approval.truth_kind
                    or local_receipt.operator_label
                    != approval.payload.get("operator_label")
                    or local_receipt.rationale_sha256 != rationale_sha256
                    or local_receipt.result_ref
                    != "refs/graphene/results/" + sha256_hex(mission_id.encode())[:24]
                ):
                    raise MissionConflict("isolated commit receipt bindings changed")
                if self.local_commit_verifier is None or not self.local_commit_verifier(
                    raw
                ):
                    raise MissionConflict(
                        "isolated commit Git proof is not authoritative"
                    )
                connection.execute(
                    "UPDATE missions SET status = ?, final_outcome = ? WHERE mission_id = ?",
                    (MissionStatus.COMPLETED.value, "approved", mission_id),
                )
                head = self._append(
                    connection,
                    mission_id,
                    command_id,
                    (
                        self._draft(
                            MissionEventType.ISOLATED_COMMIT_CREATED,
                            {
                                "local_commit_sha": commit_sha,
                                "outcome": "local_isolated_commit",
                                "pushed": False,
                                "pull_request_created": False,
                                "receipt_id": receipt.id,
                                "receipt_sha256": receipt.sha256,
                                "status": MissionStatus.COMPLETED.value,
                            },
                            truth_kind=TruthKind.RUNTIME_OBSERVED,
                            authority=MissionAuthority.MISSION_SERVICE,
                            references=(receipt,),
                        ),
                    ),
                    recorded_at,
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def retry_task(
        self,
        mission_id: str,
        task_id: str,
        command_id: str,
        *,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        command_id = _COMMAND_ID.validate_python(command_id)
        recorded_at = self._time(recorded_at)
        self._validate_operator_truth(truth_kind, operator_label, rationale)
        request = {
            "mission_id": mission_id,
            "operator_label": operator_label,
            "rationale": rationale,
            "recorded_at": recorded_at.isoformat(),
            "task_id": task_id,
            "truth_kind": truth_kind.value,
        }
        request_sha = self._request_sha256("retry_task", request)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._existing_command(
                    connection, mission_id, command_id, request_sha
                )
                if existing is not None:
                    connection.commit()
                    return self._result_head(existing)
                mission_row = self._mission_row(connection, mission_id)
                task_row = self._task_row(
                    connection, mission_id, mission_row["plan_revision"], task_id
                )
                task = self._task_from_row(connection, task_row)
                if task.state != TaskState.FAILED:
                    raise MissionConflict("only failed tasks can be retried")
                if task.attempt_count >= task.attempt_limit:
                    raise MissionConflict("task attempt limit is exhausted")
                retried = Task.model_validate(
                    {
                        **task.model_dump(mode="json"),
                        "retry_at": recorded_at,
                        "state": transition_task(task.state, TaskState.RETRYING),
                    }
                )
                self._update_task(connection, task_row, retried)
                drafts: list[MissionEventInput] = []
                current = MissionStatus(mission_row["status"])
                if current == MissionStatus.FAILED:
                    target = transition_mission(current, MissionStatus.RUNNING)
                    connection.execute(
                        "UPDATE missions SET status = ?, final_outcome = NULL WHERE mission_id = ?",
                        (target.value, mission_id),
                    )
                    drafts.append(
                        self._draft(
                            MissionEventType.OPERATOR_RESUMED,
                            {
                                "operator_label": operator_label,
                                "operator_rationale": rationale,
                                "reason_code": "operator_retry",
                                "status": target.value,
                            },
                            truth_kind=truth_kind,
                            authority=self._authority_for_truth(truth_kind),
                        )
                    )
                elif current != MissionStatus.RUNNING:
                    raise MissionConflict("mission cannot retry a task now")
                drafts.append(
                    self._draft(
                        MissionEventType.TASK_RETRIED,
                        {
                            "reason_code": "operator_retry",
                            "operator_label": operator_label,
                            "operator_rationale": rationale,
                            "retry_at": recorded_at.isoformat(),
                            "state": TaskState.RETRYING.value,
                            "task_id": task_id,
                        },
                        truth_kind=truth_kind,
                        authority=self._authority_for_truth(truth_kind),
                    )
                )
                head = self._append(
                    connection, mission_id, command_id, tuple(drafts), recorded_at
                )
                result = self._head_result(head)
                self._record_command(
                    connection, mission_id, command_id, request_sha, result
                )
                connection.commit()
                return head
            except Exception:
                connection.rollback()
                raise

    def head(self, mission_id: str) -> MissionHead:
        with closing(self._connect()) as connection:
            head = self._head(connection, mission_id)
            if (
                head.seq == 0
                and connection.execute(
                    "SELECT 1 FROM missions WHERE mission_id = ?", (mission_id,)
                ).fetchone()
                is None
            ):
                raise MissionNotFound(mission_id)
            return head

    def tail(
        self, mission_id: str, after_seq: int, limit: int
    ) -> tuple[MissionEvent, ...]:
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        with closing(self._connect()) as connection:
            self._mission_row(connection, mission_id)
            rows = connection.execute(
                "SELECT event_bytes FROM mission_events WHERE mission_id = ? "
                "AND seq > ? ORDER BY seq LIMIT ?",
                (mission_id, after_seq, limit),
            ).fetchall()
        return tuple(
            MissionEvent.model_validate_json(row["event_bytes"]) for row in rows
        )

    def _all_events(self, mission_id: str) -> tuple[MissionEvent, ...]:
        head = self.head(mission_id)
        events: list[MissionEvent] = []
        after = 0
        while after < head.seq:
            batch = self.tail(mission_id, after, min(256, head.seq - after))
            if not batch:
                raise MissionStoreError("mission event stream is incomplete")
            events.extend(batch)
            after = batch[-1].seq
        return tuple(events)

    def verify(self, mission_id: str) -> MissionHead:
        with closing(self._connect()) as connection:
            mission_row = self._mission_row(connection, mission_id)
            initial_mission = self._initial_mission(connection, mission_row)
            revision = mission_row["plan_revision"]
            policy, policy_sha256 = self._policy(
                connection,
                mission_row["policy_id"],
                mission_row["policy_revision"],
                mission_id=mission_id,
            )
            rows = connection.execute(
                "SELECT * FROM mission_tasks WHERE mission_id = ? AND plan_revision = ? "
                "ORDER BY task_id",
                (mission_id, revision),
            ).fetchall()
            plan = self._plan(connection, mission_id, revision)
            initial_tasks = plan.tasks
            current_tasks = tuple(self._task_from_row(connection, row) for row in rows)
            gate_rows = connection.execute(
                "SELECT gate_bytes FROM mission_gates WHERE mission_id = ? ORDER BY gate_id",
                (mission_id,),
            ).fetchall()
            gates = tuple(
                Gate.model_validate_json(row["gate_bytes"]) for row in gate_rows
            )
            stored_status = MissionStatus(mission_row["status"])
        head = self.head(mission_id)
        events = self._all_events(mission_id)
        reduced = reduce_events(initial_mission, initial_tasks, events)
        projects = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.PROJECT_CREATED
        )
        missions = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.MISSION_CREATED
        )
        proposed = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.PLAN_PROPOSED
        )
        validated = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.PLAN_VALIDATED
        )
        plan_sha256 = canonical_json_sha256(plan.model_dump(mode="json"))
        contracts_match_events = (
            len(projects) == len(missions) == len(proposed) == len(validated) == 1
            and projects[0].payload
            == {
                "base_sha": policy.base_sha,
                "policy_id": policy.policy_id,
                "policy_revision": policy.revision,
                "policy_sha256": policy_sha256,
                "repo_id": policy.repo_id,
            }
            and missions[0].payload
            == {
                "creation_source": initial_mission.creation_source,
                "goal_sha256": canonical_json_sha256(initial_mission.goal),
                "mission_sha256": canonical_json_sha256(
                    initial_mission.model_dump(mode="json")
                ),
                "plan_revision": plan.revision,
                "status": MissionStatus.PROPOSED.value,
                "success_criteria_count": len(initial_mission.success_criteria),
            }
            and proposed[0].payload.get("plan_revision") == plan.revision
            and proposed[0].payload.get("plan_sha256") == plan_sha256
            and proposed[0].payload.get("task_count") == len(plan.tasks)
            and validated[0].payload
            == {
                "plan_revision": plan.revision,
                "plan_sha256": plan_sha256,
                "status": "valid",
            }
        )
        requested = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.GATE_REQUESTED
        )
        decided = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.GATE_DECIDED
        )
        requested_by_id = {
            str(event.payload.get("gate_id")): event for event in requested
        }
        decided_by_id = {str(event.payload.get("gate_id")): event for event in decided}
        gates_by_id = {str(gate.gate_id): gate for gate in gates}
        gates_match_events = (
            len(requested_by_id) == len(requested)
            and len(decided_by_id) == len(decided)
            and set(requested_by_id) == set(gates_by_id)
            and set(decided_by_id).issubset(gates_by_id)
        )
        if gates_match_events:
            for gate_id, gate in gates_by_id.items():
                request = requested_by_id[gate_id]
                requested_gate = gate.model_copy(
                    update={
                        "operator_label": None,
                        "rationale": None,
                        "resolution": None,
                    }
                )
                decision = decided_by_id.get(gate_id)
                if (
                    request.payload.get("gate_sha256")
                    != canonical_json_sha256(requested_gate.model_dump(mode="json"))
                    or request.truth_kind != gate.truth_kind
                    or request.references != gate.evidence
                    or (gate.resolution is None) != (decision is None)
                    or (
                        decision is not None
                        and (
                            decision.payload.get("gate_sha256")
                            != canonical_json_sha256(gate.model_dump(mode="json"))
                            or decision.payload.get("choice") != gate.resolution
                            or decision.payload.get("operator_label")
                            != gate.operator_label
                            or decision.payload.get("operator_rationale")
                            != gate.rationale
                            or decision.references != gate.evidence
                        )
                    )
                ):
                    gates_match_events = False
                    break
        if (
            len(events) != head.event_count
            or (events[-1].event_sha256 if events else None) != head.event_sha256
            or reduced.status != stored_status
            or reduced.task_states
            != {task.task_id: task.state for task in current_tasks}
            or reduced.attempt_counts
            != {task.task_id: task.attempt_count for task in current_tasks}
            or not gates_match_events
            or not contracts_match_events
        ):
            raise MissionStoreError("mission materialized state does not match replay")
        return head

    def snapshot(self, mission_id: str) -> MissionSnapshot:
        with closing(self._connect()) as connection:
            mission_row = self._mission_row(connection, mission_id)
            policy, policy_sha256 = self._policy(
                connection,
                mission_row["policy_id"],
                mission_row["policy_revision"],
                mission_id=mission_id,
            )
            initial_mission = self._initial_mission(connection, mission_row)
            mission = Mission.model_validate(
                {
                    **initial_mission.model_dump(mode="json"),
                    "final_outcome": mission_row["final_outcome"],
                    "status": mission_row["status"],
                }
            )
            plan = self._plan(connection, mission_id, mission_row["plan_revision"])
            task_rows = connection.execute(
                "SELECT * FROM mission_tasks WHERE mission_id = ? AND plan_revision = ? "
                "ORDER BY task_id",
                (mission_id, mission_row["plan_revision"]),
            ).fetchall()
            attempt_rows = connection.execute(
                "SELECT attempt_bytes FROM mission_attempts WHERE mission_id = ? "
                "ORDER BY attempt_id",
                (mission_id,),
            ).fetchall()
            lease_rows = connection.execute(
                "SELECT lease_bytes FROM mission_leases WHERE mission_id = ? ORDER BY lease_id",
                (mission_id,),
            ).fetchall()
            publication_rows = connection.execute(
                "SELECT publication_bytes FROM mission_publications WHERE mission_id = ? "
                "ORDER BY publication_id",
                (mission_id,),
            ).fetchall()
            gate_rows = connection.execute(
                "SELECT gate_bytes FROM mission_gates WHERE mission_id = ? ORDER BY gate_id",
                (mission_id,),
            ).fetchall()
            head = self._head(connection, mission_id)
            tasks = tuple(self._task_from_row(connection, row) for row in task_rows)
        summary = ProjectPolicySummary(
            policy_id=policy.policy_id,
            revision=policy.revision,
            repo_id=policy.repo_id,
            base_ref=policy.base_ref,
            base_sha=policy.base_sha,
            command_template_ids=tuple(
                item.template_id for item in policy.command_templates
            ),
            max_concurrency=policy.max_concurrency,
            retry_limit=policy.retry_limit,
            network_mode=policy.network.mode,
            policy_sha256=policy_sha256,
        )
        values = {
            "schema_version": 1,
            "policy": summary.model_dump(mode="json"),
            "mission": mission.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "attempts": [
                Attempt.model_validate_json(row["attempt_bytes"]).model_dump(
                    mode="json"
                )
                for row in attempt_rows
            ],
            "leases": [
                Lease.model_validate_json(row["lease_bytes"]).model_dump(mode="json")
                for row in lease_rows
            ],
            "publications": [
                ArtifactPublication.model_validate_json(
                    row["publication_bytes"]
                ).model_dump(mode="json")
                for row in publication_rows
            ],
            "gates": [
                Gate.model_validate_json(row["gate_bytes"]).model_dump(mode="json")
                for row in gate_rows
            ],
            "head": head.model_dump(mode="json"),
            "unknowns": list(mission.unknowns),
        }
        return MissionSnapshot.model_validate(
            {**values, "snapshot_sha256": canonical_json_sha256(values)}
        )
