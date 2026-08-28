"""Process-boundary tests for durable supervisor acceptance and ownership."""

from __future__ import annotations

import io
import os
import json
import signal
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import graphene.orchestration.process_control as process_control
import graphene.orchestration.planner_child as planner_child_module
import graphene.orchestration.supervisor as supervisor_module
from graphene.cli import mission as mission_cli
from graphene.cli.mission import _mission_runtime, _store_for_mission, initialize
from graphene.core_models import TruthKind
from graphene.hashing import canonical_json_bytes
from graphene.hashing import canonical_json_sha256
from graphene.orchestration.adk_planner import (
    LIVE_GEMINI_MODEL,
    PlanningRequest,
    PlanProposal,
    PlanProposalReceipt,
    ProviderUsage,
)
from graphene.orchestration.mission_models import MissionEventType, MissionStatus
from graphene.orchestration.mission_models import Plan
from graphene.orchestration.planner_child import (
    PlannerAttemptOutcome,
    PlannerChildFrame,
    PlannerChildRequest,
    PlannerChildProcess,
    PlannerGo,
    planner_frame_bytes,
    read_planner_frames,
)
from graphene.orchestration.scripted import load_scenario, scripted_supported
from graphene.orchestration.supervisor import (
    _RUNTIME_ENVIRONMENT_KEYS,
    SupervisorError,
    SupervisorProcess,
    SupervisorRequest,
    _live,
    _runtime_environment,
    _state,
    _write,
    accept_goal,
    ensure_supervisor,
    recover_supervisors,
    supervisor_status,
)


def test_supervisor_environment_is_an_exact_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", "/tmp/graphene-test-state")
    monkeypatch.setenv("GOOGLE_API_KEY", "required-model-credential")
    monkeypatch.setenv("GRAPHENE_GITHUB_TOKEN", "must-not-cross-boundary")
    monkeypatch.setenv("GRAPHENE_ARBITRARY_SECRET", "must-not-cross-boundary")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-cross-boundary")

    environment = _runtime_environment()

    assert environment["GRAPHENE_STATE_DIR"] == "/tmp/graphene-test-state"
    assert environment["GOOGLE_API_KEY"] == "required-model-credential"
    assert set(environment) <= _RUNTIME_ENVIRONMENT_KEYS | {"GIT_TERMINAL_PROMPT"}
    assert "GRAPHENE_GITHUB_TOKEN" not in environment
    assert "GRAPHENE_ARBITRARY_SECRET" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment


def test_planner_journal_fsyncs_its_file_and_parent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "planner"
    directory.mkdir(mode=0o700)
    synced: list[str] = []
    real_fsync = os.fsync

    def observed_fsync(descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        synced.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(descriptor)

    monkeypatch.setattr(planner_child_module.os, "fsync", observed_fsync)
    planner_child_module._append_frame(
        directory / "planner.frames",
        PlannerChildFrame(
            type="error",
            mission_id="mission-planner-fsync",
            supervisor_request_sha256="a" * 64,
            child_request_sha256="b" * 64,
            attempt_number=1,
            error_code="injected-error",
        ),
    )

    assert synced == ["file", "directory"]


def _repository(path: Path) -> Path:
    path.mkdir()
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "README.md").write_text("# Target\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(path), "add", "README.md"], check=True, env=environment
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "fixture"],
        check=True,
        env=environment,
    )
    return path


def _stop_owned_supervisors(state: Path) -> None:
    for path in (state / "missions").glob("*/supervisor-process.json"):
        try:
            record = SupervisorProcess.model_validate_json(path.read_bytes())
        except (OSError, ValueError):
            continue
        if not _live(record):
            continue
        os.killpg(record.pgid, signal.SIGTERM)
        deadline = time.monotonic() + 2
        while _live(record) and time.monotonic() < deadline:
            time.sleep(0.01)
        if _live(record):
            os.killpg(record.pgid, signal.SIGKILL)


@pytest.fixture
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    repository = _repository(tmp_path / "target")
    initialize(repository)
    try:
        yield state, repository
    finally:
        _stop_owned_supervisors(state)


def _accept(
    repository: Path,
    command_id: str = "request-supervisor-0001",
    *,
    requested_mode: str = "review_required",
    finalization_mode: str = "review_required",
):
    scenario = load_scenario()
    return accept_goal(
        repository=repository,
        goal=scenario.goal,
        success_criteria=scenario.success_criteria,
        driver="scripted-local",
        max_workers=2,
        command_id=command_id,
        requested_mode=requested_mode,
        finalization_mode=finalization_mode,
    )


