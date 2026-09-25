"""The synthetic run of tests/fixtures/make_run_fixture.py, ingested the way the product ingests it:
from hook events, in a real git repository with both worktrees; and the hooks `graphene init` installs.
"""

import io
import json
import sys
from pathlib import Path

import pytest

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
