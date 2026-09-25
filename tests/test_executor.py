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
    from graphene_map.node_record import node_record, render
    from graphene_map.run import summary

    with Store.open(repo) as store:
        shown = "\n".join(render(node_record(store, repo, plan.get(store, "greet"))))
        assert f"bill: ${bill['detail']['dollars']:.4f} at list price · 4 model calls" in shown
        assert "Nemotron-3-Nano-fake (Token Factory's usage)" in shown
        assert summary(store, 0).endswith(f"; ${bill['detail']['dollars']:.4f} at list price")


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


def test_the_check_graphene_runs_after_the_executor_never_gets_the_key(repo, fake):
    fake([script({"greet": [call("edit", path="app.py", old='"hi"', new='"hello"')] + [
        {"content": "that is all"}] * 3})] * 10)  # fmt: skip
    plan_of(repo, leaf(check="env | grep -E 'NEBIUS|GRAPHENE_AS'; false"))
    run_one(repo)  # the executor stops calling tools; `graphene run` runs the gate itself
    with Store.open(repo) as store:
        said = store.node_log("greet", ("check_failed",))[-1]["detail"]["output"]
    assert "GRAPHENE_AS=agent:check" in said
    assert "NEBIUS_API_KEY" not in said and "fake-key" not in said


def test_the_attempt_is_the_one_run_names_not_the_log_s_count(repo, fake, monkeypatch):
    """`graphene run` writes an attempt's row only once the executor is running: an executor that read
    the log for its attempt could read attempt 2 as 1 and stay on the ladder's first model (a CI run
    on macOS did). The run names the attempt (GRAPHENE_TRY), and that is the one used."""
    from graphene_map import executor

    f = fake([call("release", why="just looking")] * 3)
    plan_of(repo, leaf())
    with Store.open(repo) as store:
        plan.start(store, "greet", Caller("run:nemotron", False, "s-1"), repo)
        store.log_node("greet", plan._now(), "attempt", "run:nemotron", "s-1", None, {"attempt": 1})
    monkeypatch.setenv("GRAPHENE_NODE", "greet")
    monkeypatch.setenv("GRAPHENE_ATTEMPT", "s-1")
    monkeypatch.setenv("GRAPHENE_TRY", "2")  # the second attempt, whose row is not written yet
    executor.main(["--model", NANO, "--model", SUPER, "the contract"])
    assert f.requests[0]["model"] == SUPER


def test_a_tool_called_by_another_common_name_is_the_tool_it_means(repo, fake):
    fake([script({"greet": [
        call("str_replace", file_path="app.py", old_str='"hi"', new_str='"hello"'),
        call("bash", cmd=CHECK),
        call("finish"),
    ]})] * 10)  # fmt: skip
    plan_of(repo, leaf())
    done, _ = run_one(repo)
    assert [n.id for n in done] == ["greet"]


def test_a_wrong_key_comes_back_once_with_its_cause_and_no_check_runs(repo, fake, monkeypatch):
    """The executor cannot work at all: it hands the leaf back itself, with the cause, and the run does
    not send it round again to fail the same way on untouched code (a judge saw '3 attempts, the last
    one refused: AssertionError', the 401 only in the log)."""
    fake([call("done")] * 5)
    monkeypatch.setenv("NEBIUS_API_KEY", "wrong")
    plan_of(repo, leaf())
    done, said = run_one(repo, attempts=3)
    assert done == []
    with Store.open(repo) as store:
        why = store.node_log("greet", ("released",))[-1]["detail"]["why"]
        assert why.startswith("the executor stopped: Token Factory answered 401")
        assert len(store.node_log("greet", ("attempt",))) == 1
        assert store.node_log("greet", ("check_failed", "check_passed")) == []
    back = "handed back by the executor: the executor stopped: Token Factory answered 401"
    assert any(back in s for s in said)


def test_graphenes_own_done_keeps_the_key_for_a_sandbox_check(repo, monkeypatch):
    """`graphene node done` is Graphene's own process: a sandbox leaf's check is forked in ConTree from
    there, which needs the key. (The check itself never gets it: see the test above it.)"""
    from graphene_map import executor

    seen = {}
    monkeypatch.setenv("NEBIUS_API_KEY", "the-key")
    monkeypatch.setattr(executor.subprocess, "run", lambda argv, **kw: seen.update(kw) or
                        subprocess.CompletedProcess(argv, 0, "ok", ""))  # fmt: skip
    plan_of(repo, leaf())
    with Store.open(repo) as store:
        node = plan.get(store, "greet")
        executor.Leaf(store, node, executor.Local(repo), repo, "s")._graphene("node", "done", "greet")
    assert seen["env"]["NEBIUS_API_KEY"] == "the-key"


def test_a_reply_cut_off_at_the_token_limit_is_said_and_asked_again_with_more_room(repo, fake):
    f = fake([script({"greet": [
        {"content": "Let me think about greet at length", "_finish": "length"},
        call("edit", path="app.py", old='"hi"', new='"hello"'),
        call("done"),
    ]})] * 10)  # fmt: skip
    plan_of(repo, leaf())
    done, _ = run_one(repo)
    assert [n.id for n in done] == ["greet"]
    assert f.requests[0]["max_tokens"] == 4096 and f.requests[1]["max_tokens"] == 8192
    assert f.requests[1]["messages"][-1]["content"].startswith("Your answer was cut off at the token limit")


def test_nemotrons_own_toolcall_text_is_read_as_its_calls(repo, fake):
    def tag(name, **arguments):
        return {"content": f"<TOOLCALL>{json.dumps([{'name': name, 'arguments': arguments}])}</TOOLCALL>"}

    fake([script({"greet": [tag("edit", path="app.py", old='"hi"', new='"hello"'), tag("done")]})] * 5)
    plan_of(repo, leaf())
    done, _ = run_one(repo)  # the native protocol: a server that hands the call back as text still works
    assert [n.id for n in done] == ["greet"]


def test_the_executor_never_views_what_git_ignores(repo, fake):
    (repo / ".gitignore").write_text(".graphene/\n__pycache__/\n.env\n")
    (repo / ".env").write_text("AWS_SECRET_ACCESS_KEY=do-not-send\n")
    f = fake([script({"greet": [call("view", path=".env"), call("view", path="."),
                                call("release", why="looked")]})] * 5)  # fmt: skip
    plan_of(repo, leaf())
    run_one(repo)
    assert "do-not-send" not in json.dumps(f.requests)
    shown = tool_results(f.requests[-1])
    assert "git ignores it" in shown[0] and ".env" not in shown[1].split("\n") and "app.py" in shown[1]
