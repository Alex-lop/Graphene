from __future__ import annotations

import pathlib
import re
from contextlib import closing
from datetime import timedelta

import pytest
from pydantic import ValidationError

import graphene.orchestration.store as store_module
from graphene.hashing import canonical_json_sha256
from graphene.models import TruthKind
from graphene.orchestration.models import (
    ArtifactRequirement,
    MissionEvent,
    AttemptState,
    MissionEventType,
    MissionStatus,
    Plan,
    PublicationState,
    Task,
    TaskKind,
    TaskState,
)
from graphene.orchestration.projection import MissionProjection
from graphene.orchestration.store import (
    LeaseConflict,
    MissionConflict,
    SQLiteMissionStore,
    StaleWorker,
)
from graphene.orchestration.validation import PlanValidationError
from tests.unit.orchestration.test_store import (
    NOW,
    _task,
    _artifacts,
    _command,
    _create,
    _plan,
    _register_worker,
    _success,
)


def _revision_two() -> Plan:
    original = _plan()
    tasks = []
    for task in original.tasks:
        value = task.model_dump(mode="json")
        if task.task_id == "work-a":
            value["contract"] = "Produce patch-a for the revised plan."
            value["priority"] = 3
        tasks.append(Task.model_validate(value))
    return Plan.model_validate(
        {
            **original.model_dump(mode="json"),
            "previous_revision": 1,
            "revision": 2,
            "tasks": [item.model_dump(mode="json") for item in tasks],
        }
    )


