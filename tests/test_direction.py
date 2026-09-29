"""The direction: a tree of goals above the plans, in a file git tracks, with every plan and every
recorded session hanging from one of its nodes, and its status read from what the hooks recorded."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from test_plan_cli import AGENT_ENV, agent, person, repo  # noqa: F401  (fixtures)

from graphene_map import direction as D
from graphene_map import plan as P
from graphene_map.hooks import ingest_hook_event
from graphene_map.store import Store

ALEX = P.Caller("alex", True)
BOT = P.Caller("claude:5e55105e", False)
TEXT = (
    '﻿# our direction: "?" is proposed, "-" accepted\r\n'
    "- the product people pay for  [product]\r\n"
    "    what it is for, in a line\r\n"
    "\r\n"
    "  ? live on the real service  [live]\r\n"
    "      every rung passes live\r\n"
    "  - the board earns its place   [board]\r\n"
    "# a note of the person's own\r\n"
    "? the submission by 30 October  [submission]\r\n"
)
TREE = "- the product  [product]\n  - live  [live]\n  - the board  [board]\n- the submission  [submission]\n"
AGENT_SID = AGENT_ENV["CLAUDE_CODE_SESSION_ID"]


def test_the_text_round_trips_byte_for_byte_and_an_accept_changes_only_its_marks():
    d = D.parse(TEXT)
    assert d.text() == TEXT  # a byte order mark, CRLF, a comment, a blank line and odd spacing kept
    assert [(n.id, n.parent, n.proposed) for n in d.nodes] == [
        ("product", None, False),
        ("live", "product", True),
        ("board", "product", False),
        ("submission", None, True),
    ]
    assert d.get("product").about == ["what it is for, in a line"]
    assert D.accept(d, ["live"], ALEX) == ["live"]
    before, after = TEXT.splitlines(keepends=True), d.text().splitlines(keepends=True)
    assert [k for k, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [4]
    assert after[4] == "  - live on the real service  [live]\r\n"
    assert D.parse(d.text()).text() == d.text()


def test_a_text_with_lines_it_cannot_read_is_refused_by_line_number_and_none_of_it_is_used():
    bad = (
        "- a goal  [a]\n"
        "- another goal with no id\n"  # 2
        "  - under a  [a]\n"  # 3: the id is taken
        "\t- tabbed  [t]\n"  # 4
        "  - child  [c]\n"
        "    about the child\n"
        "- b  [b]\n"
        "  - b's child  [bc]\n"
        "  about b, after its child\n"  # 9
    )
    with pytest.raises(P.Refused) as no:
        D.parse(bad)
    said = str(no.value)
    assert said.startswith(f"{D.FILE} cannot be read, so none of it is used:")
    assert [line.split(":")[0].strip() for line in said.splitlines()[1:]] == [
        "line 2",
        "line 3",
        "line 4",
        "line 9",
    ]
    with pytest.raises(P.Refused, match="line 1: a line under no node"):
        D.parse("not a node\n")


def test_an_agent_proposes_only_the_person_accepts_or_drops_and_git_sees_the_file(repo):  # noqa: F811
    proposed = agent("direction", "propose", "-", input=TREE)
    assert proposed.exit_code == 0, proposed.output
    assert "proposed product, live, board, submission: the person accepts them" in proposed.stdout
    text = (repo / D.FILE).read_text()
    assert text == TREE.replace("- ", "? ")  # an agent's "-" is a proposal
    assert agent("direction", "accept", "live").exit_code == 1
    assert "the person's to do" in agent("direction", "accept", "live").stderr
    assert agent("direction", "drop", "board").exit_code == 1
    accepted = person("direction", "accept", "live")
    assert accepted.exit_code == 0 and accepted.stdout.startswith("accepted product, live")  # with its why
    under = agent("direction", "propose", "-", "--under", "live", input="- the ladder's rungs  [rungs]\n")
    assert under.exit_code == 0, under.output
    assert person("direction", "drop", "board").stdout.startswith("dropped board")
    assert (repo / D.FILE).read_text() == (
        "- the product  [product]\n  - live  [live]\n    ? the ladder's rungs  [rungs]\n"
        "? the submission  [submission]\n"
    )
    taken = agent("direction", "propose", "-", input="? live again  [live]\n")
    assert taken.exit_code == 1 and "already in the direction: [live]" in taken.stderr
    # the store's own .gitignore leaves this one file to git; the store stays ignored
    status = subprocess.run(
        ["git", "status", "--porcelain", "-uall"], cwd=repo, capture_output=True, text=True
    )
    assert f"?? {D.FILE}" in status.stdout.splitlines() and "graphene.db" not in status.stdout


def test_a_broken_file_is_refused_by_every_command_that_reads_it(repo):  # noqa: F811
    (repo / ".graphene").mkdir(exist_ok=True)
    (repo / D.FILE).write_text("- fine  [fine]\n- no id here\n")
    for said in (person("direction"), agent("direction", "propose", "-", input="? more  [more]\n")):
        assert said.exit_code == 1 and "line 2: a node's line ends with its id in brackets" in said.stderr
    assert (repo / D.FILE).read_text() == "- fine  [fine]\n- no id here\n"  # nothing written over it


def _event(store, root, name, sid, at, **more):
    ingest_hook_event(store, {"hook_event_name": name, "session_id": sid, **more}, root, timestamp=at)


def _stamp(now: datetime, seconds: float) -> str:
    return (now - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def test_sessions_attach_by_what_they_do_or_by_the_person_and_say_whose_move_it_is(repo):  # noqa: F811
    """A session holding a leaf attaches through the plan's node; a subagent goes with its session;
    another session stays unattached until the person attaches it. Each says running, idle, your turn
    or finished from the hooks' own rows, and a day's quiet leaves a session out."""
    agent("direction", "propose", "-", input=TREE)
    person("direction", "accept", "product", "submission")
    agent(
        "plan",
        "propose",
        "-",
        input="goal: users come back with ids\n- users returns ids  [ids]\n    scope: api.py\n    check: true\n",  # noqa: E501
    )
    person("plan", "accept")
    assert person("direction", "plan", "live").stdout.startswith(
        "the plan (users come back with ids) hangs from live"
    )
    assert agent("node", "start", "ids").exit_code == 0
    now = datetime.now(UTC)
    with Store.open(repo) as store:
        _event(store, repo, "SessionStart", AGENT_SID, _stamp(now, 900))
        _event(store, repo, "UserPromptSubmit", AGENT_SID, _stamp(now, 890), prompt="make users return ids")
        bash = {"command": "pytest -q", "description": "Run the tests"}
        _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 30), tool_name="Bash", tool_input=bash)
        lane, task = "a640f5b22c59e6b51", {"description": "Lane D: the direction"}
        _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 800), tool_name="Agent", tool_use_id="t1",
               tool_input=task, tool_response={"agentId": lane})  # fmt: skip
        _event(store, repo, "SubagentStart", AGENT_SID, _stamp(now, 799), agent_id=lane)
        _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 700), tool_name="Edit", agent_id=lane,
               tool_input={"file_path": str(repo / "api.py")}, tool_response={})  # fmt: skip
        other = "0ther000-0000-4000-8000-000000000002"
        _event(store, repo, "UserPromptSubmit", other, _stamp(now, 600), prompt="fix the readme\nplease")
        _event(store, repo, "PostToolUse", other, _stamp(now, 590), tool_name="Write",
               tool_input={"file_path": str(repo / "README.md")}, tool_response={})  # fmt: skip
        _event(store, repo, "Stop", other, _stamp(now, 580))
        _event(store, repo, "UserPromptSubmit", "01d00000-0000", _stamp(now, 2 * D.DAY), prompt="old")
        _event(store, repo, "UserPromptSubmit", "1d1e0000-0000", _stamp(now, D.IDLE + 60), prompt="quiet")
        st = D.status(store, D.read(repo), now)
    by = {w["short"]: w for w in st["sessions"]}
    assert set(by) == {AGENT_SID[:8], "a640f5b2", other[:8]}
    assert st["older"] == 2  # a day's quiet, and an hour idle
    me, lane, loose = by[AGENT_SID[:8]], by["a640f5b2"], by[other[:8]]
    assert (me["node"], me["how"], me["word"], me["last"]) == (
        "plan",
        "worked on the plan",
        "running",
        "Run the tests",
    )
    assert (lane["node"], lane["how"], lane["word"], lane["label"]) == (
        "plan",
        "with its session",
        "idle",
        "Lane D: the direction",
    )
    assert lane["last"] == "edited api.py"
    assert (loose["node"], loose["word"], loose["label"]) == (
        None,
        "your turn",
        "a Claude Code session: fix the readme",
    )
    live = next(n for n in st["nodes"] if n["id"] == "live")
    assert (live["word"], live["running"], live["you"]) == ("running", 2, 0)  # the leaf and the session
    top = next(n for n in st["nodes"] if n["id"] == "product")
    assert top["running"] == 2 and top["next"] is None
    shown = person("direction", "--width", "120").stdout.splitlines()
    narrow = person("direction", "--width", "60").stdout.splitlines()[0]
    assert narrow.startswith("you: 1 · 2 running · the direction of …") and len(narrow) == 60
    assert all(len(line) <= 80 for line in person("direction", "--width", "80").stdout.splitlines()[:-1])
    assert any("the plan: users come back with ids" in line and "0/1 done" in line for line in shown)
    assert any("not in the direction" in line for line in shown)
    # the person attaches the other session; `none` gives it back
    assert (
        person("direction", "attach", other[:8], "submission").stdout
        == f"{other[:8]} attached to submission\n"
    )
    assert agent("direction", "attach", other[:8], "live").exit_code == 1
    with Store.open(repo) as store:
        st = D.status(store, D.read(repo), now)
    sub = next(n for n in st["nodes"] if n["id"] == "submission")
    assert (sub["word"], sub["you"]) == ("yours", 1)
    assert next(w for w in st["sessions"] if w["short"] == other[:8])["how"] == "attached by you"
    person("direction", "attach", other[:8], "none")
    with Store.open(repo) as store:
        assert (
            next(w for w in D.status(store, D.read(repo), now)["sessions"] if w["short"] == other[:8])["node"]
            is None
        )


def test_the_hook_imports_nothing_of_the_direction(tmp_path):
    """The hook's hot path does no work for the direction: status is read by the commands, at read time."""
    said = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, io; from graphene_map import hooks; hooks.hook_main(io.StringIO('{}'));"
            "print('graphene_map.direction' in sys.modules)",
        ],  # fmt: skip
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    assert said.stdout.strip() == "False"


