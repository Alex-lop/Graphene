"""docs/proof/nemotron.sh, end to end against the recorded fake: the Nemotron path from nothing to
`git log --graph` reading as the tree, and the bill. The script is the demo; this runs it on a tiny
repository instead of feeds, with a scripted Ultra planner and scripted Nano executors, so every
command in it is known to work before a key spends anything on it. It records the run as it goes
(RECORD), and the recording replays to where the run ended: `graphene demo` ships the one made here."""

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import demo, plan, run
from graphene_map.store import Store

NANO = "nvidia/Nemotron-3-Nano-fake"
SCRIPT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "nemotron.sh"
MAKE = textwrap.dedent('''\
    import pathlib, subprocess, sys
    d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True)
    (d / ".gitignore").write_text(".graphene/\\n__pycache__/\\n")
    (d / "app.py").write_text("from words import HELLO\\n\\ndef greet():\\n    return 'hi'\\n")
    (d / "words.py").write_text("HELLO = 'hi'\\n")
    (d / "bye.py").write_text("def bye():\\n    return 'bye'\\n")
    for a in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"],
              ["add", "-A"], ["commit", "-qm", "start"]):
        subprocess.run(["git", "-C", str(d), *a], check=True)
''')
PLAN = """```plan
goal: a friendlier app
question: what does bye say?  [bye-word]
    default: goodbye, as the paragraph's friendlier app would
    then: goal farewell + It says goodbye, in full.
    option: see you
    then: goal farewell + It says see you.
    then: check farewell: python3 -c 'import bye; assert bye.bye() == "see you"'
    about: farewell
assume: greet reads its word from words.py, where HELLO is  [hello-home]
leave out: a --name flag; nobody asked for one  [name-flag]
- say hello  [friendly]
  ? greet says hello  [greet]
      greet returns the word hello, from words.py
      scope: app.py, words.py
      check: python3 -c 'import app; assert app.greet() == "hello"'
  ? bye says goodbye  [farewell]
      scope: bye.py
      check: python3 -c 'import bye; assert bye.bye() == "goodbye"'
```"""
GREET_CHECK = "python3 -c 'import app; assert app.greet() == \"hello\"'"
SCRIPTS = {
    "planner": [call("list", path="."), call("read", path="app.py"), {"content": PLAN}],
    # the prune took words.py from greet's scope: its first hold comes back wanting it
    "greet (revision 2": [call("edit", path="app.py", old="return 'hi'", new="return HELLO"),
                          call("write", path="words.py", content="HELLO = 'hello'\n"),
                          call("release", why="the word lives in words.py", wants=["words.py"])],
    "greet (revision 3": [call("edit", path="app.py", old="return 'hi'", new="return HELLO"),
                          call("edit", path="words.py", old="'hi'", new="'hello'"),
                          call("run", command=GREET_CHECK), call("done")],
    "farewell (revision": [call("edit", path="bye.py", old="'bye'", new="'goodbye'"), call("done")],
}  # fmt: skip
# no prune: greet keeps words.py in its scope, and both leaves land on the first run
IN_ONE_GO = {"planner": SCRIPTS["planner"], "greet (revision": SCRIPTS["greet (revision 3"],
             "farewell (revision": SCRIPTS["farewell (revision"]}  # fmt: skip


def reply(body, scripts=SCRIPTS):
    first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
    key = "planner" if "Ultra" in body["model"] else next((k for k in scripts if k in first), None)
    steps = scripts.get(key, [])
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    return steps[k] if k < len(steps) else {"content": "nothing more"}


