from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

from graphene.artifact_envelope import (
    ArtifactEnvelopeV2,
    DirectArtifactInputV2,
    verify_artifact_envelope,
)
from graphene.hashing import (
    canonical_json_bytes,
    canonical_json_sha256,
    candidate_tree_sha256,
    sha256_hex,
)
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.final_bundle import (
    FinalResultBundleError,
    build_final_result_bundle,
    verify_final_result_bundle,
)
from graphene.orchestration.mission_models import (
    ArtifactEnvelopeReferenceV2,
    ArtifactPublication,
    Attempt,
    AttemptState,
    CriterionVerificationKind,
    EvidenceReference,
    GenericEvidenceLink,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    ProjectPolicy,
    ProjectPolicySummary,
    PublicationState,
    Task,
    TaskState,
)
from tests.unit.orchestration.test_store import NOW, _command, _mission, _plan, _policy


@dataclass
class Artifacts:
    values: dict[tuple[str, str], bytes] = field(default_factory=dict)
    envelopes: dict[str, ArtifactEnvelopeV2] = field(default_factory=dict)

    def put(self, kind: str, content: bytes) -> EvidenceReference:
        digest = sha256_hex(content)
        reference = EvidenceReference(
            kind=kind, id=f"artifact-{digest[:24]}", sha256=digest
        )
        self.values[(kind, reference.id)] = content
        return reference

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        return self.values.get((kind, artifact_id))

    def put_enveloped(
        self, envelope: ArtifactEnvelopeV2, content: bytes
    ) -> tuple[EvidenceReference, ArtifactEnvelopeReferenceV2]:
        verify_artifact_envelope(envelope, content)
        content_reference = self.put(envelope.artifact_kind, content)
        self.envelopes[envelope.artifact_envelope_sha256] = envelope
        return content_reference, ArtifactEnvelopeReferenceV2(
            schema_version=2,
            artifact_id=content_reference.id,
            producer_task_id=envelope.task_id,
            output_name=envelope.output_name,
            kind=envelope.artifact_kind,
            media_type=envelope.media_type,
            byte_count=envelope.byte_count,
            content_sha256=envelope.content_sha256,
            artifact_envelope_sha256=envelope.artifact_envelope_sha256,
        )

    def resolve_enveloped(self, reference: ArtifactEnvelopeReferenceV2) -> bytes | None:
        content = self.resolve(reference.kind, reference.artifact_id)
        envelope = self.envelopes.get(reference.artifact_envelope_sha256)
        if content is None or envelope is None:
            return None
        try:
            verify_artifact_envelope(envelope, content)
        except ValueError:
            return None
        if (
            reference.producer_task_id,
            reference.output_name,
            reference.kind,
            reference.media_type,
            reference.byte_count,
            reference.content_sha256,
        ) != (
            envelope.task_id,
            envelope.output_name,
            envelope.artifact_kind,
            envelope.media_type,
            envelope.byte_count,
            envelope.content_sha256,
        ):
            return None
        return content


