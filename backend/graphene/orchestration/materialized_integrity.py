from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..hashing import sha256_hex
from .mission_models import Attempt, Gate


class ArtifactResolver(Protocol):
    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...


class MaterializedArtifactError(ValueError):
    pass


def verify_materialized_artifacts(
    *,
    attempt_documents: Iterable[bytes],
    gate_documents: Iterable[bytes],
    resolver: ArtifactResolver | None,
    max_artifact_bytes: int,
) -> int:
    """Re-resolve every materialized artifact binding and return unique bytes."""

    references = {}
    try:
        for document in attempt_documents:
            for reference in Attempt.model_validate_json(document).evidence_refs:
                references[(reference.kind, reference.id, reference.sha256)] = reference
        for document in gate_documents:
            for reference in Gate.model_validate_json(document).evidence:
                references[(reference.kind, reference.id, reference.sha256)] = reference
    except (TypeError, ValueError) as error:
        raise MaterializedArtifactError(
            "materialized artifact bindings are invalid"
        ) from error
    if not references:
        return 0
    if resolver is None:
        raise MaterializedArtifactError(
            "materialized artifact resolver is unavailable"
        )
    # ponytail: bounded full scan; persist a resolver manifest root if mission
    # artifact budgets outgrow cold-read reconciliation.
    total = 0
    for reference in references.values():
        try:
            content = resolver.resolve(reference.kind, reference.id)
        except Exception as error:
            raise MaterializedArtifactError(
                "materialized artifact resolver failed"
            ) from error
        if not isinstance(content, bytes) or sha256_hex(content) != reference.sha256:
            raise MaterializedArtifactError(
                "materialized artifact bytes do not match their committed digest"
            )
        total += len(content)
    if total > max_artifact_bytes:
        raise MaterializedArtifactError(
            "materialized artifact bytes exceed the committed policy budget"
        )
    return total
