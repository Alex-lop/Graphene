from __future__ import annotations

import sqlite3

from graphene.artifact_envelope import ArtifactEnvelopeV2
from graphene.hashing import canonical_json_bytes
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore


CONTENT = b"exact candidate bytes\0\xff"


def _envelope(*, fencing_token: int = 3) -> ArtifactEnvelopeV2:
    return ArtifactEnvelopeV2.create(
        CONTENT,
        mission_id="mission_cas",
        plan_revision=2,
        plan_sha256="1" * 64,
        task_id="task_cas",
        attempt_id="attempt_cas",
        fencing_token=fencing_token,
        policy_sha256="2" * 64,
        base_git_commit="3" * 40,
        direct_inputs=(),
        output_name="candidate",
        artifact_kind="patch",
        media_type="application/vnd.graphene.git-patch",
        created_by="trusted-worker-wrapper",
    )


def test_cas_rejects_missing_swapped_stale_and_rewritten_envelope(tmp_path) -> None:
    path = tmp_path / "evidence.sqlite3"
    store = SQLiteAttemptEvidenceStore(path)
    envelope = _envelope()
    _, reference = store.put_artifact_envelope(envelope, CONTENT)

    assert store.resolve_enveloped(reference) == CONTENT
    assert store.verify_enveloped(reference, expected={"fencing_token": 3})
    assert not store.verify_enveloped(reference, expected={"fencing_token": 4})
    assert store.resolve_enveloped(
        reference.model_copy(update={"output_name": "swapped"})
    ) is None
    assert store.resolve_enveloped(
        reference.model_copy(update={"artifact_envelope_sha256": "f" * 64})
    ) is None

    # Simulate an attacker with direct database write access, bypassing the
    # immutability trigger. Cold resolution still verifies canonical V2 bytes.
    tampered = envelope.model_copy(update={"fencing_token": 99})
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER artifact_envelopes_v2_no_update")
        connection.execute(
            "UPDATE artifact_envelopes_v2 SET envelope_bytes = ? "
            "WHERE artifact_envelope_sha256 = ?",
            (
                canonical_json_bytes(tampered.model_dump(mode="json")),
                envelope.artifact_envelope_sha256,
            ),
        )
    assert store.resolve_enveloped(reference) is None
