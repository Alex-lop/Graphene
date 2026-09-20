"""`graphene ui`: the loopback server's boundaries, the plan edits it accepts, and what an export holds."""

import json
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

from graphene_debrief import plan as P
from graphene_debrief import server as ui
from graphene_debrief.model import Prompt, Session, ToolEvent
from graphene_debrief.store import Store

SID = "aaaaaaaa-0000-4000-8000-000000000000"
QUIET = "bbbbbbbb-0000-4000-8000-000000000000"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(
        '<html><head><script type="module" crossorigin src="./assets/app.js"></script>'
        '<link rel="stylesheet" crossorigin href="./assets/app.css"></head>'
        '<body><div id="root"></div></body></html>'
    )
    (static / "assets" / "app.js").write_text('console.log("</script>")')
    (static / "assets" / "app.css").write_text("body{margin:0}")
    (tmp_path / "secret.txt").write_text("not yours")
    monkeypatch.setattr(ui, "STATIC", static)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    root = tmp_path / "repo"
    root.mkdir()
    with Store.open(root) as store:
        for sid, minute in ((SID, 0), (QUIET, 30)):
            store.upsert_session(
                Session(sid, str(root), f"2026-03-02T09:{minute:02d}:00.000Z", source="backfill")
            )
        store.add_prompt(Prompt("p1", SID, 1, "2026-03-02T09:00:05.000Z", "say </script> twice"))
        path = {"file_path": f"{root}/app/x.py"}
        store.add_event(
            ToolEvent("e1", SID, "p1", "2026-03-02T09:01:00.000Z", "Edit", path, {}, True, None, "app/x.py")
        )
    return root


def serve(repo, writable=True):
    server = ui.make_server(repo, [SID], writable=writable)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def served(repo):
    server = serve(repo)
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def get(port, path, **headers):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(), error.headers


def post(port, op, body, token=None, **headers):
    """A plan edit as the page makes it: its own Origin, and the token this launch handed it."""
    headers = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", **headers}
    if token is not None:
        headers["X-Graphene-Token"] = token
    headers = {k: v for k, v in headers.items() if v is not None}  # Origin=None means: send none
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/plan/{op}", data=json.dumps(body).encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def token_of(port):
    return json.loads(get(port, f"/api/graph?sessions={SID}")[1])["plan"]["token"]


def test_the_page_its_assets_and_the_graph_are_served(served):
    status, body, headers = get(served, "/")
    assert status == 200 and 'id="root"' in body and headers["Content-Type"].startswith("text/html")
    assert get(served, "/assets/app.css")[1] == "body{margin:0}"
    status, body, _ = get(served, f"/api/graph?sessions={SID}")
    data = json.loads(body)
    assert status == 200 and [r["id"] for r in data["runs"]] == [
        SID
    ]  # the session with no calls is not a run
    assert data["graph"]["run"]["sessions"][0]["id"] == SID and data["graph"]["rows"][0]["path"] == "app"


def test_a_request_for_another_host_or_from_another_origin_is_refused(served):
    assert get(served, "/api/graph", Host="evil.example")[0] == 403
    assert get(served, "/api/graph", Origin="https://evil.example")[0] == 403
    assert get(served, "/", Host=f"localhost:{served}", Origin=f"http://localhost:{served}")[0] == 200


def test_nothing_outside_the_built_page_is_served(served):
    for path in ("/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt", "/missing.js"):
        status, body, _ = get(served, path)
        assert status == 404 and "not yours" not in body


def test_the_export_is_one_file_with_the_page_and_the_data_inlined(repo):
    with Store.open(repo) as store:
        page = ui.export_html(store, [SID])
    assert "src=" not in page and "href=" not in page and "body{margin:0}" in page
    assert page.count("</script>") == 2  # the data and the page's script: nothing recorded closes a tag early
    start = page.index(ui.DATA_TAG) + len(ui.DATA_TAG)
    data = json.loads(page[start : page.index("</script>", start)])
    assert [r["id"] for r in data["runs"]] == [SID] and data["graph"]["caption"]
    assert "say </script> twice" in json.dumps(data, ensure_ascii=False)  # and the text survives the escaping


# -- the plan, beside the record -------------------------------------------------------------------


def node(**extra):
    return {"title": "users endpoint", "scope": ["src/api/**"], "check": "true", **extra}


def plan_of(port):
    return json.loads(get(port, f"/api/graph?sessions={SID}")[1])["plan"]


def test_the_payload_carries_the_plan_beside_the_graph(served, repo):
    with Store.open(repo) as store:
        P.propose(store, [node(id="n1")], P.Caller("alex", True))
    shown = plan_of(served)
    assert [n["id"] for n in shown["nodes"]] == ["n1"] and shown["nodes"][0]["display_state"] == "ready"
    assert shown["holes"]["scope"] and shown["writable"] is True and shown["token"]


def test_the_page_edits_the_plan_and_the_change_lands_in_the_store(served, repo):
    token = token_of(served)
    assert post(served, "add", node(id="n1", goal="the endpoint"), token)[0] == 200
    assert post(served, "set", {"id": "n1", "scope": ["src/api/**", "tests/**"]}, token)[0] == 200
    with Store.open(repo) as store:
        n = P.get(store, "n1")
        assert n.scope == ["src/api/**", "tests/**"] and n.rev == 2 and n.owner == P.AGENT
        assert [e["kind"] for e in store.node_log("n1")] == ["added", "edited"]
        assert store.node_log("n1")[0]["actor"] == P.person_name()  # the page speaks for the person


