"""The synthetic run of tests/fixtures/make_run_fixture.py, ingested the way the product ingests it:
from hook events, in a real git repository with both worktrees; and the hooks `graphene init` installs.
"""

import io
import json
import sys
from pathlib import Path

import pytest

from graphene_map.graph import build_graph
from graphene_map.hooks import (
    HOOK_COMMAND,
    HOOK_EVENTS,
    hook_main,
    ingest_hook_event,
    install_hooks,
)
from graphene_map.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_run_fixture as run  # noqa: E402

S2 = run.S2


@pytest.fixture
def scenario(tmp_path):
    """The run's git repo, with both worktrees."""
    repo, elsewhere = tmp_path / "repo", tmp_path / "wt-api"
    run.build_repo(repo, elsewhere)
    return repo, elsewhere


# 1 -- the live hooks ------------------------------------------------------------------------------


def test_hook_events_record_the_agent_its_cwd_and_the_worktree_copy(scenario):
    repo, elsewhere = scenario
    with Store.open(repo) as store:
        for timestamp, event in run.hook_events(root=str(repo), elsewhere=str(elsewhere)):
            ingest_hook_event(store, event, repo, timestamp)
        events = store.events(S2)
        (helper,) = store.agents(S2)
        assert store.session(S2) is not None

    assert (helper.id, helper.type, helper.cwd) == (run.SH, "general-purpose", str(elsewhere))
    assert (helper.started_at, helper.ended_at) == (run.stamp("09:35:35"), run.stamp("09:37:35"))
    assert all(e.cwd == str(elsewhere) for e in events)
    edit = next(e for e in events if e.id == "toolu_s2_edit")
    assert edit.file_path == "app/api.py"  # written in the worktree, filed against what it copies


def test_a_hook_event_from_inside_a_worktree_lands_in_the_main_repos_store(scenario):
    repo, elsewhere = scenario
    events = dict(run.hook_events(root=str(repo), elsewhere=str(elsewhere)))
    start = next(e for e in events.values() if e["hook_event_name"] == "SessionStart")
    assert hook_main(io.StringIO(json.dumps(start)), cwd=elsewhere) == 0
    assert not (elsewhere / ".graphene").exists()
    with Store.open(repo) as store:
        assert store.session(S2) is not None


def test_a_bad_event_from_inside_a_worktree_logs_to_the_main_repo_and_leaves_the_worktree_alone(scenario):
    repo, elsewhere = scenario
    assert hook_main(io.StringIO("this is not json"), cwd=elsewhere) == 0
    assert not (elsewhere / ".graphene").exists()
    assert "Traceback" in (repo / ".graphene" / "ingest.log").read_text()


def test_an_agent_id_in_an_unknown_shape_is_kept_as_written_not_read_as_the_main_agent(scenario):
    repo, _ = scenario
    call = {"hook_event_name": "PostToolUse", "session_id": "odd", "tool_name": "Bash", "tool_use_id": "t1"}
    with Store.open(repo) as store:
        assert ingest_hook_event(store, call | {"agent_id": 42, "tool_input": {"command": "ls"}}, repo)
        assert [e.agent_id for e in store.events("odd")] == ["42"]


def test_a_subagent_lane_is_named_by_what_the_hooks_recorded(scenario):
    """The Agent call that spawned it names it in its response and carries its task and prompt, its
    SubagentHandback call carries its closing words, and SubagentStart's cwd is its worktree: the
    lane has them all, and its spawn link starts at that Agent call, with no transcript read."""
    repo, elsewhere = scenario
    with Store.open(repo) as store:
        for timestamp, event in run.hook_events(root=str(repo), elsewhere=str(elsewhere)):
            ingest_hook_event(store, event, repo, timestamp)
        graph = build_graph(store, [S2])

    lane = next(lane for lane in graph.lanes if lane.agent == run.SH)
    assert (lane.task, lane.prompt, lane.closing) == ("Lint the API", run.TASK_SH, run.CLOSE_SH)
    assert lane.worktree == str(elsewhere)
    spawned = next(link for link in graph.links if link.kind == "spawned" and link.target == lane.id)
    assert spawned.ref == f"event:{S2[:8]}:toolu_s2_agent"
    assert spawned.source in {mark.id for mark in graph.marks}  # the call's mark, not the lane


def test_a_shell_write_in_a_subagents_worktree_is_filed_against_the_file_it_copies(scenario):
    """A command's list of changed files names the worktree's copy; the worktree SubagentStart
    recorded maps it back to the repo's file, flagged as a copy, not a file under .claude/."""
    repo, _ = scenario
    worktree = str(repo / run.WT_REL)
    sid, agent = "44444444-0000-4000-8000-000000000001", "aaaa1111"
    events = [
        {"hook_event_name": "SessionStart", "cwd": str(repo)},
        {"hook_event_name": "UserPromptSubmit", "cwd": str(repo), "prompt": "change core", "prompt_id": "p1"},
        {"hook_event_name": "SubagentStart", "cwd": worktree, "agent_id": agent, "agent_type": "helper"},
        {
            "hook_event_name": "PostToolUse",
            "cwd": worktree,
            "agent_id": agent,
            "tool_use_id": "t1",
            "tool_name": "Bash",
            "tool_input": {"command": "sed -i '' s/1/2/ app/core.py"},
            "tool_response": {"stdout": "", "bashEditDiff": {"changedFiles": [f"{worktree}/app/core.py"]}},
        },
        {"hook_event_name": "SubagentStop", "cwd": worktree, "agent_id": agent},
        {"hook_event_name": "Stop", "cwd": str(repo)},
    ]
    with Store.open(repo) as store:
        for second, event in enumerate(events):
            ingest_hook_event(store, event | {"session_id": sid}, repo, f"2026-01-01T10:00:0{second}.000Z")
        graph = build_graph(store, [sid])

    assert [row.path for row in graph.rows] == ["app", "app/core.py"]
    (change,) = [mark for mark in graph.marks if mark.kind == "change"]
    assert change.copy
    assert next(lane for lane in graph.lanes if lane.agent == agent).worktree == worktree


# 2 -- init ----------------------------------------------------------------------------------------


def ours(events: list[str]) -> str:
    handler = [{"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 5}]}]
    return json.dumps({"hooks": {event: list(handler) for event in events}}, indent=2)


def test_init_adds_the_new_events_to_the_file_that_already_holds_ours(tmp_path):
    (tmp_path / ".claude").mkdir()
    team = tmp_path / ".claude" / "settings.json"
    team.write_text(ours(["SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop"]))
    assert install_hooks(tmp_path) == ["PreToolUse", "SubagentStart", "SubagentStop"]
    assert list(json.loads(team.read_text())["hooks"]) == [
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
        "PreToolUse",
        "SubagentStart",
        "SubagentStop",
    ]
    assert not (tmp_path / ".claude" / "settings.local.json").exists()  # never in both files
    assert install_hooks(tmp_path) == []


def test_init_writes_every_event_into_a_fresh_repos_personal_file(tmp_path):
    assert install_hooks(tmp_path) == list(HOOK_EVENTS)
    settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    assert list(settings["hooks"]) == list(HOOK_EVENTS)
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert install_hooks(tmp_path) == []
