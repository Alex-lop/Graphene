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
from test_plan_cli import AGENT_ENV, agent, person, repo, runner  # noqa: F401  (fixtures)

from graphene_map import board as B
from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map.cli import build
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
    assert lines[0] == (
        "the board: 5 open · graphene board take|drop|park ID, pick ID N, answer ID WORDS"
    )
    assert lines[1] == "questions" and lines[2].split()[-2:] == ["which-id", "open"]
    assert "      default: the row id; schema.py already has it" in lines
    assert "      1: a uuid column, added to schema.py  → scope users + schema.py" in lines
    assert [line for line in lines if not line.startswith(" ")] == [
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
    assert shown[0].startswith("the board: 0 open, 1 parked, 4 settled")
    assert [line for line in shown if not line.startswith(" ")][1:] == ["parked", "settled"]


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
    undone = person("plan", "undo")
    assert undone.exit_code == 1 and "the board changed since" in undone.stderr


def test_an_effect_or_about_that_names_no_node_is_refused_by_its_line(repo):
    with Store.open(repo) as store:
        P.propose(store, [{"id": "users", "title": "users", "scope": ["api.py"], "check": "true"}], ALEX)
        for text, said in (
            ("question: q  [q]\n    default: d\n    then: scope nobody + x\n", "line 3: then: scope nobody"),
            ("question: q  [q]\n    about: nobody\n", "line 2: about: nobody, which is not a node"),
            ("risk: r  [r]\n    then: drop users\n", "line 2: then: goes under the default: or option:"),
            ("risk: r  [r]\n    default: d\n    then: rename users\n", "line 3: then: 'rename users' is not"),
            ("assume: a  [a]\n    option: o\n", "line 2: option: is a question's"),
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
                          "l-answered": "answered", "n-open": "open", "gone": "dropped"}  # fmt: skip


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
