from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.adk.models import LlmRequest, LlmResponse
from pydantic import PrivateAttr

from graphene.cli import mission as mission_cli
from graphene.execution.adapter import _FIXED_TEST_COMMAND, _sanitized_environment
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.core_models import TruthKind
from graphene.orchestration.adk_planner import (
    PlanIntent,
    PlanningRequest,
    WorkIntent,
    compile_plan_intent,
    criterion_id,
)
from graphene.orchestration.mission_models import (
    AttemptState,
    AuthorizationMode,
    CriterionVerificationKind,
    FinalizationMode,
    Mission,
    MissionEventType,
    MissionStatus,
    ProjectPolicy,
    TaskKind,
    TaskState,
    plan_policy_decision,
)
from graphene.orchestration.final_bundle import FinalResultBundleV2
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.resources import ResourcePoint
from graphene.orchestration.process_control import OwnedProcessRegistry
from graphene.orchestration.scheduler import MissionScheduler, SystemClock
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore
from graphene.orchestration.validation import evaluate_plan_policy
from graphene.orchestration.worker_runtime import (
    WORKER_PROVIDER_INTERRUPTION_KIND,
    WORKER_PROVIDER_RECEIPT_KIND,
    CheckOutcome,
    CompletionOutcome,
    RuntimeAssignment,
    RuntimeErrorCode,
    WorkerCompletion,
    WorkerProviderInterruption,
    WorkerProviderReceipt,
    WorkerRegistry,
    stable_operation_id,
)
from graphene.orchestration.workers import (
    DeterministicWorkerModel,
    FileMutation,
    GeminiWorkerAdapter,
)
from graphene.orchestration.workers.gemini import (
    GeminiChildRequest,
    GeminiChildSource,
    WorkerIntent,
    child_frame_bytes,
)
from scripts.materialize_north_star import load_goal, materialize

from .test_store import NOW, _command, _mission, _plan, _policy


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


def test_owned_result_repository_ignores_ambient_git_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Source Test")
    _git(source, "config", "user.email", "source@example.invalid")
    (source / "README.md").write_text("# Source\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-q", "-m", "base")
    base_sha = _git(source, "rev-parse", "HEAD")

    caller = tmp_path / "caller"
    caller.mkdir()
    _git(caller, "init", "-q")
    _git(caller, "remote", "add", "sentinel", str(source))
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("GIT_DIR", str(caller / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(caller))

    repository = mission_cli._ensure_owned_result_repository(source, runtime, base_sha)

    assert _git(caller, "remote") == "sentinel"
    assert mission_cli._git_read(repository, "remote") == b""
    assert mission_cli._git_read(repository, "rev-parse", "HEAD").strip() == (
        base_sha.encode()
    )


def test_legacy_gemini_mission_recovers_as_review_only_under_v2_policy(
    tmp_path: Path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "legacy-policy-recovery.sqlite")
    policy = ProjectPolicy.model_validate(
        {
            **_policy().model_dump(mode="json"),
            "schema_version": 2,
            "authorization_mode": AuthorizationMode.POLICY_PRE_AUTHORIZED,
            "finalization_mode": FinalizationMode.AUTO_FINALIZE_ISOLATED,
        }
    )
    mission = _mission()
    plan = _plan()
    store.create_mission(
        policy,
        mission,
        plan,
        _command("create-legacy-policy-v2"),
        recorded_at=NOW,
    )
    snapshot = store.snapshot(mission.mission_id)

    recovered = mission_cli._ensure_gemini_policy_decision(
        argparse.Namespace(
            authorization_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
            finalization_mode=FinalizationMode.AUTO_FINALIZE_ISOLATED,
        ),
        command_id="command_legacy_policy_recovery_0001",
        policy=policy,
        store=store,
        snapshot=snapshot,
    )
    decision = plan_policy_decision(
        store.tail(mission.mission_id, 0, recovered.head.event_count),
        plan.revision,
    )

    assert decision is not None
    assert decision.requested_mode == AuthorizationMode.REVIEW_REQUIRED
    assert decision.effective_mode == AuthorizationMode.REVIEW_REQUIRED
    assert decision.finalization_mode == FinalizationMode.REVIEW_REQUIRED
    assert recovered.mission.status == MissionStatus.PROPOSED
    assert store.verify(mission.mission_id) == recovered.head

    legacy_snapshot = SimpleNamespace(
        mission=SimpleNamespace(schema_version=1),
        policy=SimpleNamespace(schema_version=1),
    )
    assert (
        mission_cli._ensure_gemini_policy_decision(
            argparse.Namespace(),
            command_id="command_mocked_legacy_review_0001",
            policy=legacy_snapshot.policy,
            store=object(),
            snapshot=legacy_snapshot,
        )
        is legacy_snapshot
    )


def test_taskmaster_demo_command_selects_live_opt_in_driver() -> None:
    args = mission_cli.build_parser().parse_args(
        ["mission", "demo", "taskmaster", "--driver", "gemini-adk", "--open"]
    )

    assert args.mission_action == "demo"
    assert args.driver == "gemini-adk"
    assert args.max_workers == 2
    assert args.open_viewer is True
    with pytest.raises(SystemExit):
        mission_cli.build_parser().parse_args(
            ["mission", "demo", "taskmaster", "--max-workers", "1"]
        )


def test_outbound_executor_connect_parser_requires_two_to_five_workers() -> None:
    args = mission_cli.build_parser().parse_args(
        [
            "mission",
            "executor",
            "connect",
            "--repo",
            ".",
            "--mission",
            "mission-outbound",
            "--coordinator-url",
            "https://coordinator.example/v1",
            "--audience",
            "https://coordinator.example",
            "--workers",
            "2",
            "--expected-seq",
            "7",
            "--expected-event-sha256",
            "a" * 64,
        ]
    )

    assert args.mission_action == "executor"
    assert args.executor_action == "connect"
    assert args.workers == 2
    assert args.expected_seq == 7
    with pytest.raises(SystemExit):
        mission_cli.build_parser().parse_args(
            [
                "mission",
                "executor",
                "connect",
                "--repo",
                ".",
                "--mission",
                "mission-outbound",
                "--coordinator-url",
                "https://coordinator.example",
                "--audience",
                "https://coordinator.example",
                "--workers",
                "1",
            ]
        )


def test_doctor_separates_cloud_configuration_without_echoing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "doctor-repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Doctor Test")
    _git(repository, "config", "user.email", "doctor@example.invalid")
    (repository / "README.md").write_text("# Doctor\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "base")
    mission_cli.initialize(repository)
    canary = "cloud-binding-secret-canary"
    for name, value in {
        "GOOGLE_CLOUD_PROJECT": "graphene-project",
        "GRAPHENE_FIRESTORE_DATABASE": "graphene",
        "GRAPHENE_FIRESTORE_NAMESPACE": "graphene",
        "GRAPHENE_MISSION_ID": "mission-cloud",
        "GRAPHENE_MISSION_CONTROL_READ_TOKEN": "read-token-not-reported",
        "GRAPHENE_COORDINATOR_AUDIENCE": "https://coordinator.example",
        "GRAPHENE_COORDINATOR_URL": "https://coordinator.example/private",
        "GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS": json.dumps(
            {canary: "executor-local"}
        ),
    }.items():
        monkeypatch.setenv(name, value)

    cloud = mission_cli.doctor(repository)["modes"]["firestore-cloud"]

    assert cloud["read_viewer"]["configuration_ready"] is True
    assert cloud["private_coordinator"]["configuration_ready"] is True
    assert cloud["outbound_executor"]["configuration_ready"] is True
    assert cloud["outbound_executor"]["adc_token_proven"] is False
    assert cloud["connectivity_proven"] is False
    assert cloud["write_proven"] is False
    assert canary not in json.dumps(cloud)


def test_outbound_executor_preflight_runs_before_client_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = mission_cli.build_parser().parse_args(
        [
            "mission",
            "executor",
            "connect",
            "--repo",
            str(tmp_path),
            "--mission",
            "mission-outbound",
            "--coordinator-url",
            "https://coordinator.example",
            "--audience",
            "https://coordinator.example",
        ]
    )
    monkeypatch.setattr(
        mission_cli,
        "_load_project_policy",
        lambda _repo: (tmp_path, "a" * 40, object()),
    )
    monkeypatch.setattr(
        mission_cli,
        "doctor",
        lambda _repo: {"gemini_preflight": {"configuration_ready": False}},
    )
    monkeypatch.setattr(
        mission_cli,
        "CoordinatorClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network client constructed before preflight")
        ),
    )

    with pytest.raises(mission_cli.MissionCliError, match="preflight"):
        mission_cli._executor_connect(args)


