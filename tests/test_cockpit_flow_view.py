"""The flow screen: the plan as boxes and arrows."""

from cockpit_scene import scene

from graphene_map.cockpit import flow_view as FV
from graphene_map.cockpit import flowlayout as F
from graphene_map.cockpit.model import Task


def test_the_graph_starts_from_the_goal_with_a_box_for_each_task_and_an_arrow_for_each_need():
    nodes, edges = FV.flow_graph(scene())
    goal = nodes[0]
    assert (goal.id, goal.state, goal.label) == (FV.GOAL, "goal", "users come back with their ids")
    assert {n.id for n in nodes} == {FV.GOAL, "ids", "migrate", "tests", "docs", "schema"}
    assert {(e.a, e.b) for e in edges if e.kind == "needs"} == {("ids", "tests"), ("migrate", "tests")}
    assert {(e.a, e.b) for e in edges if e.kind == "tree"} == {(FV.GOAL, t) for t in scene().tasks}
    assert next(n for n in nodes if n.id == "ids").badge == "1"  # which agent is on it, while it runs
    assert next(n for n in nodes if n.id == "docs").badge == ""


def test_sub_goals_stand_between_the_goal_and_their_tasks_and_a_task_waiting_beside_hangs_from_it():
    m = scene()
    m.tasks["ids"].above = m.tasks["tests"].above = [("api", "the API")]
    m.tasks["migrate"].above = [("api", "the API"), ("db", "the database")]
    nodes, edges = FV.flow_graph(m)
    by_id = {n.id: n for n in nodes}
    assert (by_id["api"].label, by_id["api"].state, by_id["db"].state) == ("the API", "sub-goal", "sub-goal")
    tree = {(e.a, e.b) for e in edges if e.kind == "tree"}
    assert {(FV.GOAL, "api"), ("api", "ids"), ("api", "db"), ("db", "migrate"), (FV.GOAL, "docs")} <= tree
    drawn = {(e.a, e.b) for e in FV.drawn(edges)}
    assert ("api", "tests") in tree and ("api", "tests") not in drawn  # it waits on ids, under api with it
    assert ("ids", "tests") in drawn and ("migrate", "tests") in drawn
    m.goal = "no goal yet"  # a plan with no goal starts at what is under it
    assert FV.GOAL not in {n.id for n in FV.flow_graph(m)[0]}


def test_the_whole_graph_is_drawn_when_it_fits_and_only_a_task_is_selected_by_a_click():
    m = scene()
    m.tasks["ids"].above = [("api", "the API")]
    nodes, edges = FV.flow_graph(m)
    lines, layout, note = FV.build_flow(nodes, edges, 140, "ids")
    text = "\n".join(line.plain() for line in lines)
    assert note == "" and "users come back" in text and "the API" in text  # the goal and the sub-goal
    assert set(layout.rects) == set(m.tasks)  # an arrow key moves among these: the tasks
    actions = {s.action for line in lines for s in line.segs if s.action}
    assert actions == {f"select:{t}" for t in m.tasks}
    assert all(line.width() <= 140 for line in lines)


def test_a_graph_too_wide_for_the_terminal_shows_the_selected_tasks_neighbourhood_and_says_so():
    m = scene()
    for i in range(8):  # a chain of eight more
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    nodes, edges = FV.flow_graph(m)
    lines, layout, note = FV.build_flow(nodes, edges, 60, "c3")
    assert note.startswith("showing ") and "step 3" in note  # the task by its name, not its id
    assert "c3" in layout.rects and len(layout.rects) < len(nodes)
    assert "users come" in "\n".join(line.plain() for line in lines)  # and the goal it serves
    assert all(line.width() <= 60 for line in lines)
    _lines, _layout, note = FV.build_flow(nodes, edges, 60, "q")  # a question selected: the goal's
    assert note.startswith("showing ") and "users come back with their ids" in note


def test_a_wide_screen_gives_a_title_its_whole_line_and_80_columns_still_fit():
    m = scene()
    m.tasks["ids"].title = "Render the invoice template"  # 27 cells
    nodes, edges = FV.flow_graph(m)
    lines, _layout, _note = FV.build_flow(nodes, edges, 160, "ids")
    assert any("Render the invoice template" in line.plain() for line in lines)
    lines, _layout, note = FV.build_flow(nodes, edges, 80, "ids")
    assert note == "" and all(line.width() <= 80 for line in lines)


def test_at_80_columns_a_neighbourhood_has_the_widest_labels_that_fit_and_the_goal_whole():
    m = scene()
    m.goal = "customers get their invoices by email"
    for i in range(8):  # a chain of eight more: too wide for 80 columns whole
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    nodes, edges = FV.flow_graph(m)
    lines, _layout, note = FV.build_flow(nodes, edges, 80, "c3")
    text = "\n".join(line.plain() for line in lines)
    assert note.startswith("showing ") and "customers get their" in text and "…" not in text
    assert all(line.width() <= 80 for line in lines)


def test_a_small_plan_too_wide_for_80_columns_shows_a_neighbourhood_and_is_never_cut_at_the_edge():
    from graphene_map.cockpit.model import Model

    m = Model("customers get their invoices by email")
    titles = ["Render the invoice template", "Email the PDF", "Store when sent", "Document the mailer"]
    for i, title in enumerate(titles):  # four tasks, each waiting on the one before: five boxes with the goal
        m.tasks[f"t{i}"] = Task(f"t{i}", title, "waiting", needs=[f"t{i - 1}"] if i else [])
    nodes, edges = FV.flow_graph(m)
    _lines, layout, note = FV.build_flow(nodes, edges, 80, "t3")
    assert layout.width <= 80 and note.startswith("showing ") and "Document the mailer" in note


def test_a_plan_with_no_edges_is_laid_out_in_columns_not_one_long_column():
    nodes = [F.GNode(f"t{i}", f"task {i}") for i in range(6)]
    lines, lay, _note = FV.build_flow(nodes, [], 120, "t0")
    assert len({r[0] for r in lay.rects.values()}) == 2 and len(lines) < len(F.layout(nodes, []).cells)
    _lines, lay, _note = FV.build_flow(nodes, [], 20, "t0")  # too narrow for two: one column, as before
    assert len({r[0] for r in lay.rects.values()}) == 1


def test_a_plan_with_no_tasks_has_no_graph_and_says_so_in_one_line():
    from graphene_map.cockpit.model import Model

    assert FV.flow_graph(Model("users come back with their ids")) == ([], [])  # not a goal on its own
    lines, lay, note = FV.build_flow([], [], 80, None)
    assert [line.plain() for line in lines] == [" " + FV.EMPTY] and lines[0].width() <= 78
    assert FV.EMPTY.startswith("Nothing is planned yet") and lay.width == 0 and note == ""
