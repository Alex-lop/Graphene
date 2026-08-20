from __future__ import annotations

import http.client
import json
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from fastapi.testclient import TestClient
import pytest

from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.local_result import (
    LocalResultError,
    LocalResultReceipt,
    finalize_local_result_decision,
    prepare_local_final_result_bundle,
)
from graphene.orchestration.models import (
    AttemptState,
    EvidenceReference,
    MissionEventType,
    MissionHead,
    MissionStatus,
    PublicationState,
    TaskKind,
)
from graphene.orchestration.mission_control import create_mission_control_app
from graphene.orchestration.projection import (
    MissionControlSnapshot,
    MissionProjection,
    apply_delta,
)
from graphene.orchestration.replay import (
    MISSION_REPLAY_TRUTH_LABEL,
    ReplayMissionProjection,
    VerifiedMissionReplay,
    load_verified_mission_replay,
)
from graphene.orchestration.scripted import (
    load_scenario,
    run_scripted_mission,
    scripted_supported,
)
from graphene.orchestration.store import MissionConflict, SQLiteMissionStore

TOKEN = "ephemeral-mission-token"
COMMAND_TOKEN = "separate-command-token"
ORIGIN = "http://testserver"
FAKE_BUNDLE_ID = "final_result_" + "1" * 32
FAKE_BUNDLE_SHA256 = "2" * 64


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
        assert task.json()["task"]["contract"] == (
            "Produce the scoped Markdown status renderer and pass check_render_markdown."
        )
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
        assert '"commandsEnabled":false' in page.text
        assert '"inputEnabled":false' in page.text
        assert '"cancelEnabled":false' in page.text
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
        command_path = f"/api/mission-control/missions/{replay.mission_id}/commands"
        command = {
            "action": "pause",
            "command_id": "replay_command_0001",
            "expected_head": replay.stages[-1].head.model_dump(mode="json"),
            "target_id": replay.mission_id,
            "confirmation": f"pause:{replay.mission_id}",
        }
        assert client.post(command_path, json=command).status_code == 404


class _CommandStore:
    def __init__(self, head):
        self.current = head
        self.calls = []
        self.results = {}
        self.requests = {}
        self.artifact_resolver = _ArtifactResolver()

    def head(self, mission_id):
        assert mission_id == self.current.mission_id
        return self.current

    def pause(self, mission_id, command_id, **kwargs):
        semantic = {
            name: value for name, value in kwargs.items() if name != "recorded_at"
        }
        if command_id in self.results:
            if self.requests[command_id] != semantic:
                raise MissionConflict(
                    "mission command id was reused with another request"
                )
            return self.results[command_id]
        expected = kwargs["expected_head"]
        if (
            expected.seq != self.current.seq
            or expected.event_sha256 != self.current.event_sha256
        ):
            raise MissionConflict("mission head changed")
        self.calls.append(("pause", mission_id, command_id, kwargs))
        self.current = SimpleNamespace(
            mission_id=mission_id,
            seq=self.current.seq + 1,
            event_sha256="f" * 64,
        )
        self.results[command_id] = self.current
        self.requests[command_id] = semantic
        return self.current

    def reject_plan(self, mission_id, command_id, *, expected_revision, **kwargs):
        result = self.pause(mission_id, command_id, **kwargs)
        self.calls[-1] = (
            "reject_plan",
            mission_id,
            command_id,
            {**kwargs, "expected_revision": expected_revision},
        )
        return result

    def __getattr__(self, name):
        if name in {
            "resume",
            "cancel",
            "request_replan",
            "retry_task",
            "approve_plan",
            "decide_gate",
            "approve_final_result",
            "reject_final_result",
        }:
            return lambda *args, **kwargs: self.pause(args[0], args[-1], **kwargs)
        raise AttributeError(name)

    def supply_task_input(
        self, mission_id, task_id, gate_id, reference, command_id, **kwargs
    ):
        if command_id in self.results:
            return self.results[command_id]
        expected = kwargs["expected_head"]
        if (
            expected.seq != self.current.seq
            or expected.event_sha256 != self.current.event_sha256
        ):
            raise MissionConflict("mission head changed")
        self.calls.append(
            (
                "supply_task_input",
                mission_id,
                command_id,
                {
                    **kwargs,
                    "task_id": task_id,
                    "gate_id": gate_id,
                    "reference": reference,
                },
            )
        )
        self.current = SimpleNamespace(
            mission_id=mission_id,
            seq=self.current.seq + 1,
            event_sha256="e" * 64,
        )
        self.results[command_id] = self.current
        self.requests[command_id] = {
            "task_id": task_id,
            "gate_id": gate_id,
            "reference": reference,
            **{name: value for name, value in kwargs.items() if name != "recorded_at"},
        }
        return self.current


class _ArtifactResolver:
    def __init__(self):
        self.values = {}

    def put_artifact(self, kind, content):
        digest = sha256_hex(content)
        reference = EvidenceReference(
            kind=kind, id=f"artifact_{digest[:32]}", sha256=digest
        )
        self.values[(kind, reference.id)] = content
        return reference

    def resolve(self, kind, artifact_id):
        return self.values.get((kind, artifact_id))


