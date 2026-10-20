"""The flow screen: the plan as boxes and arrows, flowing into the goal at the right."""

from cockpit_scene import scene

from graphene_map.cockpit import flow_view as FV
from graphene_map.cockpit import flowlayout as F
from graphene_map.cockpit.model import Task


def test_the_graph_has_a_box_for_each_task_an_arrow_for_each_need_and_the_goal_last_where_the_rest_arrive():
    g = FV.flow_graph(scene())
    goal = g.nodes[0]
    assert (goal.id, goal.state, goal.label) == (FV.GOAL, "goal", "users come back with their ids")
    assert goal.badge == "1 of 5"  # how many are done, on its border
    assert {n.id for n in g.nodes} == {FV.GOAL, "ids", "migrate", "tests", "docs", "schema"}
    assert {(e.a, e.b) for e in g.edges if e.b != FV.GOAL} == {("ids", "tests"), ("migrate", "tests")}
    assert {e.a for e in g.edges if e.b == FV.GOAL} == {"tests", "docs", "schema"}  # what nothing waits on
    assert g.wave[FV.GOAL] == 2 and [g.wave[t] for t in ("ids", "tests")] == [0, 1]  # the goal: last column
    chain = {(e.a, e.b) for e in g.edges if e.double}
    assert chain == {("ids", "tests"), ("tests", FV.GOAL)}  # the longest chain into the goal
    assert g.heads == ["wave 1 · 4 tasks", "wave 2 · 1 task", "goal"] and g.lanes == []
    assert next(n for n in g.nodes if n.id == "ids").badge == "1"  # which agent is on it, as its row says
    assert next(n for n in g.nodes if n.id == "docs").badge == ""  # nobody has taken it yet


def test_a_wave_is_named_by_its_agents_once_every_task_in_it_has_one():
    m = scene()
    for t in m.tasks.values():
        t.agent = t.agent or "5"
    assert FV.flow_graph(m).heads == ["wave 1 · 4 agents", "wave 2 · agent 5", "goal"]


def test_a_box_keeps_its_agents_number_in_every_state_and_a_state_change_moves_no_box():
    """A box carried its agent's number only while it ran, so the ↩ box had none while the bell, the row and
    the map said agent 3; and a number wider than the box's least room made the box wider as it appeared."""
    m = scene()
    m.tasks["docs"].state, m.tasks["docs"].title = "ready", "docs"  # nobody on it yet: no number
    before = FV.build_flow(FV.flow_graph(m), 120, "ids")[1].rects
    for state in ("running", "came back", "review", "done"):
        m.tasks["docs"].state, m.tasks["docs"].agent = state, "100"  # a hundredth agent: wider than "docs"
        g = FV.flow_graph(m)
        assert next(n for n in g.nodes if n.id == "docs").badge == "100"
        lay = FV.build_flow(g, 120, "ids")[1]
        x0, _y0, x1, y1 = lay.rects["docs"]
        assert lay.rects == before and " 100 " in "".join(c for c, _ in lay.cells[y1][x0 : x1 + 1])


def test_a_forked_tasks_box_says_how_many_agents_are_on_it_until_one_is_kept():
    m = scene()
    m.tasks["ids"].forks = ["a", "b", "c"]  # the rows' field: three forks of agent 1's hold, running
    lay = FV.build_flow(FV.flow_graph(m), 120, "docs")[1]
    x0, _y0, x1, y1 = lay.rects["ids"]
    assert "┗━ 1 ×3 ━" in "".join(c for c, _ in lay.cells[y1][x0 : x1 + 1])  # on its running border
    for state in ("review", "done", "came back"):  # one kept, or none passed: its agent's number alone
        m.tasks["ids"].state = state
        assert next(n for n in FV.flow_graph(m).nodes if n.id == "ids").badge == "1"


def test_a_box_has_its_states_mark_on_its_border_as_its_row_has_it_yours_too():
    m = scene()
    m.tasks["docs"].state = "yours"  # its row's ◇: on the graph it had no mark, in a review box's purple
    lay = FV.build_flow(FV.flow_graph(m), 120, "ids")[1]
    x0, y0, x1, _y1 = lay.rects["docs"]
    assert "".join(c for c, _ in lay.cells[y0][x0 : x1 + 1]).startswith("╭─◇─")


