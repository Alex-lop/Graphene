from datetime import timedelta

from graphene.hashing import canonical_json_bytes
from graphene.core_models import TruthKind
from graphene.orchestration.causal_query import why
from graphene.orchestration.mission_models import (
    PLAN_AWAITING_REVIEW_UNKNOWN,
    MissionEventType,
)
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore

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
    # Registration recomputes the bundle against a real repository; these
    # fixtures have none, so they stand in for a recompute that said yes.
    store.bind_final_bundle_verifier(lambda _raw, _snapshot: True)
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
        "prior_attempts",
        "accepted_inputs",
        "assembly_candidate",
        "verification",
        "approval",
    ]
    assert [link.status for link in result.links] == [
        "established",
        "established",
        "not_present",
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
    inputs = next(link for link in assembly.links if link.stage == "accepted_inputs")
    assert inputs.status == "established"
    assert len(inputs.nodes) == 2

    missing = why(
        snapshot,
        events,
        "publication-does-not-exist",
        reference_exists=lambda _reference: None,
    )
    assert missing.matched_by == "none"
    assert all(link.status == "unknown" for link in missing.links)
    assert "No committed publication or artifact matches" in " ".join(missing.unknowns)


def test_plan_review_unknown_clears_once_the_plan_is_approved(tmp_path) -> None:
    """A caveat that stopped being true must stop being printed.

    A Gemini-planned mission is created carrying "the model-proposed plan awaits
    operator review". It did — and then the operator approved it, and `why` went
    on printing the caveat on every later answer, including on completed live
    missions. The unknown is now dropped exactly when a PLAN_APPROVED event is in
    the validated chain, and only then.
    """
    store = SQLiteMissionStore(tmp_path / "unknown.sqlite")
    _create(store, approve=False)
    mission = store.snapshot("mission-1").mission
    assert PLAN_AWAITING_REVIEW_UNKNOWN not in mission.unknowns, (
        "the fixture mission carries no unknowns, so this test drives the "
        "predicate directly below"
    )

    approved = [
        event
        for event in store.tail("mission-1", 0, store.head("mission-1").seq)
        if event.event_type == MissionEventType.PLAN_APPROVED
    ]
    assert not approved

    store.approve_plan(
        "mission-1",
        _command("approve-plan-unknown"),
        expected_revision=1,
        expected_head=store.head("mission-1"),
        operator_label="reviewer",
        rationale="Reviewed the proposed plan.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    snapshot = store.snapshot("mission-1")
    events = store.tail("mission-1", 0, snapshot.head.seq)
    carrying = snapshot.model_copy(
        update={"unknowns": (PLAN_AWAITING_REVIEW_UNKNOWN, "Something else is unknown.")}
    )

    result = why(carrying, events, "app/nothing.py", reference_exists=lambda *_: True)

    assert PLAN_AWAITING_REVIEW_UNKNOWN not in result.unknowns
    assert "Something else is unknown." in result.unknowns