class _CommandSource(ReplayMissionProjection):
    def __init__(self, replay, stage):
        super().__init__(replay)
        self.stage = stage
        self.store = _CommandStore(stage.head)

    def snapshot(self, mission_id):
        if mission_id != self.replay.mission_id:
            return super().snapshot(mission_id)
        return self.stage


def _test_input_coordinator(store):
    def coordinate(**values):
        reference = store.artifact_resolver.put_artifact(
            "operator-input", values.pop("input_bytes")
        )
        return store.supply_task_input(
            values.pop("mission_id"),
            values.pop("task_id"),
            values.pop("gate_id"),
            reference,
            values.pop("command_id"),
            **values,
        )

    return coordinate


def _needs_input_stage(stage):
    value = stage.model_dump(mode="json")
    for task in value["tasks"]:
        if task["task_id"] == "redact_notes":
            task["state"] = "needs_input"
            task["blocker_reason"] = "input:gate_privacy_default"
    public = {
        name: item
        for name, item in value.items()
        if name not in {"cursor", "snapshot_sha256"}
    }
    value["snapshot_sha256"] = canonical_json_sha256(public)
    return MissionControlSnapshot.model_validate(value)


def _proposed_stage(stage):
    value = stage.model_dump(mode="json")
    value["mission"]["status"] = "proposed"
    public = {
        name: item
        for name, item in value.items()
        if name not in {"cursor", "snapshot_sha256"}
    }
    value["snapshot_sha256"] = canonical_json_sha256(public)
    return MissionControlSnapshot.model_validate(value)


def _runtime_final_stage(stage, candidate, verification, bundle_reference):
    value = stage.model_dump(mode="json")
    value["result"] = {
        "state": "awaiting_decision",
        "summary": "Runtime candidate and bound verification await a decision.",
        "bundle_id": FAKE_BUNDLE_ID,
        "bundle_sha256": FAKE_BUNDLE_SHA256,
        "evidence_refs": [
            {
                "kind": "artifact-envelope-v2",
                "id": "publication_runtime_patch",
                "sha256": "c" * 64,
            },
            {
                "kind": "artifact-envelope-v2",
                "id": "publication_runtime_verification",
                "sha256": "d" * 64,
            },
            bundle_reference.model_dump(mode="json"),
        ],
    }
    value["publications"].extend(
        (
            {
                "publication_id": "publication_runtime_patch",
                "task_id": "assemble",
                "attempt_id": "attempt_assemble_1",
                "output_name": "assembled_output",
                "kind": "patch",
                "state": "accepted",
                "sha256": candidate.sha256,
                "paths": ["backend/runtime.py", "tests/test_runtime.py"],
                "consumers": ["verify"],
            },
            {
                "publication_id": "publication_runtime_verification",
                "task_id": "verify",
                "attempt_id": "attempt_verify_1",
                "output_name": "bound_check",
                "kind": "test-receipt",
                "state": "accepted",
                "sha256": verification.sha256,
                "paths": ["receipts/runtime.json"],
                "consumers": [],
            },
        )
    )
    value["publications"].sort(key=lambda item: item["publication_id"])
    public = {
        name: item
        for name, item in value.items()
        if name not in {"cursor", "snapshot_sha256"}
    }
    value["snapshot_sha256"] = canonical_json_sha256(public)
    return MissionControlSnapshot.model_validate(value)


