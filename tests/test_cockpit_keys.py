# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The cockpit's keys and clicks, driven headless against a real plan: each does what its command does."""

import asyncio
import subprocess

from cockpit_repo import ALEX, BOT, cockpit, items, make_plan, node, type_in
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board, plan
from graphene_map.cockpit.app import Canvas
from graphene_map.store import Store


def drive(repo, steps, **plan_kw):
    """Run `steps(app, pilot)` in a cockpit over a plan made with these options."""
    make_plan(repo, **plan_kw)
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            await steps(app, pilot)
            await pilot.pause(0.1)

    asyncio.run(go())
    return app


def test_enter_on_a_question_takes_its_default_and_digits_pick_an_option(repo):
    async def steps(app, pilot):
        assert app.model.selected == app.model.questions[0].id
        await pilot.press("enter")

    drive(repo, steps, question=True)
    assert board.reads(items(repo)[0]) == "taken"

    async def pick(app, pilot):
        await pilot.press("1")

    other = repo / "second"
    other.mkdir()
    # a second plan in a fresh repo would need its own git: pick on the first repo's new question instead
    with Store.open(repo) as store:
        board.add(store, "question", "another?", BOT, default="no", options=[{"text": "yes"}])
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("1")

    asyncio.run(go())
    assert [board.reads(it) for it in items(repo) if it["text"] == "another?"] == ["picked"]


def test_a_answers_a_question_in_your_own_words(repo):
    async def steps(app, pilot):
        await pilot.press("a")
        await type_in(pilot, "use tabs everywhere")
        await pilot.press("enter")

    drive(repo, steps, question=True)
    assert items(repo)[0]["answer"] == "use tabs everywhere"


def test_enter_on_a_proposal_accepts_it_and_d_drops_one(repo):
    async def steps(app, pilot):
        app.model.selected = "notes"
        await pilot.press("enter")

    drive(repo, steps, proposal=True)
    assert node(repo, "notes").state != plan.PROPOSED


def test_d_drops_a_proposal(repo):
    async def steps(app, pilot):
        app.model.selected = "notes"
        await pilot.press("d")

    drive(repo, steps, proposal=True)
    assert node(repo, "notes").state in plan.GONE


def test_w_gives_a_running_agent_the_path_the_gate_stopped(repo):
    make_plan(repo, running=True)
    with Store.open(repo) as store:
        denied = {"path": "db/x.py", "how": "Write"}
        store.log_node("ids", plan._now(), "denied", BOT.name, BOT.session_id, None, denied)
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "ids"
            assert app.model.tasks["ids"].stopped
            await pilot.press("w")

    asyncio.run(go())
    assert "db/x.py" in node(repo, "ids").scope


def test_x_pulls_back_a_running_agent(repo):
    async def steps(app, pilot):
        app.model.selected = "ids"
        await pilot.press("x", "y", "enter")  # it asks first: its agent stops

    drive(repo, steps, running=True)
    assert node(repo, "ids").state != plan.RUNNING


def test_v_turns_the_lens_and_p_paints_a_folder_to_the_selected_task(repo):
    for name in ("ext/c.py", "ext/d.py", "lib/a.py", "lib/b.py"):  # two folders nobody owns
        (repo / name).parent.mkdir(exist_ok=True)
        (repo / name).write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    who = ["-c", "user.email=t@t", "-c", "user.name=T"]
    subprocess.run(["git", *who, "commit", "-qm", "more"], cwd=repo, check=True)

    async def steps(app, pilot):
        app.model.selected = "docs"
        await pilot.press("v")
        assert app.model.lens == "live"
        await pilot.press("p")
        assert app.paint_mode and app.view == "territory"
        await pilot.press("j")
        assert app.groups[app.cursor].name == "ext/"
        await pilot.press("enter")
        await pilot.press("enter")  # painted again: the folder goes back
        await pilot.press("enter")

    drive(repo, steps)
    assert node(repo, "docs").scope == ["README.md", "ext/**"]


def test_colon_runs_any_graphene_command_and_the_news_says_which(repo):
    async def steps(app, pilot):
        await pilot.press("colon")
        await type_in(pilot, "plan")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.model.latest().startswith("graphene plan")

    drive(repo, steps)


