# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""When something new needs you, the terminal says so: its bell and a notification with the reason, once."""

import asyncio

from cockpit_repo import ALEX, BOT, cockpit, make_plan
from cockpit_scene import scene
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board, plan
from graphene_map import settings as S
from graphene_map.cockpit.app import Cockpit
from graphene_map.cockpit.model import Question
from graphene_map.store import Store


def test_what_newly_needs_you_rings_once_with_its_reason_and_never_in_a_replay():
    async def go():
        m = scene()  # a question and a sign-off already need you: the screen shows them, unrung
        app = Cockpit(lambda previous: previous or m)
        said = []
        app.writer = said.append
        async with app.run_test(size=(100, 30)):
            app.look()
            assert said == []
            m.tasks["tests"].state, m.tasks["tests"].agent = "came back", "2"
            m.tasks["tests"].note = "the word lives in words.py,\nwhich my scope \x1b[2Jdoes not cover"
            app.look()
            app.look()  # once: the same one again rings nothing
            back = "agent 2 came back: the word lives in words.py, which my scope [2Jdoes not cover"
            assert said == [f"\a\x1b]9;graphene: {back}\a"]  # one line, and no escape of the agent's own
            m.tasks["ids"].stopped.append(("db/new.py", 99.0))
            m.questions.append(Question("q2", "Which PDF library?", "weasyprint", []))
            app.look()  # two at once: one bell, the first named (questions first, as on the rows), one more
            assert said[-1] == "\a\x1b]9;graphene: a question: Which PDF library? (and 1 more)\a"
            m.tasks["docs"].state, m.tasks["docs"].note = "came back", "it needs " + "a/" * 200 + "b.py"
            app.look()  # a reason kept whole is cut for the notification, and says so
            assert len(said[-1]) < 230 and said[-1].endswith("…\a")
            m.source = "replay"  # a replay is a recording: nothing in it is yours to answer
            m.questions.append(Question("q3", "Tabs?", "spaces", []))
            app.look()
            assert len(said) == 3

    asyncio.run(go())


def test_a_leaf_that_comes_back_rings_and_notify_off_in_the_settings_keeps_the_screen_quiet(repo):
    make_plan(repo, running=True)
    app = cockpit(repo)
    app.open_store = lambda: Store.open(repo)
    said = []

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.writer = said.append
            with Store.open(repo) as store:
                plan.release(store, "ids", BOT, "the id lives in db/models.py", wants=["db/models.py"])
            app.look()
            assert said == ["\a\x1b]9;graphene: agent 1 came back: the id lives in db/models.py\a"]
            with Store.open(repo) as store:
                S.apply(store, "notify: off\n", ALEX)
                assert S.notify(store) == "off" and "notify: off" in S.render(store)  # `graphene config`
                board.add(store, "question", "tabs or spaces?", BOT, default="spaces")
            app.look()
            assert len(said) == 1

    asyncio.run(go())
