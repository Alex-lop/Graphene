"""The product claim, end to end: the user's edit is what runs.

A mission is proposed, exported as canonical YAML, edited the way a person
edits it — one node added, one edge rewired — compiled into immutable
revision 2, approved on the new digest, and executed. Everything asserted
below is about revision 2: that it dispatched, that the added node ran in the
order the edit implied, and that what it produced reached the verified result.
"""

from __future__ import annotations

import pytest
import yaml

from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.models import (
    AttemptState,
    MissionEventType,
    MissionStatus,
    Plan,
    PublicationState,
    Task,
    TaskKind,
)
from graphene.orchestration.plan_yaml import plan_from_yaml, plan_to_yaml
from graphene.orchestration.runner import AcceptedArtifactCache, MissionRunner
from graphene.orchestration.scheduler import MissionScheduler, SystemClock
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.store import (
    LeaseConflict,
    MissionConflict,
    SQLiteMissionStore,
)
from graphene.orchestration.runtime import CheckOutcome, RuntimeAssignment
from tests.unit.orchestration.test_runner import (
    CHECK,
    _Adapter,
    _contracts,
    _git,
    _repository,
    _runtime,
)


class _CheckEveryFile:
    """The acceptance check for a plan the user edited — including the new node.

    It asserts the same thing the fixture's own runner does: the workspace it
    is handed already contains exactly the writes the node owns.
    """

    EXPECTED = {
        "work-a": {"a.txt": "a-after\n"},
        "work-c": {"c.txt": "c-after\n"},
        "work-z": {"b.txt": "b-after\n"},
        "assemble": {"a.txt": "a-after\n", "b.txt": "b-after\n", "c.txt": "c-after\n"},
        "verify": {"a.txt": "a-after\n", "b.txt": "b-after\n", "c.txt": "c-after\n"},
    }

    async def __call__(self, workspace, assignment, owner_id) -> CheckOutcome:
        del owner_id
        expected = self.EXPECTED[assignment.task_id]
        assert all(
            (workspace / path).read_text() == text for path, text in expected.items()
        )
        return CheckOutcome(
            template_id=CHECK.template_id,
            template_sha256=canonical_json_sha256(CHECK.model_dump(mode="json")),
            exit_code=0,
            timed_out=False,
            output_sha256=sha256_hex(b"passed"),
            output_truncated=False,
            cleanup_complete=True,
        )


def _edited_document(document: str) -> str:
    """The edit a person makes in their editor, expressed as the text change.

    `work-c` is added with a write scope nothing else owns, and `assemble` is
    rewired to wait for it and consume what it publishes.
    """
    plan = plan_from_yaml(document)
    tasks = {task.task_id: task for task in plan.tasks}
    work_a = tasks["work-a"]
    tasks["work-c"] = Task.model_validate(
        {
            **work_a.model_dump(mode="json"),
            "task_id": "work-c",
            "title": "work-c",
            "contract": "Write the third file the user asked for.",
            "write_paths": ["c.txt"],
            "expected_outputs": [
                {"name": "patch-c", "kind": "patch", "paths": ["c.txt"]}
            ],
        }
    )
    assemble = tasks["assemble"]
    tasks["assemble"] = Task.model_validate(
        {
            **assemble.model_dump(mode="json"),
            "dependencies": ["work-a", "work-c", "work-z"],
            "inputs": sorted(
                (
                    *(item.model_dump(mode="json") for item in assemble.inputs),
                    {
                        "producer_task_id": "work-c",
                        "name": "patch-c",
                        "kind": "patch",
                    },
                ),
                key=lambda item: (item["producer_task_id"], item["name"], item["kind"]),
            ),
        }
    )
    edited = Plan.model_validate(
        {
            **plan.model_dump(mode="json"),
            "tasks": [
                item.model_dump(mode="json")
                for item in sorted(tasks.values(), key=lambda item: item.task_id)
            ],
        }
    )
    return plan_to_yaml(edited)


