from __future__ import annotations

import asyncio
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceEventType,
    SQLiteAttemptEvidenceStore,
    TrustedCheckReceipt,
)
from graphene.orchestration.models import (
    ArtifactContract,
    ArtifactRequirement,
    AttemptState,
    CommandTemplate,
    Criterion,
    CriterionVerificationKind,
    GenericEvidenceLink,
    Mission,
    MissionStatus,
    Plan,
    ProjectPolicy,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
)
from graphene.orchestration.runner import (
    AcceptedArtifactCache,
    MissionRunner,
    RunnerCancelled,
    RunnerDeadlineExceeded,
    RunnerError,
    RunnerExecutionFailed,
    RunnerStalled,
)
from graphene.orchestration.runtime import (
    CheckOutcome,
    CompletionOutcome,
    RuntimeAssignment,
    RuntimeErrorCode,
    WorkerCapabilities,
    WorkerCompletion,
    WorkerContext,
    WorkerRegistry,
    WorkerRuntime,
)
from graphene.orchestration.scheduler import MissionScheduler, SystemClock
from graphene.orchestration.store import SQLiteMissionStore


CHECK = CommandTemplate(
    template_id="unit-check",
    argv=("python", "-m", "pytest", "-q"),
    timeout_seconds=30,
)


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=input_bytes is None,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip() if isinstance(result.stdout, str) else ""


def _repository(path: Path) -> tuple[Path, str]:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "runner@example.invalid")
    _git(path, "config", "user.name", "Runner Test")
    (path / "a.txt").write_text("a-before\n")
    (path / "b.txt").write_text("b-before\n")
    _git(path, "add", "a.txt", "b.txt")
    _git(path, "commit", "-q", "-m", "base")
    return path, _git(path, "rev-parse", "HEAD")


def _task(
    task_id: str,
    *,
    kind: TaskKind,
    output_name: str,
    output_kind: str,
    write_paths: tuple[str, ...] = (),
    dependencies: tuple[str, ...] = (),
    inputs: tuple[ArtifactRequirement, ...] = (),
) -> Task:
    role = {
        TaskKind.ASSEMBLY: "assembler",
        TaskKind.VERIFICATION: "verifier",
        TaskKind.WORK: "worker",
    }[kind]
    return Task(
        task_id=task_id,
        title=task_id,
        contract=f"Complete {task_id} within its exact scope.",
        kind=kind,
        dependencies=dependencies,
        assigned_role=role,
        read_paths=("a.txt", "b.txt"),
        write_paths=write_paths,
        allowed_commands=(CHECK.template_id,),
        inputs=inputs,
        expected_outputs=(
            ArtifactContract(
                name=output_name,
                kind=output_kind,
                paths=write_paths,
            ),
        ),
        acceptance_checks=(CHECK.template_id,),
        priority=1,
        attempt_limit=1,
    )


def _contracts(base_sha: str) -> tuple[ProjectPolicy, Mission, Plan]:
    work_a = _task(
        "work-a",
        kind=TaskKind.WORK,
        output_name="patch-a",
        output_kind="patch",
        write_paths=("a.txt",),
    )
    work_z = _task(
        "work-z",
        kind=TaskKind.WORK,
        output_name="patch-z",
        output_kind="patch",
        write_paths=("b.txt",),
    )
    assembly = _task(
        "assemble",
        kind=TaskKind.ASSEMBLY,
        output_name="candidate",
        output_kind="patch",
        dependencies=("work-a", "work-z"),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-a", name="patch-a", kind="patch"
            ),
            ArtifactRequirement(
                producer_task_id="work-z", name="patch-z", kind="patch"
            ),
        ),
    )
    verify = _task(
        "verify",
        kind=TaskKind.VERIFICATION,
        output_name="verification",
        output_kind="test-receipt",
        dependencies=("assemble",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="assemble", name="candidate", kind="patch"
            ),
        ),
    )
    budget = ResourceBudget(
        max_worker_seconds=600,
        max_attempts=8,
        max_artifact_bytes=5_000_000,
    )
    policy = ProjectPolicy(
        policy_id="runner-policy",
        revision=1,
        repo_id="runner-repository",
        base_ref="HEAD",
        base_sha=base_sha,
        allowed_read_globs=("a.txt", "b.txt"),
        allowed_write_globs=("a.txt", "b.txt"),
        command_templates=(CHECK,),
        agent_roles=("assembler", "verifier", "worker"),
        max_concurrency=2,
        retry_limit=0,
        resource_budget=budget,
        retention=RetentionPolicy(retain_days=1),
    )
    mission = Mission(
        mission_id="runner-mission",
        policy_id=policy.policy_id,
        policy_revision=policy.revision,
        repo_id=policy.repo_id,
        base_sha=base_sha,
        goal="Change two independent files and verify the exact integrated result.",
        success_criteria=("Both exact file changes pass verification.",),
        plan_revision=1,
        creation_source="operator",
        resource_budget=budget,
        created_at=datetime.now(UTC),
    )
    plan = Plan(
        mission_id=mission.mission_id,
        revision=1,
        criteria=(
            Criterion(
                criterion_id="criterion-files",
                description=mission.success_criteria[0],
                producer_task_ids=("work-a", "work-z"),
                verification_kind=CriterionVerificationKind.DETERMINISTIC_CHECK,
                verifier_task_id="verify",
                verifier_id=CHECK.template_id,
            ),
        ),
        tasks=tuple(
            sorted((assembly, verify, work_a, work_z), key=lambda item: item.task_id)
        ),
        max_concurrency=2,
    )
    return policy, mission, plan


