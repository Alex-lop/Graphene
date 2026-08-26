from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import pytest

from graphene.cli import mission as mission_cli
from graphene.hashing import sha256_hex
from graphene.orchestration.adk_planner import LIVE_GEMINI_MODEL
from graphene.orchestration.mission_models import AttemptState, MissionStatus, TaskKind
from graphene.orchestration.worker_runtime import (
    WORKER_PROVIDER_RECEIPT_KIND,
    WorkerProviderReceipt,
)


def _credentials_configured() -> bool:
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
    if vertex in {"1", "true"}:
        return bool(
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            and os.environ.get("GOOGLE_CLOUD_LOCATION")
        )
    return sum(
        bool(os.environ.get(name)) for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    ) == 1


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


@pytest.mark.skipif(
    os.environ.get("GRAPHENE_RUN_LIVE_GEMINI") != "1"
    or not _credentials_configured(),
    reason=(
        "NOT PROVEN: set GRAPHENE_RUN_LIVE_GEMINI=1 with one valid Gemini "
        "credential mode to run the paid full two-worker mission"
    ),
)
def test_real_gemini_runs_the_full_two_worker_mission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "source"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Graphene Live Test")
    _git(repository, "config", "user.email", "live@graphene.invalid")
    (repository / "README.md").write_text("# Live bounded fixture\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "base")
    mission_cli.initialize(repository)
    source_status = _git(repository, "status", "--porcelain=v1")
    source_head = _git(repository, "rev-parse", "HEAD")
    source_ref = _git(repository, "symbolic-ref", "HEAD")
    source_remote_refs = _git(
        repository, "for-each-ref", "--format=%(refname):%(objectname)", "refs/remotes"
    )
    source_readme = (repository / "README.md").read_bytes()
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "state"))

    start_args = argparse.Namespace(
        repo=repository,
        goal="Create two independent bounded reports under .graphene/generated.",
        success_criteria=[
            "Two reviewed generated reports are assembled and structurally verified."
        ],
        driver="gemini-adk",
        max_workers=2,
        auto_approve=False,
        command_id="command_live_gemini_full_path_001",
        open_viewer=False,
    )
    proposed = mission_cli._start(start_args)
    mission_id = proposed["mission_id"]

    assert proposed["status"] == "proposed"
    assert proposed["review_required"] is True
    assert proposed["requested_model"] == LIVE_GEMINI_MODEL
    assert proposed["returned_model"]
    assert len(
        [item for item in proposed["task_graph"] if item["kind"] == "work"]
    ) >= 2

    # The paid live run gets one explicit approval and has no fake fallback.
    completed = mission_cli._mutate(
        argparse.Namespace(
            mission_action="approve-plan",
            mission_id=mission_id,
            revision=1,
            operator_label="live-test-operator",
            rationale="Explicitly approve the paid gated live mission plan.",
            confirm_human=False,
            command_id="command_live_gemini_approve_001",
        )
    )

    assert completed["status"] == MissionStatus.AWAITING_RESULT
    assert completed["execution_mode"] == "gemini_live"
    assert completed["review_required"] is True
    assert len(completed["worker_session_ids"]) >= 2
    assert len(completed["worker_invocation_ids"]) >= 2
    assert len(completed["provider_receipts"]) >= 2
    for receipt in completed["provider_receipts"]:
        assert receipt["driver"] == "gemini_live"
        assert receipt["requested_model"] == LIVE_GEMINI_MODEL
        assert receipt["returned_model"]
        assert receipt["input_bytes"] > 0
        assert receipt["output_bytes"] > 0
        assert receipt["usage_source"] in {"provider_reported", "unavailable"}
        assert "prompt" not in receipt and "output" not in receipt
    # Lifetime overlap comes from durable attempt and lease timestamps; the
    # real-agent claim cites the provider-call windows the runtime stamped
    # into the evidence-bound receipts. Every receipt is cited by an evidence
    # reference that resolves.
    assert completed["parallel_overlap_observed"] is True
    assert completed["parallel_overlap"]["max_window_ms"] > 0
    assert completed["provider_call_overlap_observed"] is True
    assert completed["parallel_overlap"]["provider_call_observed"] is True
    assert completed["parallel_overlap"]["provider_call_max_window_ms"] > 0
    assert {item["basis"] for item in completed["parallel_overlap"]["pairs"]} == {
        "attempt_timestamps",
        "lease_timestamps",
        "provider_call_timestamps",
    }
    assert completed["receipt_unknowns"] == []
    assert len(completed["provider_receipt_references"]) >= 2

    store = mission_cli._store_for_mission(mission_id)
    evidence = mission_cli._mission_evidence(store, mission_id)
    for reference in completed["provider_receipt_references"]:
        assert reference["kind"] == WORKER_PROVIDER_RECEIPT_KIND
        content = evidence.resolve(reference["kind"], reference["id"])
        assert content is not None
        assert sha256_hex(content) == reference["sha256"]
        assert WorkerProviderReceipt.model_validate_json(content).driver == (
            "gemini_live"
        )
    assert store.verify(mission_id) == store.head(mission_id)
    snapshot = store.snapshot(mission_id)
    kinds = {item.task_id: item.kind for item in snapshot.tasks}
    work = tuple(
        item
        for item in snapshot.attempts
        if kinds[item.task_id] == TaskKind.WORK
        and item.state == AttemptState.COMMITTED
    )
    assert len(work) >= 2
    for attempt in work:
        assert (
            sum(item.kind == WORKER_PROVIDER_RECEIPT_KIND for item in attempt.evidence_refs)
            == 1
        )
    first, second = work[:2]
    assert len({first.worker_id, second.worker_id}) == 2
    assert len({first.session_id, second.session_id}) == 2
    assert len({first.invocation_id, second.invocation_id}) == 2
    assert len({first.workspace_id, second.workspace_id}) == 2
    assert len({first.attempt_id, second.attempt_id}) == 2
    assert len({first.lease_id, second.lease_id}) == 2
    assert len(
        {
            (first.lease_id, first.fencing_token),
            (second.lease_id, second.fencing_token),
        }
    ) == 2
    assert first.started_at < second.ended_at and second.started_at < first.ended_at

    assembly = next(
        item
        for item in snapshot.attempts
        if kinds[item.task_id] == TaskKind.ASSEMBLY
        and item.state == AttemptState.COMMITTED
    )
    verification = next(
        item
        for item in snapshot.attempts
        if kinds[item.task_id] == TaskKind.VERIFICATION
        and item.state == AttemptState.COMMITTED
    )
    assert len(assembly.input_publications) >= 2
    assert len(verification.input_publications) == 1
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert snapshot.mission.final_outcome is None
    assert _git(repository, "status", "--porcelain=v1") == source_status
    assert _git(repository, "rev-parse", "HEAD") == source_head
    assert _git(repository, "symbolic-ref", "HEAD") == source_ref
    assert (
        _git(
            repository,
            "for-each-ref",
            "--format=%(refname):%(objectname)",
            "refs/remotes",
        )
        == source_remote_refs
    )
    assert (repository / "README.md").read_bytes() == source_readme
