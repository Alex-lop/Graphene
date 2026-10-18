"""`graphene demo` in the cockpit: the shipped recording applied to a store of its own, change by change."""

import asyncio

from graphene_map import demo as D
from graphene_map.cockpit.app import Canvas
from graphene_map.cockpit.help import Help
from graphene_map.cockpit.replay import CockpitReplay, banner


def replay(tmp_path):
    head, lines = D.load(D.SHIPPED, 1.0)
    return CockpitReplay(D.repository(tmp_path, head), head, lines), head, lines


def shown(app) -> str:
    return "\n".join(line.plain() for line in app.query_one(Canvas).lines)


def test_the_replay_says_what_it_is_and_plays_the_recording_into_rows(tmp_path):
    async def go():
        app, head, lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)
            assert "replay · a scripted stand-in, no model ran" in shown(app)
            for _ in range(len(lines)):  # `.` applies the next change and stays paused
                await pilot.press("full_stop")
            await pilot.pause(0.3)
            assert "ended: last frame" in shown(app)
            assert app.model.tasks and all(t.state == "done" for t in app.model.tasks.values())
            assert app.model.source == "replay" and app.model.scoreboard()[2] == app.model.scoreboard()[3]

    asyncio.run(go())


def test_space_pauses_and_plays_on_and_r_plays_it_again_from_the_start(tmp_path):
    async def go():
        app, head, lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space")
            assert app.paused is not None and "paused at" in app.state
            at = app.next
            await pilot.pause(0.5)
            assert app.next == at  # a paused replay does not move
            await pilot.press("space")
            assert app.paused is None
            for _ in range(len(lines)):
                await pilot.press("full_stop")
            assert app.next == len(lines)
            await pilot.press("r")
            await pilot.pause(0.2)
            assert app.next < len(lines) and app.model.scoreboard()[2] == 0

    asyncio.run(go())


def test_a_key_that_would_change_the_plan_says_so_and_does_nothing(tmp_path):
    async def go():
        app, head, lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            for _ in range(len(lines)):
                await pilot.press("full_stop")
            app.model.selected = next(iter(app.model.tasks))
            for key in ("t", "w", "x", "d", "R", "y", "s", "P", "u", "e"):  # r is the replay's own: again
                app.model.feed.clear()
                await pilot.press(key)
                assert app.model.latest() == "a replay: nothing runs here", key
            assert app.doer is None and not app.tell_open

    asyncio.run(go())


def test_the_help_adds_the_replays_own_keys_and_the_banner_names_the_day():
    head = {"shown": "a scripted stand-in, no model ran", "day": "2026-10-12"}
    assert banner(head, "3 of 16") == "replay · a scripted stand-in, no model ran · 2026-10-12 · 3 of 16"

    async def go(tmp_path):
        app, _head, _lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("question_mark")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Help) and app.screen.extra

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(go(Path(tmp)))
