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


def test_without_a_plan_the_hook_refuses_nothing_and_a_new_session_learns_the_text(repo):
    assert write(repo, "src/db/schema.py") is None
    assert hook(repo, "Stop") is None
    taught = hook(repo, "SessionStart", source="startup")["hookSpecificOutput"]["additionalContext"]
    assert "graphene plan propose - <<'EOF'" in taught and "scope:" in taught
    assert "A plan is in force here" not in taught


def test_the_word_ingest_in_a_reason_is_not_running_the_hook(repo):
    """Three hand-backs on 22 September were refused for naming ingest/__init__.py in their reason."""
    holding(repo)
    reason = "graphene node release n1 --why 'READERS lives in ingest/__init__.py, outside my scope'"
    assert hook(repo, "PreToolUse", tool_name="Bash", tool_input={"command": reason}) is None
    for forged in (
        "graphene ingest hook < e.json",
        "echo {} | graphene  ingest hook",
        "python -m graphene_debrief.cli ingest hook",
    ):
        refused = hook(repo, "PreToolUse", tool_name="Bash", tool_input={"command": forged})
        assert "not an agent's to run" in refused["hookSpecificOutput"]["permissionDecisionReason"]


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


# -- a paragraph becomes a tree before any code ----------------------------------------------------------

PARAGRAPH = (
    "Look at this repo. I want the new Northwind XML feed to load the same way csv and json already do: "
    "same load command, same JSONL out. Prices in that feed are already in cents. The summary line at the "
    "end is not a product. A price of 0 means skip it, for every supplier."
)


def test_a_paragraph_is_asked_for_a_tree_and_its_writes_wait_even_with_no_plan_yet(repo):
    told = hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)["hookSpecificOutput"]["additionalContext"]
    assert "becomes a tree before any code" in told and "graphene plan propose -" in told
    refused = write(repo, "ingest/xmlfeed.py")
    assert "becomes a tree before any code" in refused["hookSpecificOutput"]["permissionDecisionReason"]
    heredoc = "graphene plan propose - <<'EOF'\n- a  [a]\n    scope: x\n    check: true\nEOF"
    assert hook(repo, "PreToolUse", tool_name="Bash", tool_input={"command": heredoc}) is None
    assert hook(repo, "PreToolUse", tool_name="Read", tool_input={"file_path": str(repo / "x")}) is None


def test_a_line_and_a_paragraph_that_says_just_do_it_are_done_at_once(repo):
    assert hook(repo, "UserPromptSubmit", prompt="fix the typo in the README header") is None
    assert write(repo, "README.md") is None
    assert hook(repo, "UserPromptSubmit", prompt=PARAGRAPH + " Just do it, no plan.") is None
    assert write(repo, "ingest/xmlfeed.py") is None


def test_what_the_vendor_sends_as_a_prompt_is_never_the_persons_paragraph(repo):
    """A long background-task notification was read as a paragraph in the session that built this."""
    notice = "<task-notification>\n<task-id>b3a0</task-id>\n<status>completed</status>\n" + "x" * 300
    assert hook(repo, "UserPromptSubmit", prompt=notice) is None
    assert hook(repo, "UserPromptSubmit", prompt="[SYSTEM NOTIFICATION] " + "y" * 300) is None
    assert write(repo, "ingest/xmlfeed.py") is None


# -- the recheck of the closing review: what the paragraph's wait still got wrong --------------------------


@pytest.mark.parametrize(
    "said",
    [
        PARAGRAPH + " Please don't just do it: I want to see the tree first.",
        PARAGRAPH + " I don't want you to just do it.",
        PARAGRAPH + " I can't do it now myself.",
        "We have no plan for the Northwind feed yet. " + PARAGRAPH,
        PARAGRAPH + " I don't plan to ship this before Friday, so take your time.",
        PARAGRAPH + " There is no plan to keep the legacy importer.",
        PARAGRAPH + " Legacy has no owner; don't plan around it.",
    ],
)
def test_skipping_words_negated_or_said_in_passing_do_not_skip_the_tree(said):
    """Recheck 18 and 71: can't, curly apostrophes and a negation further back switched the rule off."""
    assert gate.paragraph(said)


