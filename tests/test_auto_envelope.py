# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The envelope: the settings `auto`, `budget`, `tasks` and `rounds` (rendered, read, written, the person's
alone; `graphene config set` changes one), what fits it (`auto.fits`, a reason each), what taking it does
(`auto.take`: the person's stand-in accepts, `plan undo` takes it back, the log says it in words), and that an
agent's proposal is taken only once the person turned auto on."""

import sys

import pytest
from test_ask import GOOD, planner
from test_plan_cli import AGENT_ENV, agent, person, repo, runner  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map import settings as S
from graphene_map.cli import build
from graphene_map.store import Store

ALEX = P.Caller("alex", True)
BOT = P.Caller("claude:b0t", False, "b0t-session")
TREE = ("- the api  [api]\n  ? users return ids  [ids]\n      scope: api.py\n      check: true\n"
        "  ? the tables  [tables]\n      scope: schema.py\n      check: true\n")  # fmt: skip


def proposed(store, text: str, files) -> list[P.Node]:
    said = T.apply(store, text, BOT, None, files=files)
    return [P.get(store, i) for i in said.ids]


def test_the_envelope_keys_render_read_and_write_as_the_rest_do(repo):
    with Store.open(repo) as store:
        assert (S.auto(store), S.budget(store), S.tasks(store), S.rounds(store)) == ("off", None, None, 2)
        shown = S.render(store)
        assert "auto: off\n" in shown and "budget:" not in shown.split("# rounds")[1]
        assert "# auto: off (every proposal waits for you) or on (one that fits the envelope" in shown
        S.apply(store, "auto: on\nbudget: 2\ntasks: 6\nrounds: 1\n", ALEX)
        assert (S.auto(store), S.budget(store), S.tasks(store), S.rounds(store)) == ("on", 2.0, 6, 1)
        assert "\nauto: on\nbudget: 2.00\ntasks: 6\nrounds: 1\nnotify: on\n" in S.render(store)
        row = store.node_log("*", ("settings",))[-1]
        assert row["detail"]["changed"] == {"auto": ["off", "on"], "budget": [None, "2.00"],
                                            "tasks": [None, "6"], "rounds": [None, "1"]}  # fmt: skip
        assert S.auto_since(store) == row["timestamp"]
        again = S.render(store)
        S.apply(store, again, ALEX)
        assert S.render(store) == again  # round-trips
        S.apply(store, "size: auto\n", ALEX)  # left out, each is cleared, as every setting is
        assert (S.auto(store), S.budget(store), S.tasks(store), S.rounds(store)) == ("off", None, None, 2)
        assert S.auto_since(store) is None


@pytest.mark.parametrize("bad, words", [
    ("budget: two", "budget is dollars, such as 2 or 0.50, not 'two'"), ("tasks: 1.5", "tasks is a count"),
    ("rounds: -1", "rounds is a count, not '-1'"), ("auto: yes", "auto is off or on, not 'yes'"),
    ("budget: 1\nbudget: 2", "budget is said on line 2 already"),
])  # fmt: skip
def test_a_bad_envelope_line_is_refused_by_its_number_and_nothing_is_written(repo, bad, words):
    with Store.open(repo) as store:
        before = S.render(store)
        with pytest.raises(P.Refused) as got:
            S.apply(store, f"size: auto\n{bad}\n", ALEX)
        assert str(got.value).startswith("line ") and words in str(got.value)
        assert S.render(store) == before


def test_config_set_changes_one_setting_keeps_the_rest_and_is_the_persons(repo):
    assert person("config", "set", "auto", "on").stdout == "added: auto: on\nremoved: auto: off\n"
    assert person("config", "set", "budget", "2").stdout == "added: budget: 2.00\n"
    assert person("config", "set", "protected", "vendor/**").stdout == "added: protected: vendor/**\n"
    with Store.open(repo) as store:
        assert (S.auto(store), S.budget(store), S.protected(store)) == ("on", 2.0, ["vendor/**"])
        assert len(store.node_log("*", ("settings",))) == 3  # one row a change, as `config edit` logs it
    assert person("config", "set", "budget", "").stdout == "removed: budget: 2.00\n"
    assert person("config", "set", "auto", "on").stdout == "nothing changed\n"
    bad = person("config", "set", "colour", "blue")
    assert bad.exit_code == 1 and "'colour: blue' is not a setting" in bad.output
    no = agent("config", "set", "auto", "on")
    assert no.exit_code == 1 and "changing Graphene's settings is the person's to do" in no.output
    with Store.open(repo) as store:
        assert S.auto(store) == "on" and S.budget(store) is None and S.protected(store) == ["vendor/**"]


def test_fits_names_each_reason_a_proposal_waits(repo):
    files = P.tracked(repo)
    with Store.open(repo) as store:
        added = proposed(store, TREE, files)
        assert AUTO.fits(store, added, files) == [
            "auto is off (`graphene config set auto on`, or `graphene auto`, turns it on)"]  # fmt: skip
        S.apply(store, "auto: on\ntasks: 1\n", ALEX)
        assert AUTO.fits(store, added, files) == ["your envelope accepts 1 tasks and this makes 2"]
        S.apply(store, "auto: on\n", ALEX)
        assert AUTO.fits(store, added, files) == []
        docs = proposed(store, "? the docs  [docs]\n    scope: README.md\n    signoff: yes\n", files)
        assert AUTO.fits(store, docs, files) == ["docs has no check"]  # a sign-off alone is the person's
        board = "question: which database?  [db]\n    about: ids\n" + TREE.replace("[ids]", "[ids2]")
        board = board.replace("[tables]", "[tables2]").replace("[api]", "[api2]")
        board = board.replace("api.py", "x.py").replace("schema.py", "y.py")  # one writer a path
        more = proposed(store, board, files)
        assert AUTO.fits(store, more, files) == ["db on the board needs your answer: it has no default"]
        drops = "risk: the tables may be wrong  [tbl]\n    default: drop them\n    then: drop tables\n"
        proposed(store, drops, files)
        why = AUTO.fits(store, added, files)
        assert "tbl on the board needs your answer: its default drops tables" in why


def test_take_accepts_as_the_persons_stand_in_says_the_width_and_undo_takes_it_back(repo):
    files = P.tracked(repo)
    with Store.open(repo) as store:
        added = proposed(store, TREE, files)
        assert AUTO.take(store, added, files, repo) is None  # auto off: it waits as any proposal does
        S.apply(store, "auto: on\nbudget: 2\n", ALEX)
        said = AUTO.take(store, added, files, repo)
        assert said.startswith("accepted inside your envelope (auto on since ")
        tail = " · $2.00 · 12 tasks): ids, tables. `graphene run` runs them; 2 tasks can run at once"
        assert said.endswith(tail), said
        assert {n.id: n.state for n in P.nodes(store)} == {"api": P.OPEN, "ids": P.OPEN, "tables": P.OPEN}
        rows = store.node_log(None, ("accepted",))
        assert {r["node_id"] for r in rows} == {"api", "ids", "tables"}
        assert all(r["actor"] == "alex (no terminal)" and r["detail"] == {"by": "auto"} for r in rows)
        assert AUTO.accepted(store, S.auto_since(store)) == 2  # tasks, not the sub-goal
        assert P.undo(store, ALEX) == "accepted inside your envelope: api"
        assert {n.state for n in P.nodes(store)} == {P.PROPOSED}
        said = AUTO.take(store, added, files, repo)  # taken again: inside a round, the row says which
        store.log_node("*", P._now(), AUTO.KIND, AUTO.ACTOR, None, None, {"round": 2, "stage": "fixing"})
        two = proposed(store, "? two  [two]\n    scope: README.md\n    check: true\n", files)
        three = AUTO.take(store, two, files, repo)
        assert three.endswith("two. `graphene run` runs them; 3 tasks can run at once"), three
        assert store.node_log("two", ("accepted",))[-1]["detail"] == {"by": "auto", "round": 2}
    log = person("plan", "log").stdout
    assert "accepted by your envelope\n" in log + "\n" or "accepted by your envelope " in log
    assert "accepted by your envelope, round 2" in log and "by their prompt" not in log


def test_an_agents_proposal_is_taken_only_once_the_person_turned_auto_on(repo):
    said = agent("plan", "propose", "-", input=TREE)
    assert said.exit_code == 0 and "3 proposed: nobody can start them until the person accepts" in said.stdout
    assert person("config", "set", "auto", "on").exit_code == 0
    more = TREE.replace("[api]", "[api2]").replace("[ids]", "[ids2]").replace("[tables]", "[tables2]")
    more = more.replace("api.py", "README.md").replace("schema.py", "docs.md")
    said = agent("plan", "propose", "-", input=more)
    assert said.exit_code == 0, said.output
    assert "accepted inside your envelope (auto on since " in said.stdout
    assert "nobody can start" not in said.stdout
    assert "): ids2, tables2. `graphene run` runs them" in said.stdout
    with Store.open(repo) as store:
        assert P.get(store, "ids2").state == P.OPEN
        assert P.get(store, "ids").state == P.PROPOSED  # what waited before auto went on still waits
        assert store.node_log("ids2", ("accepted",))[-1]["detail"] == {"by": "auto"}
    out = agent("plan", "propose", "-", input="? docs  [docs]\n    scope: CHANGES.md\n    signoff: yes\n")
    waits = "1 proposed: it waits for you: docs has no check. nobody can start it until the person accepts"
    assert waits in out.stdout
    # nothing an agent sends changes the envelope: not a config command, not a line in a proposal
    assert agent("config", "set", "tasks", "99").exit_code == 1
    text = "tasks: 99\n- x  [x]\n    scope: a.py\n    check: true\n"
    assert agent("plan", "propose", "-", input=text).exit_code == 1
    with Store.open(repo) as store:
        assert S.tasks(store) is None


def test_graphene_ask_takes_what_fits_and_says_run_not_accept(repo, tmp_path, monkeypatch):
    assert person("config", "set", "auto", "on").exit_code == 0
    script = planner(tmp_path, GOOD, monkeypatch)
    said = person("ask", "users should come back with their ids", "--with", script)
    assert said.exit_code == 0, said.output
    assert "accepted inside your envelope (auto on since " in said.stdout
    assert "): ids. `graphene run` runs them; 1 task can run at once" in said.stdout
    assert "next: `graphene plan accept`" not in said.stdout
    with Store.open(repo) as store:
        assert P.get(store, "ids").state == P.OPEN
        assert P.goal(store) == "users come back with their ids"  # the planner's sentence, as at an accept


def test_the_width_counts_what_can_run_at_once(repo):
    files = P.tracked(repo)
    with Store.open(repo) as store:
        P.propose(store, [{"id": "a", "title": "a", "scope": ["api.py"], "check": "true"},
                          {"id": "b", "title": "b", "scope": ["schema.py"], "check": "true"},
                          {"id": "d", "title": "d", "scope": ["x.py"], "check": "true", "needs": ["a"]}],
                  ALEX, files=files)  # fmt: skip
        assert AUTO.width(P.nodes(store), files) == 2  # a and b; d waits on a
        c = P.Node("c", "c", scope=["api.py", "README.md"], check="true", state=P.OPEN)  # never proposed: a
        assert AUTO.width([*P.nodes(store), c], files) == 2  # path has one writer; here it meets a's


def test_the_help_names_the_command_and_the_executor_scripts_are_what_the_tests_use():
    said = runner.invoke(build(), ["auto", "--help"])
    assert said.exit_code == 0
    options = ("--budget", "--tasks", "--rounds", "--forks", "--parallel", "--check", "--planner", "--with",
               "--attempts")  # fmt: skip
    for option in options:
        assert option in said.output, option
    assert sys.executable  # the scripted planner and executors run on this interpreter (test_auto_run)
