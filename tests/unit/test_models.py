import base64
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from graphene.hashing import (
    canonical_json_bytes,
    canonical_json_sha256,
    candidate_tree_sha256,
    sha256_hex,
)
from graphene.core_models import (
    MAX_TEST_OUTPUT_BYTES,
    CandidateArtifact,
    FileChange,
    HumanDecision,
    MemoryDecisionValue,
    MemoryRef,
    MemoryRevision,
    MemoryState,
    MEMORY_TRANSITIONS,
    PolicyCheck,
    ProofItem,
    ProofType,
    PromotionReceipt,
    RunRecord,
    RunState,
    RUN_TRANSITIONS,
    TaskId,
    TestReceipt as Receipt,
)


def _candidate() -> CandidateArtifact:
    patch = b"diff --git a/a b/a\n"
    base_sha = "a" * 40
    patch_sha = sha256_hex(patch)
    receipt_data = {
        "required_test_profile": "auth-fixture-v1",
        "base_commit_sha": base_sha,
        "candidate_patch_sha256": patch_sha,
        "command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        "candidate_exit_code": 0,
        "base_with_new_test_exit_code": 1,
        "timed_out": False,
        "output_sha256": sha256_hex(b"4 passed"),
        "output_byte_count": len(b"4 passed"),
        "output_truncated": False,
        "duration_bucket": "under_1s",
    }
    receipt = Receipt(
        **receipt_data,
        receipt_sha256=canonical_json_sha256(receipt_data),
    )
    limiter_after = b"changed\n"
    test_after = b"def test_policy(): assert True\n"
    return CandidateArtifact(
        candidate_revision=1,
        base_commit_sha=base_sha,
        canonical_patch_base64=base64.b64encode(patch).decode(),
        candidate_patch_sha256=patch_sha,
        candidate_tree_sha256=candidate_tree_sha256(
            {
                "app/auth/limiter.py": limiter_after,
                "tests/test_security_policy.py": test_after,
            }
        ),
        candidate_tree_hash_version="graphene.tree.v2",
        changed_paths=("app/auth/limiter.py", "tests/test_security_policy.py"),
        file_changes=(
            FileChange(
                path="app/auth/limiter.py",
                before_sha256="b" * 64,
                after_sha256=sha256_hex(limiter_after),
            ),
            FileChange(
                path="tests/test_security_policy.py",
                before_sha256=None,
                after_sha256=sha256_hex(test_after),
            ),
        ),
        test_receipt=receipt,
    )


def test_canonical_hashes_have_known_answers():
    value = {"b": 2, "a": "é"}
    assert canonical_json_bytes(value) == b'{"a":"\xc3\xa9","b":2}'
    assert canonical_json_sha256(value) == (
        "06c264c46ad5ada9493abd3aa2383fb205ae99d7d0bad40b03a43bfec8a1b8de"
    )
    assert candidate_tree_sha256({"b.txt": b"two", "a.txt": b"one"}) == (
        "a0ab16b6a901be5bdee7dd3ac0a6b033bd9c281e1eece44c11ff38e57a1661bf"
    )
    assert (RunState.WAITING_FOR_PROMOTION, RunState.COMPLETED) not in RUN_TRANSITIONS
    assert (MemoryState.APPROVED, MemoryState.PROPOSED) not in MEMORY_TRANSITIONS


def test_candidate_binds_patch_file_hashes_and_passing_receipt():
    candidate = _candidate()
    assert candidate.candidate_patch_sha256 == sha256_hex(
        base64.b64decode(candidate.canonical_patch_base64)
    )

    with pytest.raises(ValidationError):
        CandidateArtifact.model_validate(
            {**candidate.model_dump(), "candidate_patch_sha256": "c" * 64}
        )
    without_version = candidate.model_dump()
    without_version.pop("candidate_tree_hash_version")
    with pytest.raises(ValidationError):
        CandidateArtifact.model_validate(without_version)
    with pytest.raises(ValidationError):
        CandidateArtifact.model_validate(
            {**candidate.model_dump(), "candidate_tree_hash_version": "graphene.tree.v1"}
        )
    with pytest.raises(ValidationError):
        CandidateArtifact.model_validate(
            {
                **candidate.model_dump(),
                "changed_paths": ["docs/security.md"],
                "file_changes": [
                    {
                        **candidate.file_changes[0].model_dump(),
                        "path": "docs/security.md",
                    }
                ],
            }
        )
    oversized_receipt = candidate.test_receipt.model_dump(exclude={"receipt_sha256"})
    oversized_receipt["output_byte_count"] = MAX_TEST_OUTPUT_BYTES + 1
    with pytest.raises(ValidationError):
        Receipt(
            **oversized_receipt,
            receipt_sha256=canonical_json_sha256(oversized_receipt),
        )


