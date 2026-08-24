"""The retry learns from the attempt before it, or it terminates honestly.

Before this, a failing trusted check was hashed and the text discarded, so the
second attempt re-sent a byte-identical prompt: two draws from the same
distribution dressed up as recovery. Proven here, credential-free:

* a failing check leaves a redacted ``check-diagnostic`` artifact bound to the
  failed attempt, alongside the trusted check receipt;
* ``_diagnostic_aware_assignment`` turns that artifact into a ``PriorFailure``
  on the retry, carrying the prior attempt id, its fence, the result code, the
  failed check names and the receipt digest — and nothing else;
* the live Gemini worker puts exactly that object in the model payload and adds
  a repair instruction, while a first attempt's payload is unchanged;
* the repair scope does not widen: ``prior_failure`` carries no paths and the
  assignment's ``output_paths`` are identical on both attempts;
* a second failure with the same signature is terminal, not a third blind draw.

Not proven here: that a live model repairs the fault it is shown. That is the
completion gate, and it needs live missions.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from graphene.cli.mission import _diagnostic_aware_assignment, _prior_failure
from graphene.hashing import sha256_hex
from graphene.orchestration.diagnostics import (
    CHECK_DIAGNOSTIC_KIND,
    CheckDiagnostic,
    summarize_check_failure,
)
from graphene.orchestration.models import AttemptState, MissionStatus
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.runner import (
    AcceptedArtifactCache,
    MissionRunner,
    RunnerExecutionFailed,
)
from graphene.orchestration.runtime import (
    CheckOutcome,
    PriorFailure,
    RuntimeAssignment,
    RuntimeErrorCode,
    RuntimeFailure,
)
from graphene.orchestration.scheduler import MissionScheduler, SystemClock
from graphene.orchestration.store import SQLiteMissionStore
from graphene.orchestration.workers.deterministic import DeterministicWorkerModel
from graphene.orchestration.workers.gemini import FileMutation, GeminiWorkerAdapter
from graphene.orchestration.runtime import WorkerRegistry, WorkerRuntime
from tests.unit.orchestration.test_runner import _CheckRunner, _runtime, _setup
from tests.unit.orchestration.test_runtime_workers import (
    CHECK,
    NOW,
    _dispatch,
    _repository,
)

def _dispatch_like(attempt) -> SimpleNamespace:
    """The two fields the resolver reads off a real Dispatch."""

    return SimpleNamespace(
        task_id=attempt.task_id, attempt_number=attempt.attempt_number
    )


FAILING_OUTPUT = """\
=================================== FAILURES ===================================
______________________________ test_rows_match _______________________________
E       AssertionError: assert 3 == 4
=========================== short test summary info ============================
FAILED tests/test_report_json.py::test_rows_match - AssertionError: assert 3 == 4
1 failed, 7 passed in 0.31s
"""


class _DiagnosticCheckRunner(_CheckRunner):
    """Fail ``work-a`` once with real-shaped pytest output, then pass."""

    def __init__(self, *, always: bool = False) -> None:
        self.failures = 0
        self.always = always

    async def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        outcome = await super().__call__(workspace, assignment, owner_id)
        if assignment.task_id != "work-a" or (self.failures and not self.always):
            return outcome
        self.failures += 1
        encoded = FAILING_OUTPUT.encode("utf-8")
        return outcome.model_copy(
            update={
                "exit_code": 1,
                "output_sha256": sha256_hex(encoded),
                "diagnostic": summarize_check_failure(
                    FAILING_OUTPUT,
                    exit_code=1,
                    timed_out=False,
                    output_truncated=False,
                    cleanup_complete=True,
                    output_sha256=sha256_hex(encoded),
                    output_byte_count=len(encoded),
                ),
            }
        )


def _run(
    tmp_path: Path,
    check_runner,
    *,
    attempt_limit: int = 2,
    diagnostic_aware: bool = True,
):
    """Run the fixture mission, optionally with the blind resolver as a control."""
    repository, base_sha, runtime_root, evidence, store, assignments, a, z = _setup(
        tmp_path, retry_work_a=True, attempt_limit=attempt_limit
    )
    scheduler = MissionScheduler(store, clock=SystemClock(), retry_backoff_seconds=0)
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
        check_runner=check_runner,
    )
    if diagnostic_aware:
        runtime.assignment = _diagnostic_aware_assignment(
            assignments, store, evidence, "runner-mission"
        )
    runner = MissionRunner(
        scheduler=scheduler,
        runtime=runtime,
        worker_ids=("worker-a", "worker-z"),
        accepted_artifacts=cache,
        # Generous on purpose. The runner returns as soon as the mission
        # settles, so a large budget costs a fast machine nothing — and a small
        # one turns this into a load-dependent test that fails when it runs
        # after a full matrix.
        deadline_seconds=120,
        poll_seconds=0,
    )
    try:
        runner.run("runner-mission")
    except RunnerExecutionFailed:
        pass
    # Assertions read committed store state, never the runner's return value:
    # a mission that ends FAILED is a legitimate outcome here.
    return store.snapshot("runner-mission"), store, evidence, assignments


def _reopen(root: Path) -> SQLiteMissionStore:
    return SQLiteMissionStore(
        root / "missions.sqlite",
        artifact_resolver=SQLiteAttemptEvidenceStore(root / "evidence.sqlite"),
    )


def _work_a_attempts(store):
    return sorted(
        (
            item
            for item in store.snapshot("runner-mission").attempts
            if item.task_id == "work-a"
        ),
        key=lambda item: item.attempt_number,
    )


def test_a_failed_check_leaves_a_redacted_diagnostic_the_retry_can_read(
    tmp_path: Path,
) -> None:
    snapshot, store, evidence, assignments = _run(tmp_path, _DiagnosticCheckRunner())

    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    attempts = sorted(
        (item for item in snapshot.attempts if item.task_id == "work-a"),
        key=lambda item: item.attempt_number,
    )
    assert [item.state for item in attempts] == [
        AttemptState.FAILED,
        AttemptState.COMMITTED,
    ]
    failed = attempts[0]
    reference = next(
        item for item in failed.evidence_refs if item.kind == CHECK_DIAGNOSTIC_KIND
    )
    raw = evidence.resolve(reference.kind, reference.id)
    assert raw is not None and sha256_hex(raw) == reference.sha256
    diagnostic = CheckDiagnostic.model_validate_json(raw)
    assert diagnostic.failure_class == "checks_failed"
    assert diagnostic.failed_check_names == (
        "tests/test_report_json.py::test_rows_match",
    )
    assert "AssertionError" in diagnostic.summary
    assert diagnostic.output_sha256 == sha256_hex(FAILING_OUTPUT.encode("utf-8"))

    # A passing attempt teaches nothing and stores nothing.
    assert not [
        item
        for item in attempts[1].evidence_refs
        if item.kind == CHECK_DIAGNOSTIC_KIND
    ]


def test_the_retry_assignment_carries_the_prior_failure_and_not_a_wider_scope(
    tmp_path: Path,
) -> None:
    snapshot, store, evidence, assignments = _run(tmp_path, _DiagnosticCheckRunner())
    attempts = sorted(
        (item for item in snapshot.attempts if item.task_id == "work-a"),
        key=lambda item: item.attempt_number,
    )
    failed, retried = attempts

    resolve = _diagnostic_aware_assignment(
        assignments, store, evidence, "runner-mission"
    )
    first = resolve(_dispatch_like(failed))
    second = resolve(_dispatch_like(retried))

    assert first.prior_failure is None
    prior = second.prior_failure
    assert isinstance(prior, PriorFailure)
    assert prior.attempt_id == failed.attempt_id
    assert prior.attempt_number == failed.attempt_number
    assert prior.fencing_token == failed.fencing_token < retried.fencing_token
    assert prior.result_code == "acceptance_check_failed"
    assert prior.failure_class == "checks_failed"
    assert prior.failed_check_names == ("tests/test_report_json.py::test_rows_match",)
    assert prior.receipt_sha256 == next(
        item for item in failed.evidence_refs if item.kind == "test-receipt"
    ).sha256

    # The repair scope is unchanged, and PriorFailure carries no paths at all.
    assert first.output_paths == second.output_paths
    assert not [
        name for name in prior.model_dump() if "path" in name or "glob" in name
    ]


def test_a_repeated_identical_failure_signature_is_terminal_not_a_third_draw(
    tmp_path: Path,
) -> None:
    """The budget allows three attempts; a repeat of the same failure stops at two."""
    aware_root = tmp_path / "aware"
    blind_root = tmp_path / "blind"
    aware_root.mkdir()
    blind_root.mkdir()

    _run(aware_root, _DiagnosticCheckRunner(always=True), attempt_limit=3)
    aware = _work_a_attempts(_reopen(aware_root))

    # Control: the same budget with the blind resolver spends every attempt.
    _run(
        blind_root,
        _DiagnosticCheckRunner(always=True),
        attempt_limit=3,
        diagnostic_aware=False,
    )
    blind = _work_a_attempts(_reopen(blind_root))

    assert [item.state for item in aware] == [AttemptState.FAILED, AttemptState.FAILED]
    assert [item.state for item in blind] == [
        AttemptState.FAILED,
        AttemptState.FAILED,
        AttemptState.FAILED,
    ]
    assert len(aware) < len(blind)


def test_runtime_failure_marks_a_repeat_terminal() -> None:
    """The flag the runtime sets when the retry produced the same failure."""
    assert not RuntimeFailure(RuntimeErrorCode.ACCEPTANCE_CHECK_FAILED).terminal
    assert RuntimeFailure(
        RuntimeErrorCode.ACCEPTANCE_CHECK_FAILED, terminal=True
    ).terminal


def test_prior_failure_is_none_when_the_diagnostic_cannot_be_resolved(
    tmp_path: Path,
) -> None:
    """A missing or tampered diagnostic degrades to the old blind retry, never a crash."""
    snapshot, store, evidence, _assignments = _run(tmp_path, _DiagnosticCheckRunner())
    retried = max(
        (item for item in snapshot.attempts if item.task_id == "work-a"),
        key=lambda item: item.attempt_number,
    )

    class _Broken:
        def resolve(self, _kind, _identifier):
            return b"not a diagnostic"

    assert (
        _prior_failure(store, _Broken(), "runner-mission", _dispatch_like(retried))
        is None
    )




def test_the_worker_payload_carries_the_prior_failure_and_a_repair_instruction(
    tmp_path: Path,
) -> None:
    """What the model is told changes between attempt 1 and attempt 2, and only that."""
    repository, base_sha = _repository(tmp_path / "user-checkout")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    assignment = RuntimeAssignment(
        task_id="work-a",
        title="Change A",
        contract="Change only the leased A file.",
        read_paths=("a.txt",),
        output_name="patch-a",
        output_kind="patch",
        output_paths=("a.txt",),
        command_template=CHECK,
    )
    prior = PriorFailure(
        attempt_id="attempt-a",
        attempt_number=1,
        fencing_token=1,
        result_code="acceptance_check_failed",
        failure_class="checks_failed",
        failed_check_names=("tests/test_report_json.py::test_rows_match",),
        summary="AssertionError: assert 3 == 4",
        receipt_sha256="c" * 64,
        failure_signature="d" * 64,
    )

    first = _worker_prompt(tmp_path / "one", repository, base_sha, evidence, assignment)
    second = _worker_prompt(
        tmp_path / "two",
        repository,
        base_sha,
        evidence,
        assignment.model_copy(update={"prior_failure": prior}),
    )

    assert "prior_failure" not in first.prompt
    assert "Repair the cause it names" not in first.instruction

    assert "prior_failure" in second.prompt
    assert "tests/test_report_json.py::test_rows_match" in second.prompt
    assert "assert 3 == 4" in second.prompt
    assert "attempt-a" in second.prompt
    assert "c" * 64 in second.prompt
    assert "Repair the cause it names" in second.instruction
    assert "do not widen it" in second.instruction

    # The prompt gained the diagnostic and nothing else.
    assert json.loads(first.prompt).keys() | {"prior_failure"} == (
        json.loads(second.prompt).keys()
    )
    for key, value in json.loads(first.prompt).items():
        assert json.loads(second.prompt)[key] == value


def _worker_prompt(
    root: Path,
    repository: Path,
    base_sha: str,
    evidence: SQLiteAttemptEvidenceStore,
    assignment: RuntimeAssignment,
) -> DeterministicWorkerModel:
    """Run one fake-model attempt and hand back the model that saw the prompt."""
    root.mkdir()
    model = DeterministicWorkerModel(model="fixture-worker")
    model.bind((FileMutation(operation="update", path="a.txt", text="a-after\n"),))
    dispatch = _dispatch(
        task_id="work-a",
        worker_id="worker-a",
        workspace_id="workspace-" + root.name,
        attempt_id="attempt-" + root.name,
        lease_id="lease-" + root.name,
        fence=1,
        writes=("a.txt",),
    )
    runtime = WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=root,
        evidence=evidence,
        registry=WorkerRegistry(
            (GeminiWorkerAdapter.fake(worker_id="worker-a", model=model),)
        ),
        assignment=lambda _: assignment,
        accepted_artifact=lambda *_: b"",
        check_runner=_PassingCheckRunner(),
        policy_sha256="a" * 64,
        fence=lambda *_: None,
        heartbeat=lambda _: None,
        clock=lambda: NOW,
    )
    asyncio.run(runtime.execute_async(dispatch))
    assert model.calls == 1
    return model


class _PassingCheckRunner(_CheckRunner):
    pass
