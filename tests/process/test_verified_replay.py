from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from graphene.viewer.contract import GraphSnapshot
from graphene.viewer.replay import (
    REPLAY_TRUTH_LABEL,
    apply_replay_envelope,
    load_verified_replay,
)


def test_verified_replay_runs_cross_platform_without_authoritative_state(
    tmp_path: Path,
):
    replay = load_verified_replay()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    token = "process-replay-token"
    database = tmp_path / "must-not-exist.sqlite3"
    environment = {
        **os.environ,
        "GRAPHENE_REPLAY_TEST_PORT": str(port),
        "GRAPHENE_REPLAY_TEST_TOKEN": token,
        "GRAPHENE_LINEAGE_DB": str(database),
    }
    for name in tuple(environment):
        if name.startswith("GOOGLE_") or name in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
            environment.pop(name)
    code = """
import os
import uvicorn
from graphene.viewer.replay import create_verified_replay_app
uvicorn.run(
    create_verified_replay_app(
        os.environ['GRAPHENE_REPLAY_TEST_TOKEN'], stream_interval_seconds=0.01
    ),
    host='127.0.0.1',
    port=int(os.environ['GRAPHENE_REPLAY_TEST_PORT']),
    log_level='critical',
    access_log=False,
)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            try:
                connection.request(
                    "GET",
                    "/api/viewer/health",
                    headers={"Authorization": f"Bearer {token}"},
                )
                response = connection.getresponse()
                if response.status == 200:
                    break
            except OSError:
                time.sleep(0.05)
                connection.close()
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        else:
            raise AssertionError("verified replay server did not start")

        health = json.loads(response.read())
        assert health["mode"] == REPLAY_TRUTH_LABEL
        assert health["authoritative_writes"] is False
        assert health["human_attestation"] is False
        assert health["live_agent"] is False
        assert health["new_test_execution"] is False
        connection.request(
            "GET",
            f"/api/viewer/runs/{replay.root_run_id}/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )
        snapshot = connection.getresponse()
        assert snapshot.status == 200
        snapshot_payload = json.loads(snapshot.read())
        assert snapshot_payload["graph_sha256"] == replay.snapshot.graph_sha256
        truth_kinds = {node["truth_kind"] for node in snapshot_payload["nodes"]}
        assert "simulated_fixture" in truth_kinds
        assert "human_attested" not in truth_kinds
        verified = GraphSnapshot.model_validate(snapshot_payload)
        connection.request(
            "GET",
            (
                f"/api/viewer/runs/{replay.root_run_id}/stream"
                f"?cursor={verified.cursor}"
            ),
            headers={"Authorization": f"Bearer {token}"},
        )
        stream = connection.getresponse()
        assert stream.status == 200
        for _ in replay.deltas:
            while not (line := stream.readline().strip()):
                pass
            verified = apply_replay_envelope(verified, json.loads(line))
        assert verified.graph_sha256 == replay.meta["final_graph_sha256"]
        assert verified.model_dump(mode="json")["heads"] == replay.meta["source_heads"]
        stream.close()
    finally:
        connection.close()
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)

    assert process.returncode in {0, -15}
    assert token not in stdout + stderr
    assert not database.exists()
    assert list(tmp_path.iterdir()) == []