def test_revision_invalidates_old_work_and_cold_replay_uses_fresh_tasks(
    tmp_path,
) -> None:
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    _create(store)
    store.refresh_ready("mission-1", _command("ready-old"), recorded_at=NOW)
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))
    _register_worker(store, "worker-b", capabilities=(TaskKind.WORK,))
    old_work_a = store.claim_task(
        "mission-1",
        "work-a",
        "worker-a",
        _command("claim-old-a"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    old_work_b = store.claim_task(
        "mission-1",
        "work-b",
        "worker-b",
        _command("claim-old-b"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    old_task_b = next(task for task in _plan().tasks if task.task_id == "work-b")
    store.complete_attempt(
        "mission-1",
        old_work_b.attempt_id,
        old_work_b.worker_id,
        old_work_b.lease_id,
        old_work_b.fencing_token,
        _success(old_work_b, old_task_b, _artifacts(store)),
        _command("complete-old-b"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )

    stale_head = store.head("mission-1")
    requested = store.request_replan(
        "mission-1",
        _command("request-replan"),
        expected_head=stale_head,
        reason="The work contract changed.",
        operator_label="api-operator",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )
    assert store.snapshot("mission-1").mission.status == MissionStatus.PAUSED

    revised = _revision_two()
    with pytest.raises(MissionConflict, match="expected head"):
        store.revise_plan(
            "mission-1",
            revised,
            _command("revise-stale"),
            expected_head=stale_head,
            recorded_at=NOW + timedelta(seconds=3),
        )
    store.revise_plan(
        "mission-1",
        revised,
        _command("revise-current"),
        # Mid-mission revision is not the product's edit path this release; it
        # is exercised here as the primitive it is, behind its explicit flag.
        allow_after_dispatch=True,
        expected_head=requested,
        recorded_at=NOW + timedelta(seconds=3),
    )

    snapshot = store.snapshot("mission-1")
    assert snapshot.mission.plan_revision == snapshot.plan.revision == 2
    assert snapshot.mission.status == MissionStatus.PAUSED
    assert all(
        task.state == TaskState.QUEUED and task.attempt_count == 0
        for task in snapshot.tasks
    )
    old_attempt = next(
        item for item in snapshot.attempts if item.attempt_id == old_work_a.attempt_id
    )
    old_lease = next(
        item for item in snapshot.leases if item.lease_id == old_work_a.lease_id
    )
    assert old_attempt.state == AttemptState.ABANDONED
    assert old_attempt.result_code == "plan_revised"
    assert old_lease.release_reason == "plan_revised"
    assert all(
        publication.state == PublicationState.REJECTED
        for publication in snapshot.publications
    )

    diff = store.plan_diff("mission-1", 1, 2)
    revised_event = next(
        event
        for event in store.tail("mission-1", 0, 256)
        if event.event_type == MissionEventType.PLAN_REVISED
    )
    assert revised_event.payload["diff_sha256"] == canonical_json_sha256(
        {key: value for key, value in diff.items() if key != "diff_sha256"}
    )
    assert "tasks" not in revised_event.payload
    assert diff["tasks"]["changed"][0]["after"]["contract"].endswith("revised plan.")

    old_task_a = next(task for task in _plan().tasks if task.task_id == "work-a")
    with pytest.raises(StaleWorker):
        store.complete_attempt(
            "mission-1",
            old_work_a.attempt_id,
            old_work_a.worker_id,
            old_work_a.lease_id,
            old_work_a.fencing_token,
            _success(old_work_a, old_task_a, _artifacts(store)),
            _command("late-old-a"),
            recorded_at=NOW + timedelta(seconds=4),
            retry_backoff_seconds=0,
        )

    store.approve_plan(
        "mission-1",
        _command("approve-revised"),
        expected_revision=2,
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="The revision is validated.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=5),
    )
    artifacts = _artifacts(store)
    cold = SQLiteMissionStore(path, artifact_resolver=artifacts)
    assert cold.verify("mission-1") == cold.head("mission-1")
    assert cold.snapshot("mission-1").mission.status == MissionStatus.RUNNING
    assert MissionProjection(cold).snapshot("mission-1").mission.plan_revision == 2


def test_revision_rejects_unrequested_or_mission_mismatched_plan(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.pause(
        "mission-1",
        _command("pause-not-replan"),
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="Inspect first.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    with pytest.raises(MissionConflict, match="not requested"):
        store.revise_plan(
            "mission-1",
            _revision_two(),
            _command("unrequested"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=1),
        )

    store.resume(
        "mission-1",
        _command("resume-before-request"),
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="Continue to request the revision.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )
    store.request_replan(
        "mission-1",
        _command("request-mismatch"),
        expected_head=store.head("mission-1"),
        reason="Revise now.",
        operator_label="api-operator",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=3),
    )
    changed = _revision_two().model_dump(mode="json")
    changed["criteria"][0]["description"] = "A different criterion."
    with pytest.raises(MissionConflict, match="bindings do not match"):
        store.revise_plan(
            "mission-1",
            Plan.model_validate(changed),
            _command("criteria-mismatch"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=4),
        )

    over_policy = _revision_two().model_dump(mode="json")
    over_policy["max_concurrency"] = 5
    with pytest.raises(PlanValidationError):
        store.revise_plan(
            "mission-1",
            Plan.model_validate(over_policy),
            _command("policy-mismatch"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=5),
        )

    noncontiguous = _revision_two().model_dump(mode="json")
    noncontiguous["previous_revision"] = 2
    with pytest.raises(ValidationError, match="link contiguously"):
        Plan.model_validate(noncontiguous)


def _pre_dispatch_revision_two() -> Plan:
    """Revision 2 the way a user would make it: one added, wired-in node.

    `export` is disjoint in output from every other task, it depends on
    `work-a`, and `assemble` consumes what it publishes — so the added node
    has to run, its position in the order matters, and its artifact reaches
    the assembled result.
    """
    original = _plan()
    export = _task(
        "export",
        "export-a",
        "patch",
        "out/export.json",
        dependencies=("work-a",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-a", name="patch-a", kind="patch"
            ),
        ),
    )
    assemble = next(task for task in original.tasks if task.task_id == "assemble")
    rewired = Task.model_validate(
        {
            **assemble.model_dump(mode="json"),
            "dependencies": ["export", "work-a", "work-b"],
            "inputs": sorted(
                (
                    *(item.model_dump(mode="json") for item in assemble.inputs),
                    {
                        "producer_task_id": "export",
                        "name": "export-a",
                        "kind": "patch",
                    },
                ),
                key=lambda item: (item["producer_task_id"], item["name"], item["kind"]),
            ),
        }
    )
    tasks = sorted(
        (
            export,
            rewired,
            *(task for task in original.tasks if task.task_id != "assemble"),
        ),
        key=lambda item: item.task_id,
    )
    return Plan.model_validate(
        {
            **original.model_dump(mode="json"),
            "previous_revision": 1,
            "revision": 2,
            "tasks": [item.model_dump(mode="json") for item in tasks],
        }
    )


def test_a_plan_revision_nobody_approved_cannot_be_dispatched(tmp_path) -> None:
    """The gate the product's edit path stands on.

    Revising before dispatch is legal and leaves the mission PROPOSED. What
    must not be legal is reaching a worker with revision 2 on the strength of
    the approval that was given to revision 1.
    """
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    approved = next(
        event
        for event in store.tail("mission-1", 0, 256)
        if event.event_type == MissionEventType.PLAN_APPROVED
    )
    # All four elements of the binding are readable from the approval itself.
    assert approved.payload["plan_revision"] == 1
    assert approved.payload["base_sha"] == store.snapshot("mission-1").mission.base_sha
    assert approved.payload["plan_sha256"] == canonical_json_sha256(
        _plan().model_dump(mode="json")
    )

    # An approval of a digest the store does not hold is refused outright.
    store.pause(
        "mission-1",
        _command("pause-for-revision"),
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="Revise before running.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(MissionConflict, match="digest does not match"):
        store.approve_plan(
            "mission-1",
            _command("approve-wrong-digest"),
            expected_revision=1,
            expected_head=store.head("mission-1"),
            operator_label="api-operator",
            rationale="Wrong digest.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=2),
            expected_plan_sha256="0" * 64,
        )
    store.request_replan(
        "mission-1",
        _command("request-the-revision"),
        expected_head=store.head("mission-1"),
        reason="Add an audit node.",
        operator_label="api-operator",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=3),
    )
    store.revise_plan(
        "mission-1",
        _pre_dispatch_revision_two(),
        _command("revise-to-two"),
        expected_head=store.head("mission-1"),
        recorded_at=NOW + timedelta(seconds=4),
    )
    assert store.snapshot("mission-1").mission.plan_revision == 2

    # Revision 1's approval does not carry across the edit, so `resume` — the
    # one way back to RUNNING that never asks a person about the new graph —
    # is refused.
    with pytest.raises(MissionConflict, match="has not been approved"):
        store.resume(
            "mission-1",
            _command("resume-unapproved"),
            expected_head=store.head("mission-1"),
            operator_label="api-operator",
            rationale="Sneak revision 2 in.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=5),
        )
    # Approving the revision that is no longer current is refused too.
    with pytest.raises(MissionConflict, match="revision changed"):
        store.approve_plan(
            "mission-1",
            _command("approve-stale-revision"),
            expected_revision=1,
            expected_head=store.head("mission-1"),
            operator_label="api-operator",
            rationale="Re-approve the old revision.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=6),
        )

    store.approve_plan(
        "mission-1",
        _command("approve-revision-two"),
        expected_revision=2,
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="The added audit node is approved.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=7),
        expected_plan_sha256=canonical_json_sha256(
            _pre_dispatch_revision_two().model_dump(mode="json")
        ),
    )
    snapshot = store.snapshot("mission-1")
    assert snapshot.mission.status == MissionStatus.RUNNING
    assert "export" in {task.task_id for task in snapshot.plan.tasks}


def test_a_worker_cannot_claim_a_node_whose_revision_lost_its_approval(
    tmp_path, monkeypatch
) -> None:
    """The last gate, not only the operator's front door.

    After the `resume` and retry refusals above there is no API route left
    that reaches RUNNING with an unapproved revision — which is the point,
    and which also means no API sequence can reach this guard. So the
    approval lookup is neutered directly: the claim must be refused rather
    than dispatched. Delete the guard in `claim_task` and this test fails.
    """
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready-guard"), recorded_at=NOW)
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))

    monkeypatch.setattr(
        SQLiteMissionStore,
        "_approved_plan_sha256",
        staticmethod(lambda *_args, **_kwargs: None),
    )
    with pytest.raises(LeaseConflict, match="not approved"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-a",
            _command("claim-unapproved"),
            recorded_at=NOW + timedelta(seconds=1),
            ttl_seconds=30,
        )

    # And an approval that names a different plan than the one on disk is
    # refused for the same reason: the approval is of a graph, not a number.
    monkeypatch.setattr(
        SQLiteMissionStore,
        "_approved_plan_sha256",
        staticmethod(lambda *_args, **_kwargs: "0" * 64),
    )
    with pytest.raises(LeaseConflict, match="digest does not match"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-a",
            _command("claim-wrong-digest"),
            recorded_at=NOW + timedelta(seconds=2),
            ttl_seconds=30,
        )


def test_the_plan_cannot_be_edited_once_a_worker_has_claimed_a_node(tmp_path) -> None:
    """Editing before execution is the product; editing after it is not."""
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready-dispatch"), recorded_at=NOW)
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))
    store.claim_task(
        "mission-1",
        "work-a",
        "worker-a",
        _command("claim-before-edit"),
        recorded_at=NOW + timedelta(seconds=1),
        ttl_seconds=30,
    )
    store.pause(
        "mission-1",
        _command("pause-after-claim"),
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="Try to edit mid-flight.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )
    store.request_replan(
        "mission-1",
        _command("request-after-claim"),
        expected_head=store.head("mission-1"),
        reason="Add an audit node.",
        operator_label="api-operator",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=3),
    )
    with pytest.raises(MissionConflict, match="cannot be revised after dispatch"):
        store.revise_plan(
            "mission-1",
            _pre_dispatch_revision_two(),
            _command("revise-after-claim"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=4),
        )


def test_the_approval_lookup_never_pattern_matches_sql_against_stored_bytes() -> None:
    """The guard that would have caught a green macOS run breaking Linux CI.

    `mission_events.event_bytes` is a BLOB. SQLite's `LIKE` matches against a
    BLOB on 3.51 (macOS) and matches nothing on 3.46 (this project's Linux
    CI), so a prefilter written in SQL made `claim_task` refuse every
    approved plan on Linux while every macOS check stayed green — including
    `scripts/morning_verify.sh`, which is a macOS result by construction and
    structurally cannot see this.

    Any prefiltering belongs in Python, where the semantics do not move with
    the library version.
    """
    code = "\n".join(
        line
        for line in pathlib.Path(store_module.__file__).read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    offending = re.findall(r"event_bytes\s*(?:\"\s*\n\s*\")?\s*LIKE", code, re.I)
    assert offending == [], (
        "SQL pattern-matches against the event_bytes BLOB; prefilter in Python"
    )


def test_the_approval_prefilter_drops_nothing_an_unfiltered_scan_would_find(
    tmp_path,
) -> None:
    """The invariant the old comment asserted and did not have.

    Pinning one platform's behaviour would only fail where the bug already
    shows. This pins the property instead: whatever the lookup filters with,
    it must reach the same answer as a scan that filters nothing. It fails on
    every platform if the prefilter ever drops a real match — including the
    way it would fail if the pattern were `str` against `bytes`, where the
    containment test silently matches nothing.
    """
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    snapshot = store.snapshot("mission-1")
    digest = canonical_json_sha256(snapshot.plan.model_dump(mode="json"))

    def unfiltered(connection, revision: int) -> str | None:
        """The same question, asked with no prefilter of any kind."""
        for row in connection.execute(
            "SELECT event_bytes FROM mission_events WHERE mission_id = ? "
            "ORDER BY seq DESC",
            ("mission-1",),
        ):
            event = MissionEvent.model_validate_json(row["event_bytes"])
            if (
                event.event_type == MissionEventType.PLAN_APPROVED
                and event.payload.get("plan_revision") == revision
            ):
                value = event.payload.get("plan_sha256")
                return value if isinstance(value, str) else ""
        return None

    with closing(store._connect()) as connection:
        for revision in (1, 2, 3):
            assert store._approved_plan_sha256(
                connection, "mission-1", revision
            ) == unfiltered(connection, revision), (
                f"the prefilter and an unfiltered scan disagree at revision {revision}"
            )
        assert store._approved_plan_sha256(connection, "mission-1", 1) == digest
        # A revision nobody approved is None, never an empty string: an empty
        # string means "approved before the digest field existed".
        assert store._approved_plan_sha256(connection, "mission-1", 2) is None
