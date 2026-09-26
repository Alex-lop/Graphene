# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""What the closing review found in the executor, the client and the sandbox, each against the recorded
fake (and, where it says so, the Docker stand-in): each test fails on the code before its fix."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_executor import NANO

from graphene_map import tokenfactory as tf


def test_an_answer_that_is_not_json_says_so_in_one_line(monkeypatch):
    """A 200 that is not JSON (a portal, a proxy, a wrong GRAPHENE_TOKENFACTORY_URL) escaped as a
    JSONDecodeError: a leaf came back as "3 attempts … AssertionError", and `graphene init` printed a
    traceback."""

    class Portal(BaseHTTPRequestHandler):
        def do_GET(self):
            page = b"<html>sign in to the hotel's wifi</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        do_POST = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/"
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", url)
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-key")
    tf._listed.cache_clear()
    try:
        said = f"Token Factory's answer at {url} is not JSON: a proxy, or a wrong GRAPHENE_TOKENFACTORY_URL?"
        assert tf.reach(tries=1) == said  # what `graphene init` says
        with pytest.raises(tf.Unreachable) as no:
            tf.chat(NANO, [{"role": "user", "content": "hi"}])
        assert str(no.value) == said
    finally:
        server.shutdown()
        server.server_close()
        tf._listed.cache_clear()
