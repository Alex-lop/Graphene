from __future__ import annotations

import asyncio
import json
import shutil
import signal
import sqlite3
import stat
import subprocess
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graphene.cli import mission as mission_cli
import graphene.orchestration.worker_runtime as runtime_module
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.orchestration.evidence import (
    AttemptEvidenceEventType,
    SQLiteAttemptEvidenceStore,
)
from graphene.orchestration.mission_models import (
    ArtifactVisibility,
    CommandTemplate,
    Dispatch,
    PublishedArtifactReferenceV2,
    TaskKind,
)
from graphene.orchestration.worker_runtime import (
    WORKER_PROVIDER_INTERRUPTION_KIND,
    WORKER_PROVIDER_RECEIPT_KIND,
    CheckOutcome,
    CompletionOutcome,
    DockerCheckRunner,
    RuntimeAssignment,
    RuntimeErrorCode,
    RuntimeFailure,
    WorkerCapabilities,
    WorkerCompletion,
    WorkerContext,
    WorkerProviderInterruption,
    WorkerProviderReceipt,
    WorkerRegistry,
    WorkerRuntime,
    stable_operation_id,
)
from graphene.orchestration.process_control import (
    OwnedProcessRegistry,
    ProcessControlError,
)
from graphene.orchestration.workers import (
    DeterministicWorkerModel,
    FileMutation,
    GeminiWorkerAdapter,
    WorkerIntent,
)


NOW = datetime(2026, 8, 20, tzinfo=UTC)
CHECK = CommandTemplate(
    template_id="unit-check",
    argv=("python", "-m", "pytest", "-q"),
    timeout_seconds=30,
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repository(path: Path) -> tuple[Path, str]:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "runtime@example.invalid")
    _git(path, "config", "user.name", "Runtime Test")
    (path / "a.txt").write_text("a-before\n")
    (path / "b.txt").write_text("b-before\n")
    _git(path, "add", "a.txt", "b.txt")
    _git(path, "commit", "-q", "-m", "base")
    return path, _git(path, "rev-parse", "HEAD")


def _dispatch(
    *,
    task_id: str,
    worker_id: str,
    workspace_id: str,
    attempt_id: str,
    lease_id: str,
    fence: int,
    kind: TaskKind = TaskKind.WORK,
    writes: tuple[str, ...] = (),
    inputs=(),
) -> Dispatch:
    return Dispatch(
        mission_id="mission-runtime",
        plan_revision=1,
        plan_sha256="0" * 64,
        task_id=task_id,
        task_kind=kind,
        attempt_id=attempt_id,
        attempt_number=1,
        worker_id=worker_id,
        workspace_id=workspace_id,
        lease_id=lease_id,
        fencing_token=fence,
        dispatch_command_id=f"dispatch-command-{task_id}-0001",
        write_paths=writes,
        allowed_commands=("unit-check",),
        acceptance_checks=("unit-check",),
        input_publications=inputs,
        expires_at=NOW + timedelta(minutes=5),
    )


def test_worker_intent_accepts_ordered_typed_file_operations() -> None:
    mutations = (
        FileMutation(
            operation="create",
            path="created.txt",
            text="created\n",
            mode="100644",
        ),
        FileMutation(operation="update", path="updated.txt", text="updated\n"),
        FileMutation(operation="delete", path="deleted.txt"),
        FileMutation(operation="rename", path="old.txt", new_path="new.txt"),
        FileMutation(operation="chmod", path="script.sh", mode="100755"),
    )

    assert WorkerIntent(mutations=mutations).mutations == mutations


