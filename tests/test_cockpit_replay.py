"""`graphene demo` in the cockpit: the shipped recording applied to a store of its own, change by change."""

import asyncio
import json
import os
import subprocess
from types import SimpleNamespace

from graphene_map import demo as D
from graphene_map import plan
from graphene_map.cockpit.app import Canvas
from graphene_map.cockpit.help import Help
from graphene_map.cockpit.replay import CockpitReplay, banner, news


def replay(tmp_path):
    head, lines = D.load(D.SHIPPED, 1.0)
    return CockpitReplay(D.repository(tmp_path, head), head, lines), head, lines


def still(monkeypatch):
    """The replay's clock stands still, so only `.` moves it: a slow machine cannot play past the opening
    frame before the test pauses (CI's macOS 3.14 took over 2 s from mount to the pause, and the first act
    had taken a row)."""
    monkeypatch.setattr("graphene_map.cockpit.replay.time", SimpleNamespace(monotonic=lambda: 1000.0))


def shown(app) -> str:
    """What the screen shows under its tabs: the head that stays on top (the goal, what the replay is, the
    counts), then the rows."""
    head = str(app.query_one("#head").render())
    return head + "\n" + "\n".join(line.plain() for line in app.query_one(Canvas).lines)


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
            for key in ("t", "w", "x", "d", "R", "y", "s", "P", "u", "e", "f"):  # r is the replay's: again
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
            assert isinstance(app.screen, Help) and app.screen.groups[0][0] == "replay"

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


def test_tasks_accepted_together_are_one_item_that_counts_them():
    """The shipped replay's accept said "you accepted banner says welcome · you accepted app says hello and
    goodbye · your goal: …", the last three of seven items: two of its four tasks, as if the others were not.
    A sub-goal accepted with its tasks says nothing of its own."""
    nodes = {n: {"data": json.dumps({"parent": up})} for n, up in
             (("friendly", None), ("greet", "friendly"), ("bye", "friendly"))}  # fmt: skip
    line = {"nodes": nodes, "node_log": [row("friendly", "accepted"), row("greet", "accepted"),
                                         row("bye", "accepted"), row("*", "goal", note="a friendlier app")]}
    assert news(line, GREET) == "you accepted 2 tasks · your goal: a friendlier app"
    assert news({"node_log": [row("greet", "accepted")]}, GREET) == "you accepted greet says hello"


def test_a_check_that_passed_with_no_finish_is_not_done_yet_and_a_refusal_says_why():
    """The replays walk (third review): the live take narrated "its check passed" where Graphene refused the
    done, nothing in the scope having changed (0.5.0 logged no refusal). A passed check with no finish in its
    change is not done yet; a refusal for an unchanged scope says so."""
    alone = [row("greet", "check_passed")]
    assert news({"node_log": alone}, GREET) == "greet says hello: its check passed, not done yet"
    done = [row("bye", "check_passed"), row("bye", "finished")]
    said = "bye says goodbye: its check passed · bye says goodbye is proven"
    assert news({"node_log": done}, GREET) == said
    refused = [row("greet", "check_passed"), row("greet", "refused", unchanged=["app.py"])]
    said = "greet says hello: its check passed · greet says hello is not done: nothing in its scope changed"
    assert news({"node_log": refused}, GREET) == said


def test_the_news_says_an_edit_as_what_it_changed():
    widened = row("greet", "edited", changed={"scope": [["app.py"], ["app.py", "words.py"]]}, rev=3)
    assert news({"node_log": [widened]}, GREET) == "greet says hello may now write words.py"
    narrowed = row("greet", "edited", changed={"scope": [["app.py", "words.py"], ["app.py"]]}, rev=2)
    assert news({"node_log": [narrowed]}, GREET) == "greet says hello may no longer write words.py"
    # a task's goal, in its own terms: "goal" is the headline's word for yours
    goal = row("farewell", "edited", changed={"goal": ["", "It says goodbye, in full."]}, rev=2)
    said = "bye says goodbye: it should now achieve “It says goodbye, in full.”"
    assert news({"node_log": [goal]}, {"farewell": "bye says goodbye"}) == said


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


def test_the_replay_opens_on_the_plan_not_on_the_settings_a_recording_begins_with(tmp_path, monkeypatch):
    still(monkeypatch)
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


def test_the_replay_names_tasks_by_their_titles_and_a_change_of_bookkeeping_leaves_the_news_up(
    tmp_path, monkeypatch
):
    still(monkeypatch)
    head, lines = recorded(
        tmp_path,
        {"t": 0.2, "nodes": {"greet": node_row("greet", "greet says hello", "proposed")},
         "node_log": [logged(1, "greet", "proposed")]},
        {"t": 0.4, "node_log": [logged(2, "*", "usage", calls=1)]},
        {"t": 0.6, "node_log": [logged(3, "greet", "accepted")]},  # not the end, which says the next step
    )  # fmt: skip

    async def go():
        app = CockpitReplay(D.repository(tmp_path, head), head, lines)
        async with app.run_test(size=(100, 30)) as pilot:
            assert app.model.latest() == "proposed: greet says hello"
            await pilot.press("space", "full_stop")
            assert app.next == 2 and app.model.latest() == "proposed: greet says hello"  # usage said nothing

    asyncio.run(go())