def test_outbound_executor_registers_two_narrow_workers_and_sanitizes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = "mission-outbound"
    head = mission_cli.MissionHead(
        mission_id=mission_id, seq=7, event_count=7, event_sha256="a" * 64
    )

    class Policy:
        base_sha = "b" * 40
        command_templates = ()

        @staticmethod
        def model_dump(*, mode: str):
            assert mode == "json"
            return {"base_sha": "b" * 40}

    policy = Policy()
    policy_sha = mission_cli.sha256_hex(
        mission_cli.canonical_json_bytes(policy.model_dump(mode="json"))
    )
    snapshot = SimpleNamespace(
        head=head,
        mission=SimpleNamespace(
            base_sha=policy.base_sha,
            plan_revision=1,
            status=MissionStatus.RUNNING,
        ),
        policy=SimpleNamespace(base_sha=policy.base_sha, policy_sha256=policy_sha),
        plan=SimpleNamespace(revision=1, tasks=()),
    )

    class Store:
        def snapshot(self, actual: str):
            assert actual == mission_id
            return snapshot

        def verify(self, actual: str):
            assert actual == mission_id
            return head

    calls = []
    monkeypatch.setattr(
        mission_cli,
        "_load_project_policy",
        lambda _repo: (tmp_path, policy.base_sha, policy),
    )
    monkeypatch.setattr(
        mission_cli,
        "doctor",
        lambda _repo: {"gemini_preflight": {"configuration_ready": True}},
    )
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _id: Store())
    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda _id: tmp_path)
    monkeypatch.setattr(mission_cli, "_mission_evidence", lambda *_args: object())
    monkeypatch.setattr(
        mission_cli.GeminiWorkerAdapter, "live", lambda **kwargs: object()
    )
    monkeypatch.setattr(mission_cli, "WorkerRegistry", lambda _items: object())
    monkeypatch.setattr(mission_cli, "CoordinatorClient", lambda *args: object())
    monkeypatch.setattr(mission_cli, "GoogleAdcAudienceTokenProvider", lambda: object())

    def connect(_client, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            session_id=kwargs["session_id"], claimed=0, completed=0, head=head
        )

    monkeypatch.setattr(mission_cli, "run_local_executor", connect)
    args = mission_cli.build_parser().parse_args(
        [
            "mission",
            "executor",
            "connect",
            "--repo",
            str(tmp_path),
            "--mission",
            mission_id,
            "--coordinator-url",
            "https://coordinator.example",
            "--audience",
            "https://coordinator.example",
            "--workers",
            "2",
        ]
    )

    result = mission_cli._executor_connect(args)

    assert result["status"] == "executor_stopped"
    assert result["worker_count"] == 2
    assert result["capabilities"] == ["work"]
    assert result["authenticated_coordinator_round_trip"] is True
    assert result["scope"] == "work_only_first_cloud_vertical"
    assert result["mission_completion_claimed"] is False
    assert len(calls) == 2
    assert {call["worker_id"] for call in calls} == {
        "outbound-work-1",
        "outbound-work-2",
    }
    assert all(call["capabilities"] == (mission_cli.TaskKind.WORK,) for call in calls)
    assert all(call["expected_head"] == head for call in calls)
    assert "coordinator.example" not in str(result)


def test_result_decision_resumes_pending_commit_through_shared_finalizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = SimpleNamespace(sha256="c" * 64)
    head = mission_cli.MissionHead(
        mission_id="mission-recovery",
        seq=11,
        event_count=11,
        event_sha256="d" * 64,
    )
    snapshot = SimpleNamespace(
        head=head,
        mission=SimpleNamespace(
            base_sha="e" * 40, final_outcome="approved_pending_commit"
        ),
        policy=SimpleNamespace(policy_sha256="a" * 64),
    )
    store = object()
    captured = {}
    receipt = SimpleNamespace(
        decision="approved",
        candidate_patch_sha256=candidate.sha256,
        receipt_id="receipt-recovered",
        local_commit_sha="f" * 40,
        result_ref="refs/graphene/results/recovered",
    )
    monkeypatch.setattr(
        mission_cli,
        "_scripted_bindings",
        lambda _mission_id: (
            store,
            snapshot,
            object(),
            object(),
            object(),
            candidate,
            object(),
        ),
    )

    def finalize(**kwargs):
        captured.update(kwargs)
        return head, receipt

    monkeypatch.setattr(mission_cli, "finalize_local_result_decision", finalize)
    bundle = SimpleNamespace(
        mission_id="mission-recovery",
        bundle_id="bundle_recovery_001",
        bundle_sha256="b" * 64,
        candidate_reference=SimpleNamespace(content_sha256=candidate.sha256),
    )
    monkeypatch.setattr(
        mission_cli, "_persisted_bundle_path", lambda _bundle_id: Path("bundle.json")
    )
    monkeypatch.setattr(mission_cli, "_read_bundle", lambda _path: (b"bundle", bundle))
    monkeypatch.setattr(
        "graphene.orchestration.final_bundle.verify_final_result_bundle",
        lambda *args, **kwargs: True,
    )
    args = SimpleNamespace(
        mission_id="mission-recovery",
        bundle_id=bundle.bundle_id,
        command_id="command-restart-finalize-001",
        operator_label="restart-operator",
        rationale="Resume the already approved isolated commit.",
        confirm_human=False,
    )

    result = mission_cli._result_decision(args, approved=True)

    assert captured["store"] is store
    assert captured["expected_head"] == head
    assert captured["command_id"] == "command-restart-finalize-001"
    assert captured["expected_bundle_id"] == bundle.bundle_id
    assert captured["approved"] is True
    assert result["status"] == "completed"
    assert result["local_commit_sha"] == "f" * 40


