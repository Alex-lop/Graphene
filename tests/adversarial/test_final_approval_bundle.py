from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.final_bundle import (
    CriterionReceiptBinding,
    FinalBundleVerificationReceiptV1,
    FinalResultBundleV2,
    MutationEntry,
    MutationManifest,
    OperatorDecisionState,
)
from graphene.orchestration.local_result import _recompute_final_bundle
from graphene.orchestration.models import (
    AttemptResult,
    GenericEvidenceLink,
    MissionStatus,
    PublicationDraft,
    TaskKind,
)
from graphene.orchestration.mission_control import create_mission_control_app
from graphene.orchestration.projection import MissionProjection
from graphene.orchestration.store import MissionConflict, SQLiteMissionStore
from tests.unit.orchestration.test_store import (
    NOW,
    _artifacts,
    _command,
    _complete_ready,
    _create,
    _register_worker,
)


def _complete_trusted_verification(store: SQLiteMissionStore) -> None:
    at = NOW + timedelta(seconds=4)
    store.refresh_ready("mission-1", _command("ready-trusted"), recorded_at=at)
    task = store.ready_tasks("mission-1")[0]
    _register_worker(store, "worker-trusted", capabilities=(task.kind,), at=at)
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-trusted",
        _command("claim-trusted"),
        recorded_at=at,
        ttl_seconds=30,
    )
    artifacts = store.artifact_resolver
    assert artifacts is not None
    policy_sha256, base_sha = artifacts.authority["mission-1"]
    receipt = TrustedCheckReceipt(
        schema_version=2,
        mission_id="mission-1",
        task_id=task.task_id,
        attempt_id=dispatch.attempt_id,
        plan_revision=dispatch.plan_revision,
        fencing_token=dispatch.fencing_token,
        policy_sha256=policy_sha256,
        base_sha=base_sha,
        runner_id="graphene_check_runner_v1",
        template_id=task.acceptance_checks[0],
        template_sha256="b" * 64,
        accepted_input_references=dispatch.input_publications,
        candidate_references=dispatch.input_publications,
        candidate_tree_hash_version="graphene.tree.v2",
        candidate_tree_sha256="c" * 64,
        result_code="passed",
        exit_code=0,
        timed_out=False,
        output_sha256=sha256_hex(b"check output"),
        output_truncated=False,
        cleanup_complete=True,
    )
    content = canonical_json_bytes(receipt.model_dump(mode="json"))
    reference, envelope = artifacts.put_enveloped(
        dispatch,
        output_name=task.expected_outputs[0].name,
        kind="test-receipt",
        content=content,
    )
    evidence_id = f"evidence-{dispatch.attempt_id}"
    artifacts.record_completed(
        evidence_id,
        mission_id="mission-1",
        task_id=task.task_id,
        attempt_id=dispatch.attempt_id,
        references=(reference,),
    )
    store.complete_attempt(
        "mission-1",
        dispatch.attempt_id,
        dispatch.worker_id,
        dispatch.lease_id,
        dispatch.fencing_token,
        AttemptResult(
            succeeded=True,
            result_code="passed",
            evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
            evidence_refs=(reference,),
            artifact_envelopes=(envelope,),
            publications=(
                PublicationDraft(
                    output_name=task.expected_outputs[0].name,
                    kind="test-receipt",
                    sha256=reference.sha256,
                    artifact=envelope,
                    paths=task.expected_outputs[0].paths,
                ),
            ),
        ),
        _command("complete-trusted"),
        recorded_at=at + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )


