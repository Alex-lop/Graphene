"""A forked hold as the hooks and an agent's own commands meet it: the Node's `forked` field names each
fork's session and tree; the gate and `_holder_only` find the held leaf for a fork's session; a fork's own
`graphene node done` judges its own tree and records its verdict without changing the leaf's state; its
`release` records that fork giving up; the Stop hook lets a fork with a verdict stop."""

import io
import json
import subprocess

import pytest
from typer.testing import CliRunner

from graphene_map import gate, plan
from graphene_map import run as R
from graphene_map.cli import build
from graphene_map.hooks import hook_main
from graphene_map.plan import RUNNING, Caller, Refused
from graphene_map.store import Store

ALEX = Caller("alex", True)
HOLD = "5e55105e-0000-4000-8000-00000000000a"  # the run's own session
FORK_A, FORK_B = "5e55105e-0000-4000-8000-00000000000b", "5e55105e-0000-4000-8000-00000000000c"
IN_A = Caller("claude:5e55105e", False, FORK_A)  # a Claude Code fork, known by its session


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_NODE",
                 "GRAPHENE_ATTEMPT"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (root / "api.py").write_text("def users():\n    return []\n")
    (root / "schema.py").write_text("TABLES = []\n")
    git("add", "-A")
    git("commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


def forked(repo, check="grep -q ids api.py") -> dict[str, str]:
    """A leaf held by a run and forked two ways, as `run._forked` sets it up: the hold's tree, a tree a
    fork, cut from the same commit, and the Node's `forked`. Returns each fork's tree."""
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "n1", "title": "users", "scope": ["api.py"], "check": check}], ALEX)
        hold = R.worktree_for(store, repo, repo, "n1")
        node = plan.start(store, "n1", Caller("run:claude", False, HOLD), hold)
        trees = {b: R.worktree_for(store, repo, hold, "n1", fork=b, at=node.base_sha) for b in "ab"}
        plan.set_forked(store, "n1", {FORK_A: {"fork": "a", "tree": str(trees["a"])},
                                      FORK_B: {"fork": "b", "tree": str(trees["b"])}})  # fmt: skip
        store.log_node("n1", plan._now(), "fork", "run:claude", FORK_A, None,
                       {"fork": "a", "of": 2, "state": "running", "why": ""})  # fmt: skip
    return {b: str(t) for b, t in trees.items()}


def hook(repo, name, session, **extra) -> dict | None:
    event = {"session_id": session, "cwd": str(repo), "hook_event_name": name, **extra}
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


def fork_rows(store):
    return [e["detail"] for e in store.node_log("n1", ("fork",))]


def test_the_hooks_find_the_held_leaf_for_a_forks_session(repo):
    trees = forked(repo)
    with Store.open(repo) as store:
        assert [n.id for n in gate._held(store, FORK_A)] == ["n1"] == [n.id for n in gate._held(store, HOLD)]
        assert gate._held(store, "someone-else") == []
        assert plan.get(store, "n1").forked == {FORK_A: {"fork": "a", "tree": trees["a"]},
                                                FORK_B: {"fork": "b", "tree": trees["b"]}}  # fmt: skip
    inside = {"tool_name": "Edit", "tool_input": {"file_path": f"{trees['a']}/api.py"}, "cwd": trees["a"]}
    assert hook(repo, "PreToolUse", FORK_A, **inside) is None  # inside the scope, from the fork's copy
    outside = {"tool_name": "Edit", "tool_input": {"file_path": f"{trees['a']}/schema.py"}, "cwd": trees["a"]}
    said = hook(repo, "PreToolUse", FORK_A, **outside)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "schema.py is outside the scope of the node you hold (n1: api.py)" in said
    stranger = hook(repo, "PreToolUse", "someone-else", **outside)
    assert "holds no leaf" in stranger["hookSpecificOutput"]["permissionDecisionReason"]  # as ever