class _Adapter:
    def __init__(self, worker_id: str, path: str, text: str, delay: float) -> None:
        self.capabilities = WorkerCapabilities(
            worker_id=worker_id,
            driver="deterministic",
            task_kinds=(TaskKind.WORK,),
        )
        self.path = path
        self.text = text
        self.delay = delay
        self.calls = 0

    async def execute(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion:
        del assignment
        self.calls += 1
        await asyncio.sleep(self.delay)
        await context.write_text(self.path, self.text)
        return WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id=f"session-{self.capabilities.worker_id}",
            invocation_id=f"invocation-{self.capabilities.worker_id}-{self.calls}",
        )


class _CancellableAdapter(_Adapter):
    def __init__(self, worker_id: str, path: str) -> None:
        super().__init__(worker_id, path, "unused\n", 0)
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.active = 0

    async def execute(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion:
        del context, assignment
        self.calls += 1
        self.active += 1
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.active -= 1
            self.cancelled.set()


class _CheckRunner:
    async def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        del owner_id
        expected = {
            "work-a": {"a.txt": "a-after\n"},
            "work-z": {"b.txt": "b-after\n"},
            "assemble": {"a.txt": "a-after\n", "b.txt": "b-after\n"},
            "verify": {"a.txt": "a-after\n", "b.txt": "b-after\n"},
        }[assignment.task_id]
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


class _OneShotCheckRunner(_CheckRunner):
    def __init__(self) -> None:
        self.failed = False

    async def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        outcome = await super().__call__(workspace, assignment, owner_id)
        if assignment.task_id == "work-a" and not self.failed:
            self.failed = True
            return outcome.model_copy(
                update={"exit_code": 1, "output_sha256": sha256_hex(b"one-shot failure")}
            )
        return outcome


def _setup(
    tmp_path: Path,
    *,
    delay: float = 0.15,
    retry_work_a: bool = False,
    attempt_limit: int = 2,
):
    repository, base_sha = _repository(tmp_path / "supplied-repository")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    store = SQLiteMissionStore(tmp_path / "missions.sqlite", artifact_resolver=evidence)
    policy, mission, plan = _contracts(base_sha)
    if retry_work_a:
        policy = policy.model_copy(update={"retry_limit": attempt_limit - 1})
        plan = Plan.model_validate(
            {
                **plan.model_dump(mode="json"),
                "tasks": [
                    {
                        **task.model_dump(mode="json"),
                        "attempt_limit": (
                            attempt_limit if task.task_id == "work-a" else 1
                        ),
                    }
                    for task in plan.tasks
                ],
            }
        )
    store.create_mission(
        policy,
        mission,
        plan,
        "command-create-runner-mission",
        recorded_at=mission.created_at,
    )
    store.approve_plan(
        mission.mission_id,
        "command-approve-runner-mission",
        expected_revision=1,
        expected_head=store.head(mission.mission_id),
        operator_label="test-operator",
        rationale="Approve the exact test plan.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=mission.created_at,
    )
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
        for task in plan.tasks
    }
    adapter_a = _Adapter("worker-a", "a.txt", "a-after\n", delay)
    adapter_z = _Adapter("worker-z", "b.txt", "b-after\n", 0)
    return (
        repository,
        base_sha,
        runtime_root,
        evidence,
        store,
        assignments,
        adapter_a,
        adapter_z,
    )


