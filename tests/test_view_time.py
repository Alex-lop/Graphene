# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The time view (view_time.py): a lane for each leaf that has been held, what its executor was doing
when, and the marks that matter, drawn from log rows written here as test_views writes them. Then the
screen and the print: the view in `graphene watch` and its pane, `graphene plan --view time`, and the
meter's recording replayed through it, frame by frame."""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)
from test_tui import RUN
from test_views import logged, look

from graphene_map import demo
from graphene_map import plan as P
from graphene_map import view_time as VT
from graphene_map import views as V
from graphene_map.store import Store

RECORDINGS = Path(__file__).parent / "recordings"


def row(node, s, kind, detail=None, actor="run:claude"):
    """A log row ``s`` seconds after 04:00 on 7 October."""
    return logged(node, f"{s // 60:02d}:{s % 60:02d}", kind, detail or {}, actor)


def did(node, s, verb, target="a.py", attempt=1):
    return row(node, s, "did", {"attempt": attempt, "tool": "x", "target": target, "verb": verb})


def stamp(s):
    return row("*", s, "x")["timestamp"]


def leaf(i, state=P.DONE, held=True):
    held = "2026-10-07T04:00:00.000Z" if held else None
    return P.Node(i, f"the {i} leaf", scope=[f"{i}.py"], check="true", state=state, started_at=held)


def drawn(nodes, rows, s, width=80, cursor=None, words=None):
    """The view at ``width``, now ``s`` seconds after 04:00, and each lane's time column by id."""
    words = words or {n.id: P.reads(n, nodes) for n in nodes}
    now = datetime.fromisoformat(stamp(s))
    out = VT.draw(nodes, words, "the goal", width, 24, cursor, V.happened(rows, "alex", now))
    label = out.lines[-1].plain.index("0")  # the axis starts the time column
    return out, {i: out.lines[line].plain[label:] for i, (line, _, _) in out.at.items()}


# a, done: two attempts, the first read, searched, edited, ran, talked, then was quiet; b, done: a Claude
# Code session held it, no attempt; c: a session holds it now. Now is 74 s after the ask: one cell a second
ACTIVE = [
    row("*", 0, "asked", actor="alex"), row("*", 30, "accepted", actor="alex (no terminal)"),
    row("*", 40, "accepted", actor="bob"),
    row("a", 0, "started"), row("a", 0, "attempt", {"attempt": 1}), did("a", 1, "reading"),
    did("a", 2, "searching"), did("a", 3, "editing"), did("a", 3, "reading"), did("a", 3, "editing"),
    did("a", 4, "running"), row("a", 5, "said", {"attempt": 1, "text": "now the tests"}),
    row("a", 66, "ended", {"attempt": 1, "exit": 1}), row("a", 69, "attempt", {"attempt": 2}),
    did("a", 70, "editing", attempt=2), row("a", 72, "ended", {"attempt": 2, "exit": 0}),
    row("b", 10, "started", actor="claude:aaaa1111"), row("b", 20, "finished", actor="claude:aaaa1111"),
    row("c", 60, "started", actor="claude:bbbb2222"),
]  # fmt: skip


def test_each_cell_is_what_the_executor_mostly_did_idle_past_a_minute_a_session_a_plain_bar():
    nodes = [leaf("a"), leaf("b"), leaf("c", P.RUNNING), leaf("d", P.OPEN, held=False)]
    out, lanes = drawn(nodes, ACTIVE, 74)
    assert out.order == ["a", "b", "c"]  # d was never held: no lane
    assert [line.plain.split()[0] for line in out.lines[1:5]] == ["you", "a", "b", "c"]
    # idle before the first row; reading, searching (reading too), editing (two rows of three), running,
    # talking, carried on until the said row is a minute old; nothing between attempts
    assert lanes["a"] == "─▒▒█▓" + "░" * 60 + "──" + "  " + "─███"
    assert lanes["b"] == " " * 10 + "━" * 11  # the session's hold: no meter, a plain bar
    assert lanes["c"] == " " * 60 + "━" * 13 + "●"  # held now: to now, running
    assert out.lines[1].plain == " you  |" + " " * 29 + "|"  # alex's acts, with or without a terminal
    axis = "".join(f"{k * 15}s".ljust(15) for k in range(5)).rstrip()  # a label each 15 s: 10 s left 7 cells
    assert out.lines[-1].plain == " " * 6 + axis
    assert out.note == "3 lanes · 1 min · agents 1 min · you 2 acts ~1 min · width 1 of 1"  # b, c: sessions
    assert {s.style for s in out.lines[2].spans} == {"green", "dim"}  # a done leaf's bar; idle dim


