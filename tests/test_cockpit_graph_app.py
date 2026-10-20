"""The graph screen in the app: the goal is the box where the arrows arrive, and neither an arrow key nor a
click on it selects it."""

import asyncio

from cockpit_scene import scene

from graphene_map.cockpit.app import Canvas, Cockpit


def test_the_arrows_land_only_on_tasks_and_a_click_on_the_goal_selects_nothing():
    async def go():
        m = scene()
        m.tasks["ids"].above = [("api", "the API")]
        app = Cockpit(lambda previous: previous or m, screen="flow")
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.1)
            for key in ("left", "left", "up", "down", "down", "right", "left", "left", "up"):
                await pilot.press(key)
                assert m.selected in m.tasks
            before = m.selected
            lines = app.query_one(Canvas).lines
            y = next(k for k, line in enumerate(lines) if "users come back" in line.plain())
            await pilot.click(Canvas, offset=(lines[y].plain().index("users"), y))
            assert app.is_running and m.selected == before

    asyncio.run(go())


def test_an_empty_plan_says_one_line_on_the_graph_and_on_the_map():
    from graphene_map.cockpit.flow_view import EMPTY as ON_THE_GRAPH
    from graphene_map.cockpit.model import Model
    from graphene_map.cockpit.territory_view import EMPTY as ON_THE_MAP

    async def go():
        app = Cockpit(lambda previous: previous or Model("no goal yet"))
        async with app.run_test(size=(80, 24)) as pilot:
            shown = {}
            for key in ("g", "m", "j", "right", "enter"):
                await pilot.press(key)
                shown[key] = [line.plain() for line in app.query_one(Canvas).lines]
            assert shown["g"][0] == " " + ON_THE_GRAPH
            assert shown["m"] == shown["enter"] == [" " + ON_THE_MAP]
            assert app.is_running

    asyncio.run(go())


def test_the_graphs_head_cuts_a_long_title_and_never_the_state_and_agent_after_it():
    """The graph's head fitted its whole line to the width, so a long title pushed the selected task's state,
    agent and checks off the end at 80 columns: the title is what is cut."""
    from graphene_map.cockpit.app import Cockpit as App

    async def go():
        m = scene()
        m.tasks["ids"].full = "users return their ids as strings everywhere the API answers, in every handler"
        app = App(lambda previous: previous or m, screen="flow")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            head = str(app.query_one("#head").render()).splitlines()[0]
            assert "running · agent 1" in head and "✓1/3" in head and len(head.rstrip()) <= 80, head

    asyncio.run(go())