def test_only_a_matching_human_decision_can_approve_memory():
    fields = {
        "memory_id": "mem_auth_review",
        "revision": 1,
        "state": MemoryState.APPROVED,
        "rule": "Auth changes require a regression test.",
        "repo_id": "graphene-demo",
        "path_globs": ("app/auth/**",),
        "task_tags": ("authentication", "security"),
        "required_test_path": "tests/test_security_policy.py",
        "required_check": "new_test_fails_on_base_and_passes_on_candidate",
        "evidence_run_id": "baseline_run",
        "feedback_id": "feedback_1",
    }
    with pytest.raises(ValidationError):
        MemoryRevision(**fields)
    with pytest.raises(ValidationError):
        HumanDecision(
            decision_id="decision_1",
            value=MemoryDecisionValue.APPROVE,
            actor="agent",
            purpose="memory",
            bound_digest="a" * 64,
            occurred_at=datetime.now(timezone.utc),
        )

    proposed = MemoryRevision(**{**fields, "state": MemoryState.PROPOSED})
    decision = HumanDecision(
        decision_id="decision_1",
        value=MemoryDecisionValue.APPROVE,
        purpose="memory",
        bound_digest=canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        ),
        occurred_at=datetime.now(timezone.utc),
    )
    assert MemoryRevision(**fields, decision=decision).state == MemoryState.APPROVED


def test_completed_run_binds_the_human_promotion_decision():
    now = datetime.now(timezone.utc)
    candidate = _candidate()
    decision = HumanDecision(
        decision_id="promotion_1",
        value=MemoryDecisionValue.APPROVE,
        purpose="promotion",
        bound_digest=candidate.candidate_patch_sha256,
        occurred_at=now,
    )
    proof = tuple(
        ProofItem(
            event_id=f"event_{sequence}",
            run_id="run_1",
            sequence=sequence,
            type=proof_type,
            occurred_at=now,
        )
        for sequence, proof_type in enumerate(
            (
                ProofType.COMPLETION_DENIED,
                ProofType.PROMOTION_APPROVED,
                ProofType.CANDIDATE_COMMITTED,
            ),
            1,
        )
    )
    receipt = PromotionReceipt(
        run_id="run_1",
        base_commit_sha=candidate.base_commit_sha,
        candidate_patch_sha256=candidate.candidate_patch_sha256,
        candidate_tree_sha256=candidate.candidate_tree_sha256,
        candidate_tree_hash_version=candidate.candidate_tree_hash_version,
        memory_id="mem_auth_review",
        memory_revision=1,
        context_packet_id="ctx_1",
        context_packet_sha256="d" * 64,
        source_graph_revision=1,
        source_graph_hash="e" * 64,
        selected_node_ids=("memory_1",),
        test_receipt_sha256=candidate.test_receipt.receipt_sha256,
        human_decision_id=decision.decision_id,
        expected_run_revision=2,
        commit_sha="c" * 40,
    )
    fields = {
        "run_id": "run_1",
        "task_id": TaskId.ADAPTED_WINDOW_SECONDS,
        "repo_id": "graphene-demo",
        "state": RunState.COMPLETED,
        "revision": 4,
        "agent_profile_id": "auth-maintainer@1",
        "base_sha": candidate.base_commit_sha,
        "allowed_paths": ("app/auth/limiter.py", "tests/test_security_policy.py"),
        "allowed_tools": ("read_file", "write_file", "run_fixture_tests"),
        "fresh_session": True,
        "context_packet_id": "ctx_1",
        "context_packet_sha256": "d" * 64,
        "source_graph_revision": 1,
        "source_graph_hash": "e" * 64,
        "selected_node_ids": ("memory_1",),
        "session_id": "session_1",
        "injected_memories": (MemoryRef(memory_id="mem_auth_review", revision=1),),
        "proof": proof,
        "policy_checks": (
            PolicyCheck(
                policy_check_id="policy_1",
                run_id="run_1",
                policy_revision=1,
                decision="denied",
                reason_codes=("human_approval_missing",),
                candidate_patch_sha256=candidate.candidate_patch_sha256,
                context_packet_sha256="d" * 64,
                test_receipt_sha256=candidate.test_receipt.receipt_sha256,
                occurred_at=now,
            ),
        ),
        "candidate": candidate,
        "promotion_receipt": receipt,
    }
    with pytest.raises(ValidationError):
        RunRecord(**fields)
    completed = RunRecord(**fields, promotion_decision=decision)
    assert completed.state == RunState.COMPLETED
    with pytest.raises(ValidationError):
        RunRecord.model_validate(
            {
                **completed.model_dump(),
                "promotion_receipt": {
                    **receipt.model_dump(),
                    "expected_run_revision": 999,
                },
            }
        )
    with pytest.raises(ValidationError):
        RunRecord.model_validate(
            {
                **completed.model_dump(),
                "state": "queued",
                "revision": 0,
            }
        )
    limiter_only = CandidateArtifact.model_validate(
        {
            **candidate.model_dump(),
            "changed_paths": ["app/auth/limiter.py"],
            "file_changes": [candidate.file_changes[0].model_dump()],
        }
    )
    with pytest.raises(ValidationError):
        RunRecord(**{**fields, "candidate": limiter_only}, promotion_decision=decision)
