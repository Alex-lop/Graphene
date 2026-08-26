from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..core_models import FrozenModel, GitSha, Identifier, RepoPath, Sha256, TruthKind
from .evidence import SQLiteAttemptEvidenceStore, TrustedCheckReceipt
from .mission_models import (
    AttemptState,
    EvidenceReference,
    MissionEvent,
    MissionEventType,
    MissionHead,
    MissionStatus,
    PublicationState,
    TaskKind,
)

if TYPE_CHECKING:
    from .final_bundle import FinalResultBundleV2


_OPERATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._@-]{0,63}$")
_COMMIT_MESSAGE = "Graphene approved isolated mission result"


class LocalResultError(RuntimeError):
    pass


class LocalResultRecoveryRequired(LocalResultError):
    """A final approval is durable and isolated-result recording must be retried."""


class _LocalGitError(RuntimeError):
    pass


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise _LocalGitError("Git executable is unavailable")
    environment = {
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_AUTHOR_EMAIL": "fixture@graphene.invalid",
        "GIT_AUTHOR_NAME": "Graphene Scripted Fixture",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_EMAIL": "fixture@graphene.invalid",
        "GIT_COMMITTER_NAME": "Graphene Scripted Fixture",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "PATH": os.defpath,
    }
    try:
        result = subprocess.run(
            (
                executable,
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.filemode=false",
                "-c",
                "core.hooksPath=/dev/null",
                *arguments,
            ),
            cwd=repository,
            env=environment,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise _LocalGitError("local result Git operation failed") from error
    if result.returncode:
        raise _LocalGitError("local result Git operation was rejected")
    return result.stdout


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
    candidate: EvidenceReference,
    expected_template_id: str,
) -> None:
    if reference.kind != "test-receipt":
        raise LocalResultError("final result is not bound to a test receipt")
    raw = evidence.resolve(reference.kind, reference.id)
    try:
        receipt = (
            TrustedCheckReceipt.model_validate_json(raw) if raw is not None else None
        )
    except ValueError as error:
        raise LocalResultError("verification receipt is unreadable") from error
    candidate_identity = (candidate.kind, candidate.id, candidate.sha256)
    accepted = (
        tuple(
            reference
            for reference in receipt.accepted_input_references
            if (reference.kind, reference.id, reference.sha256) == candidate_identity
        )
        if receipt is not None
        else ()
    )
    checked = (
        tuple(
            reference
            for reference in receipt.candidate_references
            if (reference.kind, reference.id, reference.sha256) == candidate_identity
        )
        if receipt is not None
        else ()
    )
    if (
        receipt is None
        or receipt.template_id != expected_template_id
        or len(receipt.accepted_input_references) != 1
        or len(receipt.candidate_references) != 1
        or len(accepted) != 1
        or len(checked) != 1
        or receipt.result_code != "passed"
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
    expected_template_id: str,
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
    _verification(evidence, verification, candidate, expected_template_id)
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
    expected_template_id: str = "fixture-tests",
) -> LocalResultReceipt:
    _require_decision_truth(truth_kind)
    runtime, repository = _owned_repository(runtime, repository)
    del runtime
    result_ref = _result_ref(mission_id)
    try:
        _git(repository, "rev-parse", "--verify", result_ref)
    except _LocalGitError:
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
            expected_template_id=expected_template_id,
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
    except _LocalGitError:
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
    except _LocalGitError as error:
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
    expected_template_id: str = "fixture-tests",
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
        expected_template_id=expected_template_id,
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
            except _LocalGitError:
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
            except _LocalGitError:
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
    except _LocalGitError as error:
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


