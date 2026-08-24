from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, model_validator

from ..hashing import (
    EXECUTABLE_FILE_MODE,
    REGULAR_FILE_MODE,
    SYMLINK_MODE,
    TREE_HASH_VERSION,
    TreeEntry,
    canonical_json_bytes,
    canonical_json_sha256,
    candidate_tree_sha256,
    sha256_hex,
)
from ..models import FrozenModel, Identifier, RepoPath, Sha256, TruthKind, UtcDateTime
from .evidence import TrustedCheckReceipt
from .models import (
    ArtifactEnvelopeReferenceV2,
    ArtifactPublication,
    Attempt,
    AttemptState,
    CriterionVerificationKind,
    EvidenceReference,
    MissionSnapshot,
    MissionStatus,
    PublishedArtifactReferenceV2,
    PublicationState,
    TaskKind,
    TaskState,
)


class FinalResultBundleError(RuntimeError):
    pass


class ArtifactResolver(Protocol):
    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...

    def resolve_enveloped(
        self, reference: ArtifactEnvelopeReferenceV2
    ) -> bytes | None: ...


class MutationEntry(FrozenModel):
    status: Literal["A", "D", "M"]
    path: RepoPath
    old_mode: Literal["100644", "100755", "120000"] | None = None
    new_mode: Literal["100644", "100755", "120000"] | None = None
    old_content_sha256: Sha256 | None = None
    new_content_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def shape_matches_status(self) -> MutationEntry:
        old = self.old_mode is not None and self.old_content_sha256 is not None
        new = self.new_mode is not None and self.new_content_sha256 is not None
        if (self.status, old, new) not in {
            ("A", False, True),
            ("D", True, False),
            ("M", True, True),
        }:
            raise ValueError("mutation fields do not match status")
        return self


