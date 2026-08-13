from __future__ import annotations

from pathlib import Path

import pytest
from graphene.lineage.promotion import (
    PromotionCheckpointError,
    PromotionConflict,
    PromotionEvidenceError,
    PromotionReceiptV2,
    PromotionRequest,
    PromotionRetestError,
    promote,
)
from graphene.models import LineageEventType, VerifiedHead

from test_promotion import Harness, RUN_ID


def _types(harness: Harness):
    return [event.event_type for event in harness.events()]


class _DroppedCheckpoints:
    def __call__(self, checkpoint):
        pass

    def read(self, run_id):
        return ()


def test_public_callback_cannot_mint_a_self_hashed_arbitrary_receipt(tmp_path: Path):
    harness = Harness(tmp_path)

    def forged(retest):
        return PromotionReceiptV2.create(
            **retest.model_dump(mode="json"),
            receipt_id="promotion_receipt_attacker_minted",
            authoritative_test_receipt_sha256="f" * 64,
            reconstructed_commit_sha="c" * 40,
            passed=True,
            timed_out=False,
        )

    with pytest.raises(PromotionRetestError, match="core-owned"):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=forged,
            record_checkpoint=harness.checkpoint,
        )

    assert LineageEventType.PROMOTION_COMPLETED not in _types(harness)


def test_artifact_substitution_after_approval_cannot_reach_completion(tmp_path: Path):
    harness = Harness(tmp_path)

    def substitute(retest):
        with harness.artifacts._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE lineage_artifacts SET artifact_bytes = ? WHERE artifact_id = ?",
                (b'{"substituted":true}', harness.request.candidate_reference.id),
            )
            connection.commit()
        return harness.receipt(retest)

    with pytest.raises(PromotionEvidenceError, match="invalid"):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=substitute,
            record_checkpoint=harness.checkpoint,
        )

    with harness.store._connect() as connection:
        stored = b"".join(
            row[0] for row in connection.execute("SELECT event_bytes FROM events")
        )
    assert b'"event_type":"promotion.completed"' not in stored


def test_substituted_stale_head_cannot_start_promotion(tmp_path: Path):
    harness = Harness(tmp_path)
    previous = harness.events()[-2]
    stale_head = VerifiedHead(
        run_id=RUN_ID,
        seq=previous.seq,
        event_sha256=previous.event_sha256,
        event_count=previous.seq,
    )
    request = PromotionRequest.model_validate(
        {
            **harness.request.model_dump(mode="json"),
            "expected_head": stale_head.model_dump(mode="json"),
        }
    )

    with pytest.raises(PromotionConflict, match="stale"):
        promote(
            harness.store,
            request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=harness.receipt,
            record_checkpoint=harness.checkpoint,
        )

    assert LineageEventType.PROMOTION_APPROVED not in _types(harness)
    assert not harness.checkpoints


def test_checkpoint_failure_never_exposes_promotion_completed(tmp_path: Path):
    harness = Harness(tmp_path)

    with pytest.raises(PromotionCheckpointError):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=harness.receipt,
            record_checkpoint=_DroppedCheckpoints(),
        )

    assert LineageEventType.PROMOTION_COMPLETED not in _types(harness)
    assert not harness.checkpoints


def test_callback_receipt_type_remains_strict_until_core_replaces_it():
    assert PromotionReceiptV2.model_config["extra"] == "forbid"
