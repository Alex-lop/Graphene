from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.orchestration.replay import (
    MISSION_REPLAY_TRUTH_LABEL,
    MissionReplayInvalid,
    load_verified_mission_replay,
)
from scripts.generate_mission_replay import render


def test_checked_in_mission_replay_exactly_regenerates_and_reconstructs():
    path = Path("backend/graphene/orchestration/static/mission-replay.json")
    generated = render()
    assert path.read_bytes() == generated
    assert path.with_suffix(".sha256").read_text().strip() == sha256_hex(generated)
    replay = load_verified_mission_replay()
    assert len(replay.stages) == 10
    assert replay.meta["mode"] == MISSION_REPLAY_TRUTH_LABEL
    assert replay.meta["live_agent"] is False
    assert replay.meta["human_attestation"] is False
    assert replay.meta["new_test_execution"] is False
    assert replay.meta["gemini_calls"] == 0
    assert replay.meta["cloud_proof"] is False
    assert replay.stages[-1].snapshot_sha256 == replay.meta["final_snapshot_sha256"]


def test_mission_replay_digest_truth_and_private_field_tampering_fail_closed(tmp_path: Path):
    source = Path("backend/graphene/orchestration/static/mission-replay.json")
    replay_path = tmp_path / "mission-replay.json"
    replay_path.write_bytes(source.read_bytes())
    replay_path.with_suffix(".sha256").write_text("0" * 64 + "\n")
    with pytest.raises(MissionReplayInvalid):
        load_verified_mission_replay(replay_path)

    payload = json.loads(source.read_bytes())
    payload["meta"]["prompt"] = "private"
    raw = canonical_json_bytes(payload) + b"\n"
    replay_path.write_bytes(raw)
    replay_path.with_suffix(".sha256").write_text(sha256_hex(raw) + "\n")
    with pytest.raises(MissionReplayInvalid):
        load_verified_mission_replay(replay_path)


@pytest.mark.parametrize(
    "leak",
    (
        "Bearer abcdefghijklmnopqrstuvwxyz012345",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "api_key=abcdefghijklmnopqrstuvwxyz012345",
        "/Users/alex/.ssh/id_rsa",
        r"C:\Users\alex\.ssh\id_rsa",
    ),
)
def test_recomputed_replay_and_sidecar_still_reject_private_strings(
    tmp_path: Path, leak: str
):
    source = Path("backend/graphene/orchestration/static/mission-replay.json")
    payload = json.loads(source.read_bytes())
    snapshot = payload["snapshot"]
    snapshot["mission"]["goal"] = leak
    snapshot["snapshot_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in snapshot.items()
            if key not in {"cursor", "snapshot_sha256"}
        }
    )
    raw = canonical_json_bytes(payload) + b"\n"
    replay_path = tmp_path / "mission-replay.json"
    replay_path.write_bytes(raw)
    replay_path.with_suffix(".sha256").write_text(sha256_hex(raw) + "\n")

    with pytest.raises(MissionReplayInvalid):
        load_verified_mission_replay(replay_path)
