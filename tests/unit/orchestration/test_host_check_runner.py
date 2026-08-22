from __future__ import annotations

import asyncio
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graphene.cli import mission as mission_cli
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.models import (
    AttemptState,
    CommandTemplate,
    Dispatch,
    MissionStatus,
    TaskKind,
)
from graphene.orchestration.process_control import OwnedProcessRegistry
from graphene.orchestration.runtime import (
    WORKER_PROVIDER_RECEIPT_KIND,
    HostSandboxCheckRunner,
    RuntimeAssignment,
    RuntimeErrorCode,
    RuntimeFailure,
)
from tests.unit.orchestration.test_gemini_mission_runtime import (
    prepare_fake_two_worker_mission,
    quiet_resource_sampler,
)

DARWIN_SANDBOX = pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="host-sandbox check runner requires macOS /usr/bin/sandbox-exec",
)
FIXTURE_TESTS = CommandTemplate(
    template_id="fixture-tests",
    argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
    timeout_seconds=15,
)
PASSING_TEST = "def test_ok() -> None:\n    assert True\n"


def _assignment(template: CommandTemplate) -> RuntimeAssignment:
    return RuntimeAssignment(
        task_id="work-a",
        title="Work A",
        contract="Create one bounded file.",
        read_paths=("README.md",),
        output_name="change",
        output_kind="patch",
        command_template=template,
    )


def _runner(tmp_path: Path, **overrides) -> HostSandboxCheckRunner:
    def refuse(attempt_id: str) -> Dispatch:
        raise AssertionError(f"dispatch lookup must not run for {attempt_id}")

    values = {
        "dispatch_for": refuse,
        "status": lambda: MissionStatus.RUNNING,
    }
    values.update(overrides)
    return HostSandboxCheckRunner(OwnedProcessRegistry(tmp_path / "runtime"), **values)


@DARWIN_SANDBOX
def test_host_sandbox_runner_completes_fake_mission_with_owned_check_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(
        tmp_path,
        monkeypatch,
        command_templates=(FIXTURE_TESTS,),
        extra_files={"tests/test_ok.py": PASSING_TEST},
    )
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "host-sandbox")
    recorded: list[tuple[str, str, int, str]] = []
    original_record = OwnedProcessRegistry.record

    def observe_record(self, dispatch, process, executable) -> None:
        original_record(self, dispatch, process, executable)
        assert self.directory == prepared.runtime / "processes"
        assert self._path(dispatch.attempt_id).is_file()
        recorded.append(
            (dispatch.mission_id, dispatch.attempt_id, process.pid, executable)
        )

    monkeypatch.setattr(OwnedProcessRegistry, "record", observe_record)

    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        resource_sampler=quiet_resource_sampler,
    )

    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert result["parallel_overlap_observed"] is True
    snapshot = prepared.store.snapshot(prepared.mission_id)
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    committed = tuple(
        item for item in snapshot.attempts if item.state == AttemptState.COMMITTED
    )
    kinds = {item.task_id: item.kind for item in snapshot.tasks}
    assert {kinds[item.task_id] for item in committed} == {
        TaskKind.WORK,
        TaskKind.ASSEMBLY,
        TaskKind.VERIFICATION,
    }
    # Every committed attempt's check ran as a registered Graphene-owned
    # process-group leader under sandbox-exec, and no record outlives it.
    assert {item[1] for item in recorded} == {item.attempt_id for item in committed}
    assert {item[0] for item in recorded} == {prepared.mission_id}
    assert {item[3] for item in recorded} == {"/usr/bin/sandbox-exec"}
    assert len({item[2] for item in recorded}) == len(recorded)
    registry = OwnedProcessRegistry(prepared.runtime)
    assert registry.records_for_mission(prepared.mission_id) == ()
    assert not tuple(registry.directory.glob("*.json"))
    evidence = mission_cli._mission_evidence(prepared.store, prepared.mission_id)
    for attempt in committed:
        receipts = tuple(
            item for item in attempt.evidence_refs if item.kind == "test-receipt"
        )
        assert len(receipts) == 1
        content = evidence.resolve(receipts[0].kind, receipts[0].id)
        assert content is not None
        receipt = TrustedCheckReceipt.model_validate_json(content)
        assert receipt.runner_id == "graphene_check_runner_v1"
        assert receipt.template_id == "fixture-tests"
        assert receipt.exit_code == 0
        assert receipt.timed_out is False
        assert receipt.result_code == "passed"
        assert receipt.attempt_id == attempt.attempt_id
        if kinds[attempt.task_id] == TaskKind.WORK:
            assert (
                sum(
                    item.kind == WORKER_PROVIDER_RECEIPT_KIND
                    for item in attempt.evidence_refs
                )
                == 1
            )
    assert prepared.store.verify(prepared.mission_id) == snapshot.head
    assert not (prepared.repository / ".graphene/generated").exists()
    assert _status(prepared.repository) == prepared.source_status


