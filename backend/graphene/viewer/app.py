from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..hashing import canonical_json_bytes
from .contract import GraphSnapshot
from .projection import (
    ViewerEvidenceInvalid,
    ViewerRunNotFound,
    build_snapshot,
    current_node_id,
    database_identity,
    diff_snapshots,
    snapshot_at_cursor,
)

STATIC_DIR = Path(__file__).with_name("static")


def _safe_script_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def create_viewer_app(
    database_path: str | Path,
    root_run_id: str,
    read_token: str,
    mode_label: str,
    driver: str | None = None,
) -> FastAPI:
    path = Path(database_path)
    if not read_token or len(read_token) > 512:
        raise ValueError("read_token must be nonempty and bounded")
    identity = database_identity(path)
    app = FastAPI(title="Graphene v2 Viewer", version="1", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def authorized(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {read_token}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="viewer authorization required")

    def checked_snapshot() -> GraphSnapshot:
        try:
            if database_identity(path) != identity:
                raise ViewerEvidenceInvalid("lineage database was replaced")
            snapshot = build_snapshot(path, root_run_id)
            if database_identity(path) != identity:
                raise ViewerEvidenceInvalid("lineage database was replaced")
            return snapshot
        except OSError as error:
            raise ViewerEvidenceInvalid("lineage database identity is unavailable") from error

    @app.exception_handler(ViewerEvidenceInvalid)
    async def invalid_evidence(_request: Request, error: ViewerEvidenceInvalid) -> Response:
        return Response(
            canonical_json_bytes({"code": "EVIDENCE_INVALID", "detail": str(error)}),
            status_code=409,
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(ViewerRunNotFound)
    async def missing_run(_request: Request, _error: ViewerRunNotFound) -> Response:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})

    @app.api_route("/api/viewer/health", methods=["GET", "HEAD"], dependencies=[Depends(authorized)])
    async def health(request: Request) -> Response:
        snapshot = checked_snapshot()
        body = b"" if request.method == "HEAD" else canonical_json_bytes(
            {
                "status": "ok",
                "mode": mode_label,
                "read_only": True,
                "root_run_id": root_run_id,
                "verified_heads": len(snapshot.heads),
            }
        )
        return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})

    @app.api_route(
        "/api/viewer/runs/{requested_run_id}/snapshot",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def snapshot(request: Request, requested_run_id: str) -> Response:
        if requested_run_id != root_run_id:
            return Response(status_code=404)
        value = checked_snapshot()
        body = b"" if request.method == "HEAD" else canonical_json_bytes(value.model_dump(mode="json"))
        return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})

    @app.api_route(
        "/api/viewer/runs/{requested_run_id}/nodes/{node_id:path}",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def node_detail(request: Request, requested_run_id: str, node_id: str) -> Response:
        if requested_run_id != root_run_id or len(node_id) > 400:
            return Response(status_code=404)
        node = next((item for item in checked_snapshot().nodes if item.id == node_id), None)
        if node is None:
            return Response(status_code=404)
        body = b"" if request.method == "HEAD" else canonical_json_bytes(node.model_dump(mode="json"))
        return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})

    @app.api_route(
        "/api/viewer/runs/{requested_run_id}/stream",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def stream(
        request: Request,
        requested_run_id: str,
        cursor: str | None = Query(default=None, max_length=8_192),
    ) -> Response:
        if requested_run_id != root_run_id:
            return Response(status_code=404)
        current = checked_snapshot()
        previous = snapshot_at_cursor(path, root_run_id, cursor) if cursor else None
        if request.method == "HEAD":
            return Response(media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})

        def update_envelope(before: GraphSnapshot, after: GraphSnapshot) -> dict[str, object]:
            deltas = diff_snapshots(before, after)
            if len(deltas) == 1 and deltas[0].op == "reset":
                return {
                    "type": "reset",
                    "cursor": after.cursor,
                    "current_id": current_node_id(after),
                    "snapshot": after.model_dump(mode="json"),
                }
            return {
                "type": "delta",
                "cursor": after.cursor,
                "current_id": current_node_id(after),
                "deltas": [delta.model_dump(mode="json") for delta in deltas],
                "heads": [head.model_dump(mode="json") for head in after.heads],
                "graph_sha256": after.graph_sha256,
                "omitted_counts": after.omitted_counts,
                "unknowns": after.unknowns,
                "review_brief": after.review_brief.model_dump(mode="json") if after.review_brief else None,
                "support_paths": [item.model_dump(mode="json") for item in after.support_paths or ()],
            }

        async def events():
            nonlocal current, previous
            try:
                if previous is None:
                    yield canonical_json_bytes(
                        {
                            "type": "reset",
                            "cursor": current.cursor,
                            "current_id": current_node_id(current),
                            "snapshot": current.model_dump(mode="json"),
                        }
                    ) + b"\n"
                elif previous.graph_sha256 != current.graph_sha256:
                    yield canonical_json_bytes(update_envelope(previous, current)) + b"\n"
                previous = current
                while not await request.is_disconnected():
                    await asyncio.sleep(0.1)
                    snapshot_at_cursor(path, root_run_id, previous.cursor)
                    latest = checked_snapshot()
                    if latest.graph_sha256 == previous.graph_sha256:
                        continue
                    yield canonical_json_bytes(update_envelope(previous, latest)) + b"\n"
                    previous = latest
            except (ViewerEvidenceInvalid, ViewerRunNotFound) as error:
                yield canonical_json_bytes({"type": "EVIDENCE_INVALID", "detail": str(error)}) + b"\n"

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/viewer/{requested_run_id}", response_class=HTMLResponse)
    async def viewer(requested_run_id: str) -> HTMLResponse:
        if requested_run_id != root_run_id:
            raise HTTPException(status_code=404)
        index = STATIC_DIR / "index.html"
        html = index.read_text() if index.is_file() else "<!doctype html><html><head></head><body><main id=app>Graphene viewer assets are unavailable.</main></body></html>"
        bootstrap = _safe_script_json(
            {"rootRunId": root_run_id, "token": read_token, "driver": driver, "mode": mode_label}
        )
        nonce = secrets.token_urlsafe(18)
        script = f'<script nonce="{nonce}">window.__GRAPHENE_VIEWER__={bootstrap};</script>'
        html = html.replace("</head>", f"{script}</head>", 1) if "</head>" in html else script + html
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self'; style-src-attr 'unsafe-inline'; connect-src 'self'; img-src 'self' data:",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="viewer-static")
    return app