@pytest.mark.parametrize(
    "mutation",
    (
        {"operation": "create", "path": "file.txt", "text": "missing mode"},
        {
            "operation": "update",
            "path": "file.txt",
            "text": "unexpected mode",
            "mode": "100644",
        },
        {"operation": "delete", "path": "file.txt", "text": "unexpected"},
        {"operation": "rename", "path": "file.txt"},
        {"operation": "rename", "path": "file.txt", "new_path": "file.txt"},
        {"operation": "chmod", "path": "file.txt"},
        {"operation": "chmod", "path": "file.txt", "mode": "120000"},
    ),
)
def test_file_mutation_rejects_wrong_operation_shape(mutation: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        FileMutation.model_validate(mutation)


def test_typed_mutations_publish_exact_patch_and_bound_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _ = _repository(tmp_path / "user-checkout")
    (repository / "old-name.txt").write_text("rename me\n")
    _git(repository, "add", "old-name.txt")
    _git(repository, "commit", "-q", "-m", "add rename source")
    base_sha = _git(repository, "rev-parse", "HEAD")
    source_status = _git(repository, "status", "--porcelain=v1")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    writes = (
        "a.txt",
        "b.txt",
        "created.txt",
        "new-name.txt",
        "old-name.txt",
    )
    observed_manifests: list[str] = []
    trusted_audit = runtime_module.audit_workspace

    def observe_audit(*args, **kwargs):
        audit = trusted_audit(*args, **kwargs)
        if audit.changed_paths == writes:
            observed_manifests.append(audit.patch_sha256)
        return audit

    monkeypatch.setattr(runtime_module, "audit_workspace", observe_audit)
    model = DeterministicWorkerModel(model="fixture-mutation-worker")
    model.bind(
        (
            FileMutation(
                operation="rename",
                path="old-name.txt",
                new_path="new-name.txt",
            ),
            FileMutation(operation="chmod", path="new-name.txt", mode="100755"),
            FileMutation(operation="update", path="a.txt", text="a-after\n"),
            FileMutation(operation="delete", path="b.txt"),
            FileMutation(
                operation="create",
                path="created.txt",
                text="created\n",
                mode="100644",
            ),
        )
    )
    assignment = RuntimeAssignment(
        task_id="work-mutations",
        title="Apply typed mutations",
        contract="Apply the exact leased file operations.",
        read_paths=("a.txt", "b.txt", "old-name.txt"),
        output_name="mutation-patch",
        output_kind="patch",
        output_paths=writes,
        command_template=CHECK,
    )

    async def check(
        workspace: Path, assigned: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        assert assigned == assignment
        assert owner_id
        assert (workspace / "a.txt").read_text() == "a-after\n"
        assert not (workspace / "b.txt").exists()
        assert (workspace / "created.txt").read_text() == "created\n"
        assert not (workspace / "old-name.txt").exists()
        assert (workspace / "new-name.txt").read_text() == "rename me\n"
        assert stat.S_IMODE((workspace / "new-name.txt").stat().st_mode) == 0o755
        return CheckOutcome(
            template_id=CHECK.template_id,
            template_sha256=canonical_json_sha256(CHECK.model_dump(mode="json")),
            exit_code=0,
            timed_out=False,
            output_sha256=sha256_hex(b"passed"),
            output_truncated=False,
            cleanup_complete=True,
        )

    dispatch = _dispatch(
        task_id="work-mutations",
        worker_id="mutation-worker",
        workspace_id="workspace-mutations",
        attempt_id="attempt-mutations",
        lease_id="lease-mutations",
        fence=7,
        writes=writes,
    )
    runtime = WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=WorkerRegistry(
            (GeminiWorkerAdapter.fake(worker_id="mutation-worker", model=model),)
        ),
        assignment=lambda _: assignment,
        accepted_artifact=lambda *_: b"",
        check_runner=check,
        policy_sha256="a" * 64,
        fence=lambda *_: None,
        heartbeat=lambda _: None,
        clock=lambda: NOW,
    )

    run = asyncio.run(runtime.execute_async(dispatch))

    assert run.result.succeeded, run.result.result_code
    assert observed_manifests
    patch_reference = next(
        item for item in run.result.evidence_refs if item.kind == "patch"
    )
    patch_envelope = next(
        item for item in run.result.artifact_envelopes if item.kind == "patch"
    )
    assert evidence.verify_enveloped(
        patch_envelope,
        expected={"mutation_manifest_sha256": observed_manifests[-1]},
    )
    patch = evidence.resolve(patch_reference.kind, patch_reference.id)
    assert patch is not None
    candidate = tmp_path / "candidate"
    subprocess.run(
        ("git", "clone", "-q", "--no-hardlinks", str(repository), str(candidate)),
        check=True,
    )
    subprocess.run(
        ("git", "apply", "--whitespace=nowarn", "-"),
        cwd=candidate,
        input=patch,
        check=True,
    )
    assert (candidate / "a.txt").read_text() == "a-after\n"
    assert not (candidate / "b.txt").exists()
    assert (candidate / "created.txt").read_text() == "created\n"
    assert not (candidate / "old-name.txt").exists()
    assert (candidate / "new-name.txt").read_text() == "rename me\n"
    assert stat.S_IMODE((candidate / "new-name.txt").stat().st_mode) == 0o755
    assert _git(repository, "status", "--porcelain=v1") == source_status


def test_two_adk_workers_overlap_replay_and_feed_exact_assembly_verification(
    tmp_path: Path,
) -> None:
    repository, base_sha = _repository(tmp_path / "user-checkout")
    source_before = {
        path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
    }
    status_before = _git(repository, "status", "--porcelain=v1")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")

    arrived_a, arrived_b, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    model_a = DeterministicWorkerModel(model="fixture-worker-a")
    model_a.bind(
        (FileMutation(operation="update", path="a.txt", text="a-after\n"),),
        arrived=arrived_a,
        release=release,
    )
    model_b = DeterministicWorkerModel(model="fixture-worker-b")
    model_b.bind(
        (FileMutation(operation="update", path="b.txt", text="b-after\n"),),
        arrived=arrived_b,
        release=release,
    )
    registry = WorkerRegistry(
        (
            GeminiWorkerAdapter.fake(
                worker_id="worker-a", model=model_a, heartbeat_seconds=0.01
            ),
            GeminiWorkerAdapter.fake(
                worker_id="worker-b", model=model_b, heartbeat_seconds=0.01
            ),
        )
    )
    assignments = {
        "work-a": RuntimeAssignment(
            task_id="work-a",
            title="Change A",
            contract="Change only the leased A file.",
            read_paths=("a.txt",),
            output_name="patch-a",
            output_kind="patch",
            output_paths=("a.txt",),
            command_template=CHECK,
        ),
        "work-b": RuntimeAssignment(
            task_id="work-b",
            title="Change B",
            contract="Change only the leased B file.",
            read_paths=("b.txt",),
            output_name="patch-b",
            output_kind="patch",
            output_paths=("b.txt",),
            command_template=CHECK,
        ),
        "assemble": RuntimeAssignment(
            task_id="assemble",
            title="Assemble",
            contract="Assemble only accepted patches.",
            read_paths=("a.txt", "b.txt"),
            output_name="candidate",
            output_kind="patch",
            command_template=CHECK,
        ),
        "verify": RuntimeAssignment(
            task_id="verify",
            title="Verify",
            contract="Verify the exact accepted candidate.",
            read_paths=("a.txt", "b.txt"),
            output_name="verification",
            output_kind="test-receipt",
            command_template=CHECK,
        ),
    }
    supplied = evidence.put_artifact("operator-input", b"private guidance for A")
    accepted: dict[tuple[str, str], bytes] = {
        (supplied.id, supplied.sha256): b"private guidance for A"
    }
    fences: list[tuple[str, str, str, int]] = []
    heartbeats: list[str] = []

    async def fence(dispatch: Dispatch, operation_id: str) -> None:
        fences.append(
            (
                dispatch.attempt_id,
                dispatch.lease_id,
                operation_id,
                dispatch.fencing_token,
            )
        )

    async def heartbeat(dispatch: Dispatch) -> None:
        heartbeats.append(dispatch.attempt_id)

    def resolve(dispatch: Dispatch, reference) -> bytes:
        del dispatch
        return accepted[(reference.id, reference.sha256)]

    runtime: WorkerRuntime

    async def check(
        workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        assert workspace.is_relative_to(runtime_root / "worker-workspaces")
        assert owner_id
        # The trusted check runner can resolve the active dispatch by owner id.
        assert runtime.dispatch_for(owner_id).attempt_id == owner_id
        await asyncio.sleep(0.01)
        return CheckOutcome(
            template_id=assignment.command_template.template_id,
            template_sha256=canonical_json_sha256(
                assignment.command_template.model_dump(mode="json")
            ),
            exit_code=0,
            timed_out=False,
            output_sha256=sha256_hex(b"passed"),
            output_truncated=False,
            cleanup_complete=True,
            truth_kind=(
                "simulated_fixture" if assignment.task_id == "verify" else None
            ),
            truth_label=(
                "fixture_verification_truth" if assignment.task_id == "verify" else None
            ),
        )

    runtime = WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=registry,
        assignment=lambda dispatch: assignments[dispatch.task_id],
        accepted_artifact=resolve,
        check_runner=check,
        policy_sha256="a" * 64,
        fence=fence,
        heartbeat=heartbeat,
        clock=lambda: NOW,
    )
    work_a = _dispatch(
        task_id="work-a",
        worker_id="worker-a",
        workspace_id="workspace-a",
        attempt_id="attempt-a",
        lease_id="lease-a",
        fence=11,
        writes=("a.txt",),
        inputs=(supplied,),
    )
    work_b = _dispatch(
        task_id="work-b",
        worker_id="worker-b",
        workspace_id="workspace-b",
        attempt_id="attempt-b",
        lease_id="lease-b",
        fence=22,
        writes=("b.txt",),
    )

    async def overlap():
        first = asyncio.create_task(runtime.execute_async(work_a))
        second = asyncio.create_task(runtime.execute_async(work_b))
        await asyncio.wait_for(
            asyncio.gather(arrived_a.wait(), arrived_b.wait()), timeout=5
        )
        await asyncio.sleep(0.04)
        workspaces = tuple((runtime_root / "worker-workspaces").iterdir())
        assert len(workspaces) == 2
        assert len({item.resolve() for item in workspaces}) == 2
        assert all(_git(item, "remote") == "" for item in workspaces)
        assert {
            path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
        } == source_before
        release.set()
        return await asyncio.gather(first, second)

    run_a, run_b = asyncio.run(overlap())
    assert run_a.result.succeeded and run_b.result.succeeded
    assert model_a.calls == model_b.calls == 1
    assert "private guidance for A" in model_a.prompt
    assert "private guidance for A" not in model_b.prompt
    assert "private guidance for A" not in run_a.receipt.model_dump_json()
    assert {run_a.receipt.worker_id, run_b.receipt.worker_id} == {
        "worker-a",
        "worker-b",
    }
    assert run_a.receipt.completion.session_id != run_b.receipt.completion.session_id
    assert (
        run_a.receipt.completion.invocation_id != run_b.receipt.completion.invocation_id
    )
    assert run_a.receipt.workspace_id != run_b.receipt.workspace_id
    assert run_a.receipt.attempt_id != run_b.receipt.attempt_id
    assert run_a.receipt.lease_id != run_b.receipt.lease_id
    assert run_a.receipt.fencing_token != run_b.receipt.fencing_token
    assert run_a.receipt.completion.provider is not None
    assert run_a.receipt.completion.provider.driver == "adk_fake"
    assert run_a.receipt.completion.provider.requested_model == "fixture-worker-a"
    assert run_a.receipt.completion.provider.returned_model == "fixture-worker-a"
    assert run_a.receipt.completion.provider.input_bytes > 0
    assert run_a.receipt.completion.provider.output_bytes > 0
    assert run_a.receipt.completion.provider.latency_ms >= 0
    assert (
        run_a.receipt.completion.provider.call_started_at
        <= run_a.receipt.completion.provider.call_ended_at
    )
    assert run_a.receipt.completion.provider.usage_source == "unavailable"
    assert run_a.result.session_id == run_a.receipt.completion.session_id
    assert run_a.result.invocation_id == run_a.receipt.completion.invocation_id
    assert set(heartbeats) == {"attempt-a", "attempt-b"}
    assert not tuple((runtime_root / "worker-workspaces").iterdir())
    assert all(count == 2 for count in Counter(fences).values())
    with pytest.raises(KeyError):
        runtime.dispatch_for("attempt-a")
    # Each worker attempt binds exactly one sanitized provider receipt into its
    # terminal evidence event; the bytes never carry the private operator input.
    for run in (run_a, run_b):
        provider_references = tuple(
            item
            for item in run.result.evidence_refs
            if item.kind == WORKER_PROVIDER_RECEIPT_KIND
        )
        assert len(provider_references) == 1
        content = evidence.resolve(
            WORKER_PROVIDER_RECEIPT_KIND, provider_references[0].id
        )
        assert content is not None
        assert sha256_hex(content) == provider_references[0].sha256
        assert (
            WorkerProviderReceipt.model_validate_json(content)
            == run.receipt.completion.provider
        )
        assert b"private guidance for A" not in content
        assert not {"prompt", "output", "api_key"} & set(json.loads(content))
        assert run.result.evidence_link is not None
        evidence_id = run.result.evidence_link.evidence_id
        events = evidence.tail(evidence_id, 0, 256)
        assert events[-1].event_type == AttemptEvidenceEventType.ATTEMPT_COMPLETED
        assert provider_references[0] in events[-1].references
        assert evidence.verify(evidence_id).seq == len(events)

    crashed = _dispatch(
        task_id="work-a",
        worker_id="worker-a",
        workspace_id="workspace-crashed",
        attempt_id="attempt-crashed",
        lease_id="lease-crashed",
        fence=33,
        writes=("a.txt",),
    )
    runtime._begin_nonreplayable(
        crashed, stable_operation_id(crashed, "model"), "model"
    )
    recovered_unknown = asyncio.run(runtime.execute_async(crashed))
    assert recovered_unknown.result.succeeded is False
    assert recovered_unknown.result.result_code == "outcome_unknown"
    assert model_a.calls == 1
    assert not tuple((runtime_root / "worker-workspaces").iterdir())

    patch_references = []
    for run in (run_a, run_b):
        reference = next(
            item for item in run.result.evidence_refs if item.kind == "patch"
        )
        publication = run.result.publications[0]
        assert publication.artifact is not None
        content = evidence.resolve(reference.kind, reference.id)
        assert content is not None
        accepted[(reference.id, reference.sha256)] = content
        patch_references.append(
            PublishedArtifactReferenceV2(
                **publication.artifact.model_dump(mode="json"),
                publication_id=f"publication-{run.receipt.attempt_id}",
            )
        )
    patch_references.sort(key=lambda item: item.publication_id)
    assembly = _dispatch(
        task_id="assemble",
        worker_id="assembly-worker",
        workspace_id="workspace-assembly",
        attempt_id="attempt-assembly",
        lease_id="lease-assembly",
        fence=33,
        kind=TaskKind.ASSEMBLY,
        inputs=tuple(patch_references),
    )
    assembly_run = asyncio.run(runtime.execute_async(assembly))
    assert assembly_run.result.succeeded
    assert all(
        item.kind != WORKER_PROVIDER_RECEIPT_KIND
        for item in assembly_run.result.evidence_refs
    )
    candidate = next(
        item for item in assembly_run.result.evidence_refs if item.kind == "patch"
    )
    candidate_bytes = evidence.resolve(candidate.kind, candidate.id)
    assert candidate_bytes is not None
    accepted[(candidate.id, candidate.sha256)] = candidate_bytes
    candidate_publication = assembly_run.result.publications[0]
    assert candidate_publication.artifact is not None
    published_candidate = PublishedArtifactReferenceV2(
        **candidate_publication.artifact.model_dump(mode="json"),
        publication_id="publication-assembly",
    )

    verification = _dispatch(
        task_id="verify",
        worker_id="verification-worker",
        workspace_id="workspace-verification",
        attempt_id="attempt-verification",
        lease_id="lease-verification",
        fence=44,
        kind=TaskKind.VERIFICATION,
        inputs=(published_candidate,),
    )
    verification_run = asyncio.run(runtime.execute_async(verification))
    assert verification_run.result.succeeded
    verification_reference = next(
        item
        for item in verification_run.result.evidence_refs
        if item.kind == "test-receipt"
    )
    verification_record = json.loads(
        evidence.resolve(verification_reference.kind, verification_reference.id)
    )
    assert verification_record["candidate_references"] == [
        published_candidate.model_dump(mode="json")
    ]
    assert verification_record["accepted_input_references"] == [
        published_candidate.model_dump(mode="json")
    ]
    assert verification_record["candidate_tree_hash_version"] == "graphene.tree.v2"
    assert verification_record["exit_code"] == 0
    truth_reference = next(
        item
        for item in verification_run.result.evidence_refs
        if item.kind == "simulation-truth-receipt"
    )
    truth_record = json.loads(
        evidence.resolve(truth_reference.kind, truth_reference.id)
    )
    assert truth_record["truth_kind"] == "simulated_fixture"
    assert truth_record["truth_label"] == "fixture_verification_truth"

    replay = asyncio.run(runtime.execute_async(work_a))
    assert replay.replayed is True
    assert replay.receipt == run_a.receipt
    assert model_a.calls == 1
    assert {
        path: (repository / path).read_bytes() for path in ("a.txt", "b.txt")
    } == source_before
    assert _git(repository, "status", "--porcelain=v1") == status_before
    assert not tuple((runtime_root / "worker-workspaces").iterdir())


class _StubAdapter:
    """Minimal WorkerAdapter returning one fixed completion with a receipt."""

    def __init__(self, worker_id: str, completion: WorkerCompletion) -> None:
        self.capabilities = WorkerCapabilities(
            worker_id=worker_id, driver="adk_fake", task_kinds=(TaskKind.WORK,)
        )
        self._completion = completion
        self.calls = 0

    async def execute(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion:
        del context, assignment
        self.calls += 1
        return self._completion


def _provider_receipt() -> WorkerProviderReceipt:
    return WorkerProviderReceipt(
        driver="adk_fake",
        client_version="test",
        requested_model="stub-model",
        returned_model="stub-model",
        credential_mode="not_applicable",
        input_bytes=12,
        output_bytes=34,
        latency_ms=5,
        call_started_at="2026-08-20T00:00:00.000Z",
        call_ended_at="2026-08-20T00:00:00.005Z",
        usage_source="unavailable",
    )


def _live_provider_completion(invocation_id: str) -> WorkerCompletion:
    provider = _provider_receipt().model_copy(
        update={
            "driver": "gemini_live",
            "credential_mode": "gemini_api",
        }
    )
    return WorkerCompletion(
        outcome=CompletionOutcome.COMPLETED,
        result_code="passed",
        session_id="session-terminal-cleanup",
        invocation_id=invocation_id,
        provider=provider,
    )


def _terminal_model_process(tmp_path: Path):
    runtime = tmp_path / "mission-runtime" / "adk-runtime"
    runtime.mkdir(parents=True)
    dispatch = _dispatch(
        task_id="work-cleanup",
        worker_id="worker-cleanup",
        workspace_id="workspace-cleanup",
        attempt_id="attempt-cleanup",
        lease_id="lease-cleanup",
        fence=17,
        writes=("a.txt",),
    )
    registry = OwnedProcessRegistry(runtime.parent)
    process = subprocess.Popen(("/bin/sleep", "30"), start_new_session=True)
    owned = registry.record_pid(
        dispatch,
        process.pid,
        "/bin/sleep",
        model_request_sha256="d" * 64,
        model_input_bytes=123,
    )
    barrier = registry.acknowledge_model_dispatch(
        dispatch,
        owned,
        request_sha256="d" * 64,
        sdk_invocation_id="invocation-terminal-cleanup",
        dispatched_at="2026-08-20T00:00:00.000Z",
    )
    process.kill()
    process.wait(timeout=2)
    return runtime, dispatch, registry, owned, barrier


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_terminal_provider_cleanup_recovers_barrier_first_fsync_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, dispatch, registry, owned, _barrier = _terminal_model_process(tmp_path)
    completion = _live_provider_completion("invocation-terminal-cleanup")
    original = OwnedProcessRegistry._fsync_directory
    failed = False

    def fail_after_barrier_unlink(directory: Path) -> None:
        nonlocal failed
        if not failed and directory == registry.barriers:
            failed = True
            raise ProcessControlError("injected barrier fsync crash")
        original(directory)

    monkeypatch.setattr(
        OwnedProcessRegistry,
        "_fsync_directory",
        staticmethod(fail_after_barrier_unlink),
    )
    with pytest.raises(RuntimeFailure) as interrupted:
        WorkerRuntime._clear_provider_process_at(runtime, dispatch, completion)
    assert interrupted.value.code == RuntimeErrorCode.RUNTIME_UNAVAILABLE
    assert registry.terminal_model_state(dispatch) == (owned, None)

    monkeypatch.setattr(
        OwnedProcessRegistry, "_fsync_directory", staticmethod(original)
    )
    WorkerRuntime._clear_provider_process_at(runtime, dispatch, completion)
    WorkerRuntime._clear_provider_process_at(runtime, dispatch, completion)
    assert registry.terminal_model_state(dispatch) == (None, None)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_terminal_provider_cleanup_recovers_record_first_fsync_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, dispatch, registry, owned, barrier = _terminal_model_process(tmp_path)
    completion = _live_provider_completion("invocation-terminal-cleanup")
    registry._owned_path(owned).unlink()
    registry._fsync_directory(registry.directory)
    assert registry.terminal_model_state(dispatch) == (None, barrier)
    original = OwnedProcessRegistry._fsync_directory
    failed = False

    def fail_after_barrier_unlink(directory: Path) -> None:
        nonlocal failed
        if not failed and directory == registry.barriers:
            failed = True
            raise ProcessControlError("injected barrier fsync crash")
        original(directory)

    monkeypatch.setattr(
        OwnedProcessRegistry,
        "_fsync_directory",
        staticmethod(fail_after_barrier_unlink),
    )
    with pytest.raises(RuntimeFailure) as interrupted:
        WorkerRuntime._clear_provider_process_at(runtime, dispatch, completion)
    assert interrupted.value.code == RuntimeErrorCode.RUNTIME_UNAVAILABLE

    monkeypatch.setattr(
        OwnedProcessRegistry, "_fsync_directory", staticmethod(original)
    )
    WorkerRuntime._clear_provider_process_at(runtime, dispatch, completion)
    assert registry.terminal_model_state(dispatch) == (None, None)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_terminal_acknowledged_interruption_clears_record_only_state(
    tmp_path: Path,
) -> None:
    runtime, dispatch, registry, owned, barrier = _terminal_model_process(tmp_path)
    registry._barrier_path(dispatch.attempt_id).unlink()
    registry._fsync_directory(registry.barriers)
    interruption = WorkerProviderInterruption(
        requested_model="gemini-test",
        mission_id=dispatch.mission_id,
        task_id=dispatch.task_id,
        attempt_id=dispatch.attempt_id,
        lease_id=dispatch.lease_id,
        fencing_token=dispatch.fencing_token,
        request_sha256=barrier.request_sha256,
        input_bytes=owned.model_input_bytes,
        provider_dispatch_state="transport_acknowledged",
        sdk_invocation_id=barrier.sdk_invocation_id,
        dispatched_at=barrier.dispatched_at,
        pid=owned.pid,
        pgid=owned.pgid,
        process_started_at=owned.started_at,
        process_identity_version=barrier.schema_version,
        process_birth_token=owned.birth_token,
        executable=owned.executable,
        exit_code=-9,
        signal_name="sigkill",
        stderr_sha256=sha256_hex(b""),
        stderr_truncated=False,
    )
    completion = WorkerCompletion(
        outcome=CompletionOutcome.RETRYABLE_FAILURE,
        result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED,
        session_id="session-terminal-cleanup",
        invocation_id=barrier.sdk_invocation_id,
        provider_interruption=interruption,
    )

    WorkerRuntime._clear_provider_process_at(runtime, dispatch, completion)

    assert registry.terminal_model_state(dispatch) == (None, None)


def test_provider_receipt_call_window_is_validated() -> None:
    receipt = _provider_receipt()
    assert receipt.call_started_at <= receipt.call_ended_at
    for started, ended in (
        ("2026-08-20T00:00:00.005Z", "2026-08-20T00:00:00.000Z"),
        ("2026-08-20T00:00:00Z", "2026-08-20T00:00:00.005Z"),
        ("2026-08-20T00:00:00.000+00:00", "2026-08-20T00:00:00.005Z"),
        ("2026-13-20T00:00:00.000Z", "2026-13-20T00:00:00.005Z"),
    ):
        with pytest.raises(ValueError):
            WorkerProviderReceipt.model_validate(
                {
                    **receipt.model_dump(mode="json"),
                    "call_started_at": started,
                    "call_ended_at": ended,
                }
            )


def _stub_runtime(
    tmp_path: Path,
    adapter: _StubAdapter,
    *,
    evidence: SQLiteAttemptEvidenceStore,
    check_runner,
) -> tuple[WorkerRuntime, Dispatch]:
    repository, base_sha = _repository(tmp_path / "user-checkout")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
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
    dispatch = _dispatch(
        task_id="work-a",
        worker_id=adapter.capabilities.worker_id,
        workspace_id="workspace-a",
        attempt_id="attempt-a",
        lease_id="lease-a",
        fence=11,
        writes=("a.txt",),
    )
    runtime = WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=WorkerRegistry((adapter,)),
        assignment=lambda _: assignment,
        accepted_artifact=lambda *_: b"",
        check_runner=check_runner,
        policy_sha256="a" * 64,
        fence=lambda *_: None,
        heartbeat=lambda _: None,
        clock=lambda: NOW,
    )
    return runtime, dispatch


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_fresh_restart_reconciles_started_host_check_before_model_replay(
    tmp_path: Path,
) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id="session-stub",
            invocation_id="invocation-stub",
        ),
    )
    runtime, dispatch = _stub_runtime(
        tmp_path,
        adapter,
        evidence=evidence,
        check_runner=lambda *_: None,
    )
    runtime._begin_nonreplayable(
        dispatch, stable_operation_id(dispatch, "check"), "check"
    )
    workspace = runtime._workspace(dispatch)
    workspace.mkdir()
    process = subprocess.Popen(("/bin/sleep", "30"), start_new_session=True)
    registry = OwnedProcessRegistry(runtime.runtime.parent)
    registry.record(dispatch, process, "/bin/sleep")
    owned = registry.validate(dispatch)
    reaper = threading.Thread(target=process.wait)
    reaper.start()

    try:
        run = asyncio.run(runtime.execute_async(dispatch))
    finally:
        reaper.join(timeout=0.1)
        if reaper.is_alive():
            registry.signal_prepared(owned, signal.SIGKILL)
        reaper.join(timeout=5)

    assert not reaper.is_alive()
    assert process.returncode == -signal.SIGTERM
    assert run.result.retryable is True
    assert run.result.result_code == RuntimeErrorCode.RUNTIME_UNAVAILABLE
    assert adapter.calls == 0
    assert not workspace.exists()
    assert not registry.has_record(dispatch.attempt_id, model=False)


