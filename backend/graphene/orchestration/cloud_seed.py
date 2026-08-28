"""Seed a verified local plan into the narrow Firestore executor vertical."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import model_validator

from ..core_models import (
    BoundedText,
    FrozenModel,
    GitSha,
    IdempotencyKey,
    Identifier,
    Sha256,
    TruthKind,
    UtcDateTime,
)
from ..hashing import canonical_json_sha256
from .firestore_mission_store import FirestoreMissionStore
from .mission_models import (
    AuthorizationMode,
    FinalizationMode,
    Mission,
    MissionHead,
    MissionStatus,
    PLAN_AWAITING_REVIEW_UNKNOWN,
    Plan,
    ProjectPolicy,
)

# Derived ids append ``_create`` / ``_approve`` / ``_ready``.
_COMMAND_PREFIX = re.compile(r"^[A-Za-z0-9_-]{16,120}$")


class CloudSeedError(RuntimeError):
    pass


class CloudSeedReceipt(FrozenModel):
    """Public, credential-free binding between local contracts and Firestore."""

    schema_version: Literal[1] = 1
    mission_id: Identifier
    repo_id: Identifier
    base_sha: GitSha
    source_policy_id: Identifier
    cloud_policy_id: Identifier
    source_head: MissionHead
    firestore_head: MissionHead
    source_policy_sha256: Sha256
    cloud_policy_sha256: Sha256
    plan_sha256: Sha256
    execution_contract_sha256: Sha256
    firestore_snapshot_sha256: Sha256
    project_id: BoundedText
    database_id: BoundedText
    namespace: Identifier
    coordinator_audience: BoundedText
    command_prefix: IdempotencyKey
    truth_kind: TruthKind
    recorded_at: UtcDateTime
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def bindings_are_exact(self) -> CloudSeedReceipt:
        if (
            self.source_head.mission_id != self.mission_id
            or self.firestore_head.mission_id != self.mission_id
            or self.truth_kind
            not in {TruthKind.HUMAN_ATTESTED, TruthKind.SERVER_DERIVED}
        ):
            raise ValueError("cloud seed receipt bindings do not match")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        )
        if self.receipt_sha256 != expected:
            raise ValueError("cloud seed receipt digest does not match")
        return self


def projected_cloud_contracts(
    policy: ProjectPolicy, mission: Mission
) -> tuple[ProjectPolicy, Mission]:
    """Project execution contracts to Firestore's honest schema-1 scope."""

    source_policy_sha256 = canonical_json_sha256(policy.model_dump(mode="json"))
    if policy.schema_version == 1:
        cloud_policy = policy
    else:
        cloud_policy = ProjectPolicy.model_validate(
            {
                **policy.model_dump(mode="json"),
                "schema_version": 1,
                "policy_id": f"cloud_policy_{source_policy_sha256[:24]}",
                "revision": 1,
                "authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
                "finalization_mode": FinalizationMode.REVIEW_REQUIRED,
            }
        )
    cloud_mission = Mission.model_validate(
        {
            **mission.model_dump(mode="json"),
            "schema_version": 1,
            "policy_id": cloud_policy.policy_id,
            "policy_revision": cloud_policy.revision,
            "requested_authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
            "requested_finalization_mode": FinalizationMode.REVIEW_REQUIRED,
            "status": MissionStatus.PROPOSED,
            "unknowns": tuple(
                item
                for item in mission.unknowns
                if item != PLAN_AWAITING_REVIEW_UNKNOWN
            ),
        }
    )
    return cloud_policy, cloud_mission


def cloud_execution_contract_sha256(
    policy: ProjectPolicy, mission: Mission, plan: Plan
) -> str:
    """Bind the common execution meaning, not store-specific event identities."""

    running = mission.model_copy(update={"status": MissionStatus.RUNNING})
    return canonical_json_sha256(
        {
            "mission": running.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "policy_sha256": canonical_json_sha256(policy.model_dump(mode="json")),
        }
    )