def _wait_for_phase(mission_id: str, phases: set[str], timeout: float = 30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = supervisor_status(mission_id)
        if state.phase in phases:
            return state
        time.sleep(0.02)
    runtime = _mission_runtime(mission_id)
    process_path = runtime / "supervisor-process.json"
    try:
        process = SupervisorProcess.model_validate_json(process_path.read_bytes())
        process_status = f"generation={process.generation}, live={_live(process)}"
    except (OSError, ValueError) as error:
        process_status = f"unavailable ({type(error).__name__})"
    pytest.fail(
        f"supervisor for {mission_id} did not reach {sorted(phases)}; "
        f"state={state.model_dump(mode='json')}; "
        f"mission_status={supervisor_module._authoritative_mission_status(mission_id)}; "
        f"process={process_status}"
    )


def test_acceptance_is_under_five_seconds_and_duplicate_calls_share_one_owner(
    isolated_runtime,
) -> None:
    _state, repository = isolated_runtime

    started_at = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_accept, repository) for _ in range(2)]
        accepted = [future.result(timeout=5) for future in futures]
    assert time.monotonic() - started_at < 5

    requests = [item[0] for item in accepted]
    states = [item[1] for item in accepted]
    assert requests[0] == requests[1]
    assert {state.generation for state in states} == {1}
    runtime = _mission_runtime(requests[0].mission_id)
    process = SupervisorProcess.model_validate_json(
        (runtime / "supervisor-process.json").read_bytes()
    )
    assert process.mission_id == requests[0].mission_id
    assert process.request_sha256 == requests[0].request_sha256
    assert process.generation == 1
    assert process.pid == process.pgid
    assert requests[0].schema_version == 2
    assert requests[0].check_executor in {"docker", "host-sandbox"}
    assert (runtime / "supervisor-request.json").stat().st_mode & 0o077 == 0
    assert (runtime / "supervisor-state.json").stat().st_mode & 0o077 == 0


def test_spawn_releases_child_only_after_durable_process_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    request = SimpleNamespace(
        mission_id="mission-supervisor-handshake",
        request_sha256="a" * 64,
    )
    process_recorded = False

    class ParentPipe:
        closed = False

        def close(self) -> None:
            assert process_recorded
            self.closed = True

    pipe = ParentPipe()

    class ChildProcess:
        pid = 424242
        stdin = pipe

        @staticmethod
        def poll() -> None:
            return None

    def spawn_process(*_args, **kwargs):
        assert kwargs["stdin"] == subprocess.PIPE
        return ChildProcess()

    def write_record(path: Path, _value, **_kwargs) -> None:
        nonlocal process_recorded
        assert path == runtime / "supervisor-process.json"
        process_recorded = True

    monkeypatch.setattr(supervisor_module, "_state", lambda *_args: None)
    monkeypatch.setattr(supervisor_module.subprocess, "Popen", spawn_process)
    monkeypatch.setattr(supervisor_module, "_write", write_record)
    monkeypatch.setattr(
        process_control,
        "_owned_process_identity",
        lambda _pid: (424242, "started", "S", "(python3.13)", "birth-token"),
    )

    record = supervisor_module._spawn(runtime, request, 1)

    assert record.pid == 424242
    assert record.executable == os.path.abspath(sys.executable)
    assert process_recorded is True
    assert pipe.closed is True


def test_supervisor_stays_live_after_framework_launcher_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    framework = tmp_path / "Python.framework/Versions/3.13"
    launcher = str(framework / "bin/python3.13")
    app_binary = str(framework / "Resources/Python.app/Contents/MacOS/Python")
    record = SupervisorProcess(
        mission_id="mission-framework-exec",
        request_sha256="a" * 64,
        generation=1,
        pid=424242,
        pgid=424242,
        started_at="started",
        birth_token="birth-token",
        executable=launcher,
    )
    monkeypatch.setattr(
        process_control,
        "_owned_process_identity",
        lambda _pid: (424242, "started", "S", app_binary, "birth-token"),
    )

    assert _live(record)


def test_supervisor_waits_for_parent_eof_before_reading_process_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = "mission-supervisor-delayed-record"
    request_sha256 = "b" * 64
    request = SimpleNamespace(
        mission_id=mission_id,
        request_sha256=request_sha256,
    )
    record = SupervisorProcess(
        mission_id=mission_id,
        request_sha256=request_sha256,
        generation=1,
        pid=os.getpid(),
        pgid=os.getpid(),
        started_at="started",
        birth_token="birth-token",
        executable=sys.executable,
    )
    events: list[str] = []

    class ParentHandshake:
        buffer: ParentHandshake

        def __init__(self) -> None:
            self.buffer = self

        def read(self, size: int) -> bytes:
            assert size == 1
            events.append("parent-eof")
            return b""

    def read_process(_path: Path, _request) -> SupervisorProcess:
        assert events == ["parent-eof"]
        events.append("process-record")
        return record

    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda _mission_id: tmp_path)
    monkeypatch.setattr(supervisor_module, "_read", lambda *_args: request)
    monkeypatch.setattr(supervisor_module, "_read_process", read_process)
    monkeypatch.setattr(supervisor_module, "_live", lambda _process: True)
    monkeypatch.setattr(supervisor_module, "_run", lambda *_args: events.append("run"))
    monkeypatch.setattr(sys, "stdin", ParentHandshake())

    assert supervisor_module.run_supervisor(mission_id, request_sha256, 1) == 0
    assert events == ["parent-eof", "process-record", "run"]


