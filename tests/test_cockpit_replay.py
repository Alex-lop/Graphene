"""`graphene demo` in the cockpit: the shipped recording applied to a store of its own, change by change."""

import asyncio

from graphene_map import demo as D
from graphene_map.cockpit.app import Canvas
from graphene_map.cockpit.help import Help
from graphene_map.cockpit.replay import CockpitReplay, banner, news


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


def test_the_news_says_what_an_agent_did_and_why_a_leaf_came_back_not_the_bookkeeping():
    import json

    def row(node, kind, **detail):
        return {"node_id": node, "kind": kind, "detail": json.dumps(detail)}

    line = {"node_log": [
        row("greet", "usage", model="x", calls=1), row("greet", "did", verb="editing", target="app.py"),
        row("greet", "said", text="the word\n lives in words.py"),
        row("greet", "released", why="it needs words.py"), row("greet", "ended", exit=0),
    ]}  # fmt: skip
    said = ["greet: editing app.py", "greet: the word lives in words.py"]
    said += ["greet came back: it needs words.py"]
    assert news(line) == " · ".join(said)
    assert news({"node_log": [row("bye", "landed")]}) == "bye landed"
    long = "the word lives in words.py, which my scope does not cover, so the check cannot pass"
    assert news({"node_log": [row("greet", "released", why=long)]}).endswith("cover,…")  # cut, and says so
    assert news({"nodes": {"bye": {"state": "done"}}}) == "bye done"  # nothing in words: the replay's own


def test_i_opens_everything_about_the_leaf_that_came_back_in_a_replay_too(tmp_path):
    from graphene_map.cockpit.details import Details

    async def go():
        app, head, lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space")
            while app.next < len(lines) and not any(t.state == "came back" for t in app.model.tasks.values()):
                await pilot.press("full_stop")
            back = next(t for t in app.model.tasks.values() if t.state == "came back")
            app.model.selected = back.id
            await pilot.press("i")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Details)
            await pilot.press("escape")
            await pilot.pause(0.2)
            await pilot.press("enter")  # Enter would take it: a replay says nothing runs here
            assert "nothing runs here" in app.model.latest()

    asyncio.run(go())


def test_a_look_that_lands_after_the_screen_has_closed_draws_nothing(tmp_path):
    """The look's timer could tick while the app shut down, its widgets gone: `NoMatches: #bar`, on a
    loaded runner. Once it is no longer running a look does nothing."""

    async def go():
        app, _, _ = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
        app.look()  # as a late tick would: no widget is left to draw on

    asyncio.run(go())
