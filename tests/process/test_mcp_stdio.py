from __future__ import annotations

import asyncio
import json
import signal
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path

import pytest
from graphene.hashing import canonical_json_bytes
from graphene.lineage import SQLiteArtifactStore, SQLiteLineageStore
from graphene.models import (
    LineageAuthority,
    LineageEventType,
    SourceKind,
    VerifiedHead,
)
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"
GRAPHENE_MCP = ROOT / ".venv/bin/graphene-mcp"
_TOOLS = {
    "search_repo": {"query"},
    "read_file": {"path"},
    "open_evidence": {"evidence_id"},
    "write_file": {"path", "content"},
    "run_fixed_test": set(),
    "request_completion": set(),
}


def _environment(database: Path | None = None) -> dict[str, str]:
    environment = {
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / "backend"),
    }
    if database is not None:
        environment["GRAPHENE_LINEAGE_DB"] = str(database)
    return environment


def _run_id(database: Path) -> str:
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute("SELECT run_id FROM run_heads").fetchall()
    assert len(rows) == 1
    return str(rows[0][0])


def _store(database: Path) -> SQLiteLineageStore:
    artifacts = SQLiteArtifactStore(database, read_only=True)
    return SQLiteLineageStore(
        database,
        artifact_resolver=artifacts.resolve,
        read_only=True,
    )


async def _watch_event(
    process: asyncio.subprocess.Process,
    expected_seq: int,
) -> dict[str, object]:
    assert process.stdout is not None
    raw = await asyncio.wait_for(process.stdout.readline(), timeout=10)
    assert raw
    event = json.loads(raw)
    assert raw == canonical_json_bytes(event) + b"\n"
    assert event["seq"] == expected_seq
    return event


