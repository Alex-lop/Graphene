"""The auto header: while the envelope is on, one line in the cockpit's head and the graph's says the round,
its stage, the dollars of the budget and the tasks it accepted; on top, in the need-you purple, while it waits
for the person; gone while auto is off, so today's heads hold. A recording carries the envelope's settings,
and a replay narrates the rounds."""

import asyncio
import json

from cockpit_scene import scene

from graphene_map import demo
from graphene_map.cockpit import rows
from graphene_map.cockpit.app import Cockpit
from graphene_map.cockpit.replay import news

RUNNING = {"round": 1, "rounds": 2, "stage": "running", "spent": 0.42, "budget": 2.0, "check": None,
           "why": "", "tasks": 5, "of": 12}  # fmt: skip
LINE = "auto · round 1 of 3 · running · $0.42 of $2.00 · 5 of 12 tasks"


def plain(lines) -> list[str]:
    return [line.plain() for line in lines]


def test_the_head_says_the_envelopes_round_in_one_line_while_auto_is_on_and_nothing_while_it_is_off():
    m = scene()
    assert len(rows.build_head(m, 80)) == 3 and "auto" not in "\n".join(plain(rows.build_head(m, 80)))
    m.auto = dict(RUNNING)
    for width in (80, 100, 120):
        top = rows.build_head(m, width)
        assert all(line.width() <= width for line in top)
        said = plain(top)
        assert said[0].strip() == "users come back with their ids" and "need you" in said[1]  # as before
        assert said[2].strip() == LINE and len(top) == 4 and top[3].plain().startswith("─")
        assert top[2].segs[0].style == "grey62"  # a fact while it runs, not an alarm


def test_each_stage_is_said_and_waits_sits_on_top_in_the_need_you_purple_with_why():
    m = scene()
    for stage in ("planning", "running", "checking", "fixing", "done"):
        m.auto = {**RUNNING, "stage": stage}
        assert f"round 1 of 3 · {stage} · " in plain(rows.build_head(m, 80))[2]
    why = "the goal's check is red after 3 rounds"
    m.auto = {**RUNNING, "round": 3, "rounds": 2, "stage": "waits", "why": why}
    top = rows.build_head(m, 120)
    assert top[0].plain().strip() == f"auto · round 3 of 3 · waits: {why} · $0.42 of $2.00 · 5 of 12 tasks"
    assert top[0].segs[0].style == rows.AUTO_WAITS
    assert top[1].plain().strip() == "users come back with their ids"  # the goal, under it
    narrow = rows.build_head(m, 80)  # cut to the width, with an ellipsis, never wrapped
    assert narrow[0].plain().startswith(f" auto · round 3 of 3 · waits: {why}") and narrow[0].width() <= 80
    m.auto["why"] = ""
    assert "waits: needs you" in rows.build_head(m, 80)[0].plain()


def test_what_the_envelope_does_not_set_is_left_out_never_a_zero():
    head = "auto · round 1 of 3 · running"
    assert rows.auto_line({**RUNNING, "budget": None}) == f"{head} · $0.42 · 5 of 12 tasks"
    assert rows.auto_line({**RUNNING, "of": None, "tasks": 1}) == f"{head} · $0.42 of $2.00 · 1 task"
    assert rows.auto_line({**RUNNING, "spent": None}) == f"{head} · $0.00 of $2.00 · 5 of 12 tasks"
    no_round = {"round": 1, "rounds": 2, "stage": "", "spent": None, "budget": None, "why": "", "tasks": 0,
                "of": None}  # fmt: skip
    assert rows.auto_line(no_round) == "auto · on · 0 tasks"  # on, and no round yet
    on = rows.auto_line({**no_round, "budget": 2.0, "of": 12})
    assert on == "auto · on · $0.00 of $2.00 · 0 of 12 tasks"


def test_the_graphs_head_carries_the_same_line_and_fits_80_columns():
    async def go():
        m = scene()
        m.auto = dict(RUNNING)
        app = Cockpit(lambda previous: previous or m, screen="flow")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            head = str(app.query_one("#head").render()).splitlines()
            assert "running · agent 1" in head[0] and head[1].strip() == LINE and head[2].startswith("─")
            assert all(len(line.rstrip()) <= 80 for line in head)
            m.auto = {**RUNNING, "stage": "waits", "why": "a question is open"}
            app.paint()
            await pilot.pause(0.1)
            head = str(app.query_one("#head").render()).splitlines()
            assert head[0].strip().startswith("auto · round 1 of 3 · waits: a question is open")
            m.auto = None
            app.paint()
            await pilot.pause(0.1)
            assert len(str(app.query_one("#head").render()).splitlines()) == 2  # as before: a line, the rule

    asyncio.run(go())


def test_a_recording_carries_the_envelopes_settings():
    assert {"settings:auto", "settings:budget", "settings:tasks", "settings:rounds"} <= set(demo.META)


def test_a_replay_narrates_the_rounds():
    def row(detail):
        return {"node_log": [{"node_id": "*", "kind": "auto", "detail": json.dumps(detail)}]}

    assert news(row({"round": 1, "rounds": 2, "stage": "planning"})) == "auto · round 1 of 3: planning"
    fixing = {"round": 2, "rounds": 2, "stage": "fixing", "spent": 0.5}
    assert news(row(fixing)) == "auto · round 2 of 3: fixing"
    waits = {"round": 3, "rounds": 2, "stage": "waits", "why": "the budget is spent · $2.00 of $2.00"}
    assert news(row(waits)) == "auto · round 3 of 3 waits: the budget is spent, $2.00 of $2.00"
    assert news(row({"round": 1, "rounds": 2, "stage": "done"})) == "auto · round 1 of 3: done"