def test_supervisor_parent_eof_without_process_record_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = "mission-supervisor-parent-death"
    request_sha256 = "c" * 64
    request = SimpleNamespace(
        mission_id=mission_id,
        request_sha256=request_sha256,
    )

    def missing_record(_path: Path, _request):
        raise SupervisorError("supervisor process record is missing")

    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda _mission_id: tmp_path)
    monkeypatch.setattr(supervisor_module, "_read", lambda *_args: request)
    monkeypatch.setattr(supervisor_module, "_read_process", missing_record)
    monkeypatch.setattr(
        supervisor_module,
        "_run",
        lambda *_args: pytest.fail("ran without a durable process record"),
    )
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO()))

    assert supervisor_module.run_supervisor(mission_id, request_sha256, 1) == 2


def test_durable_check_executor_ignores_restart_environment_flip(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_root, repository = isolated_runtime
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "docker")
    request, _accepted = _accept(repository, "request-supervisor-check-executor")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    binding = json.loads((runtime / "start-request.json").read_bytes())
    assert request.check_executor == binding["check_executor"] == "docker"

    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "semantic-switch-canary")
    assert mission_cli._mission_check_executor(request.mission_id) == "docker"
    duplicate, _state_value = _accept(repository, "request-supervisor-check-executor")
    assert duplicate == request


def test_legacy_request_falls_back_to_current_check_executor(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-legacy-executor")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    request_path = runtime / "supervisor-request.json"
    payload = request.model_dump(mode="json")
    payload["schema_version"] = 1
    payload.pop("check_executor")
    payload["request_sha256"] = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "request_sha256"}
    )
    request_path.write_bytes(canonical_json_bytes(payload) + b"\n")
    binding_path = runtime / "start-request.json"
    binding = json.loads(binding_path.read_bytes())
    binding.pop("check_executor")
    binding_path.write_bytes(canonical_json_bytes(binding) + b"\n")

    legacy = supervisor_module._read(request_path, SupervisorRequest)
    assert legacy.schema_version == 1 and legacy.check_executor is None
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "docker")
    assert mission_cli._mission_check_executor(request.mission_id) == "docker"


def test_dead_exact_owner_record_is_replaced_with_a_higher_generation(
    isolated_runtime,
) -> None:
    _state, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-0002")
    runtime = _mission_runtime(request.mission_id)
    original = SupervisorProcess.model_validate_json(
        (runtime / "supervisor-process.json").read_bytes()
    )

    settled = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert settled.phase == "review_required", settled
    deadline = time.monotonic() + 5
    while _live(original) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _live(original)

    restarted = ensure_supervisor(request.mission_id)
    replacement = SupervisorProcess.model_validate_json(
        (runtime / "supervisor-process.json").read_bytes()
    )
    assert restarted.generation == original.generation + 1
    assert replacement.generation == original.generation + 1
    assert (replacement.pid, replacement.started_at) != (
        original.pid,
        original.started_at,
    )
    assert _live(replacement)
    assert (
        _wait_for_phase(request.mission_id, {"review_required", "failed"}).phase
        == "review_required"
    )


