from __future__ import annotations

import asyncio
import json
import os
import pty
import select
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from graphene.bootstrap import BootstrappedRun, bootstrap_local_run
from graphene.context.consumer import FreshConsumer, start_fresh_consumer
from graphene.context.handoff import AUTH_CAPABILITIES, compile_verified_handoff
from graphene.lineage import HumanWorkflowService
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import SQLiteCheckpointRecorder
from graphene.lineage.reducer import reduce_events
from graphene.lineage.service import ToolCallIdentity
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    EvidenceKind,
    GoldenContract,
    GraphMvpContract,
    HandoffDenied,
    HunkEvidence,
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    MemoryDecisionValue,
    ScopeId,
    VerifiedHead,
)
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).parents[2]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
GRAPH = GraphMvpContract.model_validate_json(
    (ROOT / "contracts/graph_mvp.json").read_text()
)
NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)
GRAPHENE = ROOT / ".venv/bin/graphene"
GRAPHENE_MCP = ROOT / ".venv/bin/graphene-mcp"


def _tty_cli(environment: dict[str, str], cwd: Path, *arguments: str) -> dict:
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [str(GRAPHENE), "--json", *arguments],
        cwd=cwd,
        env=environment,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    output = bytearray()
    try:
        while process.poll() is None:
            # Generous on purpose: what this test asserts is that the CLI
            # recovers, not that it answers inside a wall-clock budget. On a
            # loaded host a real subprocess can take tens of seconds, and a
            # correctness test that flips on machine load is not a test.
            # pytest-timeout is the actual hang guard.
            ready, _, _ = select.select([master], [], [], 300)
            if not ready:
                process.kill()
                raise AssertionError("TTY CLI command produced no output in 300s")
            chunk = os.read(master, 65_536)
            if not chunk:
                break
            output.extend(chunk)
        while select.select([master], [], [], 0)[0]:
            chunk = os.read(master, 65_536)
            if not chunk:
                break
            output.extend(chunk)
    except OSError:
        pass
    finally:
        os.close(master)
    assert process.wait(timeout=1) == 0, output.decode(errors="replace")
    return json.loads(output.decode().replace("\r", "").splitlines()[-1])


def _head(event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _call(run: BootstrappedRun | FreshConsumer, number: int) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.handle.model_id,
        tool_call_id=f"human_loop_call_{number:03d}",
        agent_name="graphene_local",
        adapter_kind="local",
    )


def _events(store: SQLiteLineageStore, run_id: str):
    head = store.verify(run_id)
    assert isinstance(head, VerifiedHead)
    return store.tail(run_id, 0, head.seq)


def _profile(profile_id: str):
    return next(
        profile for profile in GRAPH.catalog if profile.agent_profile_id == profile_id
    )


async def _run_resumed_consumer(
    consumer: FreshConsumer,
    database: Path,
    hunk_id: str,
) -> tuple[dict, dict, dict, dict]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["GRAPHENE_LINEAGE_DB"] = str(database)
    parameters = StdioServerParameters(
        command=str(GRAPHENE_MCP),
        args=["--run", consumer.run_id],
        env=environment,
        cwd=database.parent,
    )
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        async with stdio_client(parameters, errlog=errors) as streams:  # noqa: SIM117
            async with ClientSession(*streams) as session:
                await session.initialize()
                evidence = await session.call_tool(
                    "open_evidence",
                    {"evidence_id": hunk_id},
                )
                limiter = await session.call_tool(
                    "read_file",
                    {"path": "app/auth/limiter.py"},
                )
                absent = await session.call_tool(
                    "read_file",
                    {"path": "tests/test_security_policy.py"},
                )
                limiter_write = await session.call_tool(
                    "write_file",
                    {
                        "path": "app/auth/limiter.py",
                        "content": limiter.structured_content["content"].replace(
                            "WINDOW_SECONDS = 60",
                            "WINDOW_SECONDS = 90",
                        ),
                    },
                )
                test_write = await session.call_tool(
                    "write_file",
                    {
                        "path": "tests/test_security_policy.py",
                        "content": GOLDEN.memory.expected_security_test_content,
                    },
                )
                tested = await session.call_tool("run_fixed_test")
                completion = await session.call_tool("request_completion")
                assert all(
                    not result.is_error
                    for result in (
                        evidence,
                        limiter,
                        absent,
                        limiter_write,
                        test_write,
                        tested,
                        completion,
                    )
                )
        errors.flush()
        errors.seek(0)
        assert errors.read() == "GRAPHENE_MCP_STDIO_READY\n"
    return (
        evidence.structured_content,
        limiter.structured_content,
        absent.structured_content,
        {
            "limiter_write": limiter_write.structured_content,
            "test_write": test_write.structured_content,
            "tested": tested.structured_content,
            "completion": completion.structured_content,
        },
    )


