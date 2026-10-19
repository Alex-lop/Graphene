# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`i` (or ⏎, on a row that waits for nothing) opens everything about a task: four panes, the classic ones."""

import asyncio

from cockpit_repo import BOT, cockpit, make_plan
from test_plan_cli import repo  # noqa: F401  (fixture)
from textual.widgets import Static

from graphene_map import board, plan
from graphene_map.cockpit.details import PANES, Details, pane_text
from graphene_map.store import Store


def text_of(app):
    return str(app.screen.query_one("#pane", Static).render())


def test_enter_on_a_running_task_opens_its_contract_and_tab_goes_through_the_panes(repo):
    make_plan(repo, running=True)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "ids"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Details)
            assert "ids" in text_of(app) and "api.py" in text_of(app)  # the contract: its scope
            seen = [app.screen.which]
            for _ in range(len(PANES) - 1):
                await pilot.press("tab")
                await pilot.pause(0.2)
                seen.append(app.screen.which)
            assert seen == list(PANES)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, Details)

    asyncio.run(go())


def test_the_panes_are_on_1_to_4_and_d_l_and_r_never_show_one_as_they_drop_and_run_one_screen_down(repo):
    make_plan(repo, running=True)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "ids"
            await pilot.press("i")
            await pilot.pause(0.3)
            title = str(app.screen.query_one("#title", Static).render())
            assert "1 contract" in title and "4 record" in title
            for key, pane in (("2", "output"), ("4", "record"), ("3", "changes"), ("1", "contract")):
                await pilot.press(key)
                await pilot.pause(0.1)
                assert app.screen.which == pane, key
            for key in ("d", "l", "r"):  # drop, the old output key, run: none of them moves the pane
                await pilot.press(key)
                await pilot.pause(0.1)
                assert app.screen.which == "contract", key
            assert "1-4 a pane" in str(app.screen.query_one("#foot", Static).render())

    asyncio.run(go())


def test_a_task_that_came_back_lists_no_key_this_screen_does_not_bind_and_says_where_the_rows_keys_act(repo):
    """The panes are the classic screen's: they listed its ways out of a task that came back as keys (w, b,
    n, r and t, each with its command) and `l shows the tool calls`, and here none of those keys does
    anything. They are left out, and a line says, once, where the row's keys act."""
    from graphene_map.cockpit.details import ROW_KEYS

    make_plan(repo, running=True)
    with Store.open(repo) as store:
        plan.release(store, "ids", BOT, "the id lives in db/models.py", wants=["db/models.py"])
        for wide in (60, 120):  # the command on a line of its own, and beside its key
            said = pane_text(store, repo, "ids", "contract", wide).plain
            assert "ask the planner" not in said and "graphene ask" not in said
            assert "widen its scope" not in said and "graphene node" not in said and "sibling" not in said
            assert said.count(ROW_KEYS) == 1 and "the id lives in db/models.py" in said and "scope" in said
        plan.start(store, "ids", BOT, repo)  # a session takes it again: no stream, and `l` was its output
        said = pane_text(store, repo, "ids", "contract", 80).plain
        assert "l shows" not in said and "tool calls" not in said and ROW_KEYS not in said and "check" in said


def test_from_the_graph_the_line_in_the_ways_outs_place_says_where_esc_goes_back_to(repo):
    """i on the graph opens the same panes, and Esc goes back to the graph, where the row's keys act too: the
    line that says where they act names the screen under the panes, not the cockpit."""
    make_plan(repo, running=True)
    with Store.open(repo) as store:
        plan.release(store, "ids", BOT, "the id lives in db/models.py", wants=["db/models.py"])
    app = cockpit(repo, screen="flow")
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "ids"
            await pilot.press("i")
            await pilot.pause(0.3)
            [said] = [line for line in text_of(app).splitlines() if "Esc goes back" in line]
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert app.view == "flow" and "cockpit" not in said

    asyncio.run(go())


def test_a_pane_for_a_node_that_left_the_plan_says_so_and_a_pane_that_cannot_be_made_does_not_crash(repo):
    make_plan(repo)
    with Store.open(repo) as store:
        assert "not in the plan" in pane_text(store, repo, "ghost", "contract", 80).plain
        for which in PANES:  # every pane on a leaf nobody has held: some line, never a traceback
            assert pane_text(store, repo, "ids", which, 80).plain.strip()


