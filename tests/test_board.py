# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The board: the planner puts up what the repository cannot answer, the person answers each with one
command, and an answer reaches the executors and changes the plan as the person's own edit. The planner
here is a script that prints what a model would (as in tests/test_ask.py), and Nemotron is the scripted
fake (tests/fake_tokenfactory.py)."""

import json
import signal
import subprocess
import sys
import time

import pytest
from fake_tokenfactory import Fake
from test_plan_cli import AGENT_ENV, agent, person, repo, runner  # noqa: F401  (fixtures)

from graphene_map import board as B
from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map.ask import ask, named
from graphene_map.cli import build
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.run import run_plan
from graphene_map.store import Store

ALEX = P.Caller("alex", True)
IDS = ["which-id", "int-ids", "empty-check", "paging", "shape"]
CLI = [sys.executable, "-c", "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"]
PLANNER = P.Caller("planner:script", False, "s1")
BLOCK = """\
goal: users come back with their ids
question: which id: the row id or a new uuid?  [which-id]
    default: the row id; schema.py already has it
    option: a uuid column, added to schema.py
    then: scope users + schema.py
    about: users
assume: ids are integers  [int-ids]
risk: the check could pass on an empty list  [empty-check]
    default: add a sample user
    then: leaf "a sample user in api.py" under users
leave out: pagination; nobody asked for it  [paging]
note: keep the response shape  [shape]
? users returns ids  [users]
    scope: api.py
    check: grep -q ids api.py
"""
SCRIPT = f"""
print("I read api.py and schema.py.")
print("```plan")
print({BLOCK!r}, end="")
print("```")
print("schema.py answers where ids live, so I did not ask.")
"""


def planned(repo, tmp_path):
    script = tmp_path / "planner.py"
    script.write_text(SCRIPT)
    said = person("ask", "users should come back with their ids", "--with", f"{sys.executable} {script}")
    assert said.exit_code == 0, said.output
    return said


def test_the_planners_items_land_on_the_board_as_the_planners(repo, tmp_path):
    said = planned(repo, tmp_path)
    assert "put up which-id: which id: the row id or a new uuid?" in said.stdout
    assert "the planner says:\n  I read api.py and schema.py." in said.stdout  # its prose, still printed
    with Store.open(repo) as store:
        assert [it["id"] for it in B.shown(store)] == IDS
        assert all(it["by"].startswith("planner:") and it["agent"] for it in B.items(store))
        assert {it["state"] for it in B.items(store)} == {"open"}
        [q] = [it for it in B.items(store) if it["kind"] == "question"]
        assert q["options"] == [
            {"text": "a uuid column, added to schema.py", "then": ["scope users + schema.py"]}
        ]
        assert q["about"] == "users"
        assert B.decided(store) == []  # nothing is told before the person answers
        assert [e["detail"]["item"] for e in store.node_log("*", ("board",))] == [
            "int-ids", "empty-check", "paging", "shape"
        ]  # fmt: skip
        assert store.node_log("users", ("board",))[0]["detail"]["act"] == "put up"  # on the node it is about
    shown = person("board")
    assert shown.exit_code == 0
    lines = shown.stdout.splitlines()
    assert lines[0] == "the board: 5 open"
    assert lines[-2:] == [
        "graphene board take|drop|park|unpark ID · pick ID N · answer ID TEXT · note TEXT",
        "left open, an item takes its default when you accept the plan",
    ]
    assert max(len(line) for line in lines) <= 80  # 80 columns
    assert lines[1] == "questions" and lines[2].split()[-2:] == ["which-id", "open"]
    assert "      default: the row id; schema.py already has it" in lines
    option = lines.index("      1: a uuid column, added to schema.py")
    assert not any("then:" in line for line in lines)  # what answering needs: the effects are in --all
    every = person("board", "--all").stdout.splitlines()
    at = every.index("      1: a uuid column, added to schema.py")
    assert every[at + 1] == "         then: scope users + schema.py"
    assert [line for line in lines[:-2] if not line.startswith(" ")] == [
        lines[0], "questions", "assumptions", "risks", "left out", "notes"
    ]  # fmt: skip
    assert option
    as_json = json.loads(person("board", "--json").stdout)
    assert [it["id"] for it in as_json["items"]] == IDS
    assert as_json["conditions"] == []


def test_the_person_takes_picks_drops_parks_and_answers_each_by_cli(repo, tmp_path):
    planned(repo, tmp_path)
    took = person("board", "take", "int-ids")
    assert took.exit_code == 0 and took.stdout == "taken int-ids\n"  # one short line: it was just read
    picked = person("board", "pick", "which-id", "1")
    assert picked.stdout.splitlines() == ["picked which-id: option 1", "  changed: users: scope + schema.py"]
    assert person("board", "drop", "paging").exit_code == 0
    assert person("board", "park", "empty-check").exit_code == 0
    assert person("board", "answer", "shape", "keep", "it", "a", "list").exit_code == 0
    noted = person("board", "note", "no", "new", "dependency", "--about", "users")
    assert noted.exit_code == 0 and noted.stdout == "noted no-new-dependency\n"
    assert person("plan", "accept").exit_code == 0  # nothing left open has a default: nothing is taken
    with Store.open(repo) as store:
        states = {it["id"]: (it["state"], it["answer"]) for it in B.items(store)}
        assert states == {
            "which-id": ("picked", "a uuid column, added to schema.py"),
            "int-ids": ("taken", None),
            "empty-check": ("parked", None),
            "paging": ("dropped", None),
            "shape": ("answered", "keep it a list"),
            "no-new-dependency": ("open", None),
        }
        assert P.get(store, "users").scope == ["api.py", "schema.py"]
        acts = [e["detail"]["act"] for e in store.node_log(None, ("board",))]
        assert acts[-6:] == ["took", "picked", "dropped", "parked", "answered", "put up"]
    again = person("board", "take", "which-id")
    assert again.exit_code == 1 and "which-id is picked already" in again.stderr
    wrong = person("board", "pick", "which-id", "3")
    assert wrong.exit_code == 1
    unknown = person("board", "park", "nothing")
    assert unknown.exit_code == 1 and "no item nothing on the board" in unknown.stderr
    no_zero = person("board").stdout.splitlines()[0]
    assert no_zero == "the board: 1 parked, 4 settled, 1 dropped"  # never "0 open"
    shown = person("board", "--all").stdout.splitlines()
    # walk 2026-09-28: the dropped item vanished here while watch counted it: it is listed, last
    assert shown[0] == "the board: 1 parked, 4 settled, 1 dropped"
    assert [line for line in shown[:-1] if not line.startswith(" ")][1:] == ["parked", "settled", "dropped"]
    assert any(" paging " in line and line.endswith("dropped") for line in shown)


def test_an_agent_cannot_answer_and_its_note_waits_for_the_person(repo, tmp_path):
    planned(repo, tmp_path)
    for act in (["take", "int-ids"], ["pick", "which-id", "1"], ["drop", "paging"], ["park", "paging"],
                ["answer", "shape", "yes"]):  # fmt: skip
        refused = agent("board", *act)
        assert refused.exit_code == 1
        assert refused.stderr.strip() == "answering the board is the person's, not claude:5e55105e's"
    noted = agent("board", "note", "the tests are slow")
    assert noted.exit_code == 0
    answered = agent("plan", "propose", "-", input="note: mine  [mine]\n    answer: default\n")
    assert answered.exit_code == 1 and "line 2: answering the board is the person's" in answered.stderr
    with Store.open(repo) as store:
        [mine] = [it for it in B.items(store) if it["text"] == "the tests are slow"]
        assert mine["agent"] and mine["by"].startswith("claude:") and B.reads(mine) == "open"
        assert B.decided(store) == []  # an agent's note is not told until the person takes it
    assert "(claude:5e55105e's)" in person("board").stdout
    assert person("board", "take", mine["id"]).exit_code == 0
    with Store.open(repo) as store:
        assert B.decided(store) == ["the tests are slow"]


EXECUTOR = """
import os, pathlib, sys
pathlib.Path(os.environ["TOLD"]).write_text(sys.argv[-1])
pathlib.Path("api.py").write_text("def users():\\n    return ids\\n")
"""


def test_an_answer_reaches_the_executors_contract(repo, tmp_path, monkeypatch):
    planned(repo, tmp_path)
    person("board", "pick", "which-id", "1")
    person("board", "take", "int-ids")
    person("board", "note", "keep", "it", "short")
    person("board", "park", "empty-check")
    person("board", "drop", "paging")
    person("plan", "accept")  # what is left open takes its default: the planner's note, told as written
    shown = person("node", "show", "users").stdout
    assert (
        "  goal:   users returns ids\n"
        "  decided:\n"
        "          which id: the row id or a new uuid? → a uuid column, added to schema.py\n"
        "          assumed: ids are integers\n"
        "          keep the response shape\n"
        "          keep it short\n"  # the person's own note is told as written
        "  scope:  api.py, schema.py"
    ) in shown  # each decision starts in the column every other value does
    script, told = repo.parent / f"{repo.name}-executor.py", repo.parent / f"{repo.name}-told.txt"
    script.write_text(EXECUTOR)  # beside the repo, so neither is anybody's stray file
    monkeypatch.setenv("TOLD", str(told))
    with Store.open(repo) as store:
        run_plan(store, repo, f"{sys.executable} {script}", say=lambda _: None, logs=repo / ".graphene/runs")
        assert P.get(store, "users").state == P.DONE
    told = told.read_text()
    assert (
        "  decided:\n          which id: the row id or a new uuid? → a uuid column, added to schema.py"
        in told
    )
    assert told.index("decided:") < told.index("scope:  api.py, schema.py")


EFFECTS = """\
question: one  [one]
    default: widen it
    then: scope users + schema.py
    option: a new check
    then: check users: test -f api.py
    option: none of it
    then: drop users
    option: tell it
    then: goal users + Keep the response shape.
