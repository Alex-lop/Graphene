"""The cockpit app, driven headless with Textual's pilot: screens, selection, scrolling, clicks."""

import asyncio
from dataclasses import replace

import pytest
from cockpit_scene import scene
from textual.containers import ScrollableContainer

from graphene_map.cockpit.app import Canvas, Cockpit


def run(coro):
    return asyncio.run(coro)


def app_of(m, **kw):
    return Cockpit(lambda previous: previous or m, **kw)


@pytest.mark.parametrize("size", [(80, 24), (120, 36), (60, 20)])
def test_the_three_screens_open_at_these_sizes_without_a_crash(size):
    async def go():
        m = scene()
        app = app_of(m)
        async with app.run_test(size=size) as pilot:
            for key in ("g", "m", "v", "c", "tab", "tab", "tab"):
                await pilot.press(key)
            await pilot.pause(0.1)
            assert app.view == "cockpit" and app.query_one(Canvas).lines

    run(go())


def test_j_and_k_move_the_selection_down_and_up_the_rows_and_wrap():
    async def go():
        m = scene()
        app = app_of(m)
        async with app.run_test(size=(100, 30)) as pilot:
            assert m.selected == "ids"
            order = [rid for _, rid in m.order()]
            await pilot.press("j")
            assert m.selected == order[order.index("ids") + 1]
            await pilot.press("k", "k")
            assert m.selected == order[order.index("ids") - 1]

    run(go())


def test_a_long_plan_scrolls_and_j_keeps_the_selected_row_on_screen():
    async def go():
        m = scene()
        for i in range(30):
            m.tasks[f"t{i}"] = replace(m.tasks["docs"], id=f"t{i}", title=f"task {i}", state="waiting")
        app = app_of(m)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            box = app.query_one(ScrollableContainer)
            assert box.max_scroll_y > 0
            for _ in range(len(m.order()) - 1):
                await pilot.press("j")
            await pilot.pause(0.1)
            at = next(k for k, line in enumerate(app.query_one(Canvas).lines) if line.row == m.selected)
            assert 0 < box.scroll_y <= at < box.scroll_y + box.size.height

    run(go())


def test_a_click_on_a_row_selects_it():
    async def go():
        m = scene()
        app = app_of(m)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            lines = app.query_one(Canvas).lines
            y = next(k for k, line in enumerate(lines) if line.row == "tests")
            await pilot.click(Canvas, offset=(20, y))
            assert m.selected == "tests"

    run(go())


def test_in_territory_j_moves_the_folder_cursor_and_the_arrows_pick_the_task():
    async def go():
        m = scene()
        app = app_of(m, screen="territory")
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            assert app.cursor == 1
            before = m.selected
            await pilot.press("right")
            assert m.selected != before

    run(go())


def test_in_flow_the_arrows_move_to_the_nearest_box():
    async def go():
        m = scene()
        app = app_of(m, screen="flow")
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.1)
            m.selected = "ids"
            await pilot.press("right")
            assert m.selected == "tests"  # what waits on ids is to its right

    run(go())


def test_q_quits():
    async def go():
        app = app_of(scene())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("q")
        assert app.return_code in (0, None)

    run(go())
