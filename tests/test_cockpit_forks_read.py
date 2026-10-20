# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""Reading a hold that forked into the cockpit's model: a fork each, lettered, with its own moves and its
verdict, from the rows `graphene run --forks` writes (SPEC section 5), on a store with no engine behind it."""

from datetime import UTC, datetime, timedelta

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.cockpit.read import read
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")
SESSIONS = {"a": "aaaaaaaa-0000-4000-8000-00000000000a", "b": "bbbbbbbb-0000-4000-8000-00000000000b",
            "c": "cccccccc-0000-4000-8000-00000000000c"}  # fmt: skip
WITH = {"a": "claude", "b": "claude:opus", "c": "codex"}


def plan_of(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "ids", "title": "ids", "scope": ["api.py"], "check": "true"},
                             {"id": "docs", "title": "docs", "scope": ["README.md"], "check": "true"}],
                     ALEX)  # fmt: skip
        plan.start(store, "ids", BOT, repo)


def ago(seconds):
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def row(repo, kind, detail, seconds, fork=None, node_id="ids"):
    """A row of the run's, ``seconds`` ago; a fork's row carries its letter and its own session."""
    detail = {**detail, "fork": fork} if fork else detail
    with Store.open(repo) as store:
        store.log_node(node_id, ago(seconds), kind, "run:claude", SESSIONS.get(fork, BOT.session_id), None,
                       detail)  # fmt: skip


def forked(repo, seconds=90):
    row(repo, "forked", {"forks": ["a", "b", "c"], "of": 3, "first": False, "with": WITH,
                         "sessions": SESSIONS}, seconds)  # fmt: skip


def look(repo, previous=None, **kw):
    with Store.open(repo) as store:
        return read(store, repo, previous, **kw)


def test_a_hold_that_forked_has_a_fork_a_letter_each_with_its_own_moves_and_verdict(repo):
    plan_of(repo)
    forked(repo)
    for letter in "abc":
        row(repo, "attempt", {"attempt": 1, "of": 3}, 80, letter)
    row(repo, "did", {"attempt": 1, "tool": "Edit", "target": "api.py", "verb": "editing"}, 70, "a")
    row(repo, "did", {"attempt": 1, "tool": "Edit", "target": "api.py", "verb": "editing"}, 60, "b")
    row(repo, "did", {"attempt": 1, "tool": "Bash", "target": "pytest -q", "verb": "running"}, 50, "b")
    row(repo, "said", {"attempt": 1, "text": "the ids are strings"}, 40, "b")
    row(repo, "fork", {"of": 3, "state": "passed", "why": "", "lines": 31, "with": "claude:opus"}, 30, "b")
    row(repo, "fork", {"of": 3, "state": "gave up", "why": "it needs db/models.py", "lines": 0}, 20, "c")
    row(repo, "did", {"attempt": 1, "tool": "Read", "target": "schema.py", "verb": "reading"}, 5, "a")
    m = look(repo)
    t = m.tasks["ids"]
    a, b, c = t.forks
    assert [f.letter for f in t.forks] == ["a", "b", "c"] and t.agent == "1"  # one number, three letters
    assert (a.state, b.state, c.state) == ("running", "passed", "gave up")
    assert (b.lines, c.why) == (31, "it needs db/models.py")
    assert [e.path or e.text for e in a.events] == ["api.py", "schema.py"]  # a's own, not b's
    assert [e.kind for e in b.events] == ["edit", "run", "said"] and c.events == []
    assert m.tail(a, 1) == ["read schema.py"] and 4 <= m.quiet(a) <= 8 and 39 <= m.quiet(b) <= 43
    assert c.idle is not None and 79 <= c.idle <= 83  # its attempt began: a sign, then nothing
    assert [e.kind for e in t.events] == ["edit", "edit", "run", "said", "read"]  # all of theirs, in order
    assert list(t.touched) == ["api.py"] and 4 <= m.quiet(t) <= 8  # the union; the newest fork's quiet
    assert t.kept is None and m.tasks["docs"].forks == [] and m.tasks["docs"].kept is None


def test_a_forks_moves_are_the_ones_after_its_own_last_attempt_and_a_denied_write_is_its_by_session(repo):
    """One hold's rows after its last `attempt` row were the agent's: with forks, a's attempt 2 would have
    hidden everything b did since. Each fork has its own last attempt, and a gate's row with no letter is
    the fork's whose session wrote it."""
    plan_of(repo)
    forked(repo)
    row(repo, "attempt", {"attempt": 1, "of": 3}, 80, "a")
    row(repo, "attempt", {"attempt": 1, "of": 3}, 80, "b")
    row(repo, "did", {"attempt": 1, "tool": "Edit", "target": "old.py", "verb": "editing"}, 70, "a")
    row(repo, "did", {"attempt": 1, "tool": "Edit", "target": "api.py", "verb": "editing"}, 60, "b")
    row(repo, "fork", {"of": 3, "state": "refused", "why": "`pytest -q` failed", "lines": 9}, 50, "a")
    row(repo, "attempt", {"attempt": 2, "of": 3}, 40, "a")  # a, told its refusal, tries again
    row(repo, "did", {"attempt": 2, "tool": "Edit", "target": "api.py", "verb": "editing"}, 30, "a")
    with Store.open(repo) as store:  # the gate's row: no letter, no attempt, the fork's own session
        store.log_node("ids", ago(20), "denied", "gate", SESSIONS["b"], None, {"path": "db/x.py", "how": "w"})
    m = look(repo)
    t = m.tasks["ids"]
    a, b, c = t.forks
    assert a.state == "running" and a.why == ""  # its last fork row said refused; its attempt 2 is going
    assert [e.path for e in a.events] == ["api.py"]  # not old.py: that was its attempt 1
    assert [e.path for e in b.events] == ["api.py", "db/x.py"] and [p for p, _ in b.stopped] == ["db/x.py"]
    assert [p for p, _ in t.stopped] == ["db/x.py"] and c.events == [] and c.idle is None


