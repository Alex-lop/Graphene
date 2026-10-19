"""The cockpit app, driven headless with Textual's pilot: screens, selection, scrolling, clicks."""

import asyncio
from dataclasses import replace

import pytest
from cockpit_scene import scene
from textual.containers import ScrollableContainer, VerticalScroll
from textual.widgets import Static

from graphene_map.cockpit.app import Canvas, Cockpit
from graphene_map.cockpit.help import Help


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
            assert app.screen.query_one(VerticalScroll).max_scroll_y == 0  # all of it, on 80 by 24
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert not isinstance(app.screen, Help)

    run(go())
    text = help_text(80).plain.splitlines()
    assert len(text) <= 22 and all(len(line) <= 96 for line in text)
    assert "tell its agent one line" in help_text(80).plain and "any graphene command" in help_text(80).plain


def test_the_keys_line_keeps_help_and_quit_when_the_terminal_is_narrow():
    from graphene_map.cockpit.app import KEYS, fit_keys

    for width in (79, 60, 40):
        for line in KEYS.values():
            fitted = fit_keys(line, width)
            assert len(fitted) <= width and "? keys" in fitted
            assert fitted.rstrip().endswith("q") or fitted.rstrip().endswith("quit")
    assert fit_keys(KEYS["cockpit"], 200) == KEYS["cockpit"]


def test_the_tabs_say_cockpit_graph_and_map_and_plan_first_is_said_only_when_it_is_off(tmp_path):
    async def go():
        m = scene()
        app = Cockpit(lambda previous: previous or m, root=tmp_path / "shop")
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            bar = str(app.query_one("#bar").render())
            assert "c cockpit  g graph  m map" in bar and "flow" not in bar and "territory" not in bar
            for first, shown in (("on", False), ("auto", False), ("off", True)):
                m.first = first
                app.paint()
                assert ("plan first off" in str(app.query_one("#bar").render())) is shown, first

    run(go())


def test_the_graph_says_what_the_selected_task_is_for():
    from graphene_map.cockpit.model import Model, Task

    async def go():
        m = Model("goal")
        m.tasks["a"] = Task("a", "users return ids", "running", why="API", agent="1", checks=1)
        m.selected = "a"
        app = app_of(m, screen="flow")
        async with app.run_test(size=(100, 24)) as pilot:
            await pilot.pause(0.1)
            shown = "\n".join(line.plain() for line in app.query_one(Canvas).lines)
            assert "users return ids  ·  running · agent 1 · ✓0/1 · for API" in shown

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


def test_keys_under_the_help_do_not_reach_the_rows_and_q_closes_only_the_help():
    async def go():
        m = scene()
        app = app_of(m)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("question_mark")
            await pilot.pause(0.2)
            assert isinstance(app.screen, Help)
            before = (m.selected, app.view)
            await pilot.press("j", "g", "m", "tab", "d", "r")
            await pilot.pause(0.1)
            assert (m.selected, app.view) == before and isinstance(app.screen, Help)
            await pilot.press("q")
            await pilot.pause(0.2)
            assert app.is_running and not isinstance(app.screen, Help)

    run(go())


def test_the_three_screens_open_on_a_plan_with_nothing_in_it():
    from graphene_map.cockpit.model import Model

    async def go():
        app = Cockpit(lambda previous: previous or Model("nothing yet"))
        async with app.run_test(size=(80, 24)) as pilot:
            for key in ("g", "m", "tab", "c", "tab", "tab"):
                await pilot.press(key)
                await pilot.pause(0.05)
            assert app.is_running and app.view in ("cockpit", "flow", "territory")

    run(go())


def test_the_help_scrolls_from_the_keyboard_where_the_terminal_is_shorter_than_it():
    async def go():
        app = app_of(scene())
        async with app.run_test(size=(80, 12)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("question_mark")
            await pilot.pause(0.3)
            box = app.screen.query_one(VerticalScroll)
            assert box.max_scroll_y > 0 and box.scroll_y == 0
            await pilot.press("j", "j", "down")
            await pilot.pause(0.2)
            assert box.scroll_y > 0
            await pilot.press("k", "k", "k", "k")
            await pilot.pause(0.2)
            assert box.scroll_y == 0

    run(go())


def test_the_graph_and_the_map_scroll_to_what_is_selected_when_there_are_more_than_fit():
    from graphene_map.cockpit.model import Model, Task

    m = Model("a long plan")
    m.files = [f"d{i}/f{j}.py" for i in range(12) for j in range(5)]
    m.tasks = {f"t{i}": Task(f"t{i}", f"task {i}", "ready", [f"d{i}/**"]) for i in range(40)}
    m.selected = "t0"

    async def go():
        app = app_of(m)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            box = app.query_one(ScrollableContainer)
            await pilot.press("g")
            await pilot.pause(0.2)
            for _ in range(39):
                await pilot.press("down")  # on the graph the arrows go to the next box down
            await pilot.pause(0.3)
            top, bottom = app.flow_layout.rects[m.selected][1], app.flow_layout.rects[m.selected][3]
            assert box.max_scroll_y > 0 and box.scroll_y <= top and bottom < box.scroll_y + box.size.height

    async def folders():
        app = app_of(m)
        async with app.run_test(size=(80, 10)) as pilot:  # the map's rows do not fit this height
            await pilot.pause(0.1)
            box = app.query_one(ScrollableContainer)
            await pilot.press("m")
            await pilot.pause(0.2)
            await pilot.press("k")  # wraps to the last folder, below the first screen
            await pilot.pause(0.3)
            assert box.scroll_y > 0 and 3 + app.cursor < box.scroll_y + box.size.height

    run(go())
    run(folders())


def test_a_line_wider_than_the_screen_is_cut_and_never_wraps_under_the_rows_below_it():
    from graphene_map.cockpit.lines import Line, Seg

    async def go():
        app = app_of(scene())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            canvas = app.query_one(Canvas)
            canvas.set_lines([Line([Seg("x" * 300)]), Line([Seg("second")])])
            await pilot.pause(0.2)
            assert canvas.virtual_size.height == 2 and canvas.size.height == 2

    run(go())
