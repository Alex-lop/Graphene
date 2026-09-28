"""Red first (`graphene plan precheck`): every check run before any work, its verdict read from the exit
code and the output first, and by Nano (the recorded fake here) only for a red whose reason they do not
say. A scripted runner stands in for the sandbox fork; the Docker test runs the real one."""

import json
import subprocess

import pytest
from fake_tokenfactory import Fake
from typer.testing import CliRunner

from graphene_map import plan as P
from graphene_map import precheck as C
from graphene_map import tokenfactory as tf
from graphene_map.cli import build
from graphene_map.store import Store

ME = P.Caller("alex", True)
BOT = P.Caller("planner:claude", False, "s1")
NANO = "nvidia/Nemotron-3-Nano-fake"
RED = "python3 -c 'import app; assert app.greet() == \"hello\"'"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_SANDBOX"):
        monkeypatch.delenv(name, raising=False)
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    (tmp_path / ".gitignore").write_text(".graphene/\n")
    (tmp_path / "app.py").write_text('def greet():\n    return "hi"\n')
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "start"], check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def nano(monkeypatch):
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
    tf._listed.cache_clear()


def leaves(store, *checks, who=BOT):
    nodes = [
        {"id": f"l{k}", "title": f"leaf {k}", "scope": ["app.py"], "check": c} for k, c in enumerate(checks)
    ]
    P.propose(store, nodes, who)


def scripted(answers):
    """A sandbox fork that answers from a script, and counts what it was asked."""

    def fork(command):
        fork.asked.append(command)
        return answers[command]

    fork.asked = []
    return fork


def said(verdict, why):
    return {"content": json.dumps({"verdict": verdict, "why": why})}


def test_deterministic_verdicts_need_no_model_and_one_red_needs_exactly_one_call(repo, nano):
    f = nano([said("red-right-reason", "greet still says hi; the leaf makes it say hello")])
    fork = scripted({
        "true": (0, ""),
        "pytest tests/nope.py": (4, "ERROR: file or directory not found: tests/nope.py"),
        RED: (1, "Traceback (most recent call last):\nAssertionError"),
    })  # fmt: skip
    with Store.open(repo) as store:
        leaves(store, "true", "pytest tests/nope.py", RED, RED)  # the last two: one command, run once
        rows = C.run(store, repo, fork=fork)
        verdicts = {n.id: d["verdict"] for n, d in rows}
        assert verdicts == {
            "l0": "passes",
            "l1": "cannot-run",
            "l2": "red-right-reason",
            "l3": "red-right-reason",
        }
        assert fork.asked == ["true", "pytest tests/nope.py", RED]
        assert len(f.requests) == 1
        asked = f.requests[0]
        assert asked["model"] == NANO and asked["response_format"]["type"] == "json_schema"
        assert asked["reasoning_effort"] == "low"
        usage = store.node_log("*", ("usage",))
        assert len(usage) == 1 and usage[0]["detail"]["endpoint"] == "a stand-in"
        lines = C.said(rows)
    assert "Token Factory" not in "\n".join(lines)  # a stand-in answered, and the line says so
    assert any("l2" in line and "a stand-in" in line for line in lines)
    assert lines[0].startswith("each check before any work, at ")
    assert lines[1].startswith("! l0") and lines[3].startswith("  l2")


def test_a_red_for_another_reason_is_marked_and_nano_is_not_trusted_beyond_its_schema(repo, nano):
    nano([said("typo", "tests/test_app.py is spelt test/test_app.py"), {"content": "sure, looks red"}])
    fork = scripted({"python3 test/x.py": (2, "can't open file"), "make check": (2, "Error 2")})
    with Store.open(repo) as store:
        leaves(store, "python3 test/x.py", "make check")
        rows = {n.id: d for n, d in C.run(store, repo, fork=fork)}
    assert rows["l0"]["verdict"] == "typo" and rows["l0"]["by"] == "Nemotron-3-Nano-fake, a stand-in"
    assert rows["l1"]["verdict"] == "red" and rows["l1"]["why"].startswith("not read")


def test_a_missing_module_is_the_environment_unless_a_scope_makes_it(repo):
    scopes = ["app/**", "tests/**"]
    assert C.verdict(1, "ModuleNotFoundError: No module named 'pytest'", "python3 -m pytest", scopes) == (
        "cannot-run"
    )
    assert C.verdict(2, "E   ModuleNotFoundError: No module named 'app.feed'", "pytest", scopes) is None
    assert C.verdict(127, "bash: pyest: command not found", "pyest", scopes) == "cannot-run"
    assert C.verdict(5, "no tests ran", "python3 -m pytest -k xml", scopes) == "cannot-run"
    assert C.verdict(5, "", "./run-it", scopes) is None  # 5 is pytest's only from pytest


