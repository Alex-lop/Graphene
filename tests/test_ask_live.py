# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The plan draws itself: while a planner writes, `graphene state --json` says each step whose line is
complete (`drafting`), so a graph draws it before it is a proposal; once the proposals land, or the ask
ends any other way, nobody is drafting. No model is called: every planner here is a script that prints
what one would, slowly, and waits for a file named `go` before it prints the rest."""

import json
import os
import signal
import subprocess
import sys

import pytest
from test_plan_cli import person, repo  # noqa: F401  (fixtures)
from test_run_live import CLI, ended, wait_for

from graphene_map import ask as A
from graphene_map import plan
from graphene_map import plan_text as T
from graphene_map import state as ST
from graphene_map.plan import PROPOSED, Refused
from graphene_map.store import Store

# An answer as a planner writes one: its own words with a list in them, the block, and a word after it.
BLOCK = """\
goal: wordkit prints the top words of a file
question: count words case-sensitively?  [case]
    default: no, fold to lower case
    option: yes
    then: goal count + "Counts are case-sensitive."
    about: count
- the counting  [counting]
  ? count the words of a text  [count]
      a function that returns each word with its count; lower case, as I assumed
      scope: wordkit/count.py, tests/test_count.py
      check: python3 -m unittest -q tests.test_count
  ? print the top words
      scope: wordkit/cli.py
      check: python3 -m unittest -q
      needs: count
