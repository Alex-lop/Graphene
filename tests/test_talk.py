# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""Talking on the tree: the person asks the planner about the node under the cursor (why it is there,
split it, merge these, another way), every answer lands in the store (the plan or the board), and what
anyone else changed since the person last looked is marked until they say they have seen it. The planner
is a script that prints what a model would (as in tests/test_ask.py), and Nemotron is the scripted fake
(tests/fake_tokenfactory.py). The screen is driven by keys at 80x24 and 120x36."""

import asyncio
import json
import re
import sys

import pytest
from fake_tokenfactory import Fake
from test_plan_cli import AGENT_ENV, agent, person, repo, runner  # noqa: F401  (fixtures)
from test_plan_text_cli import editor
from test_tui import SIZES, proposed, shown, states, watch

from graphene_map import board as B
from graphene_map import plan as P
from graphene_map import talk
from graphene_map.ask import named
from graphene_map.cli import build
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.store import Store
from graphene_map.tui import Watch

# one script for every kind: it answers what the prompt asks, as a model would
TALKER = r"""
import json, os, re, sys, time
while os.environ.get("GATE") and not os.path.exists(os.environ["GATE"]):  # held until the test has looked
    time.sleep(0.02)
prompt = sys.argv[-1]
open(os.environ["SEEN"], "a").write(json.dumps({"prompt": prompt}) + "\n")
said = re.search(r"The person said: (.*)", prompt)[1]
print("I read api.py.")
print("```plan")
if said.startswith("why"):
    node = said.split()[2]
    ident = re.search(r"note: what you would say  \[([\w.-]+)\]", prompt)[1]
    print(f"note: {node} is there so the API returns ids before the docs describe them  [{ident}]")
    print(f"    about: {node}")
elif said.startswith("merge"):
    print("- the API  [api]")
    print("  ? users return ids, documented  [both]")
    print("      scope: api.py, README.md")
    print("      check: grep -q ids api.py")
else:
    print("? the schema as a migration  [migration]")
    print("    scope: migrations/**")
    print("    check: test -d migrations")