class MutationManifest(FrozenModel):
    domain: Literal["graphene.mutation-manifest.v1"] = "graphene.mutation-manifest.v1"
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    result_commit: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$"
    )
    result_tree_id: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    changes: tuple[MutationEntry, ...]
    manifest_sha256: Sha256

    @model_validator(mode="after")
    def canonical_manifest(self) -> MutationManifest:
        paths = tuple(item.path for item in self.changes)
        if not paths or paths != tuple(sorted(set(paths))):
            raise ValueError("mutation paths must be sorted, unique, and non-empty")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"manifest_sha256"})
        )
        if self.manifest_sha256 != expected:
            raise ValueError("mutation manifest digest does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> MutationManifest:
        core = {"domain": "graphene.mutation-manifest.v1", **values}
        core.pop("manifest_sha256", None)
        canonical = cls.model_construct(**core, manifest_sha256="0" * 64).model_dump(
            mode="json", exclude={"manifest_sha256"}
        )
        return cls.model_validate(
            {**canonical, "manifest_sha256": canonical_json_sha256(canonical)}
        )


class CriterionReceiptBinding(FrozenModel):
    criterion_id: Identifier
    producer_task_ids: tuple[Identifier, ...]
    verification_kind: CriterionVerificationKind
    verifier_task_id: Identifier | None = None
    verifier_id: Identifier
    status: Literal["satisfied", "pending_final_decision"] = "satisfied"
    receipt_references: tuple[
        PublishedArtifactReferenceV2 | EvidenceReference, ...
    ] = ()

    @model_validator(mode="after")
    def canonical_binding(self) -> CriterionReceiptBinding:
        reference_keys = tuple(
            (
                "v2",
                item.publication_id,
                item.artifact_envelope_sha256,
            )
            if isinstance(item, PublishedArtifactReferenceV2)
            else ("legacy", item.kind, item.id, item.sha256)
            for item in self.receipt_references
        )
        if (
            self.producer_task_ids != tuple(sorted(set(self.producer_task_ids)))
            or reference_keys != tuple(sorted(set(reference_keys)))
            or (self.status == "satisfied" and not self.receipt_references)
            or (
                self.status == "pending_final_decision"
                and (
                    self.verification_kind != CriterionVerificationKind.HUMAN_GATE
                    or self.verifier_id != "final-result"
                    or bool(self.receipt_references)
                )
            )
        ):
            raise ValueError("criterion receipt binding is not canonical")
        return self


class OperatorDecisionState(FrozenModel):
    state: Literal["pending", "approved", "rejected"]
    mission_status: MissionStatus
    final_outcome: str | None = None

    @model_validator(mode="after")
    def state_matches_mission(self) -> OperatorDecisionState:
        if self.state == "approved":
            valid = self.final_outcome in {"approved", "approved_pending_commit"}
        elif self.state == "rejected":
            valid = (
                self.final_outcome == "rejected"
                or self.mission_status == MissionStatus.REJECTED
            )
        else:
            valid = (
                self.final_outcome is None
                and self.mission_status == MissionStatus.AWAITING_RESULT
            )
        if not valid:
            raise ValueError("operator decision does not match mission state")
        return self


class FinalDecisionReceiptV1(FrozenModel):
    schema_version: Literal[1] = 1
    domain: Literal["graphene.final-decision.v1"] = "graphene.final-decision.v1"
    receipt_id: Identifier
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    bundle_id: Identifier
    bundle_sha256: Sha256
    decision: Literal["approve", "reject"]
    expected_head_seq: int = Field(ge=1)
    expected_head_sha256: Sha256
    truth_kind: TruthKind
    operator_label: str = Field(min_length=1, max_length=64)
    rationale_sha256: Sha256 | None = None
    decided_at: UtcDateTime
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def canonical_receipt(self) -> FinalDecisionReceiptV1:
        core = self.model_dump(mode="json", exclude={"receipt_id", "receipt_sha256"})
        digest = canonical_json_sha256(core)
        if (
            self.receipt_id != f"final_decision_{digest[:32]}"
            or self.receipt_sha256 != digest
        ):
            raise ValueError("final decision receipt identity does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> FinalDecisionReceiptV1:
        core = {
            "schema_version": 1,
            "domain": "graphene.final-decision.v1",
            **values,
        }
        core.pop("receipt_id", None)
        core.pop("receipt_sha256", None)
        canonical = cls.model_construct(
            **core, receipt_id="placeholder", receipt_sha256="0" * 64
        ).model_dump(mode="json", exclude={"receipt_id", "receipt_sha256"})
        digest = canonical_json_sha256(canonical)
        return cls.model_validate(
            {
                **canonical,
                "receipt_id": f"final_decision_{digest[:32]}",
                "receipt_sha256": digest,
            }
        )


class FinalBundleVerificationReceiptV1(FrozenModel):
    """The store's own record that it recomputed a bundle before registering it.

    ``verify_final_result_bundle`` rebuilds the candidate patch, the mutation
    manifest and the resulting tree from the repository. Registration used to be
    caller discipline: the CLI called the verifier, the store took the caller's
    word, and an invented path/tree combination registered and approved cleanly.
    The store now runs the recompute itself and issues this receipt; approval
    accepts nothing that does not carry one bound to the exact bundle.
    """

    schema_version: Literal[1] = 1
    domain: Literal["graphene.final-bundle-verification.v1"] = (
        "graphene.final-bundle-verification.v1"
    )
    receipt_id: Identifier
    mission_id: Identifier
    bundle_id: Identifier
    bundle_sha256: Sha256
    snapshot_sha256: Sha256
    plan_revision: int = Field(ge=1)
    policy_sha256: Sha256
    base_commit: str = Field(min_length=40, max_length=40)
    expected_head_seq: int = Field(ge=1)
    expected_head_sha256: Sha256
    verifier: Literal["verify_final_result_bundle"] = "verify_final_result_bundle"
    verified_at: UtcDateTime
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def canonical_receipt(self) -> FinalBundleVerificationReceiptV1:
        core = self.model_dump(mode="json", exclude={"receipt_id", "receipt_sha256"})
        digest = canonical_json_sha256(core)
        if (
            self.receipt_id != f"bundle_verified_{digest[:32]}"
            or self.receipt_sha256 != digest
        ):
            raise ValueError("final bundle verification receipt identity does not match")
        return self

    def binds(self, bundle: FinalResultBundleV2) -> bool:
        """True when this receipt was issued for exactly ``bundle``."""

        return (
            self.mission_id == bundle.mission_id
            and self.bundle_id == bundle.bundle_id
            and self.bundle_sha256 == bundle.bundle_sha256
            and self.snapshot_sha256 == bundle.snapshot_sha256
            and self.plan_revision == bundle.plan_revision
            and self.policy_sha256 == bundle.policy_sha256
            and self.base_commit == bundle.base_commit
            and self.expected_head_seq == bundle.event_head_seq
            and self.expected_head_sha256 == bundle.event_head_sha256
        )

    @classmethod
    def issue(
        cls, bundle: FinalResultBundleV2, *, verified_at: datetime
    ) -> FinalBundleVerificationReceiptV1:
        core = cls.model_construct(
            schema_version=1,
            domain="graphene.final-bundle-verification.v1",
            receipt_id="placeholder",
            mission_id=bundle.mission_id,
            bundle_id=bundle.bundle_id,
            bundle_sha256=bundle.bundle_sha256,
            snapshot_sha256=bundle.snapshot_sha256,
            plan_revision=bundle.plan_revision,
            policy_sha256=bundle.policy_sha256,
            base_commit=bundle.base_commit,
            expected_head_seq=bundle.event_head_seq,
            expected_head_sha256=bundle.event_head_sha256,
            verifier="verify_final_result_bundle",
            verified_at=verified_at,
            receipt_sha256="0" * 64,
        ).model_dump(mode="json", exclude={"receipt_id", "receipt_sha256"})
        digest = canonical_json_sha256(core)
        return cls.model_validate(
            {
                **core,
                "receipt_id": f"bundle_verified_{digest[:32]}",
                "receipt_sha256": digest,
            }
        )


class FinalResultBundleV2(FrozenModel):
    schema_version: Literal[2] = 2
    domain: Literal["graphene.final-result.v2"] = "graphene.final-result.v2"
    bundle_id: Identifier
    mission_id: Identifier
    snapshot_sha256: Sha256
    event_head_seq: int = Field(ge=1)
    event_head_sha256: Sha256
    plan_revision: int = Field(ge=1)
    plan_sha256: Sha256
    policy_id: Identifier
    policy_revision: int = Field(ge=1)
    policy_sha256: Sha256
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    candidate_publication: ArtifactPublication
    candidate_reference: PublishedArtifactReferenceV2
    candidate_byte_count: int = Field(ge=0)
    verification_publication: ArtifactPublication
    verification_reference: PublishedArtifactReferenceV2
    verification_receipt: TrustedCheckReceipt
    result_commit: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$"
    )
    result_tree_id: str = Field(pattern=r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    candidate_tree_sha256: Sha256
    mutation_manifest: MutationManifest
    changed_paths: tuple[RepoPath, ...]
    criterion_receipts: tuple[CriterionReceiptBinding, ...]
    unresolved_unknowns: tuple[str, ...]
    operator_decision: OperatorDecisionState
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def exact_identity(self) -> FinalResultBundleV2:
        criterion_ids = tuple(item.criterion_id for item in self.criterion_receipts)
        if (
            self.candidate_tree_hash_version != TREE_HASH_VERSION
            or self.changed_paths
            != tuple(item.path for item in self.mutation_manifest.changes)
            or self.changed_paths != tuple(sorted(set(self.changed_paths)))
            or criterion_ids != tuple(sorted(set(criterion_ids)))
            or self.unresolved_unknowns != tuple(sorted(set(self.unresolved_unknowns)))
            or self.candidate_publication.mission_id != self.mission_id
            or self.verification_publication.mission_id != self.mission_id
            or self.candidate_publication.plan_revision != self.plan_revision
            or self.verification_publication.plan_revision != self.plan_revision
            or self.candidate_publication.published_reference()
            != self.candidate_reference
            or self.verification_publication.published_reference()
            != self.verification_reference
            or self.candidate_byte_count != self.candidate_reference.byte_count
            or self.verification_receipt.mission_id != self.mission_id
            or self.verification_receipt.task_id
            != self.verification_publication.task_id
            or self.verification_receipt.attempt_id
            != self.verification_publication.attempt_id
            or self.verification_receipt.plan_revision != self.plan_revision
            or self.verification_receipt.policy_sha256 != self.policy_sha256
            or self.verification_receipt.base_sha != self.base_commit
            or self.verification_receipt.candidate_tree_hash_version
            != self.candidate_tree_hash_version
            or self.verification_receipt.candidate_tree_sha256
            != self.candidate_tree_sha256
            or canonical_json_sha256(self.verification_receipt.model_dump(mode="json"))
            != self.verification_reference.content_sha256
            or self.mutation_manifest.base_commit != self.base_commit
            or self.mutation_manifest.result_commit != self.result_commit
            or self.mutation_manifest.result_tree_id != self.result_tree_id
            or (self.result_commit is None)
            != (self.operator_decision.state == "pending")
            or (
                any(
                    item.status == "pending_final_decision"
                    for item in self.criterion_receipts
                )
                and self.operator_decision.state != "pending"
            )
        ):
            raise ValueError("final result bundle bindings disagree")
        core = self.model_dump(mode="json", exclude={"bundle_id", "bundle_sha256"})
        expected = canonical_json_sha256(core)
        if (
            self.bundle_id != f"final_result_{expected[:32]}"
            or self.bundle_sha256 != expected
        ):
            raise ValueError("final result bundle identity does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> FinalResultBundleV2:
        core = {
            "schema_version": 2,
            "domain": "graphene.final-result.v2",
            **values,
        }
        core.pop("bundle_id", None)
        core.pop("bundle_sha256", None)
        canonical = cls.model_construct(
            **core, bundle_id="placeholder", bundle_sha256="0" * 64
        ).model_dump(mode="json", exclude={"bundle_id", "bundle_sha256"})
        digest = canonical_json_sha256(canonical)
        return cls.model_validate(
            {
                **canonical,
                "bundle_id": f"final_result_{digest[:32]}",
                "bundle_sha256": digest,
            }
        )


@dataclass(frozen=True, slots=True)
class _RepositoryEntry:
    mode: str
    object_id: str
    content: bytes


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    extra_env: dict[str, str] | None = None,
) -> bytes:
    try:
        result = subprocess.run(
            ("git", "-C", os.fspath(repository), *arguments),
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
                "PATH": os.defpath,
                **(extra_env or {}),
            },
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FinalResultBundleError(
            "result repository Git operation failed"
        ) from error
    if result.returncode:
        raise FinalResultBundleError("result repository Git operation was rejected")
    return result.stdout


def _repository(repository: Path) -> Path:
    try:
        metadata = repository.lstat()
        root = repository.resolve(strict=True)
    except OSError as error:
        raise FinalResultBundleError("result repository is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise FinalResultBundleError("result repository root is unsafe")
    top = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip())
    if top.resolve(strict=True) != root:
        raise FinalResultBundleError("result repository is not a Git root")
    return root


def _commit(repository: Path, revision: str) -> str:
    value = os.fsdecode(
        _git(repository, "rev-parse", "--verify", f"{revision}^{{commit}}")
    ).strip()
    if len(value) not in {40, 64} or any(
        item not in "0123456789abcdef" for item in value
    ):
        raise FinalResultBundleError("result repository commit is invalid")
    return value


def _tree_entries(
    repository: Path, revision: str
) -> tuple[str, dict[str, _RepositoryEntry]]:
    tree_id = os.fsdecode(
        _git(repository, "rev-parse", "--verify", f"{revision}^{{tree}}")
    ).strip()
    entries: dict[str, _RepositoryEntry] = {}
    for record in _git(
        repository, "ls-tree", "-r", "-z", "--full-tree", revision
    ).split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            raw_mode, kind, raw_object_id = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8")
            mode = raw_mode.decode("ascii")
            object_id = raw_object_id.decode("ascii")
        except (UnicodeDecodeError, ValueError) as error:
            raise FinalResultBundleError("result tree entry is malformed") from error
        if kind != b"blob" or mode not in {"100644", "100755", "120000"}:
            raise FinalResultBundleError("result tree contains an unsupported entry")
        content = _git(repository, "cat-file", "blob", object_id)
        entries[path] = _RepositoryEntry(mode, object_id, content)
    return tree_id, entries


def _tree_digest(entries: dict[str, _RepositoryEntry]) -> str:
    modes = {
        "100644": REGULAR_FILE_MODE,
        "100755": EXECUTABLE_FILE_MODE,
        "120000": SYMLINK_MODE,
    }
    return candidate_tree_sha256(
        {
            path: TreeEntry(entry.content, modes[entry.mode])
            for path, entry in entries.items()
        }
    )


def _manifest(
    base_commit: str,
    result_commit: str | None,
    result_tree_id: str,
    before: dict[str, _RepositoryEntry],
    after: dict[str, _RepositoryEntry],
) -> MutationManifest:
    changes = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        if old == new:
            continue
        changes.append(
            MutationEntry(
                status="A" if old is None else "D" if new is None else "M",
                path=path,
                old_mode=None if old is None else old.mode,
                new_mode=None if new is None else new.mode,
                old_content_sha256=None if old is None else sha256_hex(old.content),
                new_content_sha256=None if new is None else sha256_hex(new.content),
            )
        )
    return MutationManifest.create(
        base_commit=base_commit,
        result_commit=result_commit,
        result_tree_id=result_tree_id,
        changes=tuple(changes),
    )


def _prospective_tree(
    repository: Path, base_commit: str, candidate_bytes: bytes
) -> tuple[str, dict[str, _RepositoryEntry]]:
    with tempfile.TemporaryDirectory(prefix="graphene-final-review-") as temporary:
        clone = Path(temporary) / "repository.git"
        try:
            result = subprocess.run(
                (
                    "git",
                    "clone",
                    "--bare",
                    "--no-hardlinks",
                    "--quiet",
                    os.fspath(repository),
                    os.fspath(clone),
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                    "LC_ALL": "C",
                    "PATH": os.defpath,
                },
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise FinalResultBundleError(
                "prospective result repository clone failed"
            ) from error
        if result.returncode:
            raise FinalResultBundleError(
                "prospective result repository clone was rejected"
            )
        index = Path(temporary) / "review.index"
        environment = {"GIT_INDEX_FILE": os.fspath(index)}
        _git(clone, "read-tree", base_commit, extra_env=environment)
        _git(
            clone,
            "apply",
            "--cached",
            "--binary",
            "--whitespace=nowarn",
            "-",
            input_bytes=candidate_bytes,
            extra_env=environment,
        )
        tree_id = os.fsdecode(_git(clone, "write-tree", extra_env=environment)).strip()
        resolved_tree_id, entries = _tree_entries(clone, tree_id)
        if resolved_tree_id != tree_id:
            raise FinalResultBundleError("prospective result tree changed")
        return tree_id, entries


def _resolve(
    resolver: ArtifactResolver,
    reference: PublishedArtifactReferenceV2 | EvidenceReference,
) -> bytes:
    try:
        content = (
            resolver.resolve_enveloped(reference)
            if isinstance(reference, PublishedArtifactReferenceV2)
            else resolver.resolve(reference.kind, reference.id)
        )
    except Exception as error:
        raise FinalResultBundleError("bundle artifact resolver failed") from error
    if not isinstance(content, bytes) or sha256_hex(content) != reference.sha256:
        raise FinalResultBundleError("bundle artifact is unresolved or changed")
    return content


def _final_publication(
    snapshot: MissionSnapshot, kind: TaskKind
) -> tuple[ArtifactPublication, Attempt, PublishedArtifactReferenceV2]:
    task_ids = {item.task_id for item in snapshot.tasks if item.kind == kind}
    matches = tuple(
        item
        for item in snapshot.publications
        if item.task_id in task_ids and item.state == PublicationState.ACCEPTED
    )
    if len(task_ids) != 1 or len(matches) != 1:
        raise FinalResultBundleError("bundle requires one accepted final publication")
    publication = matches[0]
    attempts = tuple(
        item
        for item in snapshot.attempts
        if item.attempt_id == publication.attempt_id
        and item.task_id == publication.task_id
        and item.mission_id == publication.mission_id
        and item.plan_revision == publication.plan_revision
    )
    if len(attempts) != 1 or attempts[0].state != AttemptState.COMMITTED:
        raise FinalResultBundleError("final publication attempt is not committed")
    evidence = tuple(
        item
        for item in attempts[0].evidence_refs
        if item.kind == publication.kind and item.sha256 == publication.sha256
    )
    if len(evidence) != 1:
        raise FinalResultBundleError("final publication evidence is ambiguous")
    try:
        reference = publication.published_reference()
    except ValueError as error:
        raise FinalResultBundleError(
            "final publication has no V2 artifact envelope"
        ) from error
    if reference.artifact_id != evidence[0].id:
        raise FinalResultBundleError("final publication artifact was swapped")
    return publication, attempts[0], reference


def _criterion_receipts(
    snapshot: MissionSnapshot,
    verification_task_id: str,
    verification_reference: PublishedArtifactReferenceV2,
    receipt: TrustedCheckReceipt,
    resolver: ArtifactResolver,
    *,
    pending_final_decision: bool,
) -> tuple[CriterionReceiptBinding, ...]:
    task_ids = {item.task_id for item in snapshot.tasks}
    bindings = []
    for criterion in snapshot.plan.criteria:
        if (
            not criterion.producer_task_ids
            or not set(criterion.producer_task_ids) <= task_ids
        ):
            raise FinalResultBundleError("criterion coverage producer is unavailable")
        if criterion.verification_kind == CriterionVerificationKind.DETERMINISTIC_CHECK:
            if (
                criterion.verifier_task_id != verification_task_id
                or criterion.verifier_id != receipt.template_id
            ):
                raise FinalResultBundleError(
                    "criterion is not bound to final verification"
                )
            references = (verification_reference,)
        elif criterion.verification_kind == CriterionVerificationKind.HUMAN_GATE:
            gates = tuple(
                item
                for item in snapshot.gates
                if item.gate_id == criterion.verifier_id and item.resolution is not None
            )
            if len(gates) == 1 and gates[0].evidence:
                references = gates[0].evidence
                status = "satisfied"
                for reference in references:
                    _resolve(resolver, reference)
            elif (
                not gates
                and pending_final_decision
                and criterion.verifier_id == "final-result"
            ):
                references = ()
                status = "pending_final_decision"
            else:
                raise FinalResultBundleError(
                    "criterion human-gate receipt is unavailable"
                )
        else:
            raise FinalResultBundleError("model assertions cannot verify criteria")
        if criterion.verification_kind != CriterionVerificationKind.HUMAN_GATE:
            status = "satisfied"
        bindings.append(
            CriterionReceiptBinding(
                criterion_id=criterion.criterion_id,
                producer_task_ids=criterion.producer_task_ids,
                verification_kind=criterion.verification_kind,
                verifier_task_id=criterion.verifier_task_id,
                verifier_id=criterion.verifier_id or "unavailable",
                status=status,
                receipt_references=references,
            )
        )
    if not bindings:
        raise FinalResultBundleError("bundle has no criterion receipts")
    return tuple(sorted(bindings, key=lambda item: item.criterion_id))


def _operator_decision(snapshot: MissionSnapshot) -> OperatorDecisionState:
    outcome = snapshot.mission.final_outcome
    status = snapshot.mission.status
    if outcome in {"approved", "approved_pending_commit"}:
        state = "approved"
    elif outcome == "rejected" or status == MissionStatus.REJECTED:
        state = "rejected"
    elif outcome is None and status == MissionStatus.AWAITING_RESULT:
        state = "pending"
    else:
        raise FinalResultBundleError("mission has no final operator decision state")
    return OperatorDecisionState(
        state=state, mission_status=status, final_outcome=outcome
    )


def build_final_result_bundle(
    snapshot: MissionSnapshot,
    resolver: ArtifactResolver,
    repository: Path,
    *,
    result_commit: str | None = None,
    policy_sha256: str,
) -> FinalResultBundleV2:
    """Build the exact V2 identity; this does not approve or mutate the mission."""

    snapshot = MissionSnapshot.model_validate(snapshot)
    if (
        snapshot.plan.mission_id != snapshot.mission.mission_id
        or snapshot.plan.revision != snapshot.mission.plan_revision
        or snapshot.policy.policy_sha256 != policy_sha256
        or snapshot.policy.base_sha != snapshot.mission.base_sha
        or snapshot.head.seq < 1
        or snapshot.head.event_sha256 is None
        or any(item.state != TaskState.DONE for item in snapshot.tasks)
    ):
        raise FinalResultBundleError("snapshot is not a completed current plan")
    root = _repository(repository)
    base_commit = _commit(root, snapshot.mission.base_sha)
    if base_commit != snapshot.mission.base_sha:
        raise FinalResultBundleError("mission base commit changed")

    candidate, candidate_attempt, candidate_reference = _final_publication(
        snapshot, TaskKind.ASSEMBLY
    )
    verification, verification_attempt, verification_reference = _final_publication(
        snapshot, TaskKind.VERIFICATION
    )
    if candidate.kind != "patch" or verification.kind != "test-receipt":
        raise FinalResultBundleError("final publication kinds are unsupported")
    candidate_bytes = _resolve(resolver, candidate_reference)
    verification_bytes = _resolve(resolver, verification_reference)
    try:
        receipt = TrustedCheckReceipt.model_validate_json(verification_bytes)
    except ValueError as error:
        raise FinalResultBundleError("verification receipt is invalid") from error
    if (
        receipt.mission_id != snapshot.mission.mission_id
        or receipt.task_id != verification.task_id
        or receipt.attempt_id != verification_attempt.attempt_id
        or receipt.plan_revision != snapshot.plan.revision
        or receipt.fencing_token != verification_attempt.fencing_token
        or receipt.policy_sha256 != policy_sha256
        or receipt.base_sha != base_commit
        or receipt.accepted_input_references != (candidate_reference,)
        or receipt.candidate_references != (candidate_reference,)
        or receipt.result_code != "passed"
    ):
        raise FinalResultBundleError("verification receipt bindings disagree")

    _base_tree, before = _tree_entries(root, base_commit)
    if result_commit is None:
        if _operator_decision(snapshot).state != "pending":
            raise FinalResultBundleError(
                "pending bundle requires an undecided final result"
            )
        result_tree_id, after = _prospective_tree(root, base_commit, candidate_bytes)
    else:
        result_commit = _commit(root, result_commit)
        parents = os.fsdecode(
            _git(root, "rev-list", "--parents", "-n", "1", result_commit)
        ).split()
        if parents != [result_commit, base_commit]:
            raise FinalResultBundleError(
                "result commit is not based exactly on mission base"
            )
        if candidate_bytes != _git(
            root, "diff", "--binary", base_commit, result_commit, "--"
        ):
            raise FinalResultBundleError(
                "candidate patch does not produce result commit"
            )
        result_tree_id, after = _tree_entries(root, result_commit)
    tree_sha256 = _tree_digest(after)
    if (
        receipt.candidate_tree_hash_version != TREE_HASH_VERSION
        or receipt.candidate_tree_sha256 != tree_sha256
    ):
        raise FinalResultBundleError("verification receipt names another result tree")
    manifest = _manifest(base_commit, result_commit, result_tree_id, before, after)
    operator_decision = _operator_decision(snapshot)
    criterion_receipts = _criterion_receipts(
        snapshot,
        verification.task_id,
        verification_reference,
        receipt,
        resolver,
        pending_final_decision=operator_decision.state == "pending",
    )
    return FinalResultBundleV2.create(
        mission_id=snapshot.mission.mission_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        event_head_seq=snapshot.head.seq,
        event_head_sha256=snapshot.head.event_sha256,
        plan_revision=snapshot.plan.revision,
        plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
        policy_id=snapshot.policy.policy_id,
        policy_revision=snapshot.policy.revision,
        policy_sha256=policy_sha256,
        base_commit=base_commit,
        candidate_publication=candidate,
        candidate_reference=candidate_reference,
        candidate_byte_count=len(candidate_bytes),
        verification_publication=verification,
        verification_reference=verification_reference,
        verification_receipt=receipt,
        result_commit=result_commit,
        result_tree_id=result_tree_id,
        candidate_tree_hash_version=TREE_HASH_VERSION,
        candidate_tree_sha256=tree_sha256,
        mutation_manifest=manifest,
        changed_paths=tuple(item.path for item in manifest.changes),
        criterion_receipts=criterion_receipts,
        unresolved_unknowns=snapshot.unknowns,
        operator_decision=operator_decision,
    )


def verify_final_result_bundle(
    bundle: FinalResultBundleV2 | bytes,
    snapshot: MissionSnapshot,
    resolver: ArtifactResolver,
    repository: Path,
    *,
    expected_policy_sha256: str,
) -> bool:
    try:
        if isinstance(bundle, bytes):
            parsed = FinalResultBundleV2.model_validate_json(bundle)
            if canonical_json_bytes(parsed.model_dump(mode="json")) != bundle:
                return False
        else:
            parsed = FinalResultBundleV2.model_validate(bundle)
        if parsed.policy_sha256 != expected_policy_sha256:
            return False
        if parsed.operator_decision.state == "pending" and (
            snapshot.head.seq != parsed.event_head_seq
            or snapshot.head.event_sha256 != parsed.event_head_sha256
            or snapshot.mission.final_outcome is not None
        ):
            historical = snapshot.model_dump(mode="json", exclude={"snapshot_sha256"})
            historical["mission"]["status"] = MissionStatus.AWAITING_RESULT.value
            historical["mission"]["final_outcome"] = None
            historical["head"] = {
                "mission_id": parsed.mission_id,
                "seq": parsed.event_head_seq,
                "event_sha256": parsed.event_head_sha256,
                "event_count": parsed.event_head_seq,
            }
            historical["snapshot_sha256"] = canonical_json_sha256(historical)
            snapshot = MissionSnapshot.model_validate(historical)
            if snapshot.snapshot_sha256 != parsed.snapshot_sha256:
                return False
        rebuilt = build_final_result_bundle(
            snapshot,
            resolver,
            repository,
            result_commit=parsed.result_commit,
            policy_sha256=expected_policy_sha256,
        )
        return rebuilt == parsed
    except (FinalResultBundleError, TypeError, ValueError):
        return False


__all__ = [
    "CriterionReceiptBinding",
    "FinalResultBundleError",
    "FinalResultBundleV2",
    "FinalDecisionReceiptV1",
    "MutationEntry",
    "MutationManifest",
    "OperatorDecisionState",
    "build_final_result_bundle",
    "FinalBundleVerificationReceiptV1",
    "verify_final_result_bundle",
]
