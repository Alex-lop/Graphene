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
    with pytest.raises(P.Refused, match="line 2: a control character"):
        D.parse("- a  [a]\n- \x1b]0;owned\x07 b  [b]\n")  # a committed file must not drive the terminal


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
        nested = "c0c0c0c0c0c0c0c0"  # started by the lane, not by its session: it goes with the lane
        _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 650), tool_name="Agent", agent_id=lane,
               tool_input={"description": "a nested helper"}, tool_response={"agentId": nested})  # fmt: skip
        _event(store, repo, "SubagentStart", AGENT_SID, _stamp(now, 649), agent_id=nested)
        _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 20), tool_name="Read", agent_id=nested)
        other = "0ther000-0000-4000-8000-000000000002"
        _event(store, repo, "UserPromptSubmit", other, _stamp(now, 600), prompt="fix the readme\nplease")
        _event(store, repo, "PostToolUse", other, _stamp(now, 590), tool_name="Write",
               tool_input={"file_path": str(repo / "README.md")}, tool_response={})  # fmt: skip
        helper = "b0b0b0b0b0b0b0b0"  # its session's turn ended after its last call: it ended too
        _event(store, repo, "SubagentStart", other, _stamp(now, 595), agent_id=helper)
        _event(store, repo, "PostToolUse", other, _stamp(now, 594), tool_name="Grep", agent_id=helper)
        _event(store, repo, "Stop", other, _stamp(now, 580))
        _event(store, repo, "UserPromptSubmit", "01d00000-0000", _stamp(now, 2 * D.DAY), prompt="old")
        _event(store, repo, "UserPromptSubmit", "1d1e0000-0000", _stamp(now, D.IDLE + 60), prompt="quiet")
        st = D.status(store, D.read(repo), now)
    by = {w["short"]: w for w in st["sessions"]}
    assert set(by) == {AGENT_SID[:8], "a640f5b2", "c0c0c0c0", other[:8]}
    assert (by["c0c0c0c0"]["node"], by["c0c0c0c0"]["how"], by["c0c0c0c0"]["label"]) == (
        "plan",
        "with the subagent that started it",
        "a nested helper",
    )
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
    assert lane["last"] == "started a nested helper"  # its own last call: the Agent call
    assert (loose["node"], loose["word"], loose["label"]) == (
        None,
        "your turn",
        "session: fix the readme",
    )
    live = next(n for n in st["nodes"] if n["id"] == "live")
    assert (live["word"], live["running"], live["you"]) == (
        "running",
        2,
        0,
    )  # the leaf (its session is it), nested
    top = next(n for n in st["nodes"] if n["id"] == "product")
    assert top["running"] == 2 and top["next"] is None
    shown = person("direction", "--width", "120").stdout.splitlines()
    narrow = person("direction", "--width", "60").stdout.splitlines()[0]
    assert narrow.startswith("you: 1 · 2 running · the direction of …") and len(narrow) == 60
    assert all(len(line) <= 80 for line in person("direction", "--width", "80").stdout.splitlines())
    assert any("the plan: users come back with ids" in line and "0/1 done" in line for line in shown)
    assert any("not in the direction" in line for line in shown)
    # the person attaches the other session; `none` gives it back
    assert (
        person("direction", "attach", other[:8], "submission").stdout
        == f"{other[:8]} attached to submission\n"
    )
    assert agent("direction", "attach", other[:8], "live").exit_code == 1
    assert person("direction", "attach", "a640f5b2", "board").exit_code == 0
    with Store.open(repo) as store:
        placed = {w["short"]: w["node"] for w in D.status(store, D.read(repo), now)["sessions"]}
    assert (placed["a640f5b2"], placed["c0c0c0c0"]) == ("board", "board")  # what it started goes with it
    with Store.open(repo) as store:
        st = D.status(store, D.read(repo), now)
    from graphene_map import server

    with Store.open(repo) as store:
        export = server.payload(store, [], only=True)
    assert AGENT_SID[:8] not in json.dumps(json.loads(export)["direction"])  # no session leaves the machine
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
    views = (person("plan", "--view", "tree", "--width", "120", "--height", "36"), person("watch", "--once"))
    for said in (person("plan"), *views):
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