def test_a_proposed_check_with_no_sandbox_never_runs_here(repo, monkeypatch):
    def here(*_):
        raise AssertionError("a planner's check ran on the person's machine")

    monkeypatch.setattr(C, "_here", here)
    monkeypatch.setattr(P, "_ended", here)
    with Store.open(repo) as store:
        leaves(store, "touch /tmp/owned && true")
        [(_, d)] = C.run(store, repo)
    assert d["verdict"] == "not-run" and "needs a sandbox" in d["why"]


def test_an_accepted_check_runs_here_without_the_key_and_no_key_leaves_a_red_unread(repo, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-key")  # a key the check must not see
    with Store.open(repo) as store:
        leaves(store, 'test -z "$NEBIUS_API_KEY"', "false", who=ME)
        monkeypatch.delenv("NEBIUS_API_KEY")
        rows = {n.id: d for n, d in C.run(store, repo)}
    assert rows["l0"]["verdict"] == "passes" and rows["l0"]["where"] == "here"
    assert rows["l1"]["verdict"] == "red" and "NEBIUS_API_KEY is not set" in rows["l1"]["why"]


def test_a_verdict_is_kept_until_the_leaf_is_edited(repo):
    fork = scripted({"true": (0, ""), "false": (1, "")})
    with Store.open(repo) as store:
        leaves(store, "true", who=ME)
        P.propose(store, [{"id": "p", "title": "p", "scope": ["b.py"], "check": "true"}], BOT)
        C.run(store, repo, fork=fork)
        again = C.run(store, repo, fork=fork)  # current: nothing runs
        assert fork.asked == ["true"] and len(store.node_log("p", ("precheck",))) == 1
        assert again[1][1]["kept"]
        assert C.current(store, P.get(store, "p"), P.head(repo))["verdict"] == "passes"
        assert "2 kept from the last run" in C.said(again)[0]
        P.edit(store, "l0", {"check": "true && true"}, ME)
        assert C.current(store, P.get(store, "l0"), P.head(repo)) is None


def test_graphene_plan_precheck_is_the_persons_and_says_each_leaf(repo):
    runner = CliRunner()
    with Store.open(repo) as store:
        leaves(store, "true", who=ME)
    shown = runner.invoke(build(), ["plan", "precheck"], env={"GRAPHENE_AS": "person:alex"})
    assert shown.exit_code == 0, shown.output
    assert (
        "l0" in shown.stdout and "passes already" in shown.stdout and "node set <id> --check" in shown.stdout
    )
    refused = runner.invoke(build(), ["plan", "precheck"], env={"GRAPHENE_AS": "agent:bot"})
    assert refused.exit_code == 1 and "the person's" in refused.output


def test_the_flag_runs_it_as_a_proposal_lands(repo, monkeypatch, tmp_path):
    import sys

    from graphene_map.ask import ask

    script = tmp_path / "planner.py"
    script.write_text('print("```plan\\n? say hello  [hello]\\n    scope: app.py\\n    check: false\\n```")')
    with Store.open(repo) as store:
        ask(store, repo, "say hello", f"{sys.executable} {script}", say=lambda _: None)
        assert store.node_log("hello", ("precheck",)) == []
        monkeypatch.setenv("GRAPHENE_SHAPE", "notes, precheck")
        seen = []
        ask(store, repo, "say hello again", f"{sys.executable} {script}", say=seen.append)
        assert store.node_log("hello", ("precheck",))[0]["detail"]["verdict"] == "not-run"
    assert any("needs a sandbox" in line for line in seen)


def _docker() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _docker(), reason="Docker is not running here")
def test_proposed_checks_run_in_a_docker_fork_and_nothing_they_write_comes_back(repo, nano, monkeypatch):
    monkeypatch.setenv("GRAPHENE_SANDBOX", "docker")
    monkeypatch.setattr(P, "_ended", lambda *_: (_ for _ in ()).throw(AssertionError("ran here")))
    f = nano([said("red-right-reason", "greet says hi")])
    with Store.open(repo) as store:
        leaves(store, "touch app.py.stray; test -f app.py", RED, "whoami | grep -qx leaf")
        rows = {n.id: d for n, d in C.run(store, repo)}
    assert {k: d["verdict"] for k, d in rows.items()} == {
        "l0": "passes", "l1": "red-right-reason", "l2": "passes"}  # fmt: skip
    assert rows["l0"]["where"] == "a Docker fork" and len(f.requests) == 1
    assert not (repo / "app.py.stray").exists()
