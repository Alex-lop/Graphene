# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene ask --finer/--coarser` (+ and - on the screens) asks the last sentence again: with the
planner that ask started, and without losing what the person answered about the tree it replaces."""

import json
import sys

from test_ask import GOOD, planner
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import ask as A
from graphene_map import board as B
from graphene_map.plan import Caller
from graphene_map.store import Store

ME = Caller("person:alex", True, None)

ASKED = GOOD.replace(
    'print("```")\n',
    'print("question: ids as numbers or strings?  [id-type]")\n'
    'print("    default: numbers")\n'
    'print("    then: goal ids + \\"ids stay numbers\\"")\n'
    'print("    about: ids")\n'
    'print("```")\n',
    1,
)
FINER = GOOD.replace("[users-api]", "[users-api2]").replace("[ids]", "[ids2]")


def prompts(tmp_path) -> list[str]:
    return [json.loads(line)["prompt"] for line in (tmp_path / "seen.jsonl").read_text().splitlines()]


def test_a_reask_starts_the_planner_the_ask_named_not_the_repos(repo, tmp_path, monkeypatch):
    mine = planner(tmp_path, GOOD, monkeypatch)
    assert person("ask", "add ids", "--with", mine).exit_code == 0
    with Store.open(repo) as store:
        store.set_meta("planner", "no-such-planner")  # the repo's planner changes after the ask
        argv = A.reask_argv(store, "finer")
    assert argv == ["graphene", "ask", "add ids", "--with", mine, "--finer"]
    again = person(*argv[1:])
    assert again.exit_code == 0, again.output
    assert len(prompts(tmp_path)) == 2  # the script ran again; no-such-planner never started


def test_an_ask_without_with_keeps_the_planner_it_started(repo, tmp_path, monkeypatch):
    with Store.open(repo) as store:
        store.set_meta("planner", planner(tmp_path, GOOD, monkeypatch))
    assert person("ask", "add ids").exit_code == 0
    with Store.open(repo) as store:
        first = store.meta("planner")
        store.set_meta("planner", "codex")
        assert A.reask_argv(store, "coarser") == ["graphene", "ask", "add ids", "--with", first, "--coarser"]


def test_an_answer_about_a_dropped_node_is_told_to_every_executor_after_a_reask(repo, tmp_path, monkeypatch):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED, monkeypatch)).exit_code == 0
    with Store.open(repo) as store:
        B.take(store, "id-type", ME)
        assert "ids stay numbers" in A.P.get(store, "ids").goal
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "id-type was about ids, which is dropped: it is about the whole plan now" in again.output
    assert "ids is dropped, and with it its goal + ids stay numbers (from id-type)" in again.output
    with Store.open(repo) as store:
        assert B.get(store, "id-type")["about"] is None
        told = B.decided(store, A.P.get(store, "ids2"))
    assert told == ["ids as numbers or strings? → numbers"]  # the new leaf's executor is told it
    prompt = prompts(tmp_path)[-1]
    stands = prompt.index("These answers of the person's stand")
    kept = '- ids as numbers or strings? → numbers (it added to the goal of ids: "ids stay numbers")'
    assert prompt.index(kept) > stands


FAILS = 'import sys\nprint("sorry, cannot plan now")\nsys.exit(1)\n'


def states(repo) -> dict:
    with Store.open(repo) as store:
        return {n.id: n.state for n in A.P.nodes(store)}


def test_a_reask_whose_planner_fails_keeps_the_tree_it_would_have_replaced(repo, tmp_path, monkeypatch):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED, monkeypatch)).exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FAILS, monkeypatch))
    assert again.exit_code == 1 and "nothing was added" in again.output
    assert states(repo) == {"users-api": "proposed", "ids": "proposed"}  # not dropped before the planner ran
    with Store.open(repo) as store:
        assert B.get(store, "id-type")["about"] == "ids"


def test_a_reask_whose_proposal_is_refused_keeps_the_tree_and_the_answers(repo, tmp_path, monkeypatch):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED, monkeypatch)).exit_code == 0
    with Store.open(repo) as store:
        B.take(store, "id-type", ME)
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, ASKED, monkeypatch))
    assert again.exit_code == 1 and "is on the board already" in again.output
    assert "which is dropped" not in again.output  # nothing was dropped, so nothing says it was
    assert states(repo) == {"users-api": "proposed", "ids": "proposed"}
    with Store.open(repo) as store:
        assert B.get(store, "id-type")["about"] == "ids"


def test_a_reask_drops_only_the_last_asks_proposals_not_a_split_or_another_way(repo, tmp_path, monkeypatch):
    from test_talk import TALKER

    assert person("ask", "add ids", "--with", planner(tmp_path, GOOD, monkeypatch)).exit_code == 0
    assert person("plan", "accept").exit_code == 0
    other = tmp_path / "talker.py"
    other.write_text(TALKER)
    assert person("talk", "another", "ids", "--with", f"{sys.executable} {other}").exit_code == 0
    assert states(repo)["migration"] == "proposed"
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert states(repo)["migration"] == "proposed"  # another way's leaf is not the last ask's tree
    assert "This replaces the tree you proposed last" not in prompts(tmp_path)[-1]  # its tree was accepted


def test_a_reask_after_a_failed_one_still_replaces_the_tree(repo, tmp_path, monkeypatch):
    assert person("ask", "add ids", "--with", planner(tmp_path, GOOD, monkeypatch)).exit_code == 0
    assert person("ask", "add ids", "--finer", "--with", planner(tmp_path, FAILS, monkeypatch)).exit_code == 1
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert states(repo) == {
        "users-api": "dropped",
        "ids": "dropped",
        "users-api2": "proposed",
        "ids2": "proposed",
    }


ASKED_OPEN = ASKED.replace('print("    then: goal ids + \\"ids stay numbers\\"")\n', "")


def test_an_item_still_open_about_a_dropped_node_is_told_to_every_executor_once_answered(
    repo, tmp_path, monkeypatch
):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_OPEN, monkeypatch)).exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "id-type was about ids, which is dropped: it is about the whole plan now" in again.output
    assert person("board", "take", "id-type").exit_code == 0
    with Store.open(repo) as store:
        assert B.decided(store, A.P.get(store, "ids2")) == ["ids as numbers or strings? → numbers"]


ASKED_SCOPE = ASKED.replace(
    'print("    then: goal ids + \\"ids stay numbers\\"")\n',
    'print("    option: strings")\n'
    'print("    then: scope ids + schema.py")\n'
    'print("    then: check ids: grep -q str schema.py")\n',
)


def test_a_reask_says_the_scope_and_check_an_answer_gave_a_dropped_leaf(repo, tmp_path, monkeypatch):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_SCOPE, monkeypatch)).exit_code == 0
    assert person("board", "pick", "id-type", "1").exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "ids is dropped, and with it its scope + schema.py (from id-type)" in again.output
    assert "ids is dropped, and with it its check is now grep -q str schema.py (from id-type)" in again.output
    prompt = prompts(tmp_path)[-1]
    assert "- ids as numbers or strings? → strings (it changed ids: scope + schema.py)" in prompt
    assert (
        "- ids as numbers or strings? → strings (it changed ids: check is now grep -q str schema.py)"
        in prompt
    )
