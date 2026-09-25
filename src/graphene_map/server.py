"""`graphene ui`: the plan and the map, served to this machine only, or written out as one file.

A stdlib HTTP server bound to 127.0.0.1 on a free port. It serves the built page from ``ui/static``,
the JSON the page draws, and the plan edits the person makes on it. A request whose ``Host`` or
``Origin`` is not this server's own address is refused, so a web page open elsewhere in the browser
cannot read the store through it; a write must also carry an ``Origin`` (never merely leave it out)
and the token this launch made, which the page is handed in the payload and which never goes into an
export. Writing at all is the person's: ``writable`` is false when ``graphene ui`` was started from
inside an agent's shell, and the page then says so. The hook never talks to this process. The export
is the same page with its script, its stylesheet and the data inlined: it fetches nothing.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import plan as P
from .commits import refresh_commits
from .graph import build_graph, to_json
from .plan_view import build_plan_view
from .sources.claude_code import backfill
from .store import Store

STATIC = Path(__file__).parent / "ui" / "static"
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
}
DATA_TAG = '<script id="graphene-data" type="application/json">'
BODY_CAP = 256 * 1024  # a plan edit is a handful of fields; anything larger is not one
BUSY = b"the plan's store is busy: another Graphene command is writing to it. Try that again\n"
READ_ONLY = (
    b"this page is read-only: `graphene ui` was started from inside an agent's shell, and the plan "
    b"is the person's to change. Ask them, or start the page from their terminal\n"
)

# What the page may ask for, each one a function in plan.py and nothing else. The page never decides
# whether an edit is allowed: plan.py refuses, and its sentence is what the person reads.
OPS = {
    "add": lambda store, root, body, who: P.propose(store, [body], who, files=P.tracked(root)),
    "set": lambda store, root, body, who: P.edit(
        store, _id(body), _changes(body), who, files=P.tracked(root)
    ),
    "drop": lambda store, root, body, who: P.drop(store, _id(body), who),
    "accept": lambda store, root, body, who: P.accept(store, _ids(body), who),
    "signoff": lambda store, root, body, who: P.signoff(store, _id(body), who),
    "reopen": lambda store, root, body, who: P.reopen(store, _id(body), who, str(body.get("note") or "")),
    "pause": lambda store, root, body, who: P.set_paused(store, True, who),
    "resume": lambda store, root, body, who: P.set_paused(store, False, who),
    "ack": lambda store, root, body, who: P.acknowledge(store, root, who),
    "archive": lambda store, root, body, who: P.archive(store, who),
}


def _id(body: dict) -> str:
    node_id = str(body.get("id") or "")
    if not node_id:
        raise P.Refused("which node? the page sent an edit with no node id")
    return node_id


def _ids(body: dict) -> list[str]:
    return [str(i) for i in (body.get("ids") or ([body["id"]] if body.get("id") else []))]


def _changes(body: dict) -> dict:
    return {field: body[field] for field in P.EDITABLE if field in body}


def runs(store: Store) -> list[dict]:
    """The rail: sessions that made at least one call, newest first."""
    rows = store.conn.execute(
        """SELECT s.id, s.started_at, s.ended_at, s.source,
                  (SELECT COUNT(*) FROM prompts p WHERE p.session_id = s.id) AS prompts,
                  COUNT(e.id) AS calls, COUNT(DISTINCT e.agent_id) AS agents,
                  COUNT(DISTINCT CASE WHEN e.file_path NOT LIKE '/%' THEN e.file_path END) AS files
           FROM sessions s JOIN tool_events e ON e.session_id = s.id
           GROUP BY s.id ORDER BY s.started_at DESC, s.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def payload(
    store: Store,
    session_ids: list[str],
    only: bool = False,
    token: str | None = None,
    writable: bool = False,
    checkout: Path | None = None,
) -> str:
    """What the page needs in one object: the plan, then the rail and the graph of the chosen
    sessions. ``only`` keeps the rail to those sessions, for a file that leaves the machine, which
    is also the file that carries no token and no right to write."""
    rail = runs(store)
    known = {r["id"] for r in rail}
    ids = [i for i in session_ids if i in known] or [r["id"] for r in rail[:1]]
    rail = [r for r in rail if r["id"] in ids] if only else rail
    plan_view = build_plan_view(store, logs=not only, checkout=checkout) | {
        "writable": writable,
        "token": token,
    }
    return (
        '{"runs": '
        + json.dumps(rail)
        + ', "plan": '
        + json.dumps(plan_view, ensure_ascii=False)
        + ', "graph": '
        + to_json(build_graph(store, ids))
        + "}"
    )