def test_d_in_watch_shows_the_direction_across_the_width_live_and_takes_no_key(repo):  # noqa: F811
    """Walkers, 29 September (three of three): D left `:direction attach ` open and focused, so the
    next j was typed into it; at 120x36 its pane was 44 columns and cut every title; after
    `:direction plan NODE` the pane still showed the plan as not in the direction. D now shows the
    direction under the tree across the whole width, read again every tick, and opens nothing:
    attaching is typed at `:`, as the bottom line says."""
    import asyncio

    from graphene_map.tui import Watch

    agent(
        "direction",
        "propose",
        "-",
        input=TREE.replace("the product", "every supplier feed lands in one table"),
    )
    agent("plan", "propose", "-", input=PLAN)
    person("plan", "accept")
    now = datetime.now(UTC)
    with Store.open(repo) as store:
        _event(store, repo, "UserPromptSubmit", "0ther000-0000", _stamp(now, 30), prompt="the readme")
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            await pilot.press("D", "j")
            await pilot.pause()
            line = app.query_one("#line")
            seen = [
                str(app.query_one("#detail").render()),
                app.pane_room()[0],
                line.has_class("-open"),
                line.value,
            ]
            seen.append(str(app.query_one("#status").render()))
            for typed in ("direction attach 0ther000 submission", "direction plan live"):
                await pilot.press("colon", *typed, "enter")
                await pilot.pause()
            app.refresh_plan()
            await pilot.pause()
            return [*seen, str(app.query_one("#detail").render())]

    pane, wide, opened, value, status, after = asyncio.run(go())
    assert not opened and "j" not in value  # j moved the cursor; no line took it
    assert wide >= 100 and "every supplier feed lands in one table" in pane and "not in the direction" in pane
    assert ":direction attach SESSION NODE" in status
    with Store.open(repo) as store:
        assert D.links(store)["attach"] == {"0ther000-0000": "submission"}
    assert "hangs the plan" in pane and "hangs the plan" not in after  # the pane followed the command
    assert "the plan: users come back with their ids" in " ".join(after.split())


def test_d_in_a_replay_shows_its_direction_and_refuses_nothing(tmp_path):
    """Walkers: in `graphene demo` D said "a replay: nothing runs here" and left `:direction attach`
    on the bottom line, though the help lists D under "see"."""
    import asyncio

    from graphene_map import demo

    head, lines = demo.load(demo.SHIPPED)
    app = demo.Replay(demo.repository(tmp_path, head), head, lines)

    async def go():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            said = str(app.query_one("#status").render()), str(app.query_one("#detail").render())
            return (*said, app.query_one("#line").has_class("-open"))

    status, pane, opened = asyncio.run(go())
    assert demo.REFUSED not in status and not opened
    assert "no direction yet" in pane


def test_edit_writes_a_text_that_reads_whole_and_nothing_of_one_that_does_not(repo, monkeypatch):  # noqa: F811
    agent("direction", "propose", "-", input=TREE)
    before = (repo / D.FILE).read_text()
    editor = repo / "editor.sh"
    editor.write_text('#!/bin/sh\nprintf -- "- the docs  [docs]\\n" >> "$1"\n')
    editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(editor))
    assert agent("direction", "edit").exit_code == 1  # an agent proposes; the person edits
    said = person("direction", "edit")
    assert said.exit_code == 0 and said.stdout == "the direction: 5 nodes, 4 proposed\n"
    assert (repo / D.FILE).read_text() == before + "- the docs  [docs]\n"
    editor.write_text('#!/bin/sh\nprintf -- "- no id here\\n" >> "$1"\n')
    refused = person("direction", "edit")
    assert refused.exit_code == 1 and "line 6: a node's line ends with its id" in refused.stderr
    assert (repo / D.FILE).read_text() == before + "- the docs  [docs]\n"  # nothing written


