# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene ask --finer/--coarser` (+ and - on the screens) asks the last sentence again: with the
planner that ask started, and without losing what the person answered about the tree it replaces."""

import json
import sys

import pytest
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


def test_an_answer_about_a_dropped_node_follows_it_to_the_new_tree_and_the_planner_is_told_it_stands(
    repo, tmp_path, monkeypatch
):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED, monkeypatch)).exit_code == 0
    with Store.open(repo) as store:
        B.take(store, "id-type", ME)
        assert "ids stay numbers" in A.P.get(store, "ids").goal
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "carried: ids2: goal + ids stay numbers (from id-type)" in again.output
    with Store.open(repo) as store:
        assert B.get(store, "id-type")["about"] == "ids2"  # the same leaf, by its title
        assert "ids stay numbers" in A.P.get(store, "ids2").goal
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
    # a planner whose proposal cannot be read: the tree is dropped only once a proposal has landed
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FAILS, monkeypatch))
    assert again.exit_code == 1 and "nothing was added" in again.output
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
    finer = FINER.replace("api.py", "schema.py")  # ids was accepted, and api.py is its path
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, finer, monkeypatch))
    assert again.exit_code == 0, again.output
    assert states(repo)["migration"] == "proposed"  # another way's leaf is not the last ask's tree
    assert "This replaces the tree you proposed last" not in prompts(tmp_path)[-1]  # its tree was accepted


WAITING = """
print("```plan")
print("? users returns ids  [ids]\\n    scope: api.py\\n    check: grep -q ids api.py")
print("? the schema has ids  [schema-ids]\\n    scope: schema.py\\n    check: true\\n    needs: ids")
print("```")
"""


def test_a_reask_drops_the_last_tree_whole_though_its_leaves_wait_on_each_other(repo, tmp_path, monkeypatch):
    """The old tree was dropped a node at a time, and a node that another node of it waited on stayed.
    The new tree, on the same paths, was then refused as a second writer of them."""
    assert person("ask", "add ids", "--with", planner(tmp_path, WAITING, monkeypatch)).exit_code == 0
    finer = WAITING.replace("ids]", "ids2]").replace("needs: ids", "needs: ids2")
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, finer, monkeypatch))
    assert again.exit_code == 0, again.output
    assert states(repo) == {
        "ids": "dropped", "schema-ids": "dropped", "ids2": "proposed", "schema-ids2": "proposed"
    }


def test_a_reask_keeps_what_an_accepted_node_waits_on_and_what_that_waits_on(repo, tmp_path, monkeypatch):
    assert person("ask", "add ids", "--with", planner(tmp_path, WAITING, monkeypatch)).exit_code == 0
    docs = ["--id", "docs", "--scope", "README.md", "--check", "true", "--needs", "schema-ids"]
    assert person("node", "add", "the docs", *docs).exit_code == 0
    finer = WAITING.replace("ids]", "ids2]").replace("needs: ids", "needs: ids2").replace("api.py", "app.py")
    finer = finer.replace("schema.py", "db.py")  # the old leaves stay, and keep their paths
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, finer, monkeypatch))
    assert again.exit_code == 0, again.output
    assert states(repo) == {"ids": "proposed", "schema-ids": "proposed", "docs": "open"} | {
        "ids2": "proposed", "schema-ids2": "proposed"
    }  # the person sees both trees


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


def test_an_item_still_open_about_a_dropped_node_is_about_the_same_leaf_of_the_new_tree(
    repo, tmp_path, monkeypatch
):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_OPEN, monkeypatch)).exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "ids is dropped; ids2 is the same node in the new tree, so id-type is carried to it" in (
        again.output
    )
    assert person("board", "take", "id-type").exit_code == 0
    with Store.open(repo) as store:
        assert B.decided(store, A.P.get(store, "ids2")) == ["ids as numbers or strings? → numbers"]


ASKED_SCOPE = ASKED.replace(
    'print("    then: goal ids + \\"ids stay numbers\\"")\n',
    'print("    option: strings")\n'
    'print("    then: scope ids + schema.py")\n'
    'print("    then: check ids: grep -q str schema.py")\n',
)


def test_a_reask_tells_the_planner_the_scope_and_check_an_answer_gave_and_carries_them(
    repo, tmp_path, monkeypatch
):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_SCOPE, monkeypatch)).exit_code == 0
    assert person("board", "pick", "id-type", "1").exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, FINER, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "carried: ids2: scope + schema.py (from id-type)" in again.output
    assert "carried: ids2: check is now grep -q str schema.py (from id-type)" in again.output
    prompt = prompts(tmp_path)[-1]
    assert "- ids as numbers or strings? → strings (it changed ids: scope + schema.py)" in prompt
    assert (
        "- ids as numbers or strings? → strings (it changed ids: check is now grep -q str schema.py)"
        in prompt
    )


def proposed(repo) -> dict:
    with Store.open(repo) as store:
        return {n.title: n for n in A.P.nodes(store, (A.P.PROPOSED,))}


def test_a_reask_carries_a_board_answer_to_the_leaf_the_planner_proposed_again(repo, tmp_path, monkeypatch):
    """Walks 2026-09-28 (alex 1, judge 1 and 2): a pick widened a leaf, `+` asked again, the planner wrote
    the same leaf with the same [id], Graphene gave it a new id (a dropped id is never reused), and the
    pick's scope and check stayed on the dropped leaf while the board still said it had changed it. The
    answer now follows the leaf: its about, its then: lines and what it changed are on the new id."""
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_SCOPE, monkeypatch)).exit_code == 0
    assert person("board", "pick", "id-type", "1").exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, GOOD, monkeypatch))
    assert again.exit_code == 0, again.output
    leaf = proposed(repo)["users returns ids"]
    assert leaf.id != "ids" and states(repo)["ids"] == "dropped"
    assert leaf.scope == ["api.py", "schema.py"] and leaf.check == "grep -q str schema.py"
    carried = f"ids is dropped; {leaf.id} is the same node in the new tree, so id-type is carried to it"
    assert carried in again.output
    assert f"carried: {leaf.id}: scope + schema.py (from id-type)" in again.output
    assert "went with the old tree" not in again.output and "and with it its" not in again.output
    with Store.open(repo) as store:
        item = B.get(store, "id-type")
        assert item["about"] == leaf.id
        check = "grep -q str schema.py"
        assert item["options"][0]["then"] == [f"scope {leaf.id} + schema.py", f"check {leaf.id}: {check}"]
        assert item["became"] == [f"{leaf.id}: scope + schema.py", f"{leaf.id}: check is now {check}"]
        assert B.decided(store, leaf) == ["ids as numbers or strings? → strings"]


ELSEWHERE = GOOD.replace("users returns ids  [ids]", "the id column is served  [served]").replace(
    '"      scope: api.py"', '"      scope: api.py, schema.py"'
)
TWICE = GOOD.replace(
    'print("  ? users returns ids  [ids]")',
    'print("  ? users returns ids  [ids2]")\nprint("      scope: schema.py")\nprint("      check: true")\n'
    'print("  ? users returns ids  [ids3]")',
)


@pytest.mark.parametrize(
    "other, why",
    [
        (ELSEWHERE, "no node of the new tree is the same one"),
        (TWICE, "ids2 and ids3 in the new tree could each be it"),
    ],
    ids=["no-leaf-is-it", "two-could-be-it"],
)
def test_a_reask_says_what_it_could_not_carry_and_why(repo, tmp_path, monkeypatch, other, why):
    """No leaf of the new tree is the old one by the planner's [id], its title or its scope, or two are:
    nothing is guessed, the answer is about the whole plan, and the person is told the change is not on
    the new tree and how to put it there."""
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_SCOPE, monkeypatch)).exit_code == 0
    assert person("board", "pick", "id-type", "1").exit_code == 0
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, other, monkeypatch))
    assert again.exit_code == 0, again.output
    assert "carried:" not in again.output
    assert f"ids is dropped, and with it its scope + schema.py (from id-type): {why}" in again.output
    assert "`graphene node set LEAF --add-scope schema.py` puts it on one" in again.output
    with Store.open(repo) as store:
        assert B.get(store, "id-type")["about"] is None


ASKED_LEAF = ASKED.replace(
    'then: goal ids + \\"ids stay numbers\\"', 'then: leaf \\"a sample user\\" under ids'
)


def test_a_leaf_an_answer_put_beside_a_dropped_leaf_is_put_beside_the_same_leaf_again(
    repo, tmp_path, monkeypatch
):
    assert person("ask", "add ids", "--with", planner(tmp_path, ASKED_LEAF, monkeypatch)).exit_code == 0
    assert person("board", "take", "id-type").exit_code == 0
    assert "a sample user" in proposed(repo)
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, GOOD, monkeypatch))
    assert again.exit_code == 0, again.output
    now = proposed(repo)
    leaf, sample = now["users returns ids"], now["a sample user"]
    assert sample.parent == leaf.parent == now["the users API"].id  # beside the new leaf, in the new tree
    assert f"carried: proposed {sample.id} beside {leaf.id}, a leaf, under {leaf.parent};" in again.output


def two_asks(first: str, again: str) -> str:
    """A planner that writes ``first``, and ``again`` once it is told it replaces its last tree."""
    return (
        "import sys\n"
        f"again = 'This replaces the tree you proposed last' in sys.argv[-1]\n"
        f"print('```plan')\nprint({again!r} if again else {first!r})\nprint('```')\n"
    )


WHICH = "question: which id: the row id or a new uuid?"
FIRST = (
    f"goal: users come back with their ids\n{WHICH}  [which-id]\n    default: the row id\n"
    "    option: a uuid column, added to schema.py\n    then: scope ids + schema.py\n    about: ids\n"
    "? users returns ids  [ids]\n    scope: api.py\n    check: true\n"
)


def test_a_reask_that_writes_an_answered_question_again_without_its_id_does_not_put_it_up_twice(
    repo, tmp_path, monkeypatch
):
    """Closing review 9: the planner wrote the question the person had picked again, without its [id];
    it went up as a second open item, `plan accept` took its default against the person's pick, and
    the leaf's executor was told both."""
    again = (
        f"goal: users come back with their ids\n{WHICH}\n    default: the row id\n"
        "    option: a uuid column, added to schema.py\n    then: scope ids2 + schema.py\n    about: ids2\n"
        "? users returns ids  [ids2]\n    scope: api.py\n    check: true\n"
        "? users are paged  [paged]\n    scope: pages.py\n    check: true\n"
    )
    script = planner(tmp_path, two_asks(FIRST, again), monkeypatch)
    assert person("ask", "add ids", "--with", script).exit_code == 0
    assert person("board", "pick", "which-id", "1").exit_code == 0
    said = person("ask", "add ids", "--finer", "--with", script)
    assert said.exit_code == 0, said.output
    assert "put up " not in said.output, said.output
    assert person("plan", "accept").exit_code == 0
    with Store.open(repo) as store:
        assert [it["id"] for it in B.items(store) if it["text"].startswith("which id")] == ["which-id"]
        told = B.decided(store, A.P.get(store, "ids2"))
    assert told == ["which id: the row id or a new uuid? → a uuid column, added to schema.py"]


