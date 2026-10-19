"""The graph screen in the app: the goal and the sub-goals are boxes, and neither an arrow nor a click on one
selects it."""

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
