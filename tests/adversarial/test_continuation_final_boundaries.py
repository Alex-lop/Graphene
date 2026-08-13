from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene.bootstrap import bootstrap_local_run
from graphene.context.consumer import resume_fresh_consumer
from graphene.execution import run_fixture_tests
from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.lineage import HumanWorkflowService
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import (
    PromotionConflict,
    PromotionRetestResult,
    SQLiteCheckpointRecorder,
    prepare_verified_promotion,
    promote,
)
from graphene.lineage.reducer import reduce_events
from graphene.lineage.service import ToolCallIdentity
from graphene.lineage.store import LineageConflict, SQLiteLineageStore
from graphene.models import GoldenContract, LineageEventType, LineageRunState, VerifiedHead


ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)


class _FailCompletionAppend:
    def __init__(self, store: SQLiteLineageStore) -> None:
        self.store = store

    def append(self, run_id, expected_head, idempotency_key, draft):
        if draft.event_type == LineageEventType.PROMOTION_COMPLETED:
            raise LineageConflict("simulated final append outage")
        return self.store.append(run_id, expected_head, idempotency_key, draft)

    def tail(self, run_id, after_seq, limit):
        return self.store.tail(run_id, after_seq, limit)

    def verify(self, run_id):
        return self.store.verify(run_id)


def _call(run, number: int) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.handle.model_id,
        tool_call_id=f"final_boundary_call_{number:03d}",
        agent_name="graphene_local",
        adapter_kind="local",
    )


def _cli(environment: dict[str, str], cwd: Path, *arguments: str) -> dict:
    result = subprocess.run(
        [str(GRAPHENE), "--json", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stderr == b""
    return json.loads(result.stdout)


def _events(store: SQLiteLineageStore, run_id: str):
    head = store.verify(run_id)
    assert isinstance(head, VerifiedHead)
    return store.tail(run_id, 0, head.seq)


def test_retained_promotion_precommit_recovers_after_final_append_failure(
    tmp_path: Path,
) -> None:
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
    assert source.service.run_fixed_test(source.handle, _call(source, 3)).passed
    source.service.request_completion(source.handle, _call(source, 4))

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["GRAPHENE_LINEAGE_DB"] = str(database)
    review = _cli(environment, runtime, "review", source.run_id)
    asked = _cli(
        environment,
        runtime,
        "feedback",
        review["hunks"][0]["hunk_id"],
        "--event",
        review["write_event_ids"][0],
        "--run",
        source.run_id,
        "--message",
        GOLDEN.memory.correction,
    )
    answered = _cli(
        environment,
        runtime,
        "answer",
        asked["question_id"],
        "--choice",
        "all_auth",
    )
    _cli(environment, runtime, "memory", "approve", answered["memory_id"])
    started = _cli(
        environment,
        runtime,
        "handoff",
        source.run_id,
        "--to",
        "auth-maintainer@1",
        "--task",
        "adapted_window_seconds",
        "--start",
    )

    consumer = resume_fresh_consumer(
        database,
        started["consumer_run_id"],
        repository_root=ROOT,
    )
    limiter = consumer.service.read_file(
        consumer.handle,
        _call(consumer, 5),
        path="app/auth/limiter.py",
    )
    consumer.service.read_file(
        consumer.handle,
        _call(consumer, 6),
        path="tests/test_security_policy.py",
    )
    consumer.service.write_file(
        consumer.handle,
        _call(consumer, 7),
        path="app/auth/limiter.py",
        content=limiter.content.replace("WINDOW_SECONDS = 60", "WINDOW_SECONDS = 90"),
    )
    consumer.service.write_file(
        consumer.handle,
        _call(consumer, 8),
        path="tests/test_security_policy.py",
        content=GOLDEN.memory.expected_security_test_content,
    )
    assert consumer.service.run_fixed_test(consumer.handle, _call(consumer, 9)).passed
    consumer.service.request_completion(consumer.handle, _call(consumer, 10))

    workflow = HumanWorkflowService(consumer.store, consumer.artifacts, GOLDEN.memory)
    changeset = workflow.derive_changeset(
        consumer.run_id,
        consumer.handle.head,
        idempotency_key="final_boundary_changeset_001",
    )
    test_event = next(
        event
        for event in _events(consumer.store, consumer.run_id)
        if event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == "run_fixed_test"
    )
    workflow.record_test_receipt(
        consumer.run_id,
        VerifiedHead(
            run_id=consumer.run_id,
            seq=changeset.seq,
            event_sha256=changeset.event_sha256,
            event_count=changeset.seq,
        ),
        test_event_id=test_event.event_id,
        idempotency_key="final_boundary_test_receipt_001",
    )

    checkpoints = SQLiteCheckpointRecorder(database)
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(
        database,
        artifact_resolver=artifacts.resolve,
        checkpoint_reader=checkpoints.read,
    )
    request = prepare_verified_promotion(
        store,
        artifacts,
        consumer.run_id,
        decision_id="final_boundary_promotion_001",
        occurred_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )

    def authoritative_retest(retest) -> PromotionRetestResult:
        result = run_fixture_tests(consumer.checkout_root, GOLDEN.fixture)
        return PromotionRetestResult(
            authoritative_test_receipt_sha256=canonical_json_sha256(
                {
                    "bound_candidate": retest.candidate_patch_sha256,
                    "command": list(GOLDEN.fixture.fixed_test_command),
                    "exit_code": result.exit_code,
                    "output_sha256": sha256_hex(result.output.encode()),
                    "timed_out": result.timed_out,
                }
            ),
            reconstructed_commit_sha=retest.base_sha,
            passed=result.exit_code == 0,
            timed_out=result.timed_out,
        )

    with pytest.raises(PromotionConflict, match="completion append"):
        promote(
            _FailCompletionAppend(store),
            request,
            record_artifact=artifacts,
            reconstruct_and_retest=authoritative_retest,
            record_checkpoint=checkpoints,
        )

    interrupted = _events(store, consumer.run_id)
    assert interrupted[-1].event_type == LineageEventType.PROMOTION_APPROVED
    assert reduce_events(interrupted).state == LineageRunState.NEEDS_HUMAN
    assert len(checkpoints.read(consumer.run_id)) == 1

    retry = subprocess.run(
        [str(GRAPHENE), "--json", "promote", consumer.run_id],
        cwd=runtime,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert retry.returncode == 0, retry.stderr.decode(errors="replace")
    assert retry.stderr == b""
    assert json.loads(retry.stdout)["state"] == "PROMOTED"
