from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..hashing import canonical_json_sha256, sha256_hex
from ..models import FrozenModel, GitSha, Identifier, RepoPath, Sha256, TruthKind
from .evidence import SQLiteAttemptEvidenceStore
from .models import EvidenceReference
from .scripted import ScriptedError, _git


_OPERATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._@-]{0,63}$")
_COMMIT_MESSAGE = "Graphene approved isolated mission result"


class LocalResultError(RuntimeError):
    pass


class LocalResultReceipt(FrozenModel):
    schema_version: Literal[1] = 1
    receipt_id: Identifier
    mission_id: Identifier
    decision: Literal["approve", "reject"]
    truth_kind: TruthKind
    operator_label: str = Field(min_length=1, max_length=64)
    rationale_sha256: Sha256 | None = None
    base_sha: GitSha
    candidate_patch_sha256: Sha256
    verification_id: Identifier
    verification_sha256: Sha256
    changed_paths: tuple[RepoPath, ...] = ()
    local_commit_sha: GitSha | None = None
    result_ref: str | None = Field(default=None, max_length=128)
    outcome: Literal["isolated_local_commit", "rejected_no_commit"]
    pushed: Literal[False] = False
    pull_request_created: Literal[False] = False
    deployed: Literal[False] = False
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def exact_result(self) -> LocalResultReceipt:
        approved = self.decision == "approve"
        if (
            approved != (self.local_commit_sha is not None)
            or approved != (self.result_ref is not None)
            or approved != bool(self.changed_paths)
            or approved != (self.outcome == "isolated_local_commit")
            or self.changed_paths != tuple(sorted(set(self.changed_paths)))
        ):
            raise ValueError("local result fields do not match the decision")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        )
        if self.receipt_sha256 != expected:
            raise ValueError("local result receipt digest does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> LocalResultReceipt:
        core = {"schema_version": 1, **values}
        core.pop("receipt_id", None)
        core.pop("receipt_sha256", None)
        receipt_id = "local_result_" + canonical_json_sha256(core)[:32]
        record = {"receipt_id": receipt_id, **core}
        canonical = cls.model_construct(**record, receipt_sha256="0" * 64).model_dump(
            mode="json", exclude={"receipt_sha256"}
        )
        return cls.model_validate(
            {**canonical, "receipt_sha256": canonical_json_sha256(canonical)}
        )


def _owned_repository(runtime: Path, repository: Path) -> tuple[Path, Path]:
    try:
        runtime_metadata = runtime.lstat()
        repository_metadata = repository.lstat()
    except OSError as error:
        raise LocalResultError(
            "Graphene-owned result repository is unavailable"
        ) from error
    if (
        stat.S_ISLNK(runtime_metadata.st_mode)
        or stat.S_ISLNK(repository_metadata.st_mode)
        or not stat.S_ISDIR(runtime_metadata.st_mode)
        or not stat.S_ISDIR(repository_metadata.st_mode)
    ):
        raise LocalResultError("result creation requires a Graphene-owned repository")
    runtime = runtime.resolve(strict=True)
    repository = repository.resolve(strict=True)
    git_directory = repository / ".git"
    try:
        git_metadata = git_directory.lstat()
    except OSError as error:
        raise LocalResultError(
            "Graphene-owned result repository is unavailable"
        ) from error
    if (
        repository != runtime / "repository"
        or stat.S_ISLNK(git_metadata.st_mode)
        or not stat.S_ISDIR(git_metadata.st_mode)
    ):
        raise LocalResultError("result creation requires a Graphene-owned repository")
    return runtime, repository


def _verification(
    evidence: SQLiteAttemptEvidenceStore,
    reference: EvidenceReference,
    candidate_sha256: str,
) -> None:
    if reference.kind != "test-receipt":
        raise LocalResultError("final result is not bound to a test receipt")
    raw = evidence.resolve(reference.kind, reference.id)
    try:
        receipt = json.loads(raw) if raw is not None else None
    except (TypeError, ValueError, UnicodeError) as error:
        raise LocalResultError("verification receipt is unreadable") from error
    if (
        not isinstance(receipt, dict)
        or receipt.get("template_id") != "fixture-tests"
        or receipt.get("candidate_patch_sha256") != candidate_sha256
        or receipt.get("accepted_input_sha256") != [candidate_sha256]
        or receipt.get("exit_code") != 0
        or receipt.get("timed_out") is not False
        or sha256_hex(raw) != reference.sha256
    ):
        raise LocalResultError("verification receipt did not pass the bound check")


def _rationale_digest(rationale: str | None) -> str | None:
    if rationale is None:
        return None
    if not 1 <= len(rationale) <= 280:
        raise LocalResultError("operator rationale must be bounded")
    return sha256_hex(rationale.encode())


def _require_decision_truth(truth_kind: TruthKind) -> None:
    if truth_kind not in {
        TruthKind.HUMAN_ATTESTED,
        TruthKind.SERVER_DERIVED,
        TruthKind.SIMULATED_FIXTURE,
    }:
        raise LocalResultError("final result truth kind is not an operator decision")


def _common(
    *,
    mission_id: str,
    base_sha: str,
    candidate: EvidenceReference,
    verification: EvidenceReference,
    evidence: SQLiteAttemptEvidenceStore,
    operator_label: str,
    rationale: str | None,
) -> dict[str, object]:
    if not _OPERATOR.fullmatch(operator_label):
        raise LocalResultError("operator label is invalid")
    patch = evidence.resolve("patch", candidate.id)
    if (
        candidate.kind != "patch"
        or patch is None
        or sha256_hex(patch) != candidate.sha256
    ):
        raise LocalResultError("candidate patch is unavailable")
    _verification(evidence, verification, candidate.sha256)
    return {
        "mission_id": mission_id,
        "operator_label": operator_label,
        "rationale_sha256": _rationale_digest(rationale),
        "base_sha": base_sha,
        "candidate_patch_sha256": candidate.sha256,
        "verification_id": verification.id,
        "verification_sha256": verification.sha256,
    }


def reject_result(
    *,
    runtime: Path,
    repository: Path,
    mission_id: str,
    base_sha: str,
    candidate: EvidenceReference,
    verification: EvidenceReference,
    evidence: SQLiteAttemptEvidenceStore,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
) -> LocalResultReceipt:
    _require_decision_truth(truth_kind)
    runtime, repository = _owned_repository(runtime, repository)
    del runtime
    result_ref = _result_ref(mission_id)
    try:
        _git(repository, "rev-parse", "--verify", result_ref)
    except ScriptedError:
        pass
    else:
        raise LocalResultError("an approved result already exists")
    return LocalResultReceipt.create(
        **_common(
            mission_id=mission_id,
            base_sha=base_sha,
            candidate=candidate,
            verification=verification,
            evidence=evidence,
            operator_label=operator_label,
            rationale=rationale,
        ),
        decision="reject",
        truth_kind=truth_kind,
        changed_paths=(),
        local_commit_sha=None,
        result_ref=None,
        outcome="rejected_no_commit",
    )


def _result_ref(mission_id: str) -> str:
    return "refs/graphene/results/" + sha256_hex(mission_id.encode())[:24]


def _existing_result(
    repository: Path,
    result_ref: str,
    base_sha: str,
    candidate_sha256: str,
) -> tuple[str, tuple[str, ...]] | None:
    try:
        commit_sha = (
            _git(repository, "rev-parse", "--verify", result_ref).decode().strip()
        )
    except ScriptedError:
        return None
    try:
        if _git(repository, "rev-parse", f"{commit_sha}^").decode().strip() != base_sha:
            raise LocalResultError("existing isolated commit has another parent")
        committed_patch = _git(
            repository, "diff", "--binary", base_sha, commit_sha, "--"
        )
        if sha256_hex(committed_patch) != candidate_sha256:
            raise LocalResultError("existing isolated commit has another candidate")
        changed_paths = tuple(
            sorted(
                item.decode()
                for item in _git(
                    repository,
                    "diff",
                    "--name-only",
                    "-z",
                    base_sha,
                    commit_sha,
                    "--",
                ).split(b"\0")
                if item
            )
        )
    except ScriptedError as error:
        raise LocalResultError("existing isolated result is invalid") from error
    if not changed_paths:
        raise LocalResultError("existing isolated result is empty")
    return commit_sha, changed_paths


def verify_local_result_receipt(
    receipt_bytes: bytes,
    *,
    runtime: Path,
    repository: Path,
) -> bool:
    """Verify that a receipt names the exact Graphene-owned isolated commit."""

    try:
        receipt = LocalResultReceipt.model_validate_json(receipt_bytes)
        runtime, repository = _owned_repository(runtime, repository)
        del runtime
        if (
            receipt.decision != "approve"
            or receipt.outcome != "isolated_local_commit"
            or receipt.result_ref != _result_ref(receipt.mission_id)
            or receipt.local_commit_sha is None
        ):
            return False
        existing = _existing_result(
            repository,
            receipt.result_ref,
            receipt.base_sha,
            receipt.candidate_patch_sha256,
        )
        return existing == (receipt.local_commit_sha, receipt.changed_paths)
    except (LocalResultError, TypeError, ValueError):
        return False


def _approved_receipt(
    common: dict[str, object],
    truth_kind: TruthKind,
    result_ref: str,
    existing: tuple[str, tuple[str, ...]],
) -> LocalResultReceipt:
    commit_sha, changed_paths = existing
    return LocalResultReceipt.create(
        **common,
        decision="approve",
        truth_kind=truth_kind,
        changed_paths=changed_paths,
        local_commit_sha=commit_sha,
        result_ref=result_ref,
        outcome="isolated_local_commit",
    )


def approve_result(
    *,
    runtime: Path,
    repository: Path,
    mission_id: str,
    base_sha: str,
    candidate: EvidenceReference,
    approved_candidate_sha256: str,
    verification: EvidenceReference,
    evidence: SQLiteAttemptEvidenceStore,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
    allow_simulated_fixture: bool = False,
) -> LocalResultReceipt:
    try:
        import fcntl
    except ImportError as error:
        raise LocalResultError(
            "isolated local result locking is unavailable on this platform"
        ) from error

    runtime, repository = _owned_repository(runtime, repository)
    if candidate.sha256 != approved_candidate_sha256:
        raise LocalResultError("approval does not bind the exact candidate")
    if truth_kind == TruthKind.SIMULATED_FIXTURE and not allow_simulated_fixture:
        raise LocalResultError("simulated approval was not explicitly enabled")
    _require_decision_truth(truth_kind)
    common = _common(
        mission_id=mission_id,
        base_sha=base_sha,
        candidate=candidate,
        verification=verification,
        evidence=evidence,
        operator_label=operator_label,
        rationale=rationale,
    )
    patch = evidence.resolve("patch", candidate.id)
    assert patch is not None
    result_ref = _result_ref(mission_id)
    existing = _existing_result(repository, result_ref, base_sha, candidate.sha256)
    if existing is not None:
        return _approved_receipt(common, truth_kind, result_ref, existing)
    result_parent = runtime / "results"
    result_parent.mkdir(mode=0o700, exist_ok=True)
    result_metadata = result_parent.lstat()
    if (
        stat.S_ISLNK(result_metadata.st_mode)
        or not stat.S_ISDIR(result_metadata.st_mode)
        or stat.S_IMODE(result_metadata.st_mode) & 0o077
    ):
        raise LocalResultError("Graphene-owned result directory is unsafe")
    workspace = result_parent / sha256_hex(mission_id.encode())[:24]
    lock_path = result_parent / f"{workspace.name}.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        lock_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or stat.S_IMODE(lock_metadata.st_mode) & 0o077
        ):
            raise LocalResultError("Graphene-owned result lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        existing = _existing_result(repository, result_ref, base_sha, candidate.sha256)
        if existing is not None:
            return _approved_receipt(common, truth_kind, result_ref, existing)
        if workspace.is_symlink() or (workspace.exists() and not workspace.is_dir()):
            raise LocalResultError("Graphene-owned result workspace is unsafe")
        if workspace.exists():
            try:
                _git(repository, "worktree", "remove", "--force", str(workspace))
            except ScriptedError:
                if workspace.is_symlink() or not workspace.is_dir():
                    raise LocalResultError(
                        "Graphene-owned result workspace is unsafe"
                    ) from None
                shutil.rmtree(workspace)
                _git(repository, "worktree", "prune")
        if workspace.exists():
            raise LocalResultError("Graphene-owned result workspace could not be reset")
        _git(
            repository,
            "worktree",
            "add",
            "-q",
            "--detach",
            str(workspace),
            base_sha,
        )
        _git(workspace, "apply", "--whitespace=nowarn", "-", input_bytes=patch)
        _git(workspace, "add", "--all", "--")
        staged_patch = _git(workspace, "diff", "--cached", "--binary", base_sha, "--")
        if sha256_hex(staged_patch) != candidate.sha256:
            raise LocalResultError(
                "isolated commit contains changes outside the candidate"
            )
        changed_paths = tuple(
            sorted(
                item.decode()
                for item in _git(
                    workspace,
                    "diff",
                    "--cached",
                    "--name-only",
                    "-z",
                    base_sha,
                    "--",
                ).split(b"\0")
                if item
            )
        )
        if not changed_paths:
            raise LocalResultError("approved candidate is empty")
        tree_sha = _git(workspace, "write-tree").decode().strip()
        commit_sha = (
            _git(
                workspace,
                "commit-tree",
                tree_sha,
                "-p",
                base_sha,
                "-m",
                _COMMIT_MESSAGE,
            )
            .decode()
            .strip()
        )
        existing_commit = _existing_result(
            repository, result_ref, base_sha, candidate.sha256
        )
        if existing_commit is not None and existing_commit[0] != commit_sha:
            raise LocalResultError("result reference already binds another commit")
        if existing_commit is None:
            try:
                _git(repository, "update-ref", result_ref, commit_sha, "0" * 40)
            except ScriptedError:
                raced = _existing_result(
                    repository, result_ref, base_sha, candidate.sha256
                )
                if raced is None or raced[0] != commit_sha:
                    raise LocalResultError(
                        "result reference changed during isolated commit creation"
                    )
        if (
            _git(repository, "rev-parse", f"{commit_sha}^").decode().strip() != base_sha
            or _git(repository, "rev-parse", f"{commit_sha}^{{tree}}").decode().strip()
            != tree_sha
        ):
            raise LocalResultError("isolated commit does not match the candidate")
    except ScriptedError as error:
        raise LocalResultError("isolated result Git operation failed") from error
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return LocalResultReceipt.create(
        **common,
        decision="approve",
        truth_kind=truth_kind,
        changed_paths=changed_paths,
        local_commit_sha=commit_sha,
        result_ref=result_ref,
        outcome="isolated_local_commit",
    )


__all__ = [
    "LocalResultError",
    "LocalResultReceipt",
    "approve_result",
    "reject_result",
    "verify_local_result_receipt",
]
