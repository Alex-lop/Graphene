from __future__ import annotations

import asyncio
import struct
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.orchestration.worker_runtime import (
    CompletionOutcome,
    RuntimeErrorCode,
    RuntimeFailure,
    WorkerCompletion,
    WorkerProviderInterruption,
)
from graphene.orchestration.process_control import (
    ModelDispatchBarrier,
    OwnedProcess,
    OwnedProcessRegistry,
)
from graphene.orchestration.workers.gemini import (
    CHILD_MAX_FRAME_BYTES,
    GeminiChildFrame,
    GeminiChildRequest,
    GeminiChildSource,
    GeminiWorkerAdapter,
    child_frame_bytes,
)


def _request() -> GeminiChildRequest:
    return GeminiChildRequest(
        mission_id="mission-1",
        plan_revision=1,
        plan_sha256="a" * 64,
        task_id="task-1",
        attempt_id="attempt-1",
        attempt_number=1,
        worker_id="worker-1",
        lease_id="lease-1",
        fencing_token=2,
        base_sha="b" * 40,
        policy_sha256="c" * 64,
        accepted_input_sha256=("d" * 64,),
        title="Bounded task",
        contract="Change only the leased file.",
        sources=(
            GeminiChildSource(
                path="src/a.py", sha256=sha256_hex(b"old\n"), text="old\n"
            ),
        ),
        operator_inputs=(),
        write_paths=("src/a.py",),
        requested_model="gemini-3.5-flash",
        credential_mode="gemini_api",
        timeout_seconds=30,
    )


def test_child_request_is_canonical_bounded_and_contains_no_repository_authority() -> (
    None
):
    request = _request()
    frame = child_frame_bytes(request)
    size = struct.unpack(">I", frame[:4])[0]

    assert size == len(frame) - 4
    assert frame[4:] == canonical_json_bytes(request.model_dump(mode="json"))
    assert size <= CHILD_MAX_FRAME_BYTES
    serialized = frame.decode("utf-8", "ignore")
    assert "repository" not in serialized
    assert "runtime" not in serialized
    assert "command" not in serialized
    assert "GITHUB" not in serialized


def test_child_request_rejects_oversized_source_context() -> None:
    with pytest.raises(ValidationError, match="sources exceed their byte limit"):
        _request().model_copy(
            update={
                "sources": tuple(
                    GeminiChildSource(
                        path=f"src/{index}.txt",
                        sha256=sha256_hex(("x" * 262_144).encode()),
                        text="x" * 262_144,
                    )
                    for index in range(5)
                )
            }
        ).__class__.model_validate(
            _request()
            .model_copy(
                update={
                    "sources": tuple(
                        GeminiChildSource(
                            path=f"src/{index}.txt",
                            sha256=sha256_hex(("x" * 262_144).encode()),
                            text="x" * 262_144,
                        )
                        for index in range(5)
                    )
                }
            )
            .model_dump(mode="json")
        )


def test_child_source_rejects_text_that_does_not_match_its_digest() -> None:
    with pytest.raises(ValidationError, match="digest does not match"):
        GeminiChildSource(path="src/a.py", sha256="a" * 64, text="different")


def test_provider_interruption_is_retryable_and_repository_effect_is_known_absent() -> (
    None
):
    interruption = WorkerProviderInterruption(
        requested_model="gemini-3.5-flash",
        mission_id="mission-1",
        task_id="task-1",
        attempt_id="attempt-1",
        lease_id="lease-1",
        fencing_token=2,
        request_sha256="a" * 64,
        input_bytes=100,
        sdk_invocation_id="invocation-1",
        dispatched_at="2026-08-27T12:00:00.000Z",
        pid=123,
        pgid=123,
        process_started_at="Thu Aug 27 12:00:00 2026",
        process_birth_token="test:birth:123",
        executable="/usr/bin/python3",
        exit_code=-9,
        signal_name="sigkill",
        stderr_sha256=sha256_hex(b""),
        stderr_truncated=False,
    )
    completion = WorkerCompletion(
        outcome=CompletionOutcome.RETRYABLE_FAILURE,
        result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED,
        session_id="session-1",
        invocation_id="invocation-1",
        provider_interruption=interruption,
    )

    assert completion.provider_interruption is not None
    assert completion.provider_interruption.repository_effect == "known_absent"
    assert completion.provider_interruption.provider_outcome == "unknown"


