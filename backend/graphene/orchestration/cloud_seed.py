"""Seed a mission into a Firestore namespace for the outbound vertical (§9).

`docs/CLOUD_PROOF_PLAN.md` §5 documents the only implemented seeding path:
``initialize_namespace_schema`` → ``create_mission`` → ``approve_plan`` →
``refresh_ready``. This module runs exactly that sequence against a
``FirestoreMissionStore``, deriving deterministic command ids from one caller
prefix so a retried seed replays the same idempotent commands instead of
forking history. No CLI verb is exposed here; the coordinator decides where
this is surfaced.
"""

from __future__ import annotations

import re
from datetime import datetime

from ..core_models import TruthKind
from .firestore_mission_store import FirestoreMissionStore
from .mission_models import Mission, MissionHead, Plan, ProjectPolicy

# Derived ids append "_create" / "_approve" / "_ready"; the store requires
# command ids matching ^[A-Za-z0-9_-]{16,128}$, so the prefix carries the rest.
_COMMAND_PREFIX = re.compile(r"^[A-Za-z0-9_-]{10,120}$")


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
    """Create, approve, and readiness-refresh one mission; return its head.

    Idempotent on retry: every command id is derived from ``command_prefix``,
    so replaying with identical inputs returns the committed results instead
    of appending new events. ``truth_kind`` and the operator attribution are
    required because plan approval is an operator decision the seeder must
    not invent.
    """

    if not isinstance(command_prefix, str) or _COMMAND_PREFIX.fullmatch(
        command_prefix
    ) is None:
        raise ValueError("command_prefix must match ^[A-Za-z0-9_-]{10,120}$")
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


__all__ = ["seed_mission"]
