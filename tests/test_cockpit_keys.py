# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The cockpit's keys and clicks, driven headless against a real plan: each does what its command does."""

import asyncio
import subprocess

from cockpit_repo import BOT, cockpit, items, make_plan, node, type_in
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
        await pilot.press("x")

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
        y = next(k for k, line in enumerate(lines) if line.row == app.model.questions[0].id)
        segs = lines[y].segs
        x = next(sum(len(s.text) for s in segs[:i]) for i, s in enumerate(segs) if s.action == "take")
        await pilot.click(Canvas, offset=(x + 1, y))

    drive(repo, steps, question=True)
    assert board.reads(items(repo)[0]) == "taken"
