from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.adk import planning_input_sha256
from graphene.orchestration.models import (
    ArtifactContract,
    ArtifactRequirement,
    AttemptResult,
    CommandTemplate,
    EvidenceReference,
    Gate,
    GateDecision,
    GenericEvidenceLink,
    Mission,
    MissionAuthority,
    MissionEventType,
    MissionStatus,
    Plan,
    ProjectPolicy,
    PublicationDraft,
    ResourceBudget,
    ResourceReceipt,
    RetentionPolicy,
    Task,
    TaskKind,
    TaskState,
)
from graphene.orchestration.local_result import LocalResultReceipt
from graphene.orchestration.store import (
    LeaseConflict,
    MissionConflict,
    SQLiteMissionStore,
    StaleWorker,
)


NOW = datetime(2026, 1, 1, tzinfo=UTC)


class MemoryArtifacts:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], bytes] = {}
        self.completed: dict[
            str, tuple[str, str, str, tuple[EvidenceReference, ...]]
        ] = {}

    def put(self, kind: str, content: bytes) -> EvidenceReference:
        digest = sha256_hex(content)
        artifact_id = f"artifact-{digest[:32]}"
        self.values[(kind, artifact_id)] = content
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        return self.values.get((kind, artifact_id))

    def record_completed(
        self,
        evidence_id: str,
        *,
        mission_id: str,
        task_id: str,
        attempt_id: str,
        references: tuple[EvidenceReference, ...],
    ) -> None:
        self.completed[evidence_id] = (mission_id, task_id, attempt_id, references)

    def verify_attempt(
        self,
        evidence_id: str,
        *,
        mission_id: str,
        task_id: str,
        attempt_id: str,
        succeeded: bool,
        references: tuple[EvidenceReference, ...],
    ) -> bool:
        return succeeded and self.completed.get(evidence_id) == (
            mission_id,
            task_id,
            attempt_id,
            references,
        )


def _artifacts(store: SQLiteMissionStore) -> MemoryArtifacts:
    assert isinstance(store.artifact_resolver, MemoryArtifacts)
    return store.artifact_resolver


def _task_for_snapshot(store: SQLiteMissionStore, task_id: str) -> Task:
    return next(task for task in store.snapshot("mission-1").tasks if task.task_id == task_id)


def _command(label: str) -> str:
    return f"command-{label:0<16}"[:40]


def _policy(*, max_concurrency: int = 4) -> ProjectPolicy:
    return ProjectPolicy(
        policy_id="policy-1",
        revision=1,
        repo_id="repo-1",
        base_ref="main",
        base_sha="a" * 40,
        allowed_read_globs=("app/**", "out/**", "tests/**"),
        allowed_write_globs=("app/**", "out/**", "tests/**"),
        command_templates=(
            CommandTemplate(template_id="check", argv=("pytest",), timeout_seconds=60),
            CommandTemplate(template_id="edit", argv=("python", "edit.py"), timeout_seconds=60),
        ),
        agent_roles=("assembler", "verifier", "worker"),
        max_concurrency=max_concurrency,
        retry_limit=1,
        resource_budget=ResourceBudget(
            max_worker_seconds=600,
            max_attempts=100,
            max_artifact_bytes=1_000_000,
        ),
        retention=RetentionPolicy(retain_days=7),
    )


def _task(
    task_id: str,
    output_name: str,
    output_kind: str,
    output_path: str,
    *,
    kind: TaskKind = TaskKind.WORK,
    role: str = "worker",
    dependencies: tuple[str, ...] = (),
    inputs: tuple[ArtifactRequirement, ...] = (),
    priority: int = 1,
) -> Task:
    return Task(
        task_id=task_id,
        title=task_id,
        contract=f"Produce {output_name}.",
        kind=kind,
        dependencies=dependencies,
        assigned_role=role,
        read_paths=("app/source.py",),
        write_paths=(output_path,),
        allowed_commands=("edit",),
        inputs=inputs,
        expected_outputs=(
            ArtifactContract(
                name=output_name,
                kind=output_kind,
                paths=(output_path,),
            ),
        ),
        acceptance_checks=("check",),
        priority=priority,
        attempt_limit=2,
    )


def _plan(mission_id: str = "mission-1") -> Plan:
    work_a = _task("work-a", "patch-a", "patch", "app/a.py", priority=2)
    work_b = _task("work-b", "patch-b", "patch", "app/b.py", priority=1)
    assembly = _task(
        "assemble",
        "candidate",
        "candidate-patch",
        "out/candidate.patch",
        kind=TaskKind.ASSEMBLY,
        role="assembler",
        dependencies=("work-a", "work-b"),
        inputs=(
            ArtifactRequirement(producer_task_id="work-a", name="patch-a", kind="patch"),
            ArtifactRequirement(producer_task_id="work-b", name="patch-b", kind="patch"),
        ),
    )
    verify = _task(
        "verify",
        "verification",
        "test-receipt",
        "out/verification.json",
        kind=TaskKind.VERIFICATION,
        role="verifier",
        dependencies=("assemble",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="assemble",
                name="candidate",
                kind="candidate-patch",
            ),
        ),
    )
    return Plan(
        mission_id=mission_id,
        revision=1,
        tasks=tuple(sorted((assembly, verify, work_a, work_b), key=lambda item: item.task_id)),
        max_concurrency=2,
    )


