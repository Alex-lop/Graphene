from __future__ import annotations

import stat
from datetime import timedelta
from types import SimpleNamespace

import pytest

from graphene.cli import mission as mission_cli
from graphene.core_models import TruthKind
from graphene.hashing import canonical_json_bytes, canonical_json_sha256
from graphene.orchestration.cloud_seed import (
    CloudSeedReceipt,
    projected_cloud_contracts,
    seed_mission,
    seed_verified_projection,
)
from graphene.orchestration.firestore_mission_store import (
    FirestoreMissionStore,
    MissionStateInvalid,
)
from graphene.orchestration.mission_models import (
    AuthorizationMode,
    FinalizationMode,
    Mission,
    MissionHead,
    MissionStatus,
    ProjectPolicy,
    TaskState,
)
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


def _operator_source():
    values = _seed_values()
    policy = ProjectPolicy.model_validate(
        {
            **values["policy"].model_dump(mode="json"),
            "schema_version": 2,
            "authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
            "finalization_mode": FinalizationMode.REVIEW_REQUIRED,
        }
    )
    mission = Mission.model_validate(
        {
            **values["mission"].model_dump(mode="json"),
            "schema_version": 2,
            "creation_source": "operator",
            "requested_authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
            "requested_finalization_mode": FinalizationMode.REVIEW_REQUIRED,
        }
    )
    head = MissionHead(
        mission_id=mission.mission_id,
        seq=6,
        event_count=6,
        event_sha256="f" * 64,
    )
    return values, policy, mission, head


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
    assert seed_mission(
        store,
        **{**values, "recorded_at": START + timedelta(seconds=1)},
    ) == head
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


def test_verified_projection_binds_schema_two_source_to_schema_one_firestore():
    values, source_policy, source_mission, source_head = _operator_source()
    cloud_policy, cloud_mission = projected_cloud_contracts(
        source_policy, source_mission
    )

    assert cloud_policy.schema_version == cloud_mission.schema_version == 1
    assert cloud_policy.policy_id != source_policy.policy_id
    assert cloud_mission.policy_id == cloud_policy.policy_id
    assert cloud_mission.status == MissionStatus.PROPOSED
    assert source_mission.status == MissionStatus.PROPOSED

    client = Client()
    store = FirestoreMissionStore(client, namespace="test", clock=Clock(START))
    seed = {
        "source_policy": source_policy,
        "source_mission": source_mission,
        "source_head": source_head,
        "plan": values["plan"],
        "command_prefix": values["command_prefix"],
        "operator_label": "cloud-operator",
        "rationale": "approve the isolated cloud proof projection",
        "truth_kind": TruthKind.HUMAN_ATTESTED,
        "project_id": "graphene-proof-1",
        "database_id": "graphene",
        "namespace": "test",
        "coordinator_audience": "https://coordinator.example.run.app",
    }
    receipt = seed_verified_projection(store, recorded_at=START, **seed)
    retried = seed_verified_projection(
        store, recorded_at=START + timedelta(seconds=1), **seed
    )

    assert receipt.source_head == source_head
    assert receipt.firestore_head == retried.firestore_head == store.head(MISSION_ID)
    assert receipt == retried
    assert receipt.source_policy_sha256 == canonical_json_sha256(
        source_policy.model_dump(mode="json")
    )
    assert receipt.cloud_policy_sha256 == canonical_json_sha256(
        cloud_policy.model_dump(mode="json")
    )
    assert store.snapshot(MISSION_ID).mission.status == MissionStatus.RUNNING

    tampered = {**receipt.model_dump(mode="json"), "project_id": "other-project-1"}
    with pytest.raises(ValueError, match="digest"):
        CloudSeedReceipt.model_validate(tampered)

    event_path = next(path for path in client.documents if "/events/" in path)
    client.documents[event_path]["value"]["payload"]["task_count"] = 99
    with pytest.raises(MissionStateInvalid, match="event"):
        seed_verified_projection(store, recorded_at=START, **seed)