class _RuntimeFinalStore(_CommandStore):
    def __init__(self, head, evidence, candidate, verification):
        super().__init__(head)
        self.current = MissionHead(
            mission_id=head.mission_id,
            seq=head.seq,
            event_sha256=head.event_sha256,
            event_count=head.seq,
        )
        self.artifact_resolver = evidence
        self.local_commit_verifier = None
        self.candidate = candidate
        self.verification = verification
        self.final_calls = []
        self.events = []
        self.domain = SimpleNamespace(
            mission=SimpleNamespace(
                creation_source="operator",
                base_sha="a" * 40,
                final_outcome=None,
            ),
            plan=SimpleNamespace(
                tasks=(
                    SimpleNamespace(
                        kind=TaskKind.ASSEMBLY, acceptance_checks=("assemble",)
                    ),
                    SimpleNamespace(
                        kind=TaskKind.VERIFICATION, acceptance_checks=("runtime-check",)
                    ),
                )
            ),
            tasks=(
                SimpleNamespace(task_id="assemble", kind=TaskKind.ASSEMBLY),
                SimpleNamespace(task_id="verify", kind=TaskKind.VERIFICATION),
            ),
            publications=(
                SimpleNamespace(
                    publication_id="publication_runtime_patch",
                    task_id="assemble",
                    attempt_id="attempt_assemble_1",
                    kind="patch",
                    state=PublicationState.ACCEPTED,
                    sha256=candidate.sha256,
                    published_reference=lambda: candidate,
                ),
                SimpleNamespace(
                    publication_id="publication_runtime_verification",
                    task_id="verify",
                    attempt_id="attempt_verify_1",
                    kind="test-receipt",
                    state=PublicationState.ACCEPTED,
                    sha256=verification.sha256,
                    published_reference=lambda: verification,
                ),
            ),
            attempts=(
                SimpleNamespace(
                    attempt_id="attempt_assemble_1",
                    state=AttemptState.COMMITTED,
                    evidence_refs=(candidate,),
                ),
                SimpleNamespace(
                    attempt_id="attempt_verify_1",
                    state=AttemptState.COMMITTED,
                    evidence_refs=(verification,),
                ),
            ),
            head=self.current,
        )

    def snapshot(self, mission_id):
        assert mission_id == self.current.mission_id
        self.domain.head = self.current
        return self.domain

    def bind_local_commit_verifier(self, verifier):
        self.local_commit_verifier = verifier

    def approve_final_result(self, mission_id, command_id, **kwargs):
        assert kwargs["expected_bundle_id"] == FAKE_BUNDLE_ID
        self.final_calls.append(("approve", command_id, kwargs))
        self.current = MissionHead(
            mission_id=mission_id,
            seq=self.current.seq + 1,
            event_sha256="d" * 64,
            event_count=self.current.seq + 1,
        )
        self.domain.mission.final_outcome = "approved_pending_commit"
        return self.current

    def reject_final_result(self, mission_id, command_id, **kwargs):
        assert kwargs["expected_bundle_id"] == FAKE_BUNDLE_ID
        self.final_calls.append(("reject", command_id, kwargs))
        self.current = MissionHead(
            mission_id=mission_id,
            seq=self.current.seq + 1,
            event_sha256="e" * 64,
            event_count=self.current.seq + 1,
        )
        self.domain.mission.final_outcome = "rejected"
        return self.current

    def record_isolated_commit(
        self, mission_id, commit_sha, receipt, command_id, *, recorded_at
    ):
        assert self.artifact_resolver.resolve(receipt.kind, receipt.id) is not None
        self.final_calls.append(
            (
                "record",
                command_id,
                {"commit_sha": commit_sha, "recorded_at": recorded_at},
            )
        )
        self.current = MissionHead(
            mission_id=mission_id,
            seq=self.current.seq + 1,
            event_sha256="f" * 64,
            event_count=self.current.seq + 1,
        )
        self.domain.mission.final_outcome = "approved"
        return self.current

    def tail(self, mission_id, after_seq, limit):
        assert mission_id == self.current.mission_id
        return tuple(self.events[after_seq : after_seq + limit])


class _RuntimeFinalSource(ReplayMissionProjection):
    def __init__(self, replay, stage, store):
        super().__init__(replay)
        self.stage = stage
        self.store = store

    def snapshot(self, mission_id):
        if mission_id != self.replay.mission_id:
            return super().snapshot(mission_id)
        return self.stage


def _fake_local_receipt(mission_id, candidate, verification, decision, values):
    approved = decision == "approve"
    return LocalResultReceipt.create(
        mission_id=mission_id,
        decision=decision,
        truth_kind=values["truth_kind"],
        operator_label=values["operator_label"],
        rationale_sha256=(
            None
            if values["rationale"] is None
            else sha256_hex(values["rationale"].encode())
        ),
        base_sha="a" * 40,
        candidate_patch_sha256=candidate.sha256,
        verification_id=verification.id,
        verification_sha256=verification.sha256,
        changed_paths=("backend/runtime.py",) if approved else (),
        local_commit_sha="c" * 40 if approved else None,
        result_ref=(
            "refs/graphene/results/" + sha256_hex(mission_id.encode())[:24]
            if approved
            else None
        ),
        outcome="isolated_local_commit" if approved else "rejected_no_commit",
        pushed=False,
        pull_request_created=False,
        deployed=False,
    )


