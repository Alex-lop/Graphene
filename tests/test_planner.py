"""The Nemotron planner, driven by `graphene ask` against the recorded fake: it reads the repository
with tools that only read, prints the fenced plan block, and what it proposed is in the plan for the
person to prune; the bill is in the plan's log."""

import json

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import plan
from graphene_map import tokenfactory as tf
from graphene_map.ask import ask, label, named
from graphene_map.plan import PROPOSED
from graphene_map.store import Store

ULTRA = "nvidia/Nemotron-3-Ultra-fake"
PROPOSAL = """Here is the tree.

```plan
goal: the app greets properly
- the greeting  [greeting]
  ? say hello  [hello]
      greet returns hello
      scope: app.py
      check: python3 -c 'import app; assert app.greet() == "hello"'
```

The README still says hi; I left it."""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "app.py").write_text('def greet():\n    return "hi"\n')
    (root / "src").mkdir()
    (root / "src" / "deep.py").write_text("# nothing\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "start"], check=True)
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


def test_it_reads_only_and_what_it_prints_is_proposed_for_the_person(repo, fake):
    f = fake([
        call("list", path="."),
        call("glob", pattern="**/*.py"),
        call("grep", pattern="return", glob="*.py"),
        call("read", path="app.py"),
        call("read", path="../../etc/passwd"),
        call("write", path="app.py", content="gone"),
        {"content": PROPOSAL},
    ])  # fmt: skip
    said = []
    with Store.open(repo) as store:
        proposed = ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
        assert any("hello" in line for line in proposed)
        assert plan.get(store, "hello").state == PROPOSED and plan.get(store, "hello").scope == ["app.py"]
        [bill] = store.node_log("*", ("usage",))
        assert bill["actor"] == "planner:nemotron" and bill["detail"]["calls"] == 7
        asked = store.node_log("hello", ("proposed",))[-1]
        assert asked["actor"] == "planner:nemotron"
    assert f.requests[0]["model"] == ULTRA  # the largest Nemotron the live list has, by default
    assert [t["function"]["name"] for t in f.requests[0]["tools"]] == ["list", "glob", "grep", "read"]
    results = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
    assert results[0].split("\n") == [".gitignore", "app.py", "src/"]
    assert results[1].split("\n") == ["app.py", "src/deep.py"]
    assert results[2] == 'app.py:2: return "hi"'
    assert results[3].startswith("    1  def greet():")
    assert "not a file of this repository" in results[4]
    assert "there is no tool 'write'" in results[5]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hi"\n'
    assert any("The README still says hi" in line for line in said)  # what it could not settle


def test_out_of_steps_it_is_asked_to_answer_without_tools(repo, fake):
    f = fake([call("list", path=".")] * 2 + [{"content": PROPOSAL}])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron --steps 3"), say=lambda s: None)
    assert "tools" in f.requests[0] and "tools" not in f.requests[2]
    assert f.requests[2]["messages"][-1]["content"] == "Answer now with the proposal."


def test_named_planners():
    assert label(named("nemotron")) == "nemotron"
    assert named("claude") == named(None) and "--tools Read,Grep,Glob" in named(None)
    assert named("codex") == "codex exec --sandbox read-only"


def test_a_planner_that_cannot_reach_token_factory_says_why_in_its_own_words(repo, monkeypatch):
    """What the person reads when the key is missing: the planner's own last word, whole, not the
    last 300 characters of what it printed, and not "the planner" twice."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    tf._listed.cache_clear()
    said = []
    with Store.open(repo) as store, pytest.raises(plan.Refused) as no:
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
    assert "no proposal (exit 3): stopped: NEBIUS_API_KEY is not set" in str(no.value)
    assert said == ["asking the planner (nemotron)…"]  # asked once: again would fail the same way
    assert "the planner printed" not in str(no.value)


def test_a_bill_under_a_cent_is_never_shown_as_nothing():
    from graphene_map.tui import money

    assert money(0.0015) == "$0.0015" and money(0.034) == "$0.03" and money(0) == "$0.00"


def test_what_git_ignores_is_never_read_and_so_never_sent(repo, fake):
    """A judge had the planner read a git-ignored .env holding a secret, and send it to Token Factory."""
    (repo / ".gitignore").write_text(".graphene/\n.env\n")
    (repo / ".env").write_text("AWS_SECRET_ACCESS_KEY=do-not-send\n")
    f = fake([call("read", path=".env"), call("list", path="."), call("grep", pattern="SECRET"),
              call("read", path=".graphene/graphene.db"), {"content": PROPOSAL}])  # fmt: skip
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
    sent = json.dumps(f.requests)
    assert "do-not-send" not in sent and "SQLite" not in sent
    results = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
    assert "git ignores it" in results[0] and ".env" not in results[1].split("\n")
    assert results[2] == "(no match)"