def test_a_click_on_the_default_takes_it(repo):
    async def steps(app, pilot):
        lines = app.query_one(Canvas).lines
        qid = app.model.questions[0].id  # its default is on its row, or on the line under it when it is open
        takes = [k for k, line in enumerate(lines) if any(s.action == "take" for s in line.segs)]
        y = next(k for k in takes if lines[k].row == qid)
        segs = lines[y].segs
        x = next(sum(len(s.text) for s in segs[:i]) for i, s in enumerate(segs) if s.action == "take")
        await pilot.click(Canvas, offset=(x + 1, y))

    drive(repo, steps, question=True)
    assert board.reads(items(repo)[0]) == "taken"


def test_y_takes_what_waits_as_the_cli_messages_say_and_d_drops(repo):
    async def steps(app, pilot):
        app.model.selected = "notes"
        await pilot.press("y")

    drive(repo, steps, proposal=True)
    assert node(repo, "notes").state != plan.PROPOSED


def test_capital_p_turns_plan_first_round_and_u_undoes_the_last_act(repo):
    async def steps(app, pilot):
        before = app.model.first
        await pilot.press("P")
        await pilot.pause(0.2)
        assert app.model.first != before
        await pilot.press("u")

    drive(repo, steps)
    with Store.open(repo) as store:
        assert plan.plan_first(store) == "auto" or plan.plan_first(store) in plan.FIRST


def test_s_splits_only_a_leaf_still_to_do(repo):
    async def steps(app, pilot):
        app.model.selected = "ids"
        await pilot.press("s")
        assert app.model.latest().startswith("✗ ids is running")

    drive(repo, steps, running=True)


def test_a_run_that_could_start_more_than_one_leaf_asks_first_and_one_leaf_starts_at_once(repo):
    """The README says R asks first when more than one leaf could start: the cockpit holds it to that."""
    make_plan(repo)  # ids is ready, docs waits on it: two leaves could start
    with Store.open(repo) as store:
        store.set_meta("executor", "claude -p")
    app = cockpit(repo)
    started = []

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.doer.background = lambda argv: started.append(argv)
            await pilot.press("R")
            await pilot.pause(0.3)
            assert type(app.screen).__name__ == "Ask" and not started  # it asked, and started nothing
            await type_in(pilot, "y")
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert started and started[0][0] == "run"
            started.clear()
            app.model.tasks.pop("docs")  # one leaf left that could start: no question
            await pilot.press("R")
            await pilot.pause(0.2)
            assert started and type(app.screen).__name__ != "Ask"

    asyncio.run(go())


def test_r_while_a_run_is_going_asks_to_hand_the_tasks_to_it(repo, monkeypatch):
    """Mid-run, R's line said "y and Enter start them", but the run going here is what takes them."""
    from graphene_map import run as R

    make_plan(repo)
    with Store.open(repo) as store:
        store.set_meta("executor", "claude -p")
    monkeypatch.setattr(R, "run_holding", lambda root: 4242)  # a run holds the repository
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.doer.background = lambda argv: None
            await pilot.press("R")
            await pilot.pause(0.3)
            assert type(app.screen).__name__ == "Ask" and "to the run going here" in app.screen.prompt

    asyncio.run(go())


def test_colon_ask_alone_opens_the_editor_for_a_paragraph_and_asks_what_was_written(repo, monkeypatch):
    from graphene_map import plan_text

    def editor(path):  # the person writes a paragraph under the hint line
        path.write_text(path.read_text() + "add a farewell command\nthat says goodbye\n")
        return 0

    monkeypatch.setattr(plan_text, "run_editor", editor)
    make_plan(repo)
    app = cockpit(repo)
    asked = []

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.doer.background = lambda argv: asked.append(argv)
            await pilot.press("colon")
            await type_in(pilot, "ask")
            await pilot.press("enter")
            await pilot.pause(0.3)

    asyncio.run(go())
    assert asked == [["ask", "add a farewell command\nthat says goodbye"]]