def test_demo_check_fault_is_one_shot_and_truth_labeled(tmp_path: Path) -> None:
    template = mission_cli.CommandTemplate(
        template_id="unit-check",
        argv=("git", "diff", "--check", "--"),
        timeout_seconds=5,
    )
    assignment = RuntimeAssignment(
        task_id="work-a",
        title="Work A",
        contract="Create one bounded file.",
        read_paths=("README.md",),
        output_name="change",
        output_kind="patch",
        command_template=template,
    )

    async def passed(*_args) -> CheckOutcome:
        return CheckOutcome(
            template_id=template.template_id,
            template_sha256=mission_cli.sha256_hex(
                mission_cli.canonical_json_bytes(template.model_dump(mode="json"))
            ),
            exit_code=0,
            timed_out=False,
            output_sha256="0" * 64,
            output_truncated=False,
            cleanup_complete=True,
        )

    runner = mission_cli._DemoOneShotCheckRunner(passed, tmp_path)
    first = asyncio.run(runner(tmp_path, assignment, "attempt-1"))
    repaired = asyncio.run(runner(tmp_path, assignment, "attempt-2"))
    later = asyncio.run(runner(tmp_path, assignment, "attempt-3"))

    assert first.exit_code == 97
    assert first.truth_kind == "simulated_fixture"
    assert first.truth_label == "demo_injected_deterministic_check_failure"
    assert repaired.exit_code == 0
    assert repaired.truth_label == "demo_retry_repaired_injected_check_failure"
    assert later.truth_label is None
    assert (tmp_path / "demo-check-fault.json").is_file()
    assert (tmp_path / "demo-check-repair.json").is_file()


def test_open_live_cancels_running_mission_when_coordinator_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Store:
        def __init__(self) -> None:
            self.status = MissionStatus.RUNNING
            self.cancelled = None

        def snapshot(self, mission_id: str):
            return type(
                "Snapshot",
                (),
                {
                    "mission": type("Mission", (), {"status": self.status})(),
                    "head": mission_cli.MissionHead(
                        mission_id=mission_id,
                        seq=4,
                        event_sha256="a" * 64,
                        event_count=4,
                    ),
                    "attempts": (),
                    "policy": SimpleNamespace(command_templates=()),
                },
            )()

        def recover_dispatches(self, *_args, **_kwargs):
            return ()

        def head(self, mission_id: str):
            return self.snapshot(mission_id).head

        def cancel(self, mission_id: str, command_id: str, **kwargs):
            self.cancelled = (mission_id, command_id, kwargs)
            self.status = MissionStatus.CANCELLED
            return self.snapshot(mission_id).head

    store = Store()
    monkeypatch.setattr(mission_cli, "_store", lambda mission_id=None: store)
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda mission_id: store)
    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda mission_id: tmp_path)
    monkeypatch.setattr(mission_cli, "_mission_evidence", lambda *args: object())
    monkeypatch.setattr(
        mission_cli,
        "_execute_adk_mission",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("private canary")),
    )
    monkeypatch.setattr(
        "graphene.orchestration.mission_control.create_mission_control_app",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "graphene.orchestration.mission_projection.MissionProjection",
        lambda *args, **kwargs: object(),
    )

    def serve(*args, **kwargs):
        assert kwargs["stop_event"].wait(2)
        return 0

    monkeypatch.setattr(mission_cli, "_serve", serve)

    with pytest.raises(mission_cli.MissionCliError, match="failed closed"):
        mission_cli._open_live("mission-coordinator-failure", coordinate_gemini=True)

    assert store.status == MissionStatus.CANCELLED
    assert store.cancelled is not None
    assert store.cancelled[2]["truth_kind"] == TruthKind.SERVER_DERIVED
    assert "private canary" not in store.cancelled[2]["rationale"]


def test_open_live_waits_for_active_runner_cleanup_before_cancel_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = "mission-active-browser-cancel"
    head = mission_cli.MissionHead(
        mission_id=mission_id,
        seq=4,
        event_count=4,
        event_sha256="a" * 64,
    )
    entered = threading.Event()
    cleaned = threading.Event()
    captured = {}

    class Store:
        status = MissionStatus.RUNNING

        def snapshot(self, _mission_id: str):
            return SimpleNamespace(
                mission=SimpleNamespace(status=self.status),
                head=head,
                attempts=(),
                policy=SimpleNamespace(command_templates=()),
            )

        def recover_dispatches(self, *_args, **_kwargs):
            return ()

        def cancel(self, _mission_id: str, _command_id: str, **_kwargs):
            assert cleaned.is_set(), "runtime cleanup must precede cancel authority"
            self.status = MissionStatus.CANCELLED
            return head

    store = Store()
    monkeypatch.setattr(mission_cli, "_store", lambda mission_id=None: store)
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda mission_id: store)
    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda mission_id: tmp_path)
    monkeypatch.setattr(mission_cli, "_mission_evidence", lambda *args: object())

    def execute(**kwargs):
        entered.set()
        while not kwargs["should_cancel"]():
            time.sleep(0.005)
        cleaned.set()
        raise mission_cli.RunnerCancelled("cancelled after owned cleanup")

    monkeypatch.setattr(mission_cli, "_execute_adk_mission", execute)

    def create_app(*_args, **kwargs):
        captured["cancel"] = kwargs["cancel_coordinator"]
        return object()

    monkeypatch.setattr(
        "graphene.orchestration.mission_control.create_mission_control_app", create_app
    )
    monkeypatch.setattr(
        "graphene.orchestration.mission_projection.MissionProjection",
        lambda *args, **kwargs: object(),
    )

    def serve(*_args, **_kwargs):
        assert entered.wait(2)
        captured["cancel"](
            mission_id=mission_id,
            command_id="browser-cancel-active-001",
            expected_head=head,
            operator_label="browser-operator",
            rationale="Cancel after active cleanup.",
            truth_kind=TruthKind.HUMAN_ATTESTED,
            recorded_at=datetime.now(UTC),
        )
        return 0

    monkeypatch.setattr(mission_cli, "_serve", serve)

    assert mission_cli._open_live(mission_id, coordinate_gemini=True) == 0
    assert cleaned.is_set()
    assert store.status == MissionStatus.CANCELLED


def quiet_resource_sampler(mission_id: str) -> tuple[ResourcePoint, ...]:
    """Report zero managed RSS so the governor never throttles new dispatch."""

    return (
        ResourcePoint(
            subject=mission_id,
            metric="current-rss-bytes",
            units="bytes",
            category="managed_runtime",
            scope="isolated_process_tree",
            attribution_quality="sampled_partial",
            observed_at=datetime.now(UTC),
            value=0,
            semantics="sampled-current-rss",
        ),
    )


