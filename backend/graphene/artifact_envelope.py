"""Canonical, domain-separated artifact envelope V2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .hashing import TREE_HASH_VERSION, canonical_json_bytes, sha256_hex
from .models import FrozenModel, GitSha, Identifier, Sha256


ARTIFACT_ENVELOPE_DOMAIN = "graphene.artifact.v2"
MediaType = Annotated[
    str,
    Field(
        min_length=3,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$",
    ),
]


class ArtifactEnvelopeError(ValueError):
    pass


class DirectArtifactInputV2(FrozenModel):
    publication_id: Identifier
    producer_task_id: Identifier
    output_name: Identifier
    artifact_envelope_sha256: Sha256


def _envelope_digest(values: Mapping[str, Any]) -> str:
    return sha256_hex(
        ARTIFACT_ENVELOPE_DOMAIN.encode("ascii")
        + b"\0"
        + canonical_json_bytes(values)
    )


class ArtifactEnvelopeV2(FrozenModel):
    schema_version: Literal[2]
    domain: Literal["graphene.artifact.v2"]
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    plan_sha256: Sha256
    task_id: Identifier
    attempt_id: Identifier
    fencing_token: int = Field(ge=1)
    policy_sha256: Sha256
    base_git_commit: GitSha
    direct_inputs: tuple[DirectArtifactInputV2, ...]
    output_name: Identifier
    artifact_kind: Identifier
    media_type: MediaType
    byte_count: int = Field(ge=0)
    content_sha256: Sha256
    mutation_manifest_sha256: Sha256 | None = None
    tree_hash_version: Literal["graphene.tree.v2"] | None = None
    tree_sha256: Sha256 | None = None
    created_by: Literal["trusted-worker-wrapper"]
    artifact_envelope_sha256: Sha256

    @model_validator(mode="after")
    def bindings_are_canonical(self) -> ArtifactEnvelopeV2:
        input_keys = tuple(
            (
                item.producer_task_id,
                item.output_name,
                item.publication_id,
                item.artifact_envelope_sha256,
            )
            for item in self.direct_inputs
        )
        if input_keys != tuple(sorted(set(input_keys))):
            raise ValueError("direct inputs must be canonically ordered and unique")
        if (self.tree_hash_version is None) != (self.tree_sha256 is None):
            raise ValueError("tree hash version and digest must appear together")
        expected = _envelope_digest(
            self.model_dump(
                mode="json",
                exclude={"artifact_envelope_sha256"},
                exclude_none=True,
            )
        )
        if self.artifact_envelope_sha256 != expected:
            raise ValueError("envelope digest does not match canonical bindings")
        return self

    @classmethod
    def create(cls, artifact_bytes: bytes, **bindings: Any) -> ArtifactEnvelopeV2:
        if type(artifact_bytes) is not bytes:
            raise TypeError("artifact bytes must be bytes")
        computed = {"content_sha256", "byte_count", "artifact_envelope_sha256"}
        if computed & bindings.keys():
            raise ArtifactEnvelopeError("computed envelope fields cannot be supplied")
        values = {
            "schema_version": 2,
            "domain": ARTIFACT_ENVELOPE_DOMAIN,
            **bindings,
            "content_sha256": sha256_hex(artifact_bytes),
            "byte_count": len(artifact_bytes),
        }
        canonical = {key: value for key, value in values.items() if value is not None}
        canonical["direct_inputs"] = [
            DirectArtifactInputV2.model_validate(item).model_dump(mode="json")
            for item in values.get("direct_inputs", ())
        ]
        return cls.model_validate(
            {
                **values,
                "artifact_envelope_sha256": _envelope_digest(canonical),
            }
        )


def verify_artifact_envelope(
    envelope: ArtifactEnvelopeV2 | Mapping[str, Any],
    artifact_bytes: bytes,
    *,
    expected: Mapping[str, Any] | None = None,
    require_mutation_manifest: bool = False,
    require_tree_binding: bool = False,
) -> ArtifactEnvelopeV2:
    if type(artifact_bytes) is not bytes:
        raise TypeError("artifact bytes must be bytes")
    verified = (
        envelope
        if type(envelope) is ArtifactEnvelopeV2
        else ArtifactEnvelopeV2.model_validate(envelope)
    )
    if (
        verified.byte_count != len(artifact_bytes)
        or verified.content_sha256 != sha256_hex(artifact_bytes)
    ):
        raise ArtifactEnvelopeError("artifact bytes do not match the envelope")
    if require_mutation_manifest and verified.mutation_manifest_sha256 is None:
        raise ArtifactEnvelopeError("this artifact requires a mutation manifest")
    if require_tree_binding and verified.tree_hash_version is None:
        raise ArtifactEnvelopeError("this artifact requires a V2 tree binding")
    if expected:
        comparable = set(ArtifactEnvelopeV2.model_fields) - {
            "content_sha256",
            "byte_count",
            "artifact_envelope_sha256",
        }
        unknown = set(expected) - comparable
        if unknown:
            raise ArtifactEnvelopeError(f"unknown expected bindings: {sorted(unknown)}")
        mismatched = [
            name for name, value in expected.items() if getattr(verified, name) != value
        ]
        if mismatched:
            raise ArtifactEnvelopeError(f"envelope binding mismatch: {sorted(mismatched)}")
    return verified


__all__ = (
    "ARTIFACT_ENVELOPE_DOMAIN",
    "TREE_HASH_VERSION",
    "ArtifactEnvelopeError",
    "ArtifactEnvelopeV2",
    "DirectArtifactInputV2",
    "verify_artifact_envelope",
)
