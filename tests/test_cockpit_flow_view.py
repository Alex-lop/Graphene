"""The flow screen: the plan as boxes and arrows."""

from cockpit_scene import scene

from graphene_map.cockpit import flow_view as FV
from graphene_map.cockpit import flowlayout as F
from graphene_map.cockpit.model import Task


def test_the_graph_has_a_box_for_each_task_and_an_arrow_for_each_need():
    nodes, edges = FV.flow_graph(scene())
    assert {n.id for n in nodes} == {"ids", "migrate", "tests", "docs", "schema"}
    assert {(e.a, e.b) for e in edges} == {("ids", "tests"), ("migrate", "tests")}
    assert next(n for n in nodes if n.id == "ids").badge == "1"  # which agent is on it, while it runs
    assert next(n for n in nodes if n.id == "docs").badge == ""


def test_the_whole_graph_is_drawn_when_it_fits_and_every_box_selects_its_task():
    m = scene()
    nodes, edges = FV.flow_graph(m)
    lines, layout, note = FV.build_flow(nodes, edges, 140, "ids")
    assert note == "" and set(layout.rects) == {n.id for n in nodes}
    actions = {s.action for line in lines for s in line.segs if s.action}
    assert {f"select:{n.id}" for n in nodes} <= actions
    assert all(line.width() <= 140 for line in lines)


def test_a_graph_too_wide_for_the_terminal_shows_the_selected_tasks_neighbourhood_and_says_so():
    m = scene()
    for i in range(8):  # a chain of eight more
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    nodes, edges = FV.flow_graph(m)
    lines, layout, note = FV.build_flow(nodes, edges, 60, "c3")
    assert note.startswith("showing ") and "c3" in note
    assert "c3" in layout.rects and len(layout.rects) < len(nodes)
    assert all(line.width() <= 60 for line in lines)


def test_a_plan_with_no_edges_is_laid_out_in_columns_not_one_long_column():
    nodes = [F.GNode(f"t{i}", f"task {i}") for i in range(6)]
    lines, lay, _note = FV.build_flow(nodes, [], 120, "t0")
    assert len({r[0] for r in lay.rects.values()}) == 2 and len(lines) < len(F.layout(nodes, []).cells)
    _lines, lay, _note = FV.build_flow(nodes, [], 20, "t0")  # too narrow for two: one column, as before
    assert len({r[0] for r in lay.rects.values()}) == 1


def test_a_plan_with_no_tasks_has_an_empty_graph_and_g_on_it_does_not_crash():
    lines, lay, note = FV.build_flow([], [], 80, None)
    assert lines == [] and lay.width == 0 and note == ""
