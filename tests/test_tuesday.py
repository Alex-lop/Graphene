# ruff: noqa: F811  (the repo fixture is imported from test_gate and named again as an argument)
"""Free on a Tuesday: with a plan in force, a small attended task costs the person nothing more than
the prompt they would have typed anyway. Driven through hook_main with the vendor's event shapes."""

import pytest
from test_gate import ALEX, SID, bash, hook, reason, repo, write  # noqa: F401  (repo is a fixture)

from graphene_debrief import plan
from graphene_debrief.plan import DONE, DROPPED, OPEN, PROPOSED, Caller
from graphene_debrief.store import Store

OTHER = Caller("claude:0ther000", False, "0ther000-session")


def in_force(repo):  # a finished plan stays in force: the state decision 4 was written for
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "users", "scope": ["src/api/**"], "check": "true"}], ALEX)


@pytest.fixture(autouse=True)
def alex(monkeypatch):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    monkeypatch.delenv("GRAPHENE_NODE", raising=False)


def context(answer) -> str:
    return answer["hookSpecificOutput"]["additionalContext"]


def test_a_prompt_typed_into_the_session_is_a_leaf_with_no_keystroke_more(repo):
    in_force(repo)
    assert hook(repo, "UserPromptSubmit", prompt="fix the typo in the schema comment") is None
    assert write(repo, "src/db/schema.py") is None  # no node held, and not refused: the prompt is the leaf
    (repo / "src/db/schema.py").write_text("TABLES = []  # fixed\n")
    with Store.open(repo) as store:
        [aside] = [n for n in plan.nodes(store) if n.aside]
        assert aside.title == "fix the typo in the schema comment" and aside.scope == ["**"]
        assert aside.state == "running" and aside.session_id == SID and aside.proposed_by == "alex"
    assert hook(repo, "Stop") is None  # the turn ends, and so does the leaf: nothing refused, nothing asked
    with Store.open(repo) as store:
        done = plan.get(store, aside.id)
        assert done.state == DONE
        assert store.node_log(done.id, ("finished",))[-1]["detail"]["changed"] == ["src/db/schema.py"]


def test_a_question_that_led_to_no_edit_leaves_no_leaf(repo):
    in_force(repo)
    hook(repo, "UserPromptSubmit", prompt="what does schema.py do?")
    assert hook(repo, "Stop") is None
    with Store.open(repo) as store:
        assert not [n for n in plan.nodes(store) if n.aside]
    hook(repo, "UserPromptSubmit", prompt="try something")
    assert write(repo, "src/db/schema.py") is None  # allowed, then the agent wrote nothing after all
    hook(repo, "Stop")
    with Store.open(repo) as store:
        assert [n.state for n in plan.nodes(store) if n.aside] == [DROPPED]


def test_scope_and_check_in_one_line_bind_like_any_leaf(repo):
    in_force(repo)
    hook(
        repo,
        "UserPromptSubmit",
        prompt="tidy the schema scope: src/db/** check: grep -q tidy src/db/schema.py",
    )
    assert write(repo, "src/db/schema.py") is None
    assert "outside the scope" in reason(write(repo, "src/api/users.py"))
    (repo / "src/db/schema.py").write_text("TABLES = []\n# changed\n")
    blocked = hook(repo, "Stop")
    assert blocked["decision"] == "block" and "grep -q tidy" in blocked["reason"]  # the check they gave
    (repo / "src/db/schema.py").write_text("TABLES = []  # tidy\n")
    assert hook(repo, "Stop") is None
    with Store.open(repo) as store:
        [aside] = [n for n in plan.nodes(store) if n.aside]
        assert aside.title == "tidy the schema" and aside.state == DONE


def test_a_session_that_holds_a_planned_leaf_is_still_held_to_it(repo):
    in_force(repo)
    hook(repo, "UserPromptSubmit", prompt="do n1")
    with Store.open(repo) as store:
        plan.start(store, "n1", Caller("claude:5e55105e", False, SID), repo)
    assert "outside the scope" in reason(write(repo, "src/db/schema.py"))


def test_no_prompt_no_leaf_and_a_runs_executor_never_gets_one(repo, monkeypatch):
    in_force(repo)
    assert "holds no node" in reason(write(repo, "src/db/schema.py"))  # nobody typed anything
    hook(repo, "UserPromptSubmit", prompt="do the node")
    monkeypatch.setenv("GRAPHENE_NODE", "n1")  # a session `graphene run` started: its prompt is Graphene's
    assert "holds no node" in reason(write(repo, "src/db/schema.py"))
    monkeypatch.delenv("GRAPHENE_NODE")
    with Store.open(repo) as store:
        store.set_meta("asides", "off")  # the person can have the 0.3 rule back
    assert "holds no node" in reason(write(repo, "src/db/schema.py"))


def test_a_shell_write_is_covered_by_the_leaf_its_prompt_made(repo):
    in_force(repo)
    hook(repo, "UserPromptSubmit", prompt="regenerate the schema")
    assert bash(repo, "echo 'T = []' > src/db/schema.py && echo x > src/db/other.py") is None


def test_yes_typed_into_the_session_accepts_what_the_session_proposed(repo):
    bot = Caller("claude:5e55105e", False, SID)
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "mine", "scope": ["src/db/**"], "check": "true"}], bot)
        plan.propose(store, [{"title": "theirs", "scope": ["src/api/**"], "check": "true"}], OTHER)
    said = context(hook(repo, "UserPromptSubmit", prompt="yes, go ahead"))
    assert "accepted n1 (mine)" in said and "graphene node start n1" in said
    with Store.open(repo) as store:
        assert plan.get(store, "n1").state == OPEN and plan.get(store, "n2").state == PROPOSED
        entry = store.node_log("n1", ("accepted",))[-1]
        assert entry["actor"] == "alex" and entry["detail"]["by"] == "prompt"
    assert "accepted n2" in context(hook(repo, "UserPromptSubmit", prompt="ok do n2"))


def test_only_a_short_yes_accepts_and_a_request_that_mentions_a_node_does_not(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "mine", "scope": ["src/db/**"], "check": "true"}], OTHER)
    for prompt in ("no, drop n1", "can you explain n1 to me?", "yes " + "and also " * 40 + "n1", "yes"):
        assert hook(repo, "UserPromptSubmit", prompt=prompt) is None  # the last: not this session's proposal
    with Store.open(repo) as store:
        assert plan.get(store, "n1").state == PROPOSED
    assert "accepted n1" in context(hook(repo, "UserPromptSubmit", prompt="accept everything"))