def test_the_output_pane_shows_what_the_executor_did_in_words(repo):
    make_plan(repo, running=True)
    with Store.open(repo) as store:
        node = plan.get(store, "ids")
        attempt = {"attempt": 1, "log": None}
        store.log_node("ids", plan._now(), "attempt", "run:claude", node.session_id, None, attempt)
        store.log_node("ids", plan._now(), "did", "run:claude", BOT.session_id, None,
                       {"attempt": 1, "tool": "Edit", "target": "api.py", "verb": "editing"})  # fmt: skip
        text = pane_text(store, repo, "ids", "output", 80).plain
    assert "output of attempt 1" in text and "editing api.py" in text


def test_d_shows_the_direction_in_a_pane_of_its_own(repo):
    make_plan(repo)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("D")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Details) and app.screen.which == "direction"
            assert app.screen.panes == ("direction",) and text_of(app).strip()
            await pilot.press("tab")  # one pane: Tab stays on it
            await pilot.pause(0.1)
            assert app.screen.which == "direction"
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, Details)

    asyncio.run(go())


def test_the_keys_line_fits_80_columns_and_keeps_esc_and_a_single_pane_has_no_jumps(repo):
    make_plan(repo, running=True)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("enter")
            await pilot.pause(0.3)
            foot = str(app.screen.query_one("#foot", Static).render())
            assert len(foot) <= 80 and foot.rstrip().endswith("Esc back") and "Tab" in foot
            await pilot.press("escape")
            await pilot.pause(0.2)
            await pilot.press("D")
            await pilot.pause(0.3)
            foot = str(app.screen.query_one("#foot", Static).render())
            assert "Tab" not in foot and "contract" not in foot and foot.rstrip().endswith("Esc back")

    asyncio.run(go())


def test_enter_then_c_shows_what_a_landed_leaf_changed(repo):
    """README: Enter on a row, then c, is the leaf's diff, as `graphene node diff` has it."""
    from graphene_map.run import run_parallel

    with Store.open(repo) as store:
        leaf = {"id": "a", "title": "write a", "scope": ["a.txt"], "check": "test -s a.txt"}
        plan.propose(store, [leaf], plan.Caller("alex", True))
    run_parallel(lambda: Store.open(repo), repo, repo, 1, "sh -c 'echo a > a.txt'", say=[].append)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)
            app.model.selected = "a"
            await pilot.press("enter")
            await pilot.pause(0.3)
            await pilot.press("c")
            await pilot.pause(0.3)
            assert app.screen.which == "changes" and "a.txt" in text_of(app)

    asyncio.run(go())


def test_keys_under_the_details_do_not_reach_the_rows_and_q_closes_only_the_details(repo):
    make_plan(repo, running=True)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            app.model.selected = "ids"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Details)
            before = (app.model.selected, app.view)
            await pilot.press("j", "g", "m", "x", "r")  # x would hand the running leaf back, under the screen
            await pilot.pause(0.2)
            assert (app.model.selected, app.view) == before and isinstance(app.screen, Details)
            with Store.open(repo) as store:
                assert plan.get(store, "ids").state == plan.RUNNING
            await pilot.press("q")
            await pilot.pause(0.2)
            assert app.is_running and not isinstance(app.screen, Details)

    asyncio.run(go())


def test_i_on_a_question_opens_the_task_it_is_about_and_on_one_about_the_plan_says_what_the_keys_do(repo):
    make_plan(repo, question=True)  # tabs or spaces? is about ids
    with Store.open(repo) as store:
        board.add(store, "question", "ship it on Friday?", BOT, default="yes")
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            asked = {q.text: q.id for q in app.model.questions}
            app.model.selected = asked["tabs or spaces?"]
            await pilot.press("i")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Details) and app.screen.node_id == "ids"
            await pilot.press("escape")
            await pilot.pause(0.2)
            app.model.selected = asked["ship it on Friday?"]
            await pilot.press("i")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, Details)
            said = "it is about the whole plan: ⏎ takes its default, a answers in your own words"
            assert app.model.latest() == said

    asyncio.run(go())


def test_i_opens_the_details_of_a_row_that_waits_for_you_and_takes_nothing(repo):
    """Enter on a proposal accepts it; i is how to read it first (README: `i` then `c` is a diff)."""
    make_plan(repo, proposal=True)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            app.model.selected = "notes"
            await pilot.press("i")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Details) and "notes" in text_of(app)
            await pilot.press("escape")
            await pilot.pause(0.2)
            with Store.open(repo) as store:
                assert plan.get(store, "notes").state == plan.PROPOSED  # looked at, not accepted
            await pilot.press("enter")
            await pilot.pause(0.3)
            with Store.open(repo) as store:
                assert plan.get(store, "notes").state == plan.OPEN

    asyncio.run(go())