def test_the_marks_sit_at_their_moment_and_the_later_of_two_moves_right():
    rows = [row("a", 0, "started"), row("a", 0, "attempt", {"attempt": 1}), did("a", 1, "editing"),
            row("a", 10, "denied", {"path": "x"}), row("a", 12, "breach", {"paths": ["x"]}),
            row("a", 14, "refused", {"outside": ["x"]}), row("a", 20, "check_failed"),
            row("a", 30, "released", {"why": "x", "person": False}),
            row("a", 32, "released", {"why": "x", "person": True}),
            row("a", 34, "released", {"why": "x", "person": False, "stopped": True}),
            row("a", 40, "started"), row("a", 40, "attempt", {"attempt": 1}), did("a", 41, "editing"),
            row("a", 50, "check_passed"), row("a", 50, "landed"), row("a", 51, "finished"),
            row("a", 52, "ended", {"attempt": 1, "exit": 0}), row("b", 0, "started"),
            row("b", 0, "attempt", {"attempt": 1}), did("b", 1, "running")]  # fmt: skip
    nodes = [leaf("a"), leaf("b", P.RUNNING)]
    out, lanes = drawn(nodes, rows, 74)
    marks = {k: c for k, c in enumerate(lanes["a"]) if c in "!✗✓↩◆●"}
    assert marks == {10: "!", 12: "!", 14: "!", 20: "✗", 30: "↩", 50: "✓", 51: "◆"}  # landed: one right
    assert lanes["b"].endswith("●") and len(lanes["b"]) == 74  # running now: its last cell
    line = out.lines[2]
    styles = {line.plain[6 + k]: s.style for s in line.spans for k in marks if s.start <= 6 + k < s.end}
    assert styles == {"!": "magenta", "✗": "magenta", "↩": "magenta", "✓": "green", "◆": "green"}
    assert [s.style for s in out.lines[3].spans if s.end == len(out.lines[3])] == ["yellow bold"]
    assert "1 came back" in out.note  # the person's and the stopped run's are not hand-backs


def test_time_starts_at_this_plans_ask_never_at_an_archived_ones():
    rows = [row("*", 0, "asked", actor="alex"), row("*", 10, "archived", actor="alex"),
            row("*", 20, "asked", actor="alex"), row("a", 30, "started"),
            row("a", 30, "attempt", {"attempt": 1}), did("a", 31, "editing"),
            row("a", 40, "ended", {"attempt": 1, "exit": 0}),
            row("*", 94, "accepted", actor="alex")]  # fmt: skip
    out, lanes = drawn([leaf("a")], rows, 94)  # 74 s from the second ask: one cell a second
    assert lanes["a"] == " " * 10 + "─" + "█" * 10 and out.lines[1].plain == " you  |" + " " * 72 + "|"


def test_the_note_counts_this_plans_clocks_never_an_archived_ones():
    """The fourth review of 8 October: the note's agents and you read the whole log, every archived plan
    too, beside lanes and a you lane that are this plan's alone."""
    old = [row("*", 0, "asked", actor="alex"), row("old", 0, "started"),
           row("old", 0, "attempt", {"attempt": 1, "meter": "claude"}), did("old", 5, "editing"),
           row("old", 1500, "usage", {"model": "m", "calls": 9, "dollars": 5.0, "attempt": 1}),
           row("old", 1500, "ended", {"attempt": 1, "exit": 0, "meter": "claude"}),
           *(row("*", 1501 + k, "x", actor="alex") for k in range(12)),
           row("*", 1520, "archived", actor="alex")]
    new = [row("*", 1530, "asked", actor="alex"), row("a", 1540, "started"),
           row("a", 1540, "attempt", {"attempt": 1, "meter": "claude"}), did("a", 1545, "editing"),
           row("a", 1580, "ended", {"attempt": 1, "exit": 0, "meter": "claude"})]  # fmt: skip
    out, _ = drawn([leaf("a")], old + new, 1590)
    assert out.lines[1].plain.count("|") == 1  # this plan's ask, its one act
    assert out.note == "1 lane · <1 min · agents <1 min · you 1 act ~1 min · width 1 of 1"