def _status(repository: Path) -> str:
    import subprocess

    return subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()


def test_invalid_check_executor_fails_closed_before_any_worker_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    canary = "podman-executor-canary-41c2"
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", canary)

    with pytest.raises(
        mission_cli.MissionCliError,
        match="^GRAPHENE_CHECK_EXECUTOR must be docker or host-sandbox$",
    ):
        mission_cli._execute_adk_mission(
            store=prepared.store,
            mission_id=prepared.mission_id,
            registry=prepared.registry,
            resource_sampler=quiet_resource_sampler,
        )

    assert prepared.model_a.calls == 0
    assert prepared.model_b.calls == 0
    snapshot = prepared.store.snapshot(prepared.mission_id)
    assert snapshot.mission.status == MissionStatus.RUNNING
    assert snapshot.attempts == ()
    report = mission_cli.doctor(prepared.repository)
    assert report["check_executor"] == {
        "requested": "invalid",
        "supported": False,
        "reason": "GRAPHENE_CHECK_EXECUTOR must be docker or host-sandbox",
    }
    assert canary not in json.dumps(report, sort_keys=True)


@pytest.mark.parametrize(
    ("configured", "requested"),
    [
        (None, "docker"),
        ("", "docker"),
        ("docker", "docker"),
        (" host-sandbox ", "host-sandbox"),
    ],
)
def test_doctor_reports_the_requested_check_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured: str | None,
    requested: str,
) -> None:
    if configured is None:
        monkeypatch.delenv("GRAPHENE_CHECK_EXECUTOR", raising=False)
    else:
        monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", configured)

    report = mission_cli.doctor(tmp_path)["check_executor"]

    assert report["requested"] == requested
    assert isinstance(report["supported"], bool)
    assert report["reason"]
    if requested == "host-sandbox":
        assert report["supported"] is mission_cli.scripted_supported()
    else:
        assert report["supported"] is (shutil.which("docker") is not None)


@pytest.mark.parametrize(
    "template",
    [
        CommandTemplate(
            template_id="fixture-tests",
            argv=("git", "diff", "--check", "--"),
            timeout_seconds=5,
        ),
        CommandTemplate(
            template_id="fixture-tests",
            argv=("python", "-m", "pytest", "-q"),
            timeout_seconds=15,
        ),
        CommandTemplate(
            template_id="fixture-tests",
            argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
            timeout_seconds=15,
            cwd="tests",
        ),
    ],
)
def test_host_sandbox_runner_rejects_any_template_but_the_frozen_command(
    tmp_path: Path, template: CommandTemplate
) -> None:
    runner = _runner(tmp_path)

    with pytest.raises(RuntimeFailure) as rejected:
        asyncio.run(runner(tmp_path, _assignment(template), "attempt-1"))

    assert rejected.value.code == RuntimeErrorCode.POLICY_REJECTED
    assert not tuple(runner.registry.directory.iterdir())


def test_host_sandbox_runner_fails_closed_off_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    runner = _runner(tmp_path)

    with pytest.raises(RuntimeFailure) as rejected:
        asyncio.run(runner(tmp_path, _assignment(FIXTURE_TESTS), "attempt-1"))

    assert rejected.value.code == RuntimeErrorCode.SANDBOX_UNAVAILABLE
    assert not tuple(runner.registry.directory.iterdir())


