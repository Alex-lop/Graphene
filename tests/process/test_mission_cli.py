from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.evidence import (
    AttemptEvidenceEventType,
    SQLiteAttemptEvidenceStore,
)
from graphene.orchestration.local_result import LocalResultError, approve_result
from graphene.orchestration.models import (
    AttemptState,
    MissionEventType,
    MissionStatus,
    TaskState,
)
from graphene.orchestration.projection import MissionProjection
from graphene.orchestration.process_control import (
    ControlledProcessRunner,
    OwnedProcessRegistry,
    ProcessCancelled,
    ProcessControlError,
)
from graphene.orchestration.scheduler import MissionScheduler, SystemClock
from graphene.orchestration.scripted import (
    _persisted_scenario,
    load_scenario,
    initialize_fixture_repository,
    propose_scripted_mission,
    scripted_result_artifacts,
    scripted_supported,
)
from graphene.orchestration.store import SQLiteMissionStore


ROOT = Path(__file__).resolve().parents[2]


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        (
            "git",
            "-c",
            "user.name=Graphene Process Fixture",
            "-c",
            "user.email=fixture@graphene.invalid",
            *arguments,
        ),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        check=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "user-repository"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    (repository / "README.md").write_text("# User fixture\n", encoding="utf-8")
    _git(repository, "add", "--all", "--")
    _git(repository, "commit", "-q", "-m", "base")
    return repository, _git(repository, "rev-parse", "HEAD")