def test_a_plan_a_session_proposed_starts_at_your_acceptance_so_your_y_is_drawn():
    """No `graphene ask`: a Claude Code session proposed the leaf, and your y accepted it a moment before
    it started. Time starts at that acceptance, so the act that started the work has its tick."""
    rows = [row("a", 0, "accepted", actor="alex"), row("a", 1, "started"),  # accepted: on the node
            row("a", 1, "attempt", {"attempt": 1}), did("a", 2, "editing")]  # fmt: skip
    out, _ = drawn([leaf("a")], rows, 74)
    assert out.lines[1].plain.startswith(" you  |")


def test_none_under_thirty_cells_of_time_and_no_line_wider_than_the_width():
    long = "an-id-much-longer-than-the-label"
    nodes = [leaf(long), leaf("b", P.RUNNING)]
    rows = [row(long, 0, "started"), row(long, 0, "attempt", {"attempt": 1}), did(long, 30, "editing"),
            row(long, 40, "check_passed"), row(long, 40, "landed"), row("b", 0, "started")]  # fmt: skip
    words = {long: "done", "b": "running"}
    assert VT.draw(nodes, words, "g", 43, 24, None, V.happened(rows, "alex")) is None  # 14 + 29
    assert VT.draw(nodes, words, "g", 44, 24, None, V.happened(rows, "alex")) is not None
    for width in (80, 120):
        out, _ = drawn(nodes, rows, 600, width, cursor=long, words=words)
        assert max(line.cell_len for line in out.lines) <= width and len(out.note) <= width
        assert out.lines[2].plain.startswith(" an-id-much…  ") and out.at[long] == (2, 0, 12)
        assert out.lines[2].spans[0].style == "green reverse"  # the cursor's label
        steps = {80: ["0m", "2m", "4m", "6m", "8m"], 120: [f"{k}m" for k in range(10)]}  # 8 cells apart
        assert out.lines[-1].plain.split() == steps[width]
    bare = VT.draw(nodes, words, "g", 80, 24, None)  # what `choose` draws: no events, the lanes bare
    assert [line.plain.strip() for line in bare.lines[2:4]] == [long[:10] + "…", "b"]


def test_the_note_says_lanes_minutes_hand_backs_and_both_clocks_and_drops_pieces_to_fit():
    agents, you = {"seconds": 1860, "running": 1, "dollars": 2.41}, {"acts": 4, "minutes": 3}
    said = "3 lanes · 12 min · 1 came back · agents 31 min $2.41 · you 4 acts ~3 min"
    assert VT.note(3, 725, 1, agents, you) == said
    ran = {"most": 2, "lanes": 3, "alone": 0.4}  # meter.width
    assert VT.note(3, 725, 1, agents, you, None, ran) == said + " · width 2 of 3"
    assert VT.note(3, 725, 1, agents, you, len(said) + 14, ran) == said  # the width goes first
    assert VT.note(3, 725, 1, agents, you, 60) == "3 lanes · 12 min · 1 came back · agents 31 min $2.41"
    assert VT.note(3, 725, 1, agents, you, 20) == "3 lanes · 12 min"
    quiet = {"seconds": 0, "running": 0, "dollars": 0}  # no dollars said when there are none
    said = "1 lane · <1 min · agents 0 min · you 1 act ~1 min"
    assert VT.note(1, 20, 0, quiet, {"acts": 1, "minutes": 1}) == said


def test_suits_once_a_leaf_has_been_held_and_a_tree_that_fits_still_wins():
    fresh = [leaf("a", P.OPEN, held=False), leaf("b", P.OPEN, held=False)]
    assert VT.suits(fresh, 80, 24) == 0
    ran = [leaf("a", P.RUNNING), leaf("b", P.OPEN, held=False)]
    assert VT.suits(ran, 80, 24) > V.BASELINE
    words = {n.id: P.reads(n, ran) for n in ran}
    assert V.choose(ran, words, "g", 78, 10) == "tree"


