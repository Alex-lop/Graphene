from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from ..hashing import canonical_json_bytes, sha256_hex
from .mission_control import create_mission_control_app
from .projection import (
    GenericAttemptEvidence,
    MissionControlSnapshot,
    MissionDelta,
    MissionNotFound,
    MissionTaskDetail,
    apply_delta,
    attempt_evidence,
    task_detail,
)

STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_REPLAY_PATH = STATIC_DIR / "mission-replay.json"
MISSION_REPLAY_TRUTH_LABEL = (
    "VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN "
    "ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD"
)
_FORBIDDEN = (
    b'"argv"',
    b'"environment"',
    b'"prompt"',
    b'"reasoning"',
    b'"chain_of_thought"',
    b'"stdout"',
    b'"stderr"',
    b'"secret"',
    b'"password"',
    b'"token"',
    b"sk-",
    b"/private/",
)
_SECRET_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bsk-[A-Za-z0-9_-]{16,}\b",
        r"\bAIza[0-9A-Za-z_-]{20,}\b",
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"(?i)\bbearer\s+[A-Za-z0-9._~-]{16,}\b",
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*"
        r"[\"']?[^\s\"',;]{8,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )
)
_HOST_PATH = re.compile(
    r"(?i)(?:^|[\s'\"`:=])(?:/(?:Users|home|private|root|tmp|var/folders)/|"
    r"[A-Z]:[\\/]|\\\\[^\\/]+[\\/])"
)
_PATH_FIELDS = frozenset({"href", "paths", "read_scope", "write_scope"})


class MissionReplayInvalid(RuntimeError):
    pass


def _replay_value_is_public(value: Any, field: str | None = None) -> bool:
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _replay_value_is_public(item, key)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return all(_replay_value_is_public(item, field) for item in value)
    if not isinstance(value, str):
        return True
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        return False
    if _HOST_PATH.search(value) or value.startswith(("file://", "~")):
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if field == "href":
        return (
            value.startswith("/")
            and not value.startswith("//")
            and ".." not in posix.parts
        )
    if field in _PATH_FIELDS:
        return (
            not posix.is_absolute()
            and not windows.is_absolute()
            and ".." not in posix.parts
            and ".." not in windows.parts
        )
    return not posix.is_absolute() and not windows.is_absolute()


@dataclass(frozen=True, slots=True)
class VerifiedMissionReplay:
    mission_id: str
    snapshot: MissionControlSnapshot
    deltas: tuple[dict[str, object], ...]
    stages: tuple[MissionControlSnapshot, ...]
    meta: dict[str, object]


def apply_replay_envelope(
    before: MissionControlSnapshot, envelope: dict[str, object]
) -> MissionControlSnapshot:
    if envelope.get("type") == "reset":
        if set(envelope) != {"type", "cursor", "snapshot"}:
            raise ValueError("mission replay reset fields are invalid")
        value = MissionControlSnapshot.model_validate(envelope["snapshot"])
    elif envelope.get("type") == "delta":
        if set(envelope) != {"type", "cursor", "delta"}:
            raise ValueError("mission replay delta fields are invalid")
        value = apply_delta(before, MissionDelta.model_validate(envelope["delta"]))
    else:
        raise ValueError("mission replay envelope type is invalid")
    if envelope.get("cursor") != value.cursor:
        raise ValueError("mission replay cursor is invalid")
    return value


def load_verified_mission_replay(
    path: str | Path = DEFAULT_REPLAY_PATH,
) -> VerifiedMissionReplay:
    replay_path = Path(path)
    try:
        raw = replay_path.read_bytes()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"meta", "snapshot", "deltas"}:
            raise ValueError("mission replay document fields are invalid")
        expected = replay_path.with_suffix(".sha256").read_text().strip()
        if raw != canonical_json_bytes(payload) + b"\n" or sha256_hex(raw) != expected:
            raise ValueError("mission replay bytes do not match their checked-in digest")
        if any(value in raw.lower() for value in _FORBIDDEN) or not _replay_value_is_public(
            payload
        ):
            raise ValueError("mission replay contains fields outside the public contract")
        snapshot = MissionControlSnapshot.model_validate(payload["snapshot"])
        deltas = tuple(payload["deltas"])
        stages = [snapshot]
        for envelope in deltas:
            stages.append(apply_replay_envelope(stages[-1], envelope))
        meta = dict(payload["meta"])
        if set(meta) != {
            "cloud_proof",
            "driver",
            "final_head",
            "final_snapshot_sha256",
            "gemini_calls",
            "human_attestation",
            "live_agent",
            "mode",
            "new_test_execution",
            "truth_label",
        }:
            raise ValueError("mission replay metadata fields are invalid")
        final = stages[-1]
        if (
            meta.get("mode") != MISSION_REPLAY_TRUTH_LABEL
            or meta.get("truth_label") != MISSION_REPLAY_TRUTH_LABEL
            or meta.get("driver") != "mission-replay"
            or meta.get("live_agent") is not False
            or meta.get("human_attestation") is not False
            or meta.get("new_test_execution") is not False
            or meta.get("gemini_calls") != 0
            or meta.get("cloud_proof") is not False
            or meta.get("final_snapshot_sha256") != final.snapshot_sha256
            or meta.get("final_head") != final.head.model_dump(mode="json")
        ):
            raise ValueError("mission replay truth contract is invalid")
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
        MissionReplayInvalid,
    ) as error:
        raise MissionReplayInvalid("checked-in mission replay is invalid") from error
    return VerifiedMissionReplay(
        mission_id=snapshot.mission.mission_id,
        snapshot=snapshot,
        deltas=deltas,
        stages=tuple(stages),
        meta=meta,
    )


class ReplayMissionProjection:
    def __init__(self, replay: VerifiedMissionReplay):
        self.replay = replay
        self._by_cursor = {item.cursor: item for item in replay.stages}

    def snapshot(self, mission_id: str) -> MissionControlSnapshot:
        if mission_id != self.replay.mission_id:
            raise MissionNotFound("mission replay not found")
        return self.replay.stages[-1]

    def snapshot_at_cursor(
        self, mission_id: str, cursor: str
    ) -> MissionControlSnapshot:
        if mission_id != self.replay.mission_id or cursor not in self._by_cursor:
            raise MissionNotFound("mission replay cursor not found")
        return self._by_cursor[cursor]

    def task_detail(self, mission_id: str, task_id: str) -> MissionTaskDetail:
        return task_detail(self.snapshot(mission_id), task_id)

    def attempt_evidence(
        self, mission_id: str, attempt_id: str
    ) -> GenericAttemptEvidence:
        return attempt_evidence(self.snapshot(mission_id), attempt_id)


def create_mission_replay_app(
    read_token: str,
    replay: VerifiedMissionReplay | None = None,
    *,
    stream_interval_seconds: float = 0.35,
):
    replay = replay or load_verified_mission_replay()
    return create_mission_control_app(
        ReplayMissionProjection(replay),
        replay.mission_id,
        read_token,
        MISSION_REPLAY_TRUTH_LABEL,
        replay=True,
        truth_label=MISSION_REPLAY_TRUTH_LABEL,
        stream_interval_seconds=stream_interval_seconds,
    )
