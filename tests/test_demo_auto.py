# ruff: noqa: E501  (the scripted forks' files are written whole, as an agent writes them)
"""dev/proof/auto.sh, end to end against the recorded fake: auto mode on the Nemotron path, from one goal to
the bill. A scripted Ultra plans wordkit's three wishes as three tasks that can run at once; three scripted Nano
forks race each task (one is stopped at a file outside its task and hands it back, one gives up, the rest pass,
and the rule keeps one a task); all three land; the goal's own check, the whole test suite, is red, because
counting well-known as one word broke an old test no task owned; Ultra plans the fix, it races and lands, and
the suite is green. It records the run as it goes, and the recording replays to where the run ended:
`graphene demo --auto` ships the one made here (RECORD_DEMO_AUTO=src/graphene_map/demo-auto.jsonl)."""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import demo, plan
from graphene_map.store import Store

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dev" / "proof" / "auto.sh"
MAKE = ROOT / "dev" / "proof" / "make_wordkit.py"


def node(id, title, scope, check, goal):
    return {"id": id, "title": title, "goal": goal, "scope": list(scope), "check": check, "needs": [],
            "parent": None, "mark": "?"}  # fmt: skip


TREE = {"says": "Three wishes, three tasks: each owns one file and its own test file, so all three run at once.",
        "goal": None, "board": [], "nodes": [
    node("top", "the CLI prints the top words", ["wordkit/cli.py", "tests/test_top.py"],
         "python3 -m unittest tests.test_top", "`--top N` prints the N most common words with their counts"),
    node("reading", "a reading time in minutes", ["wordkit/reading.py", "tests/test_reading.py"],
         "python3 -m unittest tests.test_reading", "whole minutes at 200 words a minute, rounded up"),
    node("hyphens", "hyphenated words stay whole", ["wordkit/clean.py", "tests/test_hyphens.py"],
         "python3 -m unittest tests.test_hyphens", "well-known is one word, not two"),
]}  # fmt: skip
FIX = {"says": "hyphens landed as asked; tests/test_count.py still counts well-known as two words.",
       "goal": None, "board": [], "nodes": [
    node("count-test", "the old count test agrees with the hyphens", ["tests/test_count.py"],
         "python3 -m unittest tests.test_count",
         "well-known is one word now, as the goal asks: the test that counted it as two counts three"),
]}  # fmt: skip

CLI = textwrap.dedent('''\
    """python3 -m wordkit.cli FILE [--top N]: print how many words FILE has, and its N most common."""
    import argparse
    import sys

    from wordkit.count import top_words, word_count


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(prog="wordkit")
        parser.add_argument("file")
        parser.add_argument("--top", type=int, default=0, metavar="N", help="also print the N most common words")
        args = parser.parse_args(argv)
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
        print(f"{word_count(text)} words")
        for word, n in top_words(text, args.top):
            print(f"{n} {word}")
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ''')
TOP_TEST = textwrap.dedent('''\
    import contextlib
    import io
    import pathlib
    import tempfile
    import unittest

    from wordkit.cli import main


    def run(*argv):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "notes.txt"
            path.write_text("b a b c b a", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert main([str(path), *argv]) == 0
            return out.getvalue().splitlines()


    class TestTop(unittest.TestCase):
        def test_top_prints_the_most_common_words(self):
            self.assertEqual(run("--top", "2"), ["6 words", "3 b", "2 a"])
    ''')
TOP_TEST_MORE = TOP_TEST + (
    "\n    def test_no_top_prints_the_count_alone(self):\n"
    '        self.assertEqual(run(), ["6 words"])\n'
)
READING = textwrap.dedent('''\
    """Reading time."""
    import math

    from wordkit.count import word_count


    def minutes(text: str, wpm: int = 200) -> int:
        """Whole minutes to read ``text`` at ``wpm`` words a minute, rounded up."""
        return math.ceil(word_count(text) / wpm)
    ''')
READING_SHORT = textwrap.dedent('''\
    """Reading time."""
    from wordkit.count import word_count


    def minutes(text: str, wpm: int = 200) -> int:
        return -(-word_count(text) // wpm)  # whole minutes, rounded up
    ''')
READING_TEST = textwrap.dedent('''\
    import unittest

    from wordkit.reading import minutes


    class TestReading(unittest.TestCase):
        def test_a_started_minute_counts(self):
            self.assertEqual(minutes("word " * 201), 2)

        def test_no_words_no_minutes(self):
            self.assertEqual(minutes(""), 0)
    ''')
WORD = """_WORD = re.compile(r"[a-z0-9']+")"""
HYPHENS = """_WORD = re.compile(r"[a-z0-9']+(?:-[a-z0-9']+)*")"""
HYPHENS_SAID = """# a word may hold hyphens inside it (well-known, state-of-the-art), never at its ends
_WORD = re.compile(r"[a-z0-9']+(?:-[a-z0-9']+)*")"""
HYPHENS_TEST = textwrap.dedent('''\
    import unittest

    from wordkit.clean import normalize


    class TestHyphens(unittest.TestCase):
        def test_a_hyphenated_word_stays_whole(self):
            self.assertEqual(normalize("A well-known, state-of-the-art tool"), "a well-known state-of-the-art tool")
    ''')