def _cli(environment: dict[str, str], *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        (sys.executable, "-m", "graphene.cli.main", "--json", *arguments),
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _start(
    environment: dict[str, str],
    repository: Path,
    *,
    auto_approve: bool = False,
    command_id: str | None = None,
) -> dict[str, object]:
    arguments = [
        "mission",
        "start",
        "--repo",
        str(repository),
        "--goal",
        load_scenario().goal,
        "--driver",
        "scripted-local",
    ]
    if auto_approve:
        arguments.append("--auto-approve")
    if command_id is not None:
        arguments.extend(("--command-id", command_id))
    return _cli(environment, *arguments)


def test_fixture_base_identity_ignores_only_known_python_caches(tmp_path: Path) -> None:
    baseline_scenario = load_scenario()
    _, baseline_sha = initialize_fixture_repository(
        baseline_scenario, tmp_path / "baseline-runtime"
    )
    copied = tmp_path / "taskmaster"
    shutil.copytree(ROOT / "demo/taskmaster", copied)
    bytecode = copied / "repository/status_report/__pycache__/model.pyc"
    bytecode.parent.mkdir(exist_ok=True)
    bytecode.write_bytes(b"generated-bytecode")
    pytest_cache = copied / "repository/.pytest_cache/state"
    pytest_cache.parent.mkdir(exist_ok=True)
    pytest_cache.write_text("generated cache", encoding="utf-8")

    cached_scenario = load_scenario(copied / "scenario.json")
    cached_repository, cached_sha = initialize_fixture_repository(
        cached_scenario, tmp_path / "cached-runtime"
    )

    assert cached_sha == baseline_sha
    assert "__pycache__" not in _git(cached_repository, "ls-files")
    assert ".pytest_cache" not in _git(cached_repository, "ls-files")


def test_scripted_initialization_recovers_exact_interrupted_staging(
    tmp_path: Path,
) -> None:
    scenario = load_scenario()
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    fixture_staging = runtime / ".fixture.graphene-staging"
    fixture_staging.mkdir(mode=0o700)
    (fixture_staging / "partial").write_bytes(b"interrupted")

    persisted = _persisted_scenario(runtime, scenario)
    assert persisted.scenario_id == scenario.scenario_id
    assert not fixture_staging.exists()
    assert _persisted_scenario(runtime).scenario_id == scenario.scenario_id

    repository_staging = runtime / ".repository.graphene-staging"
    repository_staging.mkdir(mode=0o700)
    (repository_staging / "partial").write_bytes(b"interrupted")
    repository, base_sha = initialize_fixture_repository(persisted, runtime)
    assert len(base_sha) == 40
    assert not repository_staging.exists()
    assert initialize_fixture_repository(persisted, runtime) == (repository, base_sha)


@pytest.mark.skipif(
    not scripted_supported(),
    reason="active process control requires the proven macOS scripted runtime",
)
def test_cli_pauses_resumes_and_cancels_only_bound_active_process(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    environment = {
        **os.environ,
        "GRAPHENE_STATE_DIR": str(state),
        "PYTHONPATH": str(ROOT / "backend"),
    }
    mission_id = "mission-active-control"
    runtime = state / "scripted" / sha256_hex(mission_id.encode())[:32]
    store = SQLiteMissionStore(state / "missions.sqlite3")
    propose_scripted_mission(
        scenario=load_scenario(),
        store=store,
        runtime=runtime,
        mission_id=mission_id,
    )
    store.approve_plan(
        mission_id,
        "command_approve_active_control",
        expected_revision=1,
        operator_label="process-fixture",
        rationale="Approve the bounded active-control fixture.",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=datetime.now(UTC),
    )
    scheduler = MissionScheduler(store, clock=SystemClock())
    dispatch = scheduler.tick(mission_id, ("scripted-worker-1",))[0]
    registry = OwnedProcessRegistry(runtime)
    errors: list[Exception] = []
    runner = ControlledProcessRunner(
        registry,
        dispatch,
        lambda: store.snapshot(mission_id).mission.status,
        heartbeat=lambda: scheduler.heartbeat(dispatch),
    )

    def execute() -> None:
        try:
            runner(
                ("/bin/sleep", "10"),
                cwd=Path("/"),
                env={"PATH": os.defpath},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=execute)
    thread.start()
    deadline = time.monotonic() + 2
    while True:
        try:
            owned = registry.prepare_cancel((dispatch,))[0]
            break
        except ProcessControlError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)

    paused = _cli(
        environment,
        "mission",
        "pause",
        mission_id,
        "--command-id",
        "command_pause_active_control",
    )
    process_state = subprocess.run(
        ("/bin/ps", "-o", "state=", "-p", str(owned.pid)),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert paused["mission_id"] == mission_id and process_state.startswith("T")
    assert store.snapshot(mission_id).mission.status == MissionStatus.PAUSED

    resumed = _cli(
        environment,
        "mission",
        "resume",
        mission_id,
        "--command-id",
        "command_resume_active_control",
    )
    assert resumed["mission_id"] == mission_id
    assert store.snapshot(mission_id).mission.status == MissionStatus.RUNNING
    cancelled = _cli(
        environment,
        "mission",
        "cancel",
        mission_id,
        "--confirm",
        mission_id,
        "--command-id",
        "command_cancel_active_control",
    )
    thread.join(timeout=3)

    assert cancelled == {"mission_id": mission_id, "status": "cancelled"}
    assert len(errors) == 1 and isinstance(errors[0], ProcessCancelled)
    assert store.snapshot(mission_id).mission.status == MissionStatus.CANCELLED
    assert not thread.is_alive() and not tuple(registry.directory.iterdir())


@pytest.mark.skipif(
    not scripted_supported(),
    reason="scripted-local fails closed without the macOS fixture sandbox",
)
def test_reviewed_mission_retries_fans_in_verifies_and_rejects_without_commit(
    tmp_path: Path,
) -> None:
    repository, user_head = _repository(tmp_path)
    state = tmp_path / "state"
    environment = {
        **os.environ,
        "GRAPHENE_STATE_DIR": str(state),
        "PYTHONPATH": str(ROOT / "backend"),
    }
    _cli(environment, "init", "--repo", str(repository))

    proposed = _start(
        environment,
        repository,
        command_id="command_start_review_process_001",
    )
    mission_id = str(proposed["mission_id"])
    assert proposed["status"] == "proposed"
    assert proposed["review_required"] is True
    assert proposed["validation"]["valid"] is True
    assert len(proposed["task_graph"]) == 6
    proposed_store = SQLiteMissionStore(state / "missions.sqlite3")
    assert proposed_store.snapshot(mission_id).mission.status == MissionStatus.PROPOSED
    assert proposed_store.snapshot(mission_id).attempts == ()
    proposed_head = proposed_store.head(mission_id)
    proposed_again = _start(
        environment,
        repository,
        command_id="command_start_review_process_001",
    )
    assert proposed_again["mission_id"] == mission_id
    assert proposed_again["result_replayed"] is True
    assert proposed_store.head(mission_id) == proposed_head

    approval = (
        "mission",
        "approve-plan",
        mission_id,
        "--revision",
        "1",
        "--operator-label",
        "process-fixture",
        "--rationale",
        "Approve the validated bounded fixture plan.",
        "--command-id",
        "command_approve_plan_process_001",
    )
    started = _cli(environment, *approval)
    head_after_execution = proposed_store.head(mission_id)
    attempts_after_execution = proposed_store.snapshot(mission_id).attempts
    started_again = _cli(environment, *approval)
    assert started_again["candidate_sha256"] == started["candidate_sha256"]
    assert started_again["result_replayed"] is True
    assert proposed_store.head(mission_id) == head_after_execution
    assert proposed_store.snapshot(mission_id).attempts == attempts_after_execution

    candidate_sha = str(started["candidate_sha256"])
    assert started["status"] == "awaiting_result"
    assert started["parallel_overlap_observed"] is True
    assert started["dispatch_batches"][0] == ["redact_notes", "render_json"]
    assert started["attempt_count"] == 7
    watched = _cli(
        environment,
        "mission",
        "watch",
        mission_id,
        "--after-seq",
        "1",
        "--snapshot",
    )
    assert watched["after_seq"] == 1
    assert watched["next_after_seq"] > 1
    assert watched["events"][0]["seq"] == 2
    assert watched["snapshot"]["mission"]["mission_id"] == mission_id

    store = SQLiteMissionStore(state / "missions.sqlite3")
    snapshot = store.snapshot(mission_id)
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert all(task.state == TaskState.DONE for task in snapshot.tasks)
    markdown = next(
        task for task in snapshot.tasks if task.task_id == "render_markdown"
    )
    assert markdown.attempt_count == 2
    markdown_attempts = sorted(
        (item for item in snapshot.attempts if item.task_id == markdown.task_id),
        key=lambda item: item.attempt_number,
    )
    assert [item.state for item in markdown_attempts] == [
        AttemptState.FAILED,
        AttemptState.COMMITTED,
    ]
    assert markdown_attempts[0].workspace_id != markdown_attempts[1].workspace_id
    assert not any(
        item.attempt_id == markdown_attempts[0].attempt_id
        for item in snapshot.publications
    )

    evidence = SQLiteAttemptEvidenceStore(
        state
        / "scripted"
        / sha256_hex(mission_id.encode())[:32]
        / "attempt-evidence.sqlite3"
    )
    assembly = next(
        item for item in snapshot.attempts if item.task_id == "assemble_candidate"
    )
    verification_attempt = next(
        item for item in snapshot.attempts if item.task_id == "verify_candidate"
    )
    assert {
        "changed-path-hunk-manifest",
        "command-template-receipt",
        "inherited-context-manifest",
        "patch",
        "resource-receipt",
        "test-receipt",
    } <= {item.kind for item in assembly.evidence_refs}
    command_receipt = next(
        item
        for item in assembly.evidence_refs
        if item.kind == "command-template-receipt"
    )
    command_value = json.loads(
        evidence.resolve(command_receipt.kind, command_receipt.id)
    )
    assert set(command_value) == {"template_id", "template_sha256"}
    assert command_value["template_id"] == "fixture-tests"
    manifest = next(
        item
        for item in assembly.evidence_refs
        if item.kind == "changed-path-hunk-manifest"
    )
    manifest_value = json.loads(evidence.resolve(manifest.kind, manifest.id))
    assert manifest_value["changed_paths"] == sorted(
        item["path"] for item in manifest_value["entries"]
    )
    assert all(item["hunk_count"] >= 1 for item in manifest_value["entries"])
    context = next(
        item
        for item in verification_attempt.evidence_refs
        if item.kind == "inherited-context-manifest"
    )
    context_value = json.loads(evidence.resolve(context.kind, context.id))
    assert context_value["opened_sha256"] == [candidate_sha]
    assert context_value["accepted"][0]["sha256"] == candidate_sha
    assert context_value["excluded_sha256"]
    assembly_publication = next(
        item for item in snapshot.publications if item.task_id == "assemble_candidate"
    )
    assert assembly_publication.paths == (
        "status_report/cli.py",
        "status_report/redact.py",
        "status_report/render_json.py",
        "status_report/render_markdown.py",
        "tests/test_cli.py",
        "tests/test_redact.py",
        "tests/test_render_json.py",
        "tests/test_render_markdown.py",
    )
    assembly_detail = MissionProjection(store).task_detail(
        mission_id, "assemble_candidate"
    )
    assert assembly_detail.command_receipts
    assert assembly_detail.changed_hunks
    assert any(
        "paths:status_report/cli.py" in item for item in assembly_detail.publications
    )
    failed_events = evidence.tail(
        markdown_attempts[0].evidence_link.evidence_id,
        after_seq=0,
        limit=16,
    )
    assert AttemptEvidenceEventType.OPERATION_STARTED in {
        item.event_type for item in failed_events
    }
    assert AttemptEvidenceEventType.OPERATION_FAILED in {
        item.event_type for item in failed_events
    }

    events = store.tail(mission_id, after_seq=0, limit=256)
    plan_approved = next(
        event for event in events if event.event_type == MissionEventType.PLAN_APPROVED
    )
    assert plan_approved.truth_kind == "server_derived"
    accepted_seq = {
        str(event.payload.get("task_id")): event.seq
        for event in events
        if event.event_type == MissionEventType.ARTIFACT_ACCEPTED
    }
    started_seq = {
        str(event.payload.get("task_id")): event.seq
        for event in events
        if event.event_type == MissionEventType.TASK_STARTED
    }
    assert plan_approved.seq < min(started_seq.values())
    assert started_seq["wire_cli"] > max(
        accepted_seq[task]
        for task in ("redact_notes", "render_json", "render_markdown")
    )
    assert started_seq["assemble_candidate"] > accepted_seq["wire_cli"]
    assert started_seq["verify_candidate"] > accepted_seq["assemble_candidate"]

    rejected = _cli(
        environment,
        "mission",
        "reject-result",
        mission_id,
        "--candidate-sha",
        candidate_sha,
        "--operator-label",
        "process-fixture",
        "--rationale",
        "Exercise the normal no-commit outcome.",
    )
    assert rejected["status"] == "rejected"
    assert rejected["local_commit_sha"] is None
    assert store.snapshot(mission_id).mission.status == MissionStatus.REJECTED
    runtime = state / "scripted" / sha256_hex(mission_id.encode())[:32]
    result_ref = "refs/graphene/results/" + sha256_hex(mission_id.encode())[:24]
    result = subprocess.run(
        ("git", "rev-parse", "--verify", result_ref),
        cwd=runtime / "repository",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode != 0
    assert _git(repository, "rev-parse", "HEAD") == user_head


@pytest.mark.skipif(
    not scripted_supported(),
    reason="scripted-local fails closed without the macOS fixture sandbox",
)
def test_approved_result_is_one_exact_anchored_isolated_commit(tmp_path: Path) -> None:
    repository, user_head = _repository(tmp_path)
    state = tmp_path / "state"
    environment = {
        **os.environ,
        "GRAPHENE_STATE_DIR": str(state),
        "PYTHONPATH": str(ROOT / "backend"),
    }
    _cli(environment, "init", "--repo", str(repository))
    started = _start(
        environment,
        repository,
        auto_approve=True,
        command_id="command_start_auto_process_001",
    )
    assert started["approval_truth"] == "simulated_fixture_no_human_review"
    mission_id = str(started["mission_id"])
    store_after_start = SQLiteMissionStore(state / "missions.sqlite3")
    head_after_start = store_after_start.head(mission_id)
    attempts_after_start = store_after_start.snapshot(mission_id).attempts
    started_again = _start(
        environment,
        repository,
        auto_approve=True,
        command_id="command_start_auto_process_001",
    )
    assert started_again["mission_id"] == mission_id
    assert started_again["candidate_sha256"] == started["candidate_sha256"]
    assert started_again["result_replayed"] is True
    assert store_after_start.head(mission_id) == head_after_start
    assert store_after_start.snapshot(mission_id).attempts == attempts_after_start
    runtime = state / "scripted" / sha256_hex(mission_id.encode())[:32]
    internal = runtime / "repository"
    partial_workspace = runtime / "results" / sha256_hex(mission_id.encode())[:24]
    partial_workspace.parent.mkdir(mode=0o700)
    _git(
        internal,
        "worktree",
        "add",
        "-q",
        "--detach",
        str(partial_workspace),
        _git(internal, "rev-parse", "HEAD"),
    )
    (partial_workspace / "status_report/cli.py").write_text(
        "# interrupted uncommitted apply\n", encoding="utf-8"
    )

    approval = (
        "mission",
        "approve-result",
        mission_id,
        "--candidate-sha",
        str(started["candidate_sha256"]),
        "--operator-label",
        "process-fixture",
        "--rationale",
        "Approve the exact verified fixture candidate.",
        "--command-id",
        "command_approve_result_process_001",
    )
    approved = _cli(environment, *approval)
    approved_again = _cli(environment, *approval)
    assert approved_again == approved

    commit_sha = str(approved["local_commit_sha"])
    result_ref = str(approved["result_ref"])
    store = SQLiteMissionStore(state / "missions.sqlite3")
    snapshot = store.snapshot(mission_id)

    evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    candidate, verification = scripted_result_artifacts(store, evidence, mission_id)
    runtime_link = tmp_path / "runtime-link"
    runtime_link.symlink_to(runtime, target_is_directory=True)
    with pytest.raises(LocalResultError, match="Graphene-owned repository"):
        approve_result(
            runtime=runtime_link,
            repository=runtime_link / "repository",
            mission_id=mission_id,
            base_sha=snapshot.mission.base_sha,
            candidate=candidate,
            approved_candidate_sha256=candidate.sha256,
            verification=verification,
            evidence=evidence,
            operator_label="process-fixture",
            rationale="Reject a symlinked runtime.",
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            allow_simulated_fixture=True,
        )
    sibling_receipt = evidence.put_artifact(
        "test-receipt",
        canonical_json_bytes(
            {
                "accepted_input_sha256": ["0" * 64],
                "candidate_patch_sha256": "0" * 64,
                "duration_bucket": "under_1s",
                "exit_code": 0,
                "output_sha256": "0" * 64,
                "output_truncated": False,
                "template_id": "fixture-tests",
                "timed_out": False,
            }
        ),
    )
    with pytest.raises(LocalResultError, match="did not pass the bound check"):
        approve_result(
            runtime=runtime,
            repository=internal,
            mission_id=mission_id,
            base_sha=snapshot.mission.base_sha,
            candidate=candidate,
            approved_candidate_sha256=candidate.sha256,
            verification=sibling_receipt,
            evidence=evidence,
            operator_label="process-fixture",
            rationale="Reject a sibling verification receipt.",
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            allow_simulated_fixture=True,
        )

    assert approved["status"] == "completed"
    assert (
        approved["pushed"]
        is approved["pull_request_created"]
        is approved["deployed"]
        is False
    )
    assert snapshot.mission.status == MissionStatus.COMPLETED
    assert _git(internal, "rev-parse", result_ref) == commit_sha
    assert _git(internal, "rev-parse", f"{commit_sha}^") == snapshot.mission.base_sha
    assert _git(internal, "rev-parse", "HEAD") == snapshot.mission.base_sha
    assert _git(repository, "rev-parse", "HEAD") == user_head
    final = next(
        event
        for event in reversed(store.tail(mission_id, after_seq=0, limit=256))
        if event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
    )
    assert final.truth_kind == "server_derived"
    assert final.payload["candidate_sha256"] == started["candidate_sha256"]
    assert final.payload["verification_sha256"] == started["verification_sha256"]


def test_replay_cli_does_not_print_its_generated_read_token(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "GRAPHENE_STATE_DIR": str(tmp_path / "state"),
        "PYTHONPATH": str(ROOT / "backend"),
    }
    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "graphene.cli.main",
            "mission",
            "replay",
            "taskmaster",
            "--no-open",
            "--exit-after-replay",
        ),
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "token=" not in result.stdout
    assert "#" not in result.stdout
    assert "token=" not in result.stderr