def _runtime(
    *,
    repository: Path,
    base_sha: str,
    runtime_root: Path,
    evidence: SQLiteAttemptEvidenceStore,
    scheduler: MissionScheduler,
    assignments: dict[str, RuntimeAssignment],
    adapters: tuple[_Adapter, ...],
    cache: AcceptedArtifactCache,
    check_runner: _CheckRunner | None = None,
) -> WorkerRuntime:
    return WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=WorkerRegistry(adapters),
        assignment=lambda dispatch: assignments[dispatch.task_id],
        accepted_artifact=cache,
        check_runner=check_runner or _CheckRunner(),
        policy_sha256=scheduler.store.snapshot("runner-mission").policy.policy_sha256,
        fence=lambda dispatch, _operation_id: scheduler.assert_fence(dispatch),
        heartbeat=scheduler.heartbeat,
    )


def test_runner_commits_in_completion_order_recovers_receipt_and_preserves_checkout(
    tmp_path: Path,
) -> None:
    (
        repository,
        base_sha,
        runtime_root,
        evidence,
        store,
        assignments,
        adapter_a,
        adapter_z,
    ) = _setup(tmp_path)
    source_before = {
        path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
    }
    status_before = _git(repository, "status", "--porcelain=v1")
    workers = ("worker-a", "worker-z")

    first_scheduler = MissionScheduler(
        store, clock=SystemClock(), lease_ttl_seconds=30, retry_backoff_seconds=0
    )
    first_cache = AcceptedArtifactCache()
    first_runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=first_scheduler,
        assignments=assignments,
        adapters=(adapter_a, adapter_z),
        cache=first_cache,
    )
    initial = first_scheduler.tick("runner-mission", workers)
    assert tuple(item.task_id for item in initial) == ("work-a", "work-z")
    work_z = next(item for item in initial if item.task_id == "work-z")
    receipt_before_restart = asyncio.run(first_runtime.execute_async(work_z)).receipt

    restarted_scheduler = MissionScheduler(
        store, clock=SystemClock(), lease_ttl_seconds=30, retry_backoff_seconds=0
    )
    restarted_cache = AcceptedArtifactCache()
    restarted_runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=restarted_scheduler,
        assignments=assignments,
        adapters=(adapter_a, adapter_z),
        cache=restarted_cache,
    )
    run = MissionRunner(
        scheduler=restarted_scheduler,
        runtime=restarted_runtime,
        worker_ids=workers,
        accepted_artifacts=restarted_cache,
        deadline_seconds=5,
        poll_seconds=0,
    ).run("runner-mission")

    assert run.snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert run.batches == (("work-a", "work-z"), ("assemble",), ("verify",))
    assert run.completion_order == ("work-z", "work-a", "assemble", "verify")
    assert run.replayed_attempt_ids == (work_z.attempt_id,)
    assert adapter_a.calls == adapter_z.calls == 1
    assert restarted_runtime._load_receipt(work_z) == receipt_before_restart
    assert {
        path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
    } == source_before
    assert _git(repository, "status", "--porcelain=v1") == status_before
    assert _git(repository, "rev-parse", "HEAD") == base_sha

    candidate_publication = next(
        item for item in run.snapshot.publications if item.task_id == "assemble"
    )
    candidate_attempt = next(
        item
        for item in run.snapshot.attempts
        if item.attempt_id == candidate_publication.attempt_id
    )
    candidate_reference = next(
        item
        for item in candidate_attempt.evidence_refs
        if item.kind == "patch" and item.sha256 == candidate_publication.sha256
    )
    candidate = evidence.resolve(candidate_reference.kind, candidate_reference.id)
    assert candidate is not None
    logical_reference = candidate_publication.published_reference()
    logical_dispatch = work_z.model_copy(
        update={"task_id": "verify", "input_publications": (logical_reference,)}
    )
    logical_cache = AcceptedArtifactCache()

    class _ArtifactSource:
        def resolve_enveloped(self, reference) -> bytes | None:
            return evidence.resolve_enveloped(reference)

    logical_cache.prefetch((logical_dispatch,), _ArtifactSource(), run.snapshot)
    assert logical_cache(logical_dispatch, logical_reference) == candidate

    class _TamperedSource:
        @staticmethod
        def resolve_enveloped(_reference) -> bytes:
            return b"changed after acceptance"

    with pytest.raises(RunnerExecutionFailed, match="artifact is unavailable"):
        AcceptedArtifactCache().prefetch(
            (logical_dispatch,), _TamperedSource(), run.snapshot
        )
    result = tmp_path / "isolated-result"
    _git(tmp_path, "clone", "--no-local", str(repository), str(result))
    _git(result, "checkout", "--detach", "-q", base_sha)
    _git(result, "apply", "-", input_bytes=candidate)
    assert (result / "a.txt").read_text() == "a-after\n"
    assert (result / "b.txt").read_text() == "b-after\n"
    assert store.verify("runner-mission") == store.head("runner-mission")