def test_fresh_restart_reconciles_started_docker_check_before_model_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeDocker:
        def __init__(self) -> None:
            self.owners: list[str] = []

        def reconcile_owned(self, owner_id: str) -> bool:
            self.owners.append(owner_id)
            return True

    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id="session-stub",
            invocation_id="invocation-stub",
        ),
    )
    docker = FakeDocker()
    mission_runtime = tmp_path / "mission-runtime"
    mission_runtime.mkdir(mode=0o700)
    binding = mission_runtime / "start-request.json"
    binding.write_bytes(canonical_json_bytes({"check_executor": "docker"}) + b"\n")
    binding.chmod(0o600)
    monkeypatch.setattr(
        mission_cli, "_mission_runtime", lambda _mission_id: mission_runtime
    )
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "host-sandbox")
    selected = mission_cli._mission_check_executor("mission-runtime-test")
    runtime, dispatch = _stub_runtime(
        tmp_path,
        adapter,
        evidence=evidence,
        check_runner=(
            DockerCheckRunner(docker)  # type: ignore[arg-type]
            if selected == "docker"
            else pytest.fail("durable Docker binding switched executor semantics")
        ),
    )
    runtime._begin_nonreplayable(
        dispatch, stable_operation_id(dispatch, "check"), "check"
    )
    workspace = runtime._workspace(dispatch)
    workspace.mkdir()

    run = asyncio.run(runtime.execute_async(dispatch))

    assert run.result.retryable is True
    assert run.result.result_code == RuntimeErrorCode.SANDBOX_UNAVAILABLE
    assert adapter.calls == 0
    assert docker.owners == [dispatch.attempt_id]
    assert not workspace.exists()


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_expired_orphan_receipt_removes_exact_workspace(tmp_path: Path) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id="session-stub",
            invocation_id="invocation-stub",
        ),
    )
    runtime, dispatch = _stub_runtime(
        tmp_path,
        adapter,
        evidence=evidence,
        check_runner=lambda *_: None,
    )
    dispatch = dispatch.model_copy(update={"task_kind": TaskKind.ASSEMBLY})
    workspace = runtime._workspace(dispatch)
    workspace.mkdir()
    process = subprocess.Popen(("/bin/sleep", "30"), start_new_session=True)
    registry = OwnedProcessRegistry(runtime.runtime.parent)
    registry.record(dispatch, process, "/bin/sleep")
    owned = registry.validate(dispatch)
    reaper = threading.Thread(target=process.wait)
    reaper.start()

    try:
        run = asyncio.run(runtime.reconcile_expired_async(dispatch))
    finally:
        reaper.join(timeout=0.1)
        if reaper.is_alive():
            registry.signal_prepared(owned, signal.SIGKILL)
        reaper.join(timeout=5)

    assert not reaper.is_alive()
    assert process.returncode == -signal.SIGTERM
    assert run is not None
    assert run.result.result_code == RuntimeErrorCode.RUNTIME_UNAVAILABLE
    assert not workspace.exists()