def script(tmp_path, answer, prune: str, **more: str):
    """nemotron.sh on the tiny repository against the fake, answered by ``answer``: the finished script,
    all it said in the order a terminal shows it (stderr where it was said), and the fake."""
    make = tmp_path / "make_tiny.py"
    make.write_text(MAKE)
    with Fake([answer] * 60) as f:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GRAPHENE_", "CLAUDE", "CODEX"))
               and k not in ("SHOW_DEMO", "RECORD_DEMO", "NEBIUS_PROJECT_ID")}  # fmt: skip
        env |= f.env() | {"MAKE_REPO": f"{sys.executable} {make}", "PARAGRAPH": "make the app friendlier",
                          "PRUNE": prune, "HOME": str(tmp_path),
                          "GRAPHENE_PERSON": "the script"} | more  # fmt: skip  (whoever prunes and accepts)
        done = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "demo")], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=env, timeout=300)  # fmt: skip
    return done, done.stdout, f


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_the_demo_script_runs_from_nothing_to_the_bill(tmp_path):
    print_it, ship = os.environ.get("SHOW_DEMO"), os.environ.get("RECORD_DEMO")
    prune = "sed -i.bak -e 's#app.py, words.py#app.py#'"
    board = "take bye-word\ntake hello-home\ntake name-flag"  # y on each item: its default
    done, said, f = script(tmp_path, reply, prune, RECORD=str(tmp_path / "demo.jsonl"), BOARD=board)
    if print_it:
        print(said)
    assert done.returncode == 0, said
    assert "$ graphene init --planner nemotron --executor nemotron" in said
    assert "$ graphene node widen greet" in said  # the came-back leaf's offer, taken
    # what SHOW_DEMO prints reads as the terminal did: each step's notes under it, none after the bill
    at = said.index("$ graphene node widen greet")
    widen = said[at : said.index("$ graphene run", at)]
    assert "(the plan of ~/demo)" in widen and said.rindex("(the plan of") < said.index("$ git log --graph")
    graph = subprocess.run(["git", "-C", str(tmp_path / "demo"), "log", "--merges", "--format=%s"],
                           capture_output=True, text=True).stdout.split("\n")  # fmt: skip
    assert "greet says hello (greet)" in graph and "bye says goodbye (farewell)" in graph
    assert "bill: $" in said and "at list price" in said  # the record's bill, at the end
    assert "2 of 2 passed at last run, 0 runs failed on the way; 1 write refused" in said
    assert (tmp_path / "demo" / "words.py").read_text() == "HELLO = 'hello'\n"
    models = {r["model"] for r in f.requests}
    assert models == {"nvidia/Nemotron-3-Ultra-fake", "nvidia/Nemotron-3-Nano-fake"}
    assert json.dumps(f.requests).count("fake-key") == 0
    # the run was recorded, and its replay ends where the run did: a stand-in's, saying so
    recorded = (tmp_path / "demo.jsonl").read_text()
    head, lines = demo.load(tmp_path / "demo.jsonl")
    assert head["stand_in"] is True and "stand-in" in head["shown"] and head["repository"] == "demo"
    (tmp_path / "replay").mkdir()
    replay = demo.repository(tmp_path / "replay", head)
    demo.last_frame(replay, lines)
    ended = dict.fromkeys(("friendly", "greet", "farewell"), "done")
    with Store.open(replay) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == ended
        tail = run.live(store, plan.get(store, "greet"))["log"]
    assert tail.startswith(str(replay)) and "stand-in executor" in Path(tail).read_text()  # `l`, replayed
    assert str(tmp_path) not in recorded and "{repo}/.graphene/worktrees/greet" in recorded
    if ship:  # RECORD_DEMO=src/graphene_map/demo.jsonl: the recording `graphene demo` ships, made again
        shutil.copy(tmp_path / "demo.jsonl", ship)


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_when_no_leaf_comes_back_the_script_still_ends_with_the_graph_and_the_bill(tmp_path):
    """The second `graphene run` ran whatever came back, and with nothing back it said "nothing to run",
    exit 1, which `set -e` made the script's end, before `git log --graph` and the bill."""
    done, said, _ = script(tmp_path, lambda body: reply(body, IN_ONE_GO), "true")
    assert done.returncode == 0, said
    assert "$ graphene node widen" not in said and said.count("$ graphene run --parallel 4") == 1
    assert "$ git log --graph --oneline" in said and "bill: $" in said
    assert "2 of 2 passed at last run, 0 runs failed on the way" in said


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_a_leaf_back_without_asking_for_paths_still_ends_with_the_graph_and_the_bill(tmp_path):
    """A leaf that comes back because its check keeps failing asked for no path: there is nothing to widen,
    and `graphene node widen` refuses. The script says so and goes on to `git log --graph` and the bill."""

    def answer(body):
        first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
        return call("done") if "farewell (revision" in first else reply(body, IN_ONE_GO)

    done, said, _ = script(tmp_path, answer, "true")
    assert done.returncode == 0, said
    assert "$ graphene node widen farewell" in said and "farewell asked for no path" in said
    assert said.count("$ graphene run --parallel 4") == 1  # nothing was widened: nothing new to run
    assert "$ git log --graph --oneline" in said and "bill: $" in said


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_a_recording_made_with_a_planted_key_and_project_counts_none_of_them(tmp_path, monkeypatch):
    """The sanitiser end to end, as rung 5 will count its live recording: nemotron.sh recorded against the
    fake, with the key (the fake's own, planted) and a project in the environment, and a model that writes
    both and a word shaped like a key into a command, which reaches the run's output. The recording holds
    none of them, counted by demo.leaks, and says where each was taken out."""
    project, shaped = "proj-planted-0042", "Pl4ntedSecretTokenABCDEFGH123456"
    for k, v in {"NEBIUS_API_KEY": "fake-key", "NEBIUS_PROJECT_ID": project, "HOME": str(tmp_path)}.items():
        monkeypatch.setenv(k, v)  # what demo.leaks counts here is what the run's environment held
    leak = f"echo fake-key {project} {shaped}; echo $HOME"
    steps = [call("run", command=leak), *SCRIPTS["farewell (revision"]]

    def answer(body):
        first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
        if "farewell (revision" not in first:
            return reply(body, IN_ONE_GO)
        k = sum(1 for m in body["messages"] if m["role"] == "assistant")
        return steps[k] if k < len(steps) else {"content": "nothing more"}

    # local: with a project id and the sandbox extra, init would place the leaves in ConTree, live
    done, said, _ = script(tmp_path, answer, "true", RECORD=str(tmp_path / "demo.jsonl"),
                           NEBIUS_PROJECT_ID=project, EXECUTOR=f"nemotron --model {NANO} --placement local")
    assert done.returncode == 0, said
    text = (tmp_path / "demo.jsonl").read_text()
    assert demo.leaks(text) == dict.fromkeys(demo.leaks(""), 0), demo.leaks(text)
    assert "echo [removed] [removed] [removed: shaped like a key]; echo $HOME" in text
    assert '"kind": "placement"' not in text and "Sandboxes refused" not in text  # no leaf went near ConTree
