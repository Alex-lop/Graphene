from __future__ import annotations

import http.client
import json
import socket
import threading
import time

import uvicorn
from fastapi.testclient import TestClient

from graphene.orchestration.mission_control import create_mission_control_app
from graphene.orchestration.projection import apply_delta
from graphene.orchestration.replay import (
    MISSION_REPLAY_TRUTH_LABEL,
    ReplayMissionProjection,
    VerifiedMissionReplay,
    load_verified_mission_replay,
)

TOKEN = "ephemeral-mission-token"


def test_mission_control_is_authenticated_read_only_and_bootstraps_safely():
    replay = load_verified_mission_replay()
    app = create_mission_control_app(
        ReplayMissionProjection(replay),
        replay.mission_id,
        TOKEN,
        MISSION_REPLAY_TRUTH_LABEL,
        replay=True,
        truth_label=MISSION_REPLAY_TRUTH_LABEL,
    )
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as client:
        assert client.get("/api/mission-control/health").status_code == 401
        health = client.get("/api/mission-control/health", headers=headers)
        assert health.json()["read_only"] is True
        assert health.json()["authoritative_writes"] is False
        assert health.json()["live_agent"] is False
        assert health.headers["cache-control"] == "no-store"
        path = f"/api/mission-control/missions/{replay.mission_id}/snapshot"
        response = client.get(path, headers=headers)
        assert response.json()["snapshot_sha256"] == replay.stages[-1].snapshot_sha256
        assert client.head(path, headers=headers).status_code == 200
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(path, headers=headers).status_code == 405
        task = client.get(
            f"/api/mission-control/missions/{replay.mission_id}/tasks/render_markdown",
            headers=headers,
        )
        assert task.json()["task"]["task_id"] == "render_markdown"
        evidence = client.get(
            f"/api/mission-control/missions/{replay.mission_id}/attempts/attempt_render_markdown_2/evidence",
            headers=headers,
        )
        assert evidence.json()["attempt"]["evidence"]["kind"] == "generic_attempt_v1"
        earlier = replay.stages[3]
        historical = client.get(
            f"/api/mission-control/missions/{replay.mission_id}/tasks/render_markdown?cursor={earlier.cursor}",
            headers=headers,
        )
        assert historical.json()["head"]["seq"] == earlier.head.seq
        assert historical.json()["task"]["state"] == "retrying"
        replay_document = client.get(
            f"/api/mission-control/missions/{replay.mission_id}/replay",
            headers=headers,
        )
        assert replay_document.json()["meta"]["final_snapshot_sha256"] == (
            replay.stages[-1].snapshot_sha256
        )
        expired = client.get(
            f"/api/mission-control/missions/{replay.mission_id}/stream?cursor=bad",
            headers=headers,
        )
        assert expired.status_code == 409
        assert expired.json()["code"] == "MISSION_EVIDENCE_INVALID"
        page = client.get(f"/mission-control/{replay.mission_id}")
        assert TOKEN not in page.text
        assert "window.__GRAPHENE_MISSION_CONTROL__" in page.text
        policy = page.headers["content-security-policy"]
        assert "script-src 'self' 'nonce-" in policy and "'unsafe-inline'" not in policy
        for asset_name in (
            "mission_control.css",
            "mission_control.html",
            "mission_control.mjs",
            "mission_reducer.mjs",
        ):
            asset = client.get(f"/mission-static/{asset_name}")
            assert asset.status_code == 200
            assert asset.headers["cache-control"] == "no-store"
            assert client.head(f"/mission-static/{asset_name}").status_code == 200
        assert client.get("/mission-static/mission-replay.json").status_code == 404
        assert client.get("/mission-static/mission-replay.sha256").status_code == 404
        assert client.get("/mission-static/not-allowlisted.txt").status_code == 404
        assert client.get("/mission-vendor/cytoscape.esm.min.mjs").status_code == 200


class _AdvancingSource(ReplayMissionProjection):
    def __init__(self, replay):
        super().__init__(replay)
        self.index = 0

    def snapshot(self, mission_id):
        if mission_id != self.replay.mission_id:
            return super().snapshot(mission_id)
        return self.replay.stages[self.index]


def test_stream_resumes_once_and_updates_within_two_seconds():
    replay = load_verified_mission_replay()
    source = _AdvancingSource(replay)
    app = create_mission_control_app(source, replay.mission_id, TOKEN, "TEST", stream_interval_seconds=0.05)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off"))
    listener = socket.socket(); listener.bind(("127.0.0.1", 0)); port = listener.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True); thread.start()
    deadline = time.monotonic() + 2
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        before = replay.stages[0]
        connection.request(
            "GET",
            f"/api/mission-control/missions/{replay.mission_id}/stream?cursor={before.cursor}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        response = connection.getresponse(); assert response.status == 200
        started = time.monotonic(); source.index = 1
        packet = json.loads(response.readline())
        assert time.monotonic() - started < 2
        assert packet["type"] == "delta"
        assert apply_delta(before, packet["delta"]) == replay.stages[1]
        response.close()
    finally:
        connection.close(); server.should_exit = True; thread.join(timeout=2); listener.close()
    assert not thread.is_alive()


def test_supplied_replay_document_is_the_one_the_browser_receives():
    loaded = load_verified_mission_replay()
    first = loaded.stages[0]
    custom = VerifiedMissionReplay(
        mission_id=loaded.mission_id,
        snapshot=first,
        deltas=(),
        stages=(first,),
        meta={
            **loaded.meta,
            "final_head": first.head.model_dump(mode="json"),
            "final_snapshot_sha256": first.snapshot_sha256,
        },
    )
    app = create_mission_control_app(
        ReplayMissionProjection(custom),
        custom.mission_id,
        TOKEN,
        MISSION_REPLAY_TRUTH_LABEL,
        replay=True,
        truth_label=MISSION_REPLAY_TRUTH_LABEL,
    )
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as client:
        document = client.get(
            f"/api/mission-control/missions/{custom.mission_id}/replay",
            headers=headers,
        ).json()
        assert document["snapshot"]["head"]["seq"] == 1
        assert document["deltas"] == []
        assert "/mission-static/mission-replay.json" not in client.get(
            f"/mission-control/{custom.mission_id}"
        ).text