def test_live_command_plane_has_separate_auth_origin_csrf_head_and_server_identity():
    replay = load_verified_mission_replay()
    source = _CommandSource(replay, replay.stages[1])
    app = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="bound-browser-operator",
    )
    read_headers = {"Authorization": f"Bearer {TOKEN}"}
    command_headers = {
        "Authorization": f"Bearer {COMMAND_TOKEN}",
        "Origin": ORIGIN,
    }
    base = f"/api/mission-control/missions/{replay.mission_id}/commands"
    head = source.stage.head.model_dump(mode="json")
    body = {
        "action": "pause",
        "command_id": "browser_pause_0001",
        "expected_head": head,
        "target_id": replay.mission_id,
        "confirmation": f"pause:{replay.mission_id}",
    }
    with TestClient(app) as client:
        health = client.get("/api/mission-control/health", headers=read_headers).json()
        assert health["read_only"] is False
        assert health["authoritative_writes"] is True
        page = client.get(f"/mission-control/{replay.mission_id}")
        assert '"commandsEnabled":true' in page.text
        assert '"inputEnabled":false' in page.text
        assert COMMAND_TOKEN not in page.text
        assert (
            client.post(
                f"{base}/session", headers={**read_headers, "Origin": ORIGIN}
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"{base}/session",
                headers={**command_headers, "Origin": "http://localhost"},
            ).status_code
            == 403
        )
        session = client.post(f"{base}/session", headers=command_headers)
        assert session.status_code == 200
        assert session.json()["operator_label"] == "bound-browser-operator"
        assert "HttpOnly" in session.headers["set-cookie"]
        csrf = session.json()["csrf_token"]
        assert client.post(base, headers=command_headers, json=body).status_code == 403
        mutation_headers = {**command_headers, "X-CSRF-Token": csrf}

        invalid = client.post(
            base,
            headers=mutation_headers,
            json={**body, "operator_label": "client-forged"},
        )
        assert invalid.status_code == 422
        assert invalid.json() == {
            "code": "INVALID_COMMAND",
            "detail": "Request envelope is invalid.",
        }
        assert invalid.headers["cache-control"] == "no-store"
        wrong_confirmation = client.post(
            base,
            headers=mutation_headers,
            json={**body, "confirmation": "yes"},
        )
        assert wrong_confirmation.status_code == 409
        assert wrong_confirmation.json()["code"] == "CONFIRMATION_REQUIRED"
        assert source.store.calls == []

        accepted = client.post(base, headers=mutation_headers, json=body)
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        assert len(source.store.calls) == 1
        _, called_mission, called_id, kwargs = source.store.calls[0]
        assert (called_mission, called_id) == (replay.mission_id, body["command_id"])
        assert kwargs["operator_label"] == "bound-browser-operator"
        assert kwargs["truth_kind"].value == "human_attested"
        assert kwargs["expected_head"].seq == head["seq"]

        assert (
            client.post(base, headers=mutation_headers, json=body).json()
            == accepted.json()
        )
        assert len(source.store.calls) == 1
        conflict = client.post(
            base,
            headers=mutation_headers,
            json={**body, "rationale": "different payload"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
        stale = client.post(
            base,
            headers=mutation_headers,
            json={**body, "command_id": "browser_pause_0002"},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "MISSION_HEAD_STALE"
        assert stale.json()["current_head"]["seq"] == head["seq"] + 1

    restarted = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="bound-browser-operator",
    )
    with TestClient(restarted) as client:
        session = client.post(f"{base}/session", headers=command_headers)
        replay_headers = {
            **command_headers,
            "X-CSRF-Token": session.json()["csrf_token"],
        }
        replayed = client.post(base, headers=replay_headers, json=body)
        assert replayed.status_code == 200
        assert replayed.json() == accepted.json()
        assert len(source.store.calls) == 1
        reused = client.post(
            base,
            headers=replay_headers,
            json={**body, "rationale": "different after restart"},
        )
        assert reused.status_code == 409
        assert reused.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_command_configuration_fails_closed():
    replay = load_verified_mission_replay()
    source = _CommandSource(replay, replay.stages[1])
    for command_token, origin, replay_mode in (
        (TOKEN, ORIGIN, False),
        (COMMAND_TOKEN, None, False),
        (COMMAND_TOKEN, ORIGIN, True),
    ):
        try:
            create_mission_control_app(
                source,
                replay.mission_id,
                TOKEN,
                "TEST",
                replay=replay_mode,
                command_token=command_token,
                command_origin=origin,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe command configuration was accepted")


def test_browser_cancel_requires_cleanup_coordinator_and_never_calls_store_directly():
    replay = load_verified_mission_replay()
    stage = replay.stages[1]
    source = _CommandSource(replay, stage)
    calls = []

    def coordinated_cancel(**values):
        calls.append(values)
        return MissionHead(
            mission_id=replay.mission_id,
            seq=stage.head.seq + 1,
            event_sha256="9" * 64,
            event_count=stage.head.seq + 1,
        )

    def post(app, command_id):
        base = f"/api/mission-control/missions/{replay.mission_id}/commands"
        command_headers = {
            "Authorization": f"Bearer {COMMAND_TOKEN}",
            "Origin": ORIGIN,
        }
        with TestClient(app) as client:
            session = client.post(f"{base}/session", headers=command_headers)
            return client.post(
                base,
                headers={
                    **command_headers,
                    "X-CSRF-Token": session.json()["csrf_token"],
                },
                json={
                    "action": "cancel",
                    "command_id": command_id,
                    "expected_head": stage.head.model_dump(mode="json"),
                    "target_id": replay.mission_id,
                    "confirmation": f"cancel:{replay.mission_id}",
                    "rationale": "Cancel after exact owned-runtime cleanup.",
                },
            )

    unavailable = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
    )
    response = post(unavailable, "browser_cancel_no_cleanup")
    assert response.status_code == 409
    assert response.json()["code"] == "TARGET_STALE"
    assert source.store.calls == []

    coordinated = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="bound-browser-operator",
        cancel_coordinator=coordinated_cancel,
    )
    response = post(coordinated, "browser_cancel_coordinated")
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["expected_head"].seq == stage.head.seq
    assert calls[0]["operator_label"] == "bound-browser-operator"
    assert calls[0]["truth_kind"] == TruthKind.HUMAN_ATTESTED
    assert source.store.calls == [], "Mission Control must not bypass runtime cleanup"

    def cleanup_failed(**_values):
        raise RuntimeError("private process detail")

    failed = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        cancel_coordinator=cleanup_failed,
    )
    response = post(failed, "browser_cancel_cleanup_failed")
    assert response.status_code == 409
    assert response.json() == {
        "code": "COMMAND_REJECTED",
        "detail": "The committed state does not allow this command.",
    }
    assert "private process detail" not in response.text
    assert source.store.calls == []