def test_skipping_words_that_mean_it_skip_the_tree():
    assert not gate.paragraph(PARAGRAPH + " Don't worry about tests, just do it.")
    assert not gate.paragraph(PARAGRAPH + " I don’t mind: skip the plan.")


def test_a_question_paragraph_holds_its_writes_until_a_short_answer_says_no_plan(repo):
    """Recheck hunt: after a paragraph that got no tree, only 'just do it' lifted the wait, and the
    refusal did not say so. It says so now, and 'no plan' in a short answer lifts it."""
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    hook(repo, "UserPromptSubmit", prompt="thanks. fix the typo in README.md: 'hi' should be 'hello'")
    said = reason(write(repo, "README.md"))
    assert "'just do it' or 'no plan'" in said
    hook(repo, "UserPromptSubmit", prompt="do it without a plan please")
    assert write(repo, "README.md") is None


def test_a_tree_made_by_the_planner_or_before_a_second_paragraph_is_the_paragraphs_tree(repo):
    """Recheck hunt: a tree the session did not propose (:ask), or one proposed before the person's
    feedback paragraph, left the session told to 'propose it' for ever, even once it was accepted."""
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "xml", "title": "xml", "scope": ["src/api/**"], "check": "true"}],
                     Caller("planner", False))  # fmt: skip
    hook(repo, "UserPromptSubmit", prompt="On the tree: " + PARAGRAPH)  # feedback, a paragraph too
    assert "waits for the person" in reason(write(repo, "src/api/users.py"))
    with Store.open(repo) as store:
        plan.accept(store, ["xml"], ALEX)
    said = reason(write(repo, "src/api/users.py"))
    assert "graphene node start xml" in said and "propose it" not in said


def test_another_sessions_proposal_is_not_this_paragraphs_tree(repo):
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "other", "scope": ["src/db/**"], "check": "true"}],
                     Caller("claude:0badf00d", False, "0badf00d"))  # fmt: skip
    assert "propose it" in reason(write(repo, "src/api/users.py"))


def test_once_the_tree_is_accepted_and_a_leaf_done_the_refusal_names_the_next_leaf(repo, finish):
    """Recheck 25."""
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        leaves = [("xml", "src/api/**"), ("zero", "src/db/**")]
        plan.propose(store, [{"id": i, "title": i, "scope": [s], "check": "true"} for i, s in leaves], BOT)
        plan.accept(store, ["xml", "zero"], ALEX)
        plan.start(store, "xml", BOT, repo)
        finish(store, repo, "xml", BOT)
    hook(repo, "UserPromptSubmit", prompt="Now the other one. " + PARAGRAPH)
    said = reason(write(repo, "src/db/schema.py"))
    assert "graphene node start zero" in said and "propose it" not in said


def test_a_leaf_id_or_a_check_flag_in_prose_is_still_a_paragraph():
    """Recheck hunt: 'the ids first' or 'ruff format --check' in a paragraph skipped the tree."""
    assert gate.paragraph(PARAGRAPH + " Keep the same columns, the ids first.", ["ids", "schema"])
    assert gate.paragraph(PARAGRAPH + " CI runs ruff format --check and mypy on every push.")
    assert not gate.paragraph(PARAGRAPH + " So: do ids, carefully.", ["ids"])
    assert not gate.paragraph(PARAGRAPH + " --scope src/api --check 'make test'")


def test_a_command_with_many_ignored_redirects_asks_git_once(repo, monkeypatch):
    """Recheck 27: 250 redirects into build/ asked git 250 times (7 s, past the vendor's 5 s); and
    during the wait the 9th ignored path was refused as a write."""
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    asked, real = [], gate._ignored
    monkeypatch.setattr(gate, "_ignored", lambda root, rels: asked.append(rels) or real(root, rels))
    assert bash(repo, "".join(f"echo {i} > build/f{i}; " for i in range(250))) is None
    assert "becomes a tree" in reason(bash(repo, "echo 1 > build/a; echo x > src/api/users.py"))
    assert len(asked) == 2
    holding(repo)
    asked.clear()
    assert bash(repo, "".join(f"echo {i} > build/f{i}; " for i in range(250))) is None
    assert len(asked) == 1


