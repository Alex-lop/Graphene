"""Do the hooks fire for every agent? A write outside the task's files, and one inside, for each kind.

Rows 1-3 (a Claude Code session, its subagent, an agent of a Claude Code workflow) are driven through
hook_main with the event each sends. The shapes are the real ones: the probes in
dev/process/graph-edit/probes/ ran Claude Code 2.1.322 on Haiku and saw one session_id for all three,
an `agent_id` on the subagent's and the workflow agent's calls,
and `agent_type` "general-purpose" and "workflow-subagent".
Rows 4-5 (Codex, any other command) run a stand-in through `graphene run`'s own path. Row 6 (an editor's own
agent, with no Graphene launch) is what is true when no hook is called: nothing stops the write."""

import io
import json
import os
import stat
import subprocess
import sys
import textwrap

import pytest

from graphene_map import plan
from graphene_map.hooks import hook_main
from graphene_map.plan import DONE, Caller
from graphene_map.run import run_plan
from graphene_map.store import Store

SID = "5e55105e-0000-4000-8000-0000000000e1"
ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, SID)
SUBAGENT = {"agent_id": "a61c1a91256e15813", "agent_type": "general-purpose"}
WORKFLOW = {"agent_id": "aa701fb8f749b11ca", "agent_type": "workflow-subagent"}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "inside.txt").write_text("i\n")
    (tmp_path / ".gitignore").write_text(".graphene/\n")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def hold(repo):
    """The task `inside only` (files: inside.txt), held by the session SID, as `graphene run` holds a leaf."""
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "inside only", "scope": ["inside.txt"], "check": "true"}], ALEX)
        plan.start(store, "n1", BOT, repo)


def hook(repo, name, session=SID, **extra) -> dict | None:
    event = {"session_id": session, "cwd": str(repo), "hook_event_name": name, **extra}
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


def write(repo, rel, who=None, session=SID, cwd=None):
    path = str((cwd or repo) / rel)
    return hook(repo, "PreToolUse", session, tool_name="Write", tool_input={"file_path": path}, **(who or {}))


def denied(repo):
    with Store.open(repo) as store:
        return store.node_log("n1", ("denied",))


def verdict(answer) -> str:
    return answer["hookSpecificOutput"]["permissionDecision"] if answer else "silence"


@pytest.mark.parametrize(
    "who, row",
    [(None, "a session"), (SUBAGENT, "its subagent (Agent tool)"), (WORKFLOW, "a workflow's agent")],
)
def test_rows_1_to_3_a_write_outside_the_files_is_refused_and_logged_inside_is_let_through(repo, who, row):
    hold(repo)
    assert write(repo, "inside.txt", who) is None  # silence: the person's own permission rules still apply
    answer = write(repo, "outside.txt", who)
    assert verdict(answer) == "deny", row
    assert "outside.txt is outside the scope of the node you hold (n1: inside.txt)" in (
        answer["hookSpecificOutput"]["permissionDecisionReason"]
    )
    [row_] = denied(repo)
    assert row_["detail"] == {"path": "outside.txt", "how": "Write"}
    assert row_["agent_id"] == (who or {}).get("agent_id")  # the log says whose call it was


def test_row_2_and_3_a_subagent_or_workflow_agent_cannot_write_outside_through_the_shell_either(repo):
    hold(repo)
    for who in (SUBAGENT, WORKFLOW):
        bad = {"command": "echo hi > outside.txt"}
        out = hook(repo, "PreToolUse", tool_name="Bash", tool_input=bad, **who)
        assert verdict(out) == "deny"
        ok = {"command": "echo ok > inside.txt"}
        assert hook(repo, "PreToolUse", tool_name="Bash", tool_input=ok, **who) is None
    assert [r["agent_id"] for r in denied(repo)] == [SUBAGENT["agent_id"], WORKFLOW["agent_id"]]


def test_row_3_a_workflow_agent_in_its_own_worktree_is_judged_by_the_path_inside_it(repo, tmp_path_factory):
    hold(repo)
    tree = tmp_path_factory.mktemp("wt") / "tree"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(tree)], check=True)
    assert write(repo, "inside.txt", WORKFLOW, cwd=tree) is None
    assert verdict(write(repo, "outside.txt", WORKFLOW, cwd=tree)) == "deny"