def test_runner_retries_one_truth_labeled_check_failure_without_delaying_sibling(
    tmp_path: Path,
) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, retry_work_a=True
    )
    scheduler = MissionScheduler(
        store, clock=SystemClock(), retry_backoff_seconds=0
    )
    cache = AcceptedArtifactCache()
    check_runner = _OneShotCheckRunner()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
        check_runner=check_runner,
    )

    run = MissionRunner(
        scheduler=scheduler,
        runtime=runtime,
        worker_ids=("worker-a", "worker-z"),
        accepted_artifacts=cache,
        # What is under test is the order the scheduler produced, not whether
        # several real Git and filesystem rounds fit inside a wall-clock
        # budget. The clock is frozen so a loaded host cannot fail this;
        # the deadline has its own test below.
        deadline_seconds=3_600,
        poll_seconds=0,
        monotonic=lambda: 0.0,
    ).run("runner-mission")

    assert run.snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert run.completion_order[0] == "work-z"
    assert run.completion_order.count("work-a") == 2
    attempts = sorted(
        (item for item in run.snapshot.attempts if item.task_id == "work-a"),
        key=lambda item: item.attempt_number,
    )
    assert [item.state for item in attempts] == [
        AttemptState.FAILED,
        AttemptState.COMMITTED,
    ]
    assert [item.fencing_token for item in attempts] == [1, 2]
    assert attempts[0].attempt_id != attempts[1].attempt_id
    assert attempts[0].result_code == "acceptance_check_failed"
    assert isinstance(attempts[0].evidence_link, GenericEvidenceLink)
    events = evidence.tail(
        attempts[0].evidence_link.evidence_id,
        0,
        evidence.head(attempts[0].evidence_link.evidence_id).seq,
    )
    check = next(
        item
        for item in events
        if item.event_type == AttemptEvidenceEventType.CHECK_COMPLETED
    )
    assert check.truth_kind == TruthKind.RUNTIME_OBSERVED
    assert check.authority == AttemptEvidenceAuthority.CHECK_RUNNER
    receipt_bytes = evidence.resolve(check.references[0].kind, check.references[0].id)
    assert receipt_bytes is not None
    assert TrustedCheckReceipt.model_validate_json(receipt_bytes).result_code == (
        "acceptance_check_failed"
    )
    assert store.verify("runner-mission") == store.head("runner-mission")


def test_runner_stops_after_bounded_no_progress(tmp_path: Path) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=0
    )
    scheduler = MissionScheduler(
        store,
        clock=SystemClock(),
        dispatch_limiter=lambda _mission_id, _configured: 0,
    )
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )

    with pytest.raises(RunnerStalled, match="no progress"):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            max_no_progress_cycles=2,
            poll_seconds=0,
        ).run("runner-mission")


def test_one_completion_commit_failure_does_not_drop_its_successful_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path
    )
    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )
    complete = scheduler.complete

    def fail_work_a(dispatch, result):
        if dispatch.task_id == "work-a":
            raise RuntimeError("coordinator commit failed")
        return complete(dispatch, result)

    monkeypatch.setattr(scheduler, "complete", fail_work_a)
    with pytest.raises(RunnerExecutionFailed, match="work-a"):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            deadline_seconds=5,
        ).run("runner-mission")

    snapshot = store.snapshot("runner-mission")
    assert any(item.task_id == "work-z" for item in snapshot.publications)
    assert (
        next(item for item in snapshot.tasks if item.task_id == "work-z").state.value
        == "done"
    )