def _pending_bundle(store: SQLiteMissionStore) -> FinalResultBundleV2:
    artifacts = store.artifact_resolver
    assert artifacts is not None
    snapshot = store.snapshot("mission-1")
    candidate = next(
        item
        for item in snapshot.publications
        if next(task for task in snapshot.tasks if task.task_id == item.task_id).kind
        == TaskKind.ASSEMBLY
    )
    verification = next(
        item
        for item in snapshot.publications
        if next(task for task in snapshot.tasks if task.task_id == item.task_id).kind
        == TaskKind.VERIFICATION
    )
    candidate_reference = candidate.published_reference()
    verification_reference = verification.published_reference()
    receipt_bytes = artifacts.resolve_enveloped(verification_reference)
    assert receipt_bytes is not None
    receipt = TrustedCheckReceipt.model_validate_json(receipt_bytes)
    manifest = MutationManifest.create(
        base_commit=snapshot.mission.base_sha,
        result_commit=None,
        result_tree_id="d" * 40,
        changes=(
            MutationEntry(
                status="A",
                path="app/reviewed.py",
                new_mode="100644",
                new_content_sha256="e" * 64,
            ),
        ),
    )
    return FinalResultBundleV2.create(
        mission_id="mission-1",
        snapshot_sha256=snapshot.snapshot_sha256,
        event_head_seq=snapshot.head.seq,
        event_head_sha256=snapshot.head.event_sha256,
        plan_revision=snapshot.plan.revision,
        plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
        policy_id=snapshot.policy.policy_id,
        policy_revision=snapshot.policy.revision,
        policy_sha256=snapshot.policy.policy_sha256,
        base_commit=snapshot.mission.base_sha,
        candidate_publication=candidate,
        candidate_reference=candidate_reference,
        candidate_byte_count=candidate_reference.byte_count,
        verification_publication=verification,
        verification_reference=verification_reference,
        verification_receipt=receipt,
        result_commit=None,
        result_tree_id=manifest.result_tree_id,
        candidate_tree_hash_version=receipt.candidate_tree_hash_version,
        candidate_tree_sha256=receipt.candidate_tree_sha256,
        mutation_manifest=manifest,
        changed_paths=("app/reviewed.py",),
        criterion_receipts=(
            CriterionReceiptBinding(
                criterion_id=snapshot.plan.criteria[0].criterion_id,
                producer_task_ids=snapshot.plan.criteria[0].producer_task_ids,
                verification_kind=snapshot.plan.criteria[0].verification_kind,
                verifier_task_id=snapshot.plan.criteria[0].verifier_task_id,
                verifier_id=snapshot.plan.criteria[0].verifier_id,
                receipt_references=(verification_reference,),
            ),
        ),
        unresolved_unknowns=snapshot.unknowns,
        operator_decision=OperatorDecisionState(
            state="pending",
            mission_status=MissionStatus.AWAITING_RESULT,
        ),
    )


def test_decision_requires_exact_current_immutable_bundle(tmp_path, monkeypatch) -> None:
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
    _complete_trusted_verification(store)
    store.enter_awaiting_result(
        "mission-1", _command("await-bundle"), recorded_at=NOW + timedelta(seconds=6)
    )
    bundle = _pending_bundle(store)
    reference = _artifacts(store).put(
        "final-result-bundle", canonical_json_bytes(bundle.model_dump(mode="json"))
    )
    # This test pins bundle *identity*; the recompute itself is enforced by
    # test_store_refuses_a_bundle_it_cannot_recompute below.
    store.bind_final_bundle_verifier(lambda _raw, _snapshot: True)
    ready = store.register_final_result_bundle(
        "mission-1",
        reference,
        _command("register-bundle"),
        expected_head=store.head("mission-1"),
        recorded_at=NOW + timedelta(seconds=7),
    )
    projected = MissionProjection(store).snapshot("mission-1")
    assert projected.result.bundle_id == bundle.bundle_id
    assert projected.needs_you is not None
    assert projected.needs_you.gate_id == bundle.bundle_id
    assert bundle.bundle_id in projected.needs_you.options[0].consequence

    submitted: dict[str, object] = {}

    def finalizer(**values):
        submitted.update(values)
        return ready, object()

    monkeypatch.setattr(
        "graphene.orchestration.mission_control.finalize_local_result_decision",
        finalizer,
    )
    app = create_mission_control_app(
        MissionProjection(store),
        "mission-1",
        "read-token-00000000000000000001",
        "TEST",
        command_token="command-token-00000000000000001",
        command_origin="http://127.0.0.1:43123",
        operator_label="reviewer",
    )
    endpoint = "/api/mission-control/missions/mission-1/commands"
    auth = {
        "Authorization": "Bearer command-token-00000000000000001",
        "Origin": "http://127.0.0.1:43123",
    }
    body = {
        "action": "approve_final",
        "command_id": "browser_exact_bundle_001",
        "expected_head": {
            "mission_id": ready.mission_id,
            "seq": ready.seq,
            "event_sha256": ready.event_sha256,
        },
        "target_id": "result:mission-1",
        "expected_bundle_id": bundle.bundle_id,
        "confirmation": f"approve_final:result:mission-1:{bundle.bundle_id}",
        "rationale": "Reviewed the displayed immutable bundle.",
    }
    with TestClient(app) as client:
        session = client.post(f"{endpoint}/session", headers=auth)
        headers = {**auth, "X-CSRF-Token": session.json()["csrf_token"]}
        assert client.post(endpoint, headers=headers, json=body).status_code == 200
        assert (
            client.post(
                endpoint,
                headers=headers,
                json={
                    **body,
                    "command_id": "browser_candidate_fallback_001",
                    "expected_candidate_sha256": bundle.candidate_reference.content_sha256,
                },
            ).status_code
            == 422
        )
    assert submitted["expected_bundle_id"] == bundle.bundle_id

    with pytest.raises(MissionConflict, match="not current"):
        store.approve_final_result(
            "mission-1",
            _command("wrong-bundle"),
            expected_head=ready,
            expected_bundle_id="final_result_" + "f" * 32,
            operator_label="reviewer",
            rationale="Reviewed the displayed bundle.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=8),
        )
    store.approve_final_result(
        "mission-1",
        _command("exact-bundle"),
        expected_head=ready,
        expected_bundle_id=bundle.bundle_id,
        operator_label="reviewer",
        rationale="Reviewed the displayed bundle.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=8),
    )
    cold = SQLiteMissionStore(path, artifact_resolver=_artifacts(store))
    assert cold.verify("mission-1") == cold.head("mission-1")
    decision = cold.tail("mission-1", ready.seq, 1)[0]
    assert decision.payload["bundle_id"] == bundle.bundle_id
    assert decision.payload["decision_receipt"]["bundle_sha256"] == bundle.bundle_sha256


