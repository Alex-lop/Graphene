"""The cockpit app, driven headless with Textual's pilot: screens, selection, scrolling, clicks."""

import asyncio
from dataclasses import replace

import pytest
from cockpit_scene import scene
from textual.containers import ScrollableContainer
from textual.widgets import Static

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


def test_the_top_line_says_whose_plan_this_is_and_an_empty_plan_says_what_to_do(tmp_path):
    from graphene_map.cockpit.model import Model

    async def go():
        app = Cockpit(lambda previous: previous or Model("no goal yet"), root=tmp_path / "watched")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert "watched" in str(app.query_one("#bar").render())
            shown = "\n".join(line.plain() for line in app.query_one(Canvas).lines)
            assert "Nothing is planned yet." in shown

    run(go())


def test_question_mark_opens_the_keys_on_one_screen_and_escape_closes_it():
    from graphene_map.cockpit.help import Help, help_text

    async def go():
        app = app_of(scene())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("question_mark")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Help), [type(s).__name__ for s in app.screen_stack]
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert not isinstance(app.screen, Help)

    run(go())
    text = help_text(80).plain.splitlines()
    assert len(text) <= 22 and all(len(line) <= 96 for line in text)
    assert "tell it one line" in help_text(80).plain and "any graphene command" in help_text(80).plain


def test_the_keys_line_keeps_help_and_quit_when_the_terminal_is_narrow():
    from graphene_map.cockpit.app import KEYS, fit_keys

    for width in (79, 60, 40):
        for line in KEYS.values():
            fitted = fit_keys(line, width)
            assert len(fitted) <= width and "? keys" in fitted
            assert fitted.rstrip().endswith("q") or fitted.rstrip().endswith("quit")
    assert fit_keys(KEYS["cockpit"], 200) == KEYS["cockpit"]


def test_the_graph_says_what_the_selected_task_is_for():
    from graphene_map.cockpit.model import Model, Task

    async def go():
        m = Model("goal")
        m.tasks["a"] = Task("a", "users return ids", "running", why="API", agent="fox", checks=1)
        m.selected = "a"
        app = app_of(m, screen="flow")
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause(0.1)
            shown = "\n".join(line.plain() for line in app.query_one(Canvas).lines)
            assert "users return ids  ·  running · fox · proof 0/1 · for API" in shown

    run(go())


def test_a_long_news_line_ends_in_an_ellipsis_at_the_screens_width():
    async def go():
        m = scene()
        app = app_of(m)
        async with app.run_test(size=(60, 20)) as pilot:
            m.say("farewell: editing bye.py · farewell: running node done farewell · greet came back")
            app.paint()
            await pilot.pause(0.1)
            line = str(app.query_one("#feed", Static).render())
            assert line.endswith("…") and len(line) <= 60

    run(go())