def test_expired_loaded_receipt_removes_exact_workspace(tmp_path: Path) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.RETRYABLE_FAILURE,
            result_code=RuntimeErrorCode.PROVIDER_TIMEOUT,
            session_id="session-stub",
            invocation_id="invocation-stub",
        ),
    )
    runtime, dispatch = _stub_runtime(
        tmp_path,
        adapter,
        evidence=evidence,
        check_runner=lambda *_: None,
    )
    receipt = asyncio.run(runtime.execute_async(dispatch)).receipt
    workspace = runtime._workspace(dispatch)
    workspace.mkdir()

    replayed = asyncio.run(runtime.reconcile_expired_async(dispatch))

    assert replayed is not None and replayed.receipt == receipt
    assert not workspace.exists()


def test_failed_provider_completion_still_binds_its_receipt_as_evidence(
    tmp_path: Path,
) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    provider = _provider_receipt()
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.RETRYABLE_FAILURE,
            result_code="provider_timeout",
            session_id="session-stub",
            invocation_id="invocation-stub",
            provider=provider,
        ),
    )

    async def check(*_):
        raise AssertionError("check must not run after a failed completion")

    runtime, dispatch = _stub_runtime(
        tmp_path, adapter, evidence=evidence, check_runner=check
    )

    run = asyncio.run(runtime.execute_async(dispatch))

    assert run.result.succeeded is False
    assert run.result.retryable is True
    assert run.result.result_code == "provider_timeout"
    assert run.result.publications == ()
    references = tuple(
        item
        for item in run.result.evidence_refs
        if item.kind == WORKER_PROVIDER_RECEIPT_KIND
    )
    assert len(references) == 1
    content = evidence.resolve(WORKER_PROVIDER_RECEIPT_KIND, references[0].id)
    assert content is not None
    assert sha256_hex(content) == references[0].sha256
    assert WorkerProviderReceipt.model_validate_json(content) == provider
    assert run.result.evidence_link is not None
    events = evidence.tail(run.result.evidence_link.evidence_id, 0, 256)
    assert events[-1].event_type == AttemptEvidenceEventType.ATTEMPT_FAILED
    assert events[-1].references == references
    assert run.receipt.completion.provider == provider
    assert adapter.calls == 1


