"""The rows of a task whose hold forked: `3 forks` where one agent's pace goes, a line a fork when the row is
open, and the fork kept under the row once one landed. A frame is a function of the model, at 80 and 120."""

from cockpit_scene import scene

from graphene_map.cockpit import rows
from graphene_map.cockpit.look import SPARK
from graphene_map.cockpit.model import Ev, Fork


def plain(lines) -> list[str]:
    return [line.plain() for line in lines]


def forked():
    """The scene's running task (agent 1), forked three ways: a works on, b passed, c gave up."""
    m = scene()
    ids = m.tasks["ids"]
    a = Fork("a", events=[Ev(60, "edit", path="models/m0.py"), Ev(95, "read", path="tests/util.py")],
             touched={"models/m0.py": 60.0}, started=50.0, idle=5.0)  # fmt: skip
    b = Fork("b", "passed", lines=31, events=[Ev(70, "edit", path="models/m1.py")],
             touched={"models/m1.py": 70.0}, started=50.0, idle=30.0)  # fmt: skip
    c = Fork("c", "gave up", why="it needs db/models.py and the schema", started=50.0, idle=40.0)
    ids.forks = [a, b, c]
    ids.events = sorted([*a.events, *b.events], key=lambda e: e.t)
    ids.touched = {**a.touched, **b.touched}
    ids.stopped = []
    return m


def lines_of(m, width, row="ids"):
    return [line for line in rows.build_cockpit(m, width) if line.row == row]


def test_a_forked_task_says_how_many_forks_where_its_pace_went_and_a_line_a_fork_when_open():
    for width in (80, 120):
        m = forked()
        mine = lines_of(m, width)
        assert all(line.width() <= width for line in rows.build_cockpit(m, width))
        row = mine[0]
        [forks] = [s for s in row.segs if "3 forks" in s.text]
        assert forks.style.startswith(rows.RUNNING)  # in the pace's place, in its colour: no pace on the row
        assert not any(c in row.plain() for c in SPARK)
        assert "✎2/9" in row.plain()  # the union of what the forks touched, of what the task may
        said = [line.plain().split("┊ ", 1)[1].rstrip() for line in mine[1:] if "┊" in line.plain()]
        assert said[0].startswith("1a ") and "✎1" in said[0] and said[0].endswith("read tests/util.py")
        assert said[1] == "1b ✓ passed · 31 lines"
        assert said[2].startswith("1c ↩ gave up: it needs db/models.py") and len(said) == 3
        assert any("t tell" in line.plain() and "x hand back" in line.plain() for line in mine)
        assert sum("models/m0.py" in line.plain() for line in mine) == 0  # a's moves are on its own line


def test_a_forks_line_has_its_pace_in_the_running_amber_and_says_how_long_it_has_been_quiet():
    m = forked()
    [a] = [line for line in lines_of(m, 100) if "┊ 1a " in line.plain()]
    [pace] = [s for s in a.segs if any(c in SPARK for c in s.text)]
    assert pace.style.startswith(rows.RUNNING) and len(pace.text.strip()) == 6  # shorter than the row's
    assert "⏸" not in a.plain()
    m.tasks["ids"].forks[0].idle = 41.0
    [a] = [line for line in lines_of(m, 100) if "┊ 1a " in line.plain()]
    assert "⏸41s" in a.plain() and a.plain().rstrip().endswith("read tests/util.py")


def test_a_forked_task_that_is_not_selected_shows_the_newest_forks_move_with_its_letter():
    m = forked()
    m.selected = "docs"
    mine = lines_of(m, 100)
    assert len(mine) == 2 and mine[1].plain().split("┊ ", 1)[1].rstrip() == "1a read tests/util.py"
    assert "3 forks" in mine[0].plain()


def test_once_a_fork_is_kept_the_row_is_review_or_done_as_today_and_a_dim_line_says_which_and_why():
    for width in (80, 120):
        m = forked()
        ids = m.tasks["ids"]
        ids.state, ids.passed, ids.checks = "review", 1, 2
        ids.forks[0].state, ids.forks[0].lines = "passed", 58
        ids.kept = ("b", "passes a's tests (a fails b's) · 31 lines against 58", "graphene")
        assert all(line.width() <= width for line in rows.build_cockpit(m, width))
        mine = plain(lines_of(m, width))
        under = [line.split("┊ ", 1)[1].rstrip() for line in mine[1:] if "┊" in line]
        assert "⏎ sign off" in mine[0] and "forks" not in mine[0]
        assert under[0] == "kept b · passes a's tests (a fails b's) · 31 lines against 58"
        assert under[1] == "1a ✓ passed · 58 lines" and under[2] == "1b ✓ passed · 31 lines"
        [keys] = [line for line in mine if "x reopen" in line]
        assert "1-3 pick" in keys and "i details" in keys
        m.selected = "docs"  # not open: the row and the kept line, nothing more
        assert [line.split("┊ ", 1)[1][:6] for line in plain(lines_of(m, width))[1:]] == ["kept b"]
        ids.state, ids.kept = "done", ("b", "", "person")
        assert plain(lines_of(m, width))[1].split("┊ ", 1)[1].rstrip() == "kept b · your pick"


def test_the_cockpit_stays_light_at_80_columns_with_a_forked_agent_open():
    tokens = " ".join(plain(rows.build_cockpit(forked(), 80))).split()
    words = sum(1 for t in tokens if any(c.isalnum() for c in t))
    assert words <= 110, words
