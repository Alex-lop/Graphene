"""What the person says while an agent works reaches it with its next call: driven through hook_main,
the one function Claude Code's hook really calls. A note of theirs, or their answer to a board
question, about the leaf a session holds comes back as the vendor's additionalContext with the next
write or shell command, once, logged as told on the leaf, and never for what the session was already
shown when it took the leaf. Not when a command ends: told there, real agents followed a note in 1 run of
12, with the next write in 12 of 14."""

import io
import json
import subprocess

import pytest

from graphene_map import board, plan
from graphene_map.hooks import hook_main
from graphene_map.plan import Caller
from graphene_map.store import Store

SID = "7e117e11-0000-4000-8000-000000000001"
ALEX = Caller("alex", True)
BOT = Caller("claude:7e117e11", False, SID)


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "src/api").mkdir(parents=True)
    (tmp_path / "src/api/users.py").write_text("def users():\n    return []\n")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")
    return tmp_path


def hook(repo, name, session=SID, **extra) -> dict | None:
    event = {"session_id": session, "cwd": str(repo), "hook_event_name": name, **extra}
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


def write(repo, rel="src/api/users.py", **extra):
    return hook(repo, "PreToolUse", tool_name="Edit", tool_input={"file_path": str(repo / rel)}, **extra)


def bash(repo, command="pytest -q"):
    return hook(repo, "PreToolUse", tool_name="Bash", tool_input={"command": command})


def ended(repo, **response):
    done = {"stdout": "1 passed\n", **response}
    command = {"command": "pytest -q"}
    return hook(repo, "PostToolUse", tool_name="Bash", tool_input=command, tool_response=done)


def said(answer) -> str:
    return answer["hookSpecificOutput"]["additionalContext"]


def holding(repo, *others):
    """A plan of n1 (held by the session) and whatever else is named, each its own leaf."""
    with Store.open(repo) as store:
        for leaf in ("n1", *others):
            node = {"id": leaf, "title": leaf, "scope": [f"src/{leaf}/**"], "check": "true"}
            plan.propose(store, [{**node, "scope": ["src/api/**"] if leaf == "n1" else node["scope"]}], ALEX)
        plan.start(store, "n1", BOT, repo)


def say(repo, words, about="n1", who=ALEX):
    with Store.open(repo) as store:
        return board.note(store, words, who, about=about)


def log(repo, kind="told"):
    with Store.open(repo) as store:
        return store.node_log("n1", (kind,))


def test_a_note_about_the_leaf_is_told_with_the_next_write_once_and_logged_as_told(repo):
    holding(repo)
    assert write(repo) is None  # nothing said yet: silence
    note = say(repo, "use 12 spaces, not 4")
    answer = write(repo)
    assert answer["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "use 12 spaces, not 4" in said(answer) and "since you took n1" in said(answer)
    assert write(repo) is None and bash(repo) is None  # once
    [row] = log(repo)
    assert row["detail"] == {"items": [note["id"]], "how": "write"}
    assert row["session_id"] == SID and row["actor"] == "claude:7e117e11"  # who held the leaf then


def test_an_answer_to_a_board_question_is_told_with_the_next_shell_command(repo):
    holding(repo)
    with Store.open(repo) as store:
        asked = board.add(store, "question", "tabs or spaces?", BOT, default="spaces", about="n1")
    assert bash(repo) is None  # a question still open is nobody's answer
    with Store.open(repo) as store:
        board.answer(store, asked["id"], "tabs, always", ALEX)
    assert "tabs or spaces? → tabs, always" in said(bash(repo))
    assert bash(repo) is None
    assert log(repo)[0]["detail"]["how"] == "shell"


def test_a_taken_default_is_told_as_an_answer_too(repo):
    holding(repo)
    with Store.open(repo) as store:
        asked = board.add(store, "question", "tabs or spaces?", BOT, default="spaces", about="n1")
        board.take(store, asked["id"], ALEX)
    assert "tabs or spaces? → spaces" in said(write(repo))


def test_what_the_session_was_shown_when_it_took_the_leaf_is_never_told_again(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "n1", "title": "n1", "scope": ["src/api/**"], "check": "true"}], ALEX)
        board.note(store, "said before the start", ALEX, about="n1")
        board.note(store, "plan-wide, before the start", ALEX)
        plan.start(store, "n1", BOT, repo)  # the contract it prints holds both
    assert write(repo) is None and bash(repo) is None and ended(repo) is None
    say(repo, "said after")
    told = said(write(repo))
    assert "said after" in told and "before the start" not in told