def test_receipt_replay_finishes_terminal_evidence_after_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.RETRYABLE_FAILURE,
            result_code=RuntimeErrorCode.PROVIDER_TIMEOUT,
            session_id="session-stub",
            invocation_id="invocation-stub",
        ),
    )

    async def check(*_):
        raise AssertionError("check must not run after a failed completion")

    runtime, dispatch = _stub_runtime(
        tmp_path, adapter, evidence=evidence, check_runner=check
    )
    original_record = runtime._record
    fsync_modes: list[int] = []
    original_fsync = runtime_module.os.fsync

    def observe_fsync(descriptor: int) -> None:
        fsync_modes.append(runtime_module.os.fstat(descriptor).st_mode)
        original_fsync(descriptor)

    def crash_before_terminal(dispatch, event_type, payload, references=()):
        if event_type in {
            AttemptEvidenceEventType.ATTEMPT_COMPLETED,
            AttemptEvidenceEventType.ATTEMPT_FAILED,
        }:
            raise RuntimeError("simulated crash after durable receipt")
        return original_record(dispatch, event_type, payload, references)

    monkeypatch.setattr(runtime_module.os, "fsync", observe_fsync)
    monkeypatch.setattr(runtime, "_record", crash_before_terminal)
    with pytest.raises(RuntimeError, match="after durable receipt"):
        asyncio.run(runtime.execute_async(dispatch))

    receipt = runtime._load_receipt(dispatch)
    assert receipt is not None
    assert stat.S_ISDIR(fsync_modes[-1])
    events = evidence.tail(runtime._evidence_id(dispatch), 0, 256)
    assert events[-1].event_type == AttemptEvidenceEventType.ATTEMPT_STARTED

    monkeypatch.setattr(runtime, "_record", original_record)
    replayed = asyncio.run(runtime.execute_async(dispatch))

    assert replayed.replayed is True
    assert replayed.receipt == receipt
    assert adapter.calls == 1
    events = evidence.tail(runtime._evidence_id(dispatch), 0, 256)
    assert events[-1].event_type == AttemptEvidenceEventType.ATTEMPT_FAILED