def test_sub_goals_are_lanes_with_their_tasks_counted_and_a_nested_one_named_by_its_parent():
    m = scene()
    m.tasks["ids"].above = m.tasks["tests"].above = [("api", "the API")]
    m.tasks["migrate"].above = [("api", "the API"), ("db", "the database")]
    g = FV.flow_graph(m)
    assert [(lane.id, lane.label, lane.note) for lane in g.lanes] == [
        ("api", "the API", "0 of 2"), ("db", "the API › the database", "0 of 1"),
    ]  # fmt: skip
    assert {n.id: n.lane for n in g.nodes} == {
        FV.GOAL: "", "ids": "api", "tests": "api", "migrate": "db", "docs": "", "schema": "",
    }  # fmt: skip
    m.tasks["ids"].state = m.tasks["tests"].state = "done"
    assert FV.flow_graph(m).lanes[0].note == "2 of 2 ✓"
    m.goal = "no goal yet"  # a plan with no goal has no goal box, and no chain into one
    g = FV.flow_graph(m)
    assert FV.GOAL not in {n.id for n in g.nodes} and FV.GOAL not in {e.b for e in g.edges}
    assert not any(e.double for e in g.edges) and g.heads == ["wave 1 · 4 tasks", "wave 2 · 1 task"]


def test_the_whole_graph_is_drawn_when_it_fits_and_only_a_task_is_selected_by_a_click():
    m = scene()
    m.tasks["ids"].above = [("api", "the API")]
    lines, layout, note = FV.build_flow(FV.flow_graph(m), 140, "ids")
    text = "\n".join(line.plain() for line in lines)
    assert note == "" and "users come back" in text and "── the API " in text  # the goal's box, the lane
    assert "wave 1 · 4 tasks" in lines[0].plain() and "goal" in lines[0].plain()  # the headers, on top
    assert set(layout.rects) == set(m.tasks)  # an arrow key moves among these: the tasks
    actions = {s.action for line in lines for s in line.segs if s.action}
    assert actions == {f"select:{t}" for t in m.tasks}
    assert all(line.width() <= 140 for line in lines)


def test_a_graph_too_wide_for_the_terminal_shows_the_selected_tasks_neighbourhood_and_says_so():
    m = scene()
    for i in range(8):  # a chain of eight more
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    g = FV.flow_graph(m)
    lines, layout, note = FV.build_flow(g, 60, "c3")
    assert note.startswith("showing ") and "step 3" in note  # the task by its name, not its id
    assert "c3" in layout.rects and len(layout.rects) < len(g.nodes)
    text = "\n".join(line.plain() for line in lines)
    assert "users come" in text and "wave 5" in lines[0].plain()  # the goal it flows into; the plan's waves
    assert all(line.width() <= 60 for line in lines)
    _lines, _layout, note = FV.build_flow(g, 60, "q")  # a question selected: the goal's
    assert note.startswith("showing ") and "users come back with their ids" in note


def test_a_question_selected_on_a_graph_too_wide_shows_the_goal_and_what_flows_into_it_and_it_fits():
    m = scene()  # every task under the goal, eight of them in a row: the goal is a step from each
    for i in range(8):
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    _lines, layout, note = FV.build_flow(FV.flow_graph(m), 80, "q")
    assert layout.width <= 80 and layout.hidden > 0 and note.startswith("showing ")


def test_a_question_selected_in_a_plan_with_no_goal_centres_a_graph_too_wide_on_its_first_box():
    for over in ([], [("api", "the API")]):  # under nothing, or under a sub-goal, which is no box
        m = scene()
        m.goal = "no goal yet"
        for i in range(8):
            m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=[f"c{i - 1}" if i else "ids"])
        for t in m.tasks.values():
            t.above = over
        _lines, layout, note = FV.build_flow(FV.flow_graph(m), 80, "q")  # no goal to centre on: the first
        assert layout.width <= 80 and note.startswith("showing ") and "users return ids" in note


