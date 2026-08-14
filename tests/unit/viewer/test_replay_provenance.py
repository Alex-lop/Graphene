from __future__ import annotations

import json
from pathlib import Path

from graphene.hashing import canonical_json_bytes
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import SQLiteCheckpointRecorder
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import VerifiedHead
from scripts.generate_viewer_replay import DEFAULT_SOURCE, materialize, render


def test_replay_exactly_regenerates_from_checked_in_verified_v2_events(tmp_path: Path):
    database = tmp_path / "lineage.sqlite3"
    fixture, _events = materialize(DEFAULT_SOURCE, database)
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
    assert len(checkpoints.read(fixture["runs"]["consumer"]["run_id"])) == 1
    generated = render()
    assert Path("backend/graphene/viewer/static/replay.json").read_bytes() == generated

    source_bytes = DEFAULT_SOURCE.read_bytes().lower()
    assert not any(
        forbidden in source_bytes
        for forbidden in (b'"content"', b'"diff"', b'"prompt"', b'"stdout"', b"/private/")
    )
    replay = json.loads(generated)
    assert generated == canonical_json_bytes(replay) + b"\n"
    truth = [
        node["truth_kind"]
        for stage in [replay["snapshot"], *(item["snapshot"] for item in replay["deltas"])]
        for node in stage["nodes"]
    ]
    assert "simulated_fixture" in truth
    assert "human_attested" not in truth
