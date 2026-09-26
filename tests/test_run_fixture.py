"""The synthetic run fixture from tests/fixtures/make_run_fixture.py: it derives the same data
every time, it invents every path, its SHAs are the ones a real git repo produces, and what
``load()`` puts in a store is the ground truth the graph golden is built from."""

import getpass
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graphene_map.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_run_fixture as run  # noqa: E402

S1, S2 = run.S1, run.S2
SHA7 = re.compile(r"\b[0-9a-f]{7}\b")


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """The scenario's git repo, built once: name -> sha, and the repo root."""
    base = tmp_path_factory.mktemp("scenario")
    return run.build_repo(base / "repo", base / "wt-api"), base / "repo"


def git(root, *args):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return proc.stdout


# 1 -- determinism ------------------------------------------------------------------------------


def test_deriving_twice_gives_the_same_data():
    assert run.hook_events() == run.hook_events()
    assert run.expected() == run.expected()


def test_every_timestamp_is_distinct_within_an_agent():
    for turn in run._scenario(run.ROOT, run.ELSEWHERE):
        stamps = [turn.started] + ([turn.ended] if turn.id is None else [])
        stamps += [t for step in turn.steps for t in (step.at, step.done)]
        assert len(set(stamps)) == len(stamps), f"{turn.id or 'main'} reuses a timestamp"


# 2 -- nothing of this machine -------------------------------------------------------------------


def test_nothing_comes_from_this_machine():
    user = getpass.getuser()
    blobs = [
        json.dumps(run.hook_events(), default=str),
        json.dumps(run.expected(), default=str),
        json.dumps(run.SHAS),
    ]
    for blob in blobs:
        assert "/Users/" not in blob
        assert f"/{user}" not in blob and f"-{user}-" not in blob
        assert str(Path.home()) not in blob


# 3 -- the real repo -----------------------------------------------------------------------------


def test_build_repo_produces_the_pinned_shas(repo):
    built, root = repo
    assert built == run.SHAS
    logged = git(root, "log", "--all", "--format=%H").split()
    assert set(run.SHAS.values()) <= set(logged)


def test_build_repo_makes_both_worktrees(repo):
    _, root = repo
    listing = git(root, "worktree", "list", "--porcelain")
    assert f"branch refs/heads/{run.W3_BRANCH}" in listing
    assert f"branch refs/heads/{run.API_BRANCH}" in listing
    assert str(root / run.WT_REL) in listing


def test_the_cherry_pick_carries_the_same_patch(repo):
    _, root = repo
    assert git(root, "show", "--format=", "-p", run.sha("cp")) == git(
        root, "show", "--format=", "-p", run.sha("w3")
    )


def test_the_repo_agrees_with_the_expected_commits(repo):
    _, root = repo
    for commit in run.expected()["commits"]:
        names = git(root, "show", "--format=", "--name-only", commit.sha).split()
        assert names == [path for path, _ in commit.files]
        assert git(root, "log", "-1", "--format=%s", commit.sha).strip() == commit.subject


# 4 -- the SHA prefixes the recorded calls embed -------------------------------------------------


def test_rendered_sha_prefixes_belong_to_the_right_commit():
    for turn in run._scenario(run.ROOT, run.ELSEWHERE):
        for step in turn.steps:
            if step.commit:
                response = json.dumps(step.result if step.result is not None else step.text)
                assert run.short(step.commit) in response, f"{step.id} names the wrong commit"
            if step.origin:
                assert run.short(step.origin) in json.dumps(step.input)


def test_no_recorded_hex_token_is_a_stray_sha():
    prefixes = {sha[:7] for sha in run.SHAS.values()}
    for turn in run._scenario(run.ROOT, run.ELSEWHERE):
        said = [turn.prompt, turn.task, turn.closing]
        for step in turn.steps:
            for token in SHA7.findall(json.dumps([*said, step.input, step.text, step.result], default=str)):
                assert token in prefixes, f"{step.id} holds {token}, which is no commit of this run"


