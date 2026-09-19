"""The synthetic run of tests/fixtures/make_run_fixture.py, ingested the way the product ingests it:
from the transcripts, from the same transcripts once both worktrees are gone, and from hook events.

The ground truth is the fixture's own ``expected()``: every agent field, and every event's identity,
path, working directory and outcome.
"""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphene_debrief.record import changes
from graphene_debrief.sources import claude_code
from graphene_debrief.sources.claude_code import (
    HOOK_COMMAND,
    HOOK_EVENTS,
    backfill,
    hook_main,
    ingest_hook_event,
    install_hooks,
    project_dir_name,
    project_dirs,
)
from graphene_debrief.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_run_fixture as run  # noqa: E402

S1, S2 = run.S1, run.S2


@pytest.fixture
def scenario(tmp_path):
    """The run's git repo with both worktrees, and its transcripts under a projects directory."""
    repo, elsewhere = tmp_path / "repo", tmp_path / "wt-api"
    run.build_repo(repo, elsewhere)
    projects = tmp_path / "projects"
    for rel, text in run.render(root=str(repo), elsewhere=str(elsewhere)).items():
        out = projects / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return repo, elsewhere, projects


def load(repo: Path, projects: Path, into: Path):
    """Backfill the run into a store of its own; returns (report, agents, events, sessions)."""
    into.mkdir(exist_ok=True)
    with Store.open(into) as store:
        report = backfill(store, repo, projects=projects)
        agents = store.agents(S1) + store.agents(S2)
        events = [e for sid in (S1, S2) for e in store.events(sid)]
        return report, agents, [_row(e) for e in events], store.sessions()


def _row(event) -> dict:
    return {
        "id": event.id,
        "session_id": event.session_id,
        "agent_id": event.agent_id,
        "tool": event.tool,
        "timestamp": event.timestamp,
        "file_path": event.file_path,
        "cwd": event.cwd,
        "success": event.success,
    }


def _sorted(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r["session_id"], r["timestamp"]))


def remove_worktrees(repo: Path, elsewhere: Path) -> None:
    """Both worktrees, gone: the branches stay, and so does everything the agents recorded."""
    for path in (repo / run.WT_REL, elsewhere):
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, check=True)
    assert not elsewhere.exists() and not (repo / run.WT_REL).exists()
    claude_code._worktree_main.cache_clear()  # this process asked git's files before the removal


# a -- round trip from the transcripts ------------------------------------------------------------


def test_the_run_round_trips_from_its_transcripts(scenario):
    repo, elsewhere, projects = scenario
    report, agents, rows, sessions = load(repo, projects, repo)
    expected = run.expected(root=str(repo), elsewhere=str(elsewhere))

    assert sorted(s.id for s in sessions) == sorted([S1, S2])
    assert (sorted(report.added), report.other_repo, report.failed) == (sorted([S1, S2]), [], [])
    assert agents == expected["agents"]  # every field of every agent, in started order
    assert _sorted(rows) == expected["events"]
    assert dict(report.skipped_records) == {}  # journal.jsonl is read as a journal, not skipped


def test_the_second_session_is_found_only_through_its_working_directory(scenario):
    """S2 ran in the worktree outside the repo, so its project directory is named after that
    worktree: no prefix of the repo's name reaches it."""
    repo, elsewhere, projects = scenario
    mine, others = project_dirs(repo, projects)
    assert [d.name for d in mine] == [project_dir_name(repo)]
    assert [d.name for d in others] == [project_dir_name(elsewhere)]
    _, agents, _, sessions = load(repo, projects, repo)
    assert S2 in [s.id for s in sessions]
    assert [a.id for a in agents if a.session_id == S2] == [run.SH]


def test_subagent_files_filed_under_another_project_directory_still_belong_to_their_session(scenario):
    """A project directory can hold ``<session>/subagents/`` and no transcript of that session: the
    id says whose those agents are."""
    repo, elsewhere, projects = scenario
    moved = projects / project_dir_name(elsewhere) / S1
    moved.parent.mkdir(parents=True, exist_ok=True)
    (projects / project_dir_name(repo) / S1).rename(moved)
    _, agents, rows, _ = load(repo, projects, repo)
    assert agents == run.expected(root=str(repo), elsewhere=str(elsewhere))["agents"]
    assert _sorted(rows) == run.expected(root=str(repo), elsewhere=str(elsewhere))["events"]


