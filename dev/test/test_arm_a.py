"""arm_a.py against the scripted fake Token Factory: one Nano session in the whole repo with the
executor's tools and no plan, scope or check; its follow-up continues the same conversation on what is
left of the run's budget; its bill is what logline.py and tally.py read; a stopped command is stopped
by the run's time budget."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tests"))
import arm_a  # noqa: E402
import tally  # noqa: E402
from fake_tokenfactory import Fake, call  # noqa: E402

from graphene_map.nemotron import tokenfactory as tf  # noqa: E402

NANO = "nvidia/Nemotron-3-Nano-fake"
PARAGRAPH = "make greet say hello, and add a farewell module.\nthanks!"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def run(tmp_path, monkeypatch):
    repo = tmp_path / "run" / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "app.py").write_text('def greet():\n    return "hi"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    (tmp_path / "paragraph.md").write_text(PARAGRAPH)
    (tmp_path / "follow.md").write_text("also say bye")
    monkeypatch.delenv("GRAPHENE_NODE", raising=False)
    monkeypatch.setenv("GRAPHENE_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", "10")
    fakes = []

    def start(replies):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        fakes.append(f)
        return f

    yield repo, tmp_path, start
    for f in fakes:
        f.__exit__(None, None, None)


def test_the_paragraph_goes_to_nano_whole_and_it_writes_anywhere_in_the_repo(run, capsys):
    repo, tmp, start = run
    f = start([
        call("view", path="app.py"),
        call("edit", path="app.py", old='"hi"', new='"hello"'),
        call("write", path="farewell/bye.py", content="BYE = 1\n"),  # no scope: nothing is refused
        call("write", path=".git/hooks/x", content="no"),  # git's own is still not the model's
        call("run", command="echo key=${NEBIUS_API_KEY:-none}"),
        {"content": "greet says hello; farewell/bye.py is new."},  # a reply without a call is nudged
        call("done"),
    ])  # fmt: skip
    code = arm_a.main([str(repo), "--paragraph-file", str(tmp / "paragraph.md"), "--steps", "10"])
    out = capsys.readouterr().out
    assert code == 0
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hello"\n'
    assert (repo / "farewell" / "bye.py").read_text() == "BYE = 1\n"
    assert not (repo / ".git" / "hooks" / "x").exists()
    first = f.requests[0]
    assert first["model"] == NANO  # resolved from the list by role, never typed
    assert [t["function"]["name"] for t in first["tools"]] == ["view", "edit", "write", "run", "done"]
    system, user = first["messages"][0]["content"], first["messages"][1]["content"]
    assert not any(w in system.lower() for w in ("leaf", "scope", "check", "plan", "graphene"))
    assert user.startswith(PARAGRAPH + "\n\n") and "app.py" in user.split("The repository's files:")[1]
    results = [m["content"] for m in f.requests[5]["messages"] if m["role"] == "tool"]
    assert results[-1] == "exit 0\nkey=none\n"  # the key stays in this process
    assert f.requests[6]["messages"][-1] == {"role": "user", "content": arm_a.NUDGE}

    said = json.loads((repo.parent / "arm-a.json").read_text())
    assert said["calls"] == said["num_turns"] == 7 and said["ended"] == "finished"
    assert said["result"] == "greet says hello; farewell/bye.py is new."
    assert said["total_cost_usd"] > 0 and len(said["session_id"]) == 12
    assert f"session ${said['total_cost_usd']:.4f}, 7 of 10 calls" in out and "1 writes refused" in out
    again = arm_a.main([str(repo), "--paragraph-file", str(tmp / "paragraph.md"), "--steps", "10"])
    assert again == 2  # a run is never redone in place


def test_a_follow_up_continues_the_session_on_what_is_left_and_the_runlog_costs_it_once(run, capsys):
    repo, tmp, start = run
    f = start([call("view", path="app.py"), call("done"), call("done"), call("view", path=".")])
    base = [str(repo), "--steps", "3", "--conversation", str(tmp / "a.json")]
    assert arm_a.main([*base, "--paragraph-file", str(tmp / "paragraph.md")]) == 0
    assert arm_a.main([*base, "--follow-up-file", str(tmp / "follow.md")]) == 0
    assert f.requests[2]["messages"][: len(f.requests[1]["messages"])] == f.requests[1]["messages"]
    assert f.requests[2]["messages"][-1] == {"role": "user", "content": "also say bye"}
    said = json.loads((tmp / "a.json").read_text())
    assert said["calls"] == 3 and said["num_turns"] == 1
    assert arm_a.main([*base, "--follow-up-file", str(tmp / "follow.md")]) == 3  # the run's 3 calls are spent
    assert len(f.requests) == 3
    assert "budget is spent" in capsys.readouterr().out

    runlog = tmp / "runlog.jsonl"
    for _ in range(2):  # as the stand-in logs each reply: the session's running total, twice
        subprocess.run([sys.executable, str(HERE / "logline.py"), str(runlog), "executor", "result",
                        "--from-json", str(tmp / "a.json")], check=True, capture_output=True)  # fmt: skip
    counted = tally.read_runlog(runlog, [])
    assert counted["executor_cost_usd"] == said["total_cost_usd"] > 0  # the session costs its total once


def test_the_run_s_time_budget_stops_a_running_command_and_the_session(run, capsys):
    repo, tmp, start = run
    start([call("run", command="sleep 60"), call("done")])
    code = arm_a.main([str(repo), "--paragraph-file", str(tmp / "paragraph.md"), "--steps", "5",
                       "--seconds", "1"])  # fmt: skip
    said = json.loads((repo.parent / "arm-a.json").read_text())
    assert code == 0 and said["calls"] == 1 and said["ended"] == "time is up"
    assert said["seconds_used"] < 30
    assert arm_a.main([str(repo), "--follow-up-file", str(tmp / "follow.md"), "--steps", "5",
                       "--seconds", "1"]) == 3  # fmt: skip
    assert "budget is spent" in capsys.readouterr().out


def test_a_follow_up_after_a_stop_answers_the_call_that_never_ran():
    messages = [{"role": "assistant", "content": "", "tool_calls": [{"id": "a"}, {"id": "b"}]},
                {"role": "tool", "tool_call_id": "a", "content": "exit 0"}]  # fmt: skip
    assert [m["tool_call_id"] for m in arm_a.unanswered(messages)] == ["b"]


def test_a_follow_up_answered_by_another_endpoint_names_both(run):
    repo, tmp, start = run
    start([call("done"), call("done")])
    base = [str(repo), "--steps", "5", "--conversation", str(tmp / "a.json")]
    assert arm_a.main([*base, "--paragraph-file", str(tmp / "paragraph.md")]) == 0
    said = json.loads((tmp / "a.json").read_text())
    (tmp / "a.json").write_text(json.dumps(said | {"endpoint": "token factory"}))  # as a live first message
    assert arm_a.main([*base, "--follow-up-file", str(tmp / "follow.md")]) == 0  # the stand-in answers it
    assert json.loads((tmp / "a.json").read_text())["endpoint"] == "token factory then a stand-in"


def test_no_session_starts_with_no_spend_cap_or_at_80_percent_of_it_and_a_follow_up_goes_on_to_the_cap(
    run, monkeypatch, capsys
):
    repo, tmp, start = run
    f = start([call("done"), call("done")])
    base = [str(repo), "--steps", "5", "--conversation", str(tmp / "a.json")]
    paragraph = ["--paragraph-file", str(tmp / "paragraph.md")]
    follow = ["--follow-up-file", str(tmp / "follow.md")]
    monkeypatch.delenv("GRAPHENE_SPEND_CAP_USD")
    assert arm_a.main([*base, *paragraph]) == 2  # none is assumed
    assert "export GRAPHENE_SPEND_CAP_USD=10" in capsys.readouterr().out
    assert f.requests == [] and not (tmp / "a.json").exists()

    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", "10")
    assert arm_a.main([*base, *paragraph]) == 0
    with (tmp / "ledger.jsonl").open("a") as ledger:  # the other arms' spend, on the one ledger
        ledger.write(json.dumps({"tag": "bench", "dollars": 8.0}) + "\n")
    assert arm_a.main([*base, *follow]) == 0  # the session started: the client stops it at 100%
    assert len(f.requests) == 2
    assert arm_a.main([*base[:-1], str(tmp / "b.json"), *paragraph]) == 3
    assert "no new run" in capsys.readouterr().out and len(f.requests) == 2
    monkeypatch.delenv("GRAPHENE_SPEND_CAP_USD")
    assert arm_a.main([*base, *follow]) == 2 and len(f.requests) == 2