def _mission_with_room_for_a_third_file(tmp_path):
    repository, base_sha = _repository(tmp_path / "supplied-repository")
    (repository / "c.txt").write_text("c-before\n")
    _git(repository, "add", "c.txt")
    _git(repository, "commit", "-q", "-m", "third file")
    base_sha = _git(repository, "rev-parse", "HEAD")

    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    store = SQLiteMissionStore(tmp_path / "missions.sqlite", artifact_resolver=evidence)
    policy, mission, plan = _contracts(base_sha)
    # The policy is the bound the edit lives under: it permits a third file,
    # and the revision is only legal because it stays inside it.
    policy = policy.model_copy(
        update={
            "allowed_read_globs": ("a.txt", "b.txt", "c.txt"),
            "allowed_write_globs": ("a.txt", "b.txt", "c.txt"),
            "max_concurrency": 3,
        }
    )
    plan = Plan.model_validate(
        {
            **plan.model_dump(mode="json"),
            "tasks": [
                {**task.model_dump(mode="json"), "read_paths": ["a.txt", "b.txt", "c.txt"]}
                for task in plan.tasks
            ],
        }
    )
    store.create_mission(
        policy,
        mission,
        plan,
        "command-create-edit-path-mission",
        recorded_at=mission.created_at,
    )
    return repository, base_sha, runtime_root, evidence, store, mission, plan


def test_the_scheduler_executes_the_users_revision_not_the_proposal(tmp_path) -> None:
    (
        repository,
        base_sha,
        runtime_root,
        evidence,
        store,
        mission,
        proposal,
    ) = _mission_with_room_for_a_third_file(tmp_path)
    mission_id = mission.mission_id
    assert store.snapshot(mission_id).mission.status == MissionStatus.PROPOSED

    # Export, edit, compile. The revision is not approved by making it.
    revised = plan_from_yaml(_edited_document(plan_to_yaml(proposal)))
    revised = Plan.model_validate(
        {
            **revised.model_dump(mode="json"),
            "previous_revision": 1,
            "revision": 2,
        }
    )
    store.revise_plan(
        mission_id,
        revised,
        "command-revise-edit-path",
        expected_head=store.head(mission_id),
        recorded_at=mission.created_at,
    )
    revision_two_sha256 = canonical_json_sha256(revised.model_dump(mode="json"))
    assert store.snapshot(mission_id).mission.plan_revision == 2

    # The diff a person would read before approving names the change.
    diff = store.plan_diff(mission_id, 1, 2)
    assert [item["task_id"] for item in diff["tasks"]["added"]] == ["work-c"]
    assert [item["after"]["task_id"] for item in diff["tasks"]["changed"]] == [
        "assemble"
    ]

    # Approval binds the exact digest that diff was taken against.
    with pytest.raises(MissionConflict, match="digest does not match"):
        store.approve_plan(
            mission_id,
            "command-approve-wrong-digest",
            expected_revision=2,
            expected_head=store.head(mission_id),
            operator_label="test-operator",
            rationale="Approve the wrong graph.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=mission.created_at,
            expected_plan_sha256=canonical_json_sha256(
                proposal.model_dump(mode="json")
            ),
        )
    store.approve_plan(
        mission_id,
        "command-approve-edit-path",
        expected_revision=2,
        expected_head=store.head(mission_id),
        operator_label="test-operator",
        rationale="Approve the revision with the added node.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=mission.created_at,
        expected_plan_sha256=revision_two_sha256,
    )

    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    snapshot = store.snapshot(mission_id)
    assignments = {
        task.task_id: RuntimeAssignment(
            task_id=task.task_id,
            title=task.title,
            contract=task.contract,
            read_paths=task.read_paths,
            output_name=task.expected_outputs[0].name,
            output_kind=task.expected_outputs[0].kind,
            output_paths=task.expected_outputs[0].paths,
            command_template=CHECK,
        )
        for task in snapshot.plan.tasks
    }
    adapters = (
        _Adapter("worker-a", "a.txt", "a-after\n", 0),
        _Adapter("worker-c", "c.txt", "c-after\n", 0),
        _Adapter("worker-z", "b.txt", "b-after\n", 0),
    )
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=adapters,
        cache=cache,
        check_runner=_CheckEveryFile(),
    )
    run = MissionRunner(
        scheduler=scheduler,
        runtime=runtime,
        worker_ids=("worker-a", "worker-c", "worker-z"),
        accepted_artifacts=cache,
        deadline_seconds=3_600,
        poll_seconds=0,
        monotonic=lambda: 0.0,
    ).run(mission_id)

    assert run.snapshot.mission.status == MissionStatus.AWAITING_RESULT

    # 1. Every attempt ran under revision 2 — none under the proposal.
    assert {item.plan_revision for item in run.snapshot.attempts} == {2}
    assert {item.state for item in run.snapshot.attempts} == {AttemptState.COMMITTED}

    # 2. The node the user added actually ran.
    assert "work-c" in run.completion_order
    assert adapters[1].calls == 1

    # 3. Its position in the order mattered: assembly waited for it.
    assert run.completion_order.index("work-c") < run.completion_order.index(
        "assemble"
    )

    # 4. What it produced reached the assembled, verified result.
    accepted = {
        item.output_name
        for item in run.snapshot.publications
        if item.state == PublicationState.ACCEPTED
    }
    assert {"patch-a", "patch-c", "patch-z", "candidate", "verification"} <= accepted
    assert {item.plan_revision for item in run.snapshot.publications} == {2}
    assert (repository / "c.txt").read_text() == "c-before\n", (
        "the supplied checkout is never written to"
    )

    # 5. The approval that authorized all of it names all four elements.
    approval = next(
        event
        for event in reversed(store.tail(mission_id, 0, run.snapshot.head.seq))
        if event.event_type == MissionEventType.PLAN_APPROVED
    )
    assert approval.payload["plan_revision"] == 2
    assert approval.payload["plan_sha256"] == revision_two_sha256
    assert approval.payload["base_sha"] == base_sha
    assert store.verify(mission_id) == store.head(mission_id)