@pytest.mark.parametrize("interrupted_after", ("create_mission", "approve_plan"))
def test_verified_projection_recovers_after_a_partially_committed_seed(
    interrupted_after: str, monkeypatch: pytest.MonkeyPatch
):
    values, policy, mission, source_head = _operator_source()
    seed = {
        "source_policy": policy,
        "source_mission": mission,
        "source_head": source_head,
        "plan": values["plan"],
        "command_prefix": values["command_prefix"],
        "operator_label": "cloud-operator",
        "rationale": "approve the isolated cloud proof projection",
        "truth_kind": TruthKind.HUMAN_ATTESTED,
        "project_id": "graphene-proof-1",
        "database_id": "graphene",
        "namespace": "test",
        "coordinator_audience": "https://coordinator.example.run.app",
    }
    store = FirestoreMissionStore(Client(), namespace="test", clock=Clock(START))
    original = getattr(store, interrupted_after)
    interrupted = True

    def commit_then_interrupt(*args, **kwargs):
        nonlocal interrupted
        result = original(*args, **kwargs)
        if interrupted:
            interrupted = False
            raise RuntimeError("seed interrupted after commit")
        return result

    monkeypatch.setattr(store, interrupted_after, commit_then_interrupt)
    with pytest.raises(RuntimeError, match="interrupted after commit"):
        seed_verified_projection(store, recorded_at=START, **seed)

    recovered = seed_verified_projection(
        store, recorded_at=START + timedelta(seconds=1), **seed
    )
    assert recovered.firestore_head == store.head(mission.mission_id)
    assert seed_verified_projection(
        store, recorded_at=START + timedelta(seconds=2), **seed
    ) == recovered


def test_executor_seed_handler_writes_one_private_bound_receipt(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    values, policy, mission, source_head = _operator_source()
    snapshot = SimpleNamespace(mission=mission, plan=values["plan"])
    monkeypatch.setattr(
        mission_cli,
        "_executor_source",
        lambda _args: (tmp_path, policy, object(), snapshot, source_head),
    )
    client = Client()
    client_calls = []

    def firestore_client(*, project, database):
        client_calls.append((project, database))
        return client

    monkeypatch.setattr(mission_cli.firestore, "Client", firestore_client)
    for name, value in {
        "GOOGLE_CLOUD_PROJECT": "graphene-proof-1",
        "GRAPHENE_FIRESTORE_DATABASE": "graphene",
        "GRAPHENE_FIRESTORE_NAMESPACE": "test",
    }.items():
        monkeypatch.setenv(name, value)
    plan_sha256 = canonical_json_sha256(values["plan"].model_dump(mode="json"))
    output = tmp_path / "seed.json"
    args = mission_cli.build_parser().parse_args(
        [
            "mission",
            "executor",
            "seed",
            "--repo",
            str(tmp_path),
            "--mission",
            mission.mission_id,
            "--plan-sha256",
            plan_sha256,
            "--audience",
            "https://coordinator.example.run.app",
            "--output",
            str(output),
        ]
    )

    result = mission_cli._executor_seed(args)
    receipt = mission_cli._read_cloud_seed_receipt(output)

    assert client_calls == [("graphene-proof-1", "graphene")]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_bytes() == canonical_json_bytes(receipt.model_dump(mode="json"))
    assert result["receipt_sha256"] == receipt.receipt_sha256
    assert result["firestore_head"] == receipt.firestore_head.model_dump(mode="json")
    assert result["cloud_scheduling_parity_claimed"] is False

    with pytest.raises(mission_cli.MissionCliError, match="new non-symlink"):
        mission_cli._executor_seed(args)
    bad = SimpleNamespace(**{**vars(args), "output": tmp_path / "bad.json"})
    bad.plan_sha256 = "d" * 64
    with pytest.raises(mission_cli.MissionCliError, match="plan digest"):
        mission_cli._executor_seed(bad)
    assert not bad.output.exists()