def test_an_answer_whose_change_the_new_leaf_refuses_is_said_and_the_reask_still_lands(
    repo, tmp_path, monkeypatch
):
    """Closing review 10: a pick widened the leaf to schema.py, then a taken risk made schema.py
    read-only; carrying the pick to the re-asked leaf was refused, the refusal was reported as
    "Graphene could not read the proposal", the planner was asked again for a fault it cannot fix,
    and nothing was added."""
    first = FIRST + (
        "risk: schema.py is shared  [shared]\n    default: keep it read-only\n    then: condition schema.py\n"
    )
    again = "goal: users come back with their ids\n? users returns ids\n    scope: api.py\n    check: true\n"
    script = planner(tmp_path, two_asks(first, again), monkeypatch)
    assert person("ask", "add ids", "--with", script).exit_code == 0
    assert person("board", "pick", "which-id", "1").exit_code == 0
    assert person("board", "take", "shared").exit_code == 0
    said = person("ask", "add ids", "--finer", "--with", script)
    assert said.exit_code == 0, said.output
    assert "could not read the proposal" not in said.output and "again…" not in said.output, said.output
    assert "not carried: scope" in said.output and "`graphene node set" in said.output, said.output
    with Store.open(repo) as store:
        [leaf] = [n for n in A.P.nodes(store, (A.P.PROPOSED,)) if n.title == "users returns ids"]
        assert leaf.scope == ["api.py"]
        assert B.get(store, "which-id")["about"] == leaf.id  # the answer is still told to it