def test_a_note_is_told_when_it_is_about_the_leaf_a_sub_goal_above_it_or_the_whole_plan_and_no_other(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "g", "title": "g"}], ALEX)
        n1 = {"id": "n1", "title": "n1", "parent": "g", "scope": ["src/api/**"], "check": "true"}
        plan.propose(store, [n1], ALEX)
        plan.propose(store, [{"id": "n2", "title": "n2", "scope": ["src/db/**"], "check": "true"}], ALEX)
        plan.start(store, "n1", BOT, repo)
    say(repo, "about the sibling leaf", about="n2")
    assert write(repo) is None
    say(repo, "about the sub-goal", about="g")
    say(repo, "about the whole plan", about=None)
    told = said(write(repo))
    assert "about the sub-goal" in told and "about the whole plan" in told and "sibling" not in told


def test_an_agents_own_note_waits_for_the_person_and_is_not_told_to_anyone(repo):
    holding(repo)
    say(repo, "an executor's note", who=BOT)
    assert write(repo) is None and bash(repo) is None


def test_a_refused_write_does_not_carry_the_note_and_the_next_call_does(repo):
    holding(repo)
    say(repo, "keep it small")
    refused = write(repo, "src/db/schema.py")
    assert refused["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "additionalContext" not in refused["hookSpecificOutput"] and log(repo) == []
    assert "keep it small" in said(write(repo))


def test_a_note_said_while_a_command_ran_is_not_told_as_it_ends_but_with_the_next_call(repo):
    """Told as a command ended, real agents followed a note in 1 run of 12; with the next write, in 12 of 14.
    And told once at the end it could not be told again with the write: the end of a command says nothing."""
    holding(repo)
    assert bash(repo, "pytest -q") is None  # the command starts; nothing is said yet
    say(repo, "stop after the first failure")
    assert ended(repo) is None
    answer = write(repo)
    assert answer["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "stop after the first failure" in said(answer)
    assert write(repo) is None
    assert log(repo)[0]["detail"]["how"] == "write"


def test_a_command_refused_after_the_fact_says_its_reason_and_the_note_waits_for_the_next_call(repo):
    holding(repo)
    say(repo, "mind the schema")
    answer = ended(repo, bashEditDiff={"changedFiles": [str(repo / "src/db/schema.py")]})
    assert answer["decision"] == "block" and "outside the scope" in answer["reason"]
    assert "additionalContext" not in json.dumps(answer) and log(repo) == []
    assert "mind the schema" in said(write(repo))


def test_a_session_that_holds_no_leaf_is_told_nothing(repo):
    holding(repo)
    say(repo, "for the holder")
    other = hook(repo, "PreToolUse", session="someone-else", tool_name="Bash", tool_input={"command": "ls"})
    assert other is None or "for the holder" not in json.dumps(other)
    assert log(repo) == []


def test_a_leaf_made_from_a_prompt_is_not_told_the_board(repo):
    """The person is typing into that session: its prompt is the whole of what it holds."""
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "n2", "title": "n2", "scope": ["src/db/**"], "check": "true"}], ALEX)
        plan.set_plan_first(store, "off", ALEX)
    hook(repo, "UserPromptSubmit", prompt="fix the users module")
    assert write(repo) is None  # the write makes the leaf from the prompt
    with Store.open(repo) as store:
        assert [n.id for n in plan.nodes(store, (plan.RUNNING,)) if n.aside]
    say(repo, "a plan-wide note", about=None)
    assert write(repo) is None