def verified_result_artifacts(
    store: Any,
    evidence: SQLiteAttemptEvidenceStore,
    mission_id: str,
) -> tuple[EvidenceReference, EvidenceReference]:
    """Resolve the final artifacts through accepted task/publication bindings."""

    snapshot = store.snapshot(mission_id)
    attempts = {item.attempt_id: item for item in snapshot.attempts}

    def artifact(task_kind: TaskKind) -> tuple[EvidenceReference, Any]:
        task_ids = tuple(
            item.task_id for item in snapshot.tasks if item.kind == task_kind
        )
        if len(task_ids) != 1:
            raise LocalResultError("final result task authority is ambiguous")
        publications = tuple(
            item
            for item in snapshot.publications
            if item.task_id == task_ids[0] and item.state == PublicationState.ACCEPTED
        )
        if len(publications) != 1:
            raise LocalResultError("final result publication is unavailable")
        publication = publications[0]
        attempt = attempts.get(publication.attempt_id)
        if attempt is None or attempt.state != AttemptState.COMMITTED:
            raise LocalResultError("final result attempt is unavailable")
        references = tuple(
            item
            for item in attempt.evidence_refs
            if item.kind == publication.kind and item.sha256 == publication.sha256
        )
        if len(references) != 1:
            raise LocalResultError("final result artifact authority is ambiguous")
        reference = references[0]
        raw = evidence.resolve(reference.kind, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise LocalResultError("final result artifact failed digest verification")
        return reference, publication

    candidate, candidate_publication = artifact(TaskKind.ASSEMBLY)
    verification, _verification_publication = artifact(TaskKind.VERIFICATION)
    raw_verification = evidence.resolve(verification.kind, verification.id)
    try:
        receipt = TrustedCheckReceipt.model_validate_json(raw_verification)
        expected_candidate = candidate_publication.published_reference()
    except (AttributeError, TypeError, ValueError) as error:
        raise LocalResultError("final result publication proof is invalid") from error
    if receipt.accepted_input_references != (
        expected_candidate,
    ) or receipt.candidate_references != (expected_candidate,):
        raise LocalResultError(
            "final verification does not bind the accepted assembly publication"
        )
    return candidate, verification


def _final_verification_template(snapshot: Any) -> str:
    tasks = tuple(
        item for item in snapshot.plan.tasks if item.kind == TaskKind.VERIFICATION
    )
    if len(tasks) != 1 or len(tasks[0].acceptance_checks) != 1:
        raise LocalResultError("mission verification template is ambiguous")
    return tasks[0].acceptance_checks[0]


def _mission_events(
    store: Any, mission_id: str, head: MissionHead
) -> tuple[MissionEvent, ...]:
    events: list[MissionEvent] = []
    after = 0
    while after < head.seq:
        batch = store.tail(mission_id, after, min(256, head.seq - after))
        if not batch:
            raise LocalResultError("mission result event stream is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    if (
        len(events) != head.seq
        or events[-1].event_sha256 != head.event_sha256
        or any(event.seq != index for index, event in enumerate(events, start=1))
    ):
        raise LocalResultError("mission result event stream is inconsistent")
    return tuple(events)


def _head_is_committed(expected: MissionHead, events: tuple[MissionEvent, ...]) -> bool:
    return (
        expected.seq >= 1
        and expected.seq <= len(events)
        and expected.event_count == expected.seq
        and events[expected.seq - 1].event_sha256 == expected.event_sha256
    )


def _approval_event(events: tuple[MissionEvent, ...]) -> MissionEvent:
    approvals = tuple(
        event
        for event in events
        if event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
    )
    if len(approvals) != 1:
        raise LocalResultError("final result approval authority is ambiguous")
    return approvals[0]


def _completed_receipt(
    events: tuple[MissionEvent, ...],
    evidence: SQLiteAttemptEvidenceStore,
    *,
    runtime: Path,
    repository: Path,
    mission_id: str,
    candidate_sha256: str,
) -> LocalResultReceipt:
    completed = tuple(
        event
        for event in events
        if event.event_type == MissionEventType.ISOLATED_COMMIT_CREATED
    )
    if len(completed) != 1 or len(completed[0].references) != 1:
        raise LocalResultError("isolated result receipt authority is ambiguous")
    reference = completed[0].references[0]
    raw = evidence.resolve(reference.kind, reference.id)
    try:
        receipt = (
            LocalResultReceipt.model_validate_json(raw) if raw is not None else None
        )
    except ValueError as error:
        raise LocalResultError("isolated result receipt is unreadable") from error
    if (
        receipt is None
        or reference.kind != "local-result-receipt"
        or sha256_hex(raw) != reference.sha256
        or receipt.mission_id != mission_id
        or receipt.candidate_patch_sha256 != candidate_sha256
        or not verify_local_result_receipt(
            raw,
            runtime=runtime,
            repository=repository,
        )
    ):
        raise LocalResultError("isolated result receipt failed verification")
    return receipt


def _record_result_command_id(mission_id: str, receipt_sha256: str) -> str:
    return (
        "command_"
        + sha256_hex(
            canonical_json_bytes(["record-result", mission_id, receipt_sha256])
        )[:32]
    )


def _prepare_bundle_command_id(mission_id: str, bundle_id: str) -> str:
    return (
        "command_"
        + sha256_hex(
            canonical_json_bytes(["prepare-final-bundle", mission_id, bundle_id])
        )[:32]
    )


def _registered_final_result_bundle(
    *,
    store: Any,
    evidence: SQLiteAttemptEvidenceStore,
    mission_id: str,
    head: MissionHead,
) -> tuple[FinalResultBundleV2, EvidenceReference] | None:
    from .final_bundle import FinalResultBundleV2

    events = _mission_events(store, mission_id, head)
    ready = tuple(
        event
        for event in events
        if event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    )
    if not ready:
        return None
    event = ready[-1]
    if event.seq != head.seq:
        raise LocalResultError("prepared final result bundle is not current")
    references = tuple(
        item for item in event.references if item.kind == "final-result-bundle"
    )
    if len(references) != 1:
        raise LocalResultError("final result bundle evidence is ambiguous")
    reference = references[0]
    raw = evidence.resolve(reference.kind, reference.id)
    try:
        bundle = (
            FinalResultBundleV2.model_validate_json(raw) if raw is not None else None
        )
    except ValueError as error:
        raise LocalResultError("final result bundle is unreadable") from error
    if (
        bundle is None
        or canonical_json_bytes(bundle.model_dump(mode="json")) != raw
        or sha256_hex(raw) != reference.sha256
        or bundle.bundle_id != event.payload.get("bundle_id")
        or bundle.bundle_sha256 != event.payload.get("bundle_sha256")
        or bundle.event_head_seq != event.seq - 1
        or bundle.event_head_sha256 != event.previous_event_sha256
        or bundle.operator_decision.state != "pending"
        or bundle.result_commit is not None
    ):
        raise LocalResultError("final result bundle evidence changed")
    return bundle, reference


def prepare_local_final_result_bundle(
    *,
    store: Any,
    mission_id: str,
    expected_head: MissionHead,
    recorded_at: datetime,
) -> tuple[MissionHead, FinalResultBundleV2, EvidenceReference]:
    """Build, persist, and register the exact prospective local result bundle.

    The deterministic command and content identities make a crash after either the
    artifact write or event append safe to retry. Callers must invoke this write-side
    helper immediately after the mission enters awaiting-result; reads never prepare
    mission state.
    """

    from .final_bundle import build_final_result_bundle

    snapshot = store.snapshot(mission_id)
    if (
        snapshot.head.seq != expected_head.seq
        or snapshot.head.event_sha256 != expected_head.event_sha256
        or expected_head.event_count != expected_head.seq
    ):
        raise LocalResultError("final result bundle preparation head is stale")
    if (
        snapshot.mission.status != MissionStatus.AWAITING_RESULT
        or snapshot.mission.final_outcome is not None
    ):
        raise LocalResultError("mission is not awaiting final bundle preparation")
    evidence = getattr(store, "artifact_resolver", None)
    if not isinstance(evidence, SQLiteAttemptEvidenceStore):
        raise LocalResultError("mission result evidence is not locally verifiable")
    existing = _registered_final_result_bundle(
        store=store,
        evidence=evidence,
        mission_id=mission_id,
        head=snapshot.head,
    )
    if existing is not None:
        return snapshot.head, *existing

    evidence_path = Path(evidence.path)
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise LocalResultError("mission result evidence is unavailable")
    repository = evidence_path.resolve(strict=True).parent / "repository"
    try:
        bundle = build_final_result_bundle(
            snapshot,
            evidence,
            repository,
            result_commit=None,
            policy_sha256=snapshot.policy.policy_sha256,
        )
        raw = canonical_json_bytes(bundle.model_dump(mode="json"))
        reference = evidence.put_artifact("final-result-bundle", raw)
    except Exception as error:
        raise LocalResultError("final result bundle could not be built") from error
    if getattr(store, "final_bundle_verifier", None) is None:
        try:
            store.bind_final_bundle_verifier(
                partial(_recompute_final_bundle, evidence=evidence, repository=repository)
            )
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            raise LocalResultError(
                "final result bundle verifier could not be bound"
            ) from error
    try:
        head = store.register_final_result_bundle(
            mission_id,
            reference,
            _prepare_bundle_command_id(mission_id, bundle.bundle_id),
            expected_head=expected_head,
            recorded_at=recorded_at,
        )
    except Exception as error:
        # The event may have committed before the caller observed the result. Only
        # an exact current bundle matching the bytes we built makes that retry safe.
        current = store.snapshot(mission_id)
        recovered = _registered_final_result_bundle(
            store=store,
            evidence=evidence,
            mission_id=mission_id,
            head=current.head,
        )
        if recovered is None or recovered != (bundle, reference):
            raise LocalResultError("final result bundle preparation failed") from error
        return current.head, *recovered
    return head, bundle, reference


def _recompute_final_bundle(
    bundle_bytes: bytes,
    snapshot: Any,
    *,
    evidence: SQLiteAttemptEvidenceStore,
    repository: Path,
) -> bool:
    """Rebuild the bundle from the repository; the store refuses to register without it.

    Bound as the store's ``final_bundle_verifier``. Everything path-, tree- and
    manifest-shaped in the bundle is recomputed here — an invented
    ``result_tree_id`` or an invented mutation entry cannot survive it.
    """
    from .final_bundle import verify_final_result_bundle

    try:
        return verify_final_result_bundle(
            bundle_bytes,
            snapshot,
            evidence,
            repository,
            expected_policy_sha256=snapshot.policy.policy_sha256,
        )
    except Exception:
        return False


def finalize_local_result_decision(
    *,
    store: Any,
    mission_id: str,
    command_id: str,
    expected_head: MissionHead,
    expected_bundle_id: str,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
    recorded_at: datetime,
    approved: bool,
    allow_simulated_fixture: bool = False,
) -> tuple[MissionHead, LocalResultReceipt]:
    """Commit a final decision and finish or resume its isolated local result.

    Approval is intentionally recoverable across process restarts: when the approval
    event already exists, its committed attribution is reused and only the verified
    isolated-result creation/recording steps are resumed. Rejection never creates a
    Git commit or result ref.
    """

    snapshot = store.snapshot(mission_id)
    if snapshot.mission.creation_source not in {"operator", "scripted_fixture"}:
        raise LocalResultError("local result creation is unavailable for this mission")
    evidence = getattr(store, "artifact_resolver", None)
    if not isinstance(evidence, SQLiteAttemptEvidenceStore):
        raise LocalResultError("mission result evidence is not locally verifiable")
    evidence_path = Path(evidence.path)
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise LocalResultError("mission result evidence is unavailable")
    runtime = evidence_path.resolve(strict=True).parent
    repository = runtime / "repository"
    candidate, verification = verified_result_artifacts(store, evidence, mission_id)
    events = _mission_events(store, mission_id, snapshot.head)
    bundle_events = tuple(
        event
        for event in events
        if event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
        and event.payload.get("bundle_id") == expected_bundle_id
    )
    if len(bundle_events) != 1:
        raise LocalResultError("exact final result bundle is not prepared")
    bundle_event = bundle_events[0]
    bundle_references = tuple(
        item for item in bundle_event.references if item.kind == "final-result-bundle"
    )
    if len(bundle_references) != 1:
        raise LocalResultError("final result bundle evidence is ambiguous")
    bundle_bytes = evidence.resolve(bundle_references[0].kind, bundle_references[0].id)
    try:
        from .final_bundle import FinalResultBundleV2

        bundle = (
            FinalResultBundleV2.model_validate_json(bundle_bytes)
            if bundle_bytes is not None
            else None
        )
    except ValueError as error:
        raise LocalResultError("final result bundle is unreadable") from error
    if (
        bundle is None
        or sha256_hex(bundle_bytes) != bundle_references[0].sha256
        or bundle.bundle_id != expected_bundle_id
        or bundle.bundle_sha256 != bundle_event.payload.get("bundle_sha256")
        or bundle.candidate_reference.content_sha256 != candidate.sha256
        or bundle.verification_reference.content_sha256 != verification.sha256
    ):
        raise LocalResultError("final result bundle bindings changed")
    expected_template_id = _final_verification_template(snapshot)
    if getattr(store, "local_commit_verifier", None) is None:
        try:
            store.bind_local_commit_verifier(
                partial(
                    verify_local_result_receipt,
                    runtime=runtime,
                    repository=repository,
                )
            )
        except (AttributeError, RuntimeError, TypeError, ValueError) as error:
            raise LocalResultError(
                "local result verifier could not be bound"
            ) from error

    common = {
        "runtime": runtime,
        "repository": repository,
        "mission_id": mission_id,
        "base_sha": snapshot.mission.base_sha,
        "candidate": candidate,
        "verification": verification,
        "evidence": evidence,
        "operator_label": operator_label,
        "rationale": rationale,
        "truth_kind": truth_kind,
        "expected_template_id": expected_template_id,
    }
    if not approved:
        receipt = reject_result(**common)
        evidence.put_artifact(
            "local-result-receipt",
            canonical_json_bytes(receipt.model_dump(mode="json")),
        )
        head = store.reject_final_result(
            mission_id,
            command_id,
            expected_head=expected_head,
            expected_bundle_id=expected_bundle_id,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
        )
        return head, receipt

    current_head = snapshot.head
    outcome = snapshot.mission.final_outcome
    if outcome == "approved":
        events = _mission_events(store, mission_id, current_head)
        if not _head_is_committed(expected_head, events):
            raise LocalResultError(
                "result retry does not bind a committed mission head"
            )
        approval = _approval_event(events)
        if command_id == approval.command_id and (
            approval.payload.get("bundle_id") != expected_bundle_id
            or approval.payload.get("candidate_sha256") != candidate.sha256
            or approval.payload.get("operator_label") != operator_label
            or approval.payload.get("operator_rationale") != rationale
            or approval.truth_kind != truth_kind
        ):
            raise LocalResultError(
                "final approval command was reused with another request"
            )
        receipt = _completed_receipt(
            events,
            evidence,
            runtime=runtime,
            repository=repository,
            mission_id=mission_id,
            candidate_sha256=candidate.sha256,
        )
        return current_head, receipt

    if outcome == "approved_pending_commit":
        events = _mission_events(store, mission_id, current_head)
        approval = _approval_event(events)
        current_expected = (
            expected_head.seq == current_head.seq
            and expected_head.event_sha256 == current_head.event_sha256
        )
        original_expected = (
            command_id == approval.command_id
            and expected_head.seq == approval.seq - 1
            and expected_head.event_sha256 == approval.previous_event_sha256
        )
        if not (current_expected or original_expected):
            raise LocalResultError("result recovery does not bind the approved head")
        if command_id == approval.command_id and (
            approval.payload.get("bundle_id") != expected_bundle_id
            or approval.payload.get("operator_label") != operator_label
            or approval.payload.get("operator_rationale") != rationale
            or approval.truth_kind != truth_kind
        ):
            raise LocalResultError(
                "final approval command was reused with another request"
            )
        approval_operator = str(approval.payload.get("operator_label"))
        approval_rationale = approval.payload.get("operator_rationale")
        if approval_rationale is not None:
            approval_rationale = str(approval_rationale)
        common.update(
            operator_label=approval_operator,
            rationale=approval_rationale,
            truth_kind=approval.truth_kind,
        )
    elif outcome is None:
        # Validate every local evidence/repository precondition without creating a
        # commit before the durable approval authority exists.
        reject_result(**common)
        store.approve_final_result(
            mission_id,
            command_id,
            expected_head=expected_head,
            expected_bundle_id=expected_bundle_id,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
        )
    else:
        raise LocalResultError("mission already has another final outcome")

    try:
        receipt = approve_result(
            **common,
            approved_candidate_sha256=candidate.sha256,
            allow_simulated_fixture=allow_simulated_fixture,
        )
        receipt_reference = evidence.put_artifact(
            "local-result-receipt",
            canonical_json_bytes(receipt.model_dump(mode="json")),
        )
        if receipt.local_commit_sha is None:
            raise LocalResultError("approved local result has no isolated commit")
        head = store.record_isolated_commit(
            mission_id,
            receipt.local_commit_sha,
            receipt_reference,
            _record_result_command_id(mission_id, receipt.receipt_sha256),
            recorded_at=recorded_at,
        )
    except Exception as error:
        raise LocalResultRecoveryRequired(
            "final approval is committed; isolated result recording must be retried"
        ) from error
    return head, receipt


__all__ = [
    "LocalResultError",
    "LocalResultRecoveryRequired",
    "LocalResultReceipt",
    "approve_result",
    "finalize_local_result_decision",
    "prepare_local_final_result_bundle",
    "reject_result",
    "verified_result_artifacts",
    "verify_local_result_receipt",
]