def test_runner_deadline_cleans_private_workspaces_without_touching_source(
    tmp_path: Path,
) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=1
    )
    z.delay = 1
    source_before = {
        path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
    }
    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )

    # This test is about what a cut-off attempt leaves behind. The runner's
    # own clock is injected so the assertions below never depend on how long
    # the host took; the deadline decision itself is tested separately.
    calls = [0]

    def clock() -> float:
        calls[0] += 1
        return 0.0

    with pytest.raises(RunnerDeadlineExceeded, match="deadline"):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            deadline_seconds=0.05,
            poll_seconds=0,
            monotonic=clock,
        ).run("runner-mission")

    assert calls[0] >= 2
    assert not tuple((runtime_root / "worker-workspaces").iterdir())
    assert {
        path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
    } == source_before
    assert _git(repository, "status", "--porcelain=v1") == ""
    snapshot = store.snapshot("runner-mission")
    assert {item.state for item in snapshot.attempts} == {AttemptState.FAILED}
    assert {item.result_code for item in snapshot.attempts} == {"outcome_unknown"}
    assert all(item.released_at is not None for item in snapshot.leases)


def test_runner_stops_when_its_own_clock_passes_the_deadline(tmp_path: Path) -> None:
    """The deadline as a decision, with no worker timing in it at all.

    Every attempt is given effectively unlimited time, and the workers finish
    normally. The only thing that ends the run is the runner reading its clock
    and finding the budget spent.
    """
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=0
    )
    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )
    ticks = iter((0.0, 0.0))

    def clock() -> float:
        return next(ticks, 7_200.0)

    with pytest.raises(RunnerDeadlineExceeded, match="deadline"):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            deadline_seconds=3_600,
            poll_seconds=0,
            monotonic=clock,
        ).run("runner-mission")

    snapshot = store.snapshot("runner-mission")
    # The first batch was allowed to finish: this is a budget, not a kill.
    assert {item.state for item in snapshot.attempts} == {AttemptState.COMMITTED}
    assert store.verify("runner-mission") == store.head("runner-mission")


def test_unexpected_runner_failure_is_committed_and_releases_leases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=0
    )
    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )

    async def crash(_dispatch):
        raise RuntimeError("private worker detail")

    monkeypatch.setattr(runtime, "execute_async", crash)
    with pytest.raises(RunnerExecutionFailed, match="worker execution failed"):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            deadline_seconds=5,
        ).run("runner-mission")

    snapshot = store.snapshot("runner-mission")
    assert {item.state for item in snapshot.attempts} == {AttemptState.FAILED}
    assert {item.result_code for item in snapshot.attempts} == {"outcome_unknown"}
    assert all(item.released_at is not None for item in snapshot.leases)


def test_scheduler_cancel_cleans_real_runtime_before_revoking_fences(tmp_path) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=0
    )
    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )
    active = scheduler.tick("runner-mission", ("worker-a", "worker-z"))
    workspaces = tuple(runtime._workspace(dispatch) for dispatch in active)
    for workspace in workspaces:
        workspace.mkdir(mode=0o700)

    assert scheduler.cancel(
        "runner-mission",
        command_id="command_cancel_real_runtime_001",
        expected_head=store.head("runner-mission"),
        workers={"worker-a": runtime, "worker-z": runtime},
        operator_label="test-operator",
        rationale="Cancel only the exact owned runtime attempts.",
        truth_kind=TruthKind.SERVER_DERIVED,
    ) == active

    snapshot = store.snapshot("runner-mission")
    assert snapshot.mission.status == MissionStatus.CANCELLED
    assert not any(workspace.exists() for workspace in workspaces)
    assert all(lease.released_at is not None for lease in snapshot.leases)


def test_prefetch_failure_commits_every_claimed_attempt_and_releases_leases(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=0
    )
    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )

    def reject(*_args) -> None:
        raise RunnerExecutionFailed(
            "accepted artifact is unavailable",
            result_code=RuntimeErrorCode.ARTIFACT_TAMPERED,
        )

    monkeypatch.setattr(cache, "prefetch", reject)
    with pytest.raises(RunnerExecutionFailed, match="artifact is unavailable"):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            deadline_seconds=5,
            poll_seconds=0,
        ).run("runner-mission")

    snapshot = store.snapshot("runner-mission")
    assert {attempt.task_id for attempt in snapshot.attempts} == {"work-a", "work-z"}
    assert {attempt.state for attempt in snapshot.attempts} == {AttemptState.FAILED}
    assert {attempt.result_code for attempt in snapshot.attempts} == {
        RuntimeErrorCode.ARTIFACT_TAMPERED
    }
    assert all(lease.released_at is not None for lease in snapshot.leases)