def test_dispatch_frame_cannot_smuggle_a_result() -> None:
    with pytest.raises(ValidationError, match="dispatch frame has the wrong shape"):
        GeminiChildFrame(
            type="provider_dispatched",
            request_sha256="a" * 64,
            sdk_invocation_id="invocation-1",
            dispatched_at="2026-08-27T12:00:00.000Z",
            result_code=RuntimeErrorCode.RUNTIME_UNAVAILABLE,
        )


def test_isolated_child_rejects_malformed_input_without_error_leakage(
    tmp_path: Path,
) -> None:
    process = subprocess.run(
        (
            sys.executable,
            "-I",
            "-m",
            "graphene.orchestration.workers.gemini_child",
        ),
        cwd=tmp_path,
        env={"LC_ALL": "C", "PYTHONUNBUFFERED": "1"},
        input=struct.pack(">I", 0),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )

    assert process.returncode == 2
    assert process.stdout == process.stderr == b""


def test_live_child_refuses_a_symlinked_private_directory(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "private-runtime"
    runtime.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    (runtime / "model-children").symlink_to(outside, target_is_directory=True)
    adapter = GeminiWorkerAdapter.live(
        worker_id="worker-1", environ={"GOOGLE_API_KEY": "not-recorded"}
    )
    context = SimpleNamespace(runtime=SimpleNamespace(runtime=runtime))

    with pytest.raises(RuntimeFailure) as rejected:
        asyncio.run(adapter._execute_child(context, _request()))  # type: ignore[arg-type]

    assert rejected.value.code == RuntimeErrorCode.RUNTIME_UNAVAILABLE
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"


def test_live_child_startup_uses_the_model_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "private-runtime"
    runtime.mkdir()
    adapter = GeminiWorkerAdapter.live(
        worker_id="worker-1",
        environ={"GOOGLE_API_KEY": "not-recorded"},
        model_timeout_seconds=0.02,
    )
    context = SimpleNamespace(runtime=SimpleNamespace(runtime=runtime))

    async def never_starts(*_args: object, **_kwargs: object) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", never_starts)
    started = time.monotonic()
    with pytest.raises(RuntimeFailure) as rejected:
        asyncio.run(adapter._execute_child(context, _request()))  # type: ignore[arg-type]

    assert rejected.value.code == RuntimeErrorCode.PROVIDER_TIMEOUT
    assert time.monotonic() - started < 1


def test_live_child_input_backpressure_uses_the_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "private-runtime"
    runtime.mkdir()
    adapter = GeminiWorkerAdapter.live(
        worker_id="worker-1",
        environ={"GOOGLE_API_KEY": "not-recorded"},
        model_timeout_seconds=0.02,
    )

    class Input:
        def write(self, _value: bytes) -> None:
            pass

        async def drain(self) -> None:
            await asyncio.Event().wait()

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    class Child:
        pid = 424_245
        returncode: int | None = None

        def __init__(self) -> None:
            self.stdin = Input()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_eof()

        async def wait(self) -> int:
            self.returncode = -15
            return self.returncode

    request = _request()
    owned = OwnedProcess(
        "mission-1",
        "attempt-1",
        Child.pid,
        Child.pid,
        "Tue Aug 19 00:00:00 2026",
        "test:birth:424245",
        sys.executable,
        request.request_sha256(),
        len(child_frame_bytes(request)) - 4,
        3,
    )
    async def spawned(*_args: object, **_kwargs: object) -> Child:
        return Child()

    async def heartbeat() -> None:
        pass

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawned)
    monkeypatch.setattr(
        OwnedProcessRegistry, "record_pid", lambda *_, **_kwargs: owned
    )
    monkeypatch.setattr(OwnedProcessRegistry, "signal_prepared", lambda *_: True)
    removed: list[OwnedProcess] = []
    monkeypatch.setattr(
        OwnedProcessRegistry,
        "remove_exact",
        lambda _registry, value: removed.append(value),
    )
    context = SimpleNamespace(
        runtime=SimpleNamespace(runtime=runtime),
        dispatch=SimpleNamespace(
            mission_id=request.mission_id,
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            lease_id=request.lease_id,
            fencing_token=request.fencing_token,
        ),
        heartbeat=heartbeat,
    )

    _intent, completion = asyncio.run(
        asyncio.wait_for(
            adapter._execute_child(context, request),  # type: ignore[arg-type]
            timeout=0.5,
        )
    )

    assert completion.result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED
    assert completion.provider_interruption is not None
    assert (
        completion.provider_interruption.provider_dispatch_state == "unconfirmed"
    )
    assert removed == []


