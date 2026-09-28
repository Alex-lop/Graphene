# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""Talking on the tree: the person asks the planner about the node under the cursor (why it is there,
split it, merge these, another way), every answer lands in the store (the plan or the board), and what
anyone else changed since the person last looked is marked until they say they have seen it. The planner
is a script that prints what a model would (as in tests/test_ask.py), and Nemotron is the scripted fake
(tests/fake_tokenfactory.py). The screen is driven by keys at 80x24 and 120x36."""

import json
import sys

import pytest
from fake_tokenfactory import Fake
from test_plan_cli import AGENT_ENV, agent, person, repo, runner  # noqa: F401  (fixtures)
from test_tui import proposed, states

from graphene_map import board as B
from graphene_map import plan as P
from graphene_map import talk
from graphene_map import tokenfactory as tf
from graphene_map.ask import named
from graphene_map.cli import build
from graphene_map.store import Store

# one script for every kind: it answers what the prompt asks, as a model would
TALKER = r"""
import json, os, re, sys
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
            "why-ids", "note", "ids", "planner:python", "open"
        )  # fmt: skip
        assert B.decided(store, P.get(store, "ids")) == []  # the planner's words bind nobody until taken
    board = person("board").stdout  # in the store, visible later, and whole
    assert (
        "why-ids" in board
        and "\n      ids is there so the API returns ids before the docs describe them" in board
    )
    assert person("board", "drop", "why-ids").exit_code == 0  # and dismissable
    again = person("talk", "why", "ids", "--with", talker)  # a second answer is a second note, not refused
    assert again.exit_code == 0 and "why-ids-2" in again.stdout
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
        assert (q["about"], q["by"], P.get(store, "both").state) == ("both", "planner:python", P.PROPOSED)
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


def test_nemotron_answers_why_and_its_note_lands_as_its_own(repo, monkeypatch):
    accepted(repo)
    note = "```plan\nnote: ids is the leaf the docs wait on  [why-ids]\n    about: ids\n```"
    with Fake([{"content": note}]) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        with Store.open(repo) as store:
            [said] = talk.why(store, repo, "ids", named("nemotron"), say=lambda _: None)
            assert (said["by"], said["about"], said["text"]) == (
                "planner:nemotron", "ids", "ids is the leaf the docs wait on"
            )  # fmt: skip
    assert "Say why ids is in the plan" in f.requests[0]["messages"][1]["content"]
