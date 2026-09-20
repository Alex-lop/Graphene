"""What the hooks answer while a plan is in force: driven through hook_main, the one function Claude
Code's hook really calls, with the vendor's event shapes in and the vendor's JSON out."""

import io
import json
import subprocess

import pytest

from graphene_debrief import gate, plan
from graphene_debrief.plan import Caller
from graphene_debrief.sources.claude_code import hook_main
from graphene_debrief.store import Store

SID = "5e55105e-0000-4000-8000-000000000001"
ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, SID)


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "src/api").mkdir(parents=True)
    (tmp_path / "src/db").mkdir(parents=True)
    (tmp_path / "src/api/users.py").write_text("def users():\n    return []\n")
    (tmp_path / "src/db/schema.py").write_text("TABLES = []\n")
    (tmp_path / ".gitignore").write_text("build/\n")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")
    return tmp_path


def hook(repo, name, **extra) -> dict | None:
    """One hook event in, the hook's stdout out (None when it said nothing)."""
    event = {"session_id": SID, "cwd": str(repo), "hook_event_name": name, **extra}
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


def write(repo, rel, tool="Edit"):
    return hook(repo, "PreToolUse", tool_name=tool, tool_input={"file_path": str(repo / rel)})


def bash(repo, command):
    return hook(repo, "PreToolUse", tool_name="Bash", tool_input={"command": command})


def reason(answer) -> str:
    return answer["hookSpecificOutput"]["permissionDecisionReason"]


def holding(repo, **node):
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "users", "scope": ["src/api/**"], "check": "true", **node}], ALEX)
        plan.start(store, "n1", BOT, repo)


def test_without_a_plan_the_hook_says_nothing(repo):
    assert write(repo, "src/db/schema.py") is None
    assert hook(repo, "Stop") is None
    assert hook(repo, "SessionStart", source="startup") is None


def test_a_write_inside_the_scope_passes_in_silence_and_one_outside_is_refused_with_the_way_out(repo):
    holding(repo)
    assert write(repo, "src/api/users.py") is None  # silence: the person's own permission rules still apply
    assert write(repo, "src/api/new/thing.py", "Write") is None
    answer = write(repo, "src/db/schema.py")
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "src/db/schema.py is outside the scope of the node you hold (n1: src/api/**)" in reason(answer)
    assert "graphene node release n1 --why" in reason(answer) and "Only they can widen it" in reason(answer)
    with Store.open(repo) as store:
        [denied] = store.node_log("n1", ("denied",))
        assert denied["detail"] == {"path": "src/db/schema.py", "how": "Edit"}
        assert store.event_count(SID) == 0  # a call that never happened is not a recorded call


def test_a_tighter_scope_binds_the_very_next_write(repo):
    holding(repo)
    assert write(repo, "src/api/users.py") is None
    with Store.open(repo) as store:
        plan.edit(store, "n1", {"scope": ["src/api/other.py"]}, ALEX)
    assert "outside the scope" in reason(write(repo, "src/api/users.py"))


def test_with_a_plan_in_force_a_session_that_holds_no_node_writes_nothing(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "users", "scope": ["src/api/**"], "check": "true"}], ALEX)
    said = reason(write(repo, "src/api/users.py"))
    assert "holds no node" in said and "graphene node start n1" in said
    assert write(repo, "/tmp/elsewhere/notes.md") is None  # outside the repo is not the plan's business
    with Store.open(repo) as store:
        plan.edit(store, "n1", {"owner": "alex"}, ALEX)
    said = reason(write(repo, "src/api/users.py"))
    assert "no node is ready for an agent to take," in said and "propose a node for it" in said
    with Store.open(repo) as store:
        plan.set_paused(store, True, ALEX)
    assert write(repo, "src/api/users.py") is None  # paused: nothing is enforced


def test_a_finished_plan_stays_in_force_until_the_person_archives_it(repo, finish):
    """The first real agent run waited for the last node to be done, then made the edit no node
    allowed, and said so: "no node was open. Graphene accepted the write"."""
    holding(repo)
    with Store.open(repo) as store:
        finish(store, repo, "n1", BOT)
    assert "propose a node for it" in reason(write(repo, "src/db/schema.py"))
    assert "propose a node for it" in reason(bash(repo, "echo x >> src/db/schema.py"))
    assert hook(repo, "Stop") is None  # it holds nothing, so it may stop
    with Store.open(repo) as store:
        with pytest.raises(plan.Refused, match="person's to do"):
            plan.archive(store, BOT)
        assert [n.id for n in plan.archive(store, ALEX)] == ["n1"]
    assert write(repo, "src/db/schema.py") is None  # nothing left in force


def test_a_proposal_binds_nobody(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "users", "scope": ["src/api/**"], "check": "true"}], BOT)
    assert write(repo, "src/db/schema.py") is None


def test_a_stop_is_refused_while_a_node_is_held_and_allowed_once_it_is_done_or_handed_back(repo):
    holding(repo, check="grep -q 1 src/api/users.py")
    answer = hook(repo, "Stop", stop_hook_active=False)
    assert answer["decision"] == "block"
    assert "graphene node done n1" in answer["reason"] and "graphene node release n1" in answer["reason"]
    assert "`grep -q 1 src/api/users.py` passes" in answer["reason"]
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    with Store.open(repo) as store:
        plan.finish(store, "n1", BOT)
        assert [e["kind"] for e in store.node_log("n1")][-3:] == ["stop_refused", "check_passed", "finished"]
    assert hook(repo, "Stop", stop_hook_active=False) is None


