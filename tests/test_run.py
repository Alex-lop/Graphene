"""`graphene run`: Graphene hands each ready node to an executor and decides itself what is done. The
executor here is a script, so every ending is on purpose: stray write then repair, never repairs,
hands the node back, finishes by itself."""

import subprocess
import sys

import pytest

from graphene_debrief import plan
from graphene_debrief.plan import DONE, OPEN, Caller
from graphene_debrief.run import command_for, run_plan
from graphene_debrief.store import Store

ALEX = Caller("alex", True)

# What a sloppy executor does: the work, plus a file nobody asked for. Told it was refused, it cleans up.
SLOPPY = """
import pathlib, sys
prompt = sys.argv[-1]
pathlib.Path("api.py").write_text("def users():\\n    return ids\\n")
stray = pathlib.Path("schema.py")
if "not accepted" in prompt:
    stray.write_text("TABLES = []\\n")
else:
    stray.write_text("TABLES = ['sneaky']\\n")
"""
STUBBORN = "import pathlib; pathlib.Path('schema.py').write_text('again')"
HANDS_BACK = """
import os, subprocess, sys
cli = "import sys; from graphene_debrief.cli import app; sys.argv[0] = 'graphene'; app()"
argv = [sys.executable, "-c", cli, "node", "release", os.environ["GRAPHENE_NODE"], "--why", "needs schema.py"]
subprocess.run(argv, check=True, env={**os.environ, "GRAPHENE_AS": "agent:script"})
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "api.py").write_text("def users():\n    return []\n")
    (tmp_path / "schema.py").write_text("TABLES = []\n")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def executor(repo, source: str) -> str:
    script = repo.parent / f"{repo.name}-executor.py"  # beside the repo, so it is nobody's stray file
    script.write_text(source)
    return f"{sys.executable} {script}"


def users_node(**extra):
    return {"title": "users returns ids", "scope": ["api.py"], "check": "grep -q ids api.py", **extra}


def test_a_refused_executor_is_sent_back_with_the_refusal_and_the_node_is_done_when_the_boundary_says_so(
    repo,
):
    said = []
    with Store.open(repo) as store:
        plan.propose(store, [users_node(), users_node(title="a person's", owner="alex", scope=["x"])], ALEX)
        done = run_plan(store, repo, executor(repo, SLOPPY), say=said.append, logs=repo / ".graphene/runs")
        assert [n.id for n in done] == ["n1"] and plan.get(store, "n1").state == DONE
        assert [e["kind"] for e in store.node_log("n1")] == [
            "added", "started", "refused", "check_passed", "finished"
        ]  # fmt: skip
        assert plan.get(store, "n2").state == OPEN  # a person's node is never handed to an executor
    assert "n1 attempt 1 refused: n1 is not done: changed outside its scope (api.py): schema.py" in said[2]
    assert said[-1] == "n1 is done"
    assert (repo / ".graphene/runs/n1-2.txt").exists()


def test_out_of_attempts_the_node_is_handed_back_with_the_reason_and_the_run_moves_on(repo):
    said = []
    with Store.open(repo) as store:
        plan.propose(store, [users_node(), users_node(title="next", scope=["docs.md"], check="true")], ALEX)
        done = run_plan(store, repo, executor(repo, STUBBORN), attempts=2, say=said.append)
        assert done == [] and plan.get(store, "n1").state == OPEN
        [released] = store.node_log("n1", ("released",))
        assert released["detail"]["why"].startswith("2 attempts, the last one refused: n1 is not done")
        # n2 could not start either: what n1's executor left behind belongs to no node
        assert "n2 cannot start: schema.py changed while no node owned it" in " ".join(said)


def test_an_executor_that_hands_the_node_back_is_believed(repo):
    said = []
    with Store.open(repo) as store:
        plan.propose(store, [users_node()], ALEX)
        assert run_plan(store, repo, executor(repo, HANDS_BACK), say=said.append) == []
    assert "n1 handed back by the executor: needs schema.py" in said


def test_claude_is_told_which_session_it_is_and_resumed_on_a_second_attempt():
    first = command_for("claude -p --model sonnet", "do it", "abc", again=False)
    assert first == ["claude", "-p", "--model", "sonnet", "--session-id", "abc", "do it"]
    assert command_for("claude -p", "again", "abc", again=True) == [
        "claude",
        "-p",
        "--resume",
        "abc",
        "again",
    ]
    assert command_for("codex exec --sandbox workspace-write", "do it", "abc", again=True)[-1] == "do it"


def test_an_executor_that_is_not_installed_is_one_line_and_the_node_is_handed_back(repo):
    with Store.open(repo) as store:
        plan.propose(store, [users_node()], ALEX)
        with pytest.raises(plan.Refused, match="cannot run `no-such-executor-anywhere`"):
            run_plan(store, repo, "no-such-executor-anywhere --flag", say=lambda _: None)
        assert plan.get(store, "n1").state == OPEN  # not left running with nobody on it
        assert "could not be started" in store.node_log("n1", ("released",))[0]["detail"]["why"]


GROWER = """
import pathlib, time
from graphene_debrief import plan
from graphene_debrief.store import Store
pathlib.Path("api.py").write_text("def users():\\n    return ids\\n")
with Store.open(pathlib.Path(".")) as store:
    more = {"title": "more", "scope": [f"more{time.time_ns()}.py"], "check": "true"}
    plan.propose(store, [more], plan.Caller("dev", True))
"""


def test_a_plan_that_grows_while_the_run_is_going_does_not_make_the_run_unbounded(repo):
    with Store.open(repo) as store:
        plan.propose(store, [users_node()], ALEX)
        done = run_plan(store, repo, executor(repo, GROWER), say=lambda _: None)
        assert [n.id for n in done] == ["n1"]
        assert [n.state for n in plan.nodes(store)] == [DONE, OPEN]  # the new node waits for the next run