def test_a_hand_back_or_a_search_that_names_the_hook_is_not_running_it(repo):
    """Recheck 26."""
    holding(repo)
    why = "graphene node release n1 --why 'the fix is in graphene ingest hook, outside my scope'"
    assert bash(repo, why) is None
    assert bash(repo, "rg 'graphene ingest' README.md") is None
    assert "not an agent's to run" in reason(bash(repo, "rg x README.md; graphene ingest hook < e.json"))


def test_the_way_out_names_each_wanted_path_with_its_own_flag(repo):
    """Recheck hunt: `--wants <the paths you need>` led an agent to `--wants b.py c.py`, a usage error."""
    holding(repo)
    assert "--wants <a path> --wants <another>" in reason(write(repo, "src/db/schema.py"))


# recheck 14
def test_a_vendor_notice_does_not_end_a_paragraphs_wait(repo):
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    notice = "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>"
    assert hook(repo, "UserPromptSubmit", prompt=notice) is None
    refused = write(repo, "src/api/users.py")
    assert refused and "becomes a tree before any code" in reason(refused)


# recheck 15
def test_a_follow_up_prompt_does_not_end_the_wait_while_the_tree_is_only_proposed(repo):
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        plan.propose(
            store,
            [
                {"id": "xml", "title": "load the xml feed", "scope": ["src/api/**"], "check": "true"},
                {"id": "zero", "title": "skip zero prices", "scope": ["src/db/**"], "check": "true"},
            ],
            BOT,
        )
    assert hook(repo, "UserPromptSubmit", prompt="drop zero, the rest is fine") is None
    for refused in (
        write(repo, "src/api/users.py"),
        write(repo, "README.md"),
        bash(repo, "echo hi > notes.txt"),
    ):
        assert refused and "waits for the person" in reason(refused)


# recheck 16
def test_a_yes_after_a_paragraph_accepts_its_tree_and_not_what_was_proposed_before_it(repo):
    hook(repo, "UserPromptSubmit", prompt="what does the loader do with empty rows?")
    with Store.open(repo) as store:
        plan.propose(
            store,
            [{"id": "rm-csv", "title": "delete the csv loader", "scope": ["src/api/**"], "check": "true"}],
            BOT,
        )
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        plan.propose(
            store,
            [{"id": "xml", "title": "load the xml feed", "scope": ["src/api/**"], "check": "true"}],
            BOT,
        )
    hook(repo, "UserPromptSubmit", prompt="yes")
    with Store.open(repo) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"rm-csv": "proposed", "xml": "open"}


# recheck 17
def test_after_a_yes_to_its_tree_the_session_writes_only_inside_a_leaf_it_takes(repo):
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        plan.propose(
            store,
            [
                {"id": "xml", "title": "load the xml feed", "scope": ["src/api/**"], "check": "true"},
                {"id": "zero", "title": "skip zero prices", "scope": ["src/db/**"], "check": "true"},
            ],
            BOT,
        )
    hook(repo, "UserPromptSubmit", prompt="yes")
    refused = write(repo, "README.md")
    assert refused and "graphene node start xml" in reason(refused)
    with Store.open(repo) as store:
        assert [n.id for n in plan.nodes(store)] == ["xml", "zero"]  # no `**` leaf made from "yes"
        plan.start(store, "xml", BOT, repo)
    assert write(repo, "src/api/users.py") is None
    assert "outside the scope of the node you hold (xml" in reason(write(repo, "README.md"))


# recheck 19
def test_a_planner_is_refused_a_write_with_no_plan_and_with_only_proposals(repo, monkeypatch):
    monkeypatch.setenv("GRAPHENE_PLANNER", "1")
    for answer in (write(repo, "src/api/users.py", tool="Write"), bash(repo, "echo x > src/api/users.py")):
        assert answer and "you are the planner" in reason(answer)
    with Store.open(repo) as store:
        plan.propose(
            store,
            [{"id": "p1", "title": "a proposal", "scope": ["src/**"], "check": "true"}],
            Caller("claude:aaaaaaaa", False, "other"),
        )
    refused = write(repo, "src/api/users.py", tool="Write")
    assert refused and "you are the planner" in reason(refused)