def test_legacy_weak_process_record_is_migrated_without_being_trusted(
    isolated_runtime,
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-legacy-process")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    process_path = runtime / "supervisor-process.json"
    original = SupervisorProcess.model_validate_json(process_path.read_bytes())
    deadline = time.monotonic() + 5
    while _live(original) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _live(original)
    _state(runtime, request, "accepted", reviewed.generation)
    legacy = original.model_dump(mode="json")
    legacy["schema_version"] = 1
    legacy.pop("birth_token")
    process_path.write_bytes(canonical_json_bytes(legacy) + b"\n")

    assert recover_supervisors() == 1
    replacement = SupervisorProcess.model_validate_json(process_path.read_bytes())
    assert replacement.schema_version == 2
    assert replacement.generation == reviewed.generation + 1
    assert replacement.birth_token


def test_live_legacy_process_defers_strong_replacement(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-live-legacy")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    process_path = runtime / "supervisor-process.json"
    _state(runtime, request, "accepted", reviewed.generation)
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    pgid, started_at, _state_name, executable, _birth_token = (
        process_control._owned_process_identity(sentinel.pid)
    )
    legacy = {
        "executable": executable,
        "generation": reviewed.generation,
        "mission_id": request.mission_id,
        "pgid": pgid,
        "pid": sentinel.pid,
        "request_sha256": request.request_sha256,
        "schema_version": 1,
        "started_at": started_at,
    }
    process_path.write_bytes(canonical_json_bytes(legacy) + b"\n")
    spawned: list[int] = []
    monkeypatch.setattr(
        supervisor_module,
        "_spawn",
        lambda _runtime, _request, generation: spawned.append(generation),
    )
    try:
        recover_supervisors()
        assert spawned == []
        assert process_path.read_bytes() == canonical_json_bytes(legacy) + b"\n"
    finally:
        sentinel.terminate()
        sentinel.wait(timeout=5)

    recover_supervisors()
    assert spawned == [reviewed.generation + 1]


def test_stale_generation_cannot_overwrite_newer_supervisor_state(
    isolated_runtime,
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-generation")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)

    current = _state(runtime, request, "accepted", reviewed.generation + 1)
    with pytest.raises(SupervisorError, match="stale supervisor generation"):
        _state(runtime, request, "failed", reviewed.generation, error_code="stale")

    assert supervisor_status(request.mission_id) == current


@pytest.mark.parametrize(
    "first_outcome",
    ["pre_dispatch_interrupted", "provider_outcome_unknown", "child_error"],
)
def test_planner_failure_gets_one_durable_bounded_replacement(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch, first_outcome: str
) -> None:
    _state_root, repository = isolated_runtime
    from graphene.cli.mission import _load_project_policy

    _root, head, policy = _load_project_policy(repository)
    scenario = load_scenario()
    suffix = first_outcome.replace("_", "-")
    mission_id = "mission-planner-child-" + suffix
    request = SupervisorRequest.create(
        mission_id=mission_id,
        command_id="request-planner-child-" + suffix,
        repository_path=str(repository),
        goal=scenario.goal,
        success_criteria=scenario.success_criteria,
        driver="gemini-adk",
        max_workers=2,
        base_sha=head,
        policy_revision=policy.revision,
        policy_sha256=canonical_json_sha256(policy.model_dump(mode="json")),
        requested_mode="review_required",
        finalization_mode="review_required",
        check_executor="docker",
        accepted_at=datetime.now(UTC),
    )
    plan = Plan(
        mission_id=mission_id,
        revision=1,
        criteria=scenario.criteria,
        tasks=scenario.tasks,
        max_concurrency=2,
    )
    invocation_id = "planner-invocation-2"
    proposal = PlanProposal(
        plan=plan,
        receipt=PlanProposalReceipt(
            driver="gemini_live",
            client_version="1.0",
            mission_id=mission_id,
            revision=1,
            plan_sha256=canonical_json_sha256(plan.model_dump(mode="json")),
            planning_input_sha256="a" * 64,
            planning_context_sha256="b" * 64,
            requested_model=LIVE_GEMINI_MODEL,
            returned_model=LIVE_GEMINI_MODEL,
            session_id="planner-session-2",
            invocation_id=invocation_id,
            credential_mode="gemini_api",
            input_bytes=1,
            output_bytes=1,
            provider_usage=ProviderUsage(source="unavailable"),
        ),
    )
    runtime = _mission_runtime(mission_id)
    runtime.mkdir(mode=0o700, parents=True)
    children: list[subprocess.Popen[bytes]] = []
    attempts: list[int] = []

    def append(directory: Path, frame: PlannerChildFrame) -> None:
        with (directory / "planner.frames").open("ab", buffering=0) as stream:
            stream.write(planner_frame_bytes(frame))
            os.fsync(stream.fileno())
        (directory / "planner.frames").chmod(0o600)

    def spawn(directory: Path, child_request) -> None:
        attempts.append(child_request.attempt_number)
        process = subprocess.Popen(
            (sys.executable, "-I", "-c", "import time; time.sleep(30)"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        children.append(process)
        time.sleep(0.05)
        pgid, started_at, state, executable, birth_token = (
            process_control._owned_process_identity(process.pid)
        )
        assert not state.startswith("Z")
        common = {
            "mission_id": child_request.mission_id,
            "supervisor_request_sha256": child_request.supervisor_request_sha256,
            "child_request_sha256": child_request.request_sha256(),
            "attempt_number": child_request.attempt_number,
        }
        append(
            directory,
            PlannerChildFrame(
                type="ready",
                process=PlannerChildProcess(
                    pid=process.pid,
                    pgid=pgid,
                    started_at=started_at,
                    birth_token=birth_token,
                    executable=executable,
                ),
                **common,
            ),
        )

        def finish() -> None:
            deadline = time.monotonic() + 5
            while not (directory / "planner-go.json").exists():
                assert time.monotonic() < deadline
                time.sleep(0.01)
            if child_request.attempt_number == 1:
                if first_outcome == "provider_outcome_unknown":
                    append(
                        directory,
                        PlannerChildFrame(
                            type="provider_dispatched",
                            sdk_invocation_id="planner-invocation-1",
                            dispatched_at="2026-08-27T12:00:00.000Z",
                            **common,
                        ),
                    )
                elif first_outcome == "child_error":
                    append(
                        directory,
                        PlannerChildFrame(
                            type="error",
                            error_code="plannerunavailable",
                            **common,
                        ),
                    )
            else:
                append(
                    directory,
                    PlannerChildFrame(
                        type="provider_dispatched",
                        sdk_invocation_id=invocation_id,
                        dispatched_at="2026-08-27T12:00:01.000Z",
                        **common,
                    ),
                )
                append(
                    directory,
                    PlannerChildFrame(
                        type="result",
                        sdk_invocation_id=invocation_id,
                        proposal=proposal,
                        **common,
                    ),
                )
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)

        threading.Thread(target=finish, daemon=True).start()

    monkeypatch.setattr(supervisor_module, "_spawn_planner_child", spawn)
    result = supervisor_module._supervised_gemini_proposal(
        request, policy, repository, runtime
    )
    assert result == proposal
    assert attempts == [1, 2]
    recorded = PlannerAttemptOutcome.model_validate_json(
        (runtime / "planner/attempt-1/planner-outcome.json").read_bytes()
    )
    assert recorded.outcome == first_outcome
    assert (
        supervisor_module._supervised_gemini_proposal(
            request, policy, repository, runtime
        )
        == proposal
    )
    assert attempts == [1, 2]

    for process in children:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)


def test_isolated_planner_child_reaches_provider_dispatch_and_result(
    isolated_runtime,
) -> None:
    state_root, repository = isolated_runtime
    from graphene.cli.mission import _load_project_policy

    _root, _head, policy = _load_project_policy(repository)
    scenario = load_scenario()
    mission_id = "mission-planner-process-regression"
    plan = Plan(
        mission_id=mission_id,
        revision=1,
        criteria=scenario.criteria,
        tasks=scenario.tasks,
        max_concurrency=2,
    )
    invocation_id = "planner-process-invocation"
    proposal = PlanProposal(
        plan=plan,
        receipt=PlanProposalReceipt(
            driver="gemini_live",
            client_version="1.0",
            mission_id=mission_id,
            revision=1,
            plan_sha256=canonical_json_sha256(plan.model_dump(mode="json")),
            planning_input_sha256="c" * 64,
            planning_context_sha256="d" * 64,
            requested_model=LIVE_GEMINI_MODEL,
            returned_model=LIVE_GEMINI_MODEL,
            session_id="planner-process-session",
            invocation_id=invocation_id,
            credential_mode="gemini_api",
            input_bytes=1,
            output_bytes=1,
            provider_usage=ProviderUsage(source="unavailable"),
        ),
    )
    child_request = PlannerChildRequest(
        mission_id=mission_id,
        supervisor_request_sha256="a" * 64,
        attempt_number=1,
        policy=policy,
        planning=PlanningRequest(
            mission_id=mission_id,
            revision=1,
            goal=scenario.goal,
            success_criteria=scenario.success_criteria,
            repository_manifest=("README.md",),
        ),
    )
    directory = state_root.parent / "isolated-planner-child"
    directory.mkdir(mode=0o700)
    go_path = directory / "planner-go.json"
    go_path.write_bytes(
        canonical_json_bytes(
            PlannerGo(
                child_request_sha256=child_request.request_sha256()
            ).model_dump(mode="json")
        )
        + b"\n"
    )
    go_path.chmod(0o600)

    harness = f"""
import graphene.orchestration.planner_child as planner_child
from graphene.orchestration.adk_planner import PlanProposal

proposal = PlanProposal.model_validate_json({proposal.model_dump_json()!r})

def fake_preflight(_environ, *, adc_probe):
    assert adc_probe is None
    return "gemini_api"

class FakePlanner:
    def __init__(self, *, dispatch_callback, **_values):
        self.dispatch_callback = dispatch_callback

    async def propose(self, _policy, _planning):
        self.dispatch_callback({invocation_id!r})
        return proposal

planner_child._credential_preflight = fake_preflight
planner_child.StampedGemini = lambda **_values: object()
planner_child.AdkPlanner = FakePlanner
raise SystemExit(planner_child.main())
"""
    process = subprocess.Popen(
        (sys.executable, "-I", "-c", harness),
        cwd=directory,
        env={"PYTHONUNBUFFERED": "1"},
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        _stdout, stderr = process.communicate(
            input=planner_frame_bytes(child_request), timeout=10
        )
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        pytest.fail("isolated planner child did not exit")

    assert process.returncode == 0, stderr.decode(errors="replace")
    frames = read_planner_frames(directory / "planner.frames")
    assert tuple(frame.type for frame in frames) == (
        "ready",
        "provider_dispatched",
        "result",
    )
    assert frames[1].sdk_invocation_id == invocation_id
    assert frames[2].proposal == proposal


def test_dead_planner_child_rereads_a_durable_terminal_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "planner-attempt"
    directory.mkdir(mode=0o700)
    proposal = object()
    child_request = SimpleNamespace(
        mission_id="mission-planner-terminal-race",
        supervisor_request_sha256="a" * 64,
        attempt_number=1,
        planning=SimpleNamespace(timeout_seconds=1),
        request_sha256=lambda: "b" * 64,
    )
    process = SimpleNamespace(pid=424242)
    ready = SimpleNamespace(type="ready", process=process, proposal=None)
    dispatch = SimpleNamespace(
        type="provider_dispatched",
        process=None,
        proposal=None,
        sdk_invocation_id="planner-invocation-race",
        dispatched_at="2026-08-27T12:00:00.000Z",
    )
    result = SimpleNamespace(type="result", process=None, proposal=proposal)
    reads = 0

    def frames(_directory: Path, _request) -> tuple[SimpleNamespace, ...]:
        nonlocal reads
        reads += 1
        if reads == 1:
            return ready, dispatch
        return ready, dispatch, result

    monkeypatch.setattr(supervisor_module, "_planner_frames", frames)
    monkeypatch.setattr(supervisor_module, "_planner_child_live", lambda _item: False)

    assert (
        supervisor_module._await_planner_attempt(directory, child_request) is proposal
    )
    assert reads == 3
    outcome = PlannerAttemptOutcome.model_validate_json(
        (directory / "planner-outcome.json").read_bytes()
    )
    assert outcome.outcome == "completed"


def test_transient_identity_failure_does_not_spawn_a_second_supervisor(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-transient")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    _state(runtime, request, "accepted", reviewed.generation)
    record = SupervisorProcess(
        mission_id=request.mission_id,
        request_sha256=request.request_sha256,
        generation=reviewed.generation,
        pid=os.getpid(),
        pgid=os.getpid(),
        started_at="transient-test",
        birth_token="transient-test-birth",
        executable=sys.executable,
    )
    _write(runtime / "supervisor-process.json", record)

    def unavailable(_pid: int):
        raise process_control.ProcessControlError(
            "owned process identity is unavailable"
        )

    monkeypatch.setattr(process_control, "_process_identity", unavailable)
    monkeypatch.setattr(
        supervisor_module,
        "_spawn",
        lambda *_args, **_kwargs: pytest.fail("spawned a second authority"),
    )

    state = ensure_supervisor(request.mission_id)
    assert state.phase == "accepted"
    assert state.generation == reviewed.generation
    (runtime / "supervisor-process.json").unlink()


def test_same_second_pid_reuse_with_another_birth_token_is_not_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = SupervisorProcess(
        mission_id="mission-supervisor-birth-token",
        request_sha256="a" * 64,
        generation=1,
        pid=424242,
        pgid=424242,
        started_at="Thu Aug 27 12:00:00 2026",
        birth_token="darwin:100:200",
        executable=sys.executable,
    )
    monkeypatch.setattr(
        process_control,
        "_owned_process_identity",
        lambda _pid: (
            record.pgid,
            record.started_at,
            "S",
            record.executable,
            "darwin:100:201",
        ),
    )

    assert not _live(record)


def test_linux_strong_legacy_comm_supervisor_and_planner_stay_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = SupervisorProcess(
        mission_id="mission-supervisor-linux-legacy-comm",
        request_sha256="a" * 64,
        generation=1,
        pid=424242,
        pgid=424242,
        started_at="Thu Aug 27 12:00:00 2026",
        birth_token="linux:boot:123",
        executable="python3",
    )
    current = (
        record.pgid,
        record.started_at,
        "S",
        "/usr/bin/python3.13",
        record.birth_token,
    )
    matched: list[tuple[int, str, str]] = []
    monkeypatch.setattr(
        process_control, "_owned_process_identity", lambda _pid: current
    )
    monkeypatch.setattr(
        process_control,
        "_matches_live_image",
        lambda pid, expected, observed: not matched.append((pid, expected, observed)),
    )
    monkeypatch.setattr(os, "killpg", lambda _pgid, _signal: None)

    assert _live(record)
    supervisor_module._stop_planner_child(
        PlannerChildProcess(
            pid=record.pid,
            pgid=record.pgid,
            started_at=record.started_at,
            birth_token=record.birth_token,
            executable=record.executable,
        )
    )
    assert matched == [
        (record.pid, "python3", "/usr/bin/python3.13"),
        (record.pid, "python3", "/usr/bin/python3.13"),
    ]

    def unavailable(*_args):
        raise process_control.ProcessControlError(
            "owned process identity is unavailable"
        )

    monkeypatch.setattr(process_control, "_matches_live_image", unavailable)
    with pytest.raises(process_control.ProcessControlError):
        _live(record)


def test_two_processes_share_one_mission_execution_authority(
    isolated_runtime,
) -> None:
    _state_root, _repository_path = isolated_runtime
    mission_id = "mission-execution-authority"
    runtime = _mission_runtime(mission_id)
    runtime.mkdir(mode=0o700, parents=True)
    phase = runtime / "execution-phase"
    invocations = runtime / "adapter-invocations"
    trigger = runtime / "trigger"
    phase.write_text("running", encoding="utf-8")
    script = """
import sys, time
from pathlib import Path
import graphene.cli.mission as mission

mission_id, phase_name, invocations_name, trigger_name, ready_name = sys.argv[1:]
phase = Path(phase_name)
invocations = Path(invocations_name)
trigger = Path(trigger_name)
Path(ready_name).write_text("ready", encoding="utf-8")
while not trigger.exists():
    time.sleep(0.005)

def adapter(**_values):
    if phase.read_text(encoding="utf-8") == "running":
        time.sleep(0.2)
        with invocations.open("a", encoding="utf-8") as stream:
            stream.write("provider-call\\n")
        phase.write_text("awaiting_result", encoding="utf-8")
    return {"status": "ok"}

mission._execute_adk_mission_owned = adapter
mission._execute_adk_mission(store=object(), mission_id=mission_id)
"""
    ready = [runtime / f"ready-{index}" for index in range(2)]
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                mission_id,
                str(phase),
                str(invocations),
                str(trigger),
                str(ready_path),
            ],
            env=os.environ.copy(),
        )
        for ready_path in ready
    ]
    deadline = time.monotonic() + 5
    while not all(path.exists() for path in ready) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert all(path.exists() for path in ready)
    trigger.write_text("go", encoding="utf-8")
    for child in children:
        assert child.wait(timeout=5) == 0
    assert invocations.read_text(encoding="utf-8").splitlines() == ["provider-call"]


def test_failed_supervisor_recovers_once_only_after_mission_started(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-failed-recovery")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    deadline = time.monotonic() + 5
    process = SupervisorProcess.model_validate_json(
        (runtime / "supervisor-process.json").read_bytes()
    )
    while _live(process) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _live(process)
    _state(
        runtime,
        request,
        "failed",
        reviewed.generation,
        error_code="runtime-error",
    )

    assert recover_supervisors() == 0
    assert supervisor_status(request.mission_id).phase == "failed"

    store = _store_for_mission(request.mission_id)
    try:
        snapshot = store.snapshot(request.mission_id)
        store.approve_plan(
            request.mission_id,
            "approve-failed-supervisor",
            expected_revision=snapshot.plan.revision,
            expected_head=snapshot.head,
            operator_label="process-test",
            rationale="advance authoritative mission before recovery",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=datetime.now(UTC),
        )
    finally:
        store.close()

    doomed = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    pgid, started_at, _process_state, executable, birth_token = (
        process_control._owned_process_identity(doomed.pid)
    )
    _write(
        runtime / "supervisor-process.json",
        SupervisorProcess(
            mission_id=request.mission_id,
            request_sha256=request.request_sha256,
            generation=reviewed.generation,
            pid=doomed.pid,
            pgid=pgid,
            started_at=started_at,
            birth_token=birth_token,
            executable=executable,
        ),
    )
    spawned: list[int] = []

    def spawn(runtime: Path, request, generation: int) -> None:
        spawned.append(generation)
        _state(runtime, request, "accepted", generation)
        _write(
            runtime / "supervisor-process.json",
            SupervisorProcess(
                mission_id=request.mission_id,
                request_sha256=request.request_sha256,
                generation=generation,
                pid=os.getpid(),
                pgid=os.getpid(),
                started_at="failed-recovery-test",
                birth_token="failed-recovery-test-birth",
                executable=sys.executable,
            ),
        )

    try:
        monkeypatch.setattr(supervisor_module, "_spawn", spawn)
        assert recover_supervisors() == 1
        assert doomed.poll() is None
        assert spawned == [reviewed.generation + 1]
        assert (
            supervisor_status(request.mission_id).generation == reviewed.generation + 1
        )
        monkeypatch.setattr(supervisor_module, "_live", lambda _record: True)
        recover_supervisors()
        assert spawned == [reviewed.generation + 1]
        (runtime / "supervisor-process.json").unlink()
    finally:
        doomed.terminate()
        doomed.wait(timeout=5)


@pytest.mark.skipif(
    not scripted_supported(), reason="scripted sandbox is unsupported on this host"
)
def test_resume_replaces_supervisor_that_exited_while_paused_between_batches(
    isolated_runtime,
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-resume")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed
    runtime = _mission_runtime(request.mission_id)
    first_process = SupervisorProcess.model_validate_json(
        (runtime / "supervisor-process.json").read_bytes()
    )
    deadline = time.monotonic() + 5
    while _live(first_process) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _live(first_process)

    store = _store_for_mission(request.mission_id)
    try:
        snapshot = store.snapshot(request.mission_id)
        store.approve_plan(
            request.mission_id,
            "approve-before-paused-batch",
            expected_revision=snapshot.plan.revision,
            expected_head=snapshot.head,
            operator_label="process-test",
            rationale="Start the bounded pause and resume recovery fixture.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=datetime.now(UTC),
        )
    finally:
        store.close()

    generation = reviewed.generation + 1
    _state(runtime, request, "accepted", generation)
    pause_after_first_batch = """
import sys
from datetime import UTC, datetime
from graphene.cli.mission import _store_for_mission
from graphene.core_models import TruthKind
from graphene.orchestration import scripted, supervisor

mission_id, request_sha256, generation = sys.argv[1], sys.argv[2], int(sys.argv[3])
original = scripted._execute_scripted_batch
paused = False

def execute_then_pause(*args, **kwargs):
    global paused
    original(*args, **kwargs)
    if not paused:
        paused = True
        store = _store_for_mission(mission_id)
        try:
            store.pause(
                mission_id,
                "pause-between-supervised-batches",
                expected_head=store.head(mission_id),
                operator_label="process-test",
                rationale="Pause after a completed batch with no active child.",
                truth_kind=TruthKind.SERVER_DERIVED,
                recorded_at=datetime.now(UTC),
            )
        finally:
            store.close()

scripted._execute_scripted_batch = execute_then_pause
raise SystemExit(supervisor.run_supervisor(mission_id, request_sha256, generation))
"""
    process = subprocess.Popen(
        (
            sys.executable,
            "-I",
            "-c",
            pause_after_first_batch,
            request.mission_id,
            request.request_sha256,
            str(generation),
        ),
        cwd=repository,
        env=os.environ.copy(),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    time.sleep(0.05)
    pgid, started_at, process_state, executable, birth_token = (
        process_control._owned_process_identity(process.pid)
    )
    assert pgid == process.pid and not process_state.startswith("Z")
    _write(
        runtime / "supervisor-process.json",
        SupervisorProcess(
            mission_id=request.mission_id,
            request_sha256=request.request_sha256,
            generation=generation,
            pid=process.pid,
            pgid=pgid,
            started_at=started_at,
            birth_token=birth_token,
            executable=executable,
        ),
    )
    assert process.stdin is not None
    process.stdin.close()
    assert process.wait(timeout=60) == 1
    failed = supervisor_status(request.mission_id)
    assert failed.phase == "failed" and failed.generation == generation
    assert (
        process_control.OwnedProcessRegistry(runtime).records_for_mission(
            request.mission_id
        )
        == ()
    )

    resumed = subprocess.run(
        (
            sys.executable,
            "-m",
            "graphene.cli.main",
            "--json",
            "mission",
            "resume",
            request.mission_id,
            "--command-id",
            "resume-after-supervisor-exit",
        ),
        cwd=repository,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    replacement = _wait_for_phase(
        request.mission_id, {"review_required", "failed"}, timeout=60
    )
    assert replacement.phase == "review_required", replacement
    assert replacement.generation > generation
    resumed_store = _store_for_mission(request.mission_id)
    try:
        snapshot = resumed_store.snapshot(request.mission_id)
        assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
        assert len(snapshot.attempts) > 2
    finally:
        resumed_store.close()


@pytest.mark.skipif(
    not scripted_supported(), reason="scripted sandbox is unsupported on this host"
)
def test_startup_recovers_approval_commit_and_prepares_missing_bundle(
    isolated_runtime,
) -> None:
    state_root, repository = isolated_runtime
    request, _accepted = _accept(repository, "request-supervisor-0003")
    reviewed = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert reviewed.phase == "review_required", reviewed

    store = _store_for_mission(request.mission_id)
    try:
        snapshot = store.snapshot(request.mission_id)
        store.approve_plan(
            request.mission_id,
            "approve-after-supervisor-crash",
            expected_revision=snapshot.plan.revision,
            expected_head=snapshot.head,
            operator_label="process-test",
            rationale="simulate approval committed before supervisor signal",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=datetime.now(UTC),
        )
    finally:
        store.close()

    malformed = state_root / "missions" / "000-malformed-runtime"
    malformed.mkdir(mode=0o700)
    (malformed / "supervisor-request.json").write_bytes(b"{")
    (malformed / "supervisor-request.json").chmod(0o600)

    assert recover_supervisors() == 1
    recovered = _wait_for_phase(request.mission_id, {"review_required", "failed"})
    assert recovered.phase == "review_required", recovered
    assert recovered.generation > reviewed.generation

    store = _store_for_mission(request.mission_id)
    try:
        snapshot = store.snapshot(request.mission_id)
        assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
        events = store.tail(request.mission_id, 0, snapshot.head.seq)
        bundles = [
            event
            for event in events
            if event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
        ]
        assert len(bundles) == 1
        bundle_id = bundles[0].payload["bundle_id"]
    finally:
        store.close()
    assert (
        _mission_runtime(request.mission_id) / "final-bundles" / f"{bundle_id}.json"
    ).is_file()


@pytest.mark.skipif(
    not scripted_supported(), reason="scripted sandbox is unsupported on this host"
)
def test_duplicate_start_does_not_respawn_a_terminal_supervisor(
    isolated_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _state_root, repository = isolated_runtime
    request, _accepted = _accept(
        repository,
        "request-supervisor-0004",
        requested_mode="policy_pre_authorized",
        finalization_mode="auto_finalize_isolated",
    )
    completed = _wait_for_phase(request.mission_id, {"completed", "failed"}, 180)
    assert completed.phase == "completed", completed
    runtime = _mission_runtime(request.mission_id)
    process_path = runtime / "supervisor-process.json"
    process_bytes = process_path.read_bytes()
    process = SupervisorProcess.model_validate_json(process_bytes)
    deadline = time.monotonic() + 5
    while _live(process) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _live(process)

    _state(runtime, request, "finalizing", completed.generation)
    private_state = (runtime / "supervisor-state.json").read_bytes()
    reconciled = supervisor_status(request.mission_id)
    assert reconciled.phase == "completed"
    assert reconciled.generation == completed.generation
    assert (runtime / "supervisor-state.json").read_bytes() == private_state
    assert process_path.read_bytes() == process_bytes

    _state(
        runtime,
        request,
        "failed",
        completed.generation,
        error_code="after-store-completion",
    )
    reconciled = ensure_supervisor(request.mission_id, recover_failed=True)
    assert reconciled.phase == "completed"
    assert reconciled.generation == completed.generation
    assert process_path.read_bytes() == process_bytes

    _state(
        runtime,
        request,
        "failed",
        completed.generation,
        error_code="before-duplicate-start",
    )

    duplicate, duplicate_state = _accept(
        repository,
        "request-supervisor-0004",
        requested_mode="policy_pre_authorized",
        finalization_mode="auto_finalize_isolated",
    )

    assert duplicate == request
    assert duplicate_state.phase == "completed"
    assert duplicate_state.generation == reconciled.generation
    assert process_path.read_bytes() == process_bytes

    terminal_reconciliations: list[str] = []
    monkeypatch.setattr(
        supervisor_module,
        "_reconcile_terminal_worker_receipts",
        lambda mission_id: terminal_reconciliations.append(mission_id) or 0,
    )
    recover_supervisors()
    assert terminal_reconciliations == [request.mission_id]