def test_activity_runs_a_repeat_together_and_says_when_after_its_attempt_began():
    edits = [did("a", k, "editing", "cli/main.py") for k in (5, 6, 7)]
    rows = [row("a", 0, "attempt", {"attempt": 1}), *edits,
            row("a", 12, "said", {"attempt": 1, "text": "done,\n  I think"}),
            did("a", 13, "editing", "cli/main.py"), row("a", 15, "ended", {"attempt": 1, "exit": 1}),
            row("a", 20, "attempt", {"attempt": 2}), did("a", 85, "reading", attempt=2)]  # fmt: skip
    (first, said), (second, again) = VT.activity(rows)
    assert (first["attempt"], first["executor"], second["attempt"]) == (1, "claude", 2)
    assert said == [(5, "editing cli/main.py", 3), (12, "done, I think", 1), (13, "editing cli/main.py", 1)]
    assert again == [(65, "reading a.py", 1)]


def ran(repo, finish, monkeypatch, title="users returns ids"):
    """ids ran and landed: it read, edited twice, said so; schema ran and came back. The plan's clock
    is the scenario's: `finish` stamps its check with it."""
    alex = P.Caller("alex", True)
    monkeypatch.setattr(P, "_now", lambda: stamp(60))
    with Store.open(repo) as store:

        def log(*rows):
            for e in rows:
                store.log_node(e["node_id"], e["timestamp"], e["kind"], e["actor"], None, None, e["detail"])

        log(row("*", 0, "asked", {"note": "ids"}, "alex"))
        P.set_goal(store, "users come back with their ids", alex, now=stamp(0))
        P.propose(store, [{"id": "ids", "title": title, "scope": ["api.py"],
                           "check": "grep -q ids api.py"},
                          {"id": "schema", "title": "the schema", "scope": ["schema.py"], "check": "true"}],
                  alex, now=stamp(1))  # fmt: skip
        P.start(store, "ids", RUN, repo, now=stamp(5))
        log(row("ids", 5, "attempt", {"attempt": 1, "meter": "claude"}), did("ids", 10, "reading", "api.py"),
            did("ids", 30, "editing", "api.py"), did("ids", 31, "editing", "api.py"),
            row("ids", 40, "said", {"attempt": 1, "text": "users() returns ids now"}))  # fmt: skip
        finish(store, repo, "ids", RUN, now=stamp(60))
        log(row("ids", 61, "ended", {"attempt": 1, "exit": 0, "meter": "claude"}),
            row("ids", 62, "landed", {}, "graphene run"))  # fmt: skip
        P.start(store, "schema", RUN, repo, now=stamp(70))
        log(row("schema", 70, "attempt", {"attempt": 1, "meter": "claude"}),
            did("schema", 80, "running", "pytest -q"))  # fmt: skip
        P.release(store, "schema", RUN, "it needs api.py", now=stamp(120))


def test_plan_view_time_prints_the_lanes_the_axis_and_the_note(repo, finish, monkeypatch):
    ran(repo, finish, monkeypatch)
    printed = person("plan", "--view", "time", "--width", "80", "--height", "24")
    assert printed.exit_code == 0, printed.output
    assert printed.stdout.splitlines() == [
        "users come back with their ids",
        " you     |",  # the ask and the goal, then the plan, in its first slice
        " ids       ───▒▒▒▒▒▒▒▒▒▒▒▒██████░░░░░░░░░░░✓◆",
        " schema                                          ──────▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓↩",
        "         0m                                1m",
        "2 lanes · 2 min · 1 came back · agents 1 min · you 2 acts ~1 min",  # in 78 cells: the width gave way
    ]
    wide = person("plan", "--view", "time", "--width", "100", "--height", "24").stdout.splitlines()[-1]
    assert wide == printed.stdout.splitlines()[-1] + " · width 1 of 2"  # one leaf at a time, of the two


