from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from .contract import GraphDelta, GraphSnapshot
from .viewer_projection import ViewerEvidenceInvalid, apply_deltas


STATIC_DIR = Path(__file__).with_name("static")
DEFAULT_REPLAY_PATH = STATIC_DIR / "replay.json"
REPLAY_TRUTH_LABEL = (
    "VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION"
)
_FORBIDDEN = (
    b'"human_attested"',
    b'"prompt"',
    b'"raw_source"',
    b'"stderr"',
    b'"stdout"',
    b'"unified_diff"',
    b"/private/",
    b"sk-",
)


class ReplayEvidenceInvalid(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedReplay:
    root_run_id: str
    snapshot: GraphSnapshot
    deltas: tuple[dict[str, object], ...]
    stages: tuple[GraphSnapshot, ...]
    meta: dict[str, object]


def _safe_script_json(value: object) -> str:
    return (
        json.dumps(value, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def apply_replay_envelope(
    before: GraphSnapshot, envelope: dict[str, object]
) -> GraphSnapshot:
    if envelope.get("type") == "reset":
        stage = GraphSnapshot.model_validate(envelope["snapshot"])
    elif envelope.get("type") == "delta":
        stage = apply_deltas(
            before,
            tuple(GraphDelta.model_validate(item) for item in envelope["deltas"]),
            cursor=str(envelope["cursor"]),
            heads=envelope["heads"],
            graph_sha256=str(envelope["graph_sha256"]),
            omitted_counts=envelope["omitted_counts"],
            unknowns=envelope["unknowns"],
            review_brief=envelope["review_brief"],
            support_paths=envelope["support_paths"],
        )
    else:
        raise ValueError("replay envelope type is invalid")
    if envelope.get("cursor") != stage.cursor or envelope.get("current_id") not in {
        node.id for node in stage.nodes
    }:
        raise ValueError("replay envelope cursor or current node is invalid")
    return stage


def load_verified_replay(path: str | Path = DEFAULT_REPLAY_PATH) -> VerifiedReplay:
    replay_path = Path(path)
    try:
        raw = replay_path.read_bytes()
        expected = replay_path.with_suffix(".sha256").read_text().strip()
        payload = json.loads(raw)
        if raw != canonical_json_bytes(payload) + b"\n" or sha256_hex(raw) != expected:
            raise ValueError("replay bytes do not match their checked-in digest")
        if any(value in raw.lower() for value in _FORBIDDEN):
            raise ValueError("replay contains data outside the public-safe contract")
        snapshot = GraphSnapshot.model_validate(payload["snapshot"])
        deltas = tuple(payload["deltas"])
        stages = [snapshot]
        for item in deltas:
            stages.append(apply_replay_envelope(stages[-1], item))
        verified_stages = tuple(stages)
        meta = dict(payload["meta"])
        if (
            meta.get("mode") != REPLAY_TRUTH_LABEL
            or meta.get("truth_label") != REPLAY_TRUTH_LABEL
            or meta.get("driver") != "verified-replay"
            or meta.get("gemini_calls") != 0
            or meta.get("source_heads")
            != verified_stages[-1].model_dump(mode="json")["heads"]
            or meta.get("final_graph_sha256") != verified_stages[-1].graph_sha256
            or any(
                canonical_json_sha256(
                    stage.model_dump(mode="json", exclude={"cursor", "graph_sha256"})
                )
                != stage.graph_sha256
                for stage in verified_stages
            )
        ):
            raise ValueError("replay contract or truth labels are invalid")
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
        ViewerEvidenceInvalid,
    ) as error:
        raise ReplayEvidenceInvalid("checked-in replay evidence is invalid") from error
    return VerifiedReplay(snapshot.root_run_id, snapshot, deltas, verified_stages, meta)


def create_verified_replay_app(
    read_token: str,
    replay: VerifiedReplay | None = None,
    *,
    stream_interval_seconds: float = 0.35,
) -> FastAPI:
    if not read_token or len(read_token) > 512:
        raise ValueError("read_token must be nonempty and bounded")
    if not 0 <= stream_interval_seconds <= 10:
        raise ValueError("stream_interval_seconds must be between zero and ten")
    replay = replay or load_verified_replay()
    root_run_id = replay.root_run_id
    cursors = {stage.cursor: index for index, stage in enumerate(replay.stages)}
    final_nodes = {node.id: node for node in replay.stages[-1].nodes}
    app = FastAPI(
        title="Graphene Verified Replay Viewer",
        version="1",
        docs_url=None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def authorized(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {read_token}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="viewer authorization required")

    @app.api_route(
        "/api/viewer/health",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def health(request: Request) -> Response:
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(
                {
                    "status": "ok",
                    "mode": REPLAY_TRUTH_LABEL,
                    "read_only": True,
                    "authoritative_writes": False,
                    "human_attestation": False,
                    "live_agent": False,
                    "new_test_execution": False,
                    "root_run_id": root_run_id,
                }
            )
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/viewer/runs/{requested_run_id}/snapshot",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def snapshot(request: Request, requested_run_id: str) -> Response:
        if requested_run_id != root_run_id:
            return Response(status_code=404)
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(replay.snapshot.model_dump(mode="json"))
        )
        return Response(body, media_type="application/json")

    @app.api_route(
        "/api/viewer/runs/{requested_run_id}/nodes/{node_id:path}",
        methods=["GET", "HEAD"],
        dependencies=[Depends(authorized)],
    )
    async def node_detail(
        request: Request, requested_run_id: str, node_id: str
    ) -> Response:
        if requested_run_id != root_run_id or node_id not in final_nodes:
            return Response(status_code=404)
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(final_nodes[node_id].model_dump(mode="json"))
        )
        return Response(body, media_type="application/json")

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
        if cursor not in cursors:
            return Response(
                canonical_json_bytes(
                    {"code": "EVIDENCE_INVALID", "detail": "replay cursor is invalid"}
                ),
                status_code=409,
                media_type="application/json",
            )
        if request.method == "HEAD":
            return Response(media_type="application/x-ndjson")

        async def events():
            yield b"\n"
            for item in replay.deltas[cursors[cursor] :]:
                if stream_interval_seconds:
                    await asyncio.sleep(stream_interval_seconds)
                yield canonical_json_bytes(item) + b"\n"
            while not await request.is_disconnected():
                await asyncio.sleep(0.25)
                yield b"\n"

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/viewer/{requested_run_id}", response_class=HTMLResponse)
    async def viewer(requested_run_id: str) -> HTMLResponse:
        if requested_run_id != root_run_id:
            raise HTTPException(status_code=404)
        html = (STATIC_DIR / "index.html").read_text()
        bootstrap = _safe_script_json(
            {
                "rootRunId": root_run_id,
                "token": read_token,
                "driver": "verified-replay",
                "mode": REPLAY_TRUTH_LABEL,
                "truthLabel": REPLAY_TRUTH_LABEL,
                "evidenceSource": REPLAY_TRUTH_LABEL,
                "adkRunner": "not used",
                "geminiCalls": 0,
                "replay": True,
            }
        )
        nonce = secrets.token_urlsafe(18)
        script = (
            f'<script nonce="{nonce}">window.__GRAPHENE_VIEWER__={bootstrap};</script>'
        )
        html = (
            html.replace(">LOCAL VIEWER<", f">{REPLAY_TRUTH_LABEL}<", 1)
            .replace(
                ">Committed and verified v2 SQLite lineage<",
                f">{REPLAY_TRUTH_LABEL}<",
                1,
            )
            .replace("</head>", f"{script}</head>", 1)
        )
        return HTMLResponse(
            html,
            headers={
                "Content-Security-Policy": (
                    f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
                    "style-src 'self'; style-src-attr 'unsafe-inline'; connect-src 'self'; "
                    "img-src 'self' data:"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    app.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR, check_dir=False),
        name="viewer-static",
    )
    return app