def test_the_proposal_cannot_run_once_the_user_has_revised_it(tmp_path) -> None:
    """Revision 1's approval does not survive the edit."""
    (
        _repository_path,
        _base_sha,
        _runtime_root,
        _evidence,
        store,
        mission,
        proposal,
    ) = _mission_with_room_for_a_third_file(tmp_path)
    mission_id = mission.mission_id
    revised = Plan.model_validate(
        {
            **plan_from_yaml(_edited_document(plan_to_yaml(proposal))).model_dump(
                mode="json"
            ),
            "previous_revision": 1,
            "revision": 2,
        }
    )
    store.revise_plan(
        mission_id,
        revised,
        "command-revise-before-approval",
        expected_head=store.head(mission_id),
        recorded_at=mission.created_at,
    )
    # Approving the revision the user replaced is refused outright.
    with pytest.raises(MissionConflict, match="revision changed"):
        store.approve_plan(
            mission_id,
            "command-approve-superseded",
            expected_revision=1,
            expected_head=store.head(mission_id),
            operator_label="test-operator",
            rationale="Run the proposal after all.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=mission.created_at,
        )
    # And nothing can be claimed while revision 2 has no approval of its own.
    store.register_worker(
        mission_id,
        "worker-a",
        "deterministic",
        (TaskKind.WORK,),
        "command-register-before-approval",
        recorded_at=mission.created_at,
    )
    with pytest.raises(LeaseConflict, match="not dispatchable"):
        store.claim_task(
            mission_id,
            "work-a",
            "worker-a",
            "command-claim-before-approval",
            recorded_at=mission.created_at,
            ttl_seconds=30,
        )


def test_the_exported_document_is_what_the_user_actually_edits(tmp_path) -> None:
    """The export is text, and the text is the contract."""
    *_rest, _store, _mission, proposal = _mission_with_room_for_a_third_file(tmp_path)
    document = plan_to_yaml(proposal)
    assert "graphene plan revise" in document
    body = yaml.safe_load(document)
    assert [task["task_id"] for task in body["tasks"]] == [
        "assemble",
        "verify",
        "work-a",
        "work-z",
    ]
    assert plan_from_yaml(document) == proposal