def _awaiting_store(path) -> tuple[SQLiteMissionStore, FinalResultBundleV2]:
    store = SQLiteMissionStore(path)
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
    _complete_trusted_verification(store)
    store.enter_awaiting_result(
        "mission-1", _command("await-bundle"), recorded_at=NOW + timedelta(seconds=6)
    )
    return store, _pending_bundle(store)


def test_store_refuses_a_bundle_it_cannot_recompute(tmp_path) -> None:
    """The invented path/tree bundle above used to register and approve cleanly.

    ``_pending_bundle`` fabricates ``result_tree_id = "d" * 40`` and a mutation
    entry for ``app/reviewed.py`` that no repository ever produced. Registration
    is now the enforcement point: with no verifier bound it fails closed, and a
    recompute that says no is final. Caller discipline is gone — the store asks.
    """
    store, bundle = _awaiting_store(tmp_path / "missions.sqlite")
    reference = _artifacts(store).put(
        "final-result-bundle", canonical_json_bytes(bundle.model_dump(mode="json"))
    )

    assert store.final_bundle_verifier is None
    with pytest.raises(MissionConflict, match="verifier is not bound"):
        store.register_final_result_bundle(
            "mission-1",
            reference,
            _command("register-unbound"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=7),
        )

    # The production recompute is fail-closed on an unusable repository, and this
    # adversarial fixture has none — so the real helper, not a stand-in, says no.
    raw = canonical_json_bytes(bundle.model_dump(mode="json"))
    assert not _recompute_final_bundle(
        raw,
        store.snapshot("mission-1"),
        evidence=_artifacts(store),
        repository=tmp_path / "no-such-repository",
    )

    store.bind_final_bundle_verifier(lambda _raw, _snapshot: False)
    with pytest.raises(MissionConflict, match="does not recompute"):
        store.register_final_result_bundle(
            "mission-1",
            reference,
            _command("register-rejected"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=7),
        )

    # Nothing was written: no bundle is registered, so nothing can be approved.
    with pytest.raises(MissionConflict, match="not current"):
        store.approve_final_result(
            "mission-1",
            _command("approve-nothing"),
            expected_head=store.head("mission-1"),
            expected_bundle_id=bundle.bundle_id,
            operator_label="reviewer",
            rationale="Approved without a registration.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=8),
        )


def test_approval_requires_a_server_issued_receipt_for_this_exact_bundle(
    tmp_path,
) -> None:
    """The READY event carries the store's own verification receipt, and it binds."""
    store, bundle = _awaiting_store(tmp_path / "missions.sqlite")
    reference = _artifacts(store).put(
        "final-result-bundle", canonical_json_bytes(bundle.model_dump(mode="json"))
    )
    store.bind_final_bundle_verifier(lambda _raw, _snapshot: True)
    ready = store.register_final_result_bundle(
        "mission-1",
        reference,
        _command("register-verified"),
        expected_head=store.head("mission-1"),
        recorded_at=NOW + timedelta(seconds=7),
    )

    event = store.tail("mission-1", ready.seq - 1, 1)[0]
    receipt = FinalBundleVerificationReceiptV1.model_validate(
        event.payload["verification_receipt"]
    )
    assert receipt.binds(bundle)
    assert receipt.receipt_id.startswith("bundle_verified_")
    assert receipt.verifier == "verify_final_result_bundle"

    # A receipt issued for any other bundle does not bind this one, which is what
    # _final_decision and the cold audit check before a decision is committed.
    other = bundle.model_copy(update={"bundle_sha256": "a" * 64})
    assert not FinalBundleVerificationReceiptV1.issue(
        other, verified_at=NOW
    ).binds(bundle)

    store.approve_final_result(
        "mission-1",
        _command("approve-verified"),
        expected_head=ready,
        expected_bundle_id=bundle.bundle_id,
        operator_label="reviewer",
        rationale="Reviewed the displayed bundle.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=8),
    )
    cold = SQLiteMissionStore(
        tmp_path / "missions.sqlite", artifact_resolver=_artifacts(store)
    )
    assert cold.verify("mission-1") == cold.head("mission-1")
