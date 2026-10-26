"""The race on screen: every row names its agent's model after the number, a forked row says how many forks
race and on what, each fork's line its state, lines, model and dollars, the graph's boxes and the replay's
news the same. A frame is a function of the model, at 80, 100 and 120 columns."""

import json

from cockpit_scene import scene
from test_cockpit_forks_rows import forked

from graphene_map.cockpit import flow_view, rows
from graphene_map.cockpit.model import Fork
from graphene_map.cockpit.replay import news


def plain(lines) -> list[str]:
    return [line.plain() for line in lines]


def lines_of(m, width, row):
    return [line for line in rows.build_cockpit(m, width) if line.row == row]


def test_a_row_names_its_agents_model_after_the_number_and_the_rows_keep_one_left_edge():
    m = scene()
    m.tasks["ids"].model, m.tasks["migrate"].model = "Nano", "Opus"
    for width in (80, 100, 120):
        lines = rows.build_cockpit(m, width)
        assert all(line.width() <= width for line in lines)
        first = {}
        for line in lines:
            first.setdefault(line.row, line.plain())
        assert "● 1  Nano  users return ids" in first["ids"]
        assert "◆ 2  Opus  migrate old ids" in first["migrate"]
        assert "◌          tests for ids" in first["tests"]  # no agent, no model: the columns stay empty
        words = (("q", "Keep old ids"), ("ids", "users return"), ("docs", "docs for"), ("tests", "tests for"))
        assert len({first[row].index(said) for row, said in words}) == 1, first  # one left edge
    [model] = [s for s in lines_of(m, 80, "ids")[0].segs if s.text.startswith("Nano")]
    assert "grey62" in model.style  # the model is a fact of the row, not a state


def test_a_plan_where_no_task_names_a_model_keeps_todays_rows():
    m = scene()
    assert rows.model_col(m) == 0
    assert "● 1  users return ids" in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_a_long_model_name_is_cut_to_the_columns_most_and_the_stand_ins_fits_whole():
    m = scene()
    m.tasks["ids"].model = "stand-in-Nano"
    assert "1  stand-in-Nano  users return ids" in "\n".join(plain(rows.build_cockpit(m, 80)))
    m.tasks["ids"].model = "a-model-name-longer-than-the-column"
    row = lines_of(m, 80, "ids")[0].plain()
    assert "a-model-name-" in row and "…" in row and len(row) <= 80


def test_a_forked_row_says_how_many_forks_race_and_on_which_models():
    m = forked()
    ids = m.tasks["ids"]
    for f, model in zip(ids.forks, ("Nano", "Nano", "Nano"), strict=True):
        f.model = model
    for width in (80, 100, 120):
        row = lines_of(m, width, "ids")[0]
        [said] = [s for s in row.segs if "3 forks" in s.text]
        assert said.text.startswith("3 forks · Nano ×3") and said.style.startswith(rows.RUNNING)
        assert all(line.width() <= width for line in rows.build_cockpit(m, width))
    ids.forks[2].model = "Super"
    assert "3 forks · Nano, Nano, Super" in lines_of(m, 120, "ids")[0].plain()
    assert "…" in lines_of(m, 80, "ids")[0].plain().split("✎")[0]  # at 80 the list is cut to a third of a row
    ids.forks[1].model = ""
    assert "3 forks · Nano, ?, Super" in lines_of(m, 120, "ids")[0].plain()
    for f in ids.forks:
        f.model = "stand-in-Nano"
    assert "3 forks · stand-in-Nano ×3  ✎" in lines_of(m, 80, "ids")[0].plain()  # the demo's, whole at 80


def test_each_forks_line_carries_its_state_lines_model_and_dollars():
    m = forked()
    ids = m.tasks["ids"]
    a, b, c = ids.forks
    a.model, b.model, c.model = "Nano", "Nano", "Super"
    a.usd, b.usd, c.usd = 0.0012, 0.002, 0.0151
    b.lines = 4
    for width in (80, 100, 120):
        mine = lines_of(m, width, "ids")
        assert all(line.width() <= width for line in mine)
        said = [line.plain().split("┊ ", 1)[1].rstrip() for line in mine[1:] if "┊" in line.plain()]
        assert said[0].startswith("1a Nano ") and "✎1  $0.0012  " in said[0]
        assert said[0].endswith("read tests/util.py")
        assert said[1] == "1b Nano ✓ passed · 4 lines · $0.0020"  # dollars as every bill spells them
        assert said[2].startswith("1c Super ↩ gave up · $0.02: it needs db/models.py")
    for c.usd in (None, 0.00003):  # nothing metered, or too little to show at four places: no $0.0000
        mine = lines_of(m, 120, "ids")
        under = [line.plain().split("┊ ", 1)[1].rstrip() for line in mine[1:] if "┊" in line.plain()]
        assert under[2] == "1c Super ↩ gave up: it needs db/models.py and the schema"
    m.tasks["ids"].usd = 0.00003
    assert "$" not in lines_of(m, 120, "ids")[0].plain()


def test_a_running_row_says_what_it_has_cost_where_the_row_has_room():
    m = scene()
    m.tasks["ids"].usd = 0.0042
    assert "$0.0042" in lines_of(m, 100, "ids")[0].plain() and "$0.0042" in lines_of(m, 120, "ids")[0].plain()
    assert "$" not in lines_of(m, 80, "ids")[0].plain()  # at 80 the title keeps its room
    m.tasks["ids"].usd = 1.5
    assert "$1.50" in lines_of(m, 100, "ids")[0].plain()


def test_the_graphs_box_carries_the_model_beside_the_agents_number():
    m = scene()
    ids = m.tasks["ids"]
    assert flow_view.badge(ids) == "1"
    ids.model = "Nano"
    assert flow_view.badge(ids) == "1 Nano"
    ids.forks = [Fork("a", model="Nano"), Fork("b", model="Nano"), Fork("c", model="Nano")]
    assert flow_view.badge(ids) == "1 ×3 Nano"
    ids.model = ""  # the forks differ: the row's forks line says each, the box only how many
    assert flow_view.badge(ids) == "1 ×3"
    m.tasks["tests"].model = "Nano"  # no agent yet: no badge for a model to follow
    assert flow_view.badge(m.tasks["tests"]) == ""


def row(node, kind, **detail):
    return {"node_id": node, "kind": kind, "detail": json.dumps(detail)}


def test_the_news_names_a_forks_model_when_the_replay_knows_it():
    titles, names = {"greet": "greet says hello"}, {"greet": "1"}
    models = {"greet": {"a": "Nano", "b": "Nano"}}
    line = {"node_log": [row("greet", "fork", fork="b", of=3, state="passed", lines=4, attempts=1),
                         row("greet", "fork", fork="a", of=3, state="gave up", why="it needs words.py",
                             attempts=1),
                         row("greet", "did", verb="editing", target="app.py", fork="c")]}  # fmt: skip
    said = ("agent 1b (Nano): its check passed, 4 lines · agent 1a (Nano): gave up: it needs words.py · "
            "agent 1c: editing app.py")  # c's model is not known yet: as before
    assert news(line, titles, names, models) == said
    assert "(Nano)" not in news(line, titles, names)  # no models told: as before
    line = {"node_log": [row("greet", "picked", fork="b", of=3, by="graphene", reason="4 lines against 6")]}
    assert news(line, titles, names, models) == "greet says hello kept b: 4 lines against 6"
