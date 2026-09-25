"""The Nemotron executor, driven by `graphene run` against the recorded fake: a leaf lands; a write
outside the scope is refused before it happens, in the hook's words, and becomes the hand-back's
offer; the key never reaches a command the model runs; attempts climb the model ladder; the bill is
in the record."""

import json
import os
import subprocess
import sys

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import plan
from graphene_map import tokenfactory as tf
from graphene_map.plan import DONE, OPEN, Caller
from graphene_map.run import label, named, run_parallel, run_plan
from graphene_map.store import Store

ALEX = Caller("alex", True)
NANO, SUPER = "nvidia/Nemotron-3-Nano-fake", "nvidia/Nemotron-3-Super-fake"
CHECK = "python3 -c 'import app; assert app.greet() == \"hello\"'"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    (root / "app.py").write_text('def greet():\n    return "hi"\n')
    (root / "other.py").write_text("x = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def fake(monkeypatch):
    started = []

    def start(replies):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)


def script(steps_by_leaf: dict, by_model: dict | None = None):
    """A reply that answers each leaf's conversation from its own list, by how far the conversation
    has got; with ``by_model``, the list is picked by the model asked (the ladder's attempts)."""

    def reply(body):
        first = body["messages"][1]["content"]
        leaf = next((k for k in steps_by_leaf if f"{k} (revision" in first), None)
        steps = by_model[body["model"]] if by_model else steps_by_leaf[leaf]
        k = sum(1 for m in body["messages"] if m["role"] == "assistant")
        return steps[k] if k < len(steps) else {"content": "nothing more"}

    return reply


def leaf(node_id="greet", scope=("app.py",), check=CHECK):
    return {"id": node_id, "title": f"make {node_id}", "goal": "greet says hello", "scope": list(scope),
            "check": check}  # fmt: skip


def plan_of(repo, *leaves):
    with Store.open(repo) as store:
        plan.set_goal(store, "a friendlier app", ALEX)
        plan.propose(store, list(leaves), ALEX)


def run_one(repo, spec=f"nemotron --model {NANO}", attempts=1):
    said = []
    with Store.open(repo) as store:
        done = run_plan(store, repo, named(spec), attempts, None, said.append, repo / ".graphene" / "runs")
    return done, said


def tool_results(request: dict) -> list[str]:
    return [m["content"] for m in request["messages"] if m["role"] == "tool"]


def test_a_leaf_lands_its_check_decides_and_the_bill_is_in_the_record(repo, fake):
    f = fake([script({"greet": [
        call("view", path="app.py"),
        call("edit", path="app.py", old='"hi"', new='"hello"'),
        call("run", command=CHECK),
        call("done"),
    ]})] * 10)  # fmt: skip
    plan_of(repo, leaf())
    done, said = run_one(repo)
    assert [n.id for n in done] == ["greet"]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hello"\n'
    first = f.requests[0]
    assert first["model"] == NANO and [t["function"]["name"] for t in first["tools"]] == [
        "view", "edit", "write", "run", "done", "release"]  # fmt: skip
    assert "greet (revision" in first["messages"][1]["content"]  # the contract, as run hands it over
    assert "app.py" in first["messages"][1]["content"].split("The repository's files:")[1]  # the map
    assert tool_results(f.requests[3])[-1].startswith("exit 0")
    with Store.open(repo) as store:
        [bill] = [e for e in store.node_log("greet", ("usage",))]
        assert bill["actor"] == "run:nemotron" and bill["detail"]["calls"] == 4
        assert bill["detail"]["dollars"] > 0 and bill["detail"]["model"] == NANO
        assert plan.get(store, "greet").state == DONE
        started = store.node_log("greet", ("started",))[-1]
        assert started["actor"] == "run:nemotron"
    log = next((repo / ".graphene" / "runs").glob("greet-*.txt")).read_text()
    assert "nemotron executor" in log and "bill: 4 calls" in log and "at list price" in log


