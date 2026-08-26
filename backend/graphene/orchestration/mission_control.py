from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..hashing import canonical_json_bytes, sha256_hex
from ..core_models import TruthKind
from ..viewer.viewer_app import STATIC_DIR as LEGACY_VIEWER_STATIC_DIR
from .local_result import (
    LocalResultError,
    LocalResultRecoveryRequired,
    finalize_local_result_decision,
)
from .mission_projection import (
    GenericAttemptEvidence,
    MissionControlSnapshot,
    MissionNotFound,
    MissionProjection,
    MissionProjectionError,
    MissionTaskDetail,
    attempt_evidence as project_attempt_evidence,
    decode_cursor,
    diff_snapshots,
    task_detail as project_task_detail,
)
from .mission_models import MissionHead
from .sqlite_mission_store import MissionConflict, MissionStoreError

STATIC_DIR = Path(__file__).with_name("static")
VENDOR_DIR = LEGACY_VIEWER_STATIC_DIR / "vendor"
_READ_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,512}$")
_ORIGIN = re.compile(
    r"^https?://(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]+)(?::[1-9][0-9]{0,4})?$"
)
_UI_ASSETS = {
    "mission_control.css": "text/css",
    "mission_control.html": "text/html",
    "mission_control.mjs": "text/javascript",
    "mission_reducer.mjs": "text/javascript",
}


class _ExpectedHead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mission_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _CommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal[
        "pause",
        "resume",
        "cancel",
        "retry_task",
        "request_replan",
        "approve_plan",
        "reject_plan",
        "decide_gate",
        "approve_final",
        "reject_final",
        "supply_input",
    ]
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    expected_head: _ExpectedHead
    target_id: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=280)
    rationale: str | None = Field(default=None, min_length=1, max_length=280)
    expected_plan_revision: int | None = Field(default=None, ge=1)
    decision: str | None = Field(default=None, min_length=1, max_length=128)
    expected_bundle_id: str | None = Field(
        default=None, pattern=r"^final_result_[0-9a-f]{32}$"
    )
    gate_id: str | None = Field(default=None, min_length=1, max_length=128)
    input_text: str | None = Field(default=None, min_length=1, max_length=4_096)

    @model_validator(mode="after")
    def action_fields_match(self) -> _CommandEnvelope:
        required = {
            "approve_plan": {"expected_plan_revision"},
            "reject_plan": {"expected_plan_revision"},
            "decide_gate": {"decision"},
            "approve_final": {"expected_bundle_id"},
            "reject_final": {"expected_bundle_id"},
            "supply_input": {"gate_id", "input_text"},
        }
        used = {
            name
            for name in (
                "expected_plan_revision",
                "decision",
                "expected_bundle_id",
                "gate_id",
                "input_text",
            )
            if getattr(self, name) is not None
        }
        expected = required.get(self.action, set())
        if used != expected:
            raise ValueError("command fields do not match action")
        return self