def test_an_agent_prints_the_persons_lane_and_clock_not_its_own(repo, finish, monkeypatch):
    """The fourth review of 8 October: printed from a Claude Code session, the you lane and its clock were
    the session's acts, and the person's went unseen."""
    ran(repo, finish, monkeypatch)
    args = ("plan", "--view", "time", "--width", "80", "--height", "24")
    printed, theirs = agent(*args), person(*args)
    assert printed.exit_code == 0, printed.output
    assert printed.stdout == theirs.stdout and "you 2 acts ~1 min" in printed.stdout


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_in_watch_a_leaf_that_ran_shows_what_it_did_one_that_came_back_its_usual_pane(
    repo, finish, monkeypatch, size
):
    ran(repo, finish, monkeypatch)
    seen = look(repo, ["j"], size, view="time")
    assert seen["showing"] == "time" and seen["cursor"] == "ids"
    assert any(line.startswith(" ids ") and "─▒" in line for line in seen["view"]), seen["view"]  # drawn live
    detail = [line.rstrip() for line in seen["detail"].splitlines()]
    at = detail.index("attempt 1 · claude · 04:00")
    said = ["    +5s  reading api.py", "   +25s  editing api.py ×2", "   +35s  users() returns ids now"]
    assert detail[at + 1 :] == said  # each after the attempt began; the two edits in a row, once
    back = look(repo, ["j", "j"], size, view="time")
    assert back["cursor"] == "schema" and "attempt 1 · claude" not in back["detail"]
    assert "it needs api.py" in " ".join(back["detail"].split())  # the pane a leaf that came back has


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_in_watch_the_newest_of_more_rows_than_fit_is_in_sight_under_a_title_of_two_lines(
    repo, finish, monkeypatch, size
):
    ran(repo, finish, monkeypatch, title=" ".join(["users returns ids"] * 8))
    with Store.open(repo) as store:
        for k in range(40):
            e = did("ids", 41, "editing", f"f{k}.py")
            store.log_node(e["node_id"], e["timestamp"], e["kind"], e["actor"], None, None, e["detail"])
    side = look(repo, ["j"], size, view="time")["side"]
    assert any("editing f39.py" in line for line in side), side  # the view's note is a third bottom line
    said = look(repo, ["j", "m"], size, view="time")  # m says what it did: a fourth line
    assert any("editing f39.py" in line for line in said["side"]), (said["status"], said["side"])


def test_in_watch_a_leaf_whose_executor_did_and_said_nothing_keeps_its_usual_pane(repo, finish):
    alex = P.Caller("alex", True)
    with Store.open(repo) as store:
        P.set_goal(store, "users come back with their ids", alex)
        P.propose(store, [{"id": "ids", "title": "returns ids", "scope": ["api.py"], "check": "true"}], alex)
        P.start(store, "ids", RUN, repo)
        store.log_node("ids", P._now(), "attempt", "run:script", None, None, {"attempt": 1})  # no meter
        finish(store, repo, "ids", RUN)
    detail = look(repo, ["j"], (80, 24), view="time")["detail"]
    assert "attempt 1 ·" not in detail and "scope" in detail, detail  # its contract, not a bare heading


BILL = row("a", 20, "usage", {"model": "nemotron", "calls": 12, "dollars": 0.01})  # with no attempt number


@pytest.mark.parametrize("bill", [[], [BILL]])
def test_an_attempt_the_meter_cannot_read_is_a_plain_bar_not_idle(bill):
    """With no row the meter reads, nor any bill; or, from before the meter night, a bill alone: Graphene's
    Nemotron executor wrote one usage row as an attempt ended, and nothing of what it did (the fourth
    review of 8 October: first-light-rung-7.jsonl drew such an attempt idle, whole)."""
    rows = [row("a", 0, "started"), row("a", 0, "attempt", {"attempt": 1}), *bill,
            row("a", 20, "ended", {"attempt": 1, "exit": 0})]  # fmt: skip
    _, lanes = drawn([leaf("a")], rows, 74)
    assert set(lanes["a"].strip()) == {"━"}  # held, its doings unseen: never drawn as an idle executor


def test_a_running_attempt_the_meter_reads_is_idle_until_its_first_row():
    rows = [row("a", 0, "started"), row("a", 0, "attempt", {"attempt": 1, "meter": "claude"})]
    _, lanes = drawn([leaf("a", P.RUNNING)], rows, 74)
    assert lanes["a"] == "─" * 73 + "●"


