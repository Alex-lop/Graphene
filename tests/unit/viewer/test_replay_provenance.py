from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import SQLiteCheckpointRecorder
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import VerifiedHead
from graphene.viewer.contract import GraphSnapshot
from graphene.viewer.replay import (
    REPLAY_TRUTH_LABEL,
    ReplayEvidenceInvalid,
    apply_replay_envelope,
    create_verified_replay_app,
    load_verified_replay,
)
from scripts.generate_viewer_replay import (
    DEFAULT_SOURCE,
    flat_transcript,
    materialize,
    render,
)


TOKEN = "ephemeral-replay-token"


def test_replay_exactly_regenerates_from_checked_in_verified_v2_events(tmp_path: Path):
    database = tmp_path / "lineage.sqlite3"
    fixture, events = materialize(DEFAULT_SOURCE, database)
    artifacts = SQLiteArtifactStore(database, read_only=True)
    checkpoints = SQLiteCheckpointRecorder(database, read_only=True)
    store = SQLiteLineageStore(
        database,
        artifact_resolver=artifacts.resolve,
        checkpoint_reader=checkpoints.read,
        read_only=True,
    )

    assert all(
        isinstance(store.verify(run["run_id"]), VerifiedHead)
        for run in fixture["runs"].values()
    )
    fixture_events = [
        event for run in fixture["runs"].values() for event in run["events"]
    ]
    assert all(event["truth_kind"] != "human_attested" for event in fixture_events)
    assert all(event["event_type"] != "model.dispatched" for event in fixture_events)
    opened = [
        event
        for event in events.values()
        if event.payload.get("operation") == "open_evidence"
    ]
    assert [event.event_type.value for event in opened] == [
        "tool.started",
        "tool.completed",
    ]
    assert len({event.tool_call_id for event in opened}) == 1
    assert opened[-1].references[0].kind.value == "context_brief"
    assert len(checkpoints.read(fixture["runs"]["consumer"]["run_id"])) == 1
    generated = render()
    assert Path("backend/graphene/viewer/static/replay.json").read_bytes() == generated

    source_bytes = DEFAULT_SOURCE.read_bytes().lower()
    assert not any(
        forbidden in source_bytes
        for forbidden in (
            b'"content"',
            b'"diff"',
            b'"prompt"',
            b'"stdout"',
            b"/private/",
        )
    )
    replay = json.loads(generated)
    assert generated == canonical_json_bytes(replay) + b"\n"
    stages = [replay["snapshot"]]
    snapshot = GraphSnapshot.model_validate(stages[0])
    for envelope in replay["deltas"]:
        assert envelope["type"] == "delta"
        assert "snapshot" not in envelope
        assert envelope["deltas"]
        snapshot = apply_replay_envelope(snapshot, envelope)
        stages.append(snapshot.model_dump(mode="json"))
    truth = [node["truth_kind"] for stage in stages for node in stage["nodes"]]
    assert "simulated_fixture" in truth
    assert "human_attested" not in truth
    transcript = flat_transcript(generated)
    assert transcript.startswith(REPLAY_TRUTH_LABEL + "\n")
    assert transcript.count("\nCHECKPOINT ") == len(stages)
    assert transcript.count("\nITEM ") == len(snapshot.nodes)
    assert transcript.count("\nRELATIONSHIP ") == len(snapshot.edges)
    assert transcript.count("\nFACT ") == sum(
        len(section.facts) for section in snapshot.review_brief.sections
    )
    assert len(transcript.encode()) < len(generated)
    assert '"pending_count":1' in transcript
    assert '"pending_count":0' in transcript
    assert "SUPPORT_PATH " in transcript
    assert "/private/" not in transcript.lower()


def test_replay_server_is_authenticated_disposable_and_exactly_labeled():
    replay = load_verified_replay()
    before = Path("backend/graphene/viewer/static/replay.json").read_bytes()
    app = create_verified_replay_app(TOKEN, replay, stream_interval_seconds=0)
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with TestClient(app) as client:
        assert client.get("/api/viewer/health").status_code == 401
        health = client.get("/api/viewer/health", headers=headers)
        assert health.json() == {
            "status": "ok",
            "mode": REPLAY_TRUTH_LABEL,
            "read_only": True,
            "authoritative_writes": False,
            "human_attestation": False,
            "live_agent": False,
            "new_test_execution": False,
            "root_run_id": replay.root_run_id,
        }
        snapshot = client.get(
            f"/api/viewer/runs/{replay.root_run_id}/snapshot", headers=headers
        )
        assert snapshot.json() == replay.snapshot.model_dump(mode="json")
        node_id = replay.stages[-1].nodes[-1].id
        assert (
            client.get(
                f"/api/viewer/runs/{replay.root_run_id}/nodes/{node_id}",
                headers=headers,
            ).status_code
            == 200
        )
        invalid = client.get(
            f"/api/viewer/runs/{replay.root_run_id}/stream?cursor=invalid",
            headers=headers,
        )
        assert invalid.status_code == 409
        assert invalid.json()["code"] == "EVIDENCE_INVALID"
        page = client.get(f"/viewer/{replay.root_run_id}")
        assert "verified-replay" in page.text
        assert TOKEN in page.text
        assert f'<dd id="mode">{REPLAY_TRUTH_LABEL}</dd>' in page.text
        assert f'<dd id="truth-label">{REPLAY_TRUTH_LABEL}</dd>' in page.text
        for method in ("post", "put", "patch", "delete"):
            assert (
                getattr(client, method)(
                    f"/api/viewer/runs/{replay.root_run_id}/snapshot", headers=headers
                ).status_code
                == 405
            )

    assert Path("backend/graphene/viewer/static/replay.json").read_bytes() == before


def test_replay_digest_or_truth_tampering_fails_closed(tmp_path: Path):
    replay_path = tmp_path / "replay.json"
    replay_path.write_bytes(
        Path("backend/graphene/viewer/static/replay.json").read_bytes()
    )
    replay_path.with_suffix(".sha256").write_text("0" * 64 + "\n")
    with pytest.raises(ReplayEvidenceInvalid):
        load_verified_replay(replay_path)

    payload = json.loads(render())
    payload["deltas"][-1]["graph_sha256"] = "0" * 64
    tampered = canonical_json_bytes(payload) + b"\n"
    replay_path.write_bytes(tampered)
    replay_path.with_suffix(".sha256").write_text(sha256_hex(tampered) + "\n")
    with pytest.raises(ReplayEvidenceInvalid):
        load_verified_replay(replay_path)
