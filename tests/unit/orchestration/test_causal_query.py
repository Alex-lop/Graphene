from datetime import timedelta

from graphene.hashing import canonical_json_bytes
from graphene.models import TruthKind
from graphene.orchestration.causal_query import why
from graphene.orchestration.store import SQLiteMissionStore

from .test_store import NOW, _command, _complete_ready, _create


def test_why_reports_only_committed_causal_links_and_explicit_unknowns(tmp_path):
    from tests.adversarial.test_final_approval_bundle import (
        _complete_trusted_verification,
        _pending_bundle,
    )

    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
    _complete_trusted_verification(store)
    store.enter_awaiting_result(
        "mission-1", _command("await-causal"), recorded_at=NOW + timedelta(seconds=6)
    )
    bundle = _pending_bundle(store)
    artifacts = store.artifact_resolver
    assert artifacts is not None
    bundle_reference = artifacts.put(
        "final-result-bundle",
        canonical_json_bytes(bundle.model_dump(mode="json")),
    )
    store.register_final_result_bundle(
        "mission-1",
        bundle_reference,
        _command("bundle-causal"),
        expected_head=store.head("mission-1"),
        recorded_at=NOW + timedelta(seconds=7),
    )
    review = store.snapshot("mission-1")
    store.approve_final_result(
        "mission-1",
        _command("approve-causal"),
        expected_head=review.head,
        expected_bundle_id=bundle.bundle_id,
        operator_label="test-operator",
        rationale="Reviewed exact candidate.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=8),
    )
    snapshot = store.snapshot("mission-1")
    assert store.verify("mission-1") == snapshot.head
    events = store.tail("mission-1", 0, snapshot.head.seq)
    known = {
        (reference.kind, reference.id, reference.sha256)
        for attempt in snapshot.attempts
        for reference in (*attempt.input_publications, *attempt.evidence_refs)
    }

    result = why(
        snapshot,
        events,
        "app/a.py",
        reference_exists=lambda reference: (
            reference.kind,
            reference.id,
            reference.sha256,
        )
        in known,
    )

    assert result.matched_by == "path"
    assert [link.stage for link in result.links] == [
        "target",
        "producer_attempt",
        "accepted_inputs",
        "assembly_candidate",
        "verification",
        "approval",
    ]
    assert [link.status for link in result.links] == [
        "established",
        "established",
        "not_present",
        "established",
        "established",
        "established",
    ]
    serialized = result.model_dump_json()
    assert "Reviewed exact candidate" not in serialized
    assert "artifact_bytes" not in serialized

    target = result.links[0].nodes[0]
    assert why(
        snapshot,
        events,
        target.node_id,
        reference_exists=lambda _reference: True,
    ).matched_by == "identifier"
    producer = next(
        attempt for attempt in snapshot.attempts if attempt.attempt_id == target.attempt_id
    )
    artifact_id = next(
        reference.id
        for reference in producer.evidence_refs
        if reference.kind == target.kind and reference.sha256 == target.sha256
    )
    assert why(
        snapshot,
        events,
        artifact_id,
        reference_exists=lambda _reference: True,
    ).links[0].nodes == result.links[0].nodes

    assembly = why(
        snapshot,
        events,
        "out/candidate.patch",
        reference_exists=lambda _reference: True,
    )
    assert assembly.links[2].status == "established"
    assert len(assembly.links[2].nodes) == 2

    missing = why(
        snapshot,
        events,
        "publication-does-not-exist",
        reference_exists=lambda _reference: None,
    )
    assert missing.matched_by == "none"
    assert all(link.status == "unknown" for link in missing.links)
    assert "No committed publication or artifact matches" in " ".join(missing.unknowns)
