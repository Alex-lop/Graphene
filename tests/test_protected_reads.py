"""A protected path (`graphene config`) is never read by a planner or an executor, so never sent to a
model: the Nemotron planner's tools, the Nemotron executor's view and file map, and a Claude Code
planner's Read, Grep and Glob, refused by the hook."""

import io
import json
import subprocess

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import executor, settings
from graphene_map import tokenfactory as tf
from graphene_map.ask import ask, named
from graphene_map.hooks import hook_main
from graphene_map.plan import Caller
from graphene_map.store import Store

SECRET = "do-not-send"
PROPOSAL = """```plan
goal: the app greets properly
- say hello  [hello]
    scope: app.py
    check: true
```"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "secrets").mkdir(parents=True)
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "app.py").write_text('def greet():\n    return "hi"\n')
    (root / "secrets" / "prod.txt").write_text(f"KEY={SECRET}\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "start"], check=True)
    with Store.open(root) as store:
        settings.apply(store, "protected: secrets/**\n", Caller("alex", True))
    monkeypatch.chdir(root)
    return root


def test_the_nemotron_planner_never_sees_a_protected_path(repo, monkeypatch):
    replies = [call("read", path="secrets/prod.txt"), call("list", path="."), call("list", path="secrets"),
               call("glob", pattern="**"), call("grep", pattern="KEY"), {"content": PROPOSAL}]  # fmt: skip
    with Fake(replies) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        with Store.open(repo) as store:
            ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
    assert SECRET not in json.dumps(f.requests)
    said = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
    read, top, inside, found, grepped = said
    assert "protected" in read
    assert "secrets/" not in top.split("\n") and inside == "(empty)"
    assert "secrets" not in found and grepped == "(no match)"


def test_the_nemotron_executor_never_views_or_lists_a_protected_path(repo):
    with Store.open(repo) as store:
        leaf = executor.Leaf(store, None, executor.Local(repo), repo, "s")
        assert "protected" in leaf.view("secrets/prod.txt")
        assert "secrets/" not in leaf.view(".").split("\n")
        assert executor.unprotected(store, ["app.py", "secrets/prod.txt"]) == ["app.py"]


def hook(repo, tool, **tool_input) -> dict | None:
    event = {"session_id": "s", "cwd": str(repo), "hook_event_name": "PreToolUse",
             "tool_name": tool, "tool_input": tool_input}  # fmt: skip
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


def refused(answer: dict | None) -> bool:
    return bool(answer) and answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_claude_code_planner_is_refused_a_read_grep_or_glob_reaching_a_protected_path(repo, monkeypatch):
    monkeypatch.setenv("GRAPHENE_PLANNER", "1")
    assert refused(hook(repo, "Read", file_path=str(repo / "secrets/prod.txt")))
    assert "protected" in hook(repo, "Grep", pattern="KEY")["hookSpecificOutput"]["permissionDecisionReason"]
    assert refused(hook(repo, "Grep", pattern="KEY", path="secrets"))
    assert refused(hook(repo, "Glob", pattern="**/*.txt"))
    assert hook(repo, "Read", file_path=str(repo / "app.py")) is None
    assert hook(repo, "Grep", pattern="greet", path="app.py") is None
    assert hook(repo, "Glob", pattern="*.py") is None


def test_outside_a_planner_the_hook_leaves_reads_alone(repo, monkeypatch):
    monkeypatch.delenv("GRAPHENE_PLANNER", raising=False)
    assert hook(repo, "Read", file_path=str(repo / "secrets/prod.txt")) is None