def test_a_relative_path_resolves_through_the_working_directory_it_was_written_in(scenario):
    repo, elsewhere, projects = scenario
    with Store.open(repo) as store:
        backfill(store, repo, projects=projects)
        events, agents = store.events(S1), store.agents(S1)
    edit = next(e for e in events if e.id == "toolu_a2_edit")
    assert edit.input["file_path"] == "tests/test_api.py"  # what the agent recorded: no directory
    assert edit.cwd == str(elsewhere)
    assert edit.file_path == "tests/test_api.py"  # the path in the repo the worktree copies
    written, _ = changes(events, agents, str(repo))
    copy = next(c for c in written if c.event_id == "toolu_a2_edit")
    assert (copy.path, copy.copy) == ("tests/test_api.py", True)  # only the cwd can say that


# b -- the same run once the worktrees are gone ----------------------------------------------------


def test_the_run_still_maps_once_the_worktrees_are_removed(scenario, tmp_path):
    repo, elsewhere, projects = scenario
    remove_worktrees(repo, elsewhere)
    report, agents, rows, sessions = load(repo, projects, tmp_path / "later")
    expected = run.expected(root=str(repo), elsewhere=str(elsewhere))

    assert sorted(s.id for s in sessions) == sorted([S1, S2])
    assert agents == expected["agents"]
    assert _sorted(rows) == expected["events"]
    assert report.other_repo == []


def test_a_worktree_only_a_working_directory_records_comes_from_the_history(scenario, tmp_path):
    """Many real Workflow agents have a meta.json of two fields, so once the worktree is gone the
    only record of it left is the working directory in the agent's own transcript. It is taken for
    a worktree of this repo only because the repo's history holds what was written in it."""
    repo, elsewhere, projects = scenario
    stripped = 0
    for meta in sorted(projects.rglob("*.meta.json")):
        held = json.loads(meta.read_text(encoding="utf-8"))
        stripped += bool(held.pop("worktreePath", None))
        held.pop("worktreeBranch", None)
        held.pop("spawnedWithWorktree", None)
        meta.write_text(json.dumps(held, indent=2) + "\n", encoding="utf-8")
    assert stripped == 2  # the two agents that were spawned with a worktree said so, and now do not
    remove_worktrees(repo, elsewhere)
    _, agents, rows, _ = load(repo, projects, tmp_path / "later")
    assert agents == run.expected(root=str(repo), elsewhere=str(elsewhere))["agents"]
    written = {r["id"]: r["file_path"] for r in rows}
    assert written["toolu_w3_write"] == "app/cli.py"  # not .claude/worktrees/agent-w3/app/cli.py
    assert written["toolu_a2_write"] == "app/api.py"


def test_a_directory_that_was_never_a_worktree_stays_outside(scenario, tmp_path):
    repo, elsewhere, projects = scenario
    remove_worktrees(repo, elsewhere)
    _, _, rows, _ = load(repo, projects, tmp_path / "later")
    outside = next(r for r in rows if r["id"] == "toolu_a1_outside")
    assert outside["file_path"] == "/home/dev/notes/plan.md"  # absolute: no worktree ever held it


# c -- the live hooks ------------------------------------------------------------------------------


def test_hook_events_record_the_agent_its_cwd_and_the_worktree_copy(scenario):
    repo, elsewhere, projects = scenario
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
    repo, elsewhere, _ = scenario
    events = dict(run.hook_events(root=str(repo), elsewhere=str(elsewhere)))
    start = next(e for e in events.values() if e["hook_event_name"] == "SessionStart")
    assert hook_main(io.StringIO(json.dumps(start)), cwd=elsewhere) == 0
    assert not (elsewhere / ".graphene").exists()
    with Store.open(repo) as store:
        assert store.session(S2) is not None


# d -- init ----------------------------------------------------------------------------------------


def ours(events: list[str]) -> str:
    handler = [{"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 5}]}]
    return json.dumps({"hooks": {event: list(handler) for event in events}}, indent=2)


def test_init_adds_the_two_new_events_to_the_file_that_already_holds_ours(tmp_path):
    (tmp_path / ".claude").mkdir()
    team = tmp_path / ".claude" / "settings.json"
    team.write_text(ours(["SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop"]))
    assert install_hooks(tmp_path) == ["SubagentStart", "SubagentStop"]
    assert list(json.loads(team.read_text())["hooks"]) == [
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
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
