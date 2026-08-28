"""Deterministic failure laboratory on the Gemini/ADK path.

Choreography (mirrors directive A2 steps 1-6 with fake ADK workers and the
macOS host-sandbox check runner):

* two independent WORK tasks (report-a, report-b) plus deterministic
  assembly and verification, dispatched to two fake Gemini workers;
* worker A's attempt completes and its publication is accepted;
* worker B's first attempt holds a live lease when its check subprocess --
  the strongly identified Graphene-owned process on this path -- is SIGKILLed
  through the owned-process registry record;
* B's attempt fails without publishing, A's publication survives untouched,
  dependents stay blocked, the scheduler re-dispatches B's task as attempt 2
  under a strictly higher fence, the stale fence can no longer publish, the
  mission reaches ``awaiting_result``, the event chain verifies, and
  ``graphene why`` names the retry as the producer.

This legacy choreography still kills a check subprocess and is not live-model
proof. Separate tests below exercise the barrier-bound model-child contract.
Retry is automatic: ``complete_attempt`` marks a retryable failure's task
``retrying`` and the scheduler's next tick claims it again.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import PrivateAttr

from graphene.cli import mission as mission_cli
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.mission_models import (
    AttemptResult,
    AttemptState,
    CommandTemplate,
    Dispatch,
    MissionEventType,
    MissionStatus,
    PublicationDraft,
    PublicationState,
    PublishedArtifactReferenceV2,
    TaskKind,
    TaskState,
)
from graphene.orchestration.process_control import (
    OwnedProcessRegistry,
    ProcessControlError,
)
from graphene.orchestration.worker_runtime import (
    WORKER_PROVIDER_RECEIPT_KIND,
    WorkerProviderReceipt,
    WorkerRegistry,
)
from graphene.orchestration.sqlite_mission_store import StaleWorker
from graphene.orchestration.workers import (
    DeterministicWorkerModel,
    FileMutation,
    GeminiWorkerAdapter,
)
from tests.unit.orchestration.test_gemini_mission_runtime import (
    prepare_fake_two_worker_mission,
    quiet_resource_sampler,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "failure_lab.py"
DARWIN_SANDBOX = pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="failure laboratory requires the macOS host-sandbox check runner",
)
PROCESS_TOOLS = pytest.mark.skipif(
    not (Path("/bin/ps").is_file() and Path("/bin/sleep").is_file()),
    reason="owned-process records require /bin/ps and a /bin/sleep child",
)
FIXTURE_TESTS = CommandTemplate(
    template_id="fixture-tests",
    argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
    timeout_seconds=15,
)
PASSING_TEST = "def test_ok() -> None:\n    assert True\n"
REPORT_A = ".graphene/generated/a.txt"
REPORT_B = ".graphene/generated/b.txt"
SIBLING_WAIT_SECONDS = 30


def _load_failure_lab() -> ModuleType:
    name = "failure_lab_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _git_status(repository: Path) -> str:
    return subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()


class _TaskAwareFakeModel(DeterministicWorkerModel):
    """Fake ADK model that answers for whichever leased write path the prompt names.

    The scheduler hands report-b's retry to the Gemini worker with the fewest
    attempts, which is worker A once B has failed, so both fake workers must be
    able to produce either report. Before answering, the model awaits ``gate``
    for the leased path so the choreography can require that report A's
    publication is already accepted when B's check is killed.
    """

    _by_path: dict[str, FileMutation] = PrivateAttr(default_factory=dict)
    _gate: Callable[[str], Awaitable[None]] | None = PrivateAttr(default=None)

    def bind_paths(
        self,
        mutations: dict[str, FileMutation],
        *,
        gate: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._by_path = dict(mutations)
        self._gate = gate

    async def generate_content_async(self, llm_request, stream=False):  # type: ignore[override]
        prompt = "".join(
            part.text or ""
            for content in llm_request.contents
            for part in content.parts or ()
        )
        leased = [path for path in self._by_path if path in prompt]
        assert len(leased) == 1, leased
        self.bind((self._by_path[leased[0]],))
        if self._gate is not None:
            await self._gate(leased[0])
        async for response in super().generate_content_async(llm_request, stream):
            yield response


def _sibling_accepted_gate(store, mission_id: str, *, gated_path: str, sibling: str):
    async def gate(path: str) -> None:
        if path != gated_path:
            return
        deadline = time.monotonic() + SIBLING_WAIT_SECONDS
        while True:
            snapshot = await asyncio.to_thread(store.snapshot, mission_id)
            if any(
                item.task_id == sibling and item.state == PublicationState.ACCEPTED
                for item in snapshot.publications
            ):
                return
            assert time.monotonic() < deadline, f"{sibling} was never accepted"
            await asyncio.sleep(0.05)

    return gate


def _dispatch(mission_id: str, attempt_id: str, worker_id: str) -> Dispatch:
    return Dispatch(
        mission_id=mission_id,
        plan_revision=1,
        plan_sha256="0" * 64,
        task_id="work-a",
        task_kind=TaskKind.WORK,
        attempt_id=attempt_id,
        attempt_number=1,
        worker_id=worker_id,
        workspace_id="workspace-a",
        lease_id="lease-a",
        fencing_token=1,
        dispatch_command_id="dispatch-command-lab-0001",
        write_paths=(),
        allowed_commands=("fixture-tests",),
        acceptance_checks=("fixture-tests",),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


@DARWIN_SANDBOX
def test_sigkilled_second_worker_retries_under_higher_fence_without_touching_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lab = _load_failure_lab()
    prepared = prepare_fake_two_worker_mission(
        tmp_path,
        monkeypatch,
        command_templates=(FIXTURE_TESTS,),
        extra_files={"tests/test_ok.py": PASSING_TEST},
    )
    monkeypatch.setenv("GRAPHENE_CHECK_EXECUTOR", "host-sandbox")
    store = prepared.store
    mission_id = prepared.mission_id
    gate = _sibling_accepted_gate(
        store, mission_id, gated_path=REPORT_B, sibling="report-a"
    )
    mutations = {
        REPORT_A: FileMutation(
            operation="create", path=REPORT_A, text="alpha\n", mode="100644"
        ),
        REPORT_B: FileMutation(
            operation="create", path=REPORT_B, text="beta\n", mode="100644"
        ),
    }
    model_a = _TaskAwareFakeModel(model="fixture-worker-a")
    model_a.bind_paths(mutations, gate=gate)
    model_b = _TaskAwareFakeModel(model="fixture-worker-b")
    model_b.bind_paths(mutations, gate=gate)
    registry = WorkerRegistry(
        (
            GeminiWorkerAdapter.fake(worker_id="fake-a", model=model_a),
            GeminiWorkerAdapter.fake(worker_id="fake-b", model=model_b),
        )
    )
    gemini_worker_ids = tuple(item.worker_id for item in registry.capabilities())
    worker_a, worker_b = gemini_worker_ids
    assert worker_b == "fake-b"

    laboratory: dict[str, object] = {}
    hook_errors: list[BaseException] = []
    original_record = OwnedProcessRegistry.record

    def kill_second_worker_first_check(self, dispatch, process, executable) -> None:
        original_record(self, dispatch, process, executable)
        if not (
            dispatch.worker_id == worker_b
            and dispatch.attempt_number == 1
            and dispatch.task_kind == TaskKind.WORK
        ):
            return
        try:
            assert "dispatch" not in laboratory, "the laboratory kills exactly once"
            assert self.directory == prepared.runtime / "processes"
            # The kill target comes from the durable registry record that
            # `record` just bound to this child (pid == pgid, alive, group
            # leader), never from a name. The registered /bin/sh launch barrier
            # later replaces its image with sandbox-exec and the frozen command;
            # identity remains the same pid/group/birth token throughout.
            owned = lab.record_for_attempt(self, dispatch.attempt_id)
            assert owned is not None
            assert owned.mission_id == mission_id
            assert owned.attempt_id == dispatch.attempt_id
            assert owned.pid == owned.pgid == process.pid
            assert executable == "/bin/sh"
            assert process.poll() is None
            snapshot = store.snapshot(mission_id)
            accepted = [
                item
                for item in snapshot.publications
                if item.task_id == "report-a"
                and item.state == PublicationState.ACCEPTED
            ]
            assert len(accepted) == 1, "A must be accepted before B is killed"
            running = next(
                item
                for item in snapshot.attempts
                if item.attempt_id == dispatch.attempt_id
            )
            assert running.state == AttemptState.RUNNING
            assert running.fencing_token == dispatch.fencing_token
            lease = next(
                item
                for item in snapshot.leases
                if item.attempt_id == dispatch.attempt_id
            )
            assert lease.released_at is None
            assert lease.expires_at > datetime.now(UTC), "B must hold a live lease"
            downstream = {
                item.task_id: item
                for item in snapshot.tasks
                if item.kind != TaskKind.WORK
            }
            assert downstream
            assert all(
                item.state in {TaskState.QUEUED, TaskState.BLOCKED}
                for item in downstream.values()
            )
            assert not any(item.task_id in downstream for item in snapshot.attempts)
            # This legacy fixture exercises check-stage retry directly. The
            # operator-facing failure laboratory now targets only live Gemini
            # children after their provider-dispatch barrier.
            self.signal(dispatch, signal.SIGKILL)
            laboratory.update(
                dispatch=dispatch,
                owned=owned,
                publication=accepted[0],
                killed_at=datetime.now(UTC),
            )
        except BaseException as error:  # surfaced after the run, never hidden
            hook_errors.append(error)

    monkeypatch.setattr(OwnedProcessRegistry, "record", kill_second_worker_first_check)

    result = mission_cli._execute_adk_mission(
        store=store,
        mission_id=mission_id,
        registry=registry,
        resource_sampler=quiet_resource_sampler,
    )

    assert not hook_errors, hook_errors
    assert "dispatch" in laboratory, "worker B's first check was never registered"
    stale: Dispatch = laboratory["dispatch"]  # type: ignore[assignment]
    assert stale.task_id == "report-b"
    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert result["dispatch_batches"][:2] == [["report-a", "report-b"], ["report-b"]]
    assert result["parallel_overlap_observed"] is True
    assert result["parallel_overlap"]["max_window_ms"] > 0
    snapshot = store.snapshot(mission_id)
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert store.verify(mission_id) == snapshot.head
    kinds = {item.task_id: item.kind for item in snapshot.tasks}
    evidence = mission_cli._mission_evidence(store, mission_id)

    # Step 1: B's first attempt terminated FAILED with no publication, and the
    # trusted check receipt minted by the runner records the kill signal.
    b_attempts = sorted(
        (item for item in snapshot.attempts if item.task_id == "report-b"),
        key=lambda item: item.attempt_number,
    )
    assert [item.attempt_number for item in b_attempts] == [1, 2]
    failed, retry = b_attempts
    assert failed.attempt_id == stale.attempt_id
    assert failed.worker_id == worker_b
    assert failed.state == AttemptState.FAILED
    assert failed.result_code == "acceptance_check_failed"
    assert failed.ended_at is not None
    assert failed.fencing_token == stale.fencing_token
    assert not any(
        item.attempt_id == failed.attempt_id for item in snapshot.publications
    )
    failed_receipts = [
        item for item in failed.evidence_refs if item.kind == "test-receipt"
    ]
    assert len(failed_receipts) == 1
    content = evidence.resolve(failed_receipts[0].kind, failed_receipts[0].id)
    assert content is not None
    receipt = TrustedCheckReceipt.model_validate_json(content)
    assert receipt.attempt_id == failed.attempt_id
    assert receipt.fencing_token == stale.fencing_token
    assert receipt.exit_code == -int(signal.SIGKILL)
    assert receipt.timed_out is False
    assert receipt.result_code == "acceptance_check_failed"
    failed_lease = next(
        item for item in snapshot.leases if item.attempt_id == failed.attempt_id
    )
    assert failed_lease.released_at is not None
    assert failed_lease.release_reason == "failed"
    assert failed_lease.fencing_token == stale.fencing_token

    # Step 2: A's accepted publication row is byte-for-byte unchanged.
    before = laboratory["publication"]
    after = next(
        item
        for item in snapshot.publications
        if item.publication_id == before.publication_id  # type: ignore[attr-defined]
    )
    assert after == before
    assert after.state == PublicationState.ACCEPTED
    a_attempt = next(item for item in snapshot.attempts if item.task_id == "report-a")
    assert a_attempt.worker_id == worker_a
    assert a_attempt.state == AttemptState.COMMITTED
    assert after.attempt_id == a_attempt.attempt_id
    assert after.paths == (REPORT_A,)

    # Step 4: bounded recovery re-dispatched B's task as attempt 2 under a
    # strictly higher fence, and that replacement is what published.
    assert retry.attempt_id != failed.attempt_id
    assert retry.attempt_number == 2
    assert retry.fencing_token > stale.fencing_token
    assert retry.state == AttemptState.COMMITTED
    assert retry.worker_id in gemini_worker_ids
    assert retry.started_at >= failed.ended_at
    retry_lease = next(
        item for item in snapshot.leases if item.attempt_id == retry.attempt_id
    )
    assert retry_lease.fencing_token == retry.fencing_token > failed_lease.fencing_token
    assert retry_lease.release_reason == "completed"
    retry_publication = next(
        item for item in snapshot.publications if item.attempt_id == retry.attempt_id
    )
    assert retry_publication.state == PublicationState.ACCEPTED
    assert retry_publication.paths == (REPORT_B,)
    assert retry_publication.publication_id != after.publication_id

    # Step 3: descendants waited for the retry; nothing downstream consumed
    # anything from the killed attempt.
    downstream_attempts = [
        item for item in snapshot.attempts if kinds[item.task_id] != TaskKind.WORK
    ]
    assert {kinds[item.task_id] for item in downstream_attempts} == {
        TaskKind.ASSEMBLY,
        TaskKind.VERIFICATION,
    }
    assert all(item.started_at >= retry.started_at for item in downstream_attempts)
    assert all(item.state == AttemptState.COMMITTED for item in downstream_attempts)
    assembly = next(
        item for item in downstream_attempts if kinds[item.task_id] == TaskKind.ASSEMBLY
    )
    assert {
        item.publication_id
        for item in assembly.input_publications
        if isinstance(item, PublishedArtifactReferenceV2)
    } == {after.publication_id, retry_publication.publication_id}
    events = mission_cli._mission_events(store, mission_id, snapshot.head.event_count)
    assert [
        (event.payload["task_id"], event.payload["attempt_id"])
        for event in events
        if event.event_type == MissionEventType.TASK_RETRIED
    ] == [("report-b", failed.attempt_id)]
    assert not any(event.event_type == MissionEventType.TASK_FAILED for event in events)
    assert [
        event.payload["attempt_id"]
        for event in events
        if event.event_type == MissionEventType.DEPENDENCY_SATISFIED
        and event.payload["dependency_id"] == "report-b"
    ] == [retry.attempt_id] * sum(
        "report-b" in item.dependencies for item in snapshot.tasks
    )
    assert failed.attempt_id not in {
        event.payload["attempt_id"]
        for event in events
        if event.event_type
        in {MissionEventType.ARTIFACT_PUBLISHED, MissionEventType.ARTIFACT_ACCEPTED}
    }

    # Step 4 (continued): the stale fence can neither be asserted nor publish.
    head_before = store.head(mission_id)
    with pytest.raises(StaleWorker):
        store.assert_fence(stale, recorded_at=datetime.now(UTC))
    assert retry_publication.artifact is not None
    stale_publication = AttemptResult(
        succeeded=True,
        result_code="passed",
        session_id=retry.session_id,
        invocation_id=retry.invocation_id,
        evidence_link=retry.evidence_link,
        evidence_refs=retry.evidence_refs,
        artifact_envelopes=(retry_publication.artifact,),
        publications=(
            PublicationDraft(
                output_name=retry_publication.output_name,
                kind=retry_publication.kind,
                sha256=retry_publication.sha256,
                artifact=retry_publication.artifact,
                visibility=retry_publication.visibility,
                paths=retry_publication.paths,
            ),
        ),
    )
    with pytest.raises(StaleWorker):
        store.complete_attempt(
            mission_id,
            stale.attempt_id,
            stale.worker_id,
            stale.lease_id,
            stale.fencing_token,
            stale_publication,
            "complete_stale_fence_failure_lab_0001",
            recorded_at=datetime.now(UTC),
            retry_backoff_seconds=0,
        )
    assert store.head(mission_id) == head_before
    assert store.verify(mission_id) == head_before
    assert store.snapshot(mission_id).publications == snapshot.publications

    # Every WORK attempt, the killed one included, binds one sanitized
    # provider receipt that resolves by digest and names the fake driver.
    work_attempts = [
        item for item in snapshot.attempts if kinds[item.task_id] == TaskKind.WORK
    ]
    assert {item.attempt_id for item in work_attempts} == {
        a_attempt.attempt_id,
        failed.attempt_id,
        retry.attempt_id,
    }
    for attempt in work_attempts:
        references = [
            item
            for item in attempt.evidence_refs
            if item.kind == WORKER_PROVIDER_RECEIPT_KIND
        ]
        assert len(references) == 1
        raw = evidence.resolve(references[0].kind, references[0].id)
        assert raw is not None
        assert WorkerProviderReceipt.model_validate_json(raw).driver == "adk_fake"
    assert len(result["provider_receipts"]) == 3
    assert result["receipt_unknowns"] == []

    # Step 6: `graphene why` on B's path names the retry as producer, carries
    # its fence and attempt number, and B's task history holds both attempts.
    why_b = mission_cli._why_value(
        argparse.Namespace(mission_id=mission_id, path=REPORT_B)
    )
    assert why_b["matched_by"] == "path"
    producer = next(
        link for link in why_b["links"] if link["stage"] == "producer_attempt"
    )
    assert producer["status"] == "established"
    producer_nodes = [
        node for node in producer["nodes"] if node["node_type"] == "attempt"
    ]
    assert [node["node_id"] for node in producer_nodes] == [retry.attempt_id]
    assert producer_nodes[0]["attempt_number"] == 2
    assert producer_nodes[0]["fencing_token"] == retry.fencing_token
    assert producer_nodes[0]["worker_id"] == retry.worker_id
    assert producer["event_ids"]
    # The killed attempt is part of the explanation, but only as history:
    # it sits in prior_attempts with its outcome and lower fence, never as
    # the producer or target of anything.
    prior = next(link for link in why_b["links"] if link["stage"] == "prior_attempts")
    assert prior["status"] == "established"
    prior_nodes = [node for node in prior["nodes"] if node["node_type"] == "attempt"]
    assert [node["node_id"] for node in prior_nodes] == [failed.attempt_id]
    assert prior_nodes[0]["state"] == "failed"
    assert prior_nodes[0]["result_code"] == "acceptance_check_failed"
    assert prior_nodes[0]["fencing_token"] == stale.fencing_token < retry.fencing_token
    assert any(node["kind"] == "test-receipt" for node in prior["nodes"])
    assert prior["event_ids"]
    for link in why_b["links"]:
        if link["stage"] != "prior_attempts":
            assert failed.attempt_id not in json.dumps(link)
    assert {
        item.attempt_id for item in snapshot.attempts if item.task_id == "report-b"
    } == {
        failed.attempt_id,
        retry.attempt_id,
    }
    why_a = mission_cli._why_value(
        argparse.Namespace(mission_id=mission_id, path=REPORT_A)
    )
    producer_a = next(
        link for link in why_a["links"] if link["stage"] == "producer_attempt"
    )
    producer_a_nodes = [
        node for node in producer_a["nodes"] if node["node_type"] == "attempt"
    ]
    assert [node["node_id"] for node in producer_a_nodes] == [a_attempt.attempt_id]
    assert producer_a_nodes[0]["attempt_number"] == 1
    assert producer_a_nodes[0]["worker_id"] == worker_a

    # No owned process outlives the mission; the source checkout is untouched.
    assert OwnedProcessRegistry(prepared.runtime).records_for_mission(mission_id) == ()
    assert _git_status(prepared.repository) == prepared.source_status
    assert not (prepared.repository / ".graphene/generated").exists()

    # The operator script sees the same finished mission: nothing to list, and
    # a kill of the committed retry is refused because no record exists.
    stdout, stderr = io.StringIO(), io.StringIO()
    assert lab.main(["list", mission_id], stdout=stdout, stderr=stderr) == 0
    assert json.loads(stdout.getvalue()) == []
    assert stderr.getvalue() == ""
    stdout, stderr = io.StringIO(), io.StringIO()
    assert (
        lab.main(
            [
                "kill",
                mission_id,
                "--attempt",
                retry.attempt_id,
                "--actor-label",
                "recovery-test",
            ],
            stdout=stdout,
            stderr=stderr,
        )
        == 2
    )
    assert stdout.getvalue() == ""
    assert stderr.getvalue().strip() == (
        f"refused: no owned-process record exists for attempt {retry.attempt_id}"
    )


@PROCESS_TOOLS
def test_failure_lab_script_lists_by_mission_and_refuses_foreign_or_unleased_kills(
    tmp_path: Path,
) -> None:
    lab = _load_failure_lab()
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    foreign = _dispatch("mission-foreign", "attempt-foreign", "worker-foreign")
    process = subprocess.Popen(
        ("/bin/sleep", "30"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        registry.record(foreign, process, "/bin/sleep")

        listed = lab.list_records(
            registry, "mission-foreign", {"attempt-foreign": "worker-foreign"}
        )
        assert len(listed) == 1
        assert listed[0]["attempt_id"] == "attempt-foreign"
        assert listed[0]["mission_id"] == "mission-foreign"
        assert listed[0]["worker_id"] == "worker-foreign"
        assert listed[0]["pid"] == listed[0]["pgid"] == process.pid
        assert isinstance(listed[0]["started_at"], str) and listed[0]["started_at"]
        assert listed[0]["executable"].endswith("sleep")
        assert lab.list_records(registry, "mission-lab", {}) == []
        assert lab.list_records(registry, "mission-foreign", {})[0]["worker_id"] is None

        # A record owned by another mission is never signalled.
        with pytest.raises(
            lab.FailureLabError,
            match=(
                "^refused: owned-process record for attempt attempt-foreign belongs "
                "to mission mission-foreign, not mission-lab$"
            ),
        ):
            lab.kill_model_attempt(
                registry,
                "mission-lab",
                "attempt-foreign",
                _dispatch("mission-lab", "attempt-foreign", "worker-lab"),
            )
        assert process.poll() is None
        # No record at all, and a record without a live lease, are refused too.
        with pytest.raises(
            lab.FailureLabError,
            match="^refused: no owned-process record exists for attempt attempt-none$",
        ):
            lab.kill_model_attempt(registry, "mission-foreign", "attempt-none", None)
        with pytest.raises(
            lab.FailureLabError,
            match=(
                "^refused: attempt attempt-foreign is not running under a live "
                "lease in mission mission-foreign$"
            ),
        ):
            lab.kill_model_attempt(registry, "mission-foreign", "attempt-foreign", None)
        with pytest.raises(lab.FailureLabError, match="not running under a live lease"):
            lab.kill_model_attempt(
                registry,
                "mission-foreign",
                "attempt-foreign",
                _dispatch("mission-foreign", "attempt-other", "worker-foreign"),
            )
        assert process.poll() is None
        assert registry.records_for_mission("mission-foreign")[0].pid == process.pid
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


@PROCESS_TOOLS
def test_failure_lab_kills_only_a_barrier_bound_model_child(tmp_path: Path) -> None:
    lab = _load_failure_lab()
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    dispatch = _dispatch("mission-lab", "attempt-model", "worker-live")
    process = subprocess.Popen(
        ("/bin/sleep", "30"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    reaper: threading.Thread | None = None
    try:
        registry.record(dispatch, process, "/bin/sleep")
        with pytest.raises(
            lab.FailureLabError, match="has no acknowledged model dispatch"
        ):
            lab.kill_model_attempt(
                registry, dispatch.mission_id, dispatch.attempt_id, dispatch
            )
        assert process.poll() is None

        owned = registry.validate(dispatch)
        registry.acknowledge_model_dispatch(
            dispatch,
            owned,
            request_sha256="a" * 64,
            sdk_invocation_id="invocation-model-1",
            dispatched_at="2026-08-27T12:00:00.000Z",
        )
        with pytest.raises(lab.FailureLabError, match="actor label is invalid"):
            lab.kill_model_attempt(
                registry,
                dispatch.mission_id,
                dispatch.attempt_id,
                dispatch,
                actor_label="not valid/actor",
            )
        assert process.poll() is None
        reaper = threading.Thread(target=process.wait)
        reaper.start()
        result = lab.kill_model_attempt(
            registry,
            dispatch.mission_id,
            dispatch.attempt_id,
            dispatch,
            actor_label="recovery-test",
        )
        reaper.join(timeout=5)
        assert not reaper.is_alive()

        assert process.returncode == -int(signal.SIGKILL)
        assert result["stage"] == "model"
        assert result["pid"] == result["pgid"] == process.pid
        assert result["request_sha256"] == "a" * 64
        assert result["sdk_invocation_id"] == "invocation-model-1"
        assert result["fencing_token"] == dispatch.fencing_token
        assert result["actor_label"] == "recovery-test"
        assert result["observed_process_state"] == "not_running"
        assert result["record_type"] == "signal_observed"
        record = (
            tmp_path
            / "runtime"
            / "failure-injections"
            / f"{result['injection_record_sha256']}.json"
        )
        assert record.read_bytes() == canonical_json_bytes(
            {
                key: value
                for key, value in result.items()
                if key != "injection_record_sha256"
            }
        )
        request_record = record.with_name(
            f"{result['signal_request_record_sha256']}.json"
        )
        request = json.loads(request_record.read_bytes())
        assert request["record_type"] == "signal_requested"
        assert request["actor_label"] == "recovery-test"
        assert request["attempt_id"] == dispatch.attempt_id
        assert request["pid"] == request["pgid"] == process.pid
        assert request["signal"] == "SIGKILL"
        assert request["requested_at"] == result["requested_at"]
        assert sorted(
            path.name
            for path in (tmp_path / "runtime" / "failure-injections").iterdir()
        ) == sorted((record.name, request_record.name))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        if reaper is None:
            process.wait(timeout=5)
        else:
            reaper.join(timeout=5)
        registry.remove(dispatch)


@PROCESS_TOOLS
@pytest.mark.parametrize("mode", ("crash_after_signal", "signal_refused"))
def test_failure_lab_keeps_the_request_when_no_observed_outcome_is_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    lab = _load_failure_lab()
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    dispatch = _dispatch("mission-lab", f"attempt-{mode}", "worker-live")
    process = subprocess.Popen(
        ("/bin/sleep", "30"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    class SimulatedCrash(BaseException):
        pass

    try:
        registry.record(dispatch, process, "/bin/sleep")
        owned = registry.validate(dispatch)
        registry.acknowledge_model_dispatch(
            dispatch,
            owned,
            request_sha256="b" * 64,
            sdk_invocation_id="invocation-model-crash",
            dispatched_at="2026-08-27T12:00:00.000Z",
        )
        original_signal = registry.signal_prepared

        def stop_after_request(  # noqa: ANN202
            actual_owned,
            actual_signal,  # noqa: ANN001
        ):
            if mode == "signal_refused":
                raise ProcessControlError("owned process identity changed")
            original_signal(actual_owned, actual_signal)
            raise SimulatedCrash

        monkeypatch.setattr(registry, "signal_prepared", stop_after_request)
        if mode == "signal_refused":
            with pytest.raises(lab.FailureLabError, match="identity changed"):
                lab.kill_model_attempt(
                    registry,
                    dispatch.mission_id,
                    dispatch.attempt_id,
                    dispatch,
                    actor_label="audit-test",
                )
        else:
            with pytest.raises(SimulatedCrash):
                lab.kill_model_attempt(
                    registry,
                    dispatch.mission_id,
                    dispatch.attempt_id,
                    dispatch,
                    actor_label="audit-test",
                )
            process.wait(timeout=5)

        records = [
            json.loads(path.read_bytes())
            for path in (tmp_path / "runtime" / "failure-injections").iterdir()
        ]
        requests = [
            item for item in records if item["record_type"] == "signal_requested"
        ]
        assert len(requests) == 1
        request = requests[0]
        assert request["actor_label"] == "audit-test"
        assert request["attempt_id"] == dispatch.attempt_id
        assert request["pid"] == request["pgid"] == process.pid
        assert request["signal"] == "SIGKILL"
        if mode == "crash_after_signal":
            assert len(records) == 1
        else:
            refused = next(
                item for item in records if item["record_type"] == "signal_refused"
            )
            assert refused["signal_request_record_sha256"] == sha256_hex(
                canonical_json_bytes(request)
            )
            assert refused["reason"] == "owned process identity changed"
            assert refused["observed_process_state"] == "unknown"
            assert process.poll() is None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        registry.remove(dispatch)


def test_auto_reopens_the_store_after_a_transient_read_error() -> None:
    """Live contact: one quarantined read must not blind the poller for 900 s."""

    from types import SimpleNamespace

    from graphene.orchestration.sqlite_mission_store import MissionStoreError

    lab = _load_failure_lab()

    class Quarantined:
        def snapshot(self, mission_id):  # noqa: ANN001
            raise MissionStoreError("mission materialized artifacts are invalid")

    completed = SimpleNamespace(
        snapshot=lambda mission_id: SimpleNamespace(
            mission=SimpleNamespace(status=MissionStatus.COMPLETED),
            tasks=(),
            attempts=(),
            publications=(),
        )
    )
    reopened: list[object] = []

    def reopen():  # noqa: ANN202
        reopened.append(completed)
        return completed

    with pytest.raises(lab.FailureLabError, match="no kill opportunity"):
        lab.auto_kill(
            Quarantined(),
            OwnedProcessRegistry.__new__(OwnedProcessRegistry),
            "mission-1",
            timeout=5,
            poll=0.001,
            reopen=reopen,
        )
    assert reopened == [completed]