def test_public_human_loop_reaches_a_fresh_verified_consumer(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    source = bootstrap_local_run(
        database,
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )

    original = source.service.read_file(
        source.handle,
        _call(source, 1),
        path="app/auth/limiter.py",
    )
    source.service.write_file(
        source.handle,
        _call(source, 2),
        path="app/auth/limiter.py",
        content=original.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"),
    )
    tested = source.service.run_fixed_test(source.handle, _call(source, 3))
    assert tested.passed is True
    completion = source.service.request_completion(source.handle, _call(source, 4))
    assert completion.state == "NEEDS_HUMAN"

    observed = _events(source.store, source.run_id)
    write_event = next(
        event
        for event in observed
        if event.payload.get("operation") == "write_file"
        and event.payload.get("status") == "completed"
    )
    test_event = next(
        event
        for event in observed
        if event.payload.get("operation") == "run_fixed_test"
        and event.payload.get("status") == "completed"
    )
    workflow = HumanWorkflowService(source.store, source.artifacts, GOLDEN.memory)
    changeset = workflow.derive_changeset(
        source.run_id,
        source.handle.head,
        idempotency_key="human_loop_changeset_001",
    )
    test_receipt = workflow.record_test_receipt(
        source.run_id,
        _head(changeset),
        test_event_id=test_event.event_id,
        idempotency_key="human_loop_test_receipt_001",
    )
    hunk_reference = next(
        reference
        for reference in changeset.references
        if reference.kind == EvidenceKind.HUNK
    )
    hunk_bytes = source.artifacts.resolve(
        hunk_reference.kind.value,
        hunk_reference.id,
    )
    assert hunk_bytes is not None
    hunk = HunkEvidence.model_validate_json(hunk_bytes)
    asked = workflow.ask_clarification(
        source.run_id,
        _head(test_receipt),
        write_event_id=write_event.event_id,
        hunk_id=hunk.hunk_id,
        correction=GOLDEN.memory.correction,
        idempotency_key="human_loop_question_001",
    )
    answered = workflow.answer_clarification(
        source.run_id,
        _head(asked),
        question_id=asked.payload["question_id"],
        choice=ScopeId.ALL_AUTH,
        idempotency_key="human_loop_answer_001",
        human_attestation=True,
    )
    feedback = workflow.record_feedback(
        source.run_id,
        _head(answered),
        question_id=asked.payload["question_id"],
        idempotency_key="human_loop_feedback_001",
        human_attestation=True,
    )
    proposed = workflow.propose_memory(
        source.run_id,
        _head(feedback),
        feedback_id=feedback.payload["feedback_id"],
        idempotency_key="human_loop_memory_proposed_001",
    )
    approved = workflow.decide_memory(
        source.run_id,
        _head(proposed),
        memory_id=proposed.payload["memory_id"],
        revision=proposed.payload["revision"],
        decision=MemoryDecisionValue.APPROVE,
        idempotency_key="human_loop_memory_approved_001",
        human_attestation=True,
    )

    task = GOLDEN.tasks[1]
    common = {
        "store": source.store,
        "artifacts": source.artifacts,
        "source_run_id": source.run_id,
        "source_session_id": source.session_id,
        "source_graph_sha256": reduce_events(
            _events(source.store, source.run_id)
        ).projection_sha256,
        "repo_id": source.handle.repo_id,
        "base_sha": source.handle.base_sha,
        "task": task,
        "target_profile_revision": 1,
        "policy_revision": source.handle.policy_revision,
        "selected_evidence_ids": (hunk_reference.id,),
        "policy_required_paths": (GOLDEN.memory.required_test_path,),
        "read_scope": ("app/auth/limiter.py", "tests/test_security_policy.py"),
        "write_scope": task.expected_changed_paths,
        "fixed_test_profile": GRAPH.required_test_profile,
        "byte_caps": {"read": 32_768, "write": 32_768},
        "event_caps": {"run": 256},
        "server_recorded_at": NOW,
    }
    billing = compile_verified_handoff(
        **common,
        decision_id="human_loop_billing_decision_001",
        brief_id="human_loop_billing_brief_001",
        target_profile=_profile("billing-observer@1"),
        capabilities=(),
    )
    denied = start_fresh_consumer(
        billing,
        tmp_path / "must-not-exist" / "billing.sqlite3",
        repository_root=tmp_path / "must-not-exist",
        injected_at=NOW,
    )
    assert isinstance(denied, HandoffDenied)
    assert denied.model_dispatch_count == 0
    assert denied.consumer_run_id is None
    assert not (tmp_path / "must-not-exist").exists()

    compiled = compile_verified_handoff(
        **common,
        decision_id="human_loop_auth_decision_001",
        brief_id="human_loop_auth_brief_001",
        target_profile=_profile("auth-maintainer@1"),
        capabilities=AUTH_CAPABILITIES,
    )
    consumer = start_fresh_consumer(
        compiled,
        database,
        repository_root=ROOT,
        injected_at=NOW,
    )
    assert isinstance(consumer, FreshConsumer)
    assert consumer.run_id != source.run_id
    assert consumer.session_id != source.session_id
    assert consumer.handle.evidence[0].reference.id == hunk_reference.id

    evidence, limiter, absent_test, execution = asyncio.run(
        _run_resumed_consumer(consumer, database, hunk_reference.id)
    )
    assert evidence["content_sha256"] == hunk.exact_hunk_sha256
    assert absent_test["state"] == "ABSENT" and absent_test["content"] == ""
    assert (
        execution["limiter_write"]["before_file_version_id"]
        == limiter["file_version_id"]
    )
    assert execution["test_write"]["before_file_version_id"] is None
    assert execution["tested"]["passed"] is True
    assert tuple(execution["tested"]["bound_paths"]) == task.expected_changed_paths
    assert execution["completion"] == {
        "status": "denied",
        "reason_code": "human_promotion_required",
        "state": "NEEDS_HUMAN",
    }
    resumed_events = _events(consumer.store, consumer.run_id)
    invocation = next(
        event
        for event in resumed_events
        if event.event_type == LineageEventType.INVOCATION_STARTED
    )
    assert invocation.authority == LineageAuthority.MCP_ADAPTER
    assert invocation.payload["adapter_kind"] == "mcp"
    assert not any(
        event.event_type
        in {
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
            LineageEventType.RUN_INTERRUPTED,
        }
        for event in resumed_events
    )
    assert consumer.checkout_root.is_dir()

    before_promotion = reduce_events(_events(consumer.store, consumer.run_id))
    assert before_promotion.state == LineageRunState.NEEDS_HUMAN
    consumer_events = _events(consumer.store, consumer.run_id)
    consumer_test_event = next(
        event
        for event in consumer_events
        if event.payload.get("operation") == "run_fixed_test"
        and event.payload.get("status") == "completed"
    )
    consumer_workflow = HumanWorkflowService(
        consumer.store,
        consumer.artifacts,
        GOLDEN.memory,
    )
    consumer_changeset = consumer_workflow.derive_changeset(
        consumer.run_id,
        consumer.store.verify(consumer.run_id),
        idempotency_key="human_loop_consumer_changeset_001",
    )
    consumer_workflow.record_test_receipt(
        consumer.run_id,
        _head(consumer_changeset),
        test_event_id=consumer_test_event.event_id,
        idempotency_key="human_loop_consumer_test_receipt_001",
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["GRAPHENE_LINEAGE_DB"] = str(database)
    promoted_result = _tty_cli(
        environment,
        database.parent,
        "promote",
        consumer.run_id,
        "--decision",
        "commit",
    )
    assert promoted_result["state"] == "PROMOTED"
    promoted_retry = _tty_cli(
        environment,
        database.parent,
        "promote",
        consumer.run_id,
        "--decision",
        "commit",
    )
    assert promoted_retry == promoted_result
    explained_process = subprocess.run(
        [
            str(GRAPHENE),
            "--json",
            "why",
            "app/auth/limiter.py",
            "--run",
            consumer.run_id,
        ],
        cwd=database.parent,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert explained_process.returncode == 0, explained_process.stderr.decode()
    explained = json.loads(explained_process.stdout)
    assert {item["relation"] for item in explained["relationships"]} >= {
        "WROTE",
        "VALIDATED",
        "PACKED_IN",
        "INJECTED_INTO",
        "AUTHORIZED",
        "PROMOTED_AS",
    }
    inspected_process = subprocess.run(
        [
            str(GRAPHENE),
            "--json",
            "inspect",
            promoted_result["promotion_receipt_id"],
            "--run",
            consumer.run_id,
        ],
        cwd=database.parent,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert inspected_process.returncode == 0, inspected_process.stderr.decode()
    assert json.loads(inspected_process.stdout)["item"]["type"] == "artifact"

    checkpoints = SQLiteCheckpointRecorder(database)
    promoted = reduce_events(_events(consumer.store, consumer.run_id))
    assert promoted.state == LineageRunState.PROMOTED
    retained = checkpoints.read(consumer.run_id)
    assert len(retained) == 1
    assert retained[0].checkpoint_id == promoted_result["checkpoint_id"]

    restarted_artifacts = SQLiteArtifactStore(database, read_only=True)
    restarted_checkpoints = SQLiteCheckpointRecorder(database, read_only=True)
    restarted_store = SQLiteLineageStore(
        database,
        artifact_resolver=restarted_artifacts.resolve,
        checkpoint_reader=restarted_checkpoints.read,
        read_only=True,
    )
    after_restart = reduce_events(_events(restarted_store, consumer.run_id))
    assert after_restart.state == LineageRunState.PROMOTED
    assert after_restart.projection_sha256 == promoted.projection_sha256
    assert restarted_store.verify(consumer.run_id) == VerifiedHead.model_validate(
        promoted_result["head"]
    )
    source_after_handoff = source.store.verify(source.run_id)
    assert isinstance(source_after_handoff, VerifiedHead)
    assert source_after_handoff.seq == approved.seq + 1