def test_interrupted_provider_completion_is_retryable_and_preserves_absent_effect(
    tmp_path: Path,
) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    interruption = WorkerProviderInterruption(
        requested_model="gemini-3.5-flash",
        mission_id="mission-runtime",
        task_id="work-a",
        attempt_id="attempt-a",
        lease_id="lease-a",
        fencing_token=11,
        request_sha256="b" * 64,
        input_bytes=123,
        sdk_invocation_id="invocation-interrupted",
        dispatched_at="2026-08-20T00:00:00.000Z",
        pid=321,
        pgid=321,
        process_started_at="Thu Aug 20 00:00:00 2026",
        process_birth_token="test:birth:321",
        executable="/usr/bin/python3",
        exit_code=-9,
        signal_name="sigkill",
        stderr_sha256=sha256_hex(b"private provider detail"),
        stderr_truncated=False,
    )
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.RETRYABLE_FAILURE,
            result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED,
            session_id="session-interrupted",
            invocation_id="invocation-interrupted",
            provider_interruption=interruption,
        ),
    )

    async def check(*_):
        raise AssertionError("check must not run after an interrupted model child")

    runtime, dispatch = _stub_runtime(
        tmp_path, adapter, evidence=evidence, check_runner=check
    )
    run = asyncio.run(runtime.execute_async(dispatch))

    assert run.result.succeeded is False
    assert run.result.retryable is True
    assert run.result.result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED
    assert run.result.publications == ()
    assert run.receipt.completion.provider_interruption == interruption
    assert interruption.repository_effect == "known_absent"
    references = tuple(
        item
        for item in run.result.evidence_refs
        if item.kind == WORKER_PROVIDER_INTERRUPTION_KIND
    )
    assert len(references) == 1
    content = evidence.resolve(WORKER_PROVIDER_INTERRUPTION_KIND, references[0].id)
    assert content is not None
    assert sha256_hex(content) == references[0].sha256
    assert b"private provider detail" not in content
    assert WorkerProviderInterruption.model_validate_json(content) == interruption
    assert run.result.evidence_link is not None
    events = evidence.tail(run.result.evidence_link.evidence_id, 0, 256)
    assert events[-1].event_type == AttemptEvidenceEventType.ATTEMPT_FAILED
    assert events[-1].references == references
    assert adapter.calls == 1