def test_row_3_a_call_from_a_session_that_holds_nothing_is_refused_not_let_through(repo):
    """Should a workflow's agent ever send a session_id the task is not held under, the gate does not guess:
    a session with no task has no files, so its write is refused and logged on the plan, not on n1."""
    hold(repo)
    stranger = "00000000-0000-4000-8000-00000000dead"
    answer = write(repo, "inside.txt", WORKFLOW, session=stranger)
    assert verdict(answer) == "deny"
    assert denied(repo) == []
    with Store.open(repo) as store:
        [row] = store.node_log("*", ("denied",))
        assert row["session_id"] == stranger and row["agent_id"] == WORKFLOW["agent_id"]


def _stand_in(repo, name="agent.py"):
    """A scripted agent: writes inside.txt (its file) and outside.txt (not), as any CLI agent might."""
    script = repo.parent / f"{repo.name}-{name}"
    script.write_text(textwrap.dedent("""
        import pathlib
        pathlib.Path("inside.txt").write_text("changed\\n")
        pathlib.Path("outside.txt").write_text("not mine\\n")
    """))
    return script


def _run(repo, template):
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "inside only", "scope": ["inside.txt"], "check": "true"}], ALEX)
        said = []
        done = run_plan(store, repo, template, 1, None, said.append, repo / ".graphene" / "runs")
        node = plan.get(store, "n1")
        return done, node, " ".join(said), store.node_log("n1", ("denied", "breach"))


def test_row_5_another_cli_agent_is_not_stopped_at_the_write_but_the_finish_hands_the_task_back(repo):
    script = _stand_in(repo)
    done, node, said, hooks_said = _run(repo, f"{sys.executable} {script}")
    assert done == [] and node.state != DONE  # the task came back, not done
    assert "outside.txt" in said  # the refusal names the path
    assert hooks_said == []  # the gate refused nothing before the write: the log has no `denied` row for it
    # "caught at the finish" is the whole of it: run in the checkout, the outside file is on disk until the
    # person puts it back (in `run --parallel` it is in the leaf's worktree, which is not merged)
    assert (repo / "outside.txt").exists()


def test_row_4_codex_runs_the_same_path_with_its_own_command_line(repo, tmp_path_factory):
    """No live Codex here. A stand-in named `codex` takes `exec --json --sandbox workspace-write <prompt>` as
    the real one does, so `graphene run` meters and judges it by the Codex branch."""
    bindir = tmp_path_factory.mktemp("bin")
    fake = bindir / "codex"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} {_stand_in(repo)}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    old = os.environ["PATH"]
    os.environ["PATH"] = f"{bindir}{os.pathsep}{old}"
    try:
        done, node, said, hooks_said = _run(repo, "codex exec --json --sandbox workspace-write")
    finally:
        os.environ["PATH"] = old
    assert done == [] and node.state != DONE
    assert "outside.txt" in said and hooks_said == []  # named at the finish; nothing refused before the write
    assert (repo / "outside.txt").exists()  # so the write landed, as row 5's does


def test_row_5_a_stand_in_that_writes_only_inside_is_done(repo):
    script = repo.parent / f"{repo.name}-good.py"
    script.write_text('import pathlib\npathlib.Path("inside.txt").write_text("changed\\n")\n')
    done, node, _, _ = _run(repo, f"{sys.executable} {script}")
    assert [n.id for n in done] == ["n1"] and node.state == DONE


def test_row_6_an_editors_own_agent_with_no_hook_is_not_stopped_and_only_a_held_task_notices(repo):
    """Cursor's agent or Copilot in VS Code writing in the folder: unless the editor calls Graphene's hook, no
    Graphene code runs at the write. Here the write is a plain one with no hook call, as it would be then."""
    hold(repo)
    (repo / "outside.txt").write_text("an editor's agent wrote this\n")
    assert (repo / "outside.txt").exists()  # nothing stopped it
    assert denied(repo) == []  # and nothing was recorded
    with Store.open(repo) as store:
        with pytest.raises(plan.Refused) as no:
            plan.finish(store, "n1", BOT)  # the task is held: git sees the change at `done`
    assert "outside.txt" in str(no.value)


def test_row_6_with_no_task_held_an_editors_agent_is_never_seen_at_all(repo):
    (repo / "outside.txt").write_text("x\n")
    assert write(repo, "outside.txt") is None  # even a loaded hook has no contract to enforce
    with Store.open(repo) as store:
        assert plan.nodes(store) == []