def seed_mission(
    store: FirestoreMissionStore,
    *,
    policy: ProjectPolicy,
    mission: Mission,
    plan: Plan,
    command_prefix: str,
    recorded_at: datetime,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
) -> MissionHead:
    """Create, approve, and readiness-refresh one mission idempotently."""

    if not isinstance(command_prefix, str) or _COMMAND_PREFIX.fullmatch(
        command_prefix
    ) is None:
        raise ValueError("command_prefix must match ^[A-Za-z0-9_-]{16,120}$")
    store.initialize_namespace_schema()
    created = store.create_mission(
        policy,
        mission,
        plan,
        f"{command_prefix}_create",
        recorded_at=recorded_at,
    )
    store.approve_plan(
        mission.mission_id,
        f"{command_prefix}_approve",
        expected_revision=plan.revision,
        expected_head=created,
        operator_label=operator_label,
        rationale=rationale,
        truth_kind=truth_kind,
        recorded_at=recorded_at,
    )
    store.refresh_ready(
        mission.mission_id,
        f"{command_prefix}_ready",
        recorded_at=recorded_at,
    )
    return store.head(mission.mission_id)


def seed_verified_projection(
    store: FirestoreMissionStore,
    *,
    source_policy: ProjectPolicy,
    source_mission: Mission,
    source_head: MissionHead,
    plan: Plan,
    command_prefix: str,
    recorded_at: datetime,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
    project_id: str,
    database_id: str,
    namespace: str,
    coordinator_audience: str,
) -> CloudSeedReceipt:
    """Seed, read back, and bind one separate Cloud Run proof mission."""

    cloud_policy, cloud_mission = projected_cloud_contracts(
        source_policy, source_mission
    )
    if (
        source_head.mission_id != source_mission.mission_id
        or truth_kind
        not in {TruthKind.HUMAN_ATTESTED, TruthKind.SERVER_DERIVED}
    ):
        raise CloudSeedError("cloud seed source binding is invalid")
    head = seed_mission(
        store,
        policy=cloud_policy,
        mission=cloud_mission,
        plan=plan,
        command_prefix=command_prefix,
        recorded_at=recorded_at,
        operator_label=operator_label,
        rationale=rationale,
        truth_kind=truth_kind,
    )
    snapshot = store.reconcile_materialization(source_mission.mission_id)
    observed_head = snapshot.head
    committed = store.tail(source_mission.mission_id, head.seq - 1, 1)
    running = cloud_mission.model_copy(update={"status": MissionStatus.RUNNING})
    cloud_policy_sha256 = canonical_json_sha256(cloud_policy.model_dump(mode="json"))
    if (
        observed_head != head
        or snapshot.head != head
        or snapshot.mission != running
        or snapshot.plan != plan
        or snapshot.policy.policy_sha256 != cloud_policy_sha256
        or snapshot.policy.schema_version != 1
        or snapshot.attempts
        or snapshot.leases
        or snapshot.publications
        or snapshot.gates
        or len(committed) != 1
    ):
        raise CloudSeedError("Firestore seed readback differs from the local contracts")
    values = {
        "schema_version": 1,
        "mission_id": source_mission.mission_id,
        "repo_id": source_mission.repo_id,
        "base_sha": source_mission.base_sha,
        "source_policy_id": source_policy.policy_id,
        "cloud_policy_id": cloud_policy.policy_id,
        "source_head": source_head.model_dump(mode="json"),
        "firestore_head": head.model_dump(mode="json"),
        "source_policy_sha256": canonical_json_sha256(
            source_policy.model_dump(mode="json")
        ),
        "cloud_policy_sha256": cloud_policy_sha256,
        "plan_sha256": canonical_json_sha256(plan.model_dump(mode="json")),
        "execution_contract_sha256": cloud_execution_contract_sha256(
            cloud_policy, cloud_mission, plan
        ),
        "firestore_snapshot_sha256": snapshot.snapshot_sha256,
        "project_id": project_id,
        "database_id": database_id,
        "namespace": namespace,
        "coordinator_audience": coordinator_audience,
        "command_prefix": command_prefix,
        "truth_kind": truth_kind.value,
        "recorded_at": committed[0].server_recorded_at.isoformat().replace(
            "+00:00", "Z"
        ),
    }
    return CloudSeedReceipt.model_validate(
        {**values, "receipt_sha256": canonical_json_sha256(values)}
    )


__all__ = [
    "CloudSeedError",
    "CloudSeedReceipt",
    "cloud_execution_contract_sha256",
    "projected_cloud_contracts",
    "seed_mission",
    "seed_verified_projection",
]
