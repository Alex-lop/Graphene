# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene ask` and `graphene node split`: a planner the person names, with read-only tools, whose
only output is a proposal in the plan's text. The planner here is a script that prints what a model
would, so every ending is on purpose."""

import json
import sys

import pytest
from test_plan_cli import AGENT_ENV, person, repo, runner  # noqa: F401  (fixtures)

from graphene_map import ask as A
from graphene_map import plan
from graphene_map.cli import build
from graphene_map.plan import PROPOSED, Caller, Refused
from graphene_map.store import Store

GOOD = """
import json, os, sys
seen = {"planner": os.environ.get("GRAPHENE_PLANNER"), "prompt": sys.argv[-1]}
open(os.environ["SEEN"], "a").write(json.dumps(seen) + "\\n")
print("I read api.py and schema.py; the ids come from the users table.")
print("```plan")
print("goal: users come back with their ids")
print("- the users API  [users-api]")
print("  ? users returns ids  [ids]")
print("      scope: api.py")
print("      check: grep -q ids api.py")
print("```")
print("The schema already has an id column, so no leaf touches schema.py.")
"""

SECOND_TIME = """
import os, pathlib, sys
tries = pathlib.Path(os.environ["SEEN"])
first = not tries.exists()
tries.write_text("x")
print("```plan")
bad = "- ids  [ids]\\n    scope: api.py\\n    signoff: perhaps"
good = "? ids  [ids]\\n    scope: api.py\\n    check: true"
print(bad if first else good)
print("```")
"""


def planner(tmp_path, source, monkeypatch):
    script = tmp_path / "planner.py"
    script.write_text(source)
    monkeypatch.setenv("SEEN", str(tmp_path / "seen.jsonl"))
    return f"{sys.executable} {script}"


def test_a_planner_reads_the_repo_and_its_proposal_is_added_for_the_person_to_prune(
    repo, tmp_path, monkeypatch
):
    said = person(
        "ask", "users should come back with their ids", "--with", planner(tmp_path, GOOD, monkeypatch)
    )
    assert said.exit_code == 0, said.output
    assert "proposed ids: users returns ids" in said.stdout
    assert "the planner says:\n  I read api.py and schema.py" in said.stdout  # its prose, a line each
    assert "prune it: `graphene watch`" in said.stdout
    with Store.open(repo) as store:
        ids = plan.get(store, "ids")
        assert (ids.state, ids.parent) == (PROPOSED, "users-api") and ids.proposed_by.startswith("planner:")
        assert store.meta("goal:proposed") == "users come back with their ids"
        [asked] = store.node_log("*", ("asked",))
        assert asked["detail"]["note"] == "users should come back with their ids"  # the person's words, kept
    [seen] = [json.loads(line) for line in (tmp_path / "seen.jsonl").read_text().splitlines()]
    assert seen["planner"] == "1"  # the mark the hooks and `start` read
    assert "The person said: users should come back with their ids" in seen["prompt"]
    assert "(empty: nothing is planned yet)" in seen["prompt"]


def test_a_proposal_it_cannot_read_goes_back_to_the_planner_once(repo, tmp_path, monkeypatch):
    with Store.open(repo) as store:
        said = []
        added = A.ask(store, repo, "ids", planner(tmp_path, SECOND_TIME, monkeypatch), say=said.append)
        assert added == ["proposed ids: ids"]
        assert any("Graphene could not read the proposal: line 3: signoff is yes or no" in s for s in said)


def test_a_planner_that_proposes_nothing_adds_nothing(repo, tmp_path, monkeypatch):
    with Store.open(repo) as store:
        with pytest.raises(Refused, match="no proposal after 2 tries; nothing was added"):
            A.ask(
                store,
                repo,
                "ids",
                planner(tmp_path, "print('I would rather not')", monkeypatch),
                say=lambda _: None,
            )
        assert plan.nodes(store) == []


def test_an_agent_does_not_start_a_planner(repo, tmp_path, monkeypatch):
    said = runner.invoke(
        build(), ["ask", "ids", "--with", planner(tmp_path, GOOD, monkeypatch)], env=AGENT_ENV
    )
    assert said.exit_code == 1 and "asking a planner is the person's" in said.stderr


def test_split_asks_for_leaves_under_the_leaf(repo, tmp_path, monkeypatch):
    person("node", "add", "users returns ids", "--id", "ids", "--scope", "api.py", "--check", "true")
    source = GOOD.replace("- the users API  [users-api]", "- users returns ids  [ids]").replace(
        """print("  ? users returns ids  [ids]")""", """print("  ? the id column  [col]")"""
    )
    said = person("node", "split", "ids", "--with", planner(tmp_path, source, monkeypatch))
    assert said.exit_code == 0, said.output
    [seen] = [json.loads(line) for line in (tmp_path / "seen.jsonl").read_text().splitlines()]
    assert (
        "Split ids into smaller leaves" in seen["prompt"]
        and "ids (revision 1): users returns ids" in seen["prompt"]
    )
    with Store.open(repo) as store:
        assert plan.get(store, "col").parent == "ids"


def test_the_planner_writes_nothing_and_takes_no_leaf(repo, monkeypatch):
    person("node", "add", "users returns ids", "--id", "ids", "--scope", "api.py", "--check", "true")
    monkeypatch.setenv("GRAPHENE_PLANNER", "1")
    with Store.open(repo) as store:
        with pytest.raises(Refused, match="you are the planner"):
            plan.start(store, "ids", Caller("planner:claude", False, "p1"), repo)
    import io

    from graphene_map.hooks import hook_main

    event = {"session_id": "p1", "cwd": str(repo), "hook_event_name": "PreToolUse", "tool_name": "Write",
             "tool_input": {"file_path": str(repo / "api.py"), "content": "x"}}  # fmt: skip
    out = io.StringIO()
    hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out)
    assert (
        "you are the planner" in json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_the_proposal_is_found_in_what_a_model_prints(repo):
    fenced = "prose\n```plan\n- a  [a]\n    scope: x\n```\nmore prose\n```plan\n- b  [b]\n```\n"
    assert A.proposal_in(fenced) == "- b  [b]\n"
    assert A.proposal_in("Here is the plan:\n\n- a  [a]\n    scope: x\n") == "- a  [a]\n    scope: x\n"
    assert A.proposal_in("nothing like a plan") == ""


def test_ask_lists_the_repo_before_it_takes_the_write_lock(repo, tmp_path, monkeypatch):
    """Recheck: `graphene ask` ran `git ls-files` inside the plan's write lock, and an agent's hook that
    fired meanwhile gave up on 'database is locked' and let its write through."""
    import sqlite3

    real, locked = plan._git, []

    def asked(checkout, *args):
        db = sqlite3.connect(repo / ".graphene" / "graphene.db", timeout=0, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("ROLLBACK")
            locked.append(False)
        except sqlite3.OperationalError:
            locked.append(True)  # git is asked while the plan's write lock is held
        finally:
            db.close()
        return real(checkout, *args)

    monkeypatch.setattr(plan, "_git", asked)
    said = person("ask", "ids", "--with", planner(tmp_path, GOOD, monkeypatch))
    assert said.exit_code == 0, said.output
    assert locked and not any(locked)


# -- the recheck of the closing review: its regression tests --------------------


# Recheck 54 (fixed)
def test_a_planners_check_naming_a_path_nothing_can_make_is_warned_about_on_ask_and_accept(
    repo, tmp_path, monkeypatch
):
    source = GOOD.replace("grep -q ids api.py", "python3 -m pytest test/test_ids.py -q")
    said = person("ask", "ids", "--with", planner(tmp_path, source, monkeypatch))
    assert said.exit_code == 0 and "warning: ids's check names test/test_ids.py" in said.stderr
    assert "warning: ids's check names test/test_ids.py" in person("plan", "accept").stderr


# Recheck 61 (fixed)
def test_a_planner_with_no_vendor_mark_is_an_agent_and_not_the_person(repo):
    """With only GRAPHENE_PLANNER in its shell, a planner took a leaf and added one straight into the
    plan, and the log said the person had."""
    person("node", "add", "users returns ids", "--id", "ids", "--scope", "api.py", "--check", "true")
    planner_env = {"GRAPHENE_PLANNER": "1"}
    said = runner.invoke(build(), ["node", "start", "ids"], env=planner_env)
    assert said.exit_code == 1 and "you are the planner" in said.stderr
    text = "- divide  [div]\n    scope: api.py\n    check: true\n"
    assert runner.invoke(build(), ["plan", "propose", "-"], env=planner_env, input=text).exit_code == 0
    with Store.open(repo) as store:
        assert plan.get(store, "ids").state == "open"
        div = plan.get(store, "div")
        assert div.state == PROPOSED and div.proposed_by == "planner"


# Recheck 63 (fixed)
def test_the_default_planner_reads_and_has_none_of_the_persons_mcp_servers():
    argv = A.command_for(A.DEFAULT_PLANNER, "the prompt", "s1", False)
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob" and "--strict-mcp-config" in argv


# Recheck 64 (fixed)
def test_a_plan_block_is_found_among_the_other_blocks_a_model_prints(repo):
    block = "```plan\n? subtract  [sub]\n    scope: calc.py\n```"
    typed_first = (
        "I read calc.py:\n```python\ndef add(a, b):\n    return a + b\n```\nHere is the plan:\n" + block
    )
    untyped_after = block + "\nPrune it with:\n```\ngraphene watch\n```\n"
    for said in (typed_first, untyped_after):
        assert A.proposal_in(said) == "? subtract  [sub]\n    scope: calc.py\n"


# Recheck 66 (partly)
def test_asking_again_after_a_drop_gives_a_reused_id_a_new_one(repo, tmp_path, monkeypatch):
    assert person("ask", "ids", "--with", planner(tmp_path, GOOD, monkeypatch)).exit_code == 0
    person("node", "drop", "users-api")  # with ids under it; the prompt shows neither again
    again = person("ask", "ids, again", "--with", planner(tmp_path, GOOD, monkeypatch))
    assert again.exit_code == 0, again.output
    with Store.open(repo) as store:
        alive = [n for n in plan.nodes(store) if n.state == PROPOSED]
    assert sorted(n.title for n in alive) == ["the users API", "users returns ids"]
    assert not {"ids", "users-api"} & {n.id for n in alive}


# Recheck 73 (fixed)
def test_the_planner_is_refused_a_write_before_anything_is_accepted(repo, monkeypatch):
    """`ask` is first used on an empty plan, and there the hooks let a planner with write tools write."""
    import io

    from graphene_map.hooks import hook_main

    def told(command):
        monkeypatch.setenv("GRAPHENE_PLANNER", "1")
        event = {"session_id": "p1", "cwd": str(repo), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": command}}  # fmt: skip
        out = io.StringIO()
        hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out)
        monkeypatch.delenv("GRAPHENE_PLANNER")
        return out.getvalue()

    assert "you are the planner" in told("echo x > api.py")  # nothing planned yet
    proposal = "- ids  [ids]\n    scope: api.py\n    check: true\n"
    assert runner.invoke(build(), ["plan", "propose", "-"], env=AGENT_ENV, input=proposal).exit_code == 0
    assert "you are the planner" in told("echo x > api.py")  # a proposal only: nothing in force
