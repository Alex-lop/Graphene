"""`graphene ui`: the map, served to this machine only, or written out as one file.

A stdlib HTTP server bound to 127.0.0.1 on a free port. It serves the built page from
``ui/static`` and two read-only JSON endpoints; a request whose ``Host`` or ``Origin`` is not this
server's own address is refused, so a web page open elsewhere in the browser cannot read the store
through it. The hook never talks to this process. The export is the same page with its script, its
stylesheet and the data inlined: it opens from disk and fetches nothing.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .commits import refresh_commits
from .graph import build_graph, to_json
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


def payload(store: Store, session_ids: list[str], only: bool = False) -> str:
    """What the page needs in one object: the rail and the graph of the chosen sessions. ``only``
    keeps the rail to those sessions, for a file that leaves the machine."""
    rail = runs(store)
    known = {r["id"] for r in rail}
    ids = [i for i in session_ids if i in known] or [r["id"] for r in rail[:1]]
    rail = [r for r in rail if r["id"] in ids] if only else rail
    return '{"runs": ' + json.dumps(rail) + ', "graph": ' + to_json(build_graph(store, ids)) + "}"


def export_html(store: Store, session_ids: list[str]) -> str:
    """One self-contained file: the built page with its assets and the data inlined. Paths, counts,
    task text and prompts go in; no hunks and no tool output exist in the graph to leak."""
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


def make_server(root: Path, session_ids: list[str]) -> ThreadingHTTPServer:
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

        def _ours(self) -> bool:
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            return self.headers.get("Host") in hosts and (
                origin is None or origin in {f"http://{h}" for h in hosts}
            )

        def do_GET(self) -> None:
            if not self._ours():
                return self._send(403, b"graphene ui answers this machine's own page only\n")
            url = urlsplit(self.path)
            if url.path == "/api/graph":
                asked = [i for v in parse_qs(url.query).get("sessions", []) for i in v.split(",") if i]
                with Store.open(root) as store:
                    report = backfill(store, root)  # a transcript that has not changed costs one stat
                    refresh_commits(store, root, report.added + report.refreshed + (asked or session_ids))
                    body = payload(store, asked or session_ids)
                return self._send(200, body.encode(), TYPES[".json"])
            name = "index.html" if url.path == "/" else url.path.lstrip("/")
            target = (STATIC / name).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found\n")
            self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server
