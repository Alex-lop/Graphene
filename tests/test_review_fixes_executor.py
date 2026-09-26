# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""What the closing review found in the executor, the client and the sandbox, each against the recorded
fake (and, where it says so, the Docker stand-in): each test fails on the code before its fix."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fake_tokenfactory import call
from test_executor import NANO, fake, git, leaf, plan_of, repo, run_one, script, tool_results  # noqa: F401

from graphene_map import tokenfactory as tf
from graphene_map.store import Store


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


def raw(name: str, arguments: str) -> dict:
    """A call whose arguments are sent as they are: what a misfiring model sends."""
    return {"content": None, "tool_calls": [{"id": f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": arguments}}]}  # fmt: skip


def test_arguments_that_are_json_but_not_an_object_or_hold_a_null_are_said_to_the_model(repo, fake):
    """Arguments encoded twice, an array, or `"content": null` raised AttributeError out of the tool:
    the leaf stopped ("the executor stopped: AttributeError …") and the model was never told (72)."""
    f = fake([script({"greet": [
        raw("view", json.dumps(json.dumps({"path": "app.py"}))),  # encoded twice: read once more
        raw("view", json.dumps(["app.py"])),
        raw("write", json.dumps({"path": "app.py", "content": None})),
        call("release", why="looked"),
    ]})] * 10)  # fmt: skip
    plan_of(repo, leaf())
    run_one(repo)
    said = tool_results(f.requests[-1])
    assert said[0].split("\n")[1] == '    2      return "hi"'
    assert said[1] == "view takes a JSON object of named fields"
    assert said[2].startswith("write could not take those arguments (") and "'content'" in said[2]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hi"\n'
    with Store.open(repo) as store:  # the model's own reason, not the executor's stop
        assert store.node_log("greet", ("released",))[-1]["detail"]["why"] == "looked"