def _safe_script_json(value: object) -> str:
    return (
        json.dumps(value, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _projected_final_result_binding(
    snapshot: MissionControlSnapshot,
) -> tuple[Any, Any, Any, Any, Any] | None:
    """Bind result evidence to the accepted assembly and verification outputs."""

    def artifact(task_kind: str) -> tuple[Any, Any] | None:
        tasks = tuple(item for item in snapshot.tasks if item.kind == task_kind)
        if len(tasks) != 1:
            return None
        publications = tuple(
            item
            for item in snapshot.publications
            if item.task_id == tasks[0].task_id and item.state == "accepted"
        )
        if len(publications) != 1:
            return None
        publication = publications[0]
        references = tuple(
            item
            for item in snapshot.result.evidence_refs
            if item.id == publication.publication_id
            and (
                item.kind == "artifact-envelope-v2"
                or (item.kind == publication.kind and item.sha256 == publication.sha256)
            )
        )
        return (publication, references[0]) if len(references) == 1 else None

    candidate = artifact("assembly")
    verification = artifact("verification")
    if candidate is None or verification is None:
        return None
    bundles = tuple(
        item
        for item in snapshot.result.evidence_refs
        if item.kind == "final-result-bundle"
    )
    if (
        snapshot.result.bundle_id is None
        or snapshot.result.bundle_sha256 is None
        or len(bundles) != 1
    ):
        return None
    return (*candidate, *verification, bundles[0])


def create_mission_control_app(
    source: Any,
    mission_id: str,
    read_token: str,
    mode_label: str,
    *,
    replay: bool = False,
    truth_label: str = "COMMITTED MISSION PROJECTION",
    stream_interval_seconds: float = 1.0,
    command_token: str | None = None,
    command_origin: str | None = None,
    operator_label: str = "local-browser-operator",
    cancel_coordinator: Callable[..., MissionHead] | None = None,
    input_coordinator: Callable[..., MissionHead] | None = None,
) -> FastAPI:
    """Create Mission Control with an optional, separately authenticated command API."""

    if not mission_id or len(mission_id) > 128:
        raise ValueError("mission_id must be nonempty and bounded")
    if _READ_TOKEN.fullmatch(read_token) is None:
        raise ValueError("read_token must be 16-512 URL-safe characters")
    if command_token is not None:
        if replay:
            raise ValueError("replay Mission Control cannot enable commands")
        if _READ_TOKEN.fullmatch(command_token) is None or secrets.compare_digest(
            command_token, read_token
        ):
            raise ValueError("command_token must be valid and distinct from read_token")
        if command_origin is None or _ORIGIN.fullmatch(command_origin) is None:
            raise ValueError("command_origin must be one exact HTTP(S) origin")
        if not 1 <= len(operator_label) <= 64:
            raise ValueError("operator_label must be bounded")
    if not 0.05 <= stream_interval_seconds <= 10:
        raise ValueError("stream_interval_seconds must be between 0.05 and ten seconds")
    if not hasattr(source, "task_detail"):
        source = MissionProjection(source)

    app = FastAPI(
        title="Graphene Mission Control",
        version="1",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    # ponytail: bounded process-local reconnect cache; durable cursors can move into
    # the materialized store if Mission Control ever needs resume across app instances.
    snapshots: OrderedDict[str, MissionControlSnapshot] = OrderedDict()
    snapshots_lock = RLock()
    command_lock = RLock()
    command_sessions: OrderedDict[str, tuple[str, datetime]] = OrderedDict()
    command_results: OrderedDict[str, tuple[bytes, bytes]] = OrderedDict()
    command_store = getattr(source, "store", None)
    if command_token is not None and (
        command_store is None
        or not all(
            hasattr(command_store, name)
            for name in (
                "head",
                "pause",
                "resume",
                "request_replan",
                "retry_task",
                "approve_plan",
                "reject_plan",
                "decide_gate",
                "approve_final_result",
                "reject_final_result",
            )
        )
    ):
        raise ValueError("command source does not provide the local mutation contract")

    def json_response(value: object, status_code: int = 200) -> Response:
        return Response(
            canonical_json_bytes(value),
            status_code=status_code,
            media_type="application/json",
        )

    def remember(value: MissionControlSnapshot) -> MissionControlSnapshot:
        with snapshots_lock:
            snapshots[value.cursor] = value
            snapshots.move_to_end(value.cursor)
            while len(snapshots) > 256:
                snapshots.popitem(last=False)
        return value

    def checked_snapshot() -> MissionControlSnapshot:
        try:
            value = MissionControlSnapshot.model_validate(source.snapshot(mission_id))
        except ValidationError as error:
            raise MissionProjectionError(
                "committed mission projection failed validation"
            ) from error
        if value.mission.mission_id != mission_id:
            raise MissionProjectionError("projection returned another mission")
        return remember(value)

    def snapshot_for_cursor(cursor: str) -> MissionControlSnapshot:
        decode_cursor(cursor, mission_id)
        with snapshots_lock:
            value = snapshots.get(cursor)
        if value is None and hasattr(source, "snapshot_at_cursor"):
            try:
                value = MissionControlSnapshot.model_validate(
                    source.snapshot_at_cursor(mission_id, cursor)
                )
            except ValidationError as error:
                raise MissionProjectionError(
                    "committed mission projection failed validation"
                ) from error
        if value is None or value.cursor != cursor:
            raise MissionNotFound("mission cursor not found")
        return remember(value)

    def task_value(task_id: str, cursor: str | None) -> MissionTaskDetail:
        value = (
            project_task_detail(snapshot_for_cursor(cursor), task_id)
            if cursor
            else source.task_detail(mission_id, task_id)
        )
        try:
            return MissionTaskDetail.model_validate(value)
        except ValidationError as error:
            raise MissionProjectionError(
                "committed mission task projection failed validation"
            ) from error

    def evidence_value(attempt_id: str, cursor: str | None) -> GenericAttemptEvidence:
        value = (
            project_attempt_evidence(snapshot_for_cursor(cursor), attempt_id)
            if cursor
            else source.attempt_evidence(mission_id, attempt_id)
        )
        try:
            return GenericAttemptEvidence.model_validate(value)
        except ValidationError as error:
            raise MissionProjectionError(
                "committed attempt evidence projection failed validation"
            ) from error

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def authorized(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {read_token}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=401, detail="Mission Control authorization required"
            )

    def authorize_command(request: Request, *, csrf: bool) -> None:
        if command_token is None or command_store is None:
            raise HTTPException(status_code=404)
        if request.headers.get("origin") != command_origin:
            raise HTTPException(status_code=403, detail="Command origin rejected")
        supplied = request.headers.get("authorization")
        if supplied is None or not secrets.compare_digest(
            supplied, f"Bearer {command_token}"
        ):
            raise HTTPException(
                status_code=401, detail="Command authorization required"
            )
        if not csrf:
            return
        session_id = request.cookies.get("graphene_command_session")
        supplied_csrf = request.headers.get("x-csrf-token")
        with command_lock:
            session = command_sessions.get(session_id or "")
            if session is not None and session[1] <= datetime.now(UTC):
                command_sessions.pop(session_id or "", None)
                session = None
            if session is not None:
                command_sessions.move_to_end(session_id or "")
        if (
            session is None
            or supplied_csrf is None
            or not secrets.compare_digest(supplied_csrf, session[0])
        ):
            raise HTTPException(status_code=403, detail="Command session rejected")

    def expected_confirmation(value: _CommandEnvelope) -> str:
        if value.action == "decide_gate":
            return f"{value.action}:{value.target_id}:{value.decision}"
        if value.action in {"approve_final", "reject_final"}:
            return f"{value.action}:{value.target_id}:{value.expected_bundle_id}"
        if value.action == "supply_input":
            return f"{value.action}:{value.target_id}:{value.gate_id}"
        return f"{value.action}:{value.target_id}"

    def target_is_current(
        value: _CommandEnvelope, current: MissionControlSnapshot
    ) -> bool:
        if value.expected_head.mission_id != mission_id:
            return False
        if value.action in {"pause", "resume", "cancel", "request_replan"}:
            allowed = {
                "pause": {"running"},
                "resume": {"paused"},
                "request_replan": {"running", "paused"},
                "cancel": {"proposed", "running", "paused", "awaiting_result"},
            }
            return (
                value.target_id == mission_id
                and current.mission.status in allowed[value.action]
                and (value.action != "cancel" or cancel_coordinator is not None)
                and not (
                    value.action == "cancel"
                    and current.mission.outcome == "approved_pending_commit"
                )
            )
        if value.action in {"approve_plan", "reject_plan"}:
            return (
                current.mission.status == "proposed"
                and value.target_id == f"plan:{value.expected_plan_revision}"
                and value.expected_plan_revision == current.mission.plan_revision
            )
        if value.action == "retry_task":
            return any(
                task.task_id == value.target_id and task.state == "failed"
                for task in current.tasks
            )
        if value.action == "supply_input":
            task = next(
                (task for task in current.tasks if task.task_id == value.target_id),
                None,
            )
            return (
                input_coordinator is not None
                and task is not None
                and task.state == "needs_input"
                and task.blocker_reason == f"input:{value.gate_id}"
                and any(
                    gate.gate_id == value.gate_id
                    and gate.task_id == value.target_id
                    and gate.status == "decided"
                    for gate in current.gates
                )
            )
        if value.action == "decide_gate":
            return any(
                gate.gate_id == value.target_id
                and gate.status == "pending"
                and any(option.value == value.decision for option in gate.options)
                for gate in current.gates
            )
        binding = _projected_final_result_binding(current)
        if binding is None:
            return False
        _candidate_publication, _candidate_proof, _, _, _bundle_proof = binding
        result_state_allowed = (
            current.result.state == "awaiting_decision"
            if value.action == "reject_final"
            else current.result.state in {"awaiting_decision", "approved"}
        )
        return (
            value.target_id == f"result:{mission_id}"
            and current.mission.status == "awaiting_result"
            and result_state_allowed
            and current.result.bundle_id == value.expected_bundle_id
        )

    def run_command(value: _CommandEnvelope, expected_head: MissionHead) -> Any:
        common = {
            "expected_head": expected_head,
            "operator_label": operator_label,
            "rationale": value.rationale,
            "truth_kind": TruthKind.HUMAN_ATTESTED,
            "recorded_at": datetime.now(UTC),
        }
        if value.action == "pause":
            return command_store.pause(mission_id, value.command_id, **common)
        if value.action == "resume":
            return command_store.resume(mission_id, value.command_id, **common)
        if value.action == "cancel":
            if cancel_coordinator is None:
                raise MissionConflict(
                    "mission cancellation cleanup coordinator is unavailable"
                )
            try:
                return cancel_coordinator(
                    mission_id=mission_id,
                    command_id=value.command_id,
                    **common,
                )
            except (MissionConflict, MissionStoreError):
                raise
            except Exception as error:
                raise MissionConflict(
                    "mission cancellation cleanup coordinator failed"
                ) from error
        if value.action == "request_replan":
            return command_store.request_replan(
                mission_id,
                value.command_id,
                reason=value.rationale
                or "Plan revision requested in authenticated Mission Control.",
                expected_head=expected_head,
                operator_label=operator_label,
                truth_kind=TruthKind.HUMAN_ATTESTED,
                recorded_at=common["recorded_at"],
            )
        if value.action == "retry_task":
            return command_store.retry_task(
                mission_id, value.target_id, value.command_id, **common
            )
        if value.action == "supply_input":
            if input_coordinator is None:
                raise MissionConflict("private input coordinator is unavailable")
            current_head = command_store.head(mission_id)
            if (
                current_head.seq != expected_head.seq
                or current_head.event_sha256 != expected_head.event_sha256
            ):
                raise MissionConflict("mission head changed before private input write")
            try:
                return input_coordinator(
                    mission_id=mission_id,
                    task_id=value.target_id,
                    gate_id=value.gate_id,
                    input_bytes=value.input_text.encode("utf-8"),
                    command_id=value.command_id,
                    **common,
                )
            except (MissionConflict, MissionStoreError):
                raise
            except Exception as error:
                raise MissionConflict("private input coordinator failed") from error
        if value.action == "approve_plan":
            return command_store.approve_plan(
                mission_id,
                value.command_id,
                expected_revision=value.expected_plan_revision,
                **common,
            )
        if value.action == "reject_plan":
            if common["rationale"] is None:
                common["rationale"] = "Plan rejected in authenticated Mission Control."
            return command_store.reject_plan(
                mission_id,
                value.command_id,
                expected_revision=value.expected_plan_revision,
                **common,
            )
        if value.action == "decide_gate":
            return command_store.decide_gate(
                mission_id,
                value.target_id,
                value.decision,
                value.command_id,
                **common,
            )
        head, _receipt = finalize_local_result_decision(
            store=command_store,
            mission_id=mission_id,
            command_id=value.command_id,
            expected_head=expected_head,
            expected_bundle_id=value.expected_bundle_id,
            operator_label=operator_label,
            rationale=value.rationale,
            truth_kind=TruthKind.HUMAN_ATTESTED,
            recorded_at=common["recorded_at"],
            approved=value.action == "approve_final",
        )
        return head

    @app.exception_handler(RequestValidationError)
    async def invalid_request(
        _request: Request, _error: RequestValidationError
    ) -> Response:
        return json_response(
            {"code": "INVALID_COMMAND", "detail": "Request envelope is invalid."},
            422,
        )

    @app.post("/api/mission-control/missions/{requested_mission_id}/commands/session")
    def command_session(request: Request, requested_mission_id: str) -> Response:
        if requested_mission_id != mission_id:
            return Response(status_code=404)
        authorize_command(request, csrf=False)
        session_id, csrf_token = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        with command_lock:
            command_sessions[session_id] = (
                csrf_token,
                datetime.now(UTC) + timedelta(hours=1),
            )
            while len(command_sessions) > 128:
                command_sessions.popitem(last=False)
        response = json_response(
            {"csrf_token": csrf_token, "operator_label": operator_label}
        )
        response.set_cookie(
            "graphene_command_session",
            session_id,
            httponly=True,
            secure=bool(command_origin and command_origin.startswith("https://")),
            samesite="strict",
            max_age=3600,
            path=f"/api/mission-control/missions/{mission_id}/commands",
        )
        return response

    @app.post("/api/mission-control/missions/{requested_mission_id}/commands")
    def command(
        request: Request,
        requested_mission_id: str,
        value: _CommandEnvelope,
    ) -> Response:
        if requested_mission_id != mission_id:
            return Response(status_code=404)
        authorize_command(request, csrf=True)
        request_bytes = sha256_hex(
            canonical_json_bytes(value.model_dump(mode="json"))
        ).encode()
        with command_lock:
            cached = command_results.get(value.command_id)
            if cached is not None:
                if cached[0] != request_bytes:
                    return json_response(
                        {
                            "code": "IDEMPOTENCY_CONFLICT",
                            "detail": "Command ID was already used for another request.",
                        },
                        409,
                    )
                return Response(cached[1], media_type="application/json")
            current = checked_snapshot()
            expected = value.expected_head
            projection_matches_expected = (
                current.head.seq == expected.seq
                and current.head.event_sha256 == expected.event_sha256
            )
            if projection_matches_expected and not target_is_current(value, current):
                return json_response(
                    {
                        "code": "TARGET_STALE",
                        "detail": "Command target is unavailable.",
                    },
                    409,
                )
            if not secrets.compare_digest(
                value.confirmation, expected_confirmation(value)
            ):
                return json_response(
                    {
                        "code": "CONFIRMATION_REQUIRED",
                        "detail": "Type the exact confirmation shown by Mission Control.",
                    },
                    409,
                )
            atomic_head = MissionHead(
                mission_id=expected.mission_id,
                seq=expected.seq,
                event_sha256=expected.event_sha256,
                event_count=expected.seq,
            )
            try:
                head = run_command(value, atomic_head)
            except LocalResultRecoveryRequired:
                try:
                    store_head = command_store.head(mission_id)
                except MissionStoreError:
                    store_head = None
                response = {
                    "code": "FINALIZATION_INCOMPLETE",
                    "detail": (
                        "Final approval is committed. Retry this confirmation to "
                        "finish the verified isolated local commit."
                    ),
                }
                if store_head is not None:
                    response["current_head"] = {
                        "mission_id": mission_id,
                        "seq": store_head.seq,
                        "event_sha256": store_head.event_sha256,
                    }
                return json_response(response, 409)
            except LocalResultError:
                return json_response(
                    {
                        "code": "MISSION_EVIDENCE_INVALID",
                        "detail": "Committed final-result evidence is invalid.",
                    },
                    409,
                )
            except (MissionConflict, MissionStoreError, ValueError) as error:
                if isinstance(error, MissionConflict) and str(error) == (
                    "mission command id was reused with another request"
                ):
                    return json_response(
                        {
                            "code": "IDEMPOTENCY_CONFLICT",
                            "detail": "Command ID was already used for another request.",
                        },
                        409,
                    )
                try:
                    store_head = command_store.head(mission_id)
                except MissionStoreError:
                    store_head = None
                if store_head is not None and (
                    store_head.seq != expected.seq
                    or store_head.event_sha256 != expected.event_sha256
                ):
                    return json_response(
                        {
                            "code": "MISSION_HEAD_STALE",
                            "detail": "Refresh the mission and confirm the command again.",
                            "current_head": {
                                "mission_id": mission_id,
                                "seq": store_head.seq,
                                "event_sha256": store_head.event_sha256,
                            },
                        },
                        409,
                    )
                if isinstance(error, MissionStoreError) and not isinstance(
                    error, MissionConflict
                ):
                    return json_response(
                        {
                            "code": "MISSION_EVIDENCE_INVALID",
                            "detail": "Committed mission evidence is invalid.",
                        },
                        409,
                    )
                return json_response(
                    {
                        "code": "COMMAND_REJECTED",
                        "detail": "The committed state does not allow this command.",
                    },
                    409,
                )
            response_bytes = canonical_json_bytes(
                {
                    "action": value.action,
                    "head": {
                        "mission_id": mission_id,
                        "seq": head.seq,
                        "event_sha256": head.event_sha256,
                    },
                    "status": "accepted",
                }
            )
            command_results[value.command_id] = (request_bytes, response_bytes)
            while len(command_results) > 512:
                command_results.popitem(last=False)
            return Response(response_bytes, media_type="application/json")

    @app.exception_handler(MissionNotFound)
    async def not_found(_request: Request, _error: MissionNotFound) -> Response:
        return Response(status_code=404)

    @app.exception_handler(MissionProjectionError)
    async def invalid_projection(
        _request: Request, _error: MissionProjectionError
    ) -> Response:
        return Response(
            canonical_json_bytes(
                {
                    "code": "MISSION_EVIDENCE_INVALID",
                    "detail": "Committed mission evidence is invalid.",
                }
            ),
            status_code=409,
            media_type="application/json",
        )

    @app.api_route(
        "/api/mission-control/health",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    def health(request: Request) -> Response:
        current = checked_snapshot()
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(
                {
                    "status": "ok",
                    "mode": mode_label,
                    "read_only": command_token is None,
                    "authoritative_writes": command_token is not None,
                    "replay": replay,
                    "live_agent": False if replay else None,
                    "human_attestation": False if replay else None,
                    "new_test_execution": False if replay else None,
                    "gemini_calls": 0 if replay else None,
                    "cloud_proof": False if replay else None,
                    "mission_id": mission_id,
                    "head_seq": current.head.seq,
                    "head_sha256": current.head.event_sha256,
                }
            )
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/mission-control/missions/{requested_mission_id}/snapshot",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    def snapshot(request: Request, requested_mission_id: str) -> Response:
        if requested_mission_id != mission_id:
            return Response(status_code=404)
        value = checked_snapshot()
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(value.model_dump(mode="json"))
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/mission-control/missions/{requested_mission_id}/tasks/{task_id}",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    def task_detail(
        request: Request,
        requested_mission_id: str,
        task_id: str,
        cursor: str | None = Query(default=None, max_length=8_192),
    ) -> Response:
        if requested_mission_id != mission_id or len(task_id) > 128:
            return Response(status_code=404)
        value = task_value(task_id, cursor)
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(value.model_dump(mode="json"))
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/mission-control/missions/{requested_mission_id}/attempts/{attempt_id}/evidence",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    def attempt_evidence(
        request: Request,
        requested_mission_id: str,
        attempt_id: str,
        cursor: str | None = Query(default=None, max_length=8_192),
    ) -> Response:
        if requested_mission_id != mission_id or len(attempt_id) > 128:
            return Response(status_code=404)
        value = evidence_value(attempt_id, cursor)
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(value.model_dump(mode="json"))
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/mission-control/missions/{requested_mission_id}/replay",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    def replay_document(request: Request, requested_mission_id: str) -> Response:
        value = getattr(source, "replay", None)
        if not replay or requested_mission_id != mission_id or value is None:
            return Response(status_code=404)
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(
                {
                    "meta": value.meta,
                    "snapshot": value.snapshot.model_dump(mode="json"),
                    "deltas": value.deltas,
                }
            )
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/mission-control/missions/{requested_mission_id}/stream",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def stream(
        request: Request,
        requested_mission_id: str,
        cursor: str | None = Query(default=None, max_length=8_192),
    ) -> Response:
        if requested_mission_id != mission_id:
            return Response(status_code=404)
        current = await asyncio.to_thread(checked_snapshot)
        previous: MissionControlSnapshot | None = None
        if cursor:
            try:
                previous = await asyncio.to_thread(snapshot_for_cursor, cursor)
            except MissionNotFound:
                return Response(
                    canonical_json_bytes(
                        {
                            "code": "MISSION_CURSOR_EXPIRED",
                            "detail": "Fetch a fresh committed mission snapshot.",
                        }
                    ),
                    status_code=409,
                    media_type="application/json",
                )
        if request.method == "HEAD":
            return Response(media_type="application/x-ndjson")

        def delta_envelope(
            before: MissionControlSnapshot, after: MissionControlSnapshot
        ) -> bytes:
            return (
                canonical_json_bytes(
                    {
                        "type": "delta",
                        "cursor": after.cursor,
                        "delta": diff_snapshots(before, after).model_dump(mode="json"),
                    }
                )
                + b"\n"
            )

        async def events():
            nonlocal current, previous
            if previous is None:
                yield (
                    canonical_json_bytes(
                        {
                            "type": "reset",
                            "cursor": current.cursor,
                            "snapshot": current.model_dump(mode="json"),
                        }
                    )
                    + b"\n"
                )
                previous = current
            elif previous.snapshot_sha256 != current.snapshot_sha256:
                yield delta_envelope(previous, current)
                previous = current
            heartbeat = time.monotonic()
            try:
                while not await request.is_disconnected():
                    await asyncio.sleep(stream_interval_seconds)
                    latest = await asyncio.to_thread(checked_snapshot)
                    if latest.snapshot_sha256 != previous.snapshot_sha256:
                        yield delta_envelope(previous, latest)
                        previous = latest
                        heartbeat = time.monotonic()
                    elif time.monotonic() - heartbeat >= 1:
                        yield (
                            canonical_json_bytes(
                                {
                                    "type": "heartbeat",
                                    "cursor": previous.cursor,
                                    "head_seq": previous.head.seq,
                                }
                            )
                            + b"\n"
                        )
                        heartbeat = time.monotonic()
            except (MissionNotFound, MissionProjectionError) as error:
                yield (
                    canonical_json_bytes(
                        {"type": "MISSION_EVIDENCE_INVALID", "detail": str(error)}
                    )
                    + b"\n"
                )

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/mission-control/{requested_mission_id}", response_class=HTMLResponse)
    def mission_page(requested_mission_id: str) -> HTMLResponse:
        if requested_mission_id != mission_id:
            raise HTTPException(status_code=404)
        index = STATIC_DIR / "mission_control.html"
        html = (
            index.read_text()
            if index.is_file()
            else "<!doctype html><html><head></head><body><main>Mission Control assets are unavailable.</main></body></html>"
        )
        bootstrap = _safe_script_json(
            {
                "missionId": mission_id,
                "mode": mode_label,
                "truthLabel": truth_label,
                "replay": replay,
                "commandsEnabled": command_token is not None,
                "inputEnabled": input_coordinator is not None,
                "cancelEnabled": cancel_coordinator is not None,
            }
        )
        nonce = secrets.token_urlsafe(18)
        script = f'<script nonce="{nonce}">window.__GRAPHENE_MISSION_CONTROL__={bootstrap};</script>'
        html = (
            html.replace("</head>", f"{script}</head>", 1)
            if "</head>" in html
            else script + html
        )
        return HTMLResponse(
            html,
            headers={
                "Content-Security-Policy": (
                    f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
                    "style-src 'self'; connect-src 'self'; img-src 'self' data:; "
                    "object-src 'none'; base-uri 'none'; form-action 'none'; "
                    "frame-ancestors 'none'"
                )
            },
        )

    @app.api_route(
        "/mission-static/{asset_name}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    def mission_asset(request: Request, asset_name: str) -> Response:
        media_type = _UI_ASSETS.get(asset_name)
        if media_type is None:
            return Response(status_code=404)
        path = STATIC_DIR / asset_name
        if not path.is_file():
            return Response(status_code=404)
        return Response(
            b"" if request.method == "HEAD" else path.read_bytes(),
            media_type=media_type,
        )

    app.mount(
        "/mission-vendor",
        StaticFiles(directory=VENDOR_DIR, check_dir=False),
        name="mission-vendor",
    )
    return app