def test_the_fork_kept_is_read_from_the_picked_row_in_review_and_done(repo):
    plan_of(repo)
    forked(repo)
    row(repo, "fork", {"of": 3, "state": "passed", "lines": 58}, 40, "a")
    row(repo, "fork", {"of": 3, "state": "passed", "lines": 31}, 30, "b")
    row(repo, "picked", {"fork": "b", "of": 3, "by": "graphene", "reason": "31 lines against 58"}, 10)
    with Store.open(repo) as store:
        node = plan.get(store, "ids")
        node.state = plan.REVIEW
        store.put_node(plan.to_dict(node))
    t = look(repo).tasks["ids"]
    assert t.state == "review" and t.kept == ("b", "31 lines against 58", "graphene")
    assert [f.letter for f in t.forks] == ["a", "b", "c"]  # still there: digits pick another
    with Store.open(repo) as store:
        node = plan.get(store, "ids")
        node.state, node.session_id, node.executor = plan.DONE, None, None
        store.put_node(plan.to_dict(node))
    assert look(repo).tasks["ids"].kept == ("b", "31 lines against 58", "graphene")
    with Store.open(repo) as store:  # sent back and taken again: a new hold, which has not forked
        plan.reopen(store, "ids", ALEX, "the ids should be strings")
        plan.start(store, "ids", BOT, repo)
    t = look(repo).tasks["ids"]
    assert t.state == "running" and t.forks == [] and t.kept is None


def test_the_forks_setting_is_the_models_and_unset_or_unreadable_it_is_one(repo):
    plan_of(repo)
    assert look(repo).forks == 1
    with Store.open(repo) as store:
        store.set_meta("settings:forks", "4")
    assert look(repo).forks == 4
    with Store.open(repo) as store:
        store.set_meta("settings:forks", "many")
    assert look(repo).forks == 1