print("```")
"""


@pytest.fixture
def talker(tmp_path, monkeypatch):
    script = tmp_path / "talker.py"
    script.write_text(TALKER)
    monkeypatch.setenv("SEEN", str(tmp_path / "seen.jsonl"))
    return f"{sys.executable} {script}"


def prompts(tmp_path) -> list[str]:
    return [json.loads(line)["prompt"] for line in (tmp_path / "seen.jsonl").read_text().splitlines()]


def accepted(repo):
    proposed(repo)
    assert person("plan", "accept").exit_code == 0


def test_why_lands_on_the_board_as_the_planners_note_about_the_node(repo, talker, tmp_path):
    accepted(repo)
    said = person("talk", "why", "ids", "--with", talker)
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines()[-1] == (
        "the planner on ids: ids is there so the API returns ids before the docs describe them"
    )  # last: the screen's bottom line
    assert "graphene board drop why-ids dismisses it" in said.stdout
    [prompt] = prompts(tmp_path)
    assert "Say why ids is in the plan" in prompt and "ids (revision 1): users returns ids" in prompt
    assert "It came back from its executor" not in prompt
    with Store.open(repo) as store:
        [note] = B.items(store)
        assert (note["id"], note["kind"], note["about"], note["by"], note["state"]) == (
            "why-ids", "note", "ids", "planner:talker.py", "open"
        )  # fmt: skip
        assert B.decided(store, P.get(store, "ids")) == []  # the planner's words bind nobody until taken
    board = person("board").stdout  # in the store, visible later, and whole
    assert (
        "why-ids" in board
        and "ids is there so the API returns ids before" in board
        and "\n    them" in board  # wrapped whole under its row, at the terminal's 80 columns
    )
    again = person("talk", "why", "ids", "--with", talker)  # a second answer is a second note, not refused
    assert again.exit_code == 0 and "why-ids-2" in again.stdout
    # and dismissable; once dropped, the same words are not put up again (the board's rule for drops)
    assert person("board", "drop", "why-ids").exit_code == 0
    assert runner.invoke(build(), ["talk", "why", "ids", "--with", talker], env=AGENT_ENV).exit_code == 1


def test_merge_proposes_one_leaf_and_the_board_asks_taking_it_drops_them_as_one_act(repo, talker, tmp_path):
    accepted(repo)
    said = person("talk", "merge", "ids", "docs", "--with", talker)
    assert said.exit_code == 0, said.output
    assert "proposed both: users return ids, documented" in said.stdout
    assert said.stdout.splitlines()[-1] == "the board asks (merge-ids-docs): merge ids and docs into both?"
    [prompt] = prompts(tmp_path)
    assert (
        "Propose one leaf that does all of ids, docs" in prompt and "docs (revision 1): document it" in prompt
    )
    with Store.open(repo) as store:
        [q] = B.items(store)
        assert q["then"] == [
            "drop docs",
            "drop ids",
        ]  # docs needs ids: it goes first, or that drop is refused
        assert q["options"] == [{"text": "keep them apart", "then": ["drop both"]}]
        assert (q["about"], q["by"], P.get(store, "both").state) == ("both", "planner:talker.py", P.PROPOSED)
        before = [P.to_dict(n) for n in P.nodes(store)]
    taken = person("board", "take", "merge-ids-docs")
    assert taken.exit_code == 0, taken.output
    assert (states(repo)["ids"], states(repo)["docs"], states(repo)["both"]) == (
        "dropped",
        "dropped",
        "proposed",
    )
    undone = person("plan", "undo")
    assert undone.exit_code == 0 and undone.stdout == "undid: board take merge-ids-docs\n"
    with Store.open(repo) as store:  # one act: both back, and the question open again
        assert [{**n, "rev": 0} for n in before] == [{**P.to_dict(n), "rev": 0} for n in P.nodes(store)]
        assert B.get(store, "merge-ids-docs")["state"] == "open"
    assert person("board", "pick", "merge-ids-docs", "1").exit_code == 0  # keep them apart
    assert (states(repo)["ids"], states(repo)["both"]) == ("open", "dropped")


def test_merge_is_refused_before_the_planner_is_asked(repo, talker, tmp_path):
    accepted(repo)
    for args, said in (
        (["ids"], "merge takes two leaves or more"),
        (["api", "schema"], "api has leaves under it: merge takes leaves"),
        (["ids", "nobody"], "no node nobody"),
    ):
        refused = person("talk", "merge", *args, "--with", talker)
        assert refused.exit_code == 1 and said in refused.stderr, refused.output
    with Store.open(repo) as store:
        P.start(store, "ids", P.Caller("run:claude", False, "s"), repo)
    refused = person("talk", "merge", "ids", "docs", "--with", talker)
    assert refused.exit_code == 1 and "ids is running: merge is for work still to do" in refused.stderr
    assert not (tmp_path / "seen.jsonl").exists()  # nothing was spent


def test_another_way_is_proposed_beside_it_and_the_board_asks_which(repo, talker, tmp_path):
    accepted(repo)
    said = person("talk", "another", "schema", "--with", talker)
    assert said.exit_code == 0, said.output
    [prompt] = prompts(tmp_path)
    assert "Propose another way to reach what schema is for: at the left edge, write one new leaf" in prompt
    with Store.open(repo) as store:
        [q] = B.items(store)
        assert q["text"] == "which way for schema: as planned, or migration?"
        assert (q["default"], q["then"]) == ("schema as planned", ["drop migration"])
        assert q["options"] == [{"text": "migration: the schema as a migration", "then": ["drop schema"]}]
    assert person("board", "pick", q["id"], "1").exit_code == 0  # the other way: the planned one goes
    assert (states(repo)["schema"], states(repo)["migration"]) == ("dropped", "proposed")


@pytest.mark.parametrize("was, now", [
    ("scope: migrations/**", "scope: schema.py, migrations/**"),
    ("check: test -d migrations", "check: grep -q ids schema.py"),  # it does not wait on the leaf
])  # fmt: skip
def test_another_way_may_write_what_the_leaf_it_would_replace_writes(repo, talker, tmp_path, was, now):
    """Its scope may take in the leaf's, as a merge's takes in theirs, and its check may run the leaf's
    file: the answer drops one of them."""
    accepted(repo)
    (tmp_path / "talker.py").write_text(TALKER.replace(was, now))
    said = person("talk", "another", "schema", "--with", talker)
    assert said.exit_code == 0, said.output
    with Store.open(repo) as store:
        [q] = B.items(store)
    assert person("board", "pick", q["id"], "1").exit_code == 0  # the other way: the planned one goes
    assert (states(repo)["schema"], states(repo)["migration"]) == ("dropped", "proposed")


def test_nemotron_answers_why_and_its_note_lands_as_its_own(repo, monkeypatch):
    accepted(repo)
    note = "```plan\nnote: ids is the leaf the docs wait on  [why-ids]\n    about: ids\n```"
    with Fake([{"content": note}] * 2) as f:  # its draft, then its answer
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        with Store.open(repo) as store:
            [said] = talk.why(store, repo, "ids", named("nemotron"), say=lambda _: None)
            assert (said["by"], said["about"], said["text"]) == (
                "planner:nemotron", "ids", "ids is the leaf the docs wait on"
            )  # fmt: skip
    assert "Say why ids is in the plan" in f.requests[0]["messages"][1]["content"]


def test_changes_since_seen_are_others_and_only_after_the_mark(repo, talker):
    accepted(repo)
    assert person("plan", "changes").stdout.startswith("no mark yet: `graphene plan seen`")
    with Store.open(repo) as store:  # no mark: nothing reads as changed, and the screen is as it was
        assert talk.marks(store, "alex") == ({}, 0)
    person("talk", "another", "schema", "--with", talker)  # before the mark: never listed
    assert (
        person("plan", "seen").stdout == "0 changes marked as seen; what anyone else changes next is marked\n"
    )
    assert person("plan", "changes").stdout == "nothing changed since you last looked\n"
    person("node", "add", "mine", "--scope", "x.py", "--check", "true")  # the person's own act: seen as made
    assert person("plan", "changes").stdout == "nothing changed since you last looked\n"
    person("talk", "merge", "ids", "docs", "--with", talker)  # the planner revises
    said = person("plan", "changes").stdout.splitlines()
    assert said[0] == "2 changed since you last looked (graphene plan seen marks them seen):"
    assert re.fullmatch(
        r"  \d\d:\d\d  both: proposed by planner:talker.py: users return ids, documented", said[1]
    )
    assert said[2].endswith("both: the board by planner:talker.py: put up merge-ids-docs: merge ids and docs "
                            "into both?")  # fmt: skip
    with Store.open(repo) as store:
        assert talk.marks(store, "alex") == ({"both": "+"}, 2)
    refused = agent("plan", "seen")  # an agent moving the mark would hide a change from the person
    assert refused.exit_code == 1 and "the mark is the person's" in refused.stderr
    assert person("plan", "seen").stdout.startswith("2 changes marked as seen")
    assert person("plan", "changes").stdout == "nothing changed since you last looked\n"


@pytest.mark.parametrize(
    "how, leaf",
    [(["node", "set", "a", "--check", "python3 -m pytest tests/test_b.py"], "a"), (["plan", "edit"], "a"),
     (["node", "set", "b", "--add-scope", "tests/test_c.py"], "a"),
     (["node", "add", "c", "--id", "c", "--scope", "c.py", "--check", "pytest tests/test_b.py"], "c")],
)  # fmt: skip
def test_a_need_graphene_adds_to_a_leaf_is_a_change_since_the_mark(repo, monkeypatch, tmp_path, how, leaf):
    """The loop directive, lane 5: the need was logged as the person's own edit, so neither `plan changes`
    nor the screen's ~ showed it. The command that made it says it, as before. A leaf `node add` makes is
    judged as `plan edit` judges a new line (review of lane 5)."""
    person("node", "add", "a", "--id", "a", "--scope", "a.py", "--check", "python3 -m pytest tests/test_c.py")
    person("node", "add", "b", "--id", "b", "--scope", "b.py", "--scope", "tests/test_b.py",
           "--check", "true")  # fmt: skip
    person("plan", "seen")
    editor(monkeypatch, tmp_path, "text = text.replace('tests/test_c.py', 'tests/test_b.py')")  # plan edit's
    said = person(*how)
    assert said.exit_code == 0 and f"{leaf} waits on b: its check runs tests/" in said.stdout, said.output
    changes = person("plan", "changes").stdout.splitlines()
    assert changes[0] == "1 changed since you last looked (graphene plan seen marks them seen):"
    assert changes[1].endswith(f"  {leaf}: edited needs by graphene"), changes
    with Store.open(repo) as store:
        assert talk.marks(store, "alex") == ({leaf: "~"}, 1) and P.get(store, leaf).needs == ["b"]


# -- the screen -----------------------------------------------------------------------------------


def revised(repo):
    """A plan the person has seen, and a planner's revision after it: a leaf under api."""
    accepted(repo)
    person("plan", "seen")
    paging = "- the API  [api]\n  ? paging  [paging]\n      scope: pages.py\n      check: true\n"
    said = agent("plan", "propose", "-", input=paging)
    assert said.exit_code == 0, said.output