def _git(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ("git", "-C", os.fspath(repository), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _repository(path: Path, base_content: bytes) -> tuple[str, str]:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Graphene Tests")
    _git(path, "config", "user.email", "graphene@example.invalid")
    (path / "base.txt").write_bytes(base_content)
    _git(path, "add", "--all", "--")
    _git(path, "commit", "-q", "-m", "base")
    base = _git(path, "rev-parse", "HEAD").decode().strip()
    (path / "feature.txt").write_bytes(b"bounded result\n")
    _git(path, "add", "--all", "--")
    _git(path, "commit", "-q", "-m", "result")
    result = _git(path, "rev-parse", "HEAD").decode().strip()
    return base, result


def _done(task: Task) -> Task:
    return Task.model_validate(
        {
            **task.model_dump(mode="json"),
            "attempt_count": 1,
            "state": TaskState.DONE,
        }
    )


def _snapshot(
    repository: Path, base: str, result: str
) -> tuple[MissionSnapshot, Artifacts, str]:
    policy = ProjectPolicy.model_validate(
        {**_policy().model_dump(mode="json"), "base_sha": base}
    )
    policy_sha256 = canonical_json_sha256(policy.model_dump(mode="json"))
    plan = _plan()
    plan_sha256 = canonical_json_sha256(plan.model_dump(mode="json"))
    tasks = tuple(_done(item) for item in plan.tasks)
    assembly = next(item for item in tasks if item.task_id == "assemble")
    verification = next(item for item in tasks if item.task_id == "verify")
    artifacts = Artifacts()
    patch = _git(repository, "diff", "--binary", base, result, "--")
    tree_sha256 = candidate_tree_sha256(
        {
            "base.txt": (repository / "base.txt").read_bytes(),
            "feature.txt": b"bounded result\n",
        }
    )
    candidate_envelope = ArtifactEnvelopeV2.create(
        patch,
        mission_id="mission-1",
        plan_revision=1,
        plan_sha256=plan_sha256,
        task_id=assembly.task_id,
        attempt_id="attempt-assembly",
        fencing_token=1,
        policy_sha256=policy_sha256,
        base_git_commit=base,
        direct_inputs=(),
        output_name=assembly.expected_outputs[0].name,
        artifact_kind="patch",
        media_type="application/vnd.graphene.git-patch",
        tree_hash_version="graphene.tree.v2",
        tree_sha256=tree_sha256,
        created_by="trusted-worker-wrapper",
    )
    candidate_reference, candidate_artifact = artifacts.put_enveloped(
        candidate_envelope, patch
    )
    candidate_attempt = Attempt(
        attempt_id="attempt-assembly",
        mission_id="mission-1",
        plan_revision=1,
        task_id=assembly.task_id,
        attempt_number=1,
        worker_id="worker-assembly",
        workspace_id="workspace-assembly",
        lease_id="lease-assembly",
        fencing_token=1,
        dispatch_command_id=_command("dispatch-assembly"),
        state=AttemptState.COMMITTED,
        started_at=NOW,
        ended_at=NOW + timedelta(seconds=1),
        evidence_link=GenericEvidenceLink(evidence_id="evidence-assembly"),
        result_code="passed",
        evidence_refs=(candidate_reference,),
    )
    candidate = ArtifactPublication(
        publication_id="publication-assembly",
        mission_id="mission-1",
        plan_revision=1,
        task_id=assembly.task_id,
        attempt_id=candidate_attempt.attempt_id,
        output_name=assembly.expected_outputs[0].name,
        kind="patch",
        sha256=candidate_reference.sha256,
        artifact=candidate_artifact,
        paths=assembly.expected_outputs[0].paths,
        state=PublicationState.ACCEPTED,
        consumers=(verification.task_id,),
    )
    candidate_publication_reference = candidate.published_reference()
    verification_attempt_id = "attempt-verification"
    receipt = TrustedCheckReceipt(
        schema_version=2,
        mission_id="mission-1",
        task_id=verification.task_id,
        attempt_id=verification_attempt_id,
        plan_revision=1,
        fencing_token=1,
        policy_sha256=policy_sha256,
        base_sha=base,
        runner_id="graphene_check_runner_v1",
        template_id=verification.acceptance_checks[0],
        template_sha256="b" * 64,
        accepted_input_references=(candidate_publication_reference,),
        candidate_references=(candidate_publication_reference,),
        candidate_tree_hash_version="graphene.tree.v2",
        candidate_tree_sha256=tree_sha256,
        result_code="passed",
        exit_code=0,
        timed_out=False,
        output_sha256=sha256_hex(b"check output"),
        output_truncated=False,
        cleanup_complete=True,
    )
    verification_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    verification_envelope = ArtifactEnvelopeV2.create(
        verification_bytes,
        mission_id="mission-1",
        plan_revision=1,
        plan_sha256=plan_sha256,
        task_id=verification.task_id,
        attempt_id=verification_attempt_id,
        fencing_token=1,
        policy_sha256=policy_sha256,
        base_git_commit=base,
        direct_inputs=(
            DirectArtifactInputV2(
                publication_id=candidate.publication_id,
                producer_task_id=candidate.task_id,
                output_name=candidate.output_name,
                artifact_envelope_sha256=(candidate_artifact.artifact_envelope_sha256),
            ),
        ),
        output_name=verification.expected_outputs[0].name,
        artifact_kind="test-receipt",
        media_type="application/vnd.graphene.check-receipt+json",
        tree_hash_version="graphene.tree.v2",
        tree_sha256=tree_sha256,
        created_by="trusted-worker-wrapper",
    )
    verification_reference, verification_artifact = artifacts.put_enveloped(
        verification_envelope, verification_bytes
    )
    verification_attempt = Attempt(
        attempt_id=verification_attempt_id,
        mission_id="mission-1",
        plan_revision=1,
        task_id=verification.task_id,
        attempt_number=1,
        worker_id="worker-verification",
        workspace_id="workspace-verification",
        lease_id="lease-verification",
        fencing_token=1,
        dispatch_command_id=_command("dispatch-verification"),
        state=AttemptState.COMMITTED,
        started_at=NOW + timedelta(seconds=2),
        ended_at=NOW + timedelta(seconds=3),
        evidence_link=GenericEvidenceLink(evidence_id="evidence-verification"),
        result_code="passed",
        input_publications=(candidate_publication_reference,),
        evidence_refs=(verification_reference,),
    )
    verification_publication = ArtifactPublication(
        publication_id="publication-verification",
        mission_id="mission-1",
        plan_revision=1,
        task_id=verification.task_id,
        attempt_id=verification_attempt.attempt_id,
        output_name=verification.expected_outputs[0].name,
        kind="test-receipt",
        sha256=verification_reference.sha256,
        artifact=verification_artifact,
        paths=verification.expected_outputs[0].paths,
        state=PublicationState.ACCEPTED,
    )
    mission = _mission().model_copy(
        update={
            "base_sha": base,
            "final_outcome": "approved_pending_commit",
            "status": MissionStatus.AWAITING_RESULT,
            "unknowns": ("External signature is not proven.",),
        }
    )
    core = {
        "policy": ProjectPolicySummary(
            policy_id=policy.policy_id,
            revision=policy.revision,
            repo_id=policy.repo_id,
            base_ref=policy.base_ref,
            base_sha=base,
            command_template_ids=tuple(
                item.template_id for item in policy.command_templates
            ),
            max_concurrency=policy.max_concurrency,
            retry_limit=policy.retry_limit,
            network_mode=policy.network.mode,
            policy_sha256=policy_sha256,
        ),
        "mission": mission,
        "plan": plan,
        "tasks": tasks,
        "attempts": tuple(
            sorted(
                (candidate_attempt, verification_attempt),
                key=lambda item: item.attempt_id,
            )
        ),
        "leases": (),
        "publications": (candidate, verification_publication),
        "gates": (),
        "head": MissionHead(
            mission_id="mission-1", seq=1, event_sha256="c" * 64, event_count=1
        ),
        "unknowns": mission.unknowns,
    }
    provisional = MissionSnapshot.model_construct(
        schema_version=1, **core, snapshot_sha256="0" * 64
    )
    canonical = provisional.model_dump(mode="json", exclude={"snapshot_sha256"})
    snapshot = MissionSnapshot.model_validate(
        {**canonical, "snapshot_sha256": canonical_json_sha256(canonical)}
    )
    return snapshot, artifacts, policy_sha256


def test_final_bundle_builds_and_verifies_exact_canonical_identity(tmp_path) -> None:
    repository = tmp_path / "repository"
    base, result = _repository(repository, b"base one\n")
    snapshot, artifacts, policy_sha256 = _snapshot(repository, base, result)

    bundle = build_final_result_bundle(
        snapshot,
        artifacts,
        repository,
        result_commit=result,
        policy_sha256=policy_sha256,
    )
    raw = canonical_json_bytes(bundle.model_dump(mode="json"))

    assert bundle.base_commit == base
    assert bundle.result_commit == result
    assert bundle.changed_paths == ("feature.txt",)
    assert bundle.criterion_receipts[0].criterion_id == "criterion-checks"
    assert bundle.operator_decision.state == "approved"
    assert verify_final_result_bundle(
        bundle,
        snapshot,
        artifacts,
        repository,
        expected_policy_sha256=policy_sha256,
    )
    assert verify_final_result_bundle(
        raw,
        snapshot,
        artifacts,
        repository,
        expected_policy_sha256=policy_sha256,
    )
    for changed in (
        bundle.model_copy(update={"base_commit": "f" * 40}),
        bundle.model_copy(update={"plan_revision": 2}),
        bundle.model_copy(
            update={
                "candidate_publication": bundle.candidate_publication.model_copy(
                    update={"task_id": "work-a"}
                )
            }
        ),
        bundle.model_copy(
            update={"verification_reference": bundle.candidate_reference}
        ),
        bundle.model_copy(update={"result_tree_id": "e" * 40}),
    ):
        assert not verify_final_result_bundle(
            changed,
            snapshot,
            artifacts,
            repository,
            expected_policy_sha256=policy_sha256,
        )


def test_pending_adk_final_gate_is_explicit_without_fabricated_receipt(
    tmp_path,
) -> None:
    repository = tmp_path / "repository"
    base, result = _repository(repository, b"base one\n")
    snapshot, artifacts, policy_sha256 = _snapshot(repository, base, result)
    criterion = snapshot.plan.criteria[0].model_copy(
        update={
            "verification_kind": CriterionVerificationKind.HUMAN_GATE,
            "verifier_task_id": None,
            "verifier_id": "final-result",
        }
    )
    plan = snapshot.plan.model_copy(update={"criteria": (criterion,)})
    mission = snapshot.mission.model_copy(
        update={"final_outcome": None, "status": MissionStatus.AWAITING_RESULT}
    )
    values = snapshot.model_dump(mode="json", exclude={"snapshot_sha256"})
    values.update(
        plan=plan.model_dump(mode="json"),
        mission=mission.model_dump(mode="json"),
    )
    pending = MissionSnapshot.model_validate(
        {**values, "snapshot_sha256": canonical_json_sha256(values)}
    )

    bundle = build_final_result_bundle(
        pending,
        artifacts,
        repository,
        result_commit=None,
        policy_sha256=policy_sha256,
    )

    assert bundle.operator_decision.state == "pending"
    assert len(bundle.criterion_receipts) == 1
    binding = bundle.criterion_receipts[0]
    assert binding.verification_kind == CriterionVerificationKind.HUMAN_GATE
    assert binding.verifier_id == "final-result"
    assert binding.status == "pending_final_decision"
    assert binding.receipt_references == ()
    assert verify_final_result_bundle(
        bundle,
        pending,
        artifacts,
        repository,
        expected_policy_sha256=policy_sha256,
    )

    unresolved = criterion.model_copy(update={"verifier_id": "security-review"})
    unresolved_plan = plan.model_copy(update={"criteria": (unresolved,)})
    unresolved_values = {
        **values,
        "plan": unresolved_plan.model_dump(mode="json"),
    }
    unresolved_snapshot = MissionSnapshot.model_validate(
        {
            **unresolved_values,
            "snapshot_sha256": canonical_json_sha256(unresolved_values),
        }
    )
    with pytest.raises(FinalResultBundleError, match="human-gate receipt"):
        build_final_result_bundle(
            unresolved_snapshot,
            artifacts,
            repository,
            result_commit=None,
            policy_sha256=policy_sha256,
        )


@pytest.mark.parametrize(
    ("reference_field", "replacement"),
    (("candidate_reference", b"tampered patch"), ("verification_reference", None)),
)
def test_bundle_rejects_tampered_or_unresolved_artifacts(
    tmp_path, reference_field: str, replacement: bytes | None
) -> None:
    repository = tmp_path / "repository"
    base, result = _repository(repository, b"base one\n")
    snapshot, artifacts, policy_sha256 = _snapshot(repository, base, result)
    bundle = build_final_result_bundle(
        snapshot,
        artifacts,
        repository,
        result_commit=result,
        policy_sha256=policy_sha256,
    )

    reference = getattr(bundle, reference_field)
    key = (reference.kind, reference.id)
    if replacement is None:
        artifacts.values.pop(key)
    else:
        artifacts.values[key] = replacement
    with pytest.raises(FinalResultBundleError, match="unresolved or changed"):
        build_final_result_bundle(
            snapshot,
            artifacts,
            repository,
            result_commit=result,
            policy_sha256=policy_sha256,
        )
    assert not verify_final_result_bundle(
        bundle,
        snapshot,
        artifacts,
        repository,
        expected_policy_sha256=policy_sha256,
    )


def test_same_patch_on_different_base_has_different_bundle_identity(tmp_path) -> None:
    first_repository = tmp_path / "first"
    second_repository = tmp_path / "second"
    first_base, first_result = _repository(first_repository, b"base one\n")
    second_base, second_result = _repository(second_repository, b"base two\n")
    first_snapshot, first_artifacts, first_policy = _snapshot(
        first_repository, first_base, first_result
    )
    second_snapshot, second_artifacts, second_policy = _snapshot(
        second_repository, second_base, second_result
    )
    first = build_final_result_bundle(
        first_snapshot,
        first_artifacts,
        first_repository,
        result_commit=first_result,
        policy_sha256=first_policy,
    )
    second = build_final_result_bundle(
        second_snapshot,
        second_artifacts,
        second_repository,
        result_commit=second_result,
        policy_sha256=second_policy,
    )

    assert first.candidate_reference.sha256 == second.candidate_reference.sha256
    assert first.base_commit != second.base_commit
    assert first.candidate_tree_sha256 != second.candidate_tree_sha256
    assert first.bundle_sha256 != second.bundle_sha256