def test_the_line_under_a_neighbourhood_keeps_how_far_it_reaches_at_80_columns_when_the_goal_is_long():
    from rich.cells import cell_len

    m = scene()
    m.goal = "Customers get their invoices by email every month, and every invoice sent is kept for support"
    for i in range(8):
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    _lines, _layout, note = FV.build_flow(FV.flow_graph(m), 80, "q")
    assert note.startswith("showing ") and "Customers get their" in note
    assert note.endswith(("within 2 steps", "within 1 step"))
    assert cell_len(" " + note) <= 80  # the screen draws it after one space


def test_under_a_sub_goal_in_a_sub_goal_a_neighbourhood_at_80_columns_still_shows_what_waits_on_the_task():
    m = scene()
    titles = ["log in", "refresh tokens", "log out", "audit log", "rate limit", "api keys"]  # a chain of six
    over = [("api", "API"), ("auth", "Auth")]
    for i, title in enumerate(titles):
        m.tasks[f"a{i}"] = Task(f"a{i}", title, "waiting", needs=[f"a{i - 1}"] if i else [], above=over)
    lines, layout, note = FV.build_flow(FV.flow_graph(m), 80, "a1")
    assert note.startswith("showing ") and {"a0", "a1", "a2"} <= set(layout.rects)
    assert layout.width <= 80  # log out, which waits on it, is not cut off at the right
    assert any(line.plain().startswith("── API › Auth ") for line in lines)  # its lane, with the one over it


def test_a_wide_screen_gives_a_title_its_whole_line_and_80_columns_still_fit():
    m = scene()
    m.tasks["ids"].title = "Render the invoice template"  # 27 cells
    g = FV.flow_graph(m)
    lines, _layout, _note = FV.build_flow(g, 160, "ids")
    assert any("Render the invoice template" in line.plain() for line in lines)
    lines, _layout, note = FV.build_flow(g, 80, "ids")
    assert note == "" and all(line.width() <= 80 for line in lines)


def test_at_80_columns_a_neighbourhood_has_the_widest_labels_that_fit_and_the_goal_whole():
    m = scene()
    m.goal = "customers get their invoices by email"
    for i in range(8):  # a chain of eight more: too wide for 80 columns whole
        m.tasks[f"c{i}"] = Task(f"c{i}", f"step {i}", "waiting", needs=["ids"] if i == 0 else [f"c{i - 1}"])
    lines, _layout, note = FV.build_flow(FV.flow_graph(m), 80, "c3")
    text = "\n".join(line.plain() for line in lines)
    assert note.startswith("showing ") and "customers get their" in text and "…" not in text
    assert all(line.width() <= 80 for line in lines)


def test_a_small_plan_too_wide_for_80_columns_shows_a_neighbourhood_and_is_never_cut_at_the_edge():
    from graphene_map.cockpit.model import Model

    m = Model("customers get their invoices by email")
    titles = ["Render the invoice template", "Email the PDF", "Store when sent", "Document the mailer"]
    for i, title in enumerate(titles):  # four tasks, each waiting on the one before: five boxes with the goal
        m.tasks[f"t{i}"] = Task(f"t{i}", title, "waiting", needs=[f"t{i - 1}"] if i else [])
    _lines, layout, note = FV.build_flow(FV.flow_graph(m), 80, "t3")
    assert layout.width <= 80 and note.startswith("showing ") and "Document the mailer" in note


def test_a_plan_with_no_edges_is_laid_out_in_columns_not_one_long_column():
    nodes = [F.GNode(f"t{i}", f"task {i}") for i in range(6)]
    lines, lay, _note = FV.build_flow(FV.Graph(nodes), 120, "t0")
    assert len({r[0] for r in lay.rects.values()}) == 2 and len(lines) < len(F.layout(nodes, []).cells)
    _lines, lay, _note = FV.build_flow(FV.Graph(nodes), 20, "t0")  # too narrow for two: one column, as before
    assert len({r[0] for r in lay.rects.values()}) == 1


def test_a_plan_with_no_tasks_has_no_graph_and_says_so_in_one_line():
    from graphene_map.cockpit.model import Model

    assert FV.flow_graph(Model("users come back with their ids")) == FV.Graph()  # not a goal on its own
    lines, lay, note = FV.build_flow(FV.Graph(), 80, None)
    assert [line.plain() for line in lines] == [" " + FV.EMPTY] and lines[0].width() <= 78
    assert FV.EMPTY.startswith("Nothing is planned yet") and lay.width == 0 and note == ""
