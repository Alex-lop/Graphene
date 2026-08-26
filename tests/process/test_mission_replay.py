from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from graphene.orchestration.mission_replay import (
    MISSION_REPLAY_TRUTH_LABEL,
    load_verified_mission_replay,
)


def test_mission_replay_runs_cross_platform_without_execution_or_state(tmp_path: Path):
    replay = load_verified_mission_replay()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    token = "mission-process-token"
    environment = {
        **os.environ,
        "MISSION_REPLAY_PORT": str(port),
        "MISSION_REPLAY_TOKEN": token,
    }
    for name in tuple(environment):
        if name.startswith("GOOGLE_") or name in {
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GRAPHENE_LINEAGE_DB",
        }:
            environment.pop(name)
    code = """
import os
import uvicorn
from graphene.orchestration.mission_replay import create_mission_replay_app
uvicorn.run(create_mission_replay_app(os.environ['MISSION_REPLAY_TOKEN'], stream_interval_seconds=.05), host='127.0.0.1', port=int(os.environ['MISSION_REPLAY_PORT']), log_level='critical', access_log=False)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                connection.request(
                    "GET",
                    "/api/mission-control/health",
                    headers={"Authorization": f"Bearer {token}"},
                )
                response = connection.getresponse()
                if response.status == 200:
                    break
            except OSError:
                time.sleep(0.05)
                connection.close()
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        else:
            raise AssertionError("mission replay server did not start")
        health = json.loads(response.read())
        assert health["mode"] == MISSION_REPLAY_TRUTH_LABEL
        assert health["authoritative_writes"] is False
        assert health["live_agent"] is False
        assert health["human_attestation"] is False
        assert health["new_test_execution"] is False
        assert health["gemini_calls"] == 0
        assert health["cloud_proof"] is False
        connection.request(
            "GET",
            f"/api/mission-control/missions/{replay.mission_id}/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )
        snapshot = json.loads(connection.getresponse().read())
        assert snapshot["snapshot_sha256"] == replay.stages[-1].snapshot_sha256
        connection.request("GET", f"/mission-control/{replay.mission_id}")
        page = connection.getresponse()
        assert page.status == 200
        assert b"Mission Control" in page.read()
    finally:
        connection.close()
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    assert process.returncode in {0, -15}
    assert token not in stdout + stderr
    assert list(tmp_path.iterdir()) == []
