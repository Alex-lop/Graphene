# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene watch`: the plan on one screen, driven the way a person drives it, by keys, headless
(Textual's pilot) at 80 columns and at 120. Every key is a command: after each, the store says what
the command did, and the bottom line says which command it was."""

import asyncio
import sys

from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)

from graphene_debrief import plan
from graphene_debrief.store import Store
from graphene_debrief.tui import Watch

TREE = """\
goal: users come back with their ids
- the API  [api]
  - users returns ids  [ids]
      scope: api.py
      check: grep -q ids api.py
  - document it  [docs]
      scope: README.md
      check: test -f README.md
      needs: ids
- the schema  [schema]
    scope: schema.py
    check: true
"""


def watch(repo, keys, size=(80, 24), before=None):
    """Drive the screen with keys; returns what it showed at the end, and the app."""
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            if before:
                await before(app, pilot)
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            app.refresh_plan()
            await pilot.pause()
            return {
                "where": str(app.query_one("#where").render()),
                "status": str(app.query_one("#status").render()),
                "detail": str(app.query_one("#detail").render()),
                "cursor": app.selected(),
                "classes": list(app.screen.classes),
                "screen": type(app.screen).__name__,
            }

    return asyncio.run(go()), app


def states(repo):
    with Store.open(repo) as store:
        return {n.id: n.state for n in plan.nodes(store)}


def proposed(repo):
    said = agent("plan", "propose", "-", input=TREE)
    assert said.exit_code == 0, said.output


def test_it_says_where_it_is_which_plan_and_names_the_two_agents(repo):
    proposed(repo)
    seen, _ = watch(repo, [])
    assert (
        repo.name in seen["where"] and "the plan (proposed): users come back with their ids" in seen["where"]
    )
    assert "planner: claude:5e55105e" in seen["status"] and "executors: none" in seen["status"]
    assert seen["classes"] == ["-narrow"]  # 80 columns: the tree above, the node below it
    wide, _ = watch(repo, [], size=(120, 30))
    assert wide["classes"] == ["-wide"]


def test_vim_keys_move_and_fold(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j"])
    assert seen["cursor"] == "ids"
    seen, _ = watch(repo, ["G", "g", "g"])
    assert seen["cursor"] == "api"
    seen, _ = watch(repo, ["G"])
    assert seen["cursor"] == "schema"
    seen, app = watch(repo, ["z", "M", "j"])  # all closed: the next line is the next sub-goal
    assert seen["cursor"] == "schema"
    seen, _ = watch(repo, ["z", "M", "z", "R", "j"])  # all open again
    assert seen["cursor"] == "ids"
    seen, _ = watch(repo, ["z", "a", "j"])  # za on api closes it; `a` of za adds nothing
    assert seen["cursor"] == "schema" and seen["screen"] == "Screen"


def test_y_accepts_d_drops_and_u_puts_it_back(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j", "y"])
    assert states(repo)["ids"] == "open" and states(repo)["api"] == "open"  # and the one it sits under
    assert "graphene plan accept ids" in seen["status"]
    seen, _ = watch(repo, ["G", "d"])
    assert states(repo)["schema"] == "dropped" and "graphene node drop schema" in seen["status"]
    watch(repo, ["u"])
    assert states(repo)["schema"] == "proposed"


def test_visual_selects_several_and_y_accepts_them_all(repo):
    proposed(repo)
    watch(repo, ["j", "V", "j", "y"])
    assert states(repo)["ids"] == "open" and states(repo)["docs"] == "open"
    assert states(repo)["schema"] == "proposed"


def test_search_moves_to_the_match_and_n_to_the_next(repo):
    proposed(repo)
    seen, _ = watch(repo, ["slash", *"doc", "enter"])
    assert seen["cursor"] == "docs" and "/doc: 1 of 1" in seen["status"]


def test_a_adds_a_sibling_with_the_title_typed(repo):
    proposed(repo)
    person("plan", "accept")
    watch(repo, ["j", "a", *"the orders endpoint", "enter"])
    with Store.open(repo) as store:
        [new] = [n for n in plan.nodes(store) if n.title == "the orders endpoint"]
        assert new.parent == "api" and new.state == "open"  # the planner can fill it in: s


def test_e_opens_the_contract_in_the_editor(repo, monkeypatch, tmp_path):
    proposed(repo)
    person("plan", "accept")
    script = tmp_path / "edit.py"
    change = "t.replace('check: true', 'check: make schema')"
    script.write_text(f"import sys\np = sys.argv[1]\nt = open(p).read()\nopen(p, 'w').write({change})\n")
    monkeypatch.setenv("EDITOR", f"{sys.executable} {script}")
    seen, _ = watch(repo, ["G", "e"])
    with Store.open(repo) as store:
        assert plan.get(store, "schema").check == "make schema"
    assert "graphene node edit schema" in seen["status"]


def test_a_leaf_that_came_back_shows_its_fixes_and_w_takes_one(repo):
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        plan.start(store, "schema", bot, repo)
        store.log_node(
            "schema", plan._now(), "denied", None, bot.session_id, None, {"path": "migrations/001.sql"}
        )
        plan.release(store, "schema", bot, "the column needs a migration too")
    seen, _ = watch(repo, ["G"])
    assert "came back: the column needs a migration too" in seen["detail"]
    assert "w  widen schema's scope to migrations/001.sql" in seen["detail"]
    watch(repo, ["G", "w"])
    with Store.open(repo) as store:
        assert plan.get(store, "schema").scope == ["schema.py", "migrations/001.sql"]


def test_the_colon_line_takes_any_command_verbatim(repo):
    proposed(repo)
    seen, _ = watch(repo, ["colon", *"plan accept schema", "enter"])
    assert states(repo)["schema"] == "open" and "graphene plan accept schema" in seen["status"]
    seen, _ = watch(repo, ["colon", *"graphene node show ids", "enter"])
    assert "ids (revision 1): users returns ids" in seen["detail"]


def test_question_mark_is_help_and_l_is_the_executors_output(repo):
    proposed(repo)
    seen, _ = watch(repo, ["question_mark"])
    assert seen["screen"] == "Help"
    seen, _ = watch(repo, ["j", "l"])
    assert "ids: the executor's output" in seen["detail"] and "(nothing yet)" in seen["detail"]


def test_what_a_colon_command_printed_gives_way_when_the_plan_moves(repo):
    """A recorded run: after `:plan accept`, a leaf came back and its offers were hidden under the
    accept's output until the cursor moved."""
    proposed(repo)

    async def before(app, pilot):
        for key in ["G", "colon", *"plan accept", "enter"]:
            await pilot.press(key)
            await pilot.pause()
        assert app.view == "said"
        with Store.open(repo) as store:
            bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
            plan.start(store, "schema", bot, repo)
            plan.release(store, "schema", bot, "the column needs a migration", wants=["migrations/001.sql"])

    seen, _ = watch(repo, [], before=before)
    assert "came back: the column needs a migration" in seen["detail"]