def _snapshot(runtime: Path, database: Path, run_id: str, *, json_mode: bool):
    arguments = [str(GRAPHENE)]
    if json_mode:
        arguments.append("--json")
    arguments.extend(("watch", run_id, "--snapshot"))
    return subprocess.run(
        arguments,
        cwd=runtime,
        env=_environment(database),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_official_stdio_client_routes_bootstrapped_common_service(tmp_path: Path):
    async def scenario() -> None:
        runtime = tmp_path / "runtime"
        runtime.mkdir(mode=0o700)
        database = runtime / "lineage.sqlite3"
        parameters = StdioServerParameters(
            command=str(GRAPHENE_MCP),
            args=[
                "--task",
                "baseline_max_attempts",
                "--profile",
                "platform-maintainer@1",
            ],
            env=_environment(database),
            cwd=runtime,
        )

        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
            async with stdio_client(parameters, errlog=errors) as streams:  # noqa: SIM117
                async with ClientSession(*streams) as session:
                    initialized = await session.initialize()
                    assert initialized.protocol_version == "2025-11-25"

                    run_id = _run_id(database)
                    store = _store(database)
                    head = store.verify(run_id)
                    assert isinstance(head, VerifiedHead)
                    assert head.seq == 2
                    assert [
                        event.event_type for event in store.tail(run_id, 0, 256)
                    ] == [
                        LineageEventType.RUN_STARTED,
                        LineageEventType.INVOCATION_STARTED,
                    ]

                    listed = await session.list_tools()
                    assert [tool.name for tool in listed.tools] == list(_TOOLS)
                    for tool in listed.tools:
                        schema = tool.input_schema
                        expected = _TOOLS[tool.name]
                        assert schema["type"] == "object"
                        assert schema["additionalProperties"] is False
                        assert set(schema["properties"]) == expected
                        assert set(schema.get("required", ())) == expected

                    watcher = await asyncio.create_subprocess_exec(
                        str(GRAPHENE),
                        "--json",
                        "watch",
                        run_id,
                        cwd=runtime,
                        env=_environment(database),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    assert (await _watch_event(watcher, 1))[
                        "event_type"
                    ] == "run.started"
                    assert (await _watch_event(watcher, 2))[
                        "event_type"
                    ] == "invocation.started"

                    read_task = asyncio.create_task(
                        session.call_tool(
                            "read_file",
                            {"path": "app/auth/limiter.py"},
                        )
                    )
                    ordering_failure: str | None = None
                    watched: list[dict[str, object]] = []
                    try:
                        for expected_seq in (3, 4):
                            event = await _watch_event(watcher, expected_seq)
                            watched.append(event)
                            if read_task.done() and ordering_failure is None:
                                ordering_failure = (
                                    "SDK read_file result completed before the public "
                                    f"watcher observed committed seq {expected_seq}"
                                )
                        read = await read_task
                    finally:
                        if not read_task.done():
                            read_task.cancel()
                            await asyncio.gather(read_task, return_exceptions=True)
                        if watcher.returncode is None:
                            watcher.send_signal(signal.SIGINT)
                        watch_stdout, watch_stderr = await asyncio.wait_for(
                            watcher.communicate(),
                            timeout=10,
                        )

                    assert watcher.returncode == 130
                    assert watch_stdout == b""
                    assert watch_stderr == b""
                    assert [event["event_type"] for event in watched] == [
                        "tool.started",
                        "tool.completed",
                    ]
                    assert read.is_error is False
                    assert "MAX_ATTEMPTS" in read.structured_content["content"]

                    after_read = store.verify(run_id)
                    assert isinstance(after_read, VerifiedHead)
                    assert after_read.seq == 4
                    read_events = store.tail(run_id, 0, 256)
                    assert [event.event_type for event in read_events] == [
                        LineageEventType.RUN_STARTED,
                        LineageEventType.INVOCATION_STARTED,
                        LineageEventType.TOOL_STARTED,
                        LineageEventType.TOOL_COMPLETED,
                    ]
                    assert watched == [
                        event.model_dump(mode="json") for event in read_events[2:]
                    ]

                    completion = await session.call_tool("request_completion")
                    assert completion.is_error is False
                    assert completion.structured_content == {
                        "status": "denied",
                        "reason_code": "human_promotion_required",
                        "state": "NEEDS_HUMAN",
                    }
                    completion_events = store.tail(
                        run_id,
                        after_read.seq,
                        256,
                    )
                    assert [event.event_type for event in completion_events] == [
                        LineageEventType.COMPLETION_ATTEMPTED,
                        LineageEventType.COMPLETION_DENIED,
                    ]
                    assert (
                        completion_events[0].authority == LineageAuthority.MCP_ADAPTER
                    )
                    assert (
                        completion_events[0].source_ref.kind
                        == SourceKind.MCP_REQUEST_RECEIPT
                    )

                    committed = store.verify(run_id)
                    assert isinstance(committed, VerifiedHead)
                    late = await session.call_tool(
                        "read_file",
                        {"path": "app/auth/limiter.py"},
                    )
                    assert late.is_error is True
                    assert store.verify(run_id) == committed

            errors.flush()
            errors.seek(0)
            assert errors.read() == "GRAPHENE_MCP_STDIO_READY\n"

        json_snapshot = _snapshot(
            runtime,
            database,
            run_id,
            json_mode=True,
        )
        assert json_snapshot.returncode == 0
        assert json_snapshot.stderr == b""
        persisted = store.tail(run_id, 0, 256)
        assert json_snapshot.stdout == b"".join(
            canonical_json_bytes(event.model_dump(mode="json")) + b"\n"
            for event in persisted
        )

        first_projection = _snapshot(
            runtime,
            database,
            run_id,
            json_mode=False,
        )
        restarted_projection = _snapshot(
            runtime,
            database,
            run_id,
            json_mode=False,
        )
        assert first_projection.returncode == restarted_projection.returncode == 0
        assert first_projection.stderr == restarted_projection.stderr == b""
        assert first_projection.stdout == restarted_projection.stdout
        assert b"\x1b[" not in first_projection.stdout
        if ordering_failure is not None:
            pytest.fail(ordering_failure)

    asyncio.run(scenario())


def test_stdio_denied_path_is_private(tmp_path: Path):
    async def scenario() -> None:
        runtime = tmp_path / "runtime"
        runtime.mkdir(mode=0o700)
        database = runtime / "lineage.sqlite3"
        parameters = StdioServerParameters(
            command=str(GRAPHENE_MCP),
            args=[
                "--task",
                "baseline_max_attempts",
                "--profile",
                "platform-maintainer@1",
            ],
            env=_environment(database),
            cwd=runtime,
        )

        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
            async with stdio_client(parameters, errlog=errors) as streams:  # noqa: SIM117
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    run_id = _run_id(database)
                    store = _store(database)
                    canary = "PRIVATE_DENIED_PATH_CANARY_9a3f"
                    denied = await session.call_tool("read_file", {"path": canary})
                    assert denied.is_error is True
                    assert canary not in str(denied.model_dump(mode="json"))
                    events = store.tail(run_id, 0, 256)
                    assert [event.event_type for event in events] == [
                        LineageEventType.RUN_STARTED,
                        LineageEventType.INVOCATION_STARTED,
                        LineageEventType.SCOPE_DENIED,
                    ]
                    assert canary not in str(events[-1].model_dump(mode="json"))

            errors.flush()
            errors.seek(0)
            assert errors.read() == "GRAPHENE_MCP_STDIO_READY\n"

        snapshot = _snapshot(runtime, database, run_id, json_mode=True)
        assert snapshot.returncode == 0
        assert snapshot.stderr == b""
        persisted = store.tail(run_id, 0, 256)
        assert [event.event_type for event in persisted] == [
            LineageEventType.RUN_STARTED,
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.SCOPE_DENIED,
            LineageEventType.RUN_INTERRUPTED,
        ]
        assert canary not in str(persisted[-1].model_dump(mode="json"))
        assert snapshot.stdout == b"".join(
            canonical_json_bytes(event.model_dump(mode="json")) + b"\n"
            for event in persisted
        )

    asyncio.run(scenario())


def test_stdio_interrupt_recovers_before_process_exit(tmp_path: Path):
    async def scenario() -> None:
        runtime = tmp_path / "runtime"
        runtime.mkdir(mode=0o700)
        database = runtime / "lineage.sqlite3"
        process = await asyncio.create_subprocess_exec(
            str(GRAPHENE_MCP),
            "--task",
            "baseline_max_attempts",
            "--profile",
            "platform-maintainer@1",
            cwd=runtime,
            env=_environment(database),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stderr is not None
        assert (
            await asyncio.wait_for(process.stderr.readline(), timeout=10)
            == b"GRAPHENE_MCP_STDIO_READY\n"
        )
        run_id = _run_id(database)
        process.send_signal(signal.SIGINT)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)

        assert process.returncode == 130
        assert stdout == b""
        assert stderr == b"GRAPHENE_MCP_INTERRUPTED\n"
        store = _store(database)
        events = store.tail(run_id, 0, 256)
        assert [event.event_type for event in events] == [
            LineageEventType.RUN_STARTED,
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.RUN_INTERRUPTED,
        ]
        assert not (runtime / "checkouts" / run_id).exists()

    asyncio.run(scenario())


def test_stdio_invalid_configuration_is_constant_stderr_only(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    result = subprocess.run(
        [
            str(GRAPHENE_MCP),
            "--task",
            "baseline_max_attempts",
            "--profile",
            "platform-maintainer@1",
        ],
        cwd=runtime,
        env=_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == b"GRAPHENE_MCP_CONFIG_ERROR\n"
    assert tuple(runtime.iterdir()) == ()


def test_stdio_invalid_resume_is_constant_stderr_only(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    canary = "PRIVATE_UNKNOWN_CONSUMER_CANARY"
    result = subprocess.run(
        [str(GRAPHENE_MCP), "--run", canary],
        cwd=runtime,
        env=_environment(database),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr == b"GRAPHENE_MCP_STARTUP_ERROR\n"
    assert canary.encode() not in result.stderr
    assert tuple(runtime.iterdir()) == ()


def test_stdio_invalid_arguments_do_not_echo_client_input(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    canary = "CLIENT_ARGUMENT_CANARY_b12e"
    result = subprocess.run(
        [str(GRAPHENE_MCP), "--task", canary, "--profile", canary],
        cwd=runtime,
        env=_environment(runtime / "lineage.sqlite3"),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == b"GRAPHENE_MCP_ARGUMENT_ERROR\n"
    assert canary.encode() not in result.stderr
    assert tuple(runtime.iterdir()) == ()
