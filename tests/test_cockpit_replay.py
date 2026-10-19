"""`graphene demo` in the cockpit: the shipped recording applied to a store of its own, change by change."""

import asyncio
import json

from graphene_map import demo as D
from graphene_map import plan
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
            assert "space pause · . next · r again · i details" in str(app.query_one("#keys").render())
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


def row(node, kind, **detail):
    """A row of the plan's log as a recording holds it, its detail JSON."""
    return {"node_id": node, "kind": kind, "detail": json.dumps(detail)}


GREET = {"greet": "greet says hello", "bye": "bye says goodbye"}  # the tasks' titles, as the store has them


def test_the_news_narrates_what_an_agent_did_by_its_tasks_title_and_leaves_the_bookkeeping_out():
    line = {"node_log": [
        row("greet", "usage", model="x", calls=1), row("greet", "did", verb="editing", target="app.py"),
        row("greet", "said", text="the word\n lives in words.py"), row("greet", "denied", path="words.py"),
        row("greet", "did", verb="running", target="graphene node release greet"),  # its own: bookkeeping
        row("greet", "released", why="it needs words.py"), row("greet", "ended", exit=0),
    ]}  # fmt: skip
    said = ["greet says hello: the word lives in words.py", "greet says hello: stopped writing words.py"]
    said += ["greet says hello came back: it needs words.py"]
    assert news(line, GREET) == " · ".join(said)
    assert news({"node_log": [row("bye", "landed")]}, GREET) == "bye says goodbye landed"
    long = "the word lives in words.py, which my scope does not cover, so the check cannot pass"
    assert news({"node_log": [row("greet", "released", why=long)]}).endswith("cover,…")  # cut, and says so
    busy = {"node_log": [
        row("greet", "did", verb="editing", target="app.py"), row("greet", "denied", path="words.py"),
        row("bye", "did", verb="editing", target="bye.py"),
        row("bye", "did", verb="running", target="pytest"), row("greet", "released", why="it needs words.py"),
    ]}  # fmt: skip
    said = ["greet says hello: stopped writing words.py", "bye says goodbye: running pytest"]
    said += ["greet says hello came back: it needs words.py"]  # not crowded out by the moves before it
    assert news(busy, GREET) == " · ".join(said)
    for kind in ("precheck", "usage", "model", "attempt", "ended", "run"):  # say nothing: the last news stays
        assert news({"node_log": [row("greet", kind)]}, GREET) == "", kind
    assert news({"runs": {"greet-1.txt": "ok\n"}}) == news({"plan_meta": {"plan_first": "on"}}) == ""


def test_the_news_says_the_boards_acts_in_the_items_own_words():
    items = [{"id": "bye-word", "kind": "question"}, {"id": "flag", "kind": "leave out"}]
    meta = {"board": json.dumps(items)}  # the board as the same change left it: each item's kind
    put = [row("bye", "board", note="put up bye-word: what does bye say?", item="bye-word", act="put up"),
           row("*", "board", note="put up flag: a --name flag; nobody asked", item="flag", act="put up")]
    said = "asks: what does bye say? · leaves out: a --name flag; nobody asked"
    assert news({"plan_meta": meta, "node_log": put}) == said
    took = [row("bye", "board", note="took bye-word: what does bye say? → goodbye", item="bye-word",
                act="took"),
            row("*", "board", note="took flag: a --name flag; nobody asked", item="flag", act="took")]
    said = "you took the default: goodbye · you agreed to leave out: a --name flag; nobody asked"
    assert news({"plan_meta": meta, "node_log": took}) == said


def test_the_news_says_an_edit_as_what_it_changed():
    widened = row("greet", "edited", changed={"scope": [["app.py"], ["app.py", "words.py"]]}, rev=3)
    assert news({"node_log": [widened]}, GREET) == "greet says hello may now write words.py"
    narrowed = row("greet", "edited", changed={"scope": [["app.py", "words.py"], ["app.py"]]}, rev=2)
    assert news({"node_log": [narrowed]}, GREET) == "greet says hello may no longer write words.py"


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


def recorded(tmp_path, *changes):
    """A recording of these changes, as `graphene demo --record` writes one, loaded as the replay loads it."""
    head = {"graphene demo": 1, "recorded": "2026-10-18T22:00:00.000Z", "graphene": "0.6.0",
            "repository": "demo", "shown": "a scripted stand-in, no model ran"}  # fmt: skip
    path = tmp_path / "recording.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in (head, *changes)), encoding="utf-8")
    return D.load(path, 1.0)


def node_row(node_id, title, state, seq=1):
    leaf = plan.Node(node_id, title, scope=["app.py"], check="true", state=state)
    data = json.dumps(plan.to_dict(leaf))
    return {"id": node_id, "seq": seq, "state": state, "session_id": None, "data": data}


def test_the_replay_opens_on_the_plan_not_on_the_settings_a_recording_begins_with(tmp_path):
    head, lines = recorded(
        tmp_path,
        {"t": 0.2, "plan_meta": {"plan_first": "on", "settings:size": "auto"}, "tracked": ["app.py"]},
        {"t": 0.4, "nodes": {"greet": node_row("greet", "greet says hello", "proposed")}},
        {"t": 0.6, "nodes": {"greet": node_row("greet", "greet says hello", "open")}},
    )

    async def go():
        app = CockpitReplay(D.repository(tmp_path, head), head, lines)
        async with app.run_test(size=(100, 30)) as pilot:
            assert app.next == 2 and app.model.tasks["greet"].state == "proposed"  # its first frame: the plan
            assert "Nothing is planned yet." not in shown(app)
            await pilot.press("space", "full_stop", "r")  # to the end, and again from the start
            assert app.next == 2 and app.model.tasks["greet"].state == "proposed"

    asyncio.run(go())


def logged(n, node, kind, **detail):
    """The nth row of a recorded plan's log, a second after the one before it."""
    return {"id": n, "node_id": node, "timestamp": f"2026-10-18T22:00:{n:02d}.000Z", "kind": kind,
            "actor": "planner", "session_id": None, "agent_id": None,
            "detail": json.dumps(detail)}  # fmt: skip


def test_the_replay_names_tasks_by_their_titles_and_a_change_of_bookkeeping_leaves_the_news_up(tmp_path):
    head, lines = recorded(
        tmp_path,
        {"t": 0.2, "nodes": {"greet": node_row("greet", "greet says hello", "proposed")},
         "node_log": [logged(1, "greet", "proposed")]},
        {"t": 0.4, "node_log": [logged(2, "*", "usage", calls=1)]},
    )  # fmt: skip

    async def go():
        app = CockpitReplay(D.repository(tmp_path, head), head, lines)
        async with app.run_test(size=(100, 30)) as pilot:
            assert app.model.latest() == "proposed: greet says hello"
            await pilot.press("space", "full_stop")
            assert app.next == 2 and app.model.latest() == "proposed: greet says hello"  # usage said nothing

    asyncio.run(go())