def _mission(
    mission_id: str = "mission-1", *, creation_source: str = "operator"
) -> Mission:
    policy = _policy()
    return Mission(
        mission_id=mission_id,
        policy_id=policy.policy_id,
        policy_revision=policy.revision,
        repo_id=policy.repo_id,
        base_sha=policy.base_sha,
        goal="Implement the bounded mission.",
        success_criteria=("All checks pass.",),
        plan_revision=1,
        creation_source=creation_source,
        resource_budget=policy.resource_budget,
        created_at=NOW,
    )


def _planner_receipt_bytes(
    policy: ProjectPolicy,
    mission: Mission,
    plan: Plan,
    *,
    digest: str | None = None,
    planning_digest: str | None = None,
) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": 1,
            "truth_kind": "model_proposed",
            "driver": "gemini_live",
            "framework": "google_adk",
            "framework_version": "2.5.0",
            "client": "google_genai",
            "client_version": "1.0",
            "mission_id": mission.mission_id,
            "revision": plan.revision,
            "plan_sha256": digest
            or canonical_json_sha256(plan.model_dump(mode="json")),
            "planning_input_sha256": planning_digest
            or planning_input_sha256(
                policy,
                mission_id=mission.mission_id,
                revision=plan.revision,
                goal=mission.goal,
                success_criteria=mission.success_criteria,
            ),
            "requested_model": "gemini-3.5-flash",
            "returned_model": "gemini-3.5-flash",
            "session_id": "planner-session",
            "invocation_id": "planner-invocation",
            "credential_mode": "gemini_api",
            "model_call_count": 1,
            "input_bytes": 100,
            "output_bytes": 200,
            "telemetry_content_capture": "NO_CONTENT",
            "provider_usage": {"source": "unavailable"},
        }
    )