def test_at_80_columns_the_top_line_still_says_no_model_ran(tmp_path):
    """At 80 columns the head dropped "a scripted stand-in, no model ran" first, so the demo a stranger runs
    in a default terminal never said it was a script. The day goes first, then where it is; never that."""

    async def go():
        app, head, _ = replay(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            top = str(app.query_one("#head").render()).splitlines()[0]
            assert head["shown"] in top and "replay" in top and len(top.rstrip()) <= 80, top
            await pilot.press("space")  # paused: the key line says space plays on, when the head has no room
            await pilot.pause(0.2)
            assert str(app.query_one("#keys").render()).lstrip().startswith("space play ·")
            await pilot.press("space")
            await pilot.pause(0.2)
            assert str(app.query_one("#keys").render()).lstrip().startswith("space pause ·")

    asyncio.run(go())


def test_r_plays_the_replay_again_and_is_not_also_the_cockpits_run(tmp_path):
    """r is the replay's "again", and the cockpit's r (run the task under the cursor) heard it too, so every
    replay played again under the words "a replay: nothing runs here"."""
    from graphene_map.cockpit.replay import REFUSED

    async def go():
        app, _, _ = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space", "full_stop", "full_stop")
            await pilot.press("r")
            await pilot.pause(0.3)
            assert REFUSED not in [said for _, said in app.model.feed]

    asyncio.run(go())


def test_the_changes_pane_of_a_replay_writes_nothing_where_the_demo_was_started(tmp_path, monkeypatch):
    """In a replay, `i` then the changes pane ran `graphene node diff` in the directory the demo was started
    in: it made a plan store there, read that repository's own plan, and never showed a diff (a replay keeps
    no commits). The pane says where what changed is, and the directory is left as it was."""
    from graphene_map.cockpit.details import REPLAYED

    mine = tmp_path / "mine"
    mine.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=mine, check=True)
    before = sorted(os.listdir(mine))
    monkeypatch.chdir(mine)

    async def go():
        app, _, _ = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space", *["full_stop"] * 9, "i", "3")
            await pilot.pause(0.5)
            assert REPLAYED in str(app.screen.query_one("#pane").render())

    asyncio.run(go())
    assert sorted(os.listdir(mine)) == before


