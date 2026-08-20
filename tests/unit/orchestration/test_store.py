from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from graphene.artifact_envelope import (
    ArtifactEnvelopeV2,
    DirectArtifactInputV2,
    verify_artifact_envelope,
)
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.adk import planning_input_sha256
from graphene.orchestration.evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    SQLiteAttemptEvidenceStore,
)
from graphene.orchestration.models import (
    ArtifactContract,
    ArtifactEnvelopeReferenceV2,
    ArtifactRequirement,
    AttemptResult,
    AttemptState,
    CommandTemplate,
    Criterion,
    CriterionVerificationKind,
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
    PublishedArtifactReferenceV2,
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
    BudgetExhausted,
    LeaseConflict,
    MissionConflict,
    MissionStoreError,
    SQLiteMissionStore,
    StaleWorker,
)
from graphene.orchestration.validation import PlanValidationError


NOW = datetime(2026, 1, 1, tzinfo=UTC)


class MemoryArtifacts:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], bytes] = {}
        self.envelopes: dict[str, ArtifactEnvelopeV2] = {}
        self.authority: dict[str, tuple[str, str]] = {}
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

    def authorize(self, mission_id: str, policy: ProjectPolicy) -> None:
        self.authority[mission_id] = (
            canonical_json_sha256(policy.model_dump(mode="json")),
            policy.base_sha,
        )

    def put_enveloped(
        self,
        dispatch,
        *,
        output_name: str,
        kind: str,
        content: bytes,
    ) -> tuple[EvidenceReference, ArtifactEnvelopeReferenceV2]:
        policy_sha256, base_sha = self.authority[dispatch.mission_id]
        direct_inputs = tuple(
            sorted(
                (
                    DirectArtifactInputV2(
                        publication_id=item.publication_id,
                        producer_task_id=item.producer_task_id,
                        output_name=item.output_name,
                        artifact_envelope_sha256=item.artifact_envelope_sha256,
                    )
                    for item in dispatch.input_publications
                    if isinstance(item, PublishedArtifactReferenceV2)
                ),
                key=lambda item: (
                    item.producer_task_id,
                    item.output_name,
                    item.publication_id,
                    item.artifact_envelope_sha256,
                ),
            )
        )
        envelope = ArtifactEnvelopeV2.create(
            content,
            mission_id=dispatch.mission_id,
            plan_revision=dispatch.plan_revision,
            plan_sha256=dispatch.plan_sha256,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            fencing_token=dispatch.fencing_token,
            policy_sha256=policy_sha256,
            base_git_commit=base_sha,
            direct_inputs=direct_inputs,
            output_name=output_name,
            artifact_kind=kind,
            media_type=(
                "application/vnd.graphene.git-patch"
                if kind == "patch"
                else "application/vnd.graphene.check-receipt+json"
            ),
            created_by="trusted-worker-wrapper",
        )
        reference = self.put(kind, content)
        self.envelopes[envelope.artifact_envelope_sha256] = envelope
        return reference, ArtifactEnvelopeReferenceV2(
            schema_version=2,
            artifact_id=reference.id,
            producer_task_id=dispatch.task_id,
            output_name=output_name,
            kind=kind,
            media_type=envelope.media_type,
            byte_count=envelope.byte_count,
            content_sha256=envelope.content_sha256,
            artifact_envelope_sha256=envelope.artifact_envelope_sha256,
        )

    def resolve_enveloped(
        self, reference: ArtifactEnvelopeReferenceV2
    ) -> bytes | None:
        content = self.resolve(reference.kind, reference.artifact_id)
        envelope = self.envelopes.get(reference.artifact_envelope_sha256)
        if content is None or envelope is None:
            return None
        try:
            verify_artifact_envelope(envelope, content)
        except ValueError:
            return None
        return content

    def verify_enveloped(
        self,
        reference: ArtifactEnvelopeReferenceV2,
        *,
        expected: dict[str, object],
    ) -> bool:
        content = self.resolve_enveloped(reference)
        envelope = self.envelopes.get(reference.artifact_envelope_sha256)
        if content is None or envelope is None:
            return False
        try:
            verify_artifact_envelope(envelope, content, expected=expected)
        except ValueError:
            return False
        return True

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
        result_code: str,
        references: tuple[EvidenceReference, ...],
        plan_revision: int,
        fencing_token: int,
        policy_sha256: str,
        base_sha: str,
        template_id: str,
        template_sha256: str,
        accepted_inputs: tuple[EvidenceReference, ...],
        candidate_references: tuple[EvidenceReference, ...],
    ) -> bool:
        bindings_are_well_formed = (
            result_code == "passed"
            and plan_revision >= 1
            and fencing_token >= 1
            and len(policy_sha256) == len(template_sha256) == 64
            and len(base_sha) == 40
            and bool(template_id)
            and isinstance(accepted_inputs, tuple)
            and isinstance(candidate_references, tuple)
        )
        return (
            succeeded
            and bindings_are_well_formed
            and self.completed.get(evidence_id)
            == (
                mission_id,
                task_id,
                attempt_id,
                references,
            )
        )


def _artifacts(store: SQLiteMissionStore) -> MemoryArtifacts:
    assert isinstance(store.artifact_resolver, MemoryArtifacts)
    return store.artifact_resolver


def _task_for_snapshot(store: SQLiteMissionStore, task_id: str) -> Task:
    return next(
        task for task in store.snapshot("mission-1").tasks if task.task_id == task_id
    )


