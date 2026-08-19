from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from ..hashing import canonical_json_bytes
from ..viewer.app import STATIC_DIR as LEGACY_VIEWER_STATIC_DIR
from .projection import (
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

STATIC_DIR = Path(__file__).with_name("static")
VENDOR_DIR = LEGACY_VIEWER_STATIC_DIR / "vendor"
_READ_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,512}$")
_UI_ASSETS = {
    "mission_control.css": "text/css",
    "mission_control.html": "text/html",
    "mission_control.mjs": "text/javascript",
    "mission_reducer.mjs": "text/javascript",
}


def _safe_script_json(value: object) -> str:
    return (
        json.dumps(value, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def create_mission_control_app(
    source: Any,
    mission_id: str,
    read_token: str,
    mode_label: str,
    *,
    replay: bool = False,
    truth_label: str = "COMMITTED MISSION PROJECTION",
    stream_interval_seconds: float = 1.0,
) -> FastAPI:
    """Create a read-only Mission Control over a MissionProjection-like source."""

    if not mission_id or len(mission_id) > 128:
        raise ValueError("mission_id must be nonempty and bounded")
    if _READ_TOKEN.fullmatch(read_token) is None:
        raise ValueError("read_token must be 16-512 URL-safe characters")
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

    def evidence_value(
        attempt_id: str, cursor: str | None
    ) -> GenericAttemptEvidence:
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

    @app.exception_handler(MissionNotFound)
    async def not_found(_request: Request, _error: MissionNotFound) -> Response:
        return Response(status_code=404)

    @app.exception_handler(MissionProjectionError)
    async def invalid_projection(
        _request: Request, error: MissionProjectionError
    ) -> Response:
        return Response(
            canonical_json_bytes(
                {"code": "MISSION_EVIDENCE_INVALID", "detail": str(error)}
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
                    "read_only": True,
                    "authoritative_writes": False,
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
    def replay_document(
        request: Request, requested_mission_id: str
    ) -> Response:
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
            return canonical_json_bytes(
                {
                    "type": "delta",
                    "cursor": after.cursor,
                    "delta": diff_snapshots(before, after).model_dump(mode="json"),
                }
            ) + b"\n"

        async def events():
            nonlocal current, previous
            if previous is None:
                yield canonical_json_bytes(
                    {
                        "type": "reset",
                        "cursor": current.cursor,
                        "snapshot": current.model_dump(mode="json"),
                    }
                ) + b"\n"
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
                        yield canonical_json_bytes(
                            {
                                "type": "heartbeat",
                                "cursor": previous.cursor,
                                "head_seq": previous.head.seq,
                            }
                        ) + b"\n"
                        heartbeat = time.monotonic()
            except (MissionNotFound, MissionProjectionError) as error:
                yield canonical_json_bytes(
                    {"type": "MISSION_EVIDENCE_INVALID", "detail": str(error)}
                ) + b"\n"

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get(
        "/mission-control/{requested_mission_id}", response_class=HTMLResponse
    )
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