def test_a_proposal_is_accepted_and_the_plan_is_paused_from_the_page(served, repo):
    with Store.open(repo) as store:
        P.propose(store, [node(id="n1")], P.Caller("claude:aaaa1111", False, "s"))
    token = token_of(served)
    assert plan_of(served)["nodes"][0]["state"] == "proposed"
    assert post(served, "accept", {"ids": ["n1"]}, token)[0] == 200
    assert post(served, "pause", {}, token)[0] == 200
    shown = plan_of(served)
    assert shown["nodes"][0]["state"] == "open" and shown["paused"] is True
    assert post(served, "resume", {}, token)[0] == 200 and plan_of(served)["paused"] is False


def test_a_write_needs_this_page_its_own_origin_and_the_token_of_this_launch(served):
    token = token_of(served)
    assert post(served, "add", node(id="a"), token, Origin=f"http://localhost:{served}")[0] == 200
    assert post(served, "add", node(id="b"), token, Host="evil.example")[0] == 403
    assert post(served, "add", node(id="b"), token, Origin="https://evil.example")[0] == 403
    assert post(served, "add", node(id="b"), token, Origin=None)[0] == 403  # a missing Origin, for a write
    assert post(served, "add", node(id="b"), "not-the-token")[0] == 403
    assert post(served, "add", node(id="b"), None)[0] == 403
    assert post(served, "nonsense", {}, token)[0] == 404


def test_a_ui_started_inside_an_agents_shell_serves_a_page_that_cannot_write(repo):
    server = serve(repo, writable=False)
    port = server.server_address[1]
    try:
        status, said = post(port, "add", node(id="n1"), token_of(port))
        assert status == 403 and "read-only" in said
        assert plan_of(port)["writable"] is False
        with Store.open(repo) as store:
            assert store.node_count() == 0
    finally:
        server.shutdown()
        server.server_close()


def test_a_refusal_comes_back_whole_and_a_busy_store_says_so(served, monkeypatch):
    token = token_of(served)
    status, said = post(served, "add", {"title": "no scope", "check": "true"}, token)
    assert status == 409 and "a node needs a scope" in said

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ui.Store, "open", locked)
    status, said = post(served, "add", node(id="n2"), token)
    assert status == 503 and "busy" in said and len(said.splitlines()) == 1


def test_the_token_never_leaves_the_machine_in_an_export(repo, served):
    token = token_of(served)
    with Store.open(repo) as store:
        P.propose(store, [node(id="n1")], P.Caller("alex", True))
        page = ui.export_html(store, [SID])
    assert token not in page and '"token": null' in page and '"writable": false' in page
    assert '"plan"' in page and '"n1"' in page  # and the plan itself is there, to be read


def test_what_a_check_printed_never_leaves_the_machine_in_an_export(repo):
    """A node's log holds the tail of its check's output, and the export promises no tool output."""
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    alex, bot = P.Caller("alex", True), P.Caller("claude:x", False, "x")
    with Store.open(repo) as store:
        P.propose(store, [node(id="n1", check="echo TOKEN-sk-live-hunter2; exit 1")], alex)
        P.start(store, "n1", bot, repo)
        with pytest.raises(P.Refused):
            P.finish(store, "n1", bot)
        live = ui.payload(store, [SID])
        page = ui.export_html(store, [SID])
    assert "hunter2" in json.loads(live)["plan"]["nodes"][0]["log"][-1]["said"]  # the person sees it
    assert "hunter2" not in page.replace("echo TOKEN-sk-live-hunter2; exit 1", "")  # the file does not
    assert '"log": []' in page


def test_the_words_a_node_came_back_with_are_the_plans_and_the_export_carries_them(repo):
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    alex, bot = P.Caller("alex", True), P.Caller("claude:x", False, "x")
    with Store.open(repo) as store:
        P.propose(store, [node(id="n1", signoff=True)], alex)
        P.start(store, "n1", bot, repo)
        P.finish(store, "n1", bot)
        P.reopen(store, "n1", alex, "return a dict, not a list")
        assert "sent back: return a dict, not a list" in ui.export_html(store, [SID])
        P.start(store, "n1", bot, repo)
        P.release(store, "n1", bot, "the test asserts a list")
        assert "handed back: the test asserts a list" in ui.export_html(store, [SID])


def test_a_malformed_request_is_answered_not_crashed(served):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", served, timeout=5)
    conn.putrequest("POST", "/api/plan/pause")
    for name, value in {
        "Host": f"127.0.0.1:{served}",
        "Origin": f"http://127.0.0.1:{served}",
        "X-Graphene-Token": token_of(served),
        "Content-Length": "abc",
    }.items():
        conn.putheader(name, value)
    conn.endheaders()
    assert conn.getresponse().status == 400


def test_every_operation_the_page_can_post_is_one_function_in_the_plan(served):
    assert set(ui.OPS) == {
        "add", "set", "drop", "accept", "signoff", "reopen", "pause", "resume", "ack", "archive"
    }  # fmt: skip