def test_dispatch_ack_persistence_failure_retains_exact_v3_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "private-runtime"
    runtime.mkdir()
    adapter = GeminiWorkerAdapter.live(
        worker_id="worker-1", environ={"GOOGLE_API_KEY": "not-recorded"}
    )
    request = _request()

    class Input:
        def write(self, _value: bytes) -> None:
            pass

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    class Child:
        pid = 424_247
        returncode: int | None = None

        def __init__(self) -> None:
            self.stdin = Input()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_eof()

        async def wait(self) -> int:
            self.returncode = -9
            return self.returncode

    owned = OwnedProcess(
        request.mission_id,
        request.attempt_id,
        Child.pid,
        Child.pid,
        "Tue Aug 19 00:00:00 2026",
        "test:birth:424247",
        sys.executable,
        request.request_sha256(),
        len(child_frame_bytes(request)) - 4,
        3,
    )
    persisted_barrier = ModelDispatchBarrier(
        mission_id=request.mission_id,
        task_id=request.task_id,
        attempt_id=request.attempt_id,
        lease_id=request.lease_id,
        fencing_token=request.fencing_token,
        request_sha256=request.request_sha256(),
        sdk_invocation_id="invocation-before-fsync",
        dispatched_at="2026-08-27T12:00:00.000Z",
        pid=owned.pid,
        pgid=owned.pgid,
        started_at=owned.started_at,
        birth_token=owned.birth_token,
        executable=owned.executable,
    )

    async def spawned(*_args: object, **_kwargs: object) -> Child:
        return Child()

    async def heartbeat() -> None:
        pass

    async def dispatched(_stream: object) -> GeminiChildFrame:
        return GeminiChildFrame(
            type="provider_dispatched",
            request_sha256=request.request_sha256(),
            sdk_invocation_id="invocation-before-fsync",
            dispatched_at="2026-08-27T12:00:00.000Z",
        )

    removed: list[OwnedProcess] = []
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawned)
    monkeypatch.setattr(adapter, "_read_child_frame", dispatched)
    monkeypatch.setattr(
        OwnedProcessRegistry, "record_pid", lambda *_, **_kwargs: owned
    )
    monkeypatch.setattr(
        OwnedProcessRegistry,
        "acknowledge_model_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("fsync failed")),
    )
    monkeypatch.setattr(
        OwnedProcessRegistry,
        "confirm_model_dispatch_barrier",
        lambda *_args, **_kwargs: persisted_barrier,
    )
    monkeypatch.setattr(OwnedProcessRegistry, "signal_prepared", lambda *_: True)
    monkeypatch.setattr(
        OwnedProcessRegistry,
        "remove_exact",
        lambda _registry, value: removed.append(value),
    )
    context = SimpleNamespace(
        runtime=SimpleNamespace(runtime=runtime),
        dispatch=SimpleNamespace(
            mission_id=request.mission_id,
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            lease_id=request.lease_id,
            fencing_token=request.fencing_token,
        ),
        heartbeat=heartbeat,
    )

    _intent, completion = asyncio.run(
        adapter._execute_child(context, request)  # type: ignore[arg-type]
    )

    assert completion.provider_interruption is not None
    assert (
        completion.provider_interruption.provider_dispatch_state
        == "transport_acknowledged"
    )
    assert completion.invocation_id == persisted_barrier.sdk_invocation_id
    assert removed == []