HYPHENS_TEST_MORE = HYPHENS_TEST + (
    "\n    def test_a_hyphen_at_an_end_is_not_a_word(self):\n"
    '        self.assertEqual(normalize("well- known"), "well known")\n'
)
OLD_COUNT = """    def test_a_hyphen_splits_a_word(self):
        self.assertEqual(word_count("a well-known word"), 4)"""
NEW_COUNT = """    def test_a_hyphen_splits_a_word(self):
        self.assertEqual(word_count("a well-known word"), 3)"""
RENAMED_COUNT = """    def test_a_hyphenated_word_is_one_word(self):
        self.assertEqual(word_count("a well-known word"), 3)  # well-known is one word since hyphens"""

# Each fork's steps, by the task its prompt names (`<id> (revision`) and its letter (`fork x of 3`).
SCRIPTS = {
    "top": {
        "a": [call("view", path="wordkit/cli.py"), call("write", path="wordkit/cli.py", content=CLI),
              call("write", path="tests/test_top.py", content=TOP_TEST_MORE),
              call("run", command="python3 -m unittest tests.test_top"), call("done")],
        "b": [call("write", path="wordkit/cli.py", content=CLI),
              call("write", path="tests/test_top.py", content=TOP_TEST), call("done")],
        # the top words' ties want a rule in count.py, which is no file of this task's: stopped, it says so
        "c": [call("view", path="wordkit/count.py"),
              call("edit", path="wordkit/count.py", old="most_common(n)", new="most_common(max(n, 0))"),
              call("release", why="a negative N wants a guard in count.py, outside this task's files",
                   wants=["wordkit/count.py"])],
    },
    "reading": {
        "a": [call("write", path="wordkit/reading.py", content=READING),
              call("write", path="tests/test_reading.py", content=READING_TEST), call("done")],
        "b": [call("write", path="wordkit/reading.py", content=READING_SHORT),
              call("write", path="tests/test_reading.py", content=READING_TEST),
              call("run", command="python3 -m unittest tests.test_reading"), call("done")],
        "c": [call("view", path="wordkit/count.py"), call("write", path="wordkit/reading.py", content=READING),
              call("write", path="tests/test_reading.py", content=READING_TEST), call("done")],
    },
    "hyphens": {
        "a": [call("view", path="wordkit/clean.py"),
              call("release", why="a hyphen at a word's end (well-) is not said: keep it or drop it?")],
        "b": [call("edit", path="wordkit/clean.py", old=WORD, new=HYPHENS),
              call("write", path="tests/test_hyphens.py", content=HYPHENS_TEST),
              call("run", command="python3 -m unittest tests.test_hyphens"), call("done")],
        "c": [call("edit", path="wordkit/clean.py", old=WORD, new=HYPHENS_SAID),
              call("write", path="tests/test_hyphens.py", content=HYPHENS_TEST_MORE), call("done")],
    },
    "count-test": {
        "a": [call("view", path="tests/test_count.py"),
              call("edit", path="tests/test_count.py", old=OLD_COUNT, new=RENAMED_COUNT), call("done")],
        "b": [call("edit", path="tests/test_count.py", old=OLD_COUNT, new=NEW_COUNT),
              call("run", command="python3 -m unittest tests.test_count"), call("done")],
        # it would undo the hyphens instead: clean.py is no file of this task's, and the write is stopped
        "c": [call("edit", path="wordkit/clean.py", old=HYPHENS, new=WORD),
              call("edit", path="tests/test_count.py", old=OLD_COUNT, new=NEW_COUNT), call("done")],
    },
}
ULTRA = [call("list", path="."), call("read", path="wordkit/count.py"), call("read", path="tests/test_count.py"),
         {"content": "I have read enough."}]  # fmt: skip
# seconds a fork thinks before a step: every fork is seen at work at once, and they end at different looks
THINKS = {"a": 1.2, "b": 0.7, "c": 1.6}


def reply(body):
    first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    if "Ultra" in body["model"]:
        if body.get("response_format"):
            return {"content": json.dumps(FIX if "has landed, and its own check still fails" in first else TREE)}
        time.sleep(0.3)
        return ULTRA[k] if k < len(ULTRA) else ULTRA[-1]
    task = next((t for t in SCRIPTS if f"{t} (revision" in first), None)
    fork = re.search(r"fork ([a-h]) of \d", first)
    steps = SCRIPTS.get(task, {}).get(fork.group(1) if fork else "b", [])
    time.sleep(THINKS.get(fork.group(1) if fork else "b", 0.5))
    return steps[k] if k < len(steps) else {"content": "nothing more"}