def test_browser_reject_plan_uses_revision_bound_transition_without_cancel_alias():
    replay = load_verified_mission_replay()
    stage = _proposed_stage(replay.stages[0])
    source = _CommandSource(replay, stage)
    app = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="bound-browser-operator",
    )
    base = f"/api/mission-control/missions/{replay.mission_id}/commands"
    command_headers = {
        "Authorization": f"Bearer {COMMAND_TOKEN}",
        "Origin": ORIGIN,
    }
    with TestClient(app) as client:
        session = client.post(f"{base}/session", headers=command_headers)
        response = client.post(
            base,
            headers={
                **command_headers,
                "X-CSRF-Token": session.json()["csrf_token"],
            },
            json={
                "action": "reject_plan",
                "command_id": "browser_reject_plan_001",
                "expected_head": stage.head.model_dump(mode="json"),
                "target_id": "plan:1",
                "expected_plan_revision": 1,
                "confirmation": "reject_plan:plan:1",
                "rationale": "The proposed plan is not acceptable.",
            },
        )
    assert response.status_code == 200, response.text
    action, _, _, values = source.store.calls[0]
    assert action == "reject_plan"
    assert values["expected_revision"] == 1
    assert values["expected_head"].seq == stage.head.seq
    assert values["truth_kind"] == TruthKind.HUMAN_ATTESTED