def test_failed_provider_receipt_write_never_yields_a_completed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    adapter = _StubAdapter(
        "stub-worker",
        WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id="session-stub",
            invocation_id="invocation-stub",
            provider=_provider_receipt(),
        ),
    )
    original_put = evidence.put_artifact

    def failing_put(kind, content, *, visibility=ArtifactVisibility.PRIVATE):
        if kind == WORKER_PROVIDER_RECEIPT_KIND:
            raise sqlite3.OperationalError("private disk detail must not escape")
        return original_put(kind, content, visibility=visibility)

    monkeypatch.setattr(evidence, "put_artifact", failing_put)

    async def check(*_):
        raise AssertionError("check must not run when receipt binding failed")

    runtime, dispatch = _stub_runtime(
        tmp_path, adapter, evidence=evidence, check_runner=check
    )

    run = asyncio.run(runtime.execute_async(dispatch))

    assert run.result.succeeded is False
    assert run.result.retryable is True
    assert run.result.result_code == RuntimeErrorCode.RUNTIME_UNAVAILABLE
    assert run.result.publications == ()
    assert all(
        item.kind != WORKER_PROVIDER_RECEIPT_KIND for item in run.result.evidence_refs
    )
    assert "private disk detail" not in run.receipt.model_dump_json()
    assert run.result.evidence_link is not None
    events = evidence.tail(run.result.evidence_link.evidence_id, 0, 256)
    assert events[-1].event_type == AttemptEvidenceEventType.ATTEMPT_FAILED
    assert adapter.calls == 1
    assert not tuple((tmp_path / "private-runtime" / "worker-workspaces").iterdir())