@pytest.mark.parametrize("size", SIZES)
def test_a_row_changed_since_the_person_looked_is_marked_until_m(repo, size):
    revised(repo)
    seen, _ = watch(repo, [], size)
    rows = [r for r in seen["tree"] if r.strip()]
    [paging] = [r for r in rows if "paging" in r]
    [schema] = [r for r in rows if "schema" in r]
    assert " +paging" in paging and "+" not in schema
    assert paging.rindex("paging") == schema.rindex("schema")  # the id column, where it always is
    assert sum("+" in r or "~" in r for r in rows) == 1
    top = seen["status"].splitlines()[0]
    assert top.startswith("1 changed since you last looked · graphene plan changes · m seen · 1 on you")
    assert len(top) <= size[0] - 2
    folded, _ = watch(repo, ["j", "z", "c"], size)  # api folded: the change inside it is not hidden
    [api] = [r for r in folded["tree"] if " api " in r or "~api" in r]
    assert "~api" in api
    after, _ = watch(repo, ["m"], size)
    assert "graphene plan seen: 1 change marked as seen" in after["status"]
    assert not any("+paging" in r for r in after["tree"]) and "changed since" not in after["status"]


@pytest.mark.parametrize("size", SIZES)
def test_question_mark_on_a_node_opens_the_chooser_and_each_choice_runs_its_command(repo, size, monkeypatch):
    accepted(repo)
    started = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: started.append(argv))
    goal, _ = watch(repo, [], size)
    assert "? help" in goal["status"]  # on the goal ? is the help, as it was
    seen, _ = watch(repo, ["question_mark"], size)
    assert seen["screen"] == "Help"
    seen, _ = watch(repo, ["j", "j"], size)
    assert "? talk" in seen["status"] and "? help" not in seen["status"]
    seen, _ = watch(repo, ["j", "j", "question_mark"], size)
    assert seen["screen"] == "Ask"
    for typed, argv in (
        (["w"], ["talk", "why", "ids"]),
        (list("why"), ["talk", "why", "ids"]),
        (["a"], ["talk", "another", "ids"]),
        (["s"], ["node", "split", "ids"]),
        (list("make it faster"), ["ask", "make it faster", "--about", "ids"]),
    ):
        started.clear()
        watch(repo, ["j", "j", "question_mark", *typed, "enter"], size)
        assert started == [argv], (typed, started)
    started.clear()
    seen, _ = watch(repo, ["j", "j", "V", "j", "question_mark", "m", "enter"], size)  # the selection, merged
    assert started == [["talk", "merge", "ids", "docs"]] and "VISUAL" not in seen["status"]
    started.clear()
    seen, _ = watch(repo, ["j", "j", "question_mark", "question_mark", "enter"], size)
    assert seen["screen"] == "Help" and started == []
    seen, _ = watch(repo, ["j", "j", "question_mark", "w", "escape"], size)
    assert seen["screen"] == "Screen" and started == []