@pytest.mark.parametrize(
    ("action", "expected_store_calls", "expected_low_level"),
    (
        ("approve_final", ["approve", "record"], ["reject", "approve"]),
        ("reject_final", ["reject"], ["reject"]),
    ),
)
def test_runtime_patch_final_decision_uses_authoritative_binding_and_local_flow(
    tmp_path: Path,
    monkeypatch,
    action,
    expected_store_calls,
    expected_low_level,
):
    replay = load_verified_mission_replay()
    evidence = SQLiteAttemptEvidenceStore(tmp_path / f"{action}-evidence.sqlite3")
    candidate = evidence.put_artifact("patch", b"runtime candidate patch")
    verification = evidence.put_artifact("test-receipt", b"bound runtime receipt")
    bundle_reference = evidence.put_artifact("final-result-bundle", b"bundle proof")
    stage = _runtime_final_stage(
        replay.stages[-2], candidate, verification, bundle_reference
    )
    store = _RuntimeFinalStore(stage.head, evidence, candidate, verification)
    source = _RuntimeFinalSource(replay, stage, store)
    low_level_calls = []

    def fake_finalize(**values):
        assert values["expected_bundle_id"] == FAKE_BUNDLE_ID
        low_level_calls.append("reject")
        method = (
            store.approve_final_result
            if values["approved"]
            else store.reject_final_result
        )
        head = method(
            values["mission_id"],
            values["command_id"],
            expected_head=values["expected_head"],
            expected_bundle_id=values["expected_bundle_id"],
            operator_label=values["operator_label"],
            rationale=values["rationale"],
            truth_kind=values["truth_kind"],
            recorded_at=values["recorded_at"],
        )
        decision = "approve" if values["approved"] else "reject"
        receipt = _fake_local_receipt(
            replay.mission_id, candidate, verification, decision, values
        )
        if values["approved"]:
            low_level_calls.append("approve")
            receipt_reference = evidence.put_artifact(
                "local-result-receipt", b"fake receipt"
            )
            head = store.record_isolated_commit(
                values["mission_id"],
                receipt.local_commit_sha,
                receipt_reference,
                "record_result_0001",
                recorded_at=values["recorded_at"],
            )
        return head, receipt

    monkeypatch.setattr(
        "graphene.orchestration.mission_control.finalize_local_result_decision",
        fake_finalize,
    )
    app = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="bound-browser-operator",
    )
    base = f"/api/mission-control/missions/{replay.mission_id}/commands"
    command_headers = {
        "Authorization": f"Bearer {COMMAND_TOKEN}",
        "Origin": ORIGIN,
    }
    with TestClient(app) as client:
        session = client.post(f"{base}/session", headers=command_headers)
        headers = {
            **command_headers,
            "X-CSRF-Token": session.json()["csrf_token"],
        }
        body = {
            "action": action,
            "command_id": f"browser_{action}_001",
            "expected_head": stage.head.model_dump(mode="json"),
            "target_id": f"result:{replay.mission_id}",
            "expected_bundle_id": FAKE_BUNDLE_ID,
            "confirmation": f"{action}:result:{replay.mission_id}:{FAKE_BUNDLE_ID}",
            "rationale": "Reviewed exact digest, paths, evidence, and unknowns.",
        }
        response = client.post(base, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert [item[0] for item in store.final_calls] == expected_store_calls
    assert low_level_calls == expected_low_level
    assert all(
        call[2]["truth_kind"] == TruthKind.HUMAN_ATTESTED
        for call in store.final_calls
        if call[0] in {"approve", "reject"}
    )
    if action == "reject_final":
        assert not any(call[0] == "record" for call in store.final_calls)


def test_approved_pending_commit_resumes_with_committed_attribution_and_new_command(
    tmp_path: Path, monkeypatch
):
    replay = load_verified_mission_replay()
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "recovery-evidence.sqlite3")
    candidate = evidence.put_artifact("patch", b"runtime candidate patch")
    verification = evidence.put_artifact("test-receipt", b"bound runtime receipt")
    bundle_bytes = b"bound final bundle"
    bundle_reference = evidence.put_artifact("final-result-bundle", bundle_bytes)
    store = _RuntimeFinalStore(
        replay.stages[-2].head, evidence, candidate, verification
    )
    first_sha, approval_sha = "1" * 64, "2" * 64
    store.current = MissionHead(
        mission_id=replay.mission_id,
        seq=2,
        event_sha256=approval_sha,
        event_count=2,
    )
    store.domain.head = store.current
    store.domain.mission.final_outcome = "approved_pending_commit"
    store.events = [
        SimpleNamespace(
            seq=1,
            event_sha256=first_sha,
            previous_event_sha256=None,
            event_type=MissionEventType.FINAL_RESULT_BUNDLE_READY,
            payload={
                "bundle_id": FAKE_BUNDLE_ID,
                "bundle_sha256": FAKE_BUNDLE_SHA256,
            },
            references=(bundle_reference,),
        ),
        SimpleNamespace(
            seq=2,
            event_sha256=approval_sha,
            previous_event_sha256=first_sha,
            event_type=MissionEventType.FINAL_CANDIDATE_APPROVED,
            command_id="original_approval_001",
            payload={
                "bundle_id": FAKE_BUNDLE_ID,
                "candidate_sha256": candidate.sha256,
                "operator_label": "original-browser-operator",
                "operator_rationale": "Original reviewed decision.",
            },
            truth_kind=TruthKind.HUMAN_ATTESTED,
        ),
    ]
    observed = {}

    fake_bundle = SimpleNamespace(
        bundle_id=FAKE_BUNDLE_ID,
        bundle_sha256=FAKE_BUNDLE_SHA256,
        candidate_reference=SimpleNamespace(content_sha256=candidate.sha256),
        verification_reference=SimpleNamespace(content_sha256=verification.sha256),
    )
    monkeypatch.setattr(
        "graphene.orchestration.final_bundle.FinalResultBundleV2.model_validate_json",
        lambda _raw: fake_bundle,
    )

    def unexpected_reject(**_values):
        raise AssertionError("recovery must not commit or preflight another decision")

    def fake_approve_result(**values):
        observed.update(values)
        return _fake_local_receipt(
            replay.mission_id, candidate, verification, "approve", values
        )

    monkeypatch.setattr(
        "graphene.orchestration.local_result.reject_result", unexpected_reject
    )
    monkeypatch.setattr(
        "graphene.orchestration.local_result.approve_result", fake_approve_result
    )
    monkeypatch.setattr(
        "graphene.orchestration.local_result.verified_result_artifacts",
        lambda _store, _evidence, _mission_id: (candidate, verification),
    )
    head, receipt = finalize_local_result_decision(
        store=store,
        mission_id=replay.mission_id,
        command_id="recovery_command_001",
        expected_head=store.current,
        expected_bundle_id=FAKE_BUNDLE_ID,
        operator_label="new-browser-operator",
        rationale="This must not replace committed attribution.",
        truth_kind=TruthKind.HUMAN_ATTESTED,
        recorded_at=datetime.now(UTC),
        approved=True,
    )
    assert head == store.current
    assert receipt.decision == "approve"
    assert [item[0] for item in store.final_calls] == ["record"]
    assert observed["operator_label"] == "original-browser-operator"
    assert observed["rationale"] == "Original reviewed decision."
    assert observed["truth_kind"] == TruthKind.HUMAN_ATTESTED