def test_r_with_a_question_under_the_cursor_starts_nothing(repo):
    started = []

    async def steps(app, pilot):
        app.doer.background = lambda argv: started.append(argv)
        assert app.model.selected == app.model.questions[0].id
        await pilot.press("r")
        assert not started and app.model.latest().startswith("select a task to run")

    drive(repo, steps, question=True)
    assert not started


def test_an_answer_goes_to_the_question_it_was_opened_on_though_the_selection_moves(repo):
    async def steps(app, pilot):
        await pilot.press("a")
        await type_in(pilot, "use tabs")
        app.model.selected = "ids"  # what a look does when something else needs you more
        await pilot.press("enter")
        await pilot.pause(0.3)

    drive(repo, steps, question=True)
    [item] = [it for it in items(repo) if it["kind"] == "question"]
    assert item["answer"] == "use tabs"


def test_colon_plan_edit_and_node_edit_hand_the_terminal_to_the_editor_as_e_does(repo):
    make_plan(repo)
    app = cockpit(repo)
    edited = []

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.edit_with = lambda argv: edited.append(argv)
            for line in ("plan edit", "node edit ids"):
                await pilot.press("colon")
                await pilot.pause(0.2)
                await type_in(pilot, line)
                await pilot.press("enter")
                await pilot.pause(0.2)

    asyncio.run(go())
    assert edited == [["plan", "edit"], ["node", "edit", "ids"]]


def test_on_the_map_enter_and_the_row_keys_run_nothing_and_say_where_they_act(repo):
    """The map draws folders, not rows: the question the screen opens on is not on it, nor the move of the
    task ←/→ picks. There ⏎ paints, in paint mode, and the keys its bar does not list run no command."""
    from graphene_map.cockpit.app import ON_THE_MAP

    ran = []

    async def steps(app, pilot):
        app.doer.run = lambda argv, done="": ran.append(argv)
        app.doer.background = lambda argv: ran.append(argv)
        first = app.model.selected
        assert first == app.model.questions[0].id  # the first row: what needs the person most
        await pilot.press("m")
        for sel in (first, "ids"):  # the question nobody sees there, then a task picked with ←/→
            app.model.selected = sel
            for key in ("enter", "d", "1", "y", "a", "x", "r", "R", "s", "u", "P", "A", "i", "colon"):
                await pilot.press(key)
                await pilot.pause(0.05)
                assert len(app.screen_stack) == 1 and app.view == "territory", (sel, key)  # nothing opened
                assert app.model.latest() == ON_THE_MAP, (sel, key)
        assert ran == []

    drive(repo, steps, question=True, running=True)
    assert board.reads(items(repo)[0]) == "open" and node(repo, "ids").state == plan.RUNNING


def test_r_on_a_task_that_came_back_asks_before_it_reopens_the_finished_task_that_has_its_path(repo):
    """r on a task that came back wanting a path a finished task wrote reopens that task, which was proven:
    the row names it, and r asks first, as x reopen does."""
    with Store.open(repo) as store:
        leaves = [{"id": "schema", "title": "The schema", "scope": ["db.py"], "check": "true"},
                  {"id": "export", "title": "export", "scope": ["export.py"], "check": "true"}]  # fmt: skip
        plan.propose(store, leaves, ALEX)
        plan.start(store, "schema", ALEX, repo)
        (repo / "db.py").write_text("tables = []\n")
        plan.finish(store, "schema", ALEX)
        plan.start(store, "export", BOT, repo)
        plan.release(store, "export", BOT, "it needs the export table in db.py", wants=["db.py"])
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "export"
            app.paint()
            assert any("r reopen schema" in line.plain() for line in app.query_one(Canvas).lines)
            await pilot.press("r")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ == "Ask" and app.screen.prompt.startswith("reopen schema? ")
            await pilot.press("escape")  # no y: the finished task stays finished
            await pilot.pause(0.2)
            assert node(repo, "schema").state == plan.DONE
            await pilot.press("r")
            await pilot.pause(0.2)
            await type_in(pilot, "y")
            await pilot.press("enter")
            await pilot.pause(0.3)

    asyncio.run(go())
    assert node(repo, "schema").state == plan.OPEN and "schema" in node(repo, "export").needs
