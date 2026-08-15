from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from difflib import unified_diff
from pathlib import Path

import pytest
from graphene.hashing import canonical_json_sha256, candidate_tree_sha256, sha256_hex
from graphene.lineage.local_commit import (
    LOCAL_COMMIT_APPROVAL_LABEL,
    LOCAL_COMMIT_RESULT_LABEL,
    LocalCommitError,
    LocalCommitRequest,
    create_isolated_local_commit,
    local_commit_event_input,
)
from graphene.models import (
    EvidenceKind,
    EvidenceReference,
    HumanDecision,
    MemoryDecisionValue,
)
from pydantic import ValidationError


def _git(checkout: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=checkout,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _patch(path: str, before: str, after: str) -> bytes:
    body = "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
            lineterm="\n",
        )
    )
    return f"diff --git a/{path} b/{path}\n{body}".encode()


def _repository(tmp_path: Path) -> tuple[Path, Path, str, str, bytes]:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    checkout = runtime / "checkouts" / "run_local_commit_001"
    checkout.mkdir(parents=True)
    path = checkout / "app/auth/limiter.py"
    path.parent.mkdir(parents=True)
    before = "MAX_ATTEMPTS = 5\n"
    after = "MAX_ATTEMPTS = 4\n"
    path.write_text(before)
    _git(checkout, "init", "--quiet", "--initial-branch=main")
    _git(checkout, "-c", "user.name=Fixture", "-c", "user.email=f@invalid", "add", "--all")
    _git(
        checkout,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=f@invalid",
        "commit",
        "--quiet",
        "-m",
        "baseline",
    )
    base_sha = _git(checkout, "rev-parse", "HEAD")
    path.write_text(after)
    return runtime, checkout, base_sha, after, _patch("app/auth/limiter.py", before, after)


def _request(base_sha: str, after: str, patch: bytes, *, approve: bool = True):
    patch_sha = sha256_hex(patch)
    return LocalCommitRequest(
        run_id="run_local_commit_001",
        repo_id="graphene-demo",
        base_sha=base_sha,
        candidate_patch=patch,
        candidate_patch_sha256=patch_sha,
        candidate_tree_sha256=candidate_tree_sha256(
            {"app/auth/limiter.py": after.encode()}
        ),
        changed_paths=("app/auth/limiter.py",),
        test_reference=EvidenceReference(
            kind=EvidenceKind.TEST_RECEIPT,
            id="test_receipt_001",
            sha256="1" * 64,
        ),
        authoritative_test_receipt_sha256="2" * 64,
        approval=HumanDecision(
            decision_id="approval_decision_001",
            value=(
                MemoryDecisionValue.APPROVE
                if approve
                else MemoryDecisionValue.REJECT
            ),
            purpose="promotion",
            bound_digest=patch_sha,
            occurred_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        ),
        approval_reference=EvidenceReference(
            kind=EvidenceKind.EVENT,
            id="approval_event_001",
            sha256="3" * 64,
        ),
        promotion_reference=EvidenceReference(
            kind=EvidenceKind.PROMOTION_RECEIPT,
            id="promotion_receipt_001",
            sha256="4" * 64,
        ),
    )


def test_isolated_commit_is_exact_verified_and_idempotent(tmp_path: Path, monkeypatch):
    runtime, checkout, base_sha, after, patch = _repository(tmp_path)
    request = _request(base_sha, after, patch)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "must-not-be-used")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "must-not-be-used@example.com")

    receipt = create_isolated_local_commit(runtime, request)
    retried = create_isolated_local_commit(runtime, request)
    receipt_reference = EvidenceReference(
        kind=EvidenceKind.LOCAL_COMMIT_RECEIPT,
        id="local_commit_receipt_001",
        sha256=canonical_json_sha256(receipt.model_dump(mode="json")),
    )
    idempotency_key, event = local_commit_event_input(
        receipt,
        receipt_reference,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
    )

    assert LOCAL_COMMIT_APPROVAL_LABEL == "Approve and create isolated local commit"
    assert receipt == retried
    assert receipt.result_label == LOCAL_COMMIT_RESULT_LABEL
    assert receipt.parent_sha == _git(checkout, "rev-parse", f"{receipt.local_commit_sha}^")
    assert receipt.tree_sha == _git(checkout, "rev-parse", f"{receipt.local_commit_sha}^{{tree}}")
    assert _git(checkout, "cat-file", "-e", f"{receipt.local_commit_sha}^{{commit}}") == ""
    assert _git(checkout, "diff", "--name-only", base_sha, receipt.local_commit_sha) == (
        "app/auth/limiter.py"
    )
    assert _git(
        checkout,
        "show",
        f"{receipt.local_commit_sha}:app/auth/limiter.py",
    ) == after.strip()
    assert _git(checkout, "rev-list", "--count", "HEAD") == "2"
    assert _git(checkout, "config", "--local", "user.name") == "Graphene Isolated Fixture"
    assert _git(checkout, "show", "-s", "--format=%an <%ae>", "HEAD") == (
        "Graphene Isolated Fixture <graphene-fixture@invalid>"
    )
    assert not receipt.pushed and not receipt.pull_request_created and not receipt.deployed
    assert idempotency_key.startswith("local_result_")
    assert event.payload["local_commit_sha"] == receipt.local_commit_sha
    assert event.payload["outcome"] == "local_isolated_commit"
    assert {reference.kind for reference in event.references} == {
        EvidenceKind.EVENT,
        EvidenceKind.PROMOTION_RECEIPT,
        EvidenceKind.TEST_RECEIPT,
        EvidenceKind.LOCAL_COMMIT_RECEIPT,
    }


def test_rejection_and_extra_checkout_changes_create_no_commit(tmp_path: Path):
    runtime, checkout, base_sha, after, patch = _repository(tmp_path)
    with pytest.raises(ValidationError, match="exact and approved"):
        _request(base_sha, after, patch, approve=False)
    assert _git(checkout, "rev-parse", "HEAD") == base_sha

    (checkout / "viewer.sqlite3").write_text("not candidate evidence")
    with pytest.raises(LocalCommitError, match="checkout changes"):
        create_isolated_local_commit(runtime, _request(base_sha, after, patch))
    assert _git(checkout, "rev-parse", "HEAD") == base_sha
