"""The cockpit's model, built by hand: the order of rows, the scoreboard, and the numbers on a row."""

from graphene_map.cockpit.model import Ev, Model, Question, Task


def model() -> Model:
    m = Model("users come back with their ids")
    m.clock = 100.0
    m.files = [f"models/m{i}.py" for i in range(5)] + [f"api/a{i}.py" for i in range(3)]
    for t in (
        Task("done1", "schema", "done"),
        Task("run1", "ids", "running", ["models/**"]),
        Task("rev1", "migrate", "review"),
        Task("back1", "docs", "came back"),
        Task("wait1", "tests", "waiting", ["api/**"], ["run1"]),
        Task("prop1", "notes", "proposed"),
    ):
        m.tasks[t.id] = t
    m.questions = [Question("q1", "Keep old ids working?", "keep both", ["keep both", "drop old"])]
    return m


def test_rows_run_from_what_needs_the_person_down_to_what_is_done():
    m = model()
    assert [rid for _, rid in m.order()] == ["q1", "rev1", "back1", "prop1", "run1", "wait1", "done1"]
    assert m.order()[0][0] == "question"


def test_the_scoreboard_counts_need_running_and_proven_with_folded_tasks_in_the_total():
    m = model()
    assert m.scoreboard() == (4, 1, 1, 6)  # a question, a review, a came-back, a proposal: all wait on you
    m.folded_done = 4
    assert m.scoreboard() == (4, 1, 5, 10)


def test_a_running_task_with_a_write_the_gate_stopped_needs_you_and_sorts_with_what_does():
    m = model()
    m.tasks["run1"].stopped = [("db/x.py", 99.0)]  # only the person can widen its scope
    assert m.scoreboard() == (5, 1, 1, 6)  # and it is still running
    assert [rid for _, rid in m.order()] == ["q1", "run1", "rev1", "back1", "prop1", "wait1", "done1"]


def test_allowed_counts_the_tracked_files_a_scope_covers():
    m = model()
    assert m.allowed(m.tasks["run1"]) == 5 and m.allowed(m.tasks["wait1"]) == 3
    assert m.allowed(m.tasks["prop1"]) == 0  # no scope, no files


def test_pace_is_a_sparkline_of_recent_events_and_quiet_is_the_time_since_the_last_one():
    m = model()
    t = m.tasks["run1"]
    t.events = [Ev(m.clock - 2, "edit", path="models/m0.py"), Ev(m.clock - 3, "read", path="models/m1.py")]
    spark = m.pace(t)
    assert len(spark) == 12 and spark[-1] != "▁" and spark[0] == "▁"
    assert m.quiet(t) == 2
    assert m.quiet(m.tasks["wait1"]) == 0  # nothing happened: it is not quiet, it has not begun


def test_the_tail_names_what_the_agent_did_in_words():
    m = model()
    t = m.tasks["run1"]
    t.events = [Ev(1, "read", path="a.py"), Ev(2, "edit", path="b.py"), Ev(3, "stop", path="db/c.py")]
    assert m.tail(t, 2) == ["edit b.py", "stopped db/c.py"]


def test_a_task_keeps_its_agents_number_between_looks_and_two_tasks_differ():
    m = model()
    first = m.agent_name("task-a")
    assert m.agent_name("task-a") == first and m.agent_name("task-b") != first


def test_a_glob_that_matches_no_tracked_file_is_a_file_still_to_be_made_and_counts_one_allowed():
    m = model()
    t = Task("new", "new test", "running", ["models/**", "tests/test_new.py", "!models/m0.py"])
    m.tasks["new"] = t
    assert m.allowed(t) == 4 + 1  # four models files (m0 taken out), and the test file still to come