def test_acknowledged_child_error_without_receipt_keeps_dispatch_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "private-runtime"
    runtime.mkdir()
    adapter = GeminiWorkerAdapter.live(
        worker_id="worker-1", environ={"GOOGLE_API_KEY": "not-recorded"}
    )
    request = _request()
    request_sha256 = request.request_sha256()
    invocation_id = "invocation-acknowledged"

    class Input:
        def write(self, _value: bytes) -> None:
            pass

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    class Child:
        pid = 424_246
        returncode: int | None = None

        def __init__(self) -> None:
            self.stdin = Input()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            for frame in (
                GeminiChildFrame(
                    type="provider_dispatched",
                    request_sha256=request_sha256,
                    sdk_invocation_id=invocation_id,
                    dispatched_at="2026-08-27T12:00:00.000Z",
                ),
                GeminiChildFrame(
                    type="error",
                    request_sha256=request_sha256,
                    sdk_invocation_id=invocation_id,
                    session_id="session-acknowledged",
                    result_code=RuntimeErrorCode.PROVIDER_UNAVAILABLE,
                ),
            ):
                self.stdout.feed_data(child_frame_bytes(frame))
            self.stdout.feed_eof()
            self.stderr.feed_eof()

        async def wait(self) -> int:
            self.returncode = 0
            return 0

    owned = OwnedProcess(
        request.mission_id,
        request.attempt_id,
        Child.pid,
        Child.pid,
        "Tue Aug 19 00:00:00 2026",
        "test:birth:424246",
        sys.executable,
    )
    barrier = ModelDispatchBarrier(
        mission_id=request.mission_id,
        task_id=request.task_id,
        attempt_id=request.attempt_id,
        lease_id=request.lease_id,
        fencing_token=request.fencing_token,
        request_sha256=request_sha256,
        sdk_invocation_id=invocation_id,
        dispatched_at="2026-08-27T12:00:00.000Z",
        pid=owned.pid,
        pgid=owned.pgid,
        started_at=owned.started_at,
        birth_token=owned.birth_token,
        executable=owned.executable,
    )

    async def spawned(*_args: object, **_kwargs: object) -> Child:
        return Child()

    async def heartbeat() -> None:
        pass

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawned)
    monkeypatch.setattr(
        OwnedProcessRegistry, "record_pid", lambda *_, **_kwargs: owned
    )
    monkeypatch.setattr(
        OwnedProcessRegistry, "acknowledge_model_dispatch", lambda *_args, **_kw: barrier
    )
    context = SimpleNamespace(
        runtime=SimpleNamespace(runtime=runtime),
        dispatch=SimpleNamespace(
            mission_id=request.mission_id,
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            lease_id=request.lease_id,
            fencing_token=request.fencing_token,
        ),
        heartbeat=heartbeat,
    )

    intent, completion = asyncio.run(
        adapter._execute_child(context, request)  # type: ignore[arg-type]
    )

    assert intent is None
    assert completion.result_code == RuntimeErrorCode.PROVIDER_UNAVAILABLE
    assert completion.provider is None
    assert completion.provider_interruption is not None
    assert completion.provider_interruption.sdk_invocation_id == invocation_id
    assert completion.provider_interruption.provider_outcome == "unknown"
    assert completion.provider_interruption.billing_outcome == "unknown"


def test_recovery_refuses_to_bind_prebarrier_child_to_a_different_request(
    tmp_path: Path,
) -> None:
    request = _request()
    dispatch = SimpleNamespace(
        mission_id=request.mission_id,
        task_id=request.task_id,
        attempt_id=request.attempt_id,
        lease_id=request.lease_id,
        fencing_token=request.fencing_token,
    )
    private = tmp_path / "private"
    worker_runtime = private / "worker-runtime"
    worker_runtime.mkdir(parents=True)
    registry = OwnedProcessRegistry(private)
    process = subprocess.Popen(("/bin/sleep", "30"), start_new_session=True)
    registry.record_pid(
        dispatch,  # type: ignore[arg-type]
        process.pid,
        "/bin/sleep",
        model_request_sha256="f" * 64,
        model_input_bytes=64,
    )
    context = SimpleNamespace(
        runtime=SimpleNamespace(runtime=worker_runtime), dispatch=dispatch
    )
    adapter = GeminiWorkerAdapter.live(
        worker_id=request.worker_id, environ={"GOOGLE_API_KEY": "not-recorded"}
    )
    try:
        with pytest.raises(RuntimeFailure) as rejected:
            adapter._recover_interrupted_child(  # type: ignore[arg-type]
                context, request
            )
        assert rejected.value.code == RuntimeErrorCode.ADAPTER_REJECTED
        assert process.poll() is not None
        assert registry.has_record(request.attempt_id)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        registry.remove(dispatch)  # type: ignore[arg-type]