def test_a_direction_written_while_a_leaf_runs_is_never_the_leafs_change(repo):  # noqa: F811
    """Review, 29 September: the file is the one path under .graphene/ that git sees, so a proposal
    written while a leaf ran made its `done` refused ("changed outside its scope") and every other
    start refused ("an uncommitted change no node made"). Graphene's own directory is no leaf's
    change, uncommitted or committed."""
    one = "- one  [one]\n    scope: api.py\n    check: true\n"
    two = "- two  [two]\n    scope: schema.py\n    check: true\n"
    agent("plan", "propose", "-", input="goal: g\n" + one + two)
    person("plan", "accept")
    assert agent("node", "start", "one").exit_code == 0
    (repo / "api.py").write_text("def users():\n    return ['ids']\n")
    assert agent("direction", "propose", "-", input=TREE).exit_code == 0
    started = agent("node", "start", "two")
    assert started.exit_code == 0, started.output
    subprocess.run(["git", "add", "-f", D.FILE], cwd=repo, check=True)
    commit = ["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "the direction"]
    subprocess.run(commit, cwd=repo, check=True)
    person("direction", "accept", "live")  # the committed file changes again, while both leaves run
    done = agent("node", "done", "one")
    assert done.exit_code == 0, done.output


def test_what_the_review_found_in_the_file_each_refused_or_kept_as_it_should_be(repo, monkeypatch):  # noqa: F811
    """Review, 29 September: a file saved as Latin-1 crashed `graphene plan`; a control character in a
    comment, a C1 control or a bidi override passed; a line led by a no-break space vanished into its
    node's words; U+2028 moved every refusal's line number; a node proposed under one whose children
    are indented by one space went under its last child; a write left the file private (0600); and
    `edit` would not open a file that does not read, the one time it is needed."""
    for bad, why in (
        ("- a  [a]\n# \x1b]0;owned\x07\n", "line 2: a control character"),
        ("- a  \u009b31m [a]\n", "line 1: a control character"),
        ("- a ‮ [a]\n", "line 1: a control character"),
        ("- a  [a]\n  - b  [b]\n", "line 2: indent with spaces only"),
        ("- a  [a]\n  what a is for\n- no id\n", "line 3: a node's line ends"),
    ):
        with pytest.raises(P.Refused, match=why):
            D.parse(bad)
    d = D.parse("- a  [a]\n - b  [b]\n")
    D.propose(d, "? c  [c]\n", BOT, "a")
    assert [(n.id, n.parent) for n in D.parse(d.text()).nodes] == [("a", None), ("b", "a"), ("c", "a")]

    agent("direction", "propose", "-", input=TREE)
    assert (repo / D.FILE).stat().st_mode & 0o777 == 0o644
    agent("plan", "propose", "-", input=PLAN)
    person("plan", "accept")
    (repo / D.FILE).write_bytes(b"- caf\xe9  [cafe]\n")
    plan = person("plan")
    assert plan.exit_code == 0 and plan.stdout.startswith(f"the direction: {D.FILE} cannot be read")
    assert "it is not UTF-8" in person("direction").stderr
    (repo / D.FILE).write_text("- fine  [fine]\n- no id here\n")
    editor = repo / "editor.sh"
    editor.write_text('#!/bin/sh\ngrep -q "refused: .*its id" "$1" && printf -- "- fine  [fine]\\n" > "$1"\n')
    editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(editor))
    mended = person("direction", "edit")
    assert mended.exit_code == 0, mended.output
    assert (repo / D.FILE).read_text() == "- fine  [fine]\n"


