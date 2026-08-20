import pytest

from graphene.artifact_envelope import (
    ArtifactEnvelopeError,
    ArtifactEnvelopeV2,
    verify_artifact_envelope,
)


BYTES = b"binary\0artifact\xff"
INPUTS = (
    {
        "publication_id": "publication_a",
        "producer_task_id": "task_a",
        "output_name": "delta_a",
        "artifact_envelope_sha256": "1" * 64,
    },
    {
        "publication_id": "publication_b",
        "producer_task_id": "task_b",
        "output_name": "delta_b",
        "artifact_envelope_sha256": "2" * 64,
    },
)
BINDINGS = {
    "mission_id": "mission_1",
    "plan_revision": 3,
    "plan_sha256": "3" * 64,
    "task_id": "assemble",
    "attempt_id": "attempt_1",
    "fencing_token": 7,
    "policy_sha256": "4" * 64,
    "base_git_commit": "a" * 40,
    "direct_inputs": INPUTS,
    "output_name": "candidate",
    "artifact_kind": "git_delta",
    "media_type": "application/vnd.graphene.git-patch",
    "mutation_manifest_sha256": "5" * 64,
    "tree_hash_version": "graphene.tree.v2",
    "tree_sha256": "6" * 64,
    "created_by": "trusted-worker-wrapper",
}


def test_artifact_envelope_v2_is_complete_ordered_content_bound_and_strict():
    envelope = ArtifactEnvelopeV2.create(BYTES, **BINDINGS)
    raw = envelope.model_dump(mode="json")
    assert envelope.artifact_envelope_sha256 == (
        "66d7b1570e15480d82dea6dee5d37a7c3afb512ee21de7ca46af087d5aceea14"
    )

    assert verify_artifact_envelope(
        raw,
        BYTES,
        require_mutation_manifest=True,
        require_tree_binding=True,
        expected={
            "mission_id": "mission_1",
            "plan_revision": 3,
            "plan_sha256": "3" * 64,
            "task_id": "assemble",
            "attempt_id": "attempt_1",
            "fencing_token": 7,
            "policy_sha256": "4" * 64,
            "base_git_commit": "a" * 40,
            "direct_inputs": envelope.direct_inputs,
            "output_name": "candidate",
            "artifact_kind": "git_delta",
            "media_type": "application/vnd.graphene.git-patch",
            "created_by": "trusted-worker-wrapper",
        },
    ) == envelope

    with pytest.raises(ArtifactEnvelopeError, match="bytes"):
        verify_artifact_envelope(raw, BYTES + b"tampered")
    with pytest.raises(ValueError, match="canonical bindings"):
        verify_artifact_envelope({**raw, "task_id": "task_2"}, BYTES)
    with pytest.raises(ValueError):
        verify_artifact_envelope({**raw, "unknown": True}, BYTES)

    for field, value in (
        ("schema_version", 1),
        ("domain", "graphene.artifact.v1"),
        ("tree_hash_version", "graphene.tree.v1"),
        ("created_by", "untrusted-worker"),
    ):
        with pytest.raises(ValueError):
            verify_artifact_envelope({**raw, field: value}, BYTES)

    for required in (
        "schema_version",
        "domain",
        "mission_id",
        "plan_revision",
        "plan_sha256",
        "task_id",
        "attempt_id",
        "fencing_token",
        "policy_sha256",
        "base_git_commit",
        "direct_inputs",
        "output_name",
        "artifact_kind",
        "media_type",
        "byte_count",
        "content_sha256",
        "created_by",
        "artifact_envelope_sha256",
    ):
        missing = dict(raw)
        missing.pop(required)
        with pytest.raises(ValueError):
            verify_artifact_envelope(missing, BYTES)

    with pytest.raises(ValueError, match="ordered"):
        ArtifactEnvelopeV2.create(
            BYTES, **{**BINDINGS, "direct_inputs": tuple(reversed(INPUTS))}
        )

    half_tree = dict(raw)
    half_tree.pop("tree_sha256")
    with pytest.raises(ValueError, match="appear together"):
        verify_artifact_envelope(half_tree, BYTES)

    optional = ArtifactEnvelopeV2.create(
        BYTES,
        **{
            key: value
            for key, value in BINDINGS.items()
            if key
            not in {
                "mutation_manifest_sha256",
                "tree_hash_version",
                "tree_sha256",
            }
        },
    )
    with pytest.raises(ArtifactEnvelopeError, match="mutation manifest"):
        verify_artifact_envelope(
            optional,
            BYTES,
            require_mutation_manifest=True,
        )
    with pytest.raises(ArtifactEnvelopeError, match="requires a V2 tree"):
        verify_artifact_envelope(optional, BYTES, require_tree_binding=True)

    substituted = ArtifactEnvelopeV2.create(
        BYTES, **{**BINDINGS, "fencing_token": 8}
    )
    with pytest.raises(ArtifactEnvelopeError, match="fencing_token"):
        verify_artifact_envelope(
            substituted,
            BYTES,
            expected={"fencing_token": 7},
        )