def test_every_way_out_of_the_scope_is_refused_before_the_write_and_becomes_the_offer(repo, fake, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "link").symlink_to(outside)
    git(repo, "add", "link")
    git(repo, "commit", "-qm", "a link out")
    f = fake([script({"greet": [
        call("write", path="other.py", content="x = 2\n"),
        call("edit", path="other.py", old="x = 1", new="x = 3"),
        call("write", path="../escape.txt", content="out"),
        call("write", path=str(tmp_path / "abs.txt"), content="out"),
        call("write", path=".graphene/graphene.db", content="gone"),
        call("write", path=".git/config", content="gone"),
        call("write", path="link/through.txt", content="out"),
        call("release", why="the greeting is also in other.py", wants=["other.py"]),
    ]})] * 20)  # fmt: skip
    plan_of(repo, leaf())
    done, said = run_one(repo)
    assert done == []
    assert (repo / "other.py").read_text() == "x = 1\n"
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path / "abs.txt").exists()
    assert not (outside / "through.txt").exists()
    results = tool_results(f.requests[-1])
    assert results[0].startswith("other.py is outside the scope of the node you hold (greet: app.py).")
    assert "--wants" in results[0]  # the hook's way out, said the first time
    assert results[1].startswith("other.py is outside the scope")
    assert "not in this repository" in results[2] and "not in this repository" in results[3]
    assert "Graphene's or git's own" in results[4] and "Graphene's or git's own" in results[5]
    assert "symbolic link" in results[6]
    with Store.open(repo) as store:
        node = plan.get(store, "greet")
        assert node.state == OPEN
        assert [e["detail"]["path"] for e in store.node_log("greet", ("denied",))] == ["other.py", "other.py"]
        offers = plan.offers(store, node)
        assert offers[0][0] == "w" and "other.py" in offers[0][1]
        assert store.node_log("greet", ("usage",))[-1]["detail"]["refused"] == 7


def test_the_key_never_reaches_a_command_the_model_runs(repo, fake):
    f = fake([script({"greet": [call("run", command="env"), call("release", why="looked")]})] * 5)
    plan_of(repo, leaf())
    run_one(repo)
    shown = tool_results(f.requests[1])[0]
    assert "GRAPHENE_NODE=greet" in shown
    assert "NEBIUS_API_KEY" not in shown and "fake-key" not in shown


def test_a_refused_attempt_climbs_the_ladder_with_the_refusal_in_hand(repo, fake):
    f = fake([script({}, by_model={
        NANO: [call("edit", path="app.py", old='"hi"', new='"hey"'), {"content": "done, I think"}] + [
            {"content": "really done"}] * 3,
        SUPER: [call("edit", path="app.py", old='"hey"', new='"hello"'), call("done")],
    })] * 20)  # fmt: skip
    plan_of(repo, leaf())
    done, said = run_one(repo, f"nemotron --model {NANO} --model {SUPER}", attempts=2)
    assert [n.id for n in done] == ["greet"]
    models = [r["model"] for r in f.requests]
    assert models[0] == NANO and models[-1] == SUPER and set(models) == {NANO, SUPER}
    second = next(r for r in f.requests if r["model"] == SUPER)
    assert "Your last attempt was not accepted" in second["messages"][1]["content"]
    assert any("attempt 1 refused" in s for s in said)


def test_a_model_whose_native_calls_misfire_can_speak_fenced_text(repo, fake):
    fence = "```tool\n{}\n```"
    f = fake([script({"greet": [
        {"content": "I will edit.\n" + fence.format(json.dumps(
            {"name": "edit", "arguments": {"path": "app.py", "old": '"hi"', "new": '"hello"'}}))},
        {"content": fence.format(json.dumps({"name": "done", "arguments": {}}))},
    ]})] * 5)  # fmt: skip
    plan_of(repo, leaf())
    done, _ = run_one(repo, f"nemotron --model {NANO} --protocol text")
    assert [n.id for n in done] == ["greet"]
    assert "tools" not in f.requests[0] and "```tool" in f.requests[0]["messages"][0]["content"]