def _create(
    store: SQLiteMissionStore,
    *,
    mission_id: str = "mission-1",
    creation_source: str = "operator",
    approve: bool = True,
    policy: ProjectPolicy | None = None,
) -> None:
    policy = policy or _policy()
    if store.artifact_resolver is None:
        store.bind_artifact_resolver(MemoryArtifacts())
    mission = Mission.model_validate(
        {
            **_mission(mission_id, creation_source=creation_source).model_dump(
                mode="json"
            ),
            "resource_budget": policy.resource_budget.model_dump(mode="json"),
        }
    )
    store.create_mission(
        policy,
        mission,
        _plan(mission_id),
        _command(f"create-{mission_id}"),
        recorded_at=NOW,
    )
    if approve:
        store.approve_plan(
            mission_id,
            _command(f"approve-{mission_id}"),
            expected_revision=1,
            operator_label="api-operator",
            rationale="Approved by a bounded API request.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )


def _success(dispatch, task: Task, artifacts: MemoryArtifacts) -> AttemptResult:
    receipt_bytes = canonical_json_bytes(
        {
            "accepted_input_sha256": [
                item.sha256 for item in dispatch.input_publications
            ],
            "candidate_patch_sha256": (
                dispatch.input_publications[0].sha256
                if task.kind == TaskKind.VERIFICATION
                and len(dispatch.input_publications) == 1
                else None
            ),
            "exit_code": 0,
            "template_id": task.acceptance_checks[0],
            "timed_out": False,
        }
    )
    output_references = tuple(
        artifacts.put(
            output.kind,
            (
                receipt_bytes
                if output.kind == "test-receipt"
                else canonical_json_bytes(
                    {"attempt_id": dispatch.attempt_id, "output_name": output.name}
                )
            ),
        )
        for output in task.expected_outputs
    )
    check_reference = artifacts.put("test-receipt", receipt_bytes)
    references = tuple(
        {
            (item.kind, item.id, item.sha256): item
            for item in (*output_references, check_reference)
        }.values()
    )
    publications = tuple(
        PublicationDraft(
            output_name=output.name,
            kind=output.kind,
            sha256=reference.sha256,
            paths=output.paths,
        )
        for output, reference in zip(
            task.expected_outputs, output_references, strict=True
        )
    )
    evidence_id = f"evidence-{dispatch.attempt_id}"
    artifacts.record_completed(
        evidence_id,
        mission_id=dispatch.mission_id,
        task_id=dispatch.task_id,
        attempt_id=dispatch.attempt_id,
        references=references,
    )
    return AttemptResult(
        succeeded=True,
        result_code="passed",
        evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
        evidence_refs=references,
        publications=publications,
    )


def _complete_ready(
    store: SQLiteMissionStore,
    mission_id: str,
    *,
    at: datetime,
    round_number: int,
) -> tuple[str, ...]:
    store.refresh_ready(
        mission_id, _command(f"ready-{round_number}-{mission_id}"), recorded_at=at
    )
    completed = []
    for index, task in enumerate(store.ready_tasks(mission_id)):
        dispatch = store.claim_task(
            mission_id,
            task.task_id,
            f"worker-{index}",
            _command(f"claim-{round_number}-{index}-{mission_id}"),
            recorded_at=at,
            ttl_seconds=30,
        )
        store.complete_attempt(
            mission_id,
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            _success(dispatch, task, _artifacts(store)),
            _command(f"complete-{round_number}-{index}-{mission_id}"),
            recorded_at=at + timedelta(seconds=1),
            retry_backoff_seconds=0,
        )
        completed.append(task.task_id)
    return tuple(completed)


def test_creation_is_explicit_revision_bound_idempotent_and_restart_safe(tmp_path) -> None:
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    mission = _mission(creation_source="scripted_fixture")
    plan = _plan()
    command_id = _command("create")

    first = store.create_mission(
        _policy(), mission, plan, command_id, recorded_at=NOW
    )
    duplicate = store.create_mission(
        _policy(), mission, plan, command_id, recorded_at=NOW + timedelta(minutes=1)
    )

    assert duplicate == first
    assert store.snapshot("mission-1").mission.status == MissionStatus.PROPOSED
    assert not any(
        event.event_type == MissionEventType.PLAN_APPROVED
        for event in store.tail("mission-1", 0, 20)
    )
    proposed = next(
        event
        for event in store.tail("mission-1", 0, 20)
        if event.event_type == MissionEventType.PLAN_PROPOSED
    )
    assert proposed.truth_kind == TruthKind.SIMULATED_FIXTURE
    with pytest.raises(MissionConflict, match="revision changed"):
        store.approve_plan(
            "mission-1",
            _command("wrong-revision"),
            expected_revision=2,
            operator_label="automation",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )

    approved_head = store.approve_plan(
        "mission-1",
        _command("approve"),
        expected_revision=1,
        operator_label="automation",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    approved_retry = store.approve_plan(
        "mission-1",
        _command("approve"),
        expected_revision=1,
        operator_label="automation",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(minutes=1),
    )
    reopened = SQLiteMissionStore(path)
    snapshot = reopened.snapshot("mission-1")
    approved = reopened.tail("mission-1", first.seq, 10)[0]

    assert snapshot.mission.status == MissionStatus.RUNNING
    assert approved_retry == approved_head
    assert not hasattr(snapshot.policy, "command_templates")
    assert approved.payload["plan_revision"] == 1
    assert approved.truth_kind == TruthKind.SERVER_DERIVED
    assert approved.authority == MissionAuthority.MISSION_SERVICE
    assert reopened.verify("mission-1") == reopened.head("mission-1")
    with sqlite3.connect(path) as connection, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        connection.execute(
            "DELETE FROM mission_events WHERE mission_id = ? AND seq = 1",
            ("mission-1",),
        )


def test_model_proposed_plan_requires_exact_resolved_receipt_binding(tmp_path) -> None:
    artifacts = MemoryArtifacts()
    store = SQLiteMissionStore(
        tmp_path / "missions.sqlite", artifact_resolver=artifacts
    )
    policy, mission, plan = _policy(), _mission(), _plan()
    reference = artifacts.put(
        "plan-proposal-receipt", _planner_receipt_bytes(policy, mission, plan)
    )

    first = store.create_mission(
        policy,
        mission,
        plan,
        _command("create-model-plan"),
        plan_proposal_receipt=reference,
        recorded_at=NOW,
    )
    assert store.create_mission(
        policy,
        mission,
        plan,
        _command("create-model-plan"),
        plan_proposal_receipt=reference,
        recorded_at=NOW + timedelta(minutes=1),
    ) == first
    proposed = next(
        event
        for event in store.tail(mission.mission_id, 0, 10)
        if event.event_type == MissionEventType.PLAN_PROPOSED
    )
    assert proposed.truth_kind == TruthKind.MODEL_PROPOSED
    assert proposed.authority == MissionAuthority.PLANNER
    assert proposed.references == (reference,)
    assert proposed.payload["plan_proposal_driver"] == "gemini_live"
    assert proposed.payload["planning_input_sha256"] == planning_input_sha256(
        policy,
        mission_id=mission.mission_id,
        revision=plan.revision,
        goal=mission.goal,
        success_criteria=mission.success_criteria,
    )

    invalid_artifacts = MemoryArtifacts()
    invalid_store = SQLiteMissionStore(
        tmp_path / "invalid.sqlite", artifact_resolver=invalid_artifacts
    )
    invalid_reference = invalid_artifacts.put(
        "plan-proposal-receipt",
        _planner_receipt_bytes(policy, mission, plan, digest="f" * 64),
    )
    with pytest.raises(MissionConflict, match="bindings changed"):
        invalid_store.create_mission(
            policy,
            mission,
            plan,
            _command("create-invalid-model-plan"),
            plan_proposal_receipt=invalid_reference,
            recorded_at=NOW,
        )

    forged_inputs = {
        "goal": planning_input_sha256(
            policy,
            mission_id=mission.mission_id,
            revision=plan.revision,
            goal="A different goal.",
            success_criteria=mission.success_criteria,
        ),
        "policy": planning_input_sha256(
            policy.model_copy(update={"base_ref": "another-base"}),
            mission_id=mission.mission_id,
            revision=plan.revision,
            goal=mission.goal,
            success_criteria=mission.success_criteria,
        ),
    }
    for label, planning_digest in forged_inputs.items():
        forged_artifacts = MemoryArtifacts()
        forged_store = SQLiteMissionStore(
            tmp_path / f"forged-{label}.sqlite",
            artifact_resolver=forged_artifacts,
        )
        forged_reference = forged_artifacts.put(
            "plan-proposal-receipt",
            _planner_receipt_bytes(
                policy,
                mission,
                plan,
                planning_digest=planning_digest,
            ),
        )
        with pytest.raises(MissionConflict, match="bindings changed"):
            forged_store.create_mission(
                policy,
                mission,
                plan,
                _command(f"create-forged-{label}"),
                plan_proposal_receipt=forged_reference,
                recorded_at=NOW,
            )


def test_claim_heartbeat_expiry_and_fencing_reject_stale_workers(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready"), recorded_at=NOW)

    def claim(worker: str):
        return store.claim_task(
            "mission-1",
            "work-a",
            worker,
            _command(f"claim-{worker}"),
            recorded_at=NOW,
            ttl_seconds=10,
        )

    dispatches = []
    conflicts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim, worker) for worker in ("worker-a", "worker-b")]
        for future in futures:
            try:
                dispatches.append(future.result())
            except LeaseConflict as error:
                conflicts.append(error)

    assert len(dispatches) == len(conflicts) == 1
    first = dispatches[0]
    lease = store.heartbeat(
        "mission-1",
        first.attempt_id,
        first.worker_id,
        first.lease_id,
        first.fencing_token,
        _command("heartbeat"),
        recorded_at=NOW + timedelta(seconds=1),
        ttl_seconds=10,
    )
    assert lease.expires_at == NOW + timedelta(seconds=11)
    with pytest.raises(StaleWorker, match="stale"):
        store.heartbeat(
            "mission-1",
            first.attempt_id,
            first.worker_id,
            first.lease_id,
            first.fencing_token,
            _command("heartbeat-regressed"),
            recorded_at=NOW + timedelta(milliseconds=500),
            ttl_seconds=10,
        )
    assert store.expire_leases(
        "mission-1",
        _command("expire"),
        recorded_at=NOW + timedelta(seconds=12),
        retry_backoff_seconds=0,
    ) == (first.attempt_id,)
    store.refresh_ready(
        "mission-1",
        _command("ready-again"),
        recorded_at=NOW + timedelta(seconds=12),
    )
    second = store.claim_task(
        "mission-1",
        "work-a",
        "worker-c",
        _command("claim-again"),
        recorded_at=NOW + timedelta(seconds=12),
        ttl_seconds=10,
    )

    assert second.fencing_token == first.fencing_token + 1
    assert second.attempt_number == first.attempt_number + 1
    with pytest.raises(StaleWorker):
        store.heartbeat(
            "mission-1",
            first.attempt_id,
            first.worker_id,
            first.lease_id,
            first.fencing_token,
            _command("stale-heartbeat"),
            recorded_at=NOW + timedelta(seconds=12),
            ttl_seconds=10,
        )
    with pytest.raises(StaleWorker):
        store.complete_attempt(
            "mission-1",
            first.attempt_id,
            first.worker_id,
            first.lease_id,
            first.fencing_token,
            _success(
                first,
                next(item for item in _plan().tasks if item.task_id == "work-a"),
                _artifacts(store),
            ),
            _command("stale-complete"),
            recorded_at=NOW + timedelta(seconds=12),
            retry_backoff_seconds=0,
        )
    task = next(item for item in store.snapshot("mission-1").tasks if item.task_id == "work-a")
    store.complete_attempt(
        "mission-1",
        second.attempt_id,
        second.worker_id,
        second.lease_id,
        second.fencing_token,
        _success(second, task, _artifacts(store)),
        _command("complete-current"),
        recorded_at=NOW + timedelta(seconds=13),
        retry_backoff_seconds=0,
    )
    assert store.verify("mission-1") == store.head("mission-1")


def test_successful_publication_requires_resolved_attempt_artifact(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready-evidence"), recorded_at=NOW)
    task = next(item for item in store.ready_tasks("mission-1") if item.task_id == "work-a")
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-a",
        _command("claim-evidence"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    output = task.expected_outputs[0]
    missing_reference = EvidenceReference(
        kind=output.kind, id="artifact-missing", sha256="f" * 64
    )
    _artifacts(store).record_completed(
        "evidence-unbound",
        mission_id="mission-1",
        task_id=task.task_id,
        attempt_id=dispatch.attempt_id,
        references=(missing_reference,),
    )
    unbound = AttemptResult(
        succeeded=True,
        result_code="passed",
        evidence_link=GenericEvidenceLink(evidence_id="evidence-unbound"),
        evidence_refs=(missing_reference,),
        publications=(
            PublicationDraft(
                output_name=output.name,
                kind=output.kind,
                sha256="f" * 64,
                paths=output.paths,
            ),
        ),
    )

    with pytest.raises(MissionConflict, match="artifact is unavailable"):
        store.complete_attempt(
            "mission-1",
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            unbound,
            _command("complete-unbound"),
            recorded_at=NOW + timedelta(seconds=1),
            retry_backoff_seconds=0,
        )

    snapshot = store.snapshot("mission-1")
    assert not snapshot.publications
    assert next(item for item in snapshot.tasks if item.task_id == "work-a").state == TaskState.RUNNING


def test_mission_attempt_worker_time_and_artifact_budgets_are_authoritative(tmp_path) -> None:
    def policy_with(**budget_updates: int) -> ProjectPolicy:
        policy = _policy()
        budget = ResourceBudget.model_validate(
            {**policy.resource_budget.model_dump(mode="json"), **budget_updates}
        )
        return ProjectPolicy.model_validate(
            {
                **policy.model_dump(mode="json"),
                "resource_budget": budget.model_dump(mode="json"),
            }
        )

    attempt_store = SQLiteMissionStore(tmp_path / "attempt-budget.sqlite")
    _create(attempt_store, policy=policy_with(max_attempts=4))
    for index, task_id in enumerate(("work-a", "work-b")):
        at = NOW + timedelta(seconds=index * 4)
        attempt_store.refresh_ready(
            "mission-1", _command(f"budget-ready-{index}"), recorded_at=at
        )
        task = next(item for item in attempt_store.ready_tasks("mission-1") if item.task_id == task_id)
        first = attempt_store.claim_task(
            "mission-1",
            task_id,
            f"worker-{index}",
            _command(f"budget-claim-fail-{index}"),
            recorded_at=at,
            ttl_seconds=30,
        )
        attempt_store.complete_attempt(
            "mission-1",
            first.attempt_id,
            first.worker_id,
            first.lease_id,
            first.fencing_token,
            AttemptResult(succeeded=False, retryable=True, result_code="retryable"),
            _command(f"budget-fail-{index}"),
            recorded_at=at + timedelta(seconds=1),
            retry_backoff_seconds=0,
        )
        attempt_store.refresh_ready(
            "mission-1",
            _command(f"budget-retry-ready-{index}"),
            recorded_at=at + timedelta(seconds=1),
        )
        second = attempt_store.claim_task(
            "mission-1",
            task_id,
            f"worker-retry-{index}",
            _command(f"budget-claim-pass-{index}"),
            recorded_at=at + timedelta(seconds=1),
            ttl_seconds=30,
        )
        attempt_store.complete_attempt(
            "mission-1",
            second.attempt_id,
            second.worker_id,
            second.lease_id,
            second.fencing_token,
            _success(second, _task_for_snapshot(attempt_store, task_id), _artifacts(attempt_store)),
            _command(f"budget-pass-{index}"),
            recorded_at=at + timedelta(seconds=2),
            retry_backoff_seconds=0,
        )
    attempt_store.refresh_ready(
        "mission-1", _command("budget-assembly-ready"), recorded_at=NOW + timedelta(seconds=9)
    )
    with pytest.raises(LeaseConflict, match="attempt budget"):
        attempt_store.claim_task(
            "mission-1",
            "assemble",
            "worker-assembly",
            _command("budget-assembly-claim"),
            recorded_at=NOW + timedelta(seconds=9),
            ttl_seconds=30,
        )

    time_store = SQLiteMissionStore(tmp_path / "time-budget.sqlite")
    _create(time_store, policy=policy_with(max_worker_seconds=10))
    time_store.refresh_ready("mission-1", _command("time-ready"), recorded_at=NOW)
    time_store.claim_task(
        "mission-1",
        "work-a",
        "worker-a",
        _command("time-first"),
        recorded_at=NOW,
        ttl_seconds=6,
    )
    with pytest.raises(LeaseConflict, match="worker-time budget"):
        time_store.claim_task(
            "mission-1",
            "work-b",
            "worker-b",
            _command("time-second"),
            recorded_at=NOW,
            ttl_seconds=6,
        )

    artifact_store = SQLiteMissionStore(tmp_path / "artifact-budget.sqlite")
    _create(artifact_store, policy=policy_with(max_artifact_bytes=16))
    artifact_store.refresh_ready(
        "mission-1", _command("artifact-ready"), recorded_at=NOW
    )
    task = next(item for item in artifact_store.ready_tasks("mission-1") if item.task_id == "work-a")
    dispatch = artifact_store.claim_task(
        "mission-1",
        task.task_id,
        "worker-a",
        _command("artifact-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    with pytest.raises(MissionConflict, match="artifact budget"):
        artifact_store.complete_attempt(
            "mission-1",
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            _success(dispatch, task, _artifacts(artifact_store)),
            _command("artifact-complete"),
            recorded_at=NOW + timedelta(seconds=1),
            retry_backoff_seconds=0,
        )


def test_gate_resource_and_operator_commands_preserve_non_tty_truth(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    gate = Gate(
        gate_id="gate-1",
        mission_id="mission-1",
        reason="Choose whether to continue.",
        allowed_decisions=(
            GateDecision(value="approve", consequence="Continue."),
            GateDecision(value="reject", consequence="Stop."),
        ),
        truth_kind=TruthKind.SERVER_DERIVED,
    )
    store.request_gate(gate, _command("gate-request"), recorded_at=NOW)
    store.decide_gate(
        "mission-1",
        "gate-1",
        "approve",
        _command("gate-decision"),
        operator_label="non-tty-api",
        rationale="Bounded operator-labeled input.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )

    unavailable = ResourceReceipt(
        receipt_id="resource-1",
        mission_id="mission-1",
        subject="remote-tool",
        source="resource-sentinel",
        platform="remote",
        scope="remote-request",
        semantics="provider-metric-unavailable",
        units="bytes",
        observed_from=NOW,
        observed_until=NOW,
        value=None,
        attribution_quality="unavailable",
        threshold=100,
        action="advisory-only",
    )
    store.record_resource_summary(
        unavailable, _command("resource-unavailable"), recorded_at=NOW
    )
    crossed = unavailable.model_copy(
        update={
            "receipt_id": "resource-2",
            "platform": "linux",
            "scope": "isolated-process-tree",
            "semantics": "sampled-current-rss",
            "value": 200.0,
            "attribution_quality": "measured_bound",
            "action": "pause-new-dispatch",
        }
    )
    store.record_resource_summary(crossed, _command("resource-crossed"), recorded_at=NOW)
    store.pause(
        "mission-1",
        _command("pause"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    store.resume(
        "mission-1",
        _command("resume"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    store.cancel(
        "mission-1",
        _command("cancel"),
        operator_label="non-tty-api",
        rationale="Cancelled from automation.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )

    events = store.tail("mission-1", 0, 100)
    operator_types = {
        MissionEventType.PLAN_APPROVED,
        MissionEventType.GATE_DECIDED,
        MissionEventType.OPERATOR_PAUSED,
        MissionEventType.OPERATOR_RESUMED,
        MissionEventType.OPERATOR_CANCELLED,
    }
    operator_events = [event for event in events if event.event_type in operator_types]
    assert operator_events
    assert all(event.truth_kind == TruthKind.SERVER_DERIVED for event in operator_events)
    assert all(event.authority == MissionAuthority.MISSION_SERVICE for event in operator_events)
    assert any(event.event_type == MissionEventType.RESOURCE_SUMMARY_RECORDED for event in events)
    assert any(event.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED for event in events)
    assert store.snapshot("mission-1").gates[0].resolution == "approve"
    assert store.snapshot("mission-1").mission.status == MissionStatus.CANCELLED
    with pytest.raises(ValidationError, match="only unavailable"):
        ResourceReceipt.model_validate(
            {**unavailable.model_dump(mode="json"), "value": 1}
        )


def test_task_gate_blocks_dispatch_until_an_allowed_decision(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    gate = Gate(
        gate_id="gate-task",
        mission_id="mission-1",
        task_id="work-a",
        reason="Confirm the bounded work item.",
        allowed_decisions=(
            GateDecision(value="continue", consequence="Return the task to readiness."),
        ),
        truth_kind=TruthKind.SERVER_DERIVED,
    )
    store.request_gate(gate, _command("task-gate"), recorded_at=NOW)
    store.refresh_ready("mission-1", _command("task-gate-ready"), recorded_at=NOW)

    assert tuple(task.task_id for task in store.ready_tasks("mission-1")) == ("work-b",)
    assert _task_for_snapshot(store, "work-a").state == TaskState.BLOCKED
    with pytest.raises(LeaseConflict):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-a",
            _command("task-gate-early-claim"),
            recorded_at=NOW,
            ttl_seconds=30,
        )

    store.decide_gate(
        "mission-1",
        gate.gate_id,
        "continue",
        _command("task-gate-decision"),
        operator_label="non-tty-api",
        rationale="Proceed with the accepted scope.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    assert _task_for_snapshot(store, "work-a").state == TaskState.READY
    dispatch = store.claim_task(
        "mission-1",
        "work-a",
        "worker-a",
        _command("task-gate-late-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    assert dispatch.task_id == "work-a"
    assert store.verify("mission-1") == store.head("mission-1")


def test_reassign_reprioritize_and_replan_request_are_safe_and_evented(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.reassign_task(
        "mission-1",
        "work-b",
        "assembler",
        _command("reassign"),
        operator_label="non-tty-api",
        rationale="Move queued work to an allowlisted role.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    store.reprioritize_task(
        "mission-1",
        "work-b",
        99,
        _command("reprioritize"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    changed = _task_for_snapshot(store, "work-b")
    assert changed.assigned_role == "assembler"
    assert changed.priority == 99

    store.refresh_ready("mission-1", _command("ready-operator"), recorded_at=NOW)
    dispatch = store.claim_task(
        "mission-1",
        "work-b",
        "worker-b",
        _command("claim-operator"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    with pytest.raises(MissionConflict, match="current state"):
        store.reassign_task(
            "mission-1",
            dispatch.task_id,
            "worker",
            _command("reassign-running"),
            operator_label="non-tty-api",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )
    head = store.request_replan(
        "mission-1",
        _command("request-replan"),
        reason="The accepted revision needs a new explicit successor.",
        operator_label="non-tty-api",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    assert store.request_replan(
        "mission-1",
        _command("request-replan"),
        reason="The accepted revision needs a new explicit successor.",
        operator_label="non-tty-api",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(minutes=1),
    ) == head
    snapshot = store.snapshot("mission-1")
    assert snapshot.mission.status == MissionStatus.PAUSED
    assert snapshot.plan.revision == 1
    assert store.verify("mission-1") == store.head("mission-1")


def test_verification_receipt_must_bind_exact_accepted_assembly_candidate(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
    store.refresh_ready(
        "mission-1", _command("ready-verification"), recorded_at=NOW + timedelta(seconds=4)
    )
    task = store.ready_tasks("mission-1")[0]
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-verifier",
        _command("claim-verification"),
        recorded_at=NOW + timedelta(seconds=4),
        ttl_seconds=30,
    )
    valid = _success(dispatch, task, _artifacts(store))
    bad_bytes = canonical_json_bytes(
        {
            "accepted_input_sha256": [
                item.sha256 for item in dispatch.input_publications
            ],
            "candidate_patch_sha256": "f" * 64,
            "exit_code": 0,
            "template_id": task.acceptance_checks[0],
            "timed_out": False,
        }
    )
    bad_reference = _artifacts(store).put("test-receipt", bad_bytes)
    bad = AttemptResult(
        succeeded=True,
        result_code="passed",
        evidence_link=valid.evidence_link,
        evidence_refs=(bad_reference,),
        publications=(
            PublicationDraft(
                output_name=task.expected_outputs[0].name,
                kind="test-receipt",
                sha256=bad_reference.sha256,
                paths=task.expected_outputs[0].paths,
            ),
        ),
    )
    assert isinstance(bad.evidence_link, GenericEvidenceLink)
    _artifacts(store).record_completed(
        bad.evidence_link.evidence_id,
        mission_id="mission-1",
        task_id=task.task_id,
        attempt_id=dispatch.attempt_id,
        references=bad.evidence_refs,
    )

    with pytest.raises(MissionConflict, match="bound to the candidate"):
        store.complete_attempt(
            "mission-1",
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            bad,
            _command("complete-sibling-receipt"),
            recorded_at=NOW + timedelta(seconds=5),
            retry_backoff_seconds=0,
        )

    valid = _success(dispatch, task, _artifacts(store))
    store.complete_attempt(
        "mission-1",
        dispatch.attempt_id,
        dispatch.worker_id,
        dispatch.lease_id,
        dispatch.fencing_token,
        valid,
        _command("complete-bound-receipt"),
        recorded_at=NOW + timedelta(seconds=5),
        retry_backoff_seconds=0,
    )
    store.enter_awaiting_result(
        "mission-1", _command("await-bound"), recorded_at=NOW + timedelta(seconds=6)
    )
    assert store.snapshot("mission-1").mission.status == MissionStatus.AWAITING_RESULT


@pytest.mark.parametrize("approve", (True, False))
def test_final_decision_binds_candidate_and_verification_receipt(tmp_path, approve: bool) -> None:
    mission_id = "mission-approve" if approve else "mission-reject"
    store = SQLiteMissionStore(tmp_path / f"{mission_id}.sqlite")
    _create(store, mission_id=mission_id)
    assert _complete_ready(store, mission_id, at=NOW, round_number=1) == (
        "work-a",
        "work-b",
    )
    assert _complete_ready(store, mission_id, at=NOW + timedelta(seconds=2), round_number=2) == (
        "assemble",
    )
    assert _complete_ready(store, mission_id, at=NOW + timedelta(seconds=4), round_number=3) == (
        "verify",
    )
    store.enter_awaiting_result(
        mission_id, _command(f"await-{mission_id}"), recorded_at=NOW + timedelta(seconds=6)
    )
    snapshot = store.snapshot(mission_id)
    candidate = next(item for item in snapshot.publications if item.task_id == "assemble")
    with pytest.raises(MissionConflict, match="digest changed"):
        store.approve_final_result(
            mission_id,
            _command(f"wrong-final-{mission_id}"),
            expected_candidate_sha256="f" * 64,
            operator_label="non-tty-api",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=7),
        )
    decision = store.approve_final_result if approve else store.reject_final_result
    decision_head = decision(
        mission_id,
        _command(f"final-{mission_id}"),
        expected_candidate_sha256=candidate.sha256,
        operator_label="non-tty-api",
        rationale="Reviewed the isolated candidate.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=7),
    )
    decision_retry = decision(
        mission_id,
        _command(f"final-{mission_id}"),
        expected_candidate_sha256=candidate.sha256,
        operator_label="non-tty-api",
        rationale="Reviewed the isolated candidate.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(minutes=1),
    )

    final_event = store.tail(mission_id, snapshot.head.seq, 10)[0]
    assert final_event.payload["candidate_sha256"] == candidate.sha256
    assert decision_retry == decision_head
    assert len(final_event.references) == 2
    assert final_event.truth_kind == TruthKind.SERVER_DERIVED
    assert store.snapshot(mission_id).mission.status == (
        MissionStatus.COMPLETED if approve else MissionStatus.REJECTED
    )
    assert store.verify(mission_id) == store.head(mission_id)
    if approve:
        verification = next(
            item for item in store.snapshot(mission_id).publications if item.task_id == "verify"
        )
        verification_attempt = next(
            item
            for item in store.snapshot(mission_id).attempts
            if item.attempt_id == verification.attempt_id
        )
        verification_reference = next(
            item
            for item in verification_attempt.evidence_refs
            if item.kind == verification.kind and item.sha256 == verification.sha256
        )
        local_receipt = LocalResultReceipt.create(
            mission_id=mission_id,
            decision="approve",
            truth_kind=TruthKind.SERVER_DERIVED,
            operator_label="non-tty-api",
            rationale_sha256=sha256_hex(b"Reviewed the isolated candidate."),
            base_sha="a" * 40,
            candidate_patch_sha256=candidate.sha256,
            verification_id=verification_reference.id,
            verification_sha256=verification.sha256,
            changed_paths=("app/a.py",),
            local_commit_sha="c" * 40,
            result_ref="refs/graphene/results/" + sha256_hex(mission_id.encode())[:24],
            outcome="isolated_local_commit",
            pushed=False,
            pull_request_created=False,
            deployed=False,
        )
        receipt_bytes = canonical_json_bytes(local_receipt.model_dump(mode="json"))
        receipt = _artifacts(store).put(
            "local-result-receipt",
            receipt_bytes,
        )
        store.bind_local_commit_verifier(lambda raw: raw == receipt_bytes)
        forged_receipt = LocalResultReceipt.create(
            **{
                **local_receipt.model_dump(
                    mode="python", exclude={"receipt_id", "receipt_sha256"}
                ),
                "changed_paths": ("app/forged.py",),
            }
        )
        forged_reference = _artifacts(store).put(
            "local-result-receipt",
            canonical_json_bytes(forged_receipt.model_dump(mode="json")),
        )
        with pytest.raises(MissionConflict, match="Git proof is not authoritative"):
            store.record_isolated_commit(
                mission_id,
                "c" * 40,
                forged_reference,
                _command("commit-forged"),
                recorded_at=NOW + timedelta(seconds=8),
            )
        wrong_attribution = LocalResultReceipt.create(
            **{
                **local_receipt.model_dump(
                    mode="python", exclude={"receipt_id", "receipt_sha256"}
                ),
                "operator_label": "another-operator",
            }
        )
        wrong_attribution_reference = _artifacts(store).put(
            "local-result-receipt",
            canonical_json_bytes(wrong_attribution.model_dump(mode="json")),
        )
        with pytest.raises(MissionConflict, match="bindings changed"):
            store.record_isolated_commit(
                mission_id,
                "c" * 40,
                wrong_attribution_reference,
                _command("commit-wrong-attribution"),
                recorded_at=NOW + timedelta(seconds=8),
            )
        with pytest.raises(MissionConflict, match="bindings changed"):
            store.record_isolated_commit(
                mission_id,
                "d" * 40,
                receipt,
                _command("commit-mismatch"),
                recorded_at=NOW + timedelta(seconds=8),
            )
        commit_head = store.record_isolated_commit(
            mission_id,
            "c" * 40,
            receipt,
            _command("commit"),
            recorded_at=NOW + timedelta(seconds=8),
        )
        commit_retry = store.record_isolated_commit(
            mission_id,
            "c" * 40,
            receipt,
            _command("commit"),
            recorded_at=NOW + timedelta(minutes=2),
        )
        isolated = store.tail(mission_id, final_event.seq, 10)[0]
        assert commit_retry == commit_head
        assert isolated.payload["pushed"] is False
        assert isolated.payload["pull_request_created"] is False
        with pytest.raises(MissionConflict, match="already recorded"):
            store.record_isolated_commit(
                mission_id,
                "d" * 40,
                receipt,
                _command("second-commit"),
                recorded_at=NOW + timedelta(minutes=3),
            )


def test_explicit_retry_uses_server_truth_and_restores_failed_mission(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready"), recorded_at=NOW)
    task = next(item for item in store.ready_tasks("mission-1") if item.task_id == "work-a")
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-a",
        _command("claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    store.complete_attempt(
        "mission-1",
        dispatch.attempt_id,
        dispatch.worker_id,
        dispatch.lease_id,
        dispatch.fencing_token,
        AttemptResult(succeeded=False, result_code="failed"),
        _command("failed"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )
    store.retry_task(
        "mission-1",
        "work-a",
        _command("retry"),
        operator_label="non-tty-api",
        rationale="Retry after operator review.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )

    snapshot = store.snapshot("mission-1")
    task = next(item for item in snapshot.tasks if item.task_id == "work-a")
    retry_events = [
        event
        for event in store.tail("mission-1", 0, 100)
        if event.event_type in {MissionEventType.OPERATOR_RESUMED, MissionEventType.TASK_RETRIED}
        and event.payload.get("reason_code") == "operator_retry"
    ]
    assert snapshot.mission.status == MissionStatus.RUNNING
    assert task.state == TaskState.RETRYING
    assert retry_events and all(
        event.truth_kind == TruthKind.SERVER_DERIVED
        and event.authority == MissionAuthority.MISSION_SERVICE
        for event in retry_events
    )