def test_post_effect_fence_loss_is_sanitized_as_outcome_unknown(
    tmp_path: Path,
) -> None:
    repository, base_sha = _repository(tmp_path / "user-checkout")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    model = DeterministicWorkerModel(model="fixture-worker")
    model.bind(
        (FileMutation(operation="update", path="a.txt", text="possibly-written\n"),)
    )
    adapter = GeminiWorkerAdapter.fake(worker_id="worker-a", model=model)
    dispatch = _dispatch(
        task_id="work-a",
        worker_id="worker-a",
        workspace_id="workspace-a",
        attempt_id="attempt-a",
        lease_id="lease-a",
        fence=11,
        writes=("a.txt",),
    )
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
    write_operation = stable_operation_id(dispatch, "mutation:0:update")
    calls: Counter[str] = Counter()

    async def fence(_: Dispatch, operation_id: str) -> None:
        calls[operation_id] += 1
        if operation_id == write_operation and calls[operation_id] == 2:
            raise RuntimeError("private fence detail must not escape")

    async def check(*_):
        raise AssertionError("check must not run after fence loss")

    runtime = WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=WorkerRegistry((adapter,)),
        assignment=lambda _: assignment,
        accepted_artifact=lambda *_: b"",
        check_runner=check,
        policy_sha256="a" * 64,
        fence=fence,
        heartbeat=lambda _: None,
        clock=lambda: NOW,
    )

    run = asyncio.run(runtime.execute_async(dispatch))

    assert run.result.succeeded is False
    assert run.result.retryable is False
    assert run.result.result_code == "outcome_unknown"
    assert run.receipt.completion.outcome == CompletionOutcome.OUTCOME_UNKNOWN
    assert "private fence detail" not in run.receipt.model_dump_json()
    assert not tuple((runtime_root / "worker-workspaces").iterdir())


@pytest.mark.parametrize(
    "child", ("worker-workspaces", "worker-receipts", "operation-journal")
)
def test_runtime_rejects_private_child_symlinks_without_touching_target(
    tmp_path: Path, child: str
) -> None:
    repository, base_sha = _repository(tmp_path / "user-checkout")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o751)
    sentinel = outside / "sentinel"
    sentinel.write_text("unchanged\n")
    before_mode = stat.S_IMODE(outside.stat().st_mode)
    (runtime_root / child).symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeFailure) as rejected:
        WorkerRuntime(
            repository=repository,
            base_sha=base_sha,
            runtime=runtime_root,
            evidence=SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite"),
            registry=WorkerRegistry(),
            assignment=lambda _: None,  # type: ignore[return-value]
            accepted_artifact=lambda *_: b"",
            check_runner=lambda *_: None,  # type: ignore[arg-type]
            policy_sha256="a" * 64,
            fence=lambda *_: None,
            heartbeat=lambda _: None,
        )

    assert rejected.value.code == RuntimeErrorCode.RUNTIME_UNAVAILABLE
    assert stat.S_IMODE(outside.stat().st_mode) == before_mode
    assert sentinel.read_text() == "unchanged\n"
    assert tuple(outside.iterdir()) == (sentinel,)


def test_workspace_identity_substitution_before_write_is_not_published(
    tmp_path: Path,
) -> None:
    repository, base_sha = _repository(tmp_path / "user-checkout")
    runtime_root = tmp_path / "private-runtime"
    runtime_root.mkdir(mode=0o700)
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    model = DeterministicWorkerModel(model="fixture-worker")
    model.bind(
        (FileMutation(operation="update", path="a.txt", text="must-not-be-applied\n"),)
    )
    dispatch = _dispatch(
        task_id="work-a",
        worker_id="worker-a",
        workspace_id="workspace-a",
        attempt_id="attempt-a",
        lease_id="lease-a",
        fence=11,
        writes=("a.txt",),
    )
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
    runtime: WorkerRuntime
    substituted = False

    async def fence(_: Dispatch, operation_id: str) -> None:
        nonlocal substituted
        if (
            operation_id == stable_operation_id(dispatch, "mutation:0:update")
            and not substituted
        ):
            workspace = runtime._workspace(dispatch)
            displaced = tmp_path / "displaced-workspace"
            workspace.rename(displaced)
            shutil.copytree(displaced, workspace)
            substituted = True

    runtime = WorkerRuntime(
        repository=repository,
        base_sha=base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=WorkerRegistry(
            (GeminiWorkerAdapter.fake(worker_id="worker-a", model=model),)
        ),
        assignment=lambda _: assignment,
        accepted_artifact=lambda *_: b"",
        check_runner=lambda *_: (_ for _ in ()).throw(
            AssertionError("check must not run after identity substitution")
        ),
        policy_sha256="a" * 64,
        fence=fence,
        heartbeat=lambda _: None,
        clock=lambda: NOW,
    )

    run = asyncio.run(runtime.execute_async(dispatch))

    assert substituted
    assert run.result.succeeded is False
    assert run.result.publications == ()
    assert run.result.result_code == RuntimeErrorCode.OUTCOME_UNKNOWN
    assert "must-not-be-applied" not in run.receipt.model_dump_json()
    assert (runtime._workspace(dispatch) / "a.txt").read_text() == "a-before\n"
    assert (tmp_path / "displaced-workspace" / "a.txt").read_text() == "a-before\n"


def test_live_worker_can_be_constructed_with_preflighted_credentials() -> None:
    adapter = GeminiWorkerAdapter.live(
        worker_id="gemini-worker", environ={"GOOGLE_API_KEY": "not-recorded"}
    )

    assert adapter.capabilities.driver == "gemini_live"
    assert adapter.capabilities.model_id == "gemini-3.5-flash"