def test_running_work_is_counted_once_and_a_leaf_made_from_a_prompt_leaves_its_session_where_it_was(repo):  # noqa: F811
    """Review, 29 September: a session holding a leaf and its two lanes counted the leaf twice, and a
    one-line ask typed into an unrelated session (a leaf made from a prompt) pulled that session into
    the plan's node."""
    agent("direction", "propose", "-", input=TREE)
    person("direction", "accept", "product")
    agent("plan", "propose", "-", input=PLAN)
    person("plan", "accept")
    person("direction", "plan", "live")
    assert agent("node", "start", "ids").exit_code == 0
    other, now = "a51de000-0000-4000-8000-000000000003", datetime.now(UTC)
    with Store.open(repo) as store:
        _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 10), tool_name="Read")
        for n, lane in enumerate(("d1d1d1d1d1d1d1d1", "d2d2d2d2d2d2d2d2")):
            called = {"tool_input": {"description": f"lane {n}"}, "tool_response": {"agentId": lane}}
            _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 60), tool_name="Agent", **called)
            _event(store, repo, "SubagentStart", AGENT_SID, _stamp(now, 59), agent_id=lane)
            _event(store, repo, "PostToolUse", AGENT_SID, _stamp(now, 5), tool_name="Read", agent_id=lane)
        aside = P.Node("n9", "fix the readme typo", scope=[], aside=True, state=P.RUNNING, session_id=other)
        store.put_node(P.to_dict(aside))
        store.log_node("n9", _stamp(now, 30), "started", "claude:a51de000", other, None, {})
        _event(store, repo, "PostToolUse", other, _stamp(now, 20), tool_name="Edit")
        st = D.status(store, D.read(repo), now)
    live = next(n for n in st["nodes"] if n["id"] == "live")
    assert (live["running"], st["plan"]["running"]) == (3, 1)  # the session and its two lanes; one leaf
    assert next(w for w in st["sessions"] if w["short"] == "a51de000")["node"] is None
    assert D.head(st, "repo").startswith("you: 1 · 4 running")  # submission; the three, and the loose one


def _hook(where, **event) -> str:
    import io

    from graphene_map.hooks import hook_main

    said = io.StringIO()
    event = {"session_id": "5e55105e-0000", "cwd": str(where), **event}
    hook_main(io.StringIO(json.dumps(event)), where, said)
    return said.getvalue()