risk: two  [two]
    default: a leaf
    then: leaf "a sample" under users
    then: condition vendor/*
"""


@pytest.mark.parametrize(
    "act, changed",
    [
        (["take", "one"], lambda s: P.get(s, "users").scope == ["api.py", "schema.py"]),
        (["pick", "one", "1"], lambda s: P.get(s, "users").check == "test -f api.py"),
        (["pick", "one", "2"], lambda s: P.get(s, "users").state == P.DROPPED),
        (["pick", "one", "3"], lambda s: P.get(s, "users").goal == "Keep the response shape."),
        (["take", "two"], lambda s: [P.get(s, "sample").state, *B.conditions(s)] == ["proposed", "vendor/*"]),
    ],
)
def test_each_then_effect_applies_as_the_persons_edit_and_undoes(repo, act, changed):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        T.apply(store, EFFECTS, PLANNER, None)
        before = (T.render(store)[0], [P.to_dict(n) for n in P.nodes(store)])
    assert person("board", *act).exit_code == 0
    with Store.open(repo) as store:
        assert changed(store)
        assert B.get(store, act[1])["became"]
    undone = person("plan", "undo")
    assert undone.exit_code == 0 and undone.stdout == f"undid: board {' '.join(act)}\n"
    with Store.open(repo) as store:
        assert (T.render(store)[0], [P.to_dict(n) for n in P.nodes(store) if n.id != "sample"]) == (
            before[0],
            [{**n, "rev": P.get(store, n["id"]).rev} for n in before[1]],
        )
        assert B.conditions(store) == [] and B.get(store, act[1])["state"] == "open"


def test_undo_does_not_lose_what_the_planner_put_up_since(repo):
    with Store.open(repo) as store:
        T.apply(store, "assume: one  [one]\n", PLANNER, None)
    person("board", "take", "one")
    with Store.open(repo) as store:
        T.apply(store, "assume: two  [two]\n", PLANNER, None)
    person("board", "park", "two")
    with Store.open(repo) as store:
        T.apply(store, "risk: three  [three]\n", PLANNER, None)
    for act in ("board park two", "board take one"):  # the person's own acts, last first
        undone = person("plan", "undo")
        assert undone.exit_code == 0 and undone.stdout == f"undid: {act}\n", undone.output
    with Store.open(repo) as store:
        assert [(it["id"], it["state"]) for it in B.items(store)] == [
            ("one", "open"), ("two", "open"), ("three", "open")
        ]  # fmt: skip


def test_an_effect_or_about_that_names_no_node_is_refused_by_its_line(repo):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        for text, said in (
            ("question: q  [q]\n    default: d\n    then: scope nobody + x\n", "line 3: then: scope nobody"),
            ("question: q  [q]\n    about: nobody\n", "line 2: about: nobody, which is not a node"),
            ("risk: r  [r]\n    then: drop users\n", "line 2: then: goes under the default: or option:"),
            ("risk: r  [r]\n    default: d\n    then: rename users\n", "line 3: then: 'rename users' is not"),
            ("assume: a  [a]\n    option: o\n", "line 2: option: is a question's"),
            ("question: q  [q]\n    option:\n", "line 2: an option: needs its words"),
            ("assume: a  [a]\n    default: d\n    scope: x\n", "line 3: 'scope: x' is under a assume"),
        ):
            with pytest.raises(P.Refused, match=said.replace("(", r"\(")):
                T.apply(store, text, PLANNER, None)
        assert B.items(store) == []  # a refused text applies nothing


ALL = """\
goal: users come back with their ids

question: which id?  [q-open]
    default: the row id
    option: a uuid
    then: scope users + schema.py
    about: users
question: picked  [q-picked]
    default: d
    option: o1
    option: o2
    answer: option 2
assume: taken  [a-taken]
    answer: default
risk: parked  [r-parked]
    default: d
    then: leaf "x y" under users
    answer: parked
leave out: answered  [l-answered]
    answer: not this week
risk: an effect with no words for its default  [r-bare]
    default:
    then: condition vendor/*
note: open  [n-open]

- users  [users]
    # ready
    scope: api.py
    check: true
"""


def test_the_text_form_round_trips_every_kind_and_state(repo):
    with Store.open(repo) as store:
        T.apply(store, ALL, ALEX, None)
        B.drop(store, B.add(store, "note", "gone", ALEX)["id"], ALEX)
        text, opened = T.render(store)
        assert text == ALL  # what the person wrote is what is written back
        rest, found = B.split(text)
        assert len(rest.splitlines()) == len(text.splitlines())  # every other line keeps its number
        assert [f["id"] for f in found] == list(opened["*board"])
        assert T.apply(store, text, ALEX, opened) == []  # read back and applied again, it changes nothing
        assert T.render(store)[0] == text
        states = {it["id"]: it["state"] for it in B.items(store)}
        assert states == {"q-open": "open", "q-picked": "picked", "a-taken": "taken", "r-parked": "parked",
                          "l-answered": "answered", "r-bare": "open", "n-open": "open",
                          "gone": "dropped"}  # fmt: skip


def test_plan_edit_answers_by_adding_answer_lines_and_drops_by_deleting(repo, tmp_path, monkeypatch):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        T.apply(store, BLOCK.split("? users")[0], PLANNER, None)
    edit = (
        "text = text.replace('[int-ids]\\n', '[int-ids]\\n    answer: default\\n')"
        ".replace('    about: users\\n', '    about: users\\n    answer: option 1\\n')"
        ".replace('leave out: pagination; nobody asked for it  [paging]\\n', '')"
        ".replace('    answer: parked\\n', '')"
        ".replace('note: keep the response shape  [shape]\\n', 'note: keep the response shape  [shape]\\n"
        "    answer: as it is today\\nnote: and fast\\n')"
    )
    script = tmp_path / "edit.py"
    script.write_text(f"import sys\np = sys.argv[1]\ntext = open(p).read()\n{edit}\nopen(p, 'w').write(text)")
    monkeypatch.setenv("EDITOR", f"{sys.executable} {script}")
    monkeypatch.delenv("VISUAL", raising=False)
    said = person("plan", "edit")
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines() == [
        "picked which-id: users: scope + schema.py", "taken int-ids", "answered shape",
        "put up fast: and fast", "dropped paging: pagination; nobody asked for it",
    ]  # fmt: skip
    with Store.open(repo) as store:
        assert P.get(store, "users").scope == ["api.py", "schema.py"]
        states = {it["id"]: it["state"] for it in B.items(store)}
        assert states["paging"] == "dropped" and states["fast"] == "open"
        assert B.get(store, "shape")["answer"] == "as it is today"
    assert person("plan", "undo").stdout == "undid: plan edit\n"
    with Store.open(repo) as store:
        assert P.get(store, "users").scope == ["api.py"]
        assert {it["state"] for it in B.items(store)} == {"open"}


def test_a_refused_answer_in_the_text_names_its_line(repo):
    with Store.open(repo) as store:
        T.apply(store, "question: q  [q]\n    default: d\n", PLANNER, None)
        B.take(store, "q", ALEX)
        text, opened = T.render(store)
        changed = text.replace("answer: default", "answer: option 1")
        with pytest.raises(P.Refused, match=r"line 3: q is taken already \(d\); `graphene plan undo`"):
            T.apply(store, changed, ALEX, opened)


NEMOTRON = """```plan
question: which id?  [which-id]
    default: the row id; schema.py already has it
assume: ids are integers  [int-ids]
? users returns ids  [users]
    scope: api.py
    check: grep -q ids api.py
```"""


def test_nemotron_is_told_to_ask_and_its_board_lands(repo, monkeypatch):
    with Fake([{"content": NEMOTRON}] * 2) as f:  # its draft, then its answer
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        with Store.open(repo) as store:
            ask(store, repo, "ids", named("nemotron"), say=lambda _: None)
            assert [(it["id"], it["by"]) for it in B.items(store)] == [
                ("which-id", "planner:nemotron"), ("int-ids", "planner:nemotron")
            ]  # fmt: skip
            [bill] = store.node_log("*", ("usage",))
            assert bill["detail"]["prompt"] == 5
    system = " ".join(f.requests[0]["messages"][0]["content"].split())
    assert "put a question on the board with the default" in system and "at most three" in system
    assert "An assumption you are confident of is not an item but a sentence in the goal" in system
    prompt = f.requests[0]["messages"][1]["content"]
    assert "question: what the words leave open and the repository cannot settle" in prompt
    assert "Never ask what it answers: name the file that answers" in prompt


def test_the_replay_works_with_a_plan_that_has_a_board(repo, tmp_path):
    planned(repo, tmp_path)
    out = repo.parent / f"{repo.name}-rec.jsonl"
    recorder = subprocess.Popen([*CLI, "demo", "--record", out], cwd=repo, stderr=subprocess.PIPE, text=True)
    for _ in range(100):
        if out.exists() and out.read_text():
            break
        time.sleep(0.1)
    person("board", "take", "int-ids")
    time.sleep(1.5)
    recorder.send_signal(signal.SIGTERM)
    assert recorder.wait(timeout=20) == 0, recorder.stderr.read()
    replayed = runner.invoke(build(), ["demo", str(out), "--once"])
    assert replayed.exit_code == 0, replayed.output
    assert "users returns ids" in replayed.stdout


def test_a_board_with_nothing_but_dropped_items_reads_as_empty(repo):
    from graphene_map.board_cli import EMPTY

    assert person("board").stdout == EMPTY + "\n"
    person("board", "note", "later")
    assert person("board", "drop", "later").exit_code == 0
    assert person("board").stdout == EMPTY + "\n"


def test_a_leaf_effect_under_a_leaf_puts_the_new_leaf_beside_it_and_keeps_it_a_leaf(repo):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "feed", "title": "the feed"},
                          {"id": "zero", "title": "zero price", "parent": "feed", "scope": ["feed.py"],
                           "check": "true"}], ALEX)  # fmt: skip
        risk = 'risk: no zero sample  [r]\n    default: add one\n    then: leaf "a sample" under zero\n'
        T.apply(store, risk, PLANNER, None)
    took = person("board", "take", "r")
    assert took.exit_code == 0, took.output
    assert "  changed: proposed sample beside zero, a leaf, under feed" in took.stdout
    # walk 2026-09-28 (first 10): the new leaf is to fill in, and the take said nothing of it
    assert "under feed; it has no scope or check yet (`graphene node set sample`)" in took.stdout
    with Store.open(repo) as store:
        assert P.get(store, "sample").parent == "feed"
        assert {n.id for n in P.leaves(P.nodes(store))} == {"zero", "sample"}


@pytest.mark.parametrize(
    "deleted, line",
    [
        ("question: which id?  [q-open]\n", 3),
        ("risk: an effect with no words for its default  [r-bare]\n", 21),
    ],
)
def test_deleting_only_an_items_own_line_is_refused_by_the_line_of_what_it_leaves(repo, deleted, line):
    with Store.open(repo) as store:
        T.apply(store, ALL, ALEX, None)
        text, opened = T.render(store)
        with pytest.raises(P.Refused, match=f"^line {line}: these lines belong to no board item"):
            T.apply(store, text.replace(deleted, ""), ALEX, opened)
        assert T.render(store)[0] == text  # nothing moved: not the goal, not the item above


def test_wide_characters_keep_the_boards_columns_and_a_note_with_no_ascii_is_called_a_note(repo):
    from rich.cells import cell_len

    from graphene_map.board_cli import rows

    with Store.open(repo) as store:
        wide = B.note(store, "日本語のメモ", ALEX)
        B.note(store, "plain words", ALEX)
        assert wide["id"] == "note"  # not "node", which reads as the plan's
        shown = rows(store, everything=True)  # the person's notes are settled: listed with --all
    at = [
        cell_len(ln[: ln.index(f" {i} ")])
        for i in ("note", "plain-words")
        for ln in shown
        if f"  {i}  " in ln
    ]
    assert len(at) == 2 and at[0] == at[1]
    assert cell_len(T.elide("日本語のメモ " * 10, 12)) <= 12


LONG = """\
question: which XML parser: the standard library's ElementTree or lxml, faster but not installed?  [parser]
    default: the standard library's ElementTree, because lxml is not installed and nothing else needs it here
    option: lxml, added to pyproject.toml
    then: scope users + pyproject.toml, requirements.txt, requirements-dev.txt, setup.cfg, tox.ini
"""


def test_the_board_shows_an_items_whole_text_wrapped_under_its_row(repo):
    from graphene_map.board_cli import rows

    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        T.apply(store, LONG, PLANNER, None)
        shown = rows(store)
    row = next(k for k, line in enumerate(shown) if line.endswith("parser  open"))
    words = " ".join(line.split("  parser  ")[0].strip(" ◇") for line in shown[row : row + 3])
    assert words.startswith("which XML parser: the standard library's ElementTree or lxml, faster")
    assert "but not installed?" in words  # the whole question, not cut at 44 characters
    assert shown[row + 1].startswith("    ") and "parser" not in shown[row + 1]  # under its row
    default = " ".join(line.strip() for line in shown if line.startswith("      ") and "then:" not in line)
    assert "because lxml is not installed and nothing else needs it here" in default


def test_the_board_fits_80_columns_with_the_longest_id_an_agents_note_and_a_long_effect(repo):
    from rich.cells import cell_len

    from graphene_map.board_cli import rows

    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        T.apply(store, LONG + "question: a question whose id is long?  [abcdefghijklmnopqrstuvwxyz012345]\n"
                "    default: yes\n", PLANNER, None)  # fmt: skip
        B.note(store, "the tests are slow on this machine", P.Caller("planner:script", False, "s1"))
        short, shown = rows(store), rows(store, everything=True)
    assert max(cell_len(line) for line in short) <= 80, "\n".join(short)
    assert max(cell_len(line) for line in shown) <= 80, "\n".join(shown)
    assert any(
        line.rstrip().endswith("  abcdefghijklmnopqrstuvwxyz012345  open") for line in shown
    )  # whole id
    at = next(k for k, line in enumerate(shown) if line.startswith("         then: scope users + pyproject"))
    assert shown[at + 1] == "               requirements-dev.txt, setup.cfg, tox.ini"  # wrapped, whole


def test_what_the_person_dropped_is_told_to_the_planner_and_not_put_up_again(repo):
    from graphene_map.ask import prompt_for

    with Store.open(repo) as store:
        T.apply(store, "risk: a planner item added later  [later]\n", PLANNER, None)
    assert person("board", "drop", "later").exit_code == 0
    with Store.open(repo) as store:
        prompt = prompt_for(store, "again")
        assert "do not put them up again:\n- a planner item added later\n" in prompt
        said = T.apply(store, "risk: A planner item  added later  [later]\n", PLANNER, None)
        assert said == ["not put up again: A planner item added later (the person dropped it as later)"]
        assert [it["state"] for it in B.items(store)] == ["dropped"]


def test_a_condition_binds_as_a_read_only_glob_until_undone(repo):
    """`then: condition GLOB` was only recorded ("nothing enforces it yet"): it now feeds the settings'
    read-only list, so a scope over it is refused and `graphene config` shows it, until plan undo."""
    from graphene_map import settings as S

    (repo / "vendor").mkdir()
    (repo / "vendor" / "lib.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "vendor"], cwd=repo, check=True)  # judged against what git tracks
    with Store.open(repo) as store:
        T.apply(store, "risk: vendored  [vendor]\n    default: leave it\n    then: condition vendor/**\n",
                PLANNER, None)  # fmt: skip
        with pytest.raises(P.Refused, match=r"^line 3: '/etc' is not inside the repo"):
            T.apply(store, "risk: r  [r]\n    default: d\n    then: condition /etc\n", PLANNER, None)
    took = person("board", "take", "vendor")
    said = "  changed: no leaf may write vendor/** (read-only, as `graphene config` shows)"
    assert took.stdout.splitlines()[1:] == [said]
    assert "      changed: no leaf may write vendor/**" in person("board", "--all").stdout
    with Store.open(repo) as store:
        assert B.conditions(store) == ["vendor/**"] == S.readonly(store)
        assert "No leaf may write these paths: vendor/**." in S.conditions_for_planner(store)
    config = person("config").stdout
    assert "# answered: readonly vendor/** (plan undo takes it back)" in config  # not a second `board:`
    refused = person("node", "add", "lib", "--scope", "vendor/**", "--check", "true")
    assert refused.exit_code == 1 and "`readonly: vendor/**` keeps out of every scope" in refused.output
    # walk 2026-09-28: under a header saying '#' lines are not read, the rule read as switched off
    assert "# In force too, each changed by the command it names" in config
    assert person("plan", "undo").exit_code == 0
    with Store.open(repo) as store:
        assert S.readonly(store) == []
    assert person("node", "add", "lib", "--scope", "vendor/**", "--check", "true").exit_code == 0


def test_under_inside_a_quoted_leaf_title_is_the_titles():
    assert B.effect('leaf "profile under load"') == ("leaf", None, "profile under load")
    assert B.effect("leaf 'profile under load' under users") == ("leaf", "users", "profile under load")
    assert B.effect("leaf a sample under users") == ("leaf", "users", "a sample")


def test_an_edit_with_no_board_still_forgets_a_planners_sentence_whose_tree_is_gone(repo):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        store.set_meta("goal:proposed", "a sentence whose tree is gone")
        text, opened = T.render(store)
        T.apply(store, text, ALEX, opened)
        assert store.meta("goal:proposed") is None


def test_graphene_plan_says_what_the_board_waits_on_you_for(repo, tmp_path):
    with Store.open(repo) as store:
        T.apply(store, "question: q1?  [q1]\nquestion: q2?  [q2]\nrisk: r  [r]\n", PLANNER, None)
    bare = person("plan").stdout.splitlines()
    assert bare[0] == "the board: 2 questions, 1 risk open (`graphene board`)"
    assert bare[1].startswith("nothing is planned here yet")
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
    person("board", "park", "r")
    shown = person("plan").stdout
    assert "\nthe board: 2 questions open (`graphene board`)\n" in shown
    assert "waiting on you: 2 on the board (`graphene board`)" in shown


def test_unpark_opens_a_parked_item_again_and_is_one_undoable_command(repo):
    with Store.open(repo) as store:
        T.apply(store, "assume: ids are integers  [int-ids]\n", PLANNER, None)
    person("board", "park", "int-ids")
    back = person("board", "unpark", "int-ids")
    assert back.exit_code == 0 and back.stdout == "open int-ids\n"
    again = person("board", "unpark", "int-ids")
    assert again.exit_code == 1 and "int-ids is open, not parked" in again.stderr
    assert person("plan", "undo").stdout == "undid: board unpark int-ids\n"
    with Store.open(repo) as store:
        assert B.get(store, "int-ids")["state"] == "parked"


def test_a_goal_effect_ends_the_leafs_goal_with_the_sentence_once_and_is_refused_by_its_line(repo):
    """A pick that contradicted a leaf's goal left the goal as it was, so the person rewrote it by hand
    (the evaluation's biggest stall, 11 of 55): `then: goal NODE + TEXT` puts the sentence on the leaf."""
    with Store.open(repo) as store:
        P.propose(store, [{"id": "wire", "title": "wire", "goal": "Enable the source", "scope": ["api.py"],
                           "check": "true"}], ALEX)  # fmt: skip
        said = '    then: goal wire + "Do not enable the source; Ops enables it."\n'
        asked = "question: who enables it?  [enable]\n    default: we do\n    option: Ops does\n"
        T.apply(store, asked + said, PLANNER, None)
        assert said in T.render(store)[0]  # as it was written
        B.pick(store, "enable", 1, ALEX)
        assert P.get(store, "wire").goal == "Enable the source. Do not enable the source; Ops enables it."
        assert B.get(store, "enable")["became"] == ["wire: goal + Do not enable the source; Ops enables it."]
        with pytest.raises(P.Refused, match=r"^line 3: then: goal ghost \+ x names ghost, which is not a"):
            T.apply(store, "question: q  [q]\n    default: d\n    then: goal ghost + x\n", PLANNER, None)
    assert B.effect("goal wire + said twice") == ("goal", "wire", "said twice")


PICKED = """```plan
question: who enables the xml source?  [enable]
    default: we do, in config/defaults.py
    option: Ops enables it; we only add the reader
    then: goal users + "Do not enable the source: Ops does."
    then: check users: grep -q ids api.py
? users returns ids  [users]
    Return ids and enable the source.
    scope: api.py, schema.py
    check: grep -q ids api.py && grep -q ids schema.py
```"""
RULE = "carries the then: lines that make that change"


def _picked_reaches_the_leaf(store):
    B.pick(store, "enable", 1, ALEX)
    users = P.get(store, "users")
    assert users.goal == "Return ids and enable the source. Do not enable the source: Ops does."
    assert users.check == "grep -q ids api.py"


def test_a_script_planner_is_told_that_an_option_carries_its_then_lines_and_the_pick_reaches_the_leaf(
    repo, tmp_path
):
    """The evaluation's biggest stall (11 of 55): a pick that contradicted a leaf's goal left the leaf as
    it was. The planner is now told to write the then: lines, and when it does, the pick changes the leaf."""
    script = tmp_path / "planner.py"
    script.write_text(f"import sys\nopen({str(tmp_path / 'prompt.txt')!r}, 'w').write(sys.argv[-1])\n"
                      f"print({PICKED!r})\n")  # fmt: skip
    said = person("ask", "users come back with ids", "--with", f"{sys.executable} {script}")
    assert said.exit_code == 0, said.output
    prompt = " ".join((tmp_path / "prompt.txt").read_text().split())
    assert RULE in prompt and 'goal NODE + "SENTENCE"' in prompt
    with Store.open(repo) as store:
        _picked_reaches_the_leaf(store)


def test_nemotron_is_told_that_an_option_carries_its_then_lines_and_the_pick_reaches_the_leaf(
    repo, monkeypatch
):
    with Fake([{"content": PICKED}] * 2) as f:  # its draft, then its answer
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        with Store.open(repo) as store:
            ask(store, repo, "ids", named("nemotron"), say=lambda _: None)
            _picked_reaches_the_leaf(store)
    system, prompt = (" ".join(m["content"].split()) for m in f.requests[0]["messages"][:2])
    assert "carries the then: lines that make that change (goal, scope, check, drop, leaf)" in system
    assert RULE in prompt


def test_an_ask_that_puts_up_board_items_names_the_board_as_what_waits(repo, tmp_path, monkeypatch):
    """Walk 2026-09-28: an ask that put up 5 board items ended by pointing only at the tree, and
    typed at watch's `:` it told the person to open the screen they were on."""
    said = planned(repo, tmp_path)
    assert "the board waits on you (5): `graphene board`, or `graphene watch`" in said.stdout
    assert "prune it: `graphene watch`" in said.stdout  # a leaf was proposed too
    monkeypatch.setenv("GRAPHENE_WATCH", "")
    again = planned(repo, tmp_path)
    assert "at the top, y takes, d drops" in again.stdout and "`graphene watch`" not in again.stdout


def test_a_finer_ask_carries_a_picks_change_to_the_leaf_the_planner_wrote_again(repo, tmp_path):
    """Walk 2026-09-28 (all three walkers): a pick widened a leaf, `+` asked again finer, the leaf was
    dropped with the old tree, the new one lacked the change, and nothing said so. The planner wrote the
    leaf again under its old [id]; the leaf it became has the pick's scope, and the board says so."""
    planned(repo, tmp_path)
    assert person("board", "pick", "which-id", "1").exit_code == 0
    script = tmp_path / "planner.py"
    sentence, planner = "users should come back with their ids", f"{sys.executable} {script}"
    again = person("ask", sentence, "--finer", "--with", planner)
    assert again.exit_code == 0, again.output
    assert "users is dropped; users-returns-ids is the same node in the new tree" in again.stdout
    assert "carried: users-returns-ids: scope + schema.py (from which-id)" in again.stdout
    with Store.open(repo) as store:
        assert P.get(store, "users-returns-ids").scope == ["api.py", "schema.py"]
        assert B.get(store, "which-id")["became"] == ["users-returns-ids: scope + schema.py"]


def test_an_answer_in_words_to_an_item_whose_default_changes_the_plan_says_it_changed_nothing(repo, tmp_path):
    """Walk 2026-09-28: `board answer` on a risk whose default adds a leaf changed nothing in the tree,
    and nothing said so."""
    planned(repo, tmp_path)
    said = person("board", "answer", "empty-check", "yes,", "add", "a", "sample").stdout.splitlines()
    assert said[0].startswith("answered empty-check")
    assert said[1] == (
        "  your words go to executors as written and change no leaf; `graphene plan undo`, "
        "then `graphene board take empty-check`, applies the default's change"
    )
    plain = person("board", "answer", "shape", "keep", "it").stdout.splitlines()
    assert len(plain) == 1  # a note has no change to apply: nothing more is said


def test_a_condition_over_a_leafs_scope_names_that_leaf(repo):
    """A board condition is a read-only glob as a setting is, so a take that newly covers a leaf's scope
    names the leaf, as a `graphene config` save does, before an executor is sent to it."""
    added = person("node", "add", "users", "--id", "users", "--scope", "api.py", "--check", "true")
    assert added.exit_code == 0, added.output
    with Store.open(repo) as store:
        T.apply(store, "risk: shared  [shared]\n    default: d\n    then: condition api.py\n", PLANNER, None)
    took = person("board", "take", "shared")
    assert took.exit_code == 0, took.output
    assert "users: its scope (api.py) now covers api.py, kept out by `readonly: api.py`" in took.stdout


def test_one_answer_cannot_widen_a_scope_over_its_own_condition(repo):
    """The answer's condition binds its own scope effect, as it would one taken after it."""
    added = person("node", "add", "users", "--id", "users", "--scope", "api.py", "--check", "true")
    assert added.exit_code == 0, added.output
    with Store.open(repo) as store:
        T.apply(store, "risk: both  [both]\n    default: d\n    then: scope users + schema.py\n"
                "    then: condition schema.py\n", PLANNER, None)  # fmt: skip
    took = person("board", "take", "both")
    assert took.exit_code == 1 and "`readonly: schema.py` keeps out of every scope" in took.output
    with Store.open(repo) as store:
        assert P.get(store, "users").scope == ["api.py"] and B.conditions(store) == []


def test_a_condition_that_differs_from_a_tracked_path_only_in_case_is_refused(repo):
    with Store.open(repo) as store:
        T.apply(store, "risk: r  [r]\n    default: d\n    then: condition API.py\n", PLANNER, None)
    took = person("board", "take", "r")
    assert took.exit_code == 1 and "`API.py` matches nothing git tracks, and `api.py` differs" in took.output


def test_an_item_about_a_node_that_left_the_plan_is_not_answered_and_the_pane_says_told_to_no_one(repo):
    from graphene_map import board_rows as BR

    with Store.open(repo) as store:
        users = {"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}
        P.propose(
            store, [users, {"id": "docs", "title": "docs", "scope": ["README.md"], "check": "true"}], ALEX
        )
        asked = "question: which id?  [which-id]\n    default: the row id\n    about: users\n"
        asked += "question: which docs?  [which-docs]\n    default: the readme\n    about: docs\n"
        T.apply(store, asked, PLANNER, None)
    assert person("board", "take", "which-docs").exit_code == 0
    assert person("node", "drop", "users").exit_code == 0
    assert person("node", "drop", "docs").exit_code == 0
    for act in (["take", "which-id"], ["answer", "which-id", "a", "uuid"]):
        refused = person("board", *act)
        assert refused.exit_code == 1 and "which-id is about users, which has left the plan" in refused.stderr
    assert person("board", "drop", "which-id").exit_code == 0  # dropping it is still the person's
    with Store.open(repo) as store:
        board = BR.read(store, shown=True)  # the fold on a screen that showed the board: nothing is open now
        pane = str(BR.pane(board, BR.Row("item", "which-docs"), {n.id: n for n in P.nodes(store)}, 80))
    assert "to no one: docs has left the plan" in pane and "the executors of docs" not in pane


def test_plan_edit_does_not_reword_an_item_already_answered(repo):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        asked = "question: which id?  [which-id]\n    default: the row id\n    then: condition schema.py\n"
        T.apply(store, asked + "    about: users\n", PLANNER, None)
        B.take(store, "which-id", ALEX)
        text, opened = T.render(store)
        edited = text.replace("default: the row id", "default: a new uuid").replace(
            "condition schema.py", "condition api.py"
        )
        with pytest.raises(
            P.Refused, match=r"^line \d+: \[which-id\] is taken \(the row id\); `graphene plan undo`"
        ):
            T.apply(store, edited, ALEX, opened)
        assert B.get(store, "which-id")["default"] == "the row id" and B.conditions(store) == ["schema.py"]
        T.apply(store, text.replace("which id?  [which-id]", "which id, then?  [which-id]"), ALEX, opened)


def test_a_goal_effect_is_skipped_only_when_the_goal_has_that_sentence_not_when_it_says_the_opposite(repo):
    no_uuid = "Return the row id; do not add a uuid column."
    assert P.goal_plus(no_uuid, "add a uuid column.") == f"{no_uuid} add a uuid column."
    assert P.goal_plus("Do not enable the source.", "Enable the source.") is not None
    assert P.goal_plus("Keep ids", "id") == "Keep ids. id"
    assert P.goal_plus("Keep ids. Return them sorted.", "return them sorted") is None  # it has it already
    assert P.goal_plus("Keep ids; add a uuid column", "Add a uuid column.") is None
    with Store.open(repo) as store:
        users = {"id": "users", "title": "users", "goal": no_uuid, "scope": ["api.py"], "check": "true"}
        P.propose(store, [users], ALEX)
        T.apply(store, "question: which id?  [which-id]\n    default: the row id\n    option: a uuid column\n"
                "    then: goal users + add a uuid column.\n", PLANNER, None)  # fmt: skip
    picked = person("board", "pick", "which-id", "1")
    assert "users: goal + add a uuid column." in picked.stdout and "says it already" not in picked.stdout


def test_dropping_an_answered_item_says_the_read_only_glob_it_lifts_and_the_edits_that_stay(repo):
    risk = "risk: someone edits schema.py  [schema]\n    default: leave it\n    then: condition schema.py\n"
    risk += "    then: goal users + Never touch the schema.\n"
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        T.apply(store, risk + "risk: again  [again]\n" + risk.split("\n", 1)[1], PLANNER, None)
    assert person("board", "take", "schema").exit_code == 0
    dropped = person("board", "drop", "schema").stdout.splitlines()
    assert dropped[1:] == [
        "  no longer read-only: schema.py",
        "  what it changed stays: users: goal + Never touch the schema.",
    ]
    assert person("board", "take", "again").exit_code == 0
    with Store.open(repo) as store:
        text, opened = T.render(store)
        start = text.index("risk: again")
        said = T.apply(store, text[:start] + text[text.index("\n- ", start) :], ALEX, opened)
    assert any("no longer read-only: schema.py" in line for line in said), said


def test_a_person_who_agrees_with_every_default_answers_nothing_and_accept_takes_them(repo, tmp_path):
    planned(repo, tmp_path)
    accepted = person("plan", "accept").stdout.splitlines()
    assert accepted[0] == (
        "accepted users; took the defaults of which-id, int-ids, empty-check, paging, shape, left open on "
        "the board (`graphene plan undo` takes them back)"
    )  # one line, the first, which the screen's bottom line shows
    with Store.open(repo) as store:
        assert {it["state"] for it in B.items(store)} == {"taken"}  # nothing is left waiting unseen
        # walk 2026-09-29 (3, 38): the planner's note stayed open, hidden, and reached no executor
        assert "keep the response shape" in B.decided(store, P.get(store, "users"))
        took = [e for e in store.node_log(None, ("board",)) if e["detail"]["act"] == "took"]
        assert len(took) == 5 and all(e["detail"].get("unchanged") for e in took)
        accepted_by = {e["actor"] for e in store.node_log(None, ("accepted",))}
        assert {e["actor"] for e in took} == accepted_by  # as the person
        assert "sample-user-api" in {n.id for n in P.nodes(store)}  # the risk's default, applied
    assert person("plan", "undo").exit_code == 0  # one act: the acceptance, and the defaults with it
    with Store.open(repo) as store:
        assert {it["state"] for it in B.items(store)} == {"open"}
        assert P.get(store, "users").state == P.PROPOSED


def test_take_with_no_id_takes_every_open_default_and_run_takes_what_is_left_open(repo, tmp_path):
    planned(repo, tmp_path)
    assert person("board", "pick", "which-id", "1").exit_code == 0
    refused = agent("board", "take")
    assert refused.exit_code == 1 and "answering the board is the person's" in refused.stderr
    took = person("board", "take")
    assert took.stdout.startswith("took the defaults of int-ids, empty-check, paging, shape, left open")
    assert person("board", "take").stdout == "nothing open on the board has a default to take\n"
    assert person("plan", "undo").exit_code == 0
    with Store.open(repo) as store:
        P.accept(store, ["users"], ALEX)  # as the store is, without the command: what is open stays open
        assert [it["id"] for it in B.items(store) if it["state"] == "open"] == [
            "int-ids", "empty-check", "paging", "shape"
        ]  # fmt: skip
    ran = person("run", "--with", "true", "--node", "users")
    assert "took the defaults of int-ids, empty-check, paging, shape, left open" in ran.stdout
    with Store.open(repo) as store:
        assert B.get(store, "which-id")["state"] == "picked"  # the person's own answer stays theirs


def test_a_planners_note_on_the_board_names_the_planner_by_its_script_not_its_interpreter(repo, tmp_path):
    """Walk 2026-09-28 (judge 17): a planner's note read `keep the JSONL shape · planner:python3's`."""
    from graphene_map.board_cli import _words

    planned(repo, tmp_path)
    with Store.open(repo) as store:
        said = _words(B.get(store, "shape"))  # by its script, as one word a wrap never splits
        assert said.startswith("keep the response shape (planner:") and "python" not in said, said


def test_a_run_that_starts_nothing_answers_nothing_and_a_default_dropping_a_leaf_waits(repo, tmp_path):
    """Walk 2026-09-29 (16): R with nothing ready took the board's defaults, one of which dropped a leaf."""
    planned(repo, tmp_path)
    with Store.open(repo) as store:
        B.add(store, "question", "is users needed?", PLANNER, default="no", then=["drop users"], item_id="q1")
    accepted = person("plan", "accept").stdout.splitlines()[0]
    assert accepted.endswith("; left for you: q1 (its default drops users)")
    with Store.open(repo) as store:
        assert B.get(store, "q1")["state"] == "open" and P.get(store, "users").state == P.OPEN
        B.add(store, "risk", "the list could be long", PLANNER, default="page it", item_id="long")
        P.edit(store, "users", {"needs": ["sample-user-api"]}, ALEX)  # waits on a proposal: nothing is ready
    ran = person("run", "--with", "true")
    assert "took" not in ran.stdout and "left for you" not in ran.stdout, ran.stdout
    with Store.open(repo) as store:
        assert B.get(store, "long")["state"] == "open" and B.get(store, "q1")["state"] == "open"
        assert P.get(store, "users").state == P.OPEN


def test_take_with_no_id_says_which_default_it_left_because_it_drops_a_node(repo, tmp_path):
    """Review 2026-09-29 (26): with only a default that drops a node open, `graphene board take` said
    "nothing open on the board has a default to take", which the board's own row contradicts."""
    planned(repo, tmp_path)
    assert person("board", "take").exit_code == 0  # every other open default is taken
    with Store.open(repo) as store:
        B.add(store, "question", "is users needed?", PLANNER, default="no", then=["drop users"], item_id="q1")
    said = person("board", "take").stdout
    assert said == "left for you: q1 (its default drops users)\n", said
    with Store.open(repo) as store:
        assert B.get(store, "q1")["state"] == "open" and P.get(store, "users").state != P.DROPPED


def test_undoing_a_board_answer_says_so_in_the_plans_log(repo, tmp_path):
    """Walk 2026-09-29 (5): the answer stayed the log's last line, with no undo after it."""
    planned(repo, tmp_path)
    assert person("board", "answer", "paging", "none", "needed").exit_code == 0
    assert person("plan", "undo").exit_code == 0
    with Store.open(repo) as store:
        [undone] = store.node_log(None, ("undone",))
        assert undone["node_id"] == "*"
        assert undone["detail"] == {"note": "board answer paging", "item": "paging"}
        assert store.node_log()[-1]["kind"] == "undone"
    assert "undone" in person("plan", "log").stdout.splitlines()[-1]


def test_the_print_takes_the_terminals_width_and_keeps_a_notes_byline_whole(repo, tmp_path, monkeypatch):
    """Walk 2026-09-29 (29, 44): titles wrapped at about 46 columns at any width, and a note's byline
    split from its words with a dangling `·`."""
    planned(repo, tmp_path)
    with Store.open(repo) as store:
        asked = "legacy/priceimport.py skips the zero-price rule; should the xml path skip it too?"
        B.add(store, "question", asked, PLANNER, default="yes", item_id="zero")
        B.note(store, "prices in the XML are already cents", P.Caller("planner:planner.py", False, "s1"))
    monkeypatch.setenv("COLUMNS", "160")
    wide = person("board").stdout.splitlines()
    assert any("skip it too?" in line and line.split()[-2:] == ["zero", "open"] for line in wide), wide
    assert any("prices in the XML are already cents (planner:planner.py's)" in line for line in wide)
    monkeypatch.setenv("COLUMNS", "80")
    narrow = person("board").stdout.splitlines()
    assert max(len(line) for line in narrow) <= 80
    assert not any(line.rstrip().endswith("·") for line in narrow)
    assert any("(planner:planner.py's)" in line for line in narrow)


def test_a_reask_whose_items_the_board_has_already_says_so_and_the_screen_does_not_say_nothing(
    repo, tmp_path
):
    """Walk 2026-09-29 (alex 27): after `+`, a planner that put up the same items it had before, all
    settled by then, was reported as "the planner proposed nothing and put nothing on the board", and
    nothing anywhere said its items were kept as the board had them."""
    from graphene_map.tui import Watch

    planned(repo, tmp_path)
    assert person("board", "take", "int-ids").exit_code == 0
    script = tmp_path / "planner.py"
    again = person("ask", "users should come back with their ids", "--with", f"{sys.executable} {script}")
    assert "int-ids is on the board already (taken): not put up again" in again.stdout, again.stdout
    log = repo / ".graphene" / "runs" / "ask-again.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    line = next(ln for ln in again.stdout.splitlines() if "int-ids is on the board already" in ln)
    log.write_text(f"asking the planner (planner.py)…\n{line}\n")
    app, told = Watch(repo, lambda: Store.open(repo), every=60), []
    app.call_from_thread = lambda fn, message, whole: told.append(message)

    class Done:
        def wait(self):
            return 0

    app.follow(Done(), ["ask", "--finer", "users should come back with their ids"], log)
    said = "the planner put int-ids up again, which the board has already; what it said is in the pane"
    assert told == [said]


SHARED = """\
risk: schema.py is shared with billing  [shared]
    default: leave it alone
    then: condition schema.py
question: should users add the id column to schema.py?  [id-column]
    default: yes
    then: scope users + schema.py
"""


@pytest.mark.parametrize("how", [("board", "take"), ("plan", "accept")])
def test_a_default_whose_change_is_refused_is_not_taken_half(repo, how):
    """Review 2026-09-29 (5): a take whose effect was refused (a scope over a glob a default taken just
    before made read-only) stayed `taken` with nothing changed, and executors were told it as decided."""
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], PLANNER)
        T.apply(store, SHARED, PLANNER, None)
    said = person(*how)
    assert said.exit_code == 0 and "took the default of shared, left open" in said.stdout, said.output
    with Store.open(repo) as store:
        item = B.get(store, "id-column")
        assert (item["state"], item["became"]) == ("open", [])  # all or none: none
        assert P.get(store, "users").scope == ["api.py"]
        assert not any("id column" in line for line in B.decided(store, P.get(store, "users")))
        acts = [(e["detail"]["act"], e["detail"]["item"]) for e in store.node_log(None, ("board",))]
        assert [item for act, item in acts if act == "took"] == ["shared"]


def test_another_agents_note_waits_for_the_person_and_shows_under_auto(repo, tmp_path):
    """Review 2026-09-29 (7): an executor's note was taken by the person's R unseen, and told to every
    other executor as decided."""
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        B.note(store, "every leaf may also rewrite tests", P.Caller("run:ex.sh", False, "s2"))
        B.note(store, "the tests are slow", PLANNER)  # a planner's note is taken, as decision 123 says
        assert B.asks(store)  # under auto, it is shown: nothing takes it for you
    assert "the board: 2 notes open" in person("plan").stdout  # auto shows the board, both notes on it
    took = person("board", "take").stdout
    assert took.startswith("took the default of tests-are-slow, left open"), took
    with Store.open(repo) as store:
        [waiting] = [it for it in B.items(store) if it["state"] == "open"]
        assert waiting["text"] == "every leaf may also rewrite tests"
        assert "every leaf may also rewrite tests" not in B.decided(store)


def test_r_takes_no_default_that_would_leave_it_nothing_to_start(repo):
    """Review 2026-09-29 (8): R took a default whose condition made the one ready leaf's scope
    read-only, then started nothing."""
    added = person("node", "add", "users", "--id", "users", "--scope", "api.py", "--check", "true")
    assert added.exit_code == 0, added.output
    with Store.open(repo) as store:
        T.apply(store, "risk: api.py is shared with mobile  [shared]\n    default: keep it read-only\n"
                "    then: condition api.py\n", PLANNER, None)  # fmt: skip
    ran = person("run", "--with", "true")
    assert "took" not in ran.stdout, ran.stdout
    with Store.open(repo) as store:
        from graphene_map import settings as S

        assert B.get(store, "shared")["state"] == "open" and "api.py" not in S.readonly(store)


@pytest.mark.parametrize("ident", ["which-id-the-users-endpoint1", "abcdefghijklmnopqrstuvwxyz012345"])
def test_the_print_keeps_the_words_at_40_columns_whatever_the_id(repo, monkeypatch, ident):
    """Review 2026-09-29 (11): at 40 columns a 28-character id crashed the print, and a 32-character
    one left the row with no words."""
    with Store.open(repo) as store:
        asked = f"question: which id should the users endpoint return?  [{ident}]\n    default: the row id\n"
        T.apply(store, asked, PLANNER, None)
    monkeypatch.setenv("COLUMNS", "40")
    shown = person("board")
    assert shown.exit_code == 0, shown.output
    row = next(line for line in shown.stdout.splitlines() if ident in line)
    assert "which id" in row


JUDGED = """\
question: what does leaf-a's check run?  [a-runs]
    default: leaf-b's test
    then: check leaf-a: python3 -m pytest tests/test_b.py
question: who writes tests/test_a.py?  [a-writes]
    default: leaf-a
    then: scope leaf-a + tests/test_a.py
question: may leaf-a write tests/test_b.py too?  [a-takes]
    default: yes
    then: scope leaf-a + tests/test_b.py
"""
A_WAITS = "leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes"
B_WAITS = "leaf-b waits on leaf-a: its check runs tests/test_a.py, which leaf-a writes"


@pytest.mark.parametrize(
    "item, said, needs",
    [
        ("a-runs", f"leaf-a: check is now python3 -m pytest tests/test_b.py; {A_WAITS}",
         {"leaf-a": ["leaf-b"], "leaf-b": []}),
        ("a-writes", f"leaf-a: scope + tests/test_a.py; {B_WAITS}",
         {"leaf-a": [], "leaf-b": ["leaf-a"]}),
        ("a-takes", "leaf-a and leaf-b both write tests/test_b.py. A path has one leaf that writes it",
         {"leaf-a": [], "leaf-b": []}),
    ],
)  # fmt: skip
def test_an_answer_that_changes_a_check_or_a_scope_is_judged_as_the_persons_edit_would_be(
    repo, item, said, needs
):
    """The loop directive, lane 5: a `then:` line was applied unjudged (decision 171). A leaf whose check
    then ran another leaf's file did not wait on it, and a scope could take in another leaf's path."""
    with Store.open(repo) as store:
        P.propose(store, [{"id": "leaf-a", "title": "a", "scope": ["a.py"], "check": "true"},
                          {"id": "leaf-b", "title": "b", "scope": ["b.py", "tests/test_b.py"],
                           "check": "python3 -m pytest tests/test_a.py"}], ALEX)  # fmt: skip
        T.apply(store, JUDGED, PLANNER, None)
    refused = item == "a-takes"
    took = person("board", "take", item)
    assert took.exit_code == int(refused) and said in took.output, took.output
    with Store.open(repo) as store:
        assert {n.id: n.needs for n in P.nodes(store)} == needs
        assert B.get(store, item)["state"] == ("open" if refused else "taken")  # refused: none of it