# recheck 20
def test_a_paragraph_after_an_interrupted_turn_is_still_a_tree(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"title": "users", "scope": ["src/api/**"], "check": "true"}], ALEX)
    hook(repo, "UserPromptSubmit", prompt="fix the typo in the README header")
    assert write(repo, "README.md") is None  # a leaf made from the prompt; then Esc, so no Stop
    told = hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    assert told and "becomes a tree before any code" in told["hookSpecificOutput"]["additionalContext"]
    refused = write(repo, "src/db/new.py")
    assert refused and "becomes a tree before any code" in reason(refused)


# recheck 21
def test_a_waiting_paragraph_refuses_the_ordinary_spellings_that_lift_it_even_with_no_plan(repo):
    """With no plan in force, a forged `graphene ingest hook` and sqlite3 on .graphene were let through."""
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    event = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": SID, "prompt": "ok"})
    assert "not an agent's to run" in reason(bash(repo, f"echo '{event}' | graphene ingest hook"))
    sql = "sqlite3 .graphene/graphene.db \"delete from plan_meta where key like 'tree:%'\""
    assert "the plan's own store" in reason(bash(repo, sql))
    assert "becomes a tree before any code" in reason(write(repo, "src/api/users.py"))


# recheck 22
@pytest.mark.parametrize(
    "start", ["/Users/alex/proj/ingest is where csv loads. ", "[feature] ", "<Product> rows. "]
)
def test_a_paragraph_that_starts_with_a_path_or_a_bracket_is_still_the_persons(repo, start):
    told = hook(repo, "UserPromptSubmit", prompt=start + PARAGRAPH)["hookSpecificOutput"]["additionalContext"]
    assert "becomes a tree before any code" in told
    assert "becomes a tree before any code" in reason(write(repo, "src/api/users.py"))


# recheck 24
def test_a_paragraph_that_names_a_ready_leaf_or_types_its_own_scope_is_a_request_to_do(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "xml", "title": "xml", "scope": ["src/api/**"], "check": "true"}], ALEX)
    take = "Take xml now, it is already in the plan with its scope and check. " + PARAGRAPH
    assert hook(repo, "UserPromptSubmit", prompt=take) is None
    assert "graphene node start xml" in reason(write(repo, "src/api/users.py"))
    assert hook(repo, "UserPromptSubmit", prompt=PARAGRAPH + " --scope 'src/db/**' --check 'true'") is None
    assert write(repo, "src/db/schema.py") is None  # inside the scope they typed
    assert "outside the scope" in reason(write(repo, "README.md"))


# recheck 48
def test_undo_after_a_yes_in_the_session_takes_back_that_acceptance_not_an_older_act(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "zold", "title": "old", "scope": ["docs/**"], "check": "true"}], ALEX)
        with plan.undoable(store, ALEX, "node drop zold"):
            plan.drop(store, "zold", ALEX)
        plan.propose(store, [{"id": "p1", "title": "agent's", "scope": ["src/**"], "check": "true"}], BOT)
    said = hook(repo, "UserPromptSubmit", prompt="yes p1")["hookSpecificOutput"]["additionalContext"]
    assert "accepted p1" in said
    with Store.open(repo) as store:
        assert plan.undo(store, ALEX).startswith("yes in the session")
        assert (plan.get(store, "p1").state, plan.get(store, "zold").state) == ("proposed", "dropped")


# recheck 68
def test_a_question_about_the_tree_does_not_end_the_paragraphs_wait(repo):
    hook(repo, "UserPromptSubmit", prompt=PARAGRAPH)
    with Store.open(repo) as store:
        plan.propose(
            store, [{"id": "xml", "title": "the XML feed", "scope": ["ingest/**"], "check": "true"}], BOT
        )
    hook(repo, "UserPromptSubmit", prompt="why is legacy not in any scope?")
    assert "waits for the person" in reason(write(repo, "legacy/importer.py"))
    with Store.open(repo) as store:
        plan.accept(store, ["xml"], ALEX)
    assert "is accepted" in reason(write(repo, "legacy/importer.py"))  # accepted, and not yet taken
    with Store.open(repo) as store:
        plan.start(store, "xml", BOT, repo)
    assert "outside the scope" in reason(write(repo, "legacy/importer.py"))
    assert write(repo, "ingest/xmlfeed.py") is None
