from __future__ import annotations

import pytest

from graphene.core_models import TruthKind
from graphene.orchestration.cloud_seed import seed_mission
from graphene.orchestration.firestore_mission_store import FirestoreMissionStore
from graphene.orchestration.mission_models import MissionStatus, TaskState
from graphene.orchestration.scripted import load_scenario

from .test_firestore import (
    MISSION_ID,
    START,
    Client,
    Clock,
    fake_transactional,  # noqa: F401  (autouse fixture for FirestoreMissionStore)
)


def _seed_values():
    policy, mission, plan = load_scenario().contracts(
        mission_id=MISSION_ID,
        repo_id="repo-cloud-seed",
        base_sha="a" * 40,
        created_at=START,
    )
    return {
        "policy": policy,
        "mission": mission,
        "plan": plan,
        "command_prefix": "seed_cloud_test_01",
        "recorded_at": START,
        "operator_label": "seed-fixture",
        "rationale": "cloud seed unit proof",
        "truth_kind": TruthKind.SIMULATED_FIXTURE,
    }


def test_seed_mission_runs_the_documented_sequence_and_is_idempotent():
    client = Client()
    store = FirestoreMissionStore(client, namespace="test", clock=Clock(START))
    values = _seed_values()

    head = seed_mission(store, **values)

    snapshot = store.snapshot(MISSION_ID)
    assert snapshot.head == head
    assert head.seq > 0
    assert snapshot.mission.status == MissionStatus.RUNNING
    ready = {
        item.task_id for item in snapshot.tasks if item.state == TaskState.READY
    }
    assert ready == {"redact_notes", "render_json", "render_markdown"}
    # The derived command ids landed as durable idempotency records.
    command_documents = [
        path for path in client.documents if "/commands/" in path
    ]
    assert len(command_documents) == 3

    # A retried seed replays the same commands instead of forking history.
    assert seed_mission(store, **values) == head
    assert store.snapshot(MISSION_ID) == snapshot
    assert [
        path for path in client.documents if "/commands/" in path
    ] == command_documents


def test_seed_mission_refuses_an_unusable_command_prefix_before_writing():
    client = Client()
    store = FirestoreMissionStore(client, namespace="test", clock=Clock(START))
    values = {**_seed_values(), "command_prefix": "short"}

    with pytest.raises(ValueError, match="command_prefix"):
        seed_mission(store, **values)

    assert client.documents == {}
