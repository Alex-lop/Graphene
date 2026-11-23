# ruff: noqa: F811  (the repo fixture imported from test_run_live is named again as an argument)
"""Two things `graphene state --json` says whole that the screen once lost: `asked`, the newest ask, which
the news cuts at 60 characters and an editor's header has the room for; and a task's `note` once the person
sent it back, their words, which the next agent is told (`plan.notes`) and the card keeps."""

from test_run_live import repo  # noqa: F401

from graphene_map import plan
from graphene_map import state as ST
from graphene_map.plan import Caller
from graphene_map.store import Store

RED = {"id": "red", "title": "red", "scope": ["a.txt"], "check": "grep -q done a.txt"}

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")
LONG = "wordkit grows three things: a --top N option, a reading time in minutes, and a\n  --json flag"


def snap(repo) -> dict:
    with Store.open(repo) as store:
        return ST.snapshot(store, repo)


def test_asked_is_the_newest_ask_whole_on_one_line_where_the_news_cuts_it(repo):
    assert snap(repo)["asked"] == ""  # nothing asked
    with Store.open(repo) as store:
        store.log_node("*", plan._now(), "asked", "alex", None, None, {"note": "an older ask", "about": None})
        store.log_node("*", plan._now(), "asked", "alex", None, None, {"note": LONG, "about": None})
    s = snap(repo)
    assert s["asked"] == " ".join(LONG.split())
    cut = next(line for line in reversed(s["news"]) if line.startswith("you asked: "))
    assert cut.endswith("…") and s["asked"].startswith(cut.removeprefix("you asked: ")[:-1])


def test_a_task_sent_back_carries_the_persons_note_until_an_agent_says_why_it_came_back(repo):
    with Store.open(repo) as store:
        plan.propose(store, [RED], ALEX)
        plan.start(store, "red", BOT, repo)
        (repo / "a.txt").write_text("done\n")
        plan.finish(store, "red", BOT)
    assert {t["id"]: t["note"] for t in snap(repo)["tasks"]} == {"red": ""}  # in review: nothing said
    with Store.open(repo) as store:
        plan.reopen(store, "red", ALEX, "the test only\ncovers one case")
    (red,) = snap(repo)["tasks"]
    assert (red["state"], red["note"], red["why"]) == ("ready", "the test only covers one case", "")
    with Store.open(repo) as store:  # its next agent hands it back: its why is the note now, not the old one
        plan.start(store, "red", BOT, repo)
        plan.release(store, "red", BOT, "it needs b.txt")
    (red,) = snap(repo)["tasks"]
    assert (red["state"], red["note"], red["why"]) == ("came back", "it needs b.txt", "it needs b.txt")
