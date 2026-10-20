"""The cockpit app, driven headless with Textual's pilot: screens, selection, scrolling, clicks."""

import asyncio
from dataclasses import replace

import pytest
from cockpit_scene import scene
from textual.containers import ScrollableContainer, VerticalScroll
from textual.widgets import Static

from graphene_map.cockpit.app import Canvas, Cockpit
from graphene_map.cockpit.help import Help
from graphene_map.cockpit.model import Task


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


def test_escape_on_the_graph_or_the_map_comes_back_to_the_cockpit():
    async def go():
        app = app_of(scene())
        async with app.run_test(size=(100, 30)) as pilot:
            for keys in (("g",), ("m",), ("p",)):  # p paints on the map: Esc stops that too
                await pilot.press(*keys)
                assert app.view != "cockpit"
                await pilot.press("escape")
                assert app.view == "cockpit" and not app.paint_mode, keys

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
        m.selected = m.order()[0][1]  # from the first row, j down to the last
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
            head = str(app.query_one("#head", Static).render())  # the goal and the counts stay on top
            assert "users come back with their ids" in head and "need you" in head and "proven" in head
            assert not any("need you" in line.plain() for line in app.query_one(Canvas).lines)

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


def test_the_line_being_told_shows_on_its_row_only_and_the_rows_do_not_jump(tmp_path):
    from textual.widgets import Input

    async def go():
        app = Cockpit(lambda previous: previous or scene(), root=tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            high = app.query_one(ScrollableContainer).size.height
            await pilot.press("t", "u", "s", "e")
            await pilot.pause(0.1)
            box = app.query_one("#tell", Input)
            assert box.value == "use" and box.size.height == 0
            assert app.query_one(ScrollableContainer).size.height == high  # no box pushes the rows up
            assert any("tell agent 1: use▌" in line.plain() for line in app.query_one(Canvas).lines)

    run(go())


def test_the_line_being_told_is_on_screen_from_the_graph_the_map_and_the_last_row_that_fits(tmp_path):
    async def go():
        m = scene()
        for i in range(30):  # more rows than the screen has room for
            m.tasks[f"t{i}"] = replace(m.tasks["tests"], id=f"t{i}", title=f"task {i}")
        app = Cockpit(lambda previous: previous or m, root=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            box = app.query_one(ScrollableContainer)
            for keys, sel in ((("g",), "ids"), (("m",), "ids"), ((), "t20")):  # t20: the last row on screen
                m.selected = sel
                app.paint()
                await pilot.press(*keys)
                await pilot.pause(0.1)
                await pilot.press("t", "u", "s", "e")
                await pilot.pause(0.1)
                at = [k for k, line in enumerate(app.query_one(Canvas).lines) if "use▌" in line.plain()]
                assert app.view == "cockpit" and at, keys  # the rows: only they have a line to type on
                assert box.scroll_y <= at[0] < box.scroll_y + box.size.height, keys
                await pilot.press("escape")

    run(go())


def test_the_colon_line_says_what_it_takes_before_anything_is_typed(tmp_path):
    async def go():
        app = Cockpit(lambda previous: previous or scene(), root=tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("colon")
            await pilot.pause(0.2)
            assert app.screen.prompt == "a graphene command: ask …, run, plan accept, stop"
            keys = str(app.query_one("#keys", Static).render()).strip()
            assert keys == "Enter sends · Esc cancels"  # the key bar says what the keys do while it is open
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert "Esc cancels" not in str(app.query_one("#keys", Static).render())

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
    said = help_text(80).plain
    assert "tell its agent a line, heard with its next write or command" in said
    assert "any graphene command" in said


def test_the_keys_line_keeps_help_and_quit_when_the_terminal_is_narrow():
    from graphene_map.cockpit.app import KEYS, fit_keys

    m = scene()
    m.questions[0].default, m.questions[0].options = "keep both of them, old and new", ["a", "b", "c"]
    app = app_of(m)
    lines = [KEYS["territory"]]
    for view in ("cockpit", "flow"):
        app.view = view
        for rid in [rid for _, rid in m.order()]:
            m.selected = rid
            lines.append(app.row_keys())
    for line in lines:
        assert len(line) <= 79, line
        for width in (79, 60, 40):
            fitted = fit_keys(line, width)
            assert len(fitted) <= width and "? keys" in fitted and fitted.rstrip().endswith("q")
        assert fit_keys(line, 200) == line


def test_the_keys_line_says_what_the_keys_do_to_the_selected_row(tmp_path):
    async def go():
        m = scene()
        m.tasks["back"] = Task("back", "retry it", "came back", agent="3", offers={"w": ["node", "widen"]})
        offers = {"w": ["node", "widen"], "b": ["node", "sibling"], "r": ["node", "reopen", "schema"]}
        m.tasks["more"] = Task("more", "retry more", "came back", agent="4", offers=offers)
        app = Cockpit(lambda previous: previous or m, root=tmp_path)

        def keys():
            return str(app.query_one("#keys", Static).render()).strip()

        async with app.run_test(size=(110, 30)) as pilot:  # the widest line, with f fork, needs 106
            for sel, own in (
                ("q", "⏎ keep both · 1 pick · a answer · d drop"),
                ("docs", "⏎ accept · A all · d drop · i details"),
                ("ids", "t tell · w widen · x hand back · i details"),
                ("back", "⏎ try again · f fork · w widen · t tell · i details"),
                ("more", "⏎ try again · f fork · w widen · b new task · r reopen · t tell · i details"),
                ("migrate", "⏎ sign off · x reopen · i details"),
                ("schema", "i details · x reopen"),
                ("tests", "t tell · i details"),
            ):
                m.selected = sel
                app.paint()
                assert keys() == own + " · g graph · m map · ? keys · q"
            m.source = "replay"  # a recording: only what reads it (the cockpit's line is the replay's own)
            app.view = "flow"
            assert app.row_keys() == "i details · c cockpit · m map · ? keys · q"
            m.source, app.view = "plan", "cockpit"
            m.tasks["ids"].stopped = []  # nothing stopped: nothing to widen, so no w
            m.selected = "ids"
            app.paint()
            assert "w widen" not in keys()
            await pilot.press("t")
            assert keys() == "Enter sends to agent 1 · Esc cancels"

    run(go())


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


def test_the_graphs_legend_says_only_what_it_drew():
    async def go():
        m = scene()
        app = app_of(m, screen="flow")
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.1)

            def shown():
                return "\n".join(line.plain() for line in app.query_one(Canvas).lines)

            assert "retry loop" not in shown() and "two-way" not in shown()  # plain edges: no legend
            m.extra_edges = [("tests", "ids", "loop")]
            app.paint()
            assert "amber lane = a retry loop (bounded)" in shown() and "two-way" not in shown()
            m.extra_edges = [("ids", "migrate", "two")]
            app.paint()
            assert "◀▶ two-way" in shown() and "retry loop" not in shown()

    run(go())


def test_i_on_a_question_about_the_whole_plan_names_only_the_numbers_that_pick_an_option():
    async def go():
        m = scene()  # its question is about the whole plan, and has one option: 1 drop old
        app = app_of(m)
        async with app.run_test(size=(100, 30)) as pilot:
            m.selected = "q"
            await pilot.press("i")
            assert "1 picks its option" in m.latest() and "1 2" not in m.latest()  # as its key bar: 1 pick
            m.questions[0].options = ["drop old", "keep old", "ask later"]
            await pilot.press("i")
            assert "1-3 pick an option" in m.latest()

    run(go())


def test_on_the_graph_a_selected_question_says_what_it_asks_and_what_it_is_about():
    async def go():
        m = scene()
        m.questions[0].about = "ids"
        m.selected = "q"
        app = app_of(m, screen="flow")
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(0.1)
            shown = str(app.query_one("#head", Static).render())  # on top: a question has no box
            assert "? Keep old ids working?  ·  about users return ids" in shown

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
            shown = str(app.query_one("#head", Static).render())
            assert "users return ids  ·  running · agent 1 · ✓0/1 · for API" in shown

    run(go())


def test_the_line_under_the_rows_is_blank_when_there_is_no_news():
    async def go():
        m = scene()
        app = app_of(m)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert str(app.query_one("#feed", Static).render()).strip() == ""  # the marks are in ? now
            m.say("graphene board take q: taken")
            app.paint()
            assert "board take" in str(app.query_one("#feed", Static).render())

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
            await pilot.press("g")  # the graph of nothing says what it will draw, in a line that fits
            [said] = [line.plain() for line in app.query_one(Canvas).lines if line.plain().strip()]
            assert said.strip().startswith("Nothing is planned yet") and len(said) <= 79

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
            assert box.scroll_y > 0 and box.scroll_y <= app.cursor < box.scroll_y + box.size.height
            assert str(app.query_one("#head", Static).render()).startswith(" MAP ")  # its headline, on top

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


def test_the_graph_says_what_is_selected_on_top_however_tall_it_is_in_one_line_that_fits():
    """The line that says what is selected was under the whole graph, off screen on a plan taller than the
    terminal, so a question, which has no box, was selected and acted on unseen; and it was cut at the edge.
    It is on top now, as the cockpit's head is, in one line that ends in an ellipsis where it is cut."""
    m = scene()
    for i in range(12):
        m.tasks[f"t{i}"] = replace(m.tasks["tests"], id=f"t{i}", title=f"task {i}")
    m.questions[0].text = "Which PDF library should render the invoices, and does it run in the worker?"
    m.questions[0].about = "ids"
    m.selected = "q"

    async def go():
        app = app_of(m, screen="flow")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert app.query_one(ScrollableContainer).max_scroll_y > 0  # taller than the screen
            top = str(app.query_one("#head", Static).render()).splitlines()[0]
            assert top.startswith(" ? Which PDF library") and top.endswith("…") and len(top) <= 80
            for _ in range(12):
                await pilot.press("down")
            await pilot.pause(0.2)
            top = str(app.query_one("#head", Static).render()).splitlines()[0]
            assert top.startswith(f" {m.tasks[m.selected].title}  ·  waiting") and len(top) <= 80
            m.tasks["migrate"].full = "Migrate the old ids to the new format: both stay readable"
            m.selected = "migrate"  # the line has the room a box has not: the title is whole, not five words
            app.paint()
            top = str(app.query_one("#head", Static).render()).splitlines()[0]
            assert top.startswith(" Migrate the old ids to the new format  ·  review · agent 2")

    run(go())


def test_a_replay_says_what_it_is_on_the_graph_and_on_the_map_too():
    m = scene()
    m.source, m.banner = "replay", "replay · a scripted stand-in, no model ran · 2026-10-12 · 3 of 28"

    async def go():
        app = app_of(m)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            for key in ("g", "m"):  # the cockpit's head says it; on these the top line does, where room is
                await pilot.press(key)
                bar = str(app.query_one("#bar", Static).render())
                assert bar.rstrip().endswith("replay · a scripted stand-in, no model ran") and len(bar) <= 80
            await pilot.press("c")
            assert "replay · a scripted stand-in" in str(app.query_one("#head", Static).render())

    run(go())