def test_in_watch_a_leaf_that_waits_for_your_sign_off_keeps_its_usual_pane(repo, finish):
    alex = P.Caller("alex", True)
    with Store.open(repo) as store:
        P.set_goal(store, "users come back with their ids", alex)
        P.propose(store, [{"id": "ids", "title": "returns ids", "scope": ["api.py"], "check": "true",
                           "signoff": True}], alex)  # fmt: skip
        P.start(store, "ids", RUN, repo)
        tried = row("ids", 5, "attempt", {"attempt": 1, "meter": "claude"})
        for e in (tried, did("ids", 6, "editing", "api.py")):
            store.log_node(e["node_id"], e["timestamp"], e["kind"], e["actor"], None, None, e["detail"])
        finish(store, repo, "ids", RUN)
    detail = " ".join(look(repo, ["j"], (80, 24), view="time")["detail"].split())
    assert "sign-off" in detail and "attempt 1 ·" not in detail, detail  # what to do, not what was done


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_the_replay_draws_what_each_executor_did_at_its_moment_and_a_running_bar_grows(
    tmp_path, monkeypatch, size
):
    """Tab to the time view while `graphene demo` plays the meter's recording, then step it. Each did and
    said row stays drawn on its lane, at its moment, from the frame it came in; a running bar grows to
    the replay's clock and ends in ●; a lane never goes. A finished bar takes fewer cells as the span
    grows, since the slice grows with it: a moment is where it stays, not a count of cells. The person
    is the recording's, whoever watches it."""
    monkeypatch.setenv("USER", "someone-else")
    monkeypatch.delenv("GRAPHENE_PERSON", raising=False)
    head, lines = demo.load(RECORDINGS / "meter-claude.jsonl")
    repo = demo.repository(tmp_path, head)
    app, frames, moved = demo.Replay(repo, head, lines), [], {}

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause(0.3)
            await pilot.press("space")
            while not app.nodes:  # paused; then on, to the proposal
                await pilot.press("full_stop")
                await pilot.pause(0.05)
            for _ in range(4):
                if app.showing != "time":
                    await pilot.press("tab")
            while app.next < len(lines):
                await pilot.press("full_stop")
                await pilot.pause(0.05)
                with Store.open(repo) as store:
                    rows, nodes = store.node_log(), P.nodes(store)
                frames.append((app.showing, app.drawn, rows, {n.id for n in nodes if n.state == P.RUNNING}))
            await pilot.press("j")  # j was the replay's `.` in a view, and moved nothing
            await pilot.pause(0.05)
            moved.update(cursor=app.selected(), detail=str(app.query_one("#detail").render()))

    asyncio.run(go())
    assert moved["cursor"] == "zero-rule" and "attempt 1 · claude · " in moved["detail"], moved
    width, before, grew = size[0] - 2, {}, set()
    for showing, out, rows, running in frames:
        assert showing == "time" and set(before) <= set(out.order)  # a lane never goes
        label = out.lines[-1].plain.index("0")
        cells = width - label
        lanes = {i: out.lines[line].plain[label:].ljust(cells) for i, (line, _, _) in out.at.items()}
        start = datetime.fromisoformat(next(e["timestamp"] for e in rows if e["kind"] == "asked"))
        end = datetime.fromisoformat(max(e["timestamp"] for e in rows))  # the replay's clock
        per = max((end - start).total_seconds(), 60) / cells
        for e in (e for e in rows if e["kind"] in ("did", "said")):
            at = (datetime.fromisoformat(e["timestamp"]) - start).total_seconds()
            assert lanes[e["node_id"]][min(cells - 1, int(at // per))] != " ", (e, lanes[e["node_id"]])
        for i in running:  # its bar runs to now, and grows with the clock
            drawn = sum(c != " " for c in lanes[i])
            assert lanes[i].rstrip().endswith("●") and drawn >= before.get(i, 0), (i, lanes[i])
            grew.add(i)
        before = {i: sum(c != " " for c in lane) for i, lane in lanes.items()}
    assert grew == {"zero-rule", "xml-source"} and list(lanes) == ["zero-rule", "xml-source"]
    assert all("✓" in lanes[i] and lanes[i].rstrip().endswith("◆") for i in grew), lanes
    assert "|" in out.lines[1].plain and "you 2 acts" in out.note, (out.lines[1], out.note)  # alexlopez's