def test_a_forks_own_done_judges_its_own_tree_and_leaves_the_leafs_state_to_the_run(repo, monkeypatch):
    trees = forked(repo)
    with Store.open(repo) as store:
        with pytest.raises(Refused, match="n1 is held by run:claude, not by claude:zzzz"):
            plan.finish(store, "n1", Caller("claude:zzzz", False, "zzzz-session"))  # a stranger, as ever
        (repo / ".graphene/worktrees/n1.a/api.py").write_text("def users():\n    return [0]\n")
        with pytest.raises(Refused, match="n1 is not done: `grep -q ids api.py` failed"):
            plan.finish(store, "n1", IN_A)
        (repo / ".graphene/worktrees/n1.a/api.py").write_text("def users():\n    return ids\n")
        n = plan.finish(store, "n1", IN_A)
        assert n.state == RUNNING and plan.get(store, "n1").state == RUNNING  # the leaf's state is the run's
        assert plan.get(store, "n1").forked and plan.get(store, "n1").session_id == HOLD
        verdicts = [(f["state"], f.get("why"), f.get("paths")) for f in fork_rows(store)]
        assert verdicts == [
            ("running", "", None),
            ("refused", "n1 is not done: `grep -q ids api.py` failed:", None),
            ("passed", "", ["api.py"]),
        ]
        assert all(f["fork"] == "a" and f["of"] == 2 for f in fork_rows(store))
        assert [e["session_id"] for e in store.node_log("n1", ("fork",))] == [FORK_A] * 3
        proof = store.node_log("n1", ("check_passed", "check_failed", "finished"))
        assert proof == []  # a fork's verdict is never the leaf's proof
        assert plan.fork_row(store, plan.get(store, "n1"), "a")["state"] == "passed"
        assert plan.fork_row(store, plan.get(store, "n1"), "b") is None
        # a script executor is known by the GRAPHENE_ATTEMPT the run gave it: fork b's tree, judged
        monkeypatch.setenv("GRAPHENE_NODE", "n1")
        monkeypatch.setenv("GRAPHENE_ATTEMPT", FORK_B)
        (repo / ".graphene/worktrees/n1.b/api.py").write_text("def users():\n    return ids\n")
        (repo / ".graphene/worktrees/n1.b/schema.py").write_text("TABLES = ['x']\n")
        with pytest.raises(Refused, match="n1 is not done: changed outside its scope"):
            plan.finish(store, "n1", Caller("run:claude", False, None))
        assert fork_rows(store)[-1]["fork"] == "b" and fork_rows(store)[-1]["state"] == "refused"
        assert [e["session_id"] for e in store.node_log("n1", ("fork",))][-1] == FORK_B
        assert plan.get(store, "n1").state == RUNNING and trees["b"] in str(plan.get(store, "n1").forked)


def test_a_forks_release_records_it_giving_up_and_does_not_release_the_leaf(repo):
    forked(repo)
    with Store.open(repo) as store:
        n = plan.release(store, "n1", IN_A, "needs the schema", wants=["schema.py"])
        assert n.state == RUNNING and plan.get(store, "n1").state == RUNNING and plan.get(store, "n1").forked
        assert store.node_log("n1", ("released",)) == []
        assert fork_rows(store)[-1] == {"fork": "a", "of": 2, "state": "gave up", "why": "needs the schema",
                                        "wants": ["schema.py"]}  # fmt: skip
        assert plan.fork_row(store, plan.get(store, "n1"), "a")["state"] == "gave up"
        with pytest.raises(Refused, match="say why"):
            plan.release(store, "n1", IN_A, " ")
        # the hold's own session, and the person, hand the leaf back as ever
        plan.release(store, "n1", Caller("run:claude", False, HOLD), "the run let it go", stopped=True)
        assert plan.get(store, "n1").state == plan.OPEN and plan.get(store, "n1").forked == {}


def test_the_stop_hook_lets_a_fork_stop_once_it_has_a_verdict(repo, monkeypatch):
    forked(repo)
    monkeypatch.setenv("GRAPHENE_NODE", "n1")  # an executor `graphene run` started: held until the leaf ends
    assert hook(repo, "Stop", "someone-else") is None  # holds nothing
    assert hook(repo, "Stop", HOLD, stop_hook_active=True)["decision"] == "block"  # the hold's own, as ever
    assert hook(repo, "Stop", FORK_A, stop_hook_active=True)["decision"] == "block"  # running, no verdict yet
    assert hook(repo, "Stop", FORK_B)["decision"] == "block"  # no row yet at all
    with Store.open(repo) as store:
        (repo / ".graphene/worktrees/n1.a/api.py").write_text("def users():\n    return [0]\n")
        with pytest.raises(Refused):
            plan.finish(store, "n1", IN_A)  # refused: a verdict all the same, so it may stop and be resumed
    assert hook(repo, "Stop", FORK_A, stop_hook_active=True) is None
    with Store.open(repo) as store:
        plan.release(store, "n1", Caller("claude:5e55105e", False, FORK_B), "no way", wants=None)
    assert hook(repo, "Stop", FORK_B) is None
    assert hook(repo, "Stop", HOLD)["decision"] == "block"
    with Store.open(repo) as store:
        assert [e["kind"] for e in store.node_log("n1")].count("stop_refused") == 4


def test_the_command_line_says_a_forks_verdict_in_its_own_words(repo):
    forked(repo)
    env = {"GRAPHENE_NODE": "n1", "GRAPHENE_ATTEMPT": FORK_A, "GRAPHENE_EXECUTOR": "claude"}
    (repo / ".graphene/worktrees/n1.a/api.py").write_text("def users():\n    return ids\n")
    done = CliRunner().invoke(build(), ["node", "done", "n1"], env=env)
    assert done.exit_code == 0, done.output
    assert done.stdout.splitlines()[0] == (
        "the check passed in this fork (fork a of 2); Graphene keeps one when the forks end"
    )
    assert "next: stop here" in done.stdout
    in_b = {**env, "GRAPHENE_ATTEMPT": FORK_B}
    gave = CliRunner().invoke(build(), ["node", "release", "n1", "--why", "no"], env=in_b)
    assert gave.exit_code == 0 and gave.stdout.splitlines()[0] == (
        "this fork gives up; the leaf is handed back only if every fork does"
    ), gave.output
    with Store.open(repo) as store:
        assert plan.get(store, "n1").state == RUNNING
        assert [(f["fork"], f["state"]) for f in fork_rows(store)] == [("a", "running"), ("a", "passed"),
                                                                        ("b", "gave up")]  # fmt: skip