def export_html(store: Store, session_ids: list[str]) -> str:
    """One self-contained file: the built page with its assets and the data inlined. Paths, counts,
    task text and prompts go in; no hunks and no tool output exist in the graph to leak, and the
    plan goes in without its nodes' logs, which can hold the output of a check."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")

    def inline(match: re.Match) -> str:
        text = (STATIC / match.group("src").lstrip("./")).read_text(encoding="utf-8")
        if match.group(0).startswith("<link"):
            return f"<style>{text}</style>"
        return '<script type="module">' + text.replace("</script", "<\\/script") + "</script>"

    page = re.sub(r'<script[^>]*\bsrc="(?P<src>[^"]+)"[^>]*></script>', inline, page)
    page = re.sub(r'<link[^>]*\brel="stylesheet"[^>]*\bhref="(?P<src>[^"]+)"[^>]*>', inline, page)
    data = payload(store, session_ids, only=True).replace("</", "<\\/")
    return page.replace("</head>", f"{DATA_TAG}{data}</script></head>", 1)


def make_server(root: Path, session_ids: list[str], writable: bool = False) -> ThreadingHTTPServer:
    """The page for this repo. ``writable`` is the caller's own right to change the plan: the ``ui``
    command passes whether a person is running it, and an agent's page is served read-only."""
    token = secrets.token_urlsafe(24)  # this launch only: a page from an older run cannot write

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # the terminal belongs to the person, not to an access log
            pass

        def _send(self, code: int, body: bytes, kind: str = "text/plain; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _ours(self, writing: bool = False) -> bool:
            """This machine's own page asking. A read may come without an Origin (a bare fetch from
            the page itself does not send one); a write may not, because a request with no Origin is
            exactly what a page elsewhere in the browser can still make."""
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            ours = origin in {f"http://{h}" for h in hosts}
            return self.headers.get("Host") in hosts and (ours or (origin is None and not writing))

        def do_GET(self) -> None:
            if not self._ours():
                return self._send(403, b"graphene ui answers this machine's own page only\n")
            url = urlsplit(self.path)
            if url.path == "/api/graph":
                asked = [i for v in parse_qs(url.query).get("sessions", []) for i in v.split(",") if i]
                try:
                    with Store.open(root) as store:
                        report = backfill(store, root)  # a transcript that has not changed costs one stat
                        refresh_commits(store, root, report.added + report.refreshed + (asked or session_ids))
                        body = payload(
                            store, asked or session_ids, token=token, writable=writable, checkout=root
                        )
                except sqlite3.OperationalError as busy:
                    if "locked" not in str(busy):
                        raise
                    return self._send(503, BUSY)
                return self._send(200, body.encode(), TYPES[".json"])
            name = "index.html" if url.path == "/" else url.path.lstrip("/")
            target = (STATIC / name).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found\n")
            self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

        def do_POST(self) -> None:
            """One plan edit, made by the person at this page. Every refusal is plan.py's own
            sentence, sent whole: the page prints it where the control is, and invents nothing."""
            if not self._ours(writing=True):
                return self._send(403, b"graphene ui answers this machine's own page only\n")
            if not writable:
                return self._send(403, READ_ONLY)
            if not secrets.compare_digest(self.headers.get("X-Graphene-Token") or "", token):
                return self._send(403, b"that request carries no token from this run of graphene ui\n")
            operation = OPS.get(urlsplit(self.path).path.removeprefix("/api/plan/"))
            if operation is None:
                return self._send(404, b"no such plan operation\n")
            try:
                length = min(int(self.headers.get("Content-Length") or 0), BODY_CAP)
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._send(400, b"a plan edit is one JSON object\n")
            if not isinstance(body, dict):
                return self._send(400, b"a plan edit is one JSON object\n")
            try:
                with Store.open(root) as store:
                    operation(store, root, body, P.Caller(P.person_name(), True))
            except P.Refused as no:
                return self._send(409, f"{no}\n".encode())
            except sqlite3.OperationalError as busy:
                if "locked" not in str(busy):
                    raise
                return self._send(503, BUSY)
            self._send(200, b'{"ok": true}', TYPES[".json"])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server