def test_external_cancellation_terminalizes_active_batch_before_mission_cancel(
    tmp_path: Path,
) -> None:
    repository, base_sha, runtime_root, evidence, store, assignments, _, _ = _setup(
        tmp_path
    )
    scheduler = MissionScheduler(
        store, clock=SystemClock(), lease_ttl_seconds=30, retry_backoff_seconds=0
    )
    cache = AcceptedArtifactCache()
    adapter_a = _CancellableAdapter("worker-a", "a.txt")
    adapter_z = _CancellableAdapter("worker-z", "b.txt")
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(adapter_a, adapter_z),
        cache=cache,
    )
    unrelated = subprocess.Popen(("/bin/sleep", "10"))
    try:
        with pytest.raises(RunnerCancelled, match="cancellation requested"):
            MissionRunner(
                scheduler=scheduler,
                runtime=runtime,
                worker_ids=("worker-a", "worker-z"),
                accepted_artifacts=cache,
                deadline_seconds=5,
                poll_seconds=0,
                should_cancel=lambda: (
                    adapter_a.started.is_set() and adapter_z.started.is_set()
                ),
            ).run("runner-mission")

        store.cancel(
            "runner-mission",
            "command_external_cancel_after_cleanup",
            expected_head=store.head("runner-mission"),
            operator_label="test-operator",
            rationale="Cancel after exact active-run cleanup.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=datetime.now(UTC),
        )
        snapshot = store.snapshot("runner-mission")
        assert snapshot.mission.status == MissionStatus.CANCELLED
        assert all(item.state == AttemptState.CANCELLED for item in snapshot.attempts)
        assert all(item.released_at is not None for item in snapshot.leases)
        assert not tuple(runtime.workspaces.iterdir())
        assert adapter_a.cancelled.is_set() and adapter_z.cancelled.is_set()
        assert adapter_a.active == adapter_z.active == 0
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_a_cancellation_after_a_passing_check_records_the_stage_it_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A check that passed and was then cancelled must not read as nothing.

    The deadline path is not gated by `cancellation_safe`, so a cancellation
    can land after the acceptance check has already passed — and the workspace
    cleanup that follows it sits outside every failure handler, so without a
    record the attempt reaches the store bare. The cut is driven in exactly
    there: `cleanup` is the first stage after the check, and this asserts the
    evidence chain still says the check had passed.
    """
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, delay=0
    )
    original = WorkerContext._effect

    async def cancel_at_cleanup(self, label, action):
        if label == "cleanup" and self.dispatch.task_id == "work-a":
            raise asyncio.CancelledError()
        return await original(self, label, action)

    monkeypatch.setattr(WorkerContext, "_effect", cancel_at_cleanup)

    scheduler = MissionScheduler(store, clock=SystemClock())
    cache = AcceptedArtifactCache()
    runtime = _runtime(
        repository=repository,
        base_sha=base_sha,
        runtime_root=runtime_root,
        evidence=evidence,
        scheduler=scheduler,
        assignments=assignments,
        adapters=(a, z),
        cache=cache,
    )

    with pytest.raises(RunnerError):
        MissionRunner(
            scheduler=scheduler,
            runtime=runtime,
            worker_ids=("worker-a", "worker-z"),
            accepted_artifacts=cache,
            deadline_seconds=3_600,
            poll_seconds=0,
            monotonic=lambda: 0.0,
        ).run("runner-mission")

    attempt = next(
        item
        for item in store.snapshot("runner-mission").attempts
        if item.task_id == "work-a"
    )
    evidence_id = (
        "attempt_evidence_"
        + canonical_json_sha256(("runner-mission", attempt.attempt_id))[:24]
    )
    events = evidence.tail(evidence_id, 0, evidence.head(evidence_id).seq)
    kinds = [item.event_type for item in events]
    assert AttemptEvidenceEventType.CHECK_COMPLETED in kinds
    cancelled = next(
        item
        for item in events
        if item.event_type == AttemptEvidenceEventType.OPERATION_FAILED
        and item.payload.get("reason") == "cancelled"
    )
    # The evidence says what actually happened: the check had already passed,
    # and the last stage the attempt finished was storing that check's receipt.
    assert cancelled.payload["check_completed"] is True
    assert cancelled.payload["stage_reached"] == "store-check-receipt"
    stages = str(cancelled.payload["completed_stages"]).split(",")
    assert stages.index("check") < stages.index("store-check-receipt")
    # And the attempt itself is still recorded as cancelled, not as a success.
    assert attempt.state in {AttemptState.CANCELLED, AttemptState.FAILED}