def test_the_chooser_says_its_choices_at_80_columns(repo):
    accepted(repo)

    async def before(app, pilot):
        await pilot.press("j", "j", "question_mark")
        await pilot.pause()
        line = "\n".join(shown(app, app.screen.query_one("#ask").region))
        assert "ids: w why · s split · m merge · a another way · ? help · or your words" in line, line

    watch(repo, [], (80, 24), before=before)


def test_the_chooser_on_a_selection_names_it_and_every_choice_whole_at_80_columns(repo):
    """Walks 2026-09-28 (alex 7, first 6, judge 9): with a longer id, or several, the line was cut at
    80 columns (`… a another way · ? help · or your`). What it is about goes on its border then."""
    accepted(repo)

    async def before(app, pilot):
        await pilot.press("j", "j", "V", "j", "question_mark")
        await pilot.pause()
        line = "\n".join(shown(app, app.screen.query_one("#ask").region))
        assert "w why · s split · m merge · a another way · ? help · or your words" in line, line
        assert "ids, docs" in line, line

    watch(repo, [], (80, 24), before=before)


def test_why_from_the_screen_puts_the_note_on_the_board_and_says_so(repo, talker, tmp_path, monkeypatch):
    accepted(repo)
    with Store.open(repo) as store:
        store.set_meta("planner", talker)
    gate = tmp_path / "gate"
    monkeypatch.setenv("GATE", str(gate))  # the planner answers only once "started" has been read: on a fast
    # runner it used to finish first, and "ended" had replaced "started" before the test looked

    async def before(app, pilot):
        await pilot.press("j", "j", "question_mark", "w", "enter")
        await pilot.pause()
        assert "graphene talk why ids: started" in str(app.query_one("#status").render())
        gate.touch()
        await asyncio.to_thread(app.runs[0].wait, 60)
        await pilot.pause(0.3)

    seen, _ = watch(repo, [], before=before)
    assert "graphene talk why ids ended: the planner on ids: ids is there so the API" in seen["status"]
    assert "put up why-ids on the board" in seen["detail"]
    with Store.open(repo) as store:
        assert B.get(store, "why-ids")["about"] == "ids"


def test_the_replay_refuses_m(tmp_path, monkeypatch):
    from graphene_map import demo

    head, lines = demo.load(demo.SHIPPED)
    repo = demo.repository(tmp_path, head)
    app = demo.Replay(repo, head, lines)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("m")
            await pilot.pause()
            return str(app.query_one("#status").render()).splitlines()[-1]

    assert asyncio.run(go()) == demo.REFUSED
    with Store.open(repo) as store:
        assert store.meta("seen:alex") is None and store.meta(f"seen:{P.person_name()}") is None
