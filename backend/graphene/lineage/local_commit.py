from __future__ import annotations

import base64
import binascii
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..hashing import canonical_json_sha256, candidate_tree_sha256, sha256_hex
from ..core_models import (
    AgentProfileId,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    GitSha,
    HumanDecision,
    Identifier,
    MAX_PATCH_BYTES,
    LineageAuthority,
    LineageEventType,
    MemoryDecisionValue,
    RepoPath,
    Sha256,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from .artifacts import SQLiteArtifactStore
from .promotion import PromotionReceiptV2, SQLiteCheckpointRecorder
from .sqlite_lineage_store import EvidenceInvalid, LineageConflict, SQLiteLineageStore

LOCAL_COMMIT_APPROVAL_LABEL = "Approve and create isolated local commit"
LOCAL_COMMIT_RESULT_LABEL = (
    "local isolated commit — not pushed / no PR / no deployment"
)
LOCAL_COMMIT_MESSAGE = "Graphene approved isolated candidate"
_AUTHOR_NAME = "Graphene Isolated Fixture"
_AUTHOR_EMAIL = "graphene-fixture@invalid"


class LocalCommitError(RuntimeError):
    pass


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalCommitRequest(_Frozen):
    schema_version: Literal[2] = 2
    run_id: Identifier
    repo_id: Identifier
    base_sha: GitSha
    candidate_patch: bytes = Field(min_length=1, max_length=MAX_PATCH_BYTES, repr=False)
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    changed_paths: tuple[RepoPath, ...]
    test_reference: EvidenceReference
    authoritative_test_receipt_sha256: Sha256
    approval: HumanDecision
    approval_reference: EvidenceReference
    promotion_reference: EvidenceReference

    @model_validator(mode="after")
    def exact_bindings(self) -> LocalCommitRequest:
        if (
            sha256_hex(self.candidate_patch) != self.candidate_patch_sha256
            or not self.changed_paths
            or self.changed_paths != tuple(sorted(set(self.changed_paths)))
            or self.test_reference.kind != EvidenceKind.TEST_RECEIPT
            or self.approval_reference.kind != EvidenceKind.EVENT
            or self.promotion_reference.kind != EvidenceKind.PROMOTION_RECEIPT
            or self.approval.value != MemoryDecisionValue.APPROVE
            or self.approval.purpose != "promotion"
            or self.approval.bound_digest != self.candidate_patch_sha256
        ):
            raise ValueError("local commit bindings are not exact and approved")
        return self


class LocalCommitReceiptV2(_Frozen):
    schema_version: Literal[2] = 2
    receipt_id: Identifier
    run_id: Identifier
    repo_id: Identifier
    base_sha: GitSha
    local_commit_sha: GitSha
    parent_sha: GitSha
    tree_sha: GitSha
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    changed_paths: tuple[RepoPath, ...]
    test_receipt_id: Identifier
    test_receipt_sha256: Sha256
    authoritative_test_receipt_sha256: Sha256
    approval_decision_id: Identifier
    approval_event_id: Identifier
    approval_event_sha256: Sha256
    promotion_receipt_id: Identifier
    promotion_receipt_sha256: Sha256
    commit_message: Literal[LOCAL_COMMIT_MESSAGE]
    outcome: Literal["local_isolated_commit"] = "local_isolated_commit"
    pushed: Literal[False] = False
    pull_request_created: Literal[False] = False
    deployed: Literal[False] = False
    result_label: Literal[LOCAL_COMMIT_RESULT_LABEL] = LOCAL_COMMIT_RESULT_LABEL
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def canonical_receipt(self) -> LocalCommitReceiptV2:
        if (
            self.parent_sha != self.base_sha
            or self.receipt_sha256
            != canonical_json_sha256(
                self.model_dump(mode="json", exclude={"receipt_sha256"})
            )
        ):
            raise ValueError("local commit receipt binding or digest does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> LocalCommitReceiptV2:
        core = {"schema_version": 2, **values}
        core.pop("receipt_id", None)
        core.pop("receipt_sha256", None)
        receipt_id = "local_commit_" + canonical_json_sha256(core)[:32]
        record = {"receipt_id": receipt_id, **core}
        return cls.model_validate(
            {**record, "receipt_sha256": canonical_json_sha256(record)}
        )


class LocalCommitOutcome(_Frozen):
    receipt: LocalCommitReceiptV2
    receipt_reference: EvidenceReference
    event: Event
    final_head: VerifiedHead


def _environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = {
        **{
            name: value
            for name, value in os.environ.items()
            if not name.startswith("GIT_")
        },
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }
    if extra:
        environment.update(extra)
    return environment


def _git(
    checkout: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    extra_environment: dict[str, str] | None = None,
) -> bytes:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=checkout,
            env=_environment(extra_environment),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LocalCommitError("isolated Git operation failed") from error
    if completed.returncode:
        raise LocalCommitError("isolated Git operation was rejected")
    return completed.stdout


def _sha(checkout: Path, value: str) -> str:
    raw = _git(checkout, "rev-parse", "--verify", value).decode("ascii").strip()
    if len(raw) != 40 or any(character not in "0123456789abcdef" for character in raw):
        raise LocalCommitError("isolated Git identity is malformed")
    return raw


def _paths(raw: bytes) -> tuple[str, ...]:
    try:
        values = tuple(item.decode("utf-8") for item in raw.split(b"\0") if item)
    except UnicodeDecodeError as error:
        raise LocalCommitError("isolated Git path is not UTF-8") from error
    return tuple(sorted(set(values)))


def _changed_paths(checkout: Path, revision: str = "HEAD") -> tuple[str, ...]:
    tracked = _paths(
        _git(checkout, "diff", "--name-only", "-z", revision, "--")
    )
    untracked = _paths(
        _git(checkout, "ls-files", "--others", "--exclude-standard", "-z", "--")
    )
    return tuple(sorted(set((*tracked, *untracked))))


def _runtime_checkout(runtime_dir: str | Path, run_id: str) -> Path:
    runtime = Path(runtime_dir)
    if not runtime.is_absolute() or runtime.is_symlink():
        raise LocalCommitError("runtime directory must be isolated and absolute")
    try:
        runtime = runtime.resolve(strict=True)
        metadata = runtime.stat(follow_symlinks=False)
        checkout = (runtime / "checkouts" / run_id).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise LocalCommitError("retained isolated checkout is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        or checkout.parent != runtime / "checkouts"
        or checkout.name != run_id
        or checkout.is_symlink()
        or not checkout.is_dir()
        or (checkout / ".git").is_symlink()
        or not (checkout / ".git").is_dir()
    ):
        raise LocalCommitError("retained isolated checkout binding is unsafe")
    try:
        top = Path(_git(checkout, "rev-parse", "--show-toplevel").decode().strip())
    except UnicodeDecodeError as error:
        raise LocalCommitError("isolated Git root is malformed") from error
    if top.resolve() != checkout:
        raise LocalCommitError("isolated Git root does not match the retained checkout")
    return checkout


def _approved_tree(checkout: Path, request: LocalCommitRequest) -> str:
    descriptor, index_path = tempfile.mkstemp(prefix="graphene-index-", dir=checkout.parent)
    os.close(descriptor)
    os.unlink(index_path)
    alternate = {"GIT_INDEX_FILE": index_path}
    try:
        _git(checkout, "read-tree", request.base_sha, extra_environment=alternate)
        _git(
            checkout,
            "apply",
            "--cached",
            "--binary",
            "--whitespace=nowarn",
            "-",
            input_bytes=request.candidate_patch,
            extra_environment=alternate,
        )
        tree_sha = _git(
            checkout, "write-tree", extra_environment=alternate
        ).decode("ascii").strip()
        changed = _paths(
            _git(
                checkout,
                "diff",
                "--name-only",
                "-z",
                request.base_sha,
                tree_sha,
            )
        )
        files = {
            path: _git(checkout, "show", f"{tree_sha}:{path}")
            for path in request.changed_paths
        }
    except UnicodeDecodeError as error:
        raise LocalCommitError("approved candidate tree is malformed") from error
    finally:
        try:
            os.unlink(index_path)
        except FileNotFoundError:
            pass
    if changed != request.changed_paths:
        raise LocalCommitError("approved patch paths do not match the candidate")
    if candidate_tree_sha256(files) != request.candidate_tree_sha256:
        raise LocalCommitError("approved candidate tree digest does not match")
    return tree_sha


def _verify_commit(
    checkout: Path,
    request: LocalCommitRequest,
    *,
    commit_sha: str,
    tree_sha: str,
) -> None:
    _git(checkout, "cat-file", "-e", f"{commit_sha}^{{commit}}")
    if (
        _sha(checkout, f"{commit_sha}^") != request.base_sha
        or _sha(checkout, f"{commit_sha}^{{tree}}") != tree_sha
        or _paths(
            _git(
                checkout,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "-z",
                commit_sha,
            )
        )
        != request.changed_paths
        or _git(checkout, "show", "-s", "--format=%B", commit_sha).decode().strip()
        != LOCAL_COMMIT_MESSAGE
    ):
        raise LocalCommitError("local commit does not match the approved candidate")


def create_isolated_local_commit(
    runtime_dir: str | Path,
    request: LocalCommitRequest,
    *,
    allow_simulated_fixture: bool = False,
) -> LocalCommitReceiptV2:
    """Create or recover one exact commit in the retained fixture checkout."""

    if not isinstance(request, LocalCommitRequest):
        raise TypeError("local commit requires a validated request")
    request = LocalCommitRequest.model_validate(request.model_dump())
    if request.approval.actor == "simulated_fixture" and not allow_simulated_fixture:
        raise LocalCommitError("simulated fixture commit was not explicitly enabled")
    checkout = _runtime_checkout(runtime_dir, request.run_id)
    approved_tree = _approved_tree(checkout, request)
    head = _sha(checkout, "HEAD")

    if head == request.base_sha:
        if _changed_paths(checkout) != request.changed_paths:
            raise LocalCommitError("checkout changes do not match the approved candidate")
        parent_tree = _sha(checkout, f"{request.base_sha}^{{tree}}")
        index_tree = _git(checkout, "write-tree").decode("ascii").strip()
        if index_tree not in {parent_tree, approved_tree}:
            raise LocalCommitError("checkout index contains unapproved changes")
        if index_tree != approved_tree:
            _git(checkout, "add", "-A", "--", *request.changed_paths)
            index_tree = _git(checkout, "write-tree").decode("ascii").strip()
        if index_tree != approved_tree:
            raise LocalCommitError("staged tree does not match the approved candidate")

        _git(checkout, "config", "--local", "user.name", _AUTHOR_NAME)
        _git(checkout, "config", "--local", "user.email", _AUTHOR_EMAIL)
        timestamp = str(int(request.approval.occurred_at.timestamp())) + " +0000"
        commit_sha = _git(
            checkout,
            "commit-tree",
            approved_tree,
            "-p",
            request.base_sha,
            "-m",
            LOCAL_COMMIT_MESSAGE,
            extra_environment={
                "GIT_AUTHOR_DATE": timestamp,
                "GIT_COMMITTER_DATE": timestamp,
            },
        ).decode("ascii").strip()
        try:
            _git(
                checkout,
                "update-ref",
                "-m",
                LOCAL_COMMIT_MESSAGE,
                "HEAD",
                commit_sha,
                request.base_sha,
            )
        except LocalCommitError:
            if _sha(checkout, "HEAD") != commit_sha:
                raise
    else:
        commit_sha = head

    _verify_commit(
        checkout,
        request,
        commit_sha=commit_sha,
        tree_sha=approved_tree,
    )
    if _sha(checkout, "HEAD") != commit_sha or _changed_paths(checkout) != ():
        raise LocalCommitError("local commit checkout did not become clean")

    return LocalCommitReceiptV2.create(
        run_id=request.run_id,
        repo_id=request.repo_id,
        base_sha=request.base_sha,
        local_commit_sha=commit_sha,
        parent_sha=request.base_sha,
        tree_sha=approved_tree,
        candidate_patch_sha256=request.candidate_patch_sha256,
        candidate_tree_sha256=request.candidate_tree_sha256,
        candidate_tree_hash_version=request.candidate_tree_hash_version,
        changed_paths=request.changed_paths,
        test_receipt_id=request.test_reference.id,
        test_receipt_sha256=request.test_reference.sha256,
        authoritative_test_receipt_sha256=(
            request.authoritative_test_receipt_sha256
        ),
        approval_decision_id=request.approval.decision_id,
        approval_event_id=request.approval_reference.id,
        approval_event_sha256=request.approval_reference.sha256,
        promotion_receipt_id=request.promotion_reference.id,
        promotion_receipt_sha256=request.promotion_reference.sha256,
        commit_message=LOCAL_COMMIT_MESSAGE,
        outcome="local_isolated_commit",
        pushed=False,
        pull_request_created=False,
        deployed=False,
        result_label=LOCAL_COMMIT_RESULT_LABEL,
    )


def local_commit_event_input(
    receipt: LocalCommitReceiptV2,
    receipt_reference: EvidenceReference,
    *,
    agent_profile_id: AgentProfileId,
    policy_revision: int,
) -> tuple[str, EventInput]:
    """Return the idempotency key and exact authoritative append draft."""

    if (
        not isinstance(receipt, LocalCommitReceiptV2)
        or receipt_reference.kind != EvidenceKind.LOCAL_COMMIT_RECEIPT
        or receipt_reference.sha256
        != canonical_json_sha256(receipt.model_dump(mode="json"))
    ):
        raise LocalCommitError("local commit artifact reference does not match")
    approval = EvidenceReference(
        kind=EvidenceKind.EVENT,
        id=receipt.approval_event_id,
        sha256=receipt.approval_event_sha256,
    )
    promotion = EvidenceReference(
        kind=EvidenceKind.PROMOTION_RECEIPT,
        id=receipt.promotion_receipt_id,
        sha256=receipt.promotion_receipt_sha256,
    )
    test = EvidenceReference(
        kind=EvidenceKind.TEST_RECEIPT,
        id=receipt.test_receipt_id,
        sha256=receipt.test_receipt_sha256,
    )
    payload = {
        "approval_event_id": receipt.approval_event_id,
        "approval_event_sha256": receipt.approval_event_sha256,
        "candidate_patch_sha256": receipt.candidate_patch_sha256,
        "candidate_tree_sha256": receipt.candidate_tree_sha256,
        "candidate_tree_hash_version": receipt.candidate_tree_hash_version,
        "changed_paths": list(receipt.changed_paths),
        "deployed": False,
        "local_commit_receipt_id": receipt_reference.id,
        "local_commit_receipt_sha256": receipt_reference.sha256,
        "local_commit_sha": receipt.local_commit_sha,
        "outcome": "local_isolated_commit",
        "parent_sha": receipt.parent_sha,
        "pull_request_created": False,
        "pushed": False,
        "status": "recorded",
        "test_receipt_id": receipt.test_receipt_id,
        "test_receipt_sha256": receipt.test_receipt_sha256,
        "tree_sha": receipt.tree_sha,
    }
    return (
        "local_result_"
        + canonical_json_sha256(
            {
                "run_id": receipt.run_id,
                "receipt_id": receipt_reference.id,
                "receipt_sha256": receipt_reference.sha256,
            }
        )[:32],
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=receipt.repo_id,
            base_sha=receipt.base_sha,
            agent_profile_id=agent_profile_id,
            policy_revision=policy_revision,
            event_type=LineageEventType.LOCAL_RESULT_RECORDED,
            truth_kind=TruthKind.RUNTIME_OBSERVED,
            authority=LineageAuthority.LOCAL_COMMIT_SERVICE,
            references=(approval, promotion, test, receipt_reference),
            source_ref=SourceReference(
                kind=SourceKind.LOCAL_COMMIT_RECEIPT,
                id=receipt_reference.id,
                sha256=receipt_reference.sha256,
            ),
            payload=payload,
        ),
    )


def _event_head(event: Event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _verified_events(
    store: SQLiteLineageStore,
    run_id: str,
) -> tuple[VerifiedHead, tuple[Event, ...]]:
    head = store.verify(run_id)
    if isinstance(head, EvidenceInvalidState) or head.seq < 1:
        raise LocalCommitError("promoted lineage is absent or invalid")
    events: list[Event] = []
    after = 0
    while after < head.seq:
        batch = store.tail(run_id, after, min(256, head.seq - after))
        if not batch or batch[0].seq != after + 1:
            raise LocalCommitError("promoted lineage is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    if len(events) != head.event_count or events[-1].event_sha256 != head.event_sha256:
        raise LocalCommitError("promoted lineage changed during local commit")
    return head, tuple(events)


def _artifact_json(
    artifacts: SQLiteArtifactStore,
    reference: EvidenceReference | SourceReference,
) -> dict[str, object]:
    raw = artifacts.resolve(reference.kind.value, reference.id)
    if raw is None or sha256_hex(raw) != reference.sha256:
        raise LocalCommitError("local commit binding artifact is unresolved")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError) as error:
        raise LocalCommitError("local commit binding artifact is malformed") from error
    if not isinstance(value, dict):
        raise LocalCommitError("local commit binding artifact is malformed")
    return value


def commit_promoted_run(
    database_path: str | Path,
    run_id: str,
    *,
    allow_simulated_fixture: bool = False,
) -> LocalCommitOutcome:
    """Create, verify, and record the local result for one promoted fixture run."""

    database = Path(database_path)
    if not database.is_absolute() or database.is_symlink() or not database.is_file():
        raise LocalCommitError("lineage database must be an absolute retained file")
    try:
        checkpoints = SQLiteCheckpointRecorder(database, read_only=True)
        artifacts = SQLiteArtifactStore(database)
        store = SQLiteLineageStore(
            database,
            artifact_resolver=artifacts.resolve,
            checkpoint_reader=checkpoints.read,
        )
        current, events = _verified_events(store, run_id)
    except LocalCommitError:
        raise
    except Exception as error:
        raise LocalCommitError("promoted lineage could not be opened") from error

    promotions = tuple(
        event
        for event in events
        if event.event_type == LineageEventType.PROMOTION_COMPLETED
    )
    local_results = tuple(
        event
        for event in events
        if event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
    )
    if (
        len(promotions) != 1
        or len(local_results) > 1
        or (
            not local_results
            and (events[-1] != promotions[0] or current != _event_head(promotions[0]))
        )
        or (
            local_results
            and (
                events[-1] != local_results[0]
                or local_results[0].seq != promotions[0].seq + 1
                or local_results[0].previous_event_sha256
                != promotions[0].event_sha256
                or current != _event_head(local_results[0])
            )
        )
    ):
        raise LocalCommitError("local commit requires one current promotion result")
    promotion_event = promotions[0]
    promotion_by_kind = {
        reference.kind: reference for reference in promotion_event.references
    }
    promotion_reference = promotion_by_kind.get(EvidenceKind.PROMOTION_RECEIPT)
    approval_reference = promotion_by_kind.get(EvidenceKind.EVENT)
    if promotion_reference is None or approval_reference is None:
        raise LocalCommitError("promotion result lacks exact receipt bindings")
    try:
        promotion_receipt = PromotionReceiptV2.model_validate(
            _artifact_json(artifacts, promotion_reference)
        )
    except ValueError as error:
        raise LocalCommitError("promotion receipt is malformed") from error
    approval_event = next(
        (
            event
            for event in events
            if event.event_id == approval_reference.id
            and event.event_sha256 == approval_reference.sha256
        ),
        None,
    )
    if approval_event is None:
        raise LocalCommitError("promotion approval event is unresolved")
    approval_record = _artifact_json(artifacts, approval_event.source_ref)
    try:
        approval = HumanDecision.model_validate(approval_record["human_approval"])
    except (KeyError, ValueError) as error:
        raise LocalCommitError("promotion approval receipt is malformed") from error
    references = {reference.kind: reference for reference in promotion_receipt.artifact_references}
    changeset_reference = references.get(EvidenceKind.CHANGESET)
    test_reference = references.get(EvidenceKind.TEST_RECEIPT)
    if changeset_reference is None or test_reference is None:
        raise LocalCommitError("promotion receipt lacks candidate evidence")
    changeset = _artifact_json(artifacts, changeset_reference)
    try:
        patch = base64.b64decode(changeset["canonical_patch_base64"], validate=True)
        changed_paths = tuple(changeset["changed_paths"])
    except (KeyError, TypeError, ValueError, binascii.Error) as error:
        raise LocalCommitError("promotion changeset is malformed") from error
    if (
        promotion_receipt.run_id != run_id
        or promotion_receipt.repo_id != promotion_event.repo_id
        or promotion_receipt.base_sha != promotion_event.base_sha
        or promotion_receipt.agent_profile_id != promotion_event.agent_profile_id
        or promotion_receipt.policy_revision != promotion_event.policy_revision
        or promotion_receipt.approval_event_id != approval_event.event_id
        or promotion_receipt.approval_event_sha256 != approval_event.event_sha256
        or promotion_receipt.test_receipt_sha256 != test_reference.sha256
        or promotion_event.payload.get("promotion_receipt_sha256")
        != promotion_receipt.receipt_sha256
        or approval_event.event_type != LineageEventType.PROMOTION_APPROVED
        or approval_event.payload.get("candidate_patch_sha256")
        != promotion_receipt.candidate_patch_sha256
        or approval_record.get("human_approval_sha256")
        != promotion_receipt.human_approval_sha256
        or changeset.get("candidate_patch_sha256")
        != promotion_receipt.candidate_patch_sha256
        or changeset.get("candidate_tree_sha256")
        != promotion_receipt.candidate_tree_sha256
        or changeset.get("candidate_tree_hash_version")
        != promotion_receipt.candidate_tree_hash_version
    ):
        raise LocalCommitError("promotion and candidate bindings do not match")

    request = LocalCommitRequest(
        run_id=run_id,
        repo_id=promotion_receipt.repo_id,
        base_sha=promotion_receipt.base_sha,
        candidate_patch=patch,
        candidate_patch_sha256=promotion_receipt.candidate_patch_sha256,
        candidate_tree_sha256=promotion_receipt.candidate_tree_sha256,
        candidate_tree_hash_version=promotion_receipt.candidate_tree_hash_version,
        changed_paths=changed_paths,
        test_reference=test_reference,
        authoritative_test_receipt_sha256=(
            promotion_receipt.authoritative_test_receipt_sha256
        ),
        approval=approval,
        approval_reference=approval_reference,
        promotion_reference=promotion_reference,
    )
    receipt = create_isolated_local_commit(
        database.parent,
        request,
        allow_simulated_fixture=allow_simulated_fixture,
    )
    receipt_reference = artifacts(
        EvidenceKind.LOCAL_COMMIT_RECEIPT,
        receipt.model_dump(mode="json"),
    )
    idempotency_key, draft = local_commit_event_input(
        receipt,
        receipt_reference,
        agent_profile_id=promotion_receipt.agent_profile_id,
        policy_revision=promotion_receipt.policy_revision,
    )
    try:
        event = store.append(
            run_id,
            _event_head(promotion_event),
            idempotency_key,
            draft,
        )
        final_head = store.verify(run_id)
    except (EvidenceInvalid, LineageConflict) as error:
        raise LocalCommitError("local commit result could not be recorded") from error
    if (
        event.event_type != LineageEventType.LOCAL_RESULT_RECORDED
        or isinstance(final_head, EvidenceInvalidState)
        or final_head != _event_head(event)
    ):
        raise LocalCommitError("recorded local commit result did not verify")
    return LocalCommitOutcome(
        receipt=receipt,
        receipt_reference=receipt_reference,
        event=event,
        final_head=final_head,
    )


__all__ = [
    "LOCAL_COMMIT_APPROVAL_LABEL",
    "LOCAL_COMMIT_MESSAGE",
    "LOCAL_COMMIT_RESULT_LABEL",
    "LocalCommitError",
    "LocalCommitOutcome",
    "LocalCommitReceiptV2",
    "LocalCommitRequest",
    "create_isolated_local_commit",
    "commit_promoted_run",
    "local_commit_event_input",
]
