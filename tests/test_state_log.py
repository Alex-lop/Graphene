# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene plan log --json [--since ID]`: the plan's log as rows after a cursor, one JSON object a line
(JSON lines), oldest first, so an editor that read `state --json`'s cursor follows what changed cheaply."""

import json

from test_run_live import leaf, repo  # noqa: F401
from typer.testing import CliRunner

from graphene_map import plan
from graphene_map.cli import build
from graphene_map.plan import Caller
from graphene_map.store import Store

runner = CliRunner()
ALEX = Caller("alex", True)
ROW = {"id", "node_id", "timestamp", "kind", "actor", "session_id", "agent_id", "detail"}


def log(*args):
    said = runner.invoke(build(), ["plan", "log", *args], env={"GRAPHENE_AS": "person:alex"})
    assert said.exit_code == 0, said.output + said.stderr
    return said.stdout


def test_the_rows_after_the_cursor_come_one_json_object_a_line_oldest_first(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.set_goal(store, "a goal", ALEX)
    rows = [json.loads(line) for line in log("--json").splitlines()]
    assert len(rows) >= 3 and all(set(r) == ROW for r in rows)
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)  # oldest first, by the log's id
    assert rows[0]["kind"] == "added" and rows[0]["node_id"] == "a" and rows[0]["actor"] == "alex"
    assert isinstance(rows[0]["detail"], dict)  # read, not the store's JSON string
    cursor = rows[1]["id"]
    after = [json.loads(line) for line in log("--json", "--since", str(cursor)).splitlines()]
    assert [r["id"] for r in after] == [r["id"] for r in rows if r["id"] > cursor]
    assert log("--json", "--since", str(rows[-1]["id"])) == ""  # nothing after the last: no lines


def test_the_text_form_is_as_it_was_and_since_cuts_it_too(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt")], ALEX)
    text = log()
    assert "added" in text and "  a  " in text and "  b  " in text and not text.startswith("{")
    assert "  a  " not in log("--since", "1") and "  b  " in log("--since", "1")