def test_the_end_keeps_its_state_and_its_keys_and_says_the_next_step_and_r_opens_on_what_needs_you(tmp_path):
    """At the last change the key line still offered space and `.`, space turned "ended: last frame" into
    "paused at 28 of 28", and at 80 columns, where the head has no room for "ended", nothing said the replay
    had ended or what to do next. `.` while paused said "3 of 28", and `r` opened on the row last selected,
    not on the plan's question."""

    async def go():
        app, _, lines = replay(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            opened = app.model.selected
            await pilot.press("space", "full_stop")
            assert app.state == f"paused at {app.next} of {len(lines)}"
            await pilot.press("j", *["full_stop"] * len(lines))  # a row of your own, then to the end
            ended = "r again · i details · g graph · m map · ? keys · q"
            for key in ("full_stop", "space", "space"):  # nothing is left to play: neither plays it on
                await pilot.press(key)
                assert (app.state, str(app.query_one("#feed").render()).strip()) == (D.ENDED, D.NEXT), key
                assert str(app.query_one("#keys").render()).strip() == ended, key
            await pilot.press("r")
            assert app.model.selected == opened and app.model.latest() != D.NEXT  # the plan, as it opened

    asyncio.run(go())


def test_the_replays_keys_fit_80_by_24_and_list_only_what_works_there_and_d_has_no_direction(tmp_path):
    """The replay's `?` put its keys in front of every key of the live help: at 80x24 it scrolled, three lines
    wrapped, q and the marks were below the fold, and it listed every key that answers "a replay: nothing runs
    here". D showed the direction of the replay's temporary repository, and told you to write a file there."""
    from textual.containers import VerticalScroll
    from textual.widgets import Static

    from graphene_map.cockpit.details import Details

    async def go():
        app, _, _ = replay(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space", "question_mark")
            await pilot.pause(0.3)
            assert isinstance(app.screen, Help) and app.screen.query_one(VerticalScroll).max_scroll_y == 0
            said = str(app.screen.query_one(Static).render())
            keys = [line[10:16].strip() for line in said.splitlines() if line[10:16].strip()]
            assert keys[:4] == ["space", ".", "r", "q"] and "c g m" in keys and "i" in keys, keys
            assert not {"⏎ y", "1-9 a", "t", "w", "x", "r R s", "e E", "D", ":", "v p"} & set(keys), keys
            assert all(len(line) <= 76 for line in said.splitlines()) and "● running" in said
            assert said.count("in your own repo") == 1  # where every other key acts, said once
            await pilot.press("escape", "D")
            await pilot.pause(0.3)
            assert not isinstance(app.screen, Details)
            assert app.model.latest().startswith("a replay has no direction")

    asyncio.run(go())


def test_each_board_row_of_the_shipped_replay_leaves_the_screen_only_with_the_persons_act_on_it(
    tmp_path, monkeypatch
):
    """The recording took the question first, and under `board: auto` an assumption and a leave-out show only
    while a question is open: the first `.` took all three rows off the screen (7 need you became 4), and the
    next two narrated acts on rows that had already gone."""

    def acted(line):  # the items the person's acts in this change were on
        acts = [json.loads(r["detail"]) for r in line.get("node_log") or [] if r["kind"] == "board"]
        return {a["item"] for a in acts if a["act"] != "put up"}

    still(monkeypatch)

    async def go():
        app, _, lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space")
            shown, gone = {q.id: q.kind for q in app.model.questions}, []
            assert sorted(shown.values()) == ["assume", "leave out", "question"]
            while app.next < len(lines):
                line = lines[app.next]
                await pilot.press("full_stop")
                now = {q.id: q.kind for q in app.model.questions}
                assert shown.keys() - now.keys() <= acted(line), (app.next, shown, now)
                gone += [shown[i] for i in shown.keys() - now.keys()]
                shown = now
            assert sorted(gone) == ["assume", "leave out", "question"]

    asyncio.run(go())


def test_the_shipped_replay_shows_agent_1_stopped_then_back_while_two_agents_still_run(tmp_path, monkeypatch):
    """What the README's GIF and cockpit.png show, kept when the recording is made again: agent 1's write is
    stopped in a change of its own, where it needs you while three run, and in the next change of its row
    it is back with its reason while agents 2 and 3 still run (a change between them that moves nothing on
    its row, the agent's own hand-back call in the recording of 20 October, is let by)."""
    still(monkeypatch)

    async def go():
        app, _, lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space")
            seen = []
            while app.next < len(lines):
                await pilot.press("full_stop")
                greet, (need, running, _, _) = app.model.tasks["greet"], app.model.scoreboard()
                stopped = bool(greet.stopped) if greet.state == "running" else None
                seen.append((greet.state, stopped, need, running))
            stopped = seen.index(("running", True, 1, 3))
            after = next(s for s in seen[stopped + 1 :] if s != seen[stopped])  # its row's next change
            assert after == ("came back", None, 1, 2) and greet.agent == "1"

    asyncio.run(go())


def test_at_80_columns_the_news_says_your_answer_before_what_it_changed(tmp_path):
    """board.py logs the edits an answer makes before the answer, and the news said them in that order: at 80
    columns the question left the shipped replay under "bye says goodbye: it should now achieve “It says
    goodbye, in full.” · you took…", the answer cut off. What you answered comes first, then what it
    changed."""

    def took(line):  # the change that takes the question's default
        acts = [json.loads(r["detail"]) for r in line.get("node_log") or [] if r["kind"] == "board"]
        return any(a["act"] == "took" and a["item"] == "bye-word" for a in acts)

    async def go():
        app, _, lines = replay(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space")
            while not took(lines[app.next - 1]):
                await pilot.press("full_stop")
            said = str(app.query_one("#feed").render()).strip()
            answer = "you took the default: goodbye, as the paragraph's friendlier app would"
            assert said == f"{answer} · bye s…", said  # then what it changed, cut at 80

    asyncio.run(go())


def test_the_replays_map_offers_only_what_reads_there_and_p_paints_nothing(tmp_path):
    """The replay's map kept the live map's key line ("p paint · w widen"), and p turned on a paint mode where
    a click did nothing: a replay's scopes are the recording's."""
    from graphene_map.cockpit.replay import REFUSED

    async def go():
        app, _, _ = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space", "m", "p")
            await pilot.pause(0.2)
            keys = str(app.query_one("#keys").render())
            assert "paint" not in keys and "widen" not in keys and "v lens" in keys
            assert not app.paint_mode and app.model.latest() == REFUSED

    asyncio.run(go())



def test_the_live_takes_news_stays_up_through_a_change_that_says_nothing(tmp_path):
    """The replays walk (third review): stepping `graphene demo --live`, the news went blank at nine changes
    of bookkeeping: the news fades six seconds after it was said on the model's clock, and a replay's clock
    jumps with the recording's, 8 to 80 seconds between changes there. The last news stays up."""
    head, lines = D.load(D.LIVE_TAKE, 1.0)

    async def go():
        app = CockpitReplay(D.repository(tmp_path, head), head, lines)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("space")
            blank = []
            while app.next < len(lines):
                await pilot.press("full_stop")
                if app.model.feed and not app.model.latest():
                    blank.append(app.next)
            assert blank == []

    asyncio.run(go())