? document it  [docs]
    scope:
      - README.md
      - docs/**
    check: grep -q top README.md
    needs: count, print-top-words
"""
FOUND = "I read wordkit/cli.py and the tests. What I found:\n\n- `cli.py` has no command yet\n- no tests\n\n"
SAID = f"{FOUND}```plan\n{BLOCK}```\n\n- Nothing touches setup.py.\n"
BARE = f"{FOUND}Here is the plan:\n\n{BLOCK}"
STEPS = [
    {"id": "counting", "title": "the counting", "parent": None, "leaf": False, "scope": [], "check": None,
     "needs": []},
    {"id": "count", "title": "count the words of a text", "parent": "counting", "leaf": True,
     "scope": ["wordkit/count.py", "tests/test_count.py"], "check": "python3 -m unittest -q tests.test_count",
     "needs": []},
    {"id": "print-top-words", "title": "print the top words", "parent": "counting", "leaf": True,
     "scope": ["wordkit/cli.py"], "check": "python3 -m unittest -q", "needs": ["count"]},
    {"id": "docs", "title": "document it", "parent": None, "leaf": True, "scope": ["README.md", "docs/**"],
     "check": "grep -q top README.md", "needs": ["count", "print-top-words"]},
]  # fmt: skip


def only_grew(was: list[dict], now: list[dict]) -> bool:
    """Every step said before is still there, in its place, with all it said: a step gains its scope, its
    check and its needs, and stops being a leaf when a child is written under it; nothing else changes."""
    if len(now) < len(was):
        return False
    for a, b in zip(was, now, strict=False):
        same = all(a[k] == b[k] for k in ("id", "title", "parent"))
        grown = all(b[k][: len(a[k])] == a[k] for k in ("scope", "needs"))
        if not (same and grown and a["check"] in (None, b["check"]) and (a["leaf"] or not b["leaf"])):
            return False
    return True


@pytest.mark.parametrize("said", [SAID, BARE], ids=["in a block", "with no fence"])
def test_every_prefix_of_an_answer_reads_as_steps_that_only_grow(said):
    """Whatever the planner has written so far, to the character, is read without a refusal, and what a
    graph drew from it stays: the list in its own words is never a step, in a block or with no fence."""
    was: list[dict] = []
    for cut in range(len(said) + 1):
        now = T.drafted(said[:cut])
        assert isinstance(now, list) and only_grew(was, now), (said[:cut], was, now)
        was = now
    assert was == STEPS


def test_a_step_is_read_when_its_line_ends_and_its_contract_as_each_of_its_lines_does():
    top, child = "```plan\n- the counting  [counting]", "\n  ? count the words  [count]"
    scope = "\n      scope: a.py"
    assert T.drafted(top) == []  # its line has no end yet: the last line is never read
    [first] = T.drafted(top + "\n")
    assert first == {"id": "counting", "title": "the counting", "parent": None, "leaf": True, "scope": [],
                     "check": None, "needs": []}  # fmt: skip
    assert T.drafted(top + child) == [first]
    [first, second] = T.drafted(top + child + "\n")
    assert not first["leaf"]  # a child was written under it
    assert second == {"id": "count", "title": "count the words", "parent": "counting", "leaf": True,
                      "scope": [], "check": None, "needs": []}  # fmt: skip
    assert T.drafted(top + child + scope)[1]["scope"] == []
    assert T.drafted(top + child + scope + "\n      needs: a, b\n")[1] == {**second, "scope": ["a.py"],
                                                                          "needs": ["a", "b"]}  # fmt: skip
    assert T.drafted("") == [] and T.drafted("nothing like a plan\n") == []


def test_a_line_graphene_cannot_read_ends_the_reading_and_the_steps_before_it_stand():
    said = ("```plan\n? one  [one]\n    scope: a.py\n? two  [two]\n    scope: b.py\n    signoff: perhaps\n"
            "    check: true\n? three  [three]\n    scope: c.py\n```\n")  # fmt: skip
    assert [(s["id"], s["scope"], s["check"]) for s in T.drafted(said)] == [
        ("one", ["a.py"], None), ("two", ["b.py"], None)]  # fmt: skip


def test_a_list_in_the_planners_own_words_is_not_drafted_before_its_block_opens():
    """As it writes, nothing says yet that a fence will follow: a list read as steps would be drawn, and
    go when the block opened. With no fence, the plan starts at a line only the plan's text says."""
    words = "What I found:\n- api.py returns no ids\n- schema.py has the column\n"
    assert T.drafted(words) == []
    assert [s["id"] for s in T.drafted(words + "```plan\n? users return ids  [ids]\n")] == ["ids"]
    assert [s["id"] for s in T.drafted(words + "\n? users return ids\n- the schema  [schema]\n")] == [
        "users-return-ids", "schema"]  # fmt: skip


def test_which_planners_write_their_plan_where_it_is_read_as_they_write():
    def live(command: str) -> bool:
        return A.live(A.label(command), A.command_for(command, "the prompt", "s1", False))

    assert "--include-partial-messages" in A.named("claude") and live(A.named("claude"))
    assert not live("claude -p --output-format stream-json --verbose")  # each message whole, and so the plan
    assert not live("claude -p --include-partial-messages")  # which only a stream-json stream carries
    assert not live(A.named("codex")) and not live(A.named("nemotron"))  # their answer is printed once
    assert live(f"{sys.executable} planner.py")  # anything else: what it prints is its text


def event(inner: dict, parent: str | None = None) -> str:
    """One line of Claude Code's stream under `--include-partial-messages`, in the shape 2.1.326 writes."""
    return json.dumps({"type": "stream_event", "event": inner, "session_id": "s1",
                       "parent_tool_use_id": parent, "uuid": "u1"})  # fmt: skip


def delta(text: str, parent: str | None = None) -> str:
    return event({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
                 parent)  # fmt: skip


def test_claude_codes_stream_says_its_text_as_it_is_written():
    assert A.written(delta(" one  [a]\n    sc")) == " one  [a]\n    sc"
    opens = event({"type": "message_start", "message": {"id": "m1", "role": "assistant", "content": []}})
    assert A.written(opens) == "\n"  # the next message's first line is no part of the last one's last
    assert A.written(delta("- not the planner's  [sub]\n", parent="toolu_1")) == ""  # a sub-agent's text
    thought = {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": ""}}
    whole = {"type": "assistant", "message": {"content": [{"type": "text", "text": "- one  [a]\n"}]}}
    result = {"type": "result", "result": 'it said "stream_event"\n'}
    for other in (event(thought), event({"type": "content_block_stop", "index": 0}), json.dumps(whole),
                  json.dumps(result), "not json", '"stream_event"'):  # fmt: skip
        assert A.written(other) == "", other


# What every slow planner here writes: two lines of its plan and half a third, then, told to go, the rest.
HEAD = "- the users API\n  ? users returns ids  [ids]\n      scope: api.py\n      check: grep -q"
TAIL = (" ids api.py\n  ? the schema has ids  [schema]\n      scope: schema.py\n      check: true\n"
        "      needs: ids\n")  # fmt: skip
HALF = [
    {"id": "users-api", "title": "the users API", "parent": None, "leaf": False, "scope": [], "check": None,
     "needs": []},
    {"id": "ids", "title": "users returns ids", "parent": "users-api", "leaf": True, "scope": ["api.py"],
     "check": None, "needs": []},
]  # fmt: skip
SLOW = f"""
import os, pathlib, sys, time
pathlib.Path("up").write_text(str(os.getpid()))
sys.stdout.write("I read api.py and schema.py.\\n```plan\\n" + {HEAD!r})
sys.stdout.flush()
for _ in range(1200):
    if pathlib.Path("go").exists():
        break
    time.sleep(0.05)
else:
    sys.exit(1)
print({TAIL!r} + "```")
"""


def script(repo, source: str = SLOW) -> str:
    (repo / "planner.py").write_text(source)
    return f"{sys.executable} {repo / 'planner.py'}"


def claude(repo, partial: bool) -> str:
    """A stand-in named `claude` that prints Claude Code's stream: a turn that reads a file, then the answer,
    its text in deltas cut mid-line when ``partial`` (the command then has `--include-partial-messages`),
    then the whole message and the result, as the real one does either way."""
    whole = f"```plan\n{HEAD}{TAIL}```\nThe schema has no id column yet."
    opens = event({"type": "message_start", "message": {"id": "m", "role": "assistant", "content": []}})
    read = {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "api.py"}}
    usage = {"input_tokens": 900, "output_tokens": 80}
    words = {"type": "text", "text": "I will read\n- api.py"}
    turn = {"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5-5", "usage": usage,
                                             "content": [words, read]}}  # fmt: skip
    answer = {"type": "assistant", "message": {"id": "m2", "model": "claude-sonnet-5-5", "usage": usage,
                                               "content": [{"type": "text", "text": whole}]}}  # fmt: skip
    result = {"type": "result", "subtype": "success", "result": whole, "total_cost_usd": 0.2}
    # the first message ends mid-line, on a list of its own: the block's fence opens the next one's first line
    head = [opens, delta("I will re"), delta("ad\n- api.py"), json.dumps(turn),
            delta("```plan\n? not the planner's  [sub]\n", parent="toolu_1"), opens, delta("```pl"),
            delta("an\n- the users API\n  ? users ret"), delta("urns ids  [ids]\n      sco"),
            delta("pe: api.py\n      check: grep -q")]  # fmt: skip
    tail = [delta(TAIL + "```\nThe schema has "), delta("no id column yet."), json.dumps(answer),
            json.dumps(result)]  # fmt: skip
    for name, lines in (("head.jsonl", head), ("tail.jsonl", tail)):
        kept = [line for line in lines if partial or '"stream_event"' not in line]
        (repo / name).write_text("".join(f"{line}\n" for line in kept))
    fake = repo / "bin" / "claude"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho $$ > up\ncat head.jsonl\n"
                    "for i in $(seq 1200); do [ -e go ] && break; sleep 0.05; done\n"
                    "[ -e go ] && cat tail.jsonl\n")  # fmt: skip
    fake.chmod(0o755)
    flag = " --include-partial-messages" * partial
    return f"{fake} -p --output-format stream-json --verbose{flag} --max-budget-usd 1.5"


def look(repo) -> dict:
    with Store.open(repo) as store:
        return ST.snapshot(store, repo)


def start(repo, planner: str) -> subprocess.Popen:
    """`graphene ask`, as a process of its own, which is how a screen runs it and how `state` knows it."""
    return subprocess.Popen([*CLI, "ask", "users come back with their ids", "--with", planner], cwd=repo,
                            env={**os.environ, "GRAPHENE_AS": "person:alex"}, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)  # fmt: skip


def stop(repo, asking: subprocess.Popen) -> None:
    asking.kill()
    asking.wait()
    asking.stdout.close()
    if (repo / "up").exists() and not ended(int((repo / "up").read_text())):
        os.kill(int((repo / "up").read_text()), signal.SIGKILL)


def landed(repo) -> None:
    """Nobody is drafting, and what was drafted is proposed: in one commit, so never both, never neither."""
    after = look(repo)
    assert after["drafting"] is None
    assert {t["id"]: (t["state"], t["parent"]) for t in after["tasks"]} == {
        "ids": ("proposed", "users-api"), "schema": ("proposed", "users-api")}  # fmt: skip
    assert [g["id"] for g in after["goals"]] == ["users-api"]
    assert after["edges"] == [["ids", "schema", "needs"]]
    assert json.loads(person("state", "--json").stdout)["drafting"] is None  # as the command prints it


@pytest.mark.parametrize("who", ["a script", "claude"])
def test_while_a_planner_writes_each_step_whose_line_is_complete_is_in_the_snapshot(repo, who):
    """A script's stdout is its text; Claude Code's is a stream, whose text deltas end anywhere in a line.
    Either way the snapshot holds the two steps whose lines ended and the one scope that did, not the check
    half written, and no proposal yet; then the proposals, and no draft."""
    planner, by = (script(repo), "planner.py") if who == "a script" else (claude(repo, True), "claude")
    asking = start(repo, planner)
    try:
        want = {"by": by, "live": True, "steps": HALF}
        assert wait_for(lambda: look(repo)["drafting"] == want), look(repo)["drafting"]
        assert look(repo)["tasks"] == [] and look(repo)["goals"] == []
        (repo / "go").write_text("go")
        said, _ = asking.communicate(timeout=60)
        assert asking.returncode == 0 and "proposed ids: users returns ids" in said, said
    finally:
        stop(repo, asking)
    landed(repo)


def test_a_planner_whose_stream_has_no_text_says_so_and_its_steps_come_when_the_plan_does(repo):
    """Claude Code without `--include-partial-messages` says each message whole: the snapshot says a planner
    is writing and that its plan arrives whole (`live` false), with no step until it has."""
    asking = start(repo, claude(repo, partial=False))
    try:
        want = {"by": "claude", "live": False, "steps": []}
        assert wait_for(lambda: look(repo)["drafting"] == want), look(repo)["drafting"]
        (repo / "go").write_text("go")
        said, _ = asking.communicate(timeout=60)
        assert asking.returncode == 0 and look(repo)["drafting"] is None, said
    finally:
        stop(repo, asking)
    landed(repo)


TWICE = """
import pathlib
first = not pathlib.Path("tried").exists()
pathlib.Path("tried").write_text("x")
ids = "? ids  [ids]\\n    scope: api.py\\n"
bad = ids + "    signoff: perhaps\\n? never  [never]"
good = ids + "    check: true\\n? more  [more]\\n    scope: schema.py\\n    check: true"
print("I read api.py.\\n```plan\\n" + (bad if first else good) + "\\n```")
"""


def test_a_second_try_starts_its_draft_again(repo, monkeypatch):
    """The first answer is refused and the planner is asked again: what the first drafted is on the graph
    until the second starts, then nothing is, then the second's steps; and then they are the proposals,
    with nobody drafting from the commit that made them (the ask's next words are said after it)."""
    wrote: list[list[str]] = []
    write = A._draft
    monkeypatch.setattr(A, "_draft", lambda store, record: (wrote.append([s["id"] for s in record["steps"]]),
                                                            write(store, record)))  # fmt: skip
    seen: dict[str, dict | None] = {}
    with Store.open(repo) as store:
        assert A.ask(store, repo, "ids", script(repo, TWICE), say=lambda line: seen.update(
            {line.split(":")[0]: ST.drafting(store)}))[:2] == ["proposed ids: ids", "proposed more: more"]
        steps = [ids for k, ids in enumerate(wrote) if k == 0 or ids != wrote[k - 1]]  # not what each gained
        assert steps == [[], ["ids"], [], ["ids"], ["ids", "more"]]
        refused = seen["Graphene could not read the proposal"]  # said between the tries: the first's stands
        assert refused and refused["live"] and [s["id"] for s in refused["steps"]] == ["ids"]
        assert "the planner says" in seen and seen["the planner says"] is None  # the proposals are in
        assert ST.drafting(store) is None and store.meta(A.DRAFTING) is None
        assert plan.get(store, "more").state == PROPOSED


def test_an_ask_whose_planner_fails_leaves_nobody_drafting(repo):
    """A planner that wrote half a plan and failed, twice: the ask ends with a refusal, and says itself
    that nobody is drafting (the store's own record is gone, not only passed over)."""
    failing = 'import sys\nprint("```plan\\n? ids  [ids]\\n    scope: api.py", flush=True)\nsys.exit(1)\n'
    with Store.open(repo) as store:
        with pytest.raises(Refused, match="no proposal after 2 tries"):
            A.ask(store, repo, "ids", script(repo, failing), say=lambda _: None)
        assert store.meta(A.DRAFTING) is None and ST.snapshot(store, repo)["drafting"] is None
        assert not plan.nodes(store)
    with Store.open(repo) as store, pytest.raises(Refused, match="cannot run"):
        A.ask(store, repo, "ids", str(repo / "no-such-planner"), say=lambda _: None)
    assert look(repo)["drafting"] is None


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGKILL])
def test_an_ask_that_is_killed_mid_plan_leaves_nobody_drafting(repo, sig):
    """Told to stop (TERM), the ask says nobody is drafting before it goes. Killed outright it says nothing:
    the store still holds its draft, and the snapshot, which knows the ask by its pid and start, says null;
    `--watch` hears of it too, though nothing was written (the store's version moves when the ask goes)."""
    asking = start(repo, script(repo))
    try:
        assert wait_for(lambda: (look(repo)["drafting"] or {}).get("steps") == HALF), look(repo)["drafting"]
        with Store.open(repo) as reader:
            before = ST.version(reader, repo)
            asking.send_signal(sig)
            asking.communicate(timeout=30)
            assert asking.returncode == (130 if sig == signal.SIGTERM else -signal.SIGKILL)
            assert ST.version(reader, repo) != before
            assert (reader.meta(A.DRAFTING) is None) == (sig == signal.SIGTERM)
            assert ST.snapshot(reader, repo)["drafting"] is None
    finally:
        stop(repo, asking)
    assert look(repo)["tasks"] == []


def test_an_ask_that_ends_clears_its_own_draft_and_leaves_another_asks(repo):
    """Two asks can run at once (Home's Plan it and the graph's Fill it in for me). The record is one a
    repository, so the one that wrote last is shown; an ask that ends clears it only when it is its own."""
    with Store.open(repo) as store:
        theirs = json.dumps({"by": "claude", "live": True, "steps": [], "pid": os.getpid() + 1, "start": "x"})
        A._drafting_ends(lambda s: s.set_meta(A.DRAFTING, theirs))(store)  # another ask wrote since
        assert store.meta(A.DRAFTING) == theirs
        mine = json.dumps({"by": "claude", "live": True, "steps": [], "pid": os.getpid(), "start": "x"})
        A._drafting_ends(lambda s: s.set_meta(A.DRAFTING, mine))(store)
        assert store.meta(A.DRAFTING) is None