class _AssignmentAwareWorkerModel(DeterministicWorkerModel):
    _assignment_mutations: dict[str, tuple[FileMutation, ...]] = PrivateAttr(
        default_factory=dict
    )
    _route_assignments: bool = PrivateAttr(default=False)

    def bind(
        self,
        mutations: tuple[FileMutation, ...],
        *,
        arrived: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self._route_assignments = False
        super().bind(mutations, arrived=arrived, release=release)

    def bind_assignments(
        self,
        assignments: dict[str, tuple[FileMutation, ...]],
        default: tuple[FileMutation, ...],
    ) -> None:
        self._assignment_mutations = assignments
        DeterministicWorkerModel.bind(self, default)
        self._route_assignments = True

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if self._route_assignments:
            prompt = "".join(
                part.text or ""
                for content in llm_request.contents
                for part in content.parts or ()
            )
            matches = [
                mutations
                for path, mutations in self._assignment_mutations.items()
                if path in prompt
            ]
            assert len(matches) == 1, prompt
            DeterministicWorkerModel.bind(self, matches[0])
        async for response in super().generate_content_async(llm_request, stream):
            yield response


def prepare_fake_two_worker_mission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    command_templates: tuple[mission_cli.CommandTemplate, ...] | None = None,
    extra_files: dict[str, str] | None = None,
) -> SimpleNamespace:
    """Create, bind, and approve a two-task Gemini plan backed by fake ADK workers.

    Returns everything a test needs to call ``_execute_adk_mission`` itself so
    each test chooses its own check runner, executor, and resource sampler.
    """

    repository = tmp_path / "source"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Runtime Test")
    _git(repository, "config", "user.email", "runtime@example.invalid")
    (repository / "README.md").write_text("# Source\n", encoding="utf-8")
    for relative, text in (extra_files or {}).items():
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(repository, "add", "--all", "--")
    _git(repository, "commit", "-q", "-m", "base")
    _policy_path, policy = mission_cli.initialize(repository)
    if command_templates is not None:
        policy = ProjectPolicy.model_validate(
            {
                **policy.model_dump(mode="json"),
                "command_templates": [
                    item.model_dump(mode="json") for item in command_templates
                ],
            }
        )
        (repository / ".graphene" / "project.json").write_bytes(
            canonical_json_bytes(policy.model_dump(mode="json")) + b"\n"
        )
    source_status = _git(repository, "status", "--porcelain=v1")
    source_readme = (repository / "README.md").read_bytes()
    state = tmp_path / "state"
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    args = argparse.Namespace(
        repo=repository,
        goal="Create two bounded generated reports.",
        success_criteria=["Both generated reports are present."],
        driver="gemini-adk",
        max_workers=2,
        auto_approve=False,
        command_id="command_fake_gemini_runtime_0001",
        open_viewer=False,
    )
    command_id, mission_id, _root, _head, _policy, binding = (
        mission_cli._start_identity(args)
    )
    runtime = mission_cli._mission_runtime(mission_id)
    runtime.mkdir(mode=0o700, parents=True)
    mission_cli._bind_start_request(runtime, binding)
    criterion = criterion_id(args.success_criteria[0])
    template_id = policy.command_templates[-1].template_id
    request = PlanningRequest(
        mission_id=mission_id,
        revision=1,
        goal=args.goal,
        success_criteria=tuple(args.success_criteria),
        repository_manifest=("README.md",),
    )
    plan = compile_plan_intent(
        policy,
        request,
        PlanIntent(
            mission_id=mission_id,
            revision=1,
            tasks=(
                WorkIntent(
                    task_id="report-a",
                    title="Create report A",
                    contract="Create only the first bounded report.",
                    criterion_ids=(criterion,),
                    assigned_role="worker",
                    read_paths=("README.md",),
                    write_paths=(".graphene/generated/a.txt",),
                    command_template_id=template_id,
                ),
                WorkIntent(
                    task_id="report-b",
                    title="Create report B",
                    contract="Create only the second bounded report.",
                    criterion_ids=(criterion,),
                    assigned_role="worker",
                    read_paths=("README.md",),
                    write_paths=(".graphene/generated/b.txt",),
                    command_template_id=template_id,
                ),
            ),
        ),
    )
    now = datetime.now(UTC)
    store = mission_cli._store()
    store.create_mission(
        policy,
        Mission(
            mission_id=mission_id,
            policy_id=policy.policy_id,
            policy_revision=policy.revision,
            repo_id=policy.repo_id,
            base_sha=policy.base_sha,
            goal=args.goal,
            success_criteria=tuple(args.success_criteria),
            plan_revision=1,
            creation_source="operator",
            resource_budget=policy.resource_budget,
            created_at=now,
        ),
        plan,
        "create_fake_gemini_runtime_0001",
        recorded_at=now,
    )
    store.approve_plan(
        mission_id,
        command_id,
        expected_revision=1,
        expected_head=store.head(mission_id),
        operator_label="test-operator",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=datetime.now(UTC),
    )
    mutation_a = FileMutation(
        operation="create",
        path=".graphene/generated/a.txt",
        text="alpha\n",
        mode="100644",
    )
    mutation_b = FileMutation(
        operation="create",
        path=".graphene/generated/b.txt",
        text="beta\n",
        mode="100644",
    )
    assignments = {
        mutation_a.path: (mutation_a,),
        mutation_b.path: (mutation_b,),
    }
    model_a = _AssignmentAwareWorkerModel(model="fixture-worker-a")
    model_a.bind_assignments(assignments, (mutation_a,))
    model_b = _AssignmentAwareWorkerModel(model="fixture-worker-b")
    model_b.bind_assignments(assignments, (mutation_b,))
    registry = WorkerRegistry(
        (
            GeminiWorkerAdapter.fake(worker_id="fake-a", model=model_a),
            GeminiWorkerAdapter.fake(worker_id="fake-b", model=model_b),
        )
    )
    return SimpleNamespace(
        repository=repository,
        policy=policy,
        plan=plan,
        mission_id=mission_id,
        runtime=runtime,
        state=state,
        store=store,
        registry=registry,
        model_a=model_a,
        model_b=model_b,
        source_status=source_status,
        source_readme=source_readme,
    )


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
@pytest.mark.parametrize("transport_acknowledged", (True, False))
def test_restart_reaps_barrier_child_records_interruption_and_retries_higher_fence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport_acknowledged: bool,
) -> None:
    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    mission_id = prepared.mission_id
    store = prepared.store
    model = "gemini-3.5-flash"
    prior_failures = []

    class RecoveredLiveAdapter(GeminiWorkerAdapter):
        async def _execute_child(self, context, request):  # noqa: ANN001
            prior_failures.append(request.prior_failure)
            path = request.write_paths[0]
            return (
                WorkerIntent(
                    mutations=(
                        FileMutation(
                            operation="create",
                            path=path,
                            text="alpha\n" if path.endswith("a.txt") else "beta\n",
                            mode="100644",
                        ),
                    )
                ),
                WorkerCompletion(
                    outcome=CompletionOutcome.COMPLETED,
                    result_code="passed",
                    session_id="recovered-session-" + context.dispatch.attempt_id[-8:],
                    invocation_id=(
                        "recovered-invocation-" + context.dispatch.attempt_id[-8:]
                    ),
                ),
            )

    adapters = tuple(
        RecoveredLiveAdapter(
            worker_id=f"recovery-worker-{index}",
            model=model,
            driver="gemini_live",
            credential_mode="gemini_api",
            heartbeat_seconds=0.01,
            model_timeout_seconds=10,
        )
        for index in (1, 2)
    )
    workers = WorkerRegistry(adapters)
    scheduler = MissionScheduler(
        store,
        clock=SystemClock(),
        lease_ttl_seconds=60,
        retry_backoff_seconds=0,
        runtime_id="gemini_adk_runtime",
        worker_capabilities=(TaskKind.WORK,),
    )
    dispatch = scheduler.tick(mission_id, ("recovery-worker-1",))[0]
    task = next(
        item for item in prepared.plan.tasks if item.task_id == dispatch.task_id
    )
    assignment = mission_cli._runtime_assignment(task, prepared.policy)
    source_text = (prepared.repository / "README.md").read_text(encoding="utf-8")
    request = GeminiChildRequest(
        mission_id=dispatch.mission_id,
        plan_revision=dispatch.plan_revision,
        plan_sha256=dispatch.plan_sha256,
        task_id=dispatch.task_id,
        attempt_id=dispatch.attempt_id,
        attempt_number=dispatch.attempt_number,
        worker_id=dispatch.worker_id,
        lease_id=dispatch.lease_id,
        fencing_token=dispatch.fencing_token,
        base_sha=prepared.policy.base_sha,
        policy_sha256=canonical_json_sha256(prepared.policy.model_dump(mode="json")),
        accepted_input_sha256=(),
        title=assignment.title,
        contract=assignment.contract,
        sources=(
            GeminiChildSource(
                path="README.md",
                sha256=sha256_hex(source_text.encode()),
                text=source_text,
            ),
        ),
        operator_inputs=(),
        write_paths=dispatch.write_paths,
        requested_model=model,
        credential_mode="gemini_api",
        timeout_seconds=10,
    )
    interpreter = os.path.abspath(sys.executable)
    child = subprocess.Popen(
        (interpreter, "-I", "-c", "import time; time.sleep(30)"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    reaper = threading.Thread(target=child.wait)
    reaper.start()
    process_registry = OwnedProcessRegistry(prepared.runtime)
    try:
        owned = process_registry.record_pid(
            dispatch,
            child.pid,
            interpreter,
            model_request_sha256=request.request_sha256(),
            model_input_bytes=len(child_frame_bytes(request)) - 4,
        )
        barrier = (
            process_registry.acknowledge_model_dispatch(
                dispatch,
                owned,
                request_sha256=request.request_sha256(),
                sdk_invocation_id="surviving-provider-invocation",
                dispatched_at="2026-08-27T12:00:00.000Z",
            )
            if transport_acknowledged
            else None
        )
        operation_id = stable_operation_id(dispatch, "model")
        operation_journal = prepared.runtime / "adk-runtime" / "operation-journal"
        operation_journal.mkdir(mode=0o700, parents=True)
        (operation_journal / f"{sha256_hex(operation_id.encode())}.json").write_bytes(
            canonical_json_bytes(
                {
                    "attempt_id": dispatch.attempt_id,
                    "fencing_token": dispatch.fencing_token,
                    "label": "model",
                    "lease_id": dispatch.lease_id,
                    "operation_id": operation_id,
                    "state": "started",
                }
            )
        )

        result = mission_cli._execute_adk_mission(
            store=store,
            mission_id=mission_id,
            registry=workers,
            check_runner=mission_cli._policy_check,
            resource_sampler=quiet_resource_sampler,
        )

        assert result["status"] == MissionStatus.AWAITING_RESULT
        assert child.wait(timeout=2) in {-15, -9}
        assert not process_registry.has_record(dispatch.attempt_id)
        snapshot = store.snapshot(mission_id)
        attempts = tuple(
            sorted(
                (
                    item
                    for item in snapshot.attempts
                    if item.task_id == dispatch.task_id
                ),
                key=lambda item: item.attempt_number,
            )
        )
        assert [item.state for item in attempts] == [
            AttemptState.FAILED,
            AttemptState.COMMITTED,
        ]
        assert attempts[0].result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED.value
        assert attempts[1].fencing_token > attempts[0].fencing_token
        reference = next(
            item
            for item in attempts[0].evidence_refs
            if item.kind == WORKER_PROVIDER_INTERRUPTION_KIND
        )
        content = mission_cli._mission_evidence(store, mission_id).resolve(
            reference.kind, reference.id
        )
        assert content is not None
        interruption = WorkerProviderInterruption.model_validate_json(content)
        assert interruption.provider_dispatch_state == (
            "transport_acknowledged" if transport_acknowledged else "unconfirmed"
        )
        assert interruption.sdk_invocation_id == (
            barrier.sdk_invocation_id if barrier is not None else None
        )
        assert interruption.dispatched_at == (
            barrier.dispatched_at if barrier is not None else None
        )
        assert interruption.repository_effect == "known_absent"
        assert interruption.provider_outcome == "unknown"
        assert interruption.billing_outcome == "unknown"
        retry_context = next(item for item in prior_failures if item is not None)
        assert retry_context.attempt_id == attempts[0].attempt_id
        assert retry_context.result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED.value
        assert retry_context.failure_class == "provider_interrupted"
    finally:
        if child.poll() is None:
            child.kill()
        reaper.join(timeout=2)
        assert not reaper.is_alive()


def test_approved_gemini_plan_runs_two_fake_adk_workers_without_touching_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    repository = prepared.repository
    policy = prepared.policy
    store = prepared.store
    mission_id = prepared.mission_id
    runtime = prepared.runtime
    plan = prepared.plan
    assert plan.criteria[0].verification_kind == CriterionVerificationKind.HUMAN_GATE
    assert plan.criteria[0].verifier_task_id is None
    assert plan.criteria[0].verifier_id == "final-result"
    samples = iter(
        (
            policy.resource_budget.soft_managed_rss_bytes + 1,
            0,
        )
    )

    def sample_managed_rss(actual_mission_id: str) -> tuple[ResourcePoint, ...]:
        return (
            ResourcePoint(
                subject=actual_mission_id,
                metric="current-rss-bytes",
                units="bytes",
                category="managed_runtime",
                scope="isolated_process_tree",
                attribution_quality="sampled_partial",
                observed_at=datetime.now(UTC),
                value=next(samples, 0),
                semantics="sampled-current-rss",
            ),
        )

    result = mission_cli._execute_adk_mission(
        store=store,
        mission_id=mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
        resource_sampler=sample_managed_rss,
    )

    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert result["dispatch_batches"][:2] == [["report-a"], ["report-b"]]
    resource_actions = [
        event.payload["action"]
        for event in store.tail(mission_id, 0, 256)
        if event.event_type
        in {
            MissionEventType.RESOURCE_BUDGET_CROSSED,
            MissionEventType.RESOURCE_SUMMARY_RECORDED,
        }
    ]

    assert resource_actions[:2] == [
        "reduce-new-dispatch",
        "allow-new-dispatch",
    ]
    assert len(result["worker_session_ids"]) == 2
    assert len(result["worker_invocation_ids"]) == 2
    assert _git(repository, "status", "--porcelain=v1") == prepared.source_status
    assert (repository / "README.md").read_bytes() == prepared.source_readme
    assert not (repository / ".graphene/generated").exists()
    assert (runtime / "repository" / ".git").is_dir()
    assert _git(runtime / "repository", "remote") == ""
    assert not tuple((runtime / "adk-runtime" / "worker-workspaces").iterdir())
    snapshot = store.snapshot(mission_id)
    work_attempts = tuple(
        item for item in snapshot.attempts if item.task_id in {"report-a", "report-b"}
    )
    assert len({item.worker_id for item in work_attempts}) == 2
    assert len({item.session_id for item in work_attempts}) == 2
    assert len({item.invocation_id for item in work_attempts}) == 2
    # The throttled first batch ran the two workers one after the other, so
    # the durable timestamps must not claim an overlap that never happened.
    assert result["parallel_overlap_observed"] is False
    assert result["parallel_overlap"]["attempt_count"] == 2

    # Every committed WORK attempt binds exactly one sanitized provider receipt
    # that resolves by digest, parses, and names the fake driver honestly.
    kinds = {item.task_id: item.kind for item in snapshot.tasks}
    evidence = mission_cli._mission_evidence(store, mission_id)
    committed_work = tuple(
        item
        for item in snapshot.attempts
        if kinds[item.task_id] == TaskKind.WORK and item.state == AttemptState.COMMITTED
    )
    assert len(committed_work) == 2
    for attempt in committed_work:
        references = tuple(
            item
            for item in attempt.evidence_refs
            if item.kind == WORKER_PROVIDER_RECEIPT_KIND
        )
        assert len(references) == 1
        content = evidence.resolve(references[0].kind, references[0].id)
        assert content is not None
        assert sha256_hex(content) == references[0].sha256
        receipt = WorkerProviderReceipt.model_validate_json(content)
        assert receipt.driver == "adk_fake"
        assert receipt.requested_model == receipt.returned_model
        record = json.loads(content)
        assert not {"prompt", "output", "api_key"} & set(record)
        text = content.decode("utf-8")
        assert "Create only the first bounded report." not in text
        assert "Create only the second bounded report." not in text
        assert "# Source" not in text
    assert all(
        item.kind != WORKER_PROVIDER_RECEIPT_KIND
        for attempt in snapshot.attempts
        if kinds[attempt.task_id] != TaskKind.WORK
        for item in attempt.evidence_refs
    )
    assert store.verify(mission_id) == snapshot.head
    assert [item["driver"] for item in result["provider_receipts"]] == [
        "adk_fake",
        "adk_fake",
    ]
    assert [item["attempt_id"] for item in result["provider_receipt_references"]] == [
        item.attempt_id for item in committed_work
    ]
    assert all(
        item["kind"] == WORKER_PROVIDER_RECEIPT_KIND
        for item in result["provider_receipt_references"]
    )
    assert result["receipt_unknowns"] == []
    assert result["provider_interruptions"] == []
    assert result["provider_interruption_references"] == []
    assert result["provider_interruption_unknowns"] == []
    assert result["provider_outcome_unknowns"] == []
    assert result["billing_outcome_unknowns"] == []

    # A replayed result rebuilds the receipts from evidence, not from memory.
    replayed = mission_cli._execute_adk_mission(
        store=store,
        mission_id=mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
    )
    assert replayed["result_replayed"] is True
    assert replayed["provider_receipts"] == result["provider_receipts"]
    assert replayed["worker_session_ids"] == result["worker_session_ids"]
    assert replayed["worker_invocation_ids"] == result["worker_invocation_ids"]
    assert (
        replayed["provider_receipt_references"] == result["provider_receipt_references"]
    )
    assert replayed["receipt_unknowns"] == []
    assert replayed["provider_interruptions"] == []
    assert replayed["provider_interruption_references"] == []
    assert replayed["provider_interruption_unknowns"] == []
    assert replayed["provider_outcome_unknowns"] == []
    assert replayed["billing_outcome_unknowns"] == []
    assert replayed["parallel_overlap"] == result["parallel_overlap"]


def test_default_runtime_accepts_multiple_known_sandbox_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(
        tmp_path,
        monkeypatch,
        command_templates=(
            mission_cli.CommandTemplate(
                template_id="fixture-tests",
                argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
                timeout_seconds=60,
            ),
            mission_cli.CommandTemplate(
                template_id="orders-migration-task-check",
                argv=("python", "-m", "orders_api.verify_migration"),
                timeout_seconds=60,
            ),
        ),
    )

    async def passed_check(
        _workspace: Path, assignment: RuntimeAssignment, _attempt_id: str
    ) -> CheckOutcome:
        template = assignment.command_template
        return CheckOutcome(
            template_id=template.template_id,
            template_sha256=canonical_json_sha256(template.model_dump(mode="json")),
            exit_code=0,
            timed_out=False,
            output_sha256="0" * 64,
            output_truncated=False,
            cleanup_complete=True,
        )

    monkeypatch.setattr(
        mission_cli,
        "DockerCheckRunner",
        lambda _executor: passed_check,
    )

    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        resource_sampler=quiet_resource_sampler,
    )

    assert result["status"] == MissionStatus.AWAITING_RESULT


def test_result_replays_bound_provider_interruption_and_explicit_unknowns(
    tmp_path: Path,
) -> None:
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "interruption-evidence.sqlite")
    interruption = WorkerProviderInterruption(
        requested_model="gemini-3.5-flash",
        mission_id="mission-interrupted",
        task_id="work-a",
        attempt_id="attempt-interrupted",
        lease_id="lease-interrupted",
        fencing_token=3,
        request_sha256="a" * 64,
        input_bytes=128,
        sdk_invocation_id="invocation-interrupted",
        dispatched_at="2026-08-27T12:00:00.000Z",
        pid=123,
        pgid=123,
        process_started_at="Thu Aug 27 12:00:00 2026",
        process_birth_token="test:birth:123",
        executable="/usr/bin/python3",
        exit_code=-9,
        signal_name="sigkill",
        stderr_sha256="b" * 64,
        stderr_truncated=False,
    )
    content = canonical_json_bytes(interruption.model_dump(mode="json"))
    reference = evidence.put_artifact(WORKER_PROVIDER_INTERRUPTION_KIND, content)
    task = SimpleNamespace(task_id="work-a", kind=TaskKind.WORK)
    attempt = SimpleNamespace(
        mission_id=interruption.mission_id,
        task_id=interruption.task_id,
        attempt_id=interruption.attempt_id,
        worker_id="worker-live",
        lease_id=interruption.lease_id,
        fencing_token=interruption.fencing_token,
        invocation_id=interruption.sdk_invocation_id,
        result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED.value,
        evidence_refs=(reference,),
    )
    snapshot = SimpleNamespace(
        plan=SimpleNamespace(tasks=(task,)), tasks=(), attempts=(attempt,)
    )

    values, resolution_unknowns, provider_unknowns, billing_unknowns = (
        mission_cli._replayed_provider_interruptions(snapshot, evidence)
    )

    assert values == [interruption.model_dump(mode="json")]
    assert mission_cli._provider_interruption_references(snapshot) == [
        {
            "attempt_id": interruption.attempt_id,
            "worker_id": attempt.worker_id,
            "kind": WORKER_PROVIDER_INTERRUPTION_KIND,
            "id": reference.id,
            "sha256": reference.sha256,
        }
    ]
    assert resolution_unknowns == []
    assert provider_unknowns == [
        "provider outcome for interrupted attempt attempt-interrupted is unknown"
    ]
    assert billing_unknowns == [
        "billing outcome for interrupted attempt attempt-interrupted is unknown"
    ]


