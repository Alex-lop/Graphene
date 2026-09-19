"""`graphene ui`: the loopback server's boundaries, and what the exported file holds."""

import json
import threading
import urllib.error
import urllib.request

import pytest

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


@pytest.fixture
def served(repo):
    server = ui.make_server(repo, [SID])
    threading.Thread(target=server.serve_forever, daemon=True).start()
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