def test_an_agent_cannot_write_the_direction_itself_plan_or_no_plan(repo):  # noqa: F811
    """Review, 29 September: with no plan in force the hook let an agent's Edit of
    .graphene/direction.txt through, so it could turn its own "?" into "-". Graphene's own directory
    is written by `graphene` alone, plan or no plan; a write anywhere else is as it was."""
    agent("direction", "propose", "-", input=TREE)
    for path in (str(repo / D.FILE), D.FILE, str(repo / ".graphene" / "graphene.db")):
        said = _hook(repo, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": path})
        assert '"permissionDecision": "deny"' in said and "graphene direction propose" in said, path
    assert (
        _hook(repo, hook_event_name="PreToolUse", tool_name="Write", tool_input={"file_path": "api.py"}) == ""
    )
    assert _hook(repo, hook_event_name="PreToolUse", tool_name="Read", tool_input={"file_path": D.FILE}) == ""
    with Store.open(repo) as store:
        denied = store.node_log("*", ("denied",))
    assert [e["detail"] for e in denied][-1] == {"path": ".graphene/graphene.db", "how": "graphene's own"}


def test_a_direction_proposal_from_a_leafs_shell_is_not_that_leafs_stray(repo):  # noqa: F811
    """With the vendor's list of what a shell command changed, a `graphene direction propose` run by
    an agent holding a leaf was refused after the fact as a change outside its scope."""
    agent("plan", "propose", "-", input="goal: g\n- one  [one]\n    scope: api.py\n    check: true\n")
    person("plan", "accept")
    assert agent("node", "start", "one").exit_code == 0
    agent("direction", "propose", "-", input=TREE)
    changed = {"stdout": "", "bashEditDiff": {"changedFiles": [str(repo / D.FILE)]}}
    command = {"command": "graphene direction propose - <<'EOF' … EOF"}
    said = _hook(
        repo,
        session_id=AGENT_SID,
        hook_event_name="PostToolUse",
        tool_name="Bash",
        tool_use_id="t1",
        tool_input=command,
        tool_response=changed,
    )
    assert said == ""


def test_the_empty_direction_teaches_the_persons_form_and_a_write_says_how_to_commit_an_ignored_file(repo):  # noqa: F811
    """Walkers: the empty state taught only an agent's `? title  [id]` (the `-` form was in the error
    alone); the hint that hangs the plan was cut at 80 columns; and a propose said "git ignores
    .graphene/direction.txt here" while the module said the file is tracked by git."""
    empty = person("direction")
    assert empty.exit_code == 1 and "Write it yourself, one line a node: `- title  [id]`" in empty.stderr
    (repo / ".graphene").mkdir(exist_ok=True)
    (repo / D.FILE).write_text("- every supplier feed lands in one table  [feeds]\n")
    agent("plan", "propose", "-", input=PLAN)
    person("plan", "accept")
    shown = " ".join(person("direction", "--width", "80").stdout.split())
    assert "`graphene direction plan NODE` hangs the plan" in shown
    quiet = agent("direction", "propose", "-", input="? more  [more]\n")
    assert quiet.exit_code == 0 and "git ignores" not in quiet.stderr
    (repo / ".gitignore").write_text(".graphene/\n")
    said = agent("direction", "propose", "-", input="? again  [again]\n")
    assert f"`git add -f {D.FILE}`" in said.stderr and "`.graphene/*`" in said.stderr


def test_the_hook_refuses_a_write_into_graphenes_own_directory_however_it_is_spelled(repo):  # noqa: F811
    """Closing review, 29 September: the refusal went by the path's spelling, so `.GRAPHENE/` on a
    disk that ignores case, the /System/Volumes/Data firmlink, or a link to .graphene/ let an agent's
    Edit accept its own node. It is decided by what the directory is."""
    import os

    agent("direction", "propose", "-", input=TREE)
    os.symlink(".graphene", repo / "lnk")
    spellings = [str(repo / "lnk" / "direction.txt"), str(repo / "src" / ".." / D.FILE)]
    if (repo / ".GRAPHENE").exists():  # a disk that ignores case (a Mac's)
        spellings.append(str(repo / ".GRAPHENE" / "direction.txt"))
    firm = "/System/Volumes/Data" + str(repo.resolve())
    if os.path.exists(firm):
        spellings.append(firm + "/.graphene/direction.txt")
    for path in spellings:
        said = _hook(repo, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": path})
        assert '"permissionDecision": "deny"' in said, path
    assert (
        _hook(repo, hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "graphene.txt"})
        == ""
    )


def test_an_agents_recorded_words_reach_the_terminal_without_an_escape(repo):  # noqa: F811
    """Closing review finding 19: a Bash call's description carrying OSC 52 (a clipboard write) and
    OSC 0 (the window's title) was printed raw by `graphene direction`."""
    agent("direction", "propose", "-", input=TREE)
    now = datetime.now(UTC)
    evil = "List files\x1b]52;c;cm0gLXJmIH4K\x07\x1b]0;owned\x07\u009b31m‮"
    with Store.open(repo) as store:
        _event(store, repo, "UserPromptSubmit", "e5c00000-0000", _stamp(now, 30), prompt="tidy\x1b[2J")
        _event(store, repo, "PostToolUse", "e5c00000-0000", _stamp(now, 20), tool_name="Bash",
               tool_input={"command": "ls", "description": evil})  # fmt: skip
    for width in ("80", "120"):
        said = person("direction", "--width", width).stdout
        assert "List files" in " ".join(said.split()) and "owned" in said  # the words stay; the escapes go
        assert not any(D._unsafe(c) for c in said.replace("\n", "")), width


def test_an_act_on_a_crlf_direction_file_changes_only_its_own_marks(repo, monkeypatch):  # noqa: F811
    """Closing review finding 15: the file was read with newline translation, so one accept rewrote
    every CRLF line ending as LF, and `edit` saved unchanged did the same."""
    (repo / ".graphene").mkdir(exist_ok=True)
    before = b"# ours\r\n- the product  [product]\r\n  ? live on the real service  [live]\r\n"
    before += b"  - the board  [board]\r\n"
    (repo / D.FILE).write_bytes(before)
    assert person("direction", "accept", "live").exit_code == 0
    assert (repo / D.FILE).read_bytes() == before.replace(b"? live", b"- live")
    editor = repo / "touch.sh"
    editor.write_text('#!/bin/sh\nprintf -- "  ? more  [more]\\r\\n" >> "$1"\n')
    editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(editor))
    assert person("direction", "edit").exit_code == 0
    assert (repo / D.FILE).read_bytes() == before.replace(b"? live", b"- live") + b"  ? more  [more]\r\n"