def test_live_result_lists_only_evidence_bound_provider_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt whose evidence binding failed is never cited, live or replayed."""

    import sqlite3

    from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
    from graphene.orchestration.worker_runtime import WORKER_PROVIDER_RECEIPT_KIND

    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    original = SQLiteAttemptEvidenceStore.put_artifact
    failures: list[str] = []

    def flaky_put(self, kind, content, **overrides):
        if kind == WORKER_PROVIDER_RECEIPT_KIND and not failures:
            failures.append(kind)
            raise sqlite3.OperationalError("simulated receipt write failure")
        return original(self, kind, content, **overrides)

    monkeypatch.setattr(SQLiteAttemptEvidenceStore, "put_artifact", flaky_put)

    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
        resource_sampler=quiet_resource_sampler,
    )

    assert failures == [WORKER_PROVIDER_RECEIPT_KIND]
    assert result["status"] == "awaiting_result"
    snapshot = prepared.store.snapshot(prepared.mission_id)
    kinds = {task.task_id: task.kind for task in snapshot.plan.tasks}
    work = [item for item in snapshot.attempts if kinds[item.task_id] == TaskKind.WORK]
    unbound = [item for item in work if item.result_code == "runtime_unavailable"]
    assert len(unbound) == 1
    assert not any(
        reference.kind == WORKER_PROVIDER_RECEIPT_KIND
        for reference in unbound[0].evidence_refs
    )
    bound = [item for item in work if item.attempt_id != unbound[0].attempt_id]
    assert len(bound) == 2
    # Only the two evidence-bound receipts are listed; the in-memory receipt of
    # the attempt whose binding failed is not, and nothing is guessed.
    assert len(result["provider_receipts"]) == 2
    assert {item["attempt_id"] for item in result["provider_receipt_references"]} == {
        item.attempt_id for item in bound
    }
    assert result["receipt_unknowns"] == []
    assert prepared.store.verify(prepared.mission_id) == snapshot.head

    replayed = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
    )
    assert replayed["result_replayed"] is True
    assert replayed["provider_receipts"] == result["provider_receipts"]
    assert replayed["worker_session_ids"] == result["worker_session_ids"]


def test_orders_migration_survives_a_root_failure_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_GENAI_USE_VERTEXAI",
    ):
        monkeypatch.delenv(name, raising=False)

    target = materialize(tmp_path / "orders-source")
    repository = target.repository
    expected_changed = (
        "orders_api/api.py",
        "orders_api/request_models.py",
        "orders_api/response_models.py",
        "requirements.in",
        "requirements.lock",
    )
    assert target.policy.allowed_write_globs == expected_changed
    source_head = _git(repository, "rev-parse", "HEAD")
    source_status = _git(repository, "status", "--porcelain=v1")
    source_bytes = {
        path: (repository / path).read_bytes()
        for path in target.policy.allowed_write_globs
    }
    state = tmp_path / "state"
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    goal, raw_criteria = load_goal()
    criteria = tuple(sorted(raw_criteria))
    args = argparse.Namespace(
        repo=repository,
        goal=goal,
        success_criteria=list(criteria),
        driver="gemini-adk",
        max_workers=2,
        auto_approve=False,
        command_id="command_orders_no_key_runtime_0001",
        open_viewer=False,
        authorization_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
        finalization_mode=FinalizationMode.AUTO_FINALIZE_ISOLATED,
        demo_injected_check_fault=False,
    )
    command_id, mission_id, _root, _head, policy, binding = mission_cli._start_identity(
        args
    )
    runtime = mission_cli._mission_runtime(mission_id)
    runtime.mkdir(mode=0o700, parents=True)
    mission_cli._bind_start_request(runtime, binding)
    ids = {criterion: criterion_id(criterion) for criterion in criteria}
    immutable = next(item for item in criteria if item.startswith("The immutable"))
    request = next(item for item in criteria if item.startswith("orders_api/request"))
    response = next(item for item in criteria if item.startswith("orders_api/response"))
    dependencies = next(item for item in criteria if item.startswith("requirements.in"))
    template_id = policy.command_templates[1].template_id
    planning_request = PlanningRequest(
        mission_id=mission_id,
        revision=1,
        goal=goal,
        success_criteria=criteria,
        repository_manifest=tuple(
            sorted(
                path.relative_to(repository).as_posix()
                for path in repository.rglob("*")
                if path.is_file()
                and ".git" not in path.parts
                and ".graphene" not in path.parts
            )
        ),
    )
    plan = compile_plan_intent(
        policy,
        planning_request,
        PlanIntent(
            mission_id=mission_id,
            revision=1,
            tasks=(
                WorkIntent(
                    task_id="dependency-declarations",
                    title="Freeze native Pydantic dependency declarations",
                    contract="Write only the exact final requirements files.",
                    criterion_ids=tuple(sorted((ids[dependencies], ids[immutable]))),
                    dependencies=("request-migration", "response-migration"),
                    assigned_role="worker",
                    read_paths=tuple(
                        sorted(
                            (
                                "orders_api/api.py",
                                "orders_api/request_models.py",
                                "orders_api/response_models.py",
                                "requirements.in",
                                "requirements.lock",
                                "tests/test_migration_contract.py",
                            )
                        )
                    ),
                    write_paths=("requirements.in", "requirements.lock"),
                    command_template_id=template_id,
                ),
                WorkIntent(
                    task_id="request-migration",
                    title="Migrate request validation",
                    contract="Migrate request validation and its API call site.",
                    criterion_ids=tuple(sorted((ids[immutable], ids[request]))),
                    assigned_role="worker",
                    read_paths=(
                        "orders_api/api.py",
                        "orders_api/request_models.py",
                        "tests/test_api.py",
                        "tests/test_models.py",
                    ),
                    write_paths=(
                        "orders_api/api.py",
                        "orders_api/request_models.py",
                    ),
                    command_template_id=template_id,
                ),
                WorkIntent(
                    task_id="response-migration",
                    title="Migrate response serialization",
                    contract="Migrate response configuration and serialization.",
                    criterion_ids=tuple(sorted((ids[immutable], ids[response]))),
                    assigned_role="worker",
                    read_paths=(
                        "orders_api/response_models.py",
                        "tests/test_api.py",
                        "tests/test_models.py",
                    ),
                    write_paths=("orders_api/response_models.py",),
                    command_template_id=template_id,
                ),
            ),
        ),
    )
    now = datetime.now(UTC)
    store = mission_cli._store()
    store.create_mission(
        policy,
        Mission(
            schema_version=2,
            requested_authorization_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
            requested_finalization_mode=FinalizationMode.AUTO_FINALIZE_ISOLATED,
            mission_id=mission_id,
            policy_id=policy.policy_id,
            policy_revision=policy.revision,
            repo_id=policy.repo_id,
            base_sha=policy.base_sha,
            goal=goal,
            success_criteria=criteria,
            plan_revision=1,
            creation_source="operator",
            resource_budget=policy.resource_budget,
            created_at=now,
        ),
        plan,
        "create_orders_no_key_runtime_0001",
        recorded_at=now,
    )
    decision = evaluate_plan_policy(
        policy,
        plan,
        goal_request_id=command_id,
        requested_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
        requested_finalization_mode=FinalizationMode.AUTO_FINALIZE_ISOLATED,
    )
    store.record_plan_policy_decision(
        mission_id,
        "authorize_orders_no_key_runtime_0001",
        decision,
        expected_head=store.head(mission_id),
        recorded_at=datetime.now(UTC),
    )

    def changed(path: str, *replacements: tuple[str, str]) -> str:
        text = (repository / path).read_text(encoding="utf-8")
        for old, new in replacements:
            assert old in text
            text = text.replace(old, new)
        return text

    request_mutations = (
        FileMutation(
            operation="update",
            path="orders_api/request_models.py",
            text=changed(
                "orders_api/request_models.py",
                (
                    "from pydantic.v1 import BaseModel, Field, validator",
                    "from pydantic import BaseModel, ConfigDict, Field, field_validator",
                ),
                ("regex=", "pattern="),
                (
                    '@validator("sku", pre=True)\n    def normalize_sku',
                    '@field_validator("sku", mode="before")\n'
                    "    @classmethod\n"
                    "    def normalize_sku",
                ),
                (
                    "items: list[OrderItem] = Field(min_items=1)",
                    "items: list[OrderItem] = Field(min_length=1)",
                ),
                (
                    '    class Config:\n        extra = "forbid"',
                    '    model_config = ConfigDict(extra="forbid")',
                ),
            ),
        ),
        FileMutation(
            operation="update",
            path="orders_api/api.py",
            text=changed(
                "orders_api/api.py",
                (
                    "CreateOrder.parse_obj(payload)",
                    "CreateOrder.model_validate(payload)",
                ),
            ),
        ),
    )
    response_mutations = (
        FileMutation(
            operation="update",
            path="orders_api/response_models.py",
            text=changed(
                "orders_api/response_models.py",
                (
                    "from pydantic.v1 import BaseModel",
                    "from pydantic import BaseModel, ConfigDict",
                ),
                (
                    "    class Config:\n        allow_mutation = False",
                    "    model_config = ConfigDict(frozen=True)",
                ),
                ("response.dict()", 'response.model_dump(mode="json")'),
            ),
        ),
    )
    dependency_mutations = (
        FileMutation(
            operation="update",
            path="requirements.in",
            text="pydantic==2.13.4\n",
        ),
        FileMutation(
            operation="update",
            path="requirements.lock",
            text=(
                "# Native Pydantic v2 runtime resolved from requirements.in.\n"
                "pydantic==2.13.4\n"
            ),
        ),
    )
    routed = {
        "Migrate request validation and its API call site.": request_mutations,
        "Migrate response configuration and serialization.": response_mutations,
        "Write only the exact final requirements files.": dependency_mutations,
    }
    original_generate = DeterministicWorkerModel.generate_content_async

    async def generate_for_assignment(self, llm_request, stream=False):  # type: ignore[no-untyped-def]
        prompt = "".join(
            part.text or ""
            for content in llm_request.contents
            for part in content.parts or ()
        )
        matches = [
            mutations for marker, mutations in routed.items() if marker in prompt
        ]
        assert len(matches) == 1, prompt
        self.bind(matches[0])
        async for response_value in original_generate(self, llm_request, stream):
            yield response_value

    monkeypatch.setattr(
        DeterministicWorkerModel,
        "generate_content_async",
        generate_for_assignment,
    )
    models = (
        DeterministicWorkerModel(model="orders-fixture-worker-a"),
        DeterministicWorkerModel(model="orders-fixture-worker-b"),
    )
    for model in models:
        model.bind(request_mutations)
    registry = WorkerRegistry(
        tuple(
            GeminiWorkerAdapter.fake(worker_id=f"orders-fake-{index}", model=model)
            for index, model in enumerate(models, 1)
        )
    )

    async def frozen_target_check(
        workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        del owner_id
        completed = await asyncio.to_thread(
            subprocess.run,
            (sys.executable, *_FIXED_TEST_COMMAND[1:]),
            cwd=workspace,
            env=_sanitized_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=assignment.command_template.timeout_seconds,
            check=False,
        )
        output = completed.stdout
        return CheckOutcome(
            template_id=assignment.command_template.template_id,
            template_sha256=sha256_hex(
                canonical_json_bytes(
                    assignment.command_template.model_dump(mode="json")
                )
            ),
            exit_code=completed.returncode,
            timed_out=False,
            output_sha256=sha256_hex(output),
            output_truncated=False,
            cleanup_complete=True,
        )

    injected = mission_cli._DemoOneShotCheckRunner(frozen_target_check, runtime)

    def wait_for_response_acceptance() -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            sibling = next(
                item
                for item in store.snapshot(mission_id).tasks
                if item.task_id == "response-migration"
            )
            if sibling.state == TaskState.DONE:
                return
            time.sleep(0.01)
        raise AssertionError("response sibling was not accepted before injected fault")

    async def ordered_fault_check(
        workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        if assignment.task_id != "request-migration":
            return await frozen_target_check(workspace, assignment, owner_id)
        if not (runtime / "demo-check-fault.json").exists():
            await asyncio.to_thread(wait_for_response_acceptance)
        return await injected(workspace, assignment, owner_id)

    result = mission_cli._execute_adk_mission(
        store=store,
        mission_id=mission_id,
        registry=registry,
        check_runner=ordered_fault_check,
        resource_sampler=quiet_resource_sampler,
    )

    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert result["execution_mode"] == "adk_fake"
    assert result["review_required"] is False
    assert result["effective_authorization_mode"] == "policy_pre_authorized"
    assert result["finalization_mode"] == "auto_finalize_isolated"
    assert result["dispatch_batches"][0] == ["request-migration", "response-migration"]
    snapshot = store.snapshot(mission_id)
    attempts = {
        task_id: tuple(
            sorted(
                (item for item in snapshot.attempts if item.task_id == task_id),
                key=lambda item: item.attempt_number,
            )
        )
        for task_id in ("request-migration", "response-migration")
    }
    assert [item.state for item in attempts["request-migration"]] == [
        AttemptState.FAILED,
        AttemptState.COMMITTED,
    ]
    assert [item.state for item in attempts["response-migration"]] == [
        AttemptState.COMMITTED
    ]
    events = store.tail(mission_id, 0, 256)
    sibling_accept = next(
        event.seq
        for event in events
        if event.event_type == MissionEventType.ARTIFACT_ACCEPTED
        and event.payload.get("task_id") == "response-migration"
    )
    injected_retry = next(
        event.seq
        for event in events
        if event.event_type == MissionEventType.TASK_RETRIED
        and event.payload.get("task_id") == "request-migration"
    )
    assert sibling_accept < injected_retry
    evidence = mission_cli._mission_evidence(store, mission_id)
    bundle_event = next(
        event
        for event in reversed(events)
        if event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    )
    bundle_reference = next(
        item for item in bundle_event.references if item.kind == "final-result-bundle"
    )
    bundle_bytes = evidence.resolve(bundle_reference.kind, bundle_reference.id)
    assert bundle_bytes is not None
    bundle = FinalResultBundleV2.model_validate_json(bundle_bytes)
    assert bundle.changed_paths == expected_changed
    assert bundle.verification_receipt.exit_code == 0
    assert bundle.verification_receipt.result_code == "passed"
    assert bundle.verification_receipt.timed_out is False
    assert bundle.operator_decision.state == "pending"
    assert _git(repository, "rev-parse", "HEAD") == source_head
    assert _git(repository, "status", "--porcelain=v1") == source_status
    assert {
        path: (repository / path).read_bytes()
        for path in target.policy.allowed_write_globs
    } == source_bytes