def test_the_json_is_what_the_page_reads(repo):  # noqa: F811
    agent("direction", "propose", "-", input=TREE)
    said = json.loads(person("direction", "--json").stdout)
    assert said["file"] == D.FILE and [n["id"] for n in said["nodes"]] == [
        "product",
        "live",
        "board",
        "submission",
    ]
    assert (
        all(n["word"] == "proposed" for n in said["nodes"]) and said["nodes"][0]["you"] == 3
    )  # itself and the two under it


PLAN = """\
goal: users come back with their ids
- the API  [api]
  - users returns ids  [ids]
      scope: api.py
      check: grep -q ids api.py
  - document it  [docs]
      scope: README.md
      check: test -f README.md
      needs: ids
"""


def test_the_direction_is_above_the_plan_in_its_prints_its_views_the_screen_and_the_page(repo):  # noqa: F811
    import asyncio

    from graphene_map import server
    from graphene_map.tui import Watch

    agent("direction", "propose", "-", input=TREE)
    person("direction", "accept", "product")
    agent("plan", "propose", "-", input=PLAN)
    person("plan", "accept")
    unhung = person("plan").stdout.splitlines()
    assert unhung[0] == (
        "the direction: the plan hangs from none of its nodes yet (`graphene direction plan NODE`)"
    )
    person("direction", "plan", "live")
    for said in (person("plan"), person("plan", "--view", "tree", "--width", "120", "--height", "36")):
        shown = said.stdout.splitlines()
        assert shown[0].split()[1:4] == ["the", "product", "product"] and "next: ids" in shown[0]
        assert shown[1].split()[1:3] == ["live", "live"] and shown[2:3] != []
        assert not any("board" in line.split() for line in shown[:2])  # the path only, not the siblings
    assert person("plan").stdout.splitlines()[2].startswith("the plan: users come back with their ids")

    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            return str(app.query_one("#direction").render()).splitlines()

    rows = asyncio.run(go())
    assert [r.split()[1] for r in rows] == ["the", "live"] and "next: ids" in rows[1]

    with Store.open(repo) as store:
        page = json.loads(server.payload(store, []))["direction"]
        export = json.loads(server.payload(store, [], only=True))["direction"]
    assert page["plan"]["node"] == "live" and page["plan"]["next"] == "ids"
    assert [n["id"] for n in page["nodes"]] == ["product", "live", "board", "submission"]
    assert export["sessions"] == [] and export["nodes"] == page["nodes"]  # sessions stay on this machine