@pytest.mark.skipif(
    not scripted_supported(),
    reason="real local-result integration requires the proven macOS fixture sandbox",
)
def test_sqlite_runtime_browser_approve_restart_and_reject_are_exact(
    tmp_path: Path,
):
    scenario = load_scenario()

    def awaiting(mission_id):
        runtime = tmp_path / mission_id
        database = tmp_path / f"{mission_id}.sqlite3"
        store = SQLiteMissionStore(database)
        run = run_scripted_mission(
            scenario=scenario,
            store=store,
            runtime=runtime,
            mission_id=mission_id,
        )
        assert (
            store.snapshot(mission_id).mission.status == MissionStatus.AWAITING_RESULT
        )
        awaiting_head = store.head(mission_id)
        ready, bundle, reference = prepare_local_final_result_bundle(
            store=store,
            mission_id=mission_id,
            expected_head=awaiting_head,
            recorded_at=datetime.now(UTC),
        )
        assert reference.kind == "final-result-bundle"
        replayed, replayed_bundle, replayed_reference = (
            prepare_local_final_result_bundle(
                store=store,
                mission_id=mission_id,
                expected_head=ready,
                recorded_at=datetime.now(UTC),
            )
        )
        assert (replayed, replayed_bundle, replayed_reference) == (
            ready,
            bundle,
            reference,
        )
        return database, runtime, store, run.candidate, bundle

    def command(store, mission_id, bundle, action, command_id):
        projection = MissionProjection(store)
        projected = projection.snapshot(mission_id)
        expected = projected.head
        assert projected.result.bundle_id == bundle.bundle_id
        assert projected.result.bundle_sha256 == bundle.bundle_sha256
        assert {reference.kind for reference in projected.result.evidence_refs} >= {
            "artifact-envelope-v2",
            "final-result-bundle",
        }
        app = create_mission_control_app(
            projection,
            mission_id,
            TOKEN,
            "TEST LIVE",
            command_token=COMMAND_TOKEN,
            command_origin=ORIGIN,
            operator_label="sqlite-browser-operator",
        )
        base = f"/api/mission-control/missions/{mission_id}/commands"
        command_headers = {
            "Authorization": f"Bearer {COMMAND_TOKEN}",
            "Origin": ORIGIN,
        }
        body = {
            "action": action,
            "command_id": command_id,
            "expected_head": expected.model_dump(mode="json"),
            "target_id": f"result:{mission_id}",
            "expected_bundle_id": bundle.bundle_id,
            "confirmation": f"{action}:result:{mission_id}:{bundle.bundle_id}",
            "rationale": "Reviewed exact runtime digest, paths, evidence, and unknowns.",
        }
        with TestClient(app) as client:
            session = client.post(f"{base}/session", headers=command_headers)
            headers = {
                **command_headers,
                "X-CSRF-Token": session.json()["csrf_token"],
            }
            response = client.post(base, headers=headers, json=body)
        assert response.status_code == 200, response.text
        return body, response.json()

    approved_id = "mission-browser-approved"
    (
        approved_db,
        approved_runtime,
        approved_store,
        _approved_candidate,
        approved_bundle,
    ) = awaiting(approved_id)
    approval_body, approval_response = command(
        approved_store,
        approved_id,
        approved_bundle,
        "approve_final",
        "browser_sqlite_approve_001",
    )
    approved_snapshot = approved_store.snapshot(approved_id)
    assert approved_snapshot.mission.status == MissionStatus.COMPLETED
    approved_events = approved_store.tail(approved_id, 0, 256)
    approval = next(
        event
        for event in approved_events
        if event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
    )
    assert approval.truth_kind == TruthKind.HUMAN_ATTESTED
    assert approval.payload["operator_label"] == "sqlite-browser-operator"
    isolated = tuple(
        event
        for event in approved_events
        if event.event_type == MissionEventType.ISOLATED_COMMIT_CREATED
    )
    assert len(isolated) == 1 and len(isolated[0].references) == 1
    receipt_reference = isolated[0].references[0]
    evidence = approved_store.artifact_resolver
    receipt_bytes = evidence.resolve(receipt_reference.kind, receipt_reference.id)
    receipt = LocalResultReceipt.model_validate_json(receipt_bytes)
    assert receipt.local_commit_sha == isolated[0].payload["local_commit_sha"]
    candidate_publication = next(
        item
        for item in approved_snapshot.publications
        if item.task_id == "assemble_candidate"
    )
    assert receipt.changed_paths == candidate_publication.paths
    result_ref = "refs/graphene/results/" + sha256_hex(approved_id.encode())[:24]
    commit = subprocess.run(
        ("git", "rev-parse", "--verify", result_ref),
        cwd=approved_runtime / "repository",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert commit.returncode == 0
    assert commit.stdout.strip() == receipt.local_commit_sha

    restarted_evidence = SQLiteAttemptEvidenceStore(
        approved_runtime / "attempt-evidence.sqlite3"
    )
    restarted_store = SQLiteMissionStore(
        approved_db, artifact_resolver=restarted_evidence
    )
    original_expected = MissionHead(
        **approval_body["expected_head"],
        event_count=approval_body["expected_head"]["seq"],
    )
    replayed_head, replayed_receipt = finalize_local_result_decision(
        store=restarted_store,
        mission_id=approved_id,
        command_id=approval_body["command_id"],
        expected_head=original_expected,
        expected_bundle_id=approved_bundle.bundle_id,
        operator_label="sqlite-browser-operator",
        rationale=approval_body["rationale"],
        truth_kind=TruthKind.HUMAN_ATTESTED,
        recorded_at=datetime.now(UTC),
        approved=True,
    )
    assert replayed_head == approved_snapshot.head
    assert replayed_receipt == receipt
    with pytest.raises(
        LocalResultError,
        match="final approval command was reused with another request",
    ):
        finalize_local_result_decision(
            store=restarted_store,
            mission_id=approved_id,
            command_id=approval_body["command_id"],
            expected_head=original_expected,
            expected_bundle_id=approved_bundle.bundle_id,
            operator_label="sqlite-browser-operator",
            rationale="Changed after the completed approval.",
            truth_kind=TruthKind.HUMAN_ATTESTED,
            recorded_at=datetime.now(UTC),
            approved=True,
        )
    restarted_projection = MissionProjection(restarted_store)
    restarted = create_mission_control_app(
        restarted_projection,
        approved_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="sqlite-browser-operator",
    )
    base = f"/api/mission-control/missions/{approved_id}/commands"
    command_headers = {
        "Authorization": f"Bearer {COMMAND_TOKEN}",
        "Origin": ORIGIN,
    }
    with TestClient(restarted) as client:
        session = client.post(f"{base}/session", headers=command_headers)
        retry = client.post(
            base,
            headers={
                **command_headers,
                "X-CSRF-Token": session.json()["csrf_token"],
            },
            json=approval_body,
        )
    assert retry.status_code == 200, retry.text
    assert retry.json() == approval_response
    assert restarted_store.head(approved_id) == approved_snapshot.head
    assert len(restarted_store.tail(approved_id, 0, 256)) == len(approved_events)

    rejected_id = "mission-browser-rejected"
    _, rejected_runtime, rejected_store, _rejected_candidate, rejected_bundle = (
        awaiting(rejected_id)
    )
    command(
        rejected_store,
        rejected_id,
        rejected_bundle,
        "reject_final",
        "browser_sqlite_reject_001",
    )
    assert rejected_store.snapshot(rejected_id).mission.status == MissionStatus.REJECTED
    assert not any(
        event.event_type == MissionEventType.ISOLATED_COMMIT_CREATED
        for event in rejected_store.tail(rejected_id, 0, 256)
    )
    rejected_ref = "refs/graphene/results/" + sha256_hex(rejected_id.encode())[:24]
    rejected_commit = subprocess.run(
        ("git", "rev-parse", "--verify", rejected_ref),
        cwd=rejected_runtime / "repository",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    assert rejected_commit.returncode != 0


def test_needs_input_is_stored_privately_and_only_reference_reaches_store():
    replay = load_verified_mission_replay()
    source = _CommandSource(replay, _needs_input_stage(replay.stages[1]))
    app = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        operator_label="bound-browser-operator",
        input_coordinator=_test_input_coordinator(source.store),
    )
    base = f"/api/mission-control/missions/{replay.mission_id}/commands"
    command_headers = {
        "Authorization": f"Bearer {COMMAND_TOKEN}",
        "Origin": ORIGIN,
    }
    with TestClient(app) as client:
        session = client.post(f"{base}/session", headers=command_headers)
        headers = {
            **command_headers,
            "X-CSRF-Token": session.json()["csrf_token"],
        }
        body = {
            "action": "supply_input",
            "command_id": "browser_input_0001",
            "expected_head": source.stage.head.model_dump(mode="json"),
            "target_id": "redact_notes",
            "gate_id": "gate_privacy_default",
            "input_text": "private operator value",
            "confirmation": "supply_input:redact_notes:gate_privacy_default",
        }
        response = client.post(base, headers=headers, json=body)
        assert response.status_code == 200
        action, _, _, call = source.store.calls[0]
        assert action == "supply_task_input"
        reference = call["reference"]
        assert reference.kind == "operator-input"
        assert source.store.artifact_resolver.resolve(reference.kind, reference.id) == (
            b"private operator value"
        )
        assert "private operator value" not in response.text
        assert call["truth_kind"].value == "human_attested"


def test_stale_input_head_is_rejected_before_private_artifact_write():
    replay = load_verified_mission_replay()
    stage = _needs_input_stage(replay.stages[1])
    source = _CommandSource(replay, stage)
    source.store.current = SimpleNamespace(
        mission_id=replay.mission_id,
        seq=stage.head.seq + 1,
        event_sha256="8" * 64,
    )
    app = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST LIVE",
        command_token=COMMAND_TOKEN,
        command_origin=ORIGIN,
        input_coordinator=_test_input_coordinator(source.store),
    )
    base = f"/api/mission-control/missions/{replay.mission_id}/commands"
    command_headers = {
        "Authorization": f"Bearer {COMMAND_TOKEN}",
        "Origin": ORIGIN,
    }
    with TestClient(app) as client:
        session = client.post(f"{base}/session", headers=command_headers)
        response = client.post(
            base,
            headers={
                **command_headers,
                "X-CSRF-Token": session.json()["csrf_token"],
            },
            json={
                "action": "supply_input",
                "command_id": "browser_stale_input_001",
                "expected_head": stage.head.model_dump(mode="json"),
                "target_id": "redact_notes",
                "gate_id": "gate_privacy_default",
                "input_text": "must not be orphaned",
                "confirmation": "supply_input:redact_notes:gate_privacy_default",
            },
        )
    assert response.status_code == 409
    assert response.json()["code"] == "MISSION_HEAD_STALE"
    assert source.store.artifact_resolver.values == {}
    assert source.store.calls == []


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
    app = create_mission_control_app(
        source,
        replay.mission_id,
        TOKEN,
        "TEST",
        stream_interval_seconds=0.05,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off")
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
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
        response = connection.getresponse()
        assert response.status == 200
        started = time.monotonic()
        source.index = 1
        packet = json.loads(response.readline())
        assert time.monotonic() - started < 2
        assert packet["type"] == "delta"
        assert apply_delta(before, packet["delta"]) == replay.stages[1]
        response.close()
    finally:
        connection.close()
        server.should_exit = True
        thread.join(timeout=2)
        listener.close()
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
        assert (
            "/mission-static/mission-replay.json"
            not in client.get(f"/mission-control/{custom.mission_id}").text
        )