def script(tmp_path, answer, **more: str):
    """auto.sh on wordkit against the fake, answered by ``answer``: the finished script, all it said in the
    order a terminal shows it, and the fake."""
    with Fake([answer] * 200) as f:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GRAPHENE_", "CLAUDE", "CODEX"))
               and k not in ("SHOW_DEMO", "RECORD_DEMO", "RECORD_DEMO_AUTO", "NEBIUS_PROJECT_ID", "AI_AGENT")}  # fmt: skip
        env |= f.env() | {"MAKE_REPO": f"{sys.executable} {MAKE}", "HOME": str(tmp_path),
                          "GRAPHENE_PERSON": "the script"} | more  # fmt: skip
        done = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "wordkit")], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=env, timeout=600)  # fmt: skip
    return done, done.stdout, f


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_auto_races_three_tasks_catches_what_broke_between_them_and_lands_the_fix(tmp_path):
    print_it, ship = os.environ.get("SHOW_DEMO"), os.environ.get("RECORD_DEMO_AUTO")
    done, said, f = script(tmp_path, reply, RECORD=str(tmp_path / "demo-auto.jsonl"))
    if print_it:
        print(said)
    assert done.returncode == 0, said
    assert "$ graphene auto wordkit grows three things at once" in said
    assert "accepted inside your envelope (auto on since " in said and "): top, reading, hyphens." in said
    assert "3 tasks can run at once" in said
    # the race: one fork a task stopped or gave up, the rule keeps one of the others
    assert "top fork c: gave up: a negative N wants a guard in count.py" in said  # its write there was stopped
    assert "hyphens fork a: gave up: a hyphen at a word's end (well-) is not said" in said
    for task in ("top", "reading", "hyphens"):
        assert re.search(rf"{task} kept [abc] of 3: ", said), task
    # the goal's check catches what passed alone and broke together, and Ultra plans the fix
    assert "the goal's check failed: FAIL: test_a_hyphen_splits_a_word" in said
    assert "round 2: planning the fix" in said and "count-test" in said
    assert re.search(r"count-test kept [ab] of 3: ", said)  # c was stopped undoing the hyphens
    last = [line for line in said.splitlines() if line.startswith("auto: ")][-1]
    assert last.startswith("auto: 2 rounds, 4 tasks landed, 0 came back, 12 forks raced, $"), last
    assert "the goal's check passed" in last
    assert "2 writes refused" in said  # top's c in count.py, count-test's c in clean.py: neither theirs
    assert "which this leaf changed: read that diff (`graphene node diff count-test`)" in said
    assert "bill: $" in said and "at list price" in said
    repo = tmp_path / "wordkit"
    assert subprocess.run([sys.executable, "-m", "unittest"], cwd=repo, capture_output=True).returncode == 0
    merges = subprocess.run(["git", "-C", str(repo), "log", "--merges", "--format=%s"],
                            capture_output=True, text=True).stdout.splitlines()  # fmt: skip
    assert len(merges) == 4
    models = {r["model"] for r in f.requests}
    assert models == {"nvidia/Nemotron-3-Ultra-fake", "nvidia/Nemotron-3-Nano-fake"}
    assert json.dumps(f.requests).count("fake-key") == 0
    # the recording replays to where the run ended: a stand-in's, saying so
    recorded = (tmp_path / "demo-auto.jsonl").read_text()
    head, lines = demo.load(tmp_path / "demo-auto.jsonl")
    assert head["stand_in"] is True and "stand-in" in head["shown"] and head["repository"] == "wordkit"
    (tmp_path / "replay").mkdir()
    replay = demo.repository(tmp_path / "replay", head)
    demo.last_frame(replay, lines)
    with Store.open(replay) as store:
        states = {n.id: n.state for n in plan.nodes(store)}
        assert {states[t] for t in ("top", "reading", "hyphens", "count-test")} == {"done"}
    assert str(tmp_path) not in recorded
    if ship:  # RECORD_DEMO_AUTO=src/graphene_map/demo-auto.jsonl: the recording `graphene demo --auto` ships
        shutil.copy(tmp_path / "demo-auto.jsonl", ship)


def test_graphene_demo_auto_replays_the_shipped_recording_with_no_key_and_no_network(tmp_path, monkeypatch):
    """`graphene demo --auto` is the README's first command: the recording this file makes, replayed to its last
    frame, a stand-in's and saying so, with nothing reached for."""
    import socket

    from typer.testing import CliRunner

    from graphene_map.cli import build

    def no_network(*_):
        raise AssertionError("graphene demo --auto reached for the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # anywhere: no repository here
    monkeypatch.setenv("COLUMNS", "200")
    said = CliRunner().invoke(build(), ["demo", "--auto", "--once"])
    assert said.exit_code == 0, said.output
    first = said.stdout.splitlines()[0]
    assert first.startswith("replay · a scripted stand-in, no model ran · ") and "the plan of wordkit" in first
    assert "4 leaves, 4 done, 0 running · finished" in said.stdout
    assert "the old count test agrees with the hyphens" in said.stdout
    head, lines = demo.load(demo.AUTO_TAKE)
    assert head["stand_in"] is True and len(lines) > 40