def _command(label: str) -> str:
    return f"command-{label:0<16}"[:40]


def _register_worker(
    store: SQLiteMissionStore,
    worker_id: str,
    *,
    mission_id: str = "mission-1",
    capabilities: tuple[TaskKind, ...],
    at: datetime = NOW,
) -> None:
    digest = canonical_json_sha256(
        (mission_id, worker_id, "test_runtime", capabilities)
    )
    store.register_worker(
        mission_id,
        worker_id,
        "test_runtime",
        capabilities,
        f"register_{digest[:32]}",
        recorded_at=at,
    )


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
            CommandTemplate(
                template_id="edit", argv=("python", "edit.py"), timeout_seconds=60
            ),
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
        "patch",
        "out/candidate.patch",
        kind=TaskKind.ASSEMBLY,
        role="assembler",
        dependencies=("work-a", "work-b"),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-a", name="patch-a", kind="patch"
            ),
            ArtifactRequirement(
                producer_task_id="work-b", name="patch-b", kind="patch"
            ),
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
                kind="patch",
            ),
        ),
    )
    return Plan(
        mission_id=mission_id,
        revision=1,
        criteria=(
            Criterion(
                criterion_id="criterion-checks",
                description="All checks pass.",
                producer_task_ids=("work-a", "work-b"),
                verification_kind=CriterionVerificationKind.DETERMINISTIC_CHECK,
                verifier_task_id="verify",
                verifier_id="check",
            ),
        ),
        tasks=tuple(
            sorted((assembly, verify, work_a, work_b), key=lambda item: item.task_id)
        ),
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
    if isinstance(store.artifact_resolver, MemoryArtifacts):
        store.artifact_resolver.authorize(mission_id, policy)
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
            expected_head=store.head(mission_id),
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
    output_artifacts = tuple(
        artifacts.put_enveloped(
            dispatch,
            output_name=output.name,
            kind=output.kind,
            content=(
                receipt_bytes
                if output.kind == "test-receipt"
                else canonical_json_bytes(
                    {"attempt_id": dispatch.attempt_id, "output_name": output.name}
                )
            ),
        )
        for output in task.expected_outputs
    )
    output_references = tuple(item[0] for item in output_artifacts)
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
            artifact=envelope,
            paths=output.paths,
        )
        for output, (reference, envelope) in zip(
            task.expected_outputs, output_artifacts, strict=True
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
        artifact_envelopes=tuple(
            sorted(
                (item[1] for item in output_artifacts),
                key=lambda item: item.artifact_envelope_sha256,
            )
        ),
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
        worker_id = f"worker-{round_number}-{index}"
        _register_worker(
            store,
            worker_id,
            mission_id=mission_id,
            capabilities=(task.kind,),
            at=at,
        )
        dispatch = store.claim_task(
            mission_id,
            task.task_id,
            worker_id,
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


def test_creation_is_explicit_revision_bound_idempotent_and_restart_safe(
    tmp_path,
) -> None:
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    mission = _mission(creation_source="scripted_fixture")
    plan = _plan()
    command_id = _command("create")

    first = store.create_mission(_policy(), mission, plan, command_id, recorded_at=NOW)
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
    proposed_head = store.head("mission-1")
    with pytest.raises(MissionConflict, match="revision changed"):
        store.approve_plan(
            "mission-1",
            _command("wrong-revision"),
            expected_revision=2,
            expected_head=proposed_head,
            operator_label="automation",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )

    approved_head = store.approve_plan(
        "mission-1",
        _command("approve"),
        expected_revision=1,
        expected_head=proposed_head,
        operator_label="automation",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    approved_retry = store.approve_plan(
        "mission-1",
        _command("approve"),
        expected_revision=1,
        expected_head=proposed_head,
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
    with (
        sqlite3.connect(path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        connection.execute(
            "DELETE FROM mission_events WHERE mission_id = ? AND seq = 1",
            ("mission-1",),
        )


def test_plan_rejection_is_revision_bound_attributed_idempotent_and_terminal(
    tmp_path,
) -> None:
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    mission = _mission(creation_source="operator")
    store.create_mission(
        _policy(), mission, _plan(), _command("create"), recorded_at=NOW
    )
    proposed_head = store.head("mission-1")

    with pytest.raises(MissionConflict, match="revision changed"):
        store.reject_plan(
            "mission-1",
            _command("reject-wrong-revision"),
            expected_revision=2,
            expected_head=proposed_head,
            operator_label="reviewer",
            rationale="The proposed scope is too broad.",
            truth_kind=TruthKind.HUMAN_ATTESTED,
            recorded_at=NOW,
        )

    command_id = _command("reject-plan")
    rejected_head = store.reject_plan(
        "mission-1",
        command_id,
        expected_revision=1,
        expected_head=proposed_head,
        operator_label="reviewer",
        rationale="The proposed scope is too broad.",
        truth_kind=TruthKind.HUMAN_ATTESTED,
        recorded_at=NOW,
    )
    duplicate = SQLiteMissionStore(path).reject_plan(
        "mission-1",
        command_id,
        expected_revision=1,
        expected_head=proposed_head,
        operator_label="reviewer",
        rationale="The proposed scope is too broad.",
        truth_kind=TruthKind.HUMAN_ATTESTED,
        recorded_at=NOW + timedelta(minutes=1),
    )

    reopened = SQLiteMissionStore(path)
    snapshot = reopened.snapshot("mission-1")
    rejected = reopened.tail("mission-1", proposed_head.seq, 1)[0]
    assert duplicate == rejected_head == snapshot.head
    assert snapshot.mission.status == MissionStatus.REJECTED
    assert rejected.event_type == MissionEventType.PLAN_REJECTED
    assert rejected.payload == {
        "operator_label": "reviewer",
        "operator_rationale": "The proposed scope is too broad.",
        "plan_revision": 1,
        "status": "rejected",
    }
    assert rejected.truth_kind == TruthKind.HUMAN_ATTESTED
    assert rejected.authority == MissionAuthority.OPERATOR
    assert reopened.verify("mission-1") == rejected_head

    with pytest.raises(MissionConflict, match="reused with another request"):
        reopened.reject_plan(
            "mission-1",
            command_id,
            expected_revision=1,
            expected_head=proposed_head,
            operator_label="reviewer",
            rationale="A different decision payload.",
            truth_kind=TruthKind.HUMAN_ATTESTED,
            recorded_at=NOW,
        )


def test_creation_binds_plan_criteria_to_mission_criteria(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    plan = _plan()
    mismatched = plan.model_copy(
        update={
            "criteria": (
                plan.criteria[0].model_copy(
                    update={"description": "A different outcome passes."}
                ),
            )
        }
    )

    with pytest.raises(MissionConflict, match="bindings do not match"):
        store.create_mission(
            _policy(),
            _mission(),
            mismatched,
            _command("criterion-mismatch"),
            recorded_at=NOW,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_attempts", 9),
        ("max_worker_seconds", 601),
        ("max_artifact_bytes", 1_000_001),
    ),
)
def test_mission_budget_must_exactly_match_policy(
    tmp_path, field: str, value: int
) -> None:
    policy = _policy()
    budget = policy.resource_budget.model_copy(update={field: value})
    mission = _mission().model_copy(update={"resource_budget": budget})
    store = SQLiteMissionStore(tmp_path / f"{field}.sqlite")

    with pytest.raises(MissionConflict, match="bindings do not match"):
        store.create_mission(
            policy,
            mission,
            _plan(),
            _command(f"create-{field}-mismatch"),
            recorded_at=NOW,
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
    assert (
        store.create_mission(
            policy,
            mission,
            plan,
            _command("create-model-plan"),
            plan_proposal_receipt=reference,
            recorded_at=NOW + timedelta(minutes=1),
        )
        == first
    )
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
    for worker in ("worker-a", "worker-b"):
        _register_worker(store, worker, capabilities=(TaskKind.WORK,))

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
    _register_worker(
        store,
        "worker-c",
        capabilities=(TaskKind.WORK,),
        at=NOW + timedelta(seconds=12),
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
    task = next(
        item for item in store.snapshot("mission-1").tasks if item.task_id == "work-a"
    )
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


def test_registration_capabilities_revocation_and_effect_fence_are_authoritative(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("worker-ready"), recorded_at=NOW)

    with pytest.raises(LeaseConflict, match="registration"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-unregistered",
            _command("claim-unregistered"),
            recorded_at=NOW,
            ttl_seconds=10,
        )
    _register_worker(store, "worker-wrong-kind", capabilities=(TaskKind.ASSEMBLY,))
    with pytest.raises(LeaseConflict, match="capability"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-wrong-kind",
            _command("claim-wrong-kind"),
            recorded_at=NOW,
            ttl_seconds=10,
        )

    _register_worker(store, "worker-work", capabilities=(TaskKind.WORK,))
    dispatch = store.claim_task(
        "mission-1",
        "work-a",
        "worker-work",
        _command("claim-work-kind"),
        recorded_at=NOW,
        ttl_seconds=10,
    )
    store.assert_fence(dispatch, recorded_at=NOW + timedelta(seconds=1))
    with pytest.raises(StaleWorker, match="stale"):
        store.assert_fence(dispatch, recorded_at=NOW + timedelta(seconds=10))

    store.revoke_worker(
        "mission-1",
        "worker-work",
        "runtime_retired",
        _command("revoke-worker-work"),
        recorded_at=NOW + timedelta(seconds=2),
    )
    with pytest.raises(StaleWorker, match="registration"):
        store.assert_fence(dispatch, recorded_at=NOW + timedelta(seconds=3))
    with pytest.raises(LeaseConflict, match="revoked"):
        store.recover_dispatches(
            "mission-1", ("worker-work",), recorded_at=NOW + timedelta(seconds=3)
        )
    event_types = {event.event_type for event in store.tail("mission-1", 0, 100)}
    assert MissionEventType.WORKER_REGISTERED in event_types
    assert MissionEventType.WORKER_REVOKED in event_types
    assert store.verify("mission-1") == store.head("mission-1")

    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER mission_workers_no_update")
        connection.execute(
            "UPDATE mission_workers SET runtime_id = 'forged_runtime' "
            "WHERE mission_id = 'mission-1' AND worker_id = 'worker-work'"
        )
    with pytest.raises(MissionStoreError, match="materialized state"):
        store.verify("mission-1")


def test_successful_publication_requires_resolved_attempt_artifact(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready-evidence"), recorded_at=NOW)
    task = next(
        item for item in store.ready_tasks("mission-1") if item.task_id == "work-a"
    )
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))
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
    assert (
        next(item for item in snapshot.tasks if item.task_id == "work-a").state
        == TaskState.RUNNING
    )


def test_real_stores_reject_fabricated_pass_without_trusted_check(tmp_path) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    store = SQLiteMissionStore(tmp_path / "missions.sqlite", artifact_resolver=evidence)
    _create(store)
    store.refresh_ready("mission-1", _command("forgery-ready"), recorded_at=NOW)
    task = next(
        item for item in store.ready_tasks("mission-1") if item.task_id == "work-a"
    )
    _register_worker(store, "worker-forgery", capabilities=(TaskKind.WORK,))
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-forgery",
        _command("forgery-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    patch = evidence.put_artifact("patch", b"fabricated patch")
    receipt = evidence.put_artifact(
        "test-receipt", canonical_json_bytes({"exit_code": 0})
    )
    references = tuple(
        sorted((patch, receipt), key=lambda item: (item.kind, item.id, item.sha256))
    )
    evidence_id = "evidence-forged-pass"
    for index, (event_type, payload) in enumerate(
        (
            (AttemptEvidenceEventType.ATTEMPT_STARTED, {"status": "started"}),
            (AttemptEvidenceEventType.ATTEMPT_COMPLETED, {"result_code": "passed"}),
        ),
        1,
    ):
        evidence.append(
            evidence_id,
            evidence.head(evidence_id),
            f"forged-evidence-{index:02d}",
            AttemptEvidenceInput(
                mission_id="mission-1",
                task_id=task.task_id,
                attempt_id=dispatch.attempt_id,
                event_type=event_type,
                truth_kind=TruthKind.RUNTIME_OBSERVED,
                authority=AttemptEvidenceAuthority.SCOPED_TOOL_WRAPPER,
                references=references if index == 2 else (),
                payload=payload,
            ),
            recorded_at=NOW,
        )
    result = AttemptResult(
        succeeded=True,
        result_code="passed",
        evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
        evidence_refs=references,
        publications=(
            PublicationDraft(
                output_name=task.expected_outputs[0].name,
                kind="patch",
                sha256=patch.sha256,
                paths=task.expected_outputs[0].paths,
            ),
        ),
    )

    with pytest.raises(MissionConflict, match="evidence is not completed"):
        store.complete_attempt(
            "mission-1",
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            result,
            _command("forgery-complete"),
            recorded_at=NOW + timedelta(seconds=1),
            retry_backoff_seconds=0,
        )


def test_claim_rehashes_accepted_input_artifact_before_dispatch(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    snapshot = store.snapshot("mission-1")
    publication = snapshot.publications[0]
    producer_attempt = next(
        item for item in snapshot.attempts if item.attempt_id == publication.attempt_id
    )
    reference = next(
        item
        for item in producer_attempt.evidence_refs
        if item.kind == publication.kind and item.sha256 == publication.sha256
    )
    store.refresh_ready(
        "mission-1",
        _command("ready-mutated-input"),
        recorded_at=NOW + timedelta(seconds=2),
    )
    _register_worker(
        store,
        "worker-assembly",
        capabilities=(TaskKind.ASSEMBLY,),
        at=NOW + timedelta(seconds=2),
    )
    _artifacts(store).values[(reference.kind, reference.id)] = (
        b"mutated after acceptance"
    )
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        store.claim_task(
            "mission-1",
            "assemble",
            "worker-assembly",
            _command("claim-mutated-input"),
            recorded_at=NOW + timedelta(seconds=2),
            ttl_seconds=30,
        )


def test_expected_head_is_atomic_and_replay_is_semantic(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    stale = store.head("mission-1")
    gate = Gate(
        gate_id="gate-head-change",
        mission_id="mission-1",
        reason="Advance the committed head.",
        allowed_decisions=(GateDecision(value="continue", consequence="Continue."),),
        truth_kind=TruthKind.SERVER_DERIVED,
    )
    store.request_gate(gate, _command("head-change"), recorded_at=NOW)

    with pytest.raises(MissionConflict, match="expected head"):
        store.pause(
            "mission-1",
            _command("stale-pause"),
            expected_head=stale,
            operator_label="non-tty-api",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )
    assert store.snapshot("mission-1").mission.status == MissionStatus.RUNNING

    current = store.head("mission-1")
    paused = store.pause(
        "mission-1",
        _command("atomic-pause"),
        expected_head=current,
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    assert (
        store.pause(
            "mission-1",
            _command("atomic-pause"),
            expected_head=current,
            operator_label="non-tty-api",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(minutes=1),
        )
        == paused
    )
    assert (
        store.pause(
            "mission-1",
            _command("atomic-pause"),
            expected_head=paused,
            operator_label="non-tty-api",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )
        == paused
    )
    with pytest.raises(MissionConflict, match="another request"):
        store.pause(
            "mission-1",
            _command("atomic-pause"),
            expected_head=paused,
            operator_label="non-tty-api",
            rationale="changed semantic payload",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )


def test_supplied_task_input_is_gate_scoped_and_rehashed_on_dispatch(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    gate = Gate(
        gate_id="gate-task-input",
        mission_id="mission-1",
        task_id="work-a",
        reason="Supply the private operator input.",
        allowed_decisions=(
            GateDecision(
                value="supply",
                consequence="Wait for a private artifact.",
                task_effect="needs_input",
            ),
        ),
        truth_kind=TruthKind.SERVER_DERIVED,
    )
    store.request_gate(gate, _command("request-task-input"), recorded_at=NOW)
    store.decide_gate(
        "mission-1",
        gate.gate_id,
        "supply",
        _command("authorize-task-input"),
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale="Provide the requested bounded input.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    assert _task_for_snapshot(store, "work-a").state == TaskState.NEEDS_INPUT
    content = b"private operator value"
    reference = _artifacts(store).put("operator-input", content)
    supplied_head = store.supply_task_input(
        "mission-1",
        "work-a",
        gate.gate_id,
        reference,
        _command("supply-task-input"),
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale="Bound to work-a only.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=1),
    )
    assert _task_for_snapshot(store, "work-a").state == TaskState.READY
    supplied_event = next(
        event
        for event in store.tail("mission-1", 0, 100)
        if event.event_type == MissionEventType.TASK_INPUT_SUPPLIED
    )
    assert supplied_event.references == (reference,)
    assert supplied_event.payload["consumer_task_id"] == "work-a"
    assert "private operator value" not in str(supplied_event.payload)
    assert store.verify("mission-1") == supplied_head

    _register_worker(store, "worker-input", capabilities=(TaskKind.WORK,))
    _artifacts(store).values[(reference.kind, reference.id)] = b"mutated"
    with pytest.raises(MissionConflict, match="supplied task input artifact"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-input",
            _command("claim-mutated-task-input"),
            recorded_at=NOW + timedelta(seconds=2),
            ttl_seconds=30,
        )
    _artifacts(store).values[(reference.kind, reference.id)] = content
    dispatch = store.claim_task(
        "mission-1",
        "work-a",
        "worker-input",
        _command("claim-task-input"),
        recorded_at=NOW + timedelta(seconds=2),
        ttl_seconds=30,
    )
    assert dispatch.input_publications == (reference,)


def test_completion_persists_runtime_session_and_invocation_ids(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("identity-ready"), recorded_at=NOW)
    task = next(
        item for item in store.ready_tasks("mission-1") if item.task_id == "work-a"
    )
    _register_worker(store, "worker-identity", capabilities=(TaskKind.WORK,))
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-identity",
        _command("identity-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    result = _success(dispatch, task, _artifacts(store)).model_copy(
        update={"session_id": "adk-session", "invocation_id": "adk-invocation"}
    )
    store.complete_attempt(
        "mission-1",
        dispatch.attempt_id,
        dispatch.worker_id,
        dispatch.lease_id,
        dispatch.fencing_token,
        result,
        _command("identity-complete"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )
    attempt = next(
        item
        for item in store.snapshot("mission-1").attempts
        if item.attempt_id == dispatch.attempt_id
    )
    assert (attempt.session_id, attempt.invocation_id) == (
        "adk-session",
        "adk-invocation",
    )


def test_mission_attempt_worker_time_and_artifact_budgets_are_authoritative(
    tmp_path,
) -> None:
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
    with pytest.raises(PlanValidationError, match="attempt_budget_too_small"):
        _create(attempt_store, policy=policy_with(max_attempts=4))

    time_store = SQLiteMissionStore(tmp_path / "time-budget.sqlite")
    _create(time_store, policy=policy_with(max_worker_seconds=10))
    time_store.refresh_ready("mission-1", _command("time-ready"), recorded_at=NOW)
    _register_worker(time_store, "worker-a", capabilities=(TaskKind.WORK,))
    time_store.claim_task(
        "mission-1",
        "work-a",
        "worker-a",
        _command("time-first"),
        recorded_at=NOW,
        ttl_seconds=6,
    )
    _register_worker(time_store, "worker-b", capabilities=(TaskKind.WORK,))
    capped = time_store.claim_task(
        "mission-1",
        "work-b",
        "worker-b",
        _command("time-second"),
        recorded_at=NOW,
        ttl_seconds=6,
    )
    assert capped.expires_at == NOW + timedelta(seconds=4)
    time_store.expire_leases(
        "mission-1",
        _command("time-expire"),
        recorded_at=NOW + timedelta(seconds=4),
        retry_backoff_seconds=0,
    )
    time_store.refresh_ready(
        "mission-1",
        _command("time-ready-again"),
        recorded_at=NOW + timedelta(seconds=4),
    )
    with pytest.raises(BudgetExhausted, match="worker-time budget"):
        time_store.claim_task(
            "mission-1",
            "work-b",
            "worker-b",
            _command("time-exhausted"),
            recorded_at=NOW + timedelta(seconds=4),
            ttl_seconds=6,
        )
    time_snapshot = time_store.snapshot("mission-1")
    blocked_time_task = next(
        task for task in time_snapshot.tasks if task.task_id == "work-b"
    )
    assert time_snapshot.mission.status == MissionStatus.PAUSED
    assert (blocked_time_task.state, blocked_time_task.blocker) == (
        TaskState.BLOCKED,
        "budget:worker_seconds",
    )

    artifact_store = SQLiteMissionStore(tmp_path / "artifact-budget.sqlite")
    _create(artifact_store, policy=policy_with(max_artifact_bytes=16))
    artifact_store.refresh_ready(
        "mission-1", _command("artifact-ready"), recorded_at=NOW
    )
    task = next(
        item
        for item in artifact_store.ready_tasks("mission-1")
        if item.task_id == "work-a"
    )
    _register_worker(artifact_store, "worker-a", capabilities=(TaskKind.WORK,))
    dispatch = artifact_store.claim_task(
        "mission-1",
        task.task_id,
        "worker-a",
        _command("artifact-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
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
    artifact_snapshot = artifact_store.snapshot("mission-1")
    blocked_artifact_task = next(
        item for item in artifact_snapshot.tasks if item.task_id == task.task_id
    )
    failed_attempt = next(
        item
        for item in artifact_snapshot.attempts
        if item.attempt_id == dispatch.attempt_id
    )
    assert artifact_snapshot.mission.status == MissionStatus.PAUSED
    assert (blocked_artifact_task.state, blocked_artifact_task.blocker) == (
        TaskState.BLOCKED,
        "budget:artifact_bytes",
    )
    assert (failed_attempt.state, failed_attempt.result_code) == (
        AttemptState.FAILED,
        "artifact_budget_exhausted",
    )
    assert any(
        event.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED
        and event.payload["dimension"] == "artifact_bytes"
        and event.payload["action"] == "replan_or_cancel"
        for event in artifact_store.tail("mission-1", 0, 100)
    )
    assert artifact_store.verify("mission-1") == artifact_store.head("mission-1")


def test_attempt_budget_exhaustion_after_replan_commits_a_budget_block(
    tmp_path,
) -> None:
    policy = _policy().model_copy(
        update={
            "resource_budget": _policy().resource_budget.model_copy(
                update={"max_attempts": 8}
            )
        }
    )
    store = SQLiteMissionStore(
        tmp_path / "attempt-budget.sqlite", artifact_resolver=MemoryArtifacts()
    )
    _create(store, policy=policy)
    _register_worker(store, "worker-all", capabilities=tuple(sorted(TaskKind)))
    tick = 0

    def claim(task_id: str):
        nonlocal tick
        at = NOW + timedelta(seconds=tick)
        store.refresh_ready(
            "mission-1", _command(f"attempt-ready-{tick}"), recorded_at=at
        )
        dispatch = store.claim_task(
            "mission-1",
            task_id,
            "worker-all",
            _command(f"attempt-claim-{tick}"),
            recorded_at=at,
            ttl_seconds=30,
        )
        tick += 1
        return dispatch

    def complete(dispatch, *, succeeded: bool) -> None:
        nonlocal tick
        task = _task_for_snapshot(store, dispatch.task_id)
        result = (
            _success(dispatch, task, _artifacts(store))
            if succeeded
            else AttemptResult(
                succeeded=False,
                retryable=True,
                result_code="retryable",
            )
        )
        store.complete_attempt(
            "mission-1",
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            result,
            _command(f"attempt-complete-{tick}"),
            recorded_at=NOW + timedelta(seconds=tick),
            retry_backoff_seconds=0,
        )
        tick += 1

    for task_id in ("work-a", "work-b", "assemble"):
        complete(claim(task_id), succeeded=False)
        complete(claim(task_id), succeeded=True)
    complete(claim("verify"), succeeded=False)
    assert len(store.snapshot("mission-1").attempts) == 7

    store.request_replan(
        "mission-1",
        _command("attempt-replan-request"),
        expected_head=store.head("mission-1"),
        reason="Replace the exhausted revision explicitly.",
        operator_label="non-tty-api",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=tick),
    )
    revised = Plan.model_validate(
        {
            **_plan().model_dump(mode="json"),
            "previous_revision": 1,
            "revision": 2,
        }
    )
    store.revise_plan(
        "mission-1",
        revised,
        _command("attempt-revise"),
        expected_head=store.head("mission-1"),
        recorded_at=NOW + timedelta(seconds=tick + 1),
    )
    store.approve_plan(
        "mission-1",
        _command("attempt-revision-approve"),
        expected_revision=2,
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale="Run the bounded replacement revision.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=tick + 2),
    )
    tick += 3
    first = claim("work-a")
    assert first.attempt_number == 1
    with pytest.raises(BudgetExhausted, match="attempt budget"):
        claim("work-b")

    snapshot = store.snapshot("mission-1")
    blocked = next(task for task in snapshot.tasks if task.task_id == "work-b")
    assert snapshot.mission.status == MissionStatus.PAUSED
    assert (blocked.state, blocked.blocker) == (
        TaskState.BLOCKED,
        "budget:attempts",
    )
    event = next(
        event
        for event in reversed(store.tail("mission-1", 0, 256))
        if event.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED
    )
    assert event.payload == {
        "action": "replan_or_cancel",
        "dimension": "attempts",
        "limit": 8,
        "observed": 8,
        "status": "blocked_budget",
        "task_id": "work-b",
        "threshold_crossed": True,
    }
    assert store.verify("mission-1") == store.head("mission-1")
    store.resume(
        "mission-1",
        _command("attempt-budget-resume"),
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale="Confirm a generic resume cannot erase the budget blocker.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=tick + 1),
    )
    store.refresh_ready(
        "mission-1",
        _command("attempt-budget-refresh"),
        recorded_at=NOW + timedelta(seconds=tick + 1),
    )
    still_blocked = next(
        task
        for task in store.snapshot("mission-1").tasks
        if task.task_id == "work-b"
    )
    assert (still_blocked.state, still_blocked.blocker) == (
        TaskState.BLOCKED,
        "budget:attempts",
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
        expected_head=store.head("mission-1"),
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
    store.record_resource_summary(
        crossed, _command("resource-crossed"), recorded_at=NOW
    )
    store.pause(
        "mission-1",
        _command("pause"),
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    store.resume(
        "mission-1",
        _command("resume"),
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    store.cancel(
        "mission-1",
        _command("cancel"),
        expected_head=store.head("mission-1"),
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
    assert all(
        event.truth_kind == TruthKind.SERVER_DERIVED for event in operator_events
    )
    assert all(
        event.authority == MissionAuthority.MISSION_SERVICE for event in operator_events
    )
    assert any(
        event.event_type == MissionEventType.RESOURCE_SUMMARY_RECORDED
        for event in events
    )
    assert any(
        event.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED for event in events
    )
    assert store.snapshot("mission-1").gates[0].resolution == "approve"
    assert store.snapshot("mission-1").mission.status == MissionStatus.CANCELLED
    with pytest.raises(ValidationError, match="only unavailable"):
        ResourceReceipt.model_validate(
            {**unavailable.model_dump(mode="json"), "value": 1}
        )


def test_verify_rejects_materialized_gate_without_committed_event(tmp_path) -> None:
    database = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(database)
    _create(store)
    forged = Gate(
        gate_id="gate-forged",
        mission_id="mission-1",
        reason="This row has no committed request event.",
        allowed_decisions=(GateDecision(value="approve", consequence="Continue."),),
        truth_kind=TruthKind.SERVER_DERIVED,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO mission_gates VALUES (?, ?, ?, NULL, ?)",
            (
                forged.gate_id,
                forged.mission_id,
                forged.task_id,
                canonical_json_bytes(forged.model_dump(mode="json")),
            ),
        )

    with pytest.raises(MissionStoreError, match="materialized state"):
        store.verify("mission-1")


def test_task_dispatch_rejects_contract_outside_bound_plan(tmp_path) -> None:
    database = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(database)
    _create(store)
    store.refresh_ready("mission-1", _command("ready-contract-tamper"), recorded_at=NOW)
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))
    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT task_bytes FROM mission_tasks "
            "WHERE mission_id = 'mission-1' AND task_id = 'work-a'"
        ).fetchone()[0]
        task = Task.model_validate_json(raw)
        forged = task.model_copy(
            update={
                "contract": "Write beyond the approved task scope.",
                "write_paths": tuple(sorted((*task.write_paths, "secrets.txt"))),
            }
        )
        connection.execute(
            "UPDATE mission_tasks SET task_bytes = ? "
            "WHERE mission_id = 'mission-1' AND task_id = 'work-a'",
            (canonical_json_bytes(forged.model_dump(mode="json")),),
        )

    with pytest.raises(MissionStoreError, match="bound plan"):
        store.verify("mission-1")
    with pytest.raises(MissionStoreError, match="bound plan"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-a",
            _command("claim-contract-tamper"),
            recorded_at=NOW,
            ttl_seconds=30,
        )


def test_plan_content_is_bound_to_committed_plan_events(tmp_path) -> None:
    database = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(database)
    _create(store)
    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT plan_bytes FROM mission_plans "
            "WHERE mission_id = 'mission-1' AND revision = 1"
        ).fetchone()[0]
        plan = Plan.model_validate_json(raw)
        task = plan.tasks[0].model_copy(update={"contract": "Forged plan contract."})
        forged = plan.model_copy(update={"tasks": (task, *plan.tasks[1:])})
        encoded = canonical_json_bytes(forged.model_dump(mode="json"))
        connection.execute(
            "UPDATE mission_plans SET plan_bytes = ?, plan_sha256 = ? "
            "WHERE mission_id = 'mission-1' AND revision = 1",
            (encoded, canonical_json_sha256(forged.model_dump(mode="json"))),
        )

    with pytest.raises(MissionStoreError, match="plan digest"):
        store.snapshot("mission-1")


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
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))

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
        expected_head=store.head("mission-1"),
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


def test_reassign_reprioritize_and_replan_request_are_safe_and_evented(
    tmp_path,
) -> None:
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
    _register_worker(store, "worker-b", capabilities=(TaskKind.WORK,))
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
    expected_head = store.head("mission-1")
    head = store.request_replan(
        "mission-1",
        _command("request-replan"),
        expected_head=expected_head,
        reason="The accepted revision needs a new explicit successor.",
        operator_label="non-tty-api",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    assert (
        store.request_replan(
            "mission-1",
            _command("request-replan"),
            expected_head=expected_head,
            reason="The accepted revision needs a new explicit successor.",
            operator_label="non-tty-api",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(minutes=1),
        )
        == head
    )
    snapshot = store.snapshot("mission-1")
    assert snapshot.mission.status == MissionStatus.PAUSED
    assert snapshot.plan.revision == 1
    assert store.verify("mission-1") == store.head("mission-1")


def test_verification_receipt_must_bind_exact_accepted_assembly_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
    store.refresh_ready(
        "mission-1",
        _command("ready-verification"),
        recorded_at=NOW + timedelta(seconds=4),
    )
    task = store.ready_tasks("mission-1")[0]
    _register_worker(
        store,
        "worker-verifier",
        capabilities=(TaskKind.VERIFICATION,),
        at=NOW + timedelta(seconds=4),
    )
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
    original_verify = _artifacts(store).verify_attempt
    claimed_candidate = json.loads(bad_bytes)["candidate_patch_sha256"]

    def verify_exact_candidate(*args, candidate_references, **kwargs):
        return original_verify(
            *args, candidate_references=candidate_references, **kwargs
        ) and (
            len(candidate_references) == 1
            and candidate_references[0].sha256 == claimed_candidate
        )

    monkeypatch.setattr(_artifacts(store), "verify_attempt", verify_exact_candidate)

    with pytest.raises(MissionConflict, match="generic attempt evidence"):
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

    monkeypatch.setattr(_artifacts(store), "verify_attempt", original_verify)
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


def test_forged_accepted_publication_digest_fails_verification_before_dispatch(
    tmp_path,
) -> None:
    database = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(database)
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT publication_id, publication_bytes FROM mission_publications "
            "WHERE mission_id = 'mission-1' AND state = 'accepted' "
            "ORDER BY publication_id LIMIT 1"
        ).fetchone()
        publication = json.loads(row[1])
        publication["sha256"] = "f" * 64
        connection.execute(
            "UPDATE mission_publications SET publication_bytes = ? "
            "WHERE publication_id = ?",
            (canonical_json_bytes(publication), row[0]),
        )

    with pytest.raises(MissionStoreError, match="materialized state"):
        store.verify("mission-1")
    with pytest.raises(MissionStoreError, match="materialized state"):
        store.refresh_ready(
            "mission-1",
            _command("ready-after-publication-forgery"),
            recorded_at=NOW + timedelta(seconds=2),
        )


@pytest.mark.parametrize("approve", (True, False))
def test_final_decision_binds_candidate_and_verification_receipt(
    tmp_path, approve: bool
) -> None:
    from tests.adversarial.test_final_approval_bundle import (
        _complete_trusted_verification,
        _pending_bundle,
    )

    mission_id = "mission-1"
    store = SQLiteMissionStore(
        tmp_path / ("mission-approve.sqlite" if approve else "mission-reject.sqlite")
    )
    _create(store, mission_id=mission_id)
    assert _complete_ready(store, mission_id, at=NOW, round_number=1) == (
        "work-a",
        "work-b",
    )
    assert _complete_ready(
        store, mission_id, at=NOW + timedelta(seconds=2), round_number=2
    ) == ("assemble",)
    _complete_trusted_verification(store)
    store.enter_awaiting_result(
        mission_id,
        _command(f"await-{mission_id}"),
        recorded_at=NOW + timedelta(seconds=6),
    )
    bundle = _pending_bundle(store)
    bundle_reference = _artifacts(store).put(
        "final-result-bundle",
        canonical_json_bytes(bundle.model_dump(mode="json")),
    )
    store.register_final_result_bundle(
        mission_id,
        bundle_reference,
        _command(f"bundle-{approve}"),
        expected_head=store.head(mission_id),
        recorded_at=NOW + timedelta(seconds=7),
    )
    snapshot = store.snapshot(mission_id)
    candidate = next(
        item for item in snapshot.publications if item.task_id == "assemble"
    )
    with pytest.raises(MissionConflict, match="not current"):
        store.approve_final_result(
            mission_id,
            _command(f"wrong-final-{mission_id}"),
            expected_head=snapshot.head,
            expected_bundle_id="final_result_" + "f" * 32,
            operator_label="non-tty-api",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=7),
        )
    decision = store.approve_final_result if approve else store.reject_final_result
    decision_head = decision(
        mission_id,
        _command(f"final-{mission_id}"),
        expected_head=snapshot.head,
        expected_bundle_id=bundle.bundle_id,
        operator_label="non-tty-api",
        rationale="Reviewed the isolated candidate.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=7),
    )
    decision_retry = decision(
        mission_id,
        _command(f"final-{mission_id}"),
        expected_head=snapshot.head,
        expected_bundle_id=bundle.bundle_id,
        operator_label="non-tty-api",
        rationale="Reviewed the isolated candidate.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(minutes=1),
    )

    final_event = store.tail(mission_id, snapshot.head.seq, 10)[0]
    assert final_event.payload["candidate_sha256"] == candidate.sha256
    assert final_event.payload["bundle_id"] == bundle.bundle_id
    assert decision_retry == decision_head
    assert len(final_event.references) == 3
    assert final_event.truth_kind == TruthKind.SERVER_DERIVED
    assert store.snapshot(mission_id).mission.status == (
        MissionStatus.AWAITING_RESULT if approve else MissionStatus.REJECTED
    )
    assert store.verify(mission_id) == store.head(mission_id)
    if approve:
        verification = next(
            item
            for item in store.snapshot(mission_id).publications
            if item.task_id == "verify"
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
        assert store.snapshot(mission_id).mission.status == MissionStatus.COMPLETED
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
    task = next(
        item for item in store.ready_tasks("mission-1") if item.task_id == "work-a"
    )
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))
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
        expected_head=store.head("mission-1"),
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
        if event.event_type
        in {MissionEventType.OPERATOR_RESUMED, MissionEventType.TASK_RETRIED}
        and event.payload.get("reason_code") == "operator_retry"
    ]
    assert snapshot.mission.status == MissionStatus.RUNNING
    assert task.state == TaskState.RETRYING
    assert retry_events and all(
        event.truth_kind == TruthKind.SERVER_DERIVED
        and event.authority == MissionAuthority.MISSION_SERVICE
        for event in retry_events
    )