def test_another_session_is_not_held_by_a_node_it_does_not_hold(repo):
    holding(repo)
    assert hook(repo, "Stop", session_id="someone-else") is None
    other = hook(
        repo,
        "PreToolUse",
        session_id="someone-else",
        tool_name="Edit",
        tool_input={"file_path": str(repo / "src/api/users.py")},
    )
    # and it cannot write into the first one's scope either
    assert "no node is ready for an agent to take (n1 is held by claude:5e55105e)" in reason(other)


@pytest.mark.parametrize(
    "command",
    [
        "cat > src/db/schema.py <<'EOF'\nTABLES = ['x']\nEOF",
        "echo x >> src/db/schema.py",
        "cd src/db && sed -i '' 's/a/b/' schema.py",
        "rm src/db/schema.py",
        "python gen.py | tee src/db/schema.py",
    ],
)
def test_a_shell_write_the_parser_can_read_is_refused_before_it_happens(repo, command):
    holding(repo)
    assert "src/db/schema.py is outside the scope" in reason(bash(repo, command))


def test_a_shell_write_inside_the_scope_or_to_an_ignored_path_or_outside_the_repo_passes(repo):
    holding(repo)
    assert bash(repo, "echo x >> src/api/users.py") is None
    assert bash(repo, "mkdir -p build && echo log > build/out.txt") is None  # .gitignore has build/
    assert bash(repo, "uv run pytest -q > /tmp/out.txt 2>&1") is None
    assert bash(repo, "git status && ls") is None


def test_an_agent_may_not_speak_as_a_person_or_touch_the_plans_store(repo):
    holding(repo)
    assert "may not carry it" in reason(
        bash(repo, "GRAPHENE_AS=person:alex graphene node set n1 --scope '**'")
    )
    assert "the plan's own store" in reason(bash(repo, "rm .graphene/graphene.db"))
    assert "the plan's own store" in reason(write(repo, ".graphene/graphene.db", "Write"))


def test_what_the_vendor_says_a_command_changed_is_refused_after_the_fact_and_logged_as_a_breach(repo):
    holding(repo)
    calls = iter(range(9))

    def after(changed, **diff):
        response = {"stdout": "", "bashEditDiff": {"changedFiles": [str(repo / c) for c in changed], **diff}}
        return hook(
            repo,
            "PostToolUse",
            tool_name="Bash",
            tool_use_id=f"toolu_{next(calls)}",
            tool_input={"command": "python rewrite.py"},
            tool_response=response,
        )

    assert after(["src/api/users.py", "build/x.o"]) is None
    assert (
        after(["src/db/schema.py"], shared=True) is None
    )  # a list another command leaked into proves nothing
    answer = after(["src/api/users.py", "src/db/schema.py"])
    assert answer["decision"] == "block" and "changed src/db/schema.py, outside the scope" in answer["reason"]
    with Store.open(repo) as store:
        assert store.node_log("n1", ("breach",))[0]["detail"] == {
            "paths": ["src/db/schema.py"],
            "how": "shell",
        }
        assert store.event_count(SID) == 3  # and the calls themselves are recorded as ever


def test_a_new_session_is_told_there_is_a_plan(repo):
    holding(repo)
    answer = hook(repo, "SessionStart", source="startup")
    assert "graphene node start" in answer["hookSpecificOutput"]["additionalContext"]


def test_a_gate_that_crashes_lets_the_call_through_says_so_in_the_log_and_still_records(repo, monkeypatch):
    holding(repo)
    monkeypatch.setattr(gate, "decide", lambda *a: 1 / 0)
    assert hook(repo, "PostToolUse", tool_name="Bash", tool_use_id="t9", tool_input={"command": "ls"}) is None
    assert "ZeroDivisionError" in (repo / ".graphene" / "ingest.log").read_text()
    with Store.open(repo) as store:
        assert store.event_count(SID) == 1


# -- what the closing review broke ---------------------------------------------------------------------


def test_the_plans_store_is_refused_before_any_scope_is_asked(repo):
    """With a scope of `**`, `rm -rf .graphene` and `echo x > .graphene/pwn` passed the hook."""
    holding(repo, scope=["**"])
    assert "the plan's own store" in reason(bash(repo, "echo pwned > .graphene/pwn"))
    assert "the plan's own store" in reason(bash(repo, "rm -rf .graphene"))
    assert "the plan's own store" in reason(bash(repo, "sqlite3 .graphene/graphene.db 'select 1'"))
    assert bash(repo, "graphene plan log > /tmp/log.txt") is None  # its own commands are how to read it


def test_a_write_through_a_symbolic_link_that_leaves_the_repo_is_refused(repo, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("original")
    holding(repo)
    (repo / "src/api/cache").symlink_to(outside)
    assert "symbolic link that leaves the repo" in reason(write(repo, "src/api/cache"))
    assert "symbolic link that leaves the repo" in reason(bash(repo, "echo OWNED > src/api/cache"))
    (repo / "src/api/store").symlink_to(repo / ".graphene")
    assert "symbolic link that leaves the repo" in reason(write(repo, "src/api/store/graphene.db", "Write"))
    assert write(repo, "src/api/users.py") is None  # an ordinary path in scope is untouched by all this


def test_a_command_too_long_to_parse_in_time_is_let_through_at_once(repo):
    import time

    holding(repo)
    start = time.perf_counter()
    assert bash(repo, "echo " + "x" * 400_000 + " > src/db/schema.py") is None
    assert time.perf_counter() - start < 1.0  # parsed, this took 1.4 s, and 3 MB took 234 s
