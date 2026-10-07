"""What three walkers found in `graphene demo` at 4860dec, each against the shipped recording, frame by
frame: the status line keeps one form and offers neither R nor P, the bill stays on it at 80 columns,
every step says what changed, the goal reads done only when everything under it is, a refused key's line
gives way to the next change, and j k still move after `r`."""

import asyncio
import re
from pathlib import Path

import pytest

from graphene_map import demo, plan
from graphene_map.store import Store

RECORDINGS = Path(__file__).parent / "recordings"


def frames(tmp_path, size, before=()):
    """Pause, press ``before``, then step through every change, noting after each: the status line's
    plan line, its last line, the goal row's word, and every node's state."""
    head, lines = demo.load(demo.SHIPPED)
    repo = demo.repository(tmp_path, head)
    app, seen = demo.Replay(repo, head, lines), []

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause(0.3)
            await pilot.press("space", *before)
            while app.next < len(lines):
                await pilot.press("full_stop")
                await pilot.pause(0.05)
                status = str(app.query_one("#status").render()).splitlines()
                with Store.open(repo) as store:
                    states = {n.id: n.state for n in plan.nodes(store)}
                seen.append((status[0], status[-1], app.tree.rows[None][1] if app.nodes else "", states))

    asyncio.run(go())
    return lines, seen


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_the_replays_status_line_keeps_one_form_offers_neither_r_nor_p_and_keeps_its_bill(tmp_path, size):
    """Walk findings 25 and 41: at frame 8 the line became watch's long form with `R runs 1 ready` and
    `plan first: on (P)`, and at 80x24 the bill fell off it once the run finished."""
    _, seen = frames(tmp_path, size)
    billed = False
    for top, _, _, _ in seen:
        offered = [word for word in (" R", "(P)", "plan first") if word in top]
        assert re.match(r"\d+ on you", top) and not offered, top  # the short form, never watch's long one
        billed = billed or "bill $" in top
        assert "bill $" in top or not billed, top  # once there, it stays to the last frame
    assert billed


def test_every_step_says_what_changed_and_the_goal_is_done_only_when_everything_under_it_is(tmp_path):
    """Walk finding 25: a `.` that changed nothing visible, and a frame with the goal ✓ done above a
    sub-goal still ○ (the leaves were done, the roll-up was the next change)."""
    lines, seen = frames(tmp_path, (120, 36))
    for line, (_, said, goal, states) in zip(lines[1:], seen, strict=True):  # the first is on at once
        assert said == demo.what(line)[: len(said) - 1] + "…" or said == demo.what(line), (said, line.keys())
        assert goal != "done" or set(states.values()) == {plan.DONE}, states


def test_a_refused_keys_line_gives_way_to_the_next_change(tmp_path):
    """Walk finding 11: `w` said "a replay: nothing runs here", and that line stayed to the last frame."""
    _, seen = frames(tmp_path, (80, 24), before=("w",))
    assert all(said != demo.REFUSED for _, said, _, _ in seen)


def test_j_and_k_move_after_the_replay_is_played_again(tmp_path):
    """Walk finding 35: after `r`, the tree was hidden while the replay's store was empty, lost the focus,
    and j k moved nothing, paused or playing."""
    head, lines = demo.load(demo.SHIPPED)
    app, seen = demo.Replay(demo.repository(tmp_path, head), head, lines), {}

    async def go():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("space", *["full_stop"] * 4, "r", "space", *["full_stop"] * 4)
            await pilot.pause(0.2)
            seen["at"] = app.tree.cursor_line
            await pilot.press("j", "j")
            await pilot.pause(0.2)
            seen["moved"] = app.tree.cursor_line

    asyncio.run(go())
    assert seen["moved"] == seen["at"] + 2


def test_the_replays_clock_is_its_recordings_and_it_draws_no_meter_strip():
    """The recording is from before the meter: a leaf's minutes run to its newest row, not to today."""
    from datetime import datetime

    rows = [{"timestamp": "2026-09-29T07:58:47.069Z"}, {"timestamp": "2026-09-29T08:01:00.000Z"}]
    assert demo.Replay.clock(None, rows) == datetime.fromisoformat("2026-09-29T08:01:00.000Z")
    assert demo.Replay.METERS is False


def test_a_recording_made_with_the_meter_draws_its_strip_and_the_shipped_one_does_not(tmp_path):
    """The shipped recording is from before the meter; the night's Claude Code run on feeds is not. While a
    leaf of it runs, its live row shows, with the dollars it had reached then."""
    strips = {}
    for name, path in (("shipped", demo.SHIPPED), ("meter", RECORDINGS / "meter-claude.jsonl")):
        head, lines = demo.load(path)
        (tmp_path / name).mkdir()
        app, shown = demo.Replay(demo.repository(tmp_path / name, head), head, lines), []

        async def go(app=app, lines=lines, shown=shown):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("space")
                for _ in lines:  # `.` is one change each time: it stalled on a float once, at change 31
                    await pilot.press("full_stop")
                    await pilot.pause(0.05)
                    strip = app.query_one("#meter")
                    if strip.display:
                        shown.append(str(strip.render()))
                shown.append(app.next == len(lines))

        asyncio.run(go())
        strips[name] = shown
    assert strips["shipped"] == [True]
    *rows, ended = strips["meter"]
    assert ended and any("claude" in s and "$" in s for s in rows), rows
    assert not any("no meter" in s or re.search(r"-\d+ s ago", s) for s in rows), rows  # 7 October's two