# 5 -- the store ---------------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    with Store.open(tmp_path) as opened:
        run.load(opened)
        yield opened


def test_load_writes_both_sessions(store):
    assert [s.id for s in store.sessions()] == [S1, S2]
    assert store.prompts(S1)[0].id == run.P1
    assert store.session(S1).head_at_start == run.sha("base")


def test_load_writes_every_agent_as_designed(store):
    assert len(store.agents(S1)) == 8
    assert len(store.agents(S2)) == 1
    by_id = {a.id: a for a in store.agents(S1) + store.agents(S2)}
    assert by_id == {a.id: a for a in run.expected()["agents"]}

    w3, a2, w5 = by_id[run.W3], by_id[run.A2], by_id[run.W5]
    assert w3.workflow_run == run.RUN and w3.phase == "Build" and w3.parent_tool_use_id is None
    assert w3.worktree == f"{run.ROOT}/{run.WT_REL}" and w3.task == "Build the CLI"
    assert a2.parent_tool_use_id == "toolu_ag2" and a2.workflow_run is None
    assert a2.worktree == run.ELSEWHERE and a2.closing == run.CLOSE_A2
    assert w5.phase == "Verify" and w5.closing == run.CLOSE_W5


def test_load_writes_the_commits_of_the_window(store):
    start, end = run.expected()["notes"]["windows"][S1]
    got = store.commits_between(start, end)
    assert got == run.expected()["commits"]
    assert len(got) == 9
    by_sha = {c.sha: c for c in got}
    assert by_sha[run.sha("cp")].agent_id == run.W3
    assert by_sha[run.sha("cp")].origin_sha == run.sha("w3")
    assert by_sha[run.sha("unrec")].agent_id is None
    assert by_sha[run.sha("unrec")].session_id is None


def test_load_writes_every_event_with_its_cwd(store):
    got = [
        {
            "id": e.id,
            "session_id": e.session_id,
            "agent_id": e.agent_id,
            "tool": e.tool,
            "timestamp": e.timestamp,
            "file_path": e.file_path,
            "cwd": e.cwd,
            "success": e.success,
        }
        for sid in (S1, S2)
        for e in store.events(sid)
    ]
    assert sorted(got, key=lambda e: (e["session_id"], e["timestamp"])) == run.expected()["events"]


def test_a_worktree_copy_is_stored_repo_relative(store):
    worktrees = {f"{run.ROOT}/{run.WT_REL}", run.ELSEWHERE}
    seen = 0
    for sid in (S1, S2):
        for event in store.events(sid):
            if event.cwd in worktrees and event.file_path:
                assert not os.path.isabs(event.file_path), event.id
                seen += 1
    assert seen == 5  # w3's cli.py, a2's api.py, its test twice, S2's api.py


def test_a_write_outside_the_repo_keeps_only_its_path(store):
    outside = next(e for e in store.events(S1) if e.id == "toolu_a1_outside")
    assert outside.file_path == "/home/dev/notes/plan.md"
    assert outside.input == {"file_path": "/home/dev/notes/plan.md"}
    assert outside.response is None and outside.new_content is None


# 6 -- what the hooks deliver --------------------------------------------------------------------


def test_hook_events_carry_what_the_hooks_deliver():
    events = run.hook_events()
    names = [e["hook_event_name"] for _, e in events]
    assert names[0] == "SessionStart" and names[-1] == "Stop"
    assert {"UserPromptSubmit", "SubagentStart", "SubagentStop", "PostToolUse"} <= set(names)
    assert all(e["session_id"] == S2 for _, e in events)
    calls = [e for _, e in events if e["hook_event_name"] == "PostToolUse"]
    assert len(calls) == 4
    assert {e["tool_use_id"] for e in calls if e.get("agent_id")} == {"toolu_sh_lint", "toolu_sh_back"}
