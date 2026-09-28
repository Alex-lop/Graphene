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
from graphene_map import tokenfactory as tf
from graphene_map.ask import ask, named
from graphene_map.cli import build
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
    assert lines[-1] == "graphene board take|drop|park|unpark ID · pick ID N · answer ID TEXT · note TEXT"
    assert max(len(line) for line in lines) <= 80  # 80 columns
    assert lines[1] == "questions" and lines[2].split()[-2:] == ["which-id", "open"]
    assert "      default: the row id; schema.py already has it" in lines
    option = lines.index("      1: a uuid column, added to schema.py")
    assert lines[option + 1] == "         then: scope users + schema.py"
    assert [line for line in lines[:-1] if not line.startswith(" ")] == [
        lines[0], "questions", "assumptions", "risks", "left out", "notes"
    ]  # fmt: skip
    as_json = json.loads(person("board", "--json").stdout)
    assert [it["id"] for it in as_json["items"]] == IDS
    assert as_json["conditions"] == []


def test_the_person_takes_picks_drops_parks_and_answers_each_by_cli(repo, tmp_path):
    planned(repo, tmp_path)
    assert person("plan", "accept").exit_code == 0
    took = person("board", "take", "int-ids")
    assert took.exit_code == 0 and took.stdout == "taken int-ids: ids are integers\n"
    picked = person("board", "pick", "which-id", "1")
    assert picked.stdout.splitlines() == [
        "picked which-id: which id: the row id or a new uuid? → a uuid column, added to schema.py",
        "  changed: users: scope + schema.py",
    ]
    assert person("board", "drop", "paging").exit_code == 0
    assert person("board", "park", "empty-check").exit_code == 0
    assert person("board", "answer", "shape", "keep", "it", "a", "list").exit_code == 0
    noted = person("board", "note", "no", "new", "dependency", "--about", "users")
    assert noted.exit_code == 0 and noted.stdout.startswith("noted no-new-dependency: no new dependency")
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
    shown = person("board").stdout.splitlines()
    assert shown[0] == "the board: 0 open, 1 parked, 4 settled"
    assert [line for line in shown[:-1] if not line.startswith(" ")][1:] == ["parked", "settled"]


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
    assert "· claude:5e55105e's" in person("board").stdout
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
    person("plan", "accept")
    person("board", "pick", "which-id", "1")
    person("board", "take", "int-ids")
    person("board", "note", "keep", "it", "short")
    shown = person("node", "show", "users").stdout
    assert "  decided: which id: the row id or a new uuid? → a uuid column, added to schema.py\n" in shown
    assert "  decided: assumed: ids are integers\n" in shown
    assert "  decided: keep it short\n" in shown  # the person's own note is told as written
    script, told = repo.parent / f"{repo.name}-executor.py", repo.parent / f"{repo.name}-told.txt"
    script.write_text(EXECUTOR)  # beside the repo, so neither is anybody's stray file
    monkeypatch.setenv("TOLD", str(told))
    with Store.open(repo) as store:
        run_plan(store, repo, f"{sys.executable} {script}", say=lambda _: None, logs=repo / ".graphene/runs")
        assert P.get(store, "users").state == P.DONE
    told = told.read_text()
    assert "  decided: which id: the row id or a new uuid? → a uuid column, added to schema.py" in told
    assert told.index("decided:") < told.index("scope:  api.py, schema.py")


EFFECTS = """\
question: one  [one]
    default: widen it
    then: scope users + schema.py
    option: a new check
    then: check users: test -f api.py
    option: none of it
    then: drop users
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
    with Fake([{"content": NEMOTRON}]) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        with Store.open(repo) as store:
            ask(store, repo, "ids", named("nemotron"), say=lambda _: None)
            assert [(it["id"], it["by"]) for it in B.items(store)] == [
                ("which-id", "planner:nemotron"), ("int-ids", "planner:nemotron")
            ]  # fmt: skip
            [bill] = store.node_log("*", ("usage",))
            assert bill["detail"]["prompt"] == 2
    system = f.requests[0]["messages"][0]["content"]
    assert "put a question on the board with the default" in system
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
        shown = rows(store)
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
        shown = rows(store)
    assert max(cell_len(line) for line in shown) <= 80, "\n".join(shown)
    assert any(
        line.rstrip().endswith("  abcdefghijklmnopqrstuvwxyz012345  open") for line in shown
    )  # whole id
    assert any(line.startswith("         then: scope users + pyproject.toml") for line in shown)


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


def test_a_condition_is_said_to_be_recorded_for_the_settings_never_changed(repo):
    with Store.open(repo) as store:
        T.apply(store, "risk: vendored  [vendor]\n    default: leave it\n    then: condition vendor/**\n",
                PLANNER, None)  # fmt: skip
    took = person("board", "take", "vendor")
    assert took.stdout.splitlines()[1:] == ["  recorded: condition vendor/**, for the settings"]
    assert "      recorded: condition vendor/**, for the settings" in person("board").stdout
    with Store.open(repo) as store:
        assert B.conditions(store) == ["vendor/**"]  # the seam the settings read


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
    assert back.exit_code == 0 and back.stdout == "open int-ids: ids are integers\n"
    again = person("board", "unpark", "int-ids")
    assert again.exit_code == 1 and "int-ids is open, not parked" in again.stderr
    assert person("plan", "undo").stdout == "undid: board unpark int-ids\n"
    with Store.open(repo) as store:
        assert B.get(store, "int-ids")["state"] == "parked"
