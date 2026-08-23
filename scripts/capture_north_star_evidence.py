"""Run the live two-worker Gemini mission once with a durable state directory.

Mirrors tests/process/test_gemini_live.py exactly (same CLI functions, same
assertions as evidence gates) but targets a caller-supplied durable directory
instead of pytest's ephemeral tmp_path, so the mission, its evidence store,
and a capsule export survive the process for citation in the proof record.

Usage:
    GEMINI_API_KEY=... GRAPHENE_RUN_LIVE_GEMINI=1 GRAPHENE_CHECK_EXECUTOR=host-sandbox \
        uv run --frozen python scripts/capture_north_star_evidence.py DEST_DIR

Never prints the API key, prompts, source bytes, or command output. Prints
only sanitized identifiers, digests, and counts, and writes the same to
DEST_DIR/evidence.json. Fails loudly and leaves nothing half-written if any
assertion the gated test itself makes does not hold.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from graphene.cli import mission as mission_cli
from graphene.hashing import sha256_hex
from graphene.orchestration.adk import LIVE_GEMINI_MODEL
from graphene.orchestration.capsule import export_mission_capsule
from graphene.orchestration.models import AttemptState, MissionStatus, TaskKind
from graphene.orchestration.runtime import (
    WORKER_PROVIDER_RECEIPT_KIND,
    WorkerProviderReceipt,
)


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


def main(dest: Path) -> int:
    if dest.exists() and any(dest.iterdir()):
        print(f"refusing: {dest} already exists and is not empty", file=sys.stderr)
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)

    repository = dest / "source"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Graphene North Star Capture")
    _git(repository, "config", "user.email", "north-star@graphene.invalid")
    (repository / "README.md").write_text(
        "# Live North Star capture fixture\n", encoding="utf-8"
    )
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "base")
    mission_cli.initialize(repository)
    source_status = _git(repository, "status", "--porcelain=v1")
    source_head = _git(repository, "rev-parse", "HEAD")

    os.environ["GRAPHENE_STATE_DIR"] = str(dest / "state")

    start_args = argparse.Namespace(
        repo=repository,
        goal="Create two independent bounded reports under .graphene/generated.",
        success_criteria=[
            "Two reviewed generated reports are assembled and structurally verified."
        ],
        driver="gemini-adk",
        max_workers=2,
        auto_approve=False,
        command_id="command_north_star_capture_001",
        open_viewer=False,
    )
    proposed = mission_cli._start(start_args)
    mission_id = proposed["mission_id"]
    assert proposed["status"] == "proposed"
    assert proposed["requested_model"] == LIVE_GEMINI_MODEL
    assert proposed["returned_model"]

    completed = mission_cli._mutate(
        argparse.Namespace(
            mission_action="approve-plan",
            mission_id=mission_id,
            revision=1,
            operator_label="north-star-capture-operator",
            rationale="Explicit approval to capture durable North Star evidence.",
            confirm_human=False,
            command_id="command_north_star_capture_approve_001",
        )
    )
    assert completed["status"] == MissionStatus.AWAITING_RESULT
    assert completed["execution_mode"] == "gemini_live"
    assert len(completed["worker_session_ids"]) >= 2
    assert len(completed["provider_receipts"]) >= 2
    assert completed["parallel_overlap_observed"] is True
    assert completed["provider_call_overlap_observed"] is True
    assert completed["receipt_unknowns"] == []

    store = mission_cli._store_for_mission(mission_id)
    evidence = mission_cli._mission_evidence(store, mission_id)
    receipt_fingerprints = []
    for reference in completed["provider_receipt_references"]:
        assert reference["kind"] == WORKER_PROVIDER_RECEIPT_KIND
        content = evidence.resolve(reference["kind"], reference["id"])
        assert content is not None
        assert sha256_hex(content) == reference["sha256"]
        receipt = WorkerProviderReceipt.model_validate_json(content)
        assert receipt.driver == "gemini_live"
        receipt_fingerprints.append(
            {
                "attempt_id": reference["attempt_id"],
                "worker_id": reference["worker_id"],
                "sha256": reference["sha256"],
                "requested_model": receipt.requested_model,
                "returned_model": receipt.returned_model,
                "credential_mode": receipt.credential_mode,
                "usage_source": receipt.usage_source,
            }
        )
    head = store.verify(mission_id)
    assert head == store.head(mission_id)
    snapshot = store.snapshot(mission_id)
    kinds = {item.task_id: item.kind for item in snapshot.tasks}
    work = tuple(
        item
        for item in snapshot.attempts
        if kinds[item.task_id] == TaskKind.WORK
        and item.state == AttemptState.COMMITTED
    )
    assert len(work) >= 2
    first, second = work[:2]
    assert len({first.worker_id, second.worker_id}) == 2
    assert len({first.session_id, second.session_id}) == 2

    capsule_dir = dest / "capsule"
    capsule_dir.mkdir()
    exported = export_mission_capsule(
        store=store, evidence=evidence, mission_id=mission_id, output_dir=capsule_dir
    )

    record = {
        "mission_id": mission_id,
        "head": {"seq": head.seq, "event_sha256": head.event_sha256},
        "worker_session_ids": completed["worker_session_ids"],
        "worker_invocation_ids": completed["worker_invocation_ids"],
        "receipt_fingerprints": receipt_fingerprints,
        "parallel_overlap": completed["parallel_overlap"],
        "capsule_dir": exported["capsule_dir"],
        "capsule_manifest_sha256": exported["files"]["manifest.json"]["sha256"]
        if isinstance(exported.get("files"), dict)
        and "manifest.json" in exported["files"]
        else None,
        "source_checkout_unchanged": _git(repository, "status", "--porcelain=v1")
        == source_status
        and _git(repository, "rev-parse", "HEAD") == source_head,
    }
    (dest / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dest", type=Path)
    args = parser.parse_args()
    raise SystemExit(main(args.dest.resolve()))