@DARWIN_SANDBOX
def test_host_sandbox_runner_rejects_unknown_or_mismatched_attempt_owners(
    tmp_path: Path,
) -> None:
    dispatch = Dispatch(
        mission_id="mission-host",
        plan_revision=1,
        plan_sha256="0" * 64,
        task_id="work-a",
        task_kind=TaskKind.WORK,
        attempt_id="attempt-other",
        attempt_number=1,
        worker_id="worker-a",
        workspace_id="workspace-a",
        lease_id="lease-a",
        fencing_token=1,
        dispatch_command_id="dispatch-command-host-0001",
        write_paths=(),
        allowed_commands=("fixture-tests",),
        acceptance_checks=("fixture-tests",),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    def unknown(attempt_id: str) -> Dispatch:
        raise KeyError(attempt_id)

    for dispatch_for in (unknown, lambda _attempt_id: dispatch):
        runner = _runner(tmp_path, dispatch_for=dispatch_for)
        with pytest.raises(RuntimeFailure) as rejected:
            asyncio.run(runner(tmp_path, _assignment(FIXTURE_TESTS), "attempt-1"))
        assert rejected.value.code == RuntimeErrorCode.POLICY_REJECTED
        assert not tuple(runner.registry.directory.iterdir())


def _dispatch_for_attempt(attempt_id: str) -> Dispatch:
    return Dispatch(
        mission_id="mission-host",
        plan_revision=1,
        plan_sha256="0" * 64,
        task_id="work-a",
        task_kind=TaskKind.WORK,
        attempt_id=attempt_id,
        attempt_number=1,
        worker_id="worker-a",
        workspace_id="workspace-a",
        lease_id="lease-a",
        fencing_token=1,
        dispatch_command_id="dispatch-command-host-0002",
        write_paths=(),
        allowed_commands=("fixture-tests",),
        acceptance_checks=("fixture-tests",),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def test_host_sandbox_runner_rejects_a_timeout_above_the_fixture_cap(
    tmp_path: Path,
) -> None:
    over_cap = CommandTemplate(
        template_id="fixture-tests",
        argv=FIXTURE_TESTS.argv,
        timeout_seconds=61,
    )
    runner = _runner(tmp_path)
    with pytest.raises(RuntimeFailure) as rejected:
        asyncio.run(runner(tmp_path, _assignment(over_cap), "attempt-1"))
    assert rejected.value.code == RuntimeErrorCode.POLICY_REJECTED
    assert not tuple(runner.registry.directory.iterdir())


@DARWIN_SANDBOX
def test_host_sandbox_runner_enforces_the_template_timeout_and_reaps_the_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hanging check is SIGKILLed through the registry after exec-in-place.

    The attested outcome says timed_out, cleanup_complete is measured from the
    owned record being gone, and the sandboxed process group no longer exists.
    """

    import os
    import signal as signals

    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_slow.py").write_text(
        "import time\n\n\ndef test_slow() -> None:\n    time.sleep(20)\n",
        encoding="utf-8",
    )
    short = CommandTemplate(
        template_id="fixture-tests", argv=FIXTURE_TESTS.argv, timeout_seconds=1
    )
    dispatch = _dispatch_for_attempt("attempt-slow")
    runner = _runner(tmp_path, dispatch_for=lambda _attempt_id: dispatch)
    groups: list[int] = []
    original_record = OwnedProcessRegistry.record

    def observe_record(self, owned_dispatch, process, executable) -> None:
        original_record(self, owned_dispatch, process, executable)
        groups.append(process.pid)

    monkeypatch.setattr(OwnedProcessRegistry, "record", observe_record)

    outcome = asyncio.run(runner(workspace, _assignment(short), "attempt-slow"))

    assert outcome.timed_out is True
    assert outcome.cleanup_complete is True
    assert outcome.template_id == "fixture-tests"
    assert not runner.registry.has_record("attempt-slow")
    assert len(groups) == 1
    with pytest.raises(ProcessLookupError):
        os.killpg(groups[0], signals.SIGCONT)


def test_host_sandbox_selection_fails_before_any_worker_runs_off_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(
        tmp_path,
        monkeypatch,
        command_templates=(FIXTURE_TESTS,),
        extra_files={"tests/test_ok.py": PASSING_TEST},
    )
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "host-sandbox")
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(
        mission_cli.MissionCliError,
        match="^GRAPHENE_CHECK_EXECUTOR=host-sandbox requires macOS",
    ):
        mission_cli._execute_adk_mission(
            store=prepared.store,
            mission_id=prepared.mission_id,
            registry=prepared.registry,
            resource_sampler=quiet_resource_sampler,
        )

    assert prepared.model_a.calls == 0
    assert prepared.model_b.calls == 0
    snapshot = prepared.store.snapshot(prepared.mission_id)
    assert snapshot.mission.status == MissionStatus.RUNNING
    assert snapshot.attempts == ()
    assert mission_cli.doctor(prepared.repository)["check_executor"] == {
        "requested": "host-sandbox",
        "supported": False,
        "reason": "host-sandbox requires macOS /usr/bin/sandbox-exec",
    }