def test_two_leaves_land_at_once_each_in_its_worktree(repo, fake):
    (repo / "bye.py").write_text('def bye():\n    return "bye"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "bye")
    bye_check = "python3 -c 'import bye; assert bye.bye() == \"goodbye\"'"
    fake([script({
        "greet": [call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")],
        "farewell": [call("edit", path="bye.py", old='"bye"', new='"goodbye"'), call("done")],
    })] * 20)  # fmt: skip
    plan_of(repo, leaf(), leaf("farewell", ("bye.py",), bye_check))
    said = []
    done = run_parallel(lambda: Store.open(repo), repo, repo, 2, named(f"nemotron --model {NANO}"),
                        say=said.append, logs=repo / ".graphene" / "runs")  # fmt: skip
    assert sorted(n.id for n in done) == ["farewell", "greet"]
    assert "hello" in (repo / "app.py").read_text() and "goodbye" in (repo / "bye.py").read_text()
    merges = git(repo, "log", "--merges", "--format=%s").splitlines()
    assert sorted(merges) == ["make farewell (farewell)", "make greet (greet)"]


def test_named_executors_and_their_label():
    assert named("nemotron --model x").split()[1:] == ["-m", "graphene_map.executor", "--model", "x"]
    assert label(named("nemotron")) == "nemotron"
    assert named("claude") == named(None) and "claude -p" in named(None)
    assert named("codex").startswith("codex exec")
    assert named("my-agent --flag") == "my-agent --flag"


def test_started_by_hand_it_says_who_starts_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "GRAPHENE_NODE"}
    said = subprocess.run([sys.executable, "-m", "graphene_map.executor", "a prompt"], capture_output=True,
                          text=True, env=env)  # fmt: skip
    assert said.returncode == 2 and "started by `graphene run`" in said.stdout


def by_fork(scripts: dict):
    """A reply that answers fork k's conversation from scripts[k], by how far it has got."""

    def reply(body):
        k = next(k for k in scripts if f"This is fork {k} of" in body["messages"][0]["content"])
        n = sum(1 for m in body["messages"] if m["role"] == "assistant")
        return scripts[k][n] if n < len(scripts[k]) else {"content": "nothing more"}

    return reply


def test_forks_run_from_one_checkpoint_and_the_first_whose_check_passes_lands(repo, fake):
    fake([by_fork({
        1: [call("edit", path="app.py", old='"hi"', new='"hey"'), call("done"),
            call("release", why="cannot tell what greet should say")],
        2: [call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")],
        3: [call("write", path="other.py", content="x = 9\n"), call("release", why="wants other.py",
                                                                        wants=["other.py"])],
    })] * 40)  # fmt: skip
    plan_of(repo, leaf())
    done, said = run_one(repo, f"nemotron --model {NANO} --forks 3")
    assert [n.id for n in done] == ["greet"]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hello"\n'
    assert (repo / "other.py").read_text() == "x = 1\n"
    with Store.open(repo) as store:
        bill = store.node_log("greet", ("usage",))[-1]["detail"]
    assert bill["forks"] == 3 and bill["winner"] == 2 and bill["refused"] == 1
    log = next((repo / ".graphene" / "runs").glob("greet-*.txt")).read_text()
    assert "fork 2 of 3 passed its check" in log and "[fork 1]" in log and "[fork 3]" in log


def test_when_every_fork_gives_up_the_leaf_comes_back_with_what_they_wanted(repo, fake):
    fake([by_fork({
        1: [call("release", why="the greeting is also in other.py", wants=["other.py"])],
        2: [call("release", why="needs other.py too", wants=["other.py", "cli.py"])],
    })] * 10)  # fmt: skip
    plan_of(repo, leaf())
    done, _ = run_one(repo, f"nemotron --model {NANO} --forks 2")
    assert done == []
    with Store.open(repo) as store:
        node = plan.get(store, "greet")
        assert node.state == OPEN
        released = store.node_log("greet", ("released",))[-1]["detail"]
        assert released["why"] == "the greeting is also in other.py"
        assert sorted(released["wants"]) == ["cli.py", "other.py"]
