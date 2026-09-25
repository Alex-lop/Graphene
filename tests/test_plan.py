"""The plan binds at the boundary, whoever executes a node: `finish` asks git what changed and runs
the check itself. A real git repo in every test, because git is the mechanism."""

import os
import subprocess
import threading
import time

import pytest

from graphene_map import plan
from graphene_map.plan import AGENT, DONE, OPEN, PROPOSED, REVIEW, RUNNING, Caller, Refused
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:aaaa1111", False, "aaaa1111-session")
BOT2 = Caller("claude:bbbb2222", False, "bbbb2222-session")


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "T")
    for path, text in {
        "src/api/users.py": "def users():\n    return []\n",
        "src/db/schema.py": "TABLES = []\n",
        "tests/test_users.py": "",
        "README.md": "# toy\n",
    }.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "start")
    return tmp_path


@pytest.fixture
def store(repo):
    with Store.open(repo) as s:
        yield s


def api_node(**extra):
    return {"title": "users endpoint", "scope": ["src/api/**", "tests/**"], "check": "true", **extra}


# -- scope ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, scope, inside",
    [
        ("src/api/users.py", ["src/api/**"], True),
        ("src/api/v2/users.py", ["src/api/**"], True),
        ("src/api/users.py", ["src/api"], True),  # a bare directory covers what is beneath it
        ("src/api/users.py", ["src/api/"], True),
        ("src/apiary.py", ["src/api"], False),  # and nothing that merely starts the same
        ("src/db/schema.py", ["src/api/**"], False),
        ("tests/test_users.py", ["tests/test_*.py"], True),
        ("tests/deep/test_users.py", ["tests/test_*.py"], False),  # * stays inside one directory
        ("src/a/b.py", ["src/*"], False),  # and so does a bare *: one level, not the subtree
        ("src/a", ["src/*"], True),
        ("tests/deep/test_users.py", ["**/test_*.py"], True),
        ("test_top.py", ["**/test_*.py"], True),
        ("README.md", ["README.md"], True),
        (".env", ["./.env"], True),
        ("src/db/schema.py", ["src/**", "!src/db/**"], False),  # the last match decides
        ("src/db/schema.py", ["!src/db/**", "src/**"], True),
        ("anything/at/all.py", ["**"], True),
        ("src/api/users.py", [], False),
    ],
)
def test_scope_globs(path, scope, inside):
    assert plan.in_scope(path, scope) is inside


def test_two_scopes_overlap_on_a_tracked_file_or_on_a_glob_one_of_them_spells():
    files = ["src/api/users.py", "src/db/schema.py"]
    assert plan.overlap(["src/**"], ["src/api/**"], files) == ["src/api/**", "src/api/users.py"]
    assert plan.overlap(["src/api/**"], ["src/db/**"], files) == []
    assert plan.overlap(["docs/new.md"], ["docs/**"], files) == ["docs/new.md"]  # not written yet, still seen


# -- shaping the plan -------------------------------------------------------------------------------


def test_a_persons_node_is_in_the_plan_at_once_and_an_agents_is_a_proposal(store):
    [mine] = plan.propose(store, [api_node()], ALEX)
    [theirs] = plan.propose(store, [api_node(title="docs", scope=["docs/**"])], BOT)
    assert (mine.id, mine.state, theirs.id, theirs.state) == ("n1", OPEN, "n2", PROPOSED)
    with pytest.raises(Refused, match="proposal"):
        plan.start(store, "n2", BOT, store.path.parent.parent)
    with pytest.raises(Refused, match="person's to do"):
        plan.accept(store, ["n2"], BOT)  # an agent cannot accept its own proposal
    plan.accept(store, [], ALEX)
    assert plan.get(store, "n2").state == OPEN


@pytest.mark.parametrize(
    "bad, says",
    [
        ({"title": "x", "scope": ["a"]}, "a check, a person's sign-off"),
        ({"title": "x", "check": "true"}, "needs a scope"),
        ({"title": "", "scope": ["a"], "check": "true"}, "needs a title"),
        ({"title": "x", "scope": ["a"], "check": "true", "needs": ["nope"]}, "not in the plan"),
        ({"title": "x", "scope": ["a"], "check": "true", "scop": ["b"]}, "unknown field"),
    ],
)
def test_a_node_that_cannot_run_is_refused_with_the_reason(store, bad, says):
    with pytest.raises(Refused, match=says):
        plan.propose(store, [bad], ALEX)
    assert plan.nodes(store) == []  # and nothing of the batch was kept


def test_a_cycle_is_refused(store):
    plan.propose(store, [api_node(id="a"), api_node(id="b", needs=["a"])], ALEX)
    with pytest.raises(Refused, match="cycle: a -> b -> a"):
        plan.edit(store, "a", {"needs": ["b"]}, ALEX)


def test_only_a_person_edits_a_contract_and_every_edit_is_a_revision(store):
    plan.propose(store, [api_node()], ALEX)
    with pytest.raises(Refused, match="person's to do"):
        plan.edit(store, "n1", {"scope": ["**"]}, BOT)  # an agent cannot widen its own scope
    node = plan.edit(store, "n1", {"scope": ["src/api/users.py"], "owner": "me"}, ALEX)
    assert (node.rev, node.scope, node.owner) == (2, ["src/api/users.py"], "alex")
    assert plan.edit(store, "n1", {"scope": ["src/api/users.py"]}, ALEX).rev == 2  # no change, no revision
    [entry] = store.node_log("n1", ("edited",))
    assert entry["detail"]["changed"]["scope"] == [["src/api/**", "tests/**"], ["src/api/users.py"]]


def test_the_forecast_says_before_the_run_what_will_wait_for_a_person(store):
    plan.propose(
        store,
        [
            api_node(id="api"),
            api_node(id="migration", owner="me", scope=["src/db/**"]),
            api_node(id="wire", needs=["api", "migration"], scope=["src/app.py"]),
            api_node(id="docs", needs=["api"], scope=["docs/**"], signoff=True),
            api_node(id="ship", needs=["docs"], scope=["CHANGELOG.md"]),
        ],
        ALEX,
    )
    runs, waits = plan.forecast(plan.nodes(store))
    assert [n.id for n in runs] == ["api", "docs"]  # docs runs; its sign-off stops what comes after it
    assert [(n.id, why) for n, why in waits] == [
        ("migration", ["migration is alex's"]),
        ("wire", ["migration is alex's"]),
        ("ship", ["docs needs a sign-off"]),
    ]


# -- taking a node ----------------------------------------------------------------------------------


def test_start_is_refused_until_what_it_waits_on_is_done(store, repo, finish):
    plan.propose(store, [api_node(id="a"), api_node(id="b", needs=["a"], scope=["README.md"])], ALEX)
    with pytest.raises(Refused, match=r"b waits on a \(open\)"):
        plan.start(store, "b", BOT, repo)
    plan.start(store, "a", BOT, repo)
    with pytest.raises(Refused, match=r"b waits on a \(running\)"):
        plan.start(store, "b", BOT2, repo)
    finish(store, repo, "a", BOT)
    assert plan.start(store, "b", BOT2, repo).state == RUNNING


def test_an_agent_cannot_take_a_persons_node_and_the_person_can(store, repo):
    plan.propose(store, [api_node(owner="me")], ALEX)
    with pytest.raises(Refused, match="alex's node"):
        plan.start(store, "n1", BOT, repo)
    assert plan.ready(plan.nodes(store), BOT) == []
    assert plan.start(store, "n1", ALEX, repo).executor == "alex"


def test_two_running_nodes_never_claim_the_same_path_in_one_checkout(store, repo):
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["src/**"])], ALEX)
    plan.start(store, "a", BOT, repo)
    with pytest.raises(Refused, match="both claim .*one writer at a time"):
        plan.start(store, "b", BOT2, repo)


# -- the boundary -----------------------------------------------------------------------------------


def test_a_node_with_a_change_outside_its_scope_is_not_done_however_the_file_was_written(store, repo):
    plan.propose(store, [api_node(), api_node(title="next", needs=["n1"], scope=["README.md"])], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    subprocess.run("cat > src/db/schema.py <<'X'\nTABLES = ['users']\nX", shell=True, cwd=repo, check=True)
    (repo / "notes.txt").write_text("scratch")  # a new file nobody asked for
    with pytest.raises(Refused, match=r"outside its scope [^\n]*\n  notes.txt, src/db/schema.py\n"):
        plan.finish(store, "n1", BOT)
    assert plan.get(store, "n1").state == RUNNING
    with pytest.raises(Refused, match="n2 waits on n1"):
        plan.start(store, "n2", BOT2, repo)  # what waits on it cannot start
    git(repo, "checkout", "--", "src/db/schema.py")
    (repo / "notes.txt").unlink()
    assert plan.finish(store, "n1", BOT).state == DONE
    assert [e["detail"]["outside"] for e in store.node_log("n1", ("refused",))] == [
        ["notes.txt", "src/db/schema.py"]
    ]


def test_committing_the_stray_change_does_not_hide_it(store, repo):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/db/schema.py").write_text("TABLES = ['x']\n")
    git(repo, "commit", "-qam", "sneaky")
    with pytest.raises(Refused, match="src/db/schema.py"):
        plan.finish(store, "n1", BOT)


def test_what_was_already_dirty_at_the_start_is_not_held_against_the_node(store, repo):
    (repo / "README.md").write_text("# the person was editing this\n")
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [2]\n")
    assert plan.finish(store, "n1", BOT).state == DONE


def test_but_changing_it_again_is(store, repo):
    (repo / "README.md").write_text("# the person was editing this\n")
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    git(repo, "checkout", "--", "README.md")  # the agent wiped the person's uncommitted edit
    with pytest.raises(Refused, match="README.md"):
        plan.finish(store, "n1", BOT)


def test_a_failing_check_keeps_the_node_open_and_graphene_is_the_one_who_ran_it(store, repo):
    plan.propose(store, [api_node(check="grep -q 'return \\[1\\]' src/api/users.py")], ALEX)
    plan.start(store, "n1", BOT, repo)
    with pytest.raises(Refused, match="failed"):
        plan.finish(store, "n1", BOT)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    assert plan.finish(store, "n1", BOT).state == DONE
    assert [e["kind"] for e in store.node_log("n1")] == [
        "added",
        "started",
        "check_failed",
        "check_passed",
        "finished",
    ]


def test_a_sign_off_node_waits_in_review_and_only_a_person_signs(store, repo, finish):
    plan.propose(
        store, [api_node(signoff=True), api_node(title="after", needs=["n1"], scope=["README.md"])], ALEX
    )
    plan.start(store, "n1", BOT, repo)
    assert finish(store, repo, "n1", BOT).state == REVIEW
    with pytest.raises(Refused, match=r"n2 waits on n1 \(review\)"):
        plan.start(store, "n2", BOT, repo)
    with pytest.raises(Refused, match="person's to do"):
        plan.signoff(store, "n1", BOT)
    assert plan.signoff(store, "n1", ALEX).state == DONE
    assert plan.start(store, "n2", BOT, repo).state == RUNNING


def test_reopen_sends_it_back_with_a_note_the_next_executor_is_told(store, repo, finish):
    plan.propose(store, [api_node(signoff=True)], ALEX)
    plan.start(store, "n1", BOT, repo)
    finish(store, repo, "n1", BOT)
    node = plan.reopen(store, "n1", ALEX, "returns a list, I asked for a dict")
    assert (node.state, node.rev, node.executor) == (OPEN, 2, None)
    assert plan.notes(store, "n1") == ["returns a list, I asked for a dict"]


def test_release_hands_a_node_back_and_must_say_why(store, repo):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    with pytest.raises(Refused, match="say why"):
        plan.release(store, "n1", BOT, " ")
    assert plan.release(store, "n1", BOT, "the schema has to change and it is outside my scope").state == OPEN
    assert store.node_log("n1", ("released",))[0]["detail"]["why"].startswith("the schema")


def test_another_session_cannot_finish_a_node_it_does_not_hold(store, repo):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    with pytest.raises(Refused, match="held by claude:aaaa1111"):
        plan.finish(store, "n1", BOT2)


def test_a_person_can_overrule_the_gate_with_a_reason_and_the_log_says_so(store, repo):
    plan.propose(store, [api_node(check="false")], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "README.md").write_text("# changed\n")
    with pytest.raises(Refused, match="person's to do"):
        plan.finish(store, "n1", BOT, override="trust me")
    assert plan.finish(store, "n1", ALEX, override="the README edit was mine").state == DONE
    [entry] = store.node_log("n1", ("overruled",))
    assert entry["detail"] == {
        "head": plan.head(repo),
        "changed": ["README.md"],
        "override": "the README edit was mine",
        "outside": ["README.md"],
        "check_passed": False,
    }


def test_a_node_beside_it_in_the_same_checkout_is_not_its_stray_change(store, repo, finish):
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    plan.start(store, "b", BOT2, repo)
    (repo / "README.md").write_text("# b's work\n")
    finish(store, repo, "b", BOT2)
    assert finish(store, repo, "a", BOT).state == DONE


def test_archive_puts_finished_work_away_but_keeps_what_open_work_waits_on(store, repo, finish):
    plan.propose(
        store,
        [api_node(id="a"), api_node(id="b", scope=["README.md"]), api_node(id="c", needs=["b"], scope=["x"])],
        ALEX,
    )
    for i, who in (("a", BOT), ("b", BOT2)):
        plan.start(store, i, who, repo)
        finish(store, repo, i, who)
    assert [n.id for n in plan.archive(store, ALEX)] == ["a"]  # c still waits on b
    assert plan.in_force(store)
    with pytest.raises(Refused, match="not in the plan"):
        plan.propose(store, [api_node(id="d", needs=["a"], scope=["y"])], ALEX)


def test_a_paused_plan_binds_nobody_and_starts_nothing(store, repo):
    plan.propose(store, [api_node()], ALEX)
    assert plan.in_force(store)
    with pytest.raises(Refused, match="person's to do"):
        plan.set_paused(store, True, BOT)
    plan.set_paused(store, True, ALEX)
    assert not plan.in_force(store)
    with pytest.raises(Refused, match="paused"):
        plan.start(store, "n1", BOT, repo)


# -- what the closing review broke ---------------------------------------------------------------------


def test_only_whoever_holds_a_node_finishes_it_or_hands_it_back(store, repo, finish):
    """The review's first blocker: an agent finished, and released, the person's own running node."""
    plan.propose(store, [api_node(id="mine", owner="alex"), api_node(id="theirs", scope=["README.md"])], ALEX)
    plan.start(store, "mine", ALEX, repo)
    plan.start(store, "theirs", BOT, repo)
    for node_id in ("mine", "theirs"):
        with pytest.raises(Refused, match=f"{node_id} is held by .*, not by claude:bbbb2222"):
            plan.finish(store, node_id, BOT2)
        with pytest.raises(Refused, match=f"{node_id} is held by"):
            plan.release(store, node_id, BOT2, "not mine, but I would like it gone")
    assert finish(store, repo, "theirs", BOT).state == DONE
    assert plan.release(store, "mine", ALEX, "later").state == OPEN  # a person always may


def test_a_symbolic_link_inside_the_scope_that_leaves_the_repo_is_not_inside_the_scope(store, repo, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("original\n")
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/cache").symlink_to(outside)
    (repo / "src/api/cache").write_text("OWNED\n")  # lands outside the repo
    with pytest.raises(Refused, match=r"src/api/cache.*is a symbolic link that leaves the repo"):
        plan.finish(store, "n1", BOT)


def test_a_file_git_was_told_to_stop_watching_does_not_pass_the_boundary(store, repo):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    git(repo, "update-index", "--assume-unchanged", "README.md")
    (repo / "README.md").write_text("# tampered, and git says nothing changed\n")
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    with pytest.raises(
        Refused, match="marked assume-unchanged or skip-worktree since it was started\n  README.md\n"
    ):
        plan.finish(store, "n1", BOT)
    git(repo, "update-index", "--no-assume-unchanged", "README.md")
    with pytest.raises(Refused, match="outside its scope [^\n]*\n  README.md"):
        plan.finish(store, "n1", BOT)


def test_a_line_added_to_the_clones_exclude_file_does_not_hide_a_new_file(store, repo):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / ".git/info/exclude").write_text("stray.txt\n")
    (repo / "stray.txt").write_text("hidden from git status\n")
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    with pytest.raises(Refused, match=r"\.git/info/exclude edited since it was started"):
        plan.finish(store, "n1", BOT)


def test_a_node_with_nothing_changed_inside_its_scope_is_not_done(store, repo):
    """The review ran `graphene run` with an executor that crashed at once; the check already
    passed, and the node was reported done."""
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    with pytest.raises(Refused, match="nothing inside its scope .* has changed since it was started"):
        plan.finish(store, "n1", BOT)
    assert plan.finish(store, "n1", ALEX, override="it was already right").state == DONE


def test_a_scope_spelled_in_the_wrong_case_says_so_when_it_refuses(store, repo):
    plan.propose(store, [api_node(scope=["readme.md"])], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "README.md").write_text("# changed\n")
    with pytest.raises(Refused, match=r"\(readme.md\)[^\n]*; README.md differs from it only in upper and"):
        plan.finish(store, "n1", BOT)


def test_a_change_in_another_worktree_of_the_repo_does_not_pass_the_boundary(store, repo, tmp_path):
    side = tmp_path.parent / f"{tmp_path.name}-side"
    git(repo, "worktree", "add", "-q", str(side), "-b", "side")
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (side / "src/db/schema.py").write_text("TABLES = ['written by absolute path']\n")
    with pytest.raises(Refused, match=r"src/db/schema.py \(in the worktree .*-side\)"):
        plan.finish(store, "n1", BOT)
    git(side, "checkout", "--", "src/db/schema.py")
    (side / "src/api/helper.py").write_text("# inside the scope is inside the scope, in any tree\n")
    assert plan.finish(store, "n1", BOT).state == DONE


def test_a_stale_worktree_git_can_no_longer_read_stops_nothing(store, repo, tmp_path, finish):
    """Found by timing the audit on the author's repo: 33 other worktrees, one of them a directory
    that was no longer a checkout, and every `node start` would have been refused over it."""
    import shutil

    stale = tmp_path.parent / f"{tmp_path.name}-stale"
    git(repo, "worktree", "add", "-q", str(stale), "-b", "stale")
    shutil.rmtree(stale)
    stale.mkdir()  # the directory is there, the checkout is not
    plan.propose(store, [api_node()], ALEX)
    assert plan.start(store, "n1", BOT, repo).others_at_start == {}
    assert finish(store, repo, "n1", BOT).state == DONE


def test_a_worktree_made_after_the_start_is_compared_with_where_the_node_started(store, repo, tmp_path):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    late = tmp_path.parent / f"{tmp_path.name}-late"
    git(repo, "worktree", "add", "-q", str(late), "-b", "late")
    (late / "README.md").write_text("# a subagent's worktree, outside the scope\n")
    with pytest.raises(Refused, match=r"README.md \(in the worktree .*-late\)"):
        plan.finish(store, "n1", BOT)


def test_a_scope_that_differs_from_gits_spelling_only_in_case_is_refused_when_it_is_typed(store, repo):
    files = plan.tracked(repo)
    with pytest.raises(Refused, match="`readme.md` matches nothing git tracks, and `README.md` differs"):
        plan.propose(store, [api_node(scope=["readme.md"])], ALEX, files=files)
    plan.propose(store, [api_node(scope=["docs/**"])], ALEX, files=files)  # nothing there yet: fine
    with pytest.raises(Refused, match="`SRC/api/\\*\\*` matches nothing git tracks"):
        plan.edit(store, "n1", {"scope": ["SRC/api/**"]}, ALEX, files=files)


# -- who is asking ------------------------------------------------------------------------------------


def test_an_agent_is_known_by_its_own_marks_and_whoever_carries_none_is_the_person():
    claude = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "abcdef1234"}
    assert plan.caller(claude, tty=True) == Caller("claude:abcdef12", False, "abcdef1234")
    codex = {**claude, "CODEX_SESSION_ID": "01a0bd1a-32c4", "CODEX_SANDBOX": "seatbelt"}
    assert plan.caller(codex, tty=False) == Caller("codex:01a0bd1a", False, None)  # Codex inside Claude Code
    assert plan.caller({"AI_AGENT": "some-new-agent"}, tty=True).person is False
    assert plan.caller({"USER": "Alex"}, tty=True) == Caller("alex", True, None)
    # no terminal (an editor task, a pipe) is still the person: their `add` must never become a
    # proposal they then cannot accept. The log says "no terminal", and that is all the test decides
    piped = plan.caller({"USER": "Alex"}, tty=False)
    assert piped == Caller("alex", True, None, stand_in=True) and piped.label == "alex (no terminal)"
    assert plan.caller({"USER": "Alex", "GRAPHENE_NODE": "n1"}, tty=True).person is False  # run's executor
    stand_in = plan.caller({"USER": "alex", "GRAPHENE_AS": "person:sam"}, tty=False)
    assert stand_in == Caller("sam", True, None, stand_in=True) and stand_in.label == "sam (no terminal)"
    assert plan.caller({"GRAPHENE_AS": "agent:codex"}, tty=True).person is False


def test_inside_an_agents_shell_the_variable_a_script_uses_to_speak_for_a_person_changes_nothing():
    """The closing review spelled the variable so the hook's text match missed it (`export
    GRAPHENE$(printf "\\137")AS=person:dev`) and got every person-only act. The agent's own
    environment now outranks it, wherever it was set and however it was spelled."""
    forged = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "abcdef1234", "GRAPHENE_AS": "person:dev"}
    assert plan.caller(forged, tty=True) == Caller("claude:abcdef12", False, "abcdef1234")
    assert plan.caller({"CODEX_SESSION_ID": "01a0", "GRAPHENE_AS": "person:dev"}).person is False


def test_a_persons_act_made_without_a_terminal_is_logged_as_such(store):
    plan.propose(store, [api_node()], Caller("dev", True, None, stand_in=True))
    assert store.node_log("n1")[0]["actor"] == "dev (no terminal)"


# -- between nodes ------------------------------------------------------------------------------------


def test_work_done_after_the_audited_window_closed_stops_the_next_start(store, repo):
    """What a tempted agent really did in the spike: finish inside the scope, then do the rest."""
    plan.propose(store, [api_node(), api_node(title="next", needs=["n1"], scope=["README.md"])], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    plan.finish(store, "n1", BOT)
    (repo / "src/db/schema.py").write_text("TABLES = ['after hours']\n")  # no node is open now
    assert plan.unowned(store, repo) == ["src/db/schema.py"]
    with pytest.raises(Refused, match="has an uncommitted change no node made\n  src/db/schema.py\n"):
        plan.start(store, "n2", BOT, repo)
    with pytest.raises(Refused, match="person's to do"):
        plan.acknowledge(store, repo, BOT)
    assert plan.acknowledge(store, repo, ALEX) == ["src/db/schema.py"]  # "that was me": theirs to say
    assert plan.start(store, "n2", BOT, repo).state == RUNNING


def test_a_file_the_person_had_graphene_write_is_not_a_loose_change(store, repo, finish):
    """The first walkthrough: `graphene ui --export plan.html` in the repo, then the next node would
    not start: "plan.html changed while no node owned it"."""
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    (repo / "plan.html").write_text("<html>")
    assert plan.unowned(store, repo) == ["plan.html"]
    plan.accept_path(store, repo, repo / "plan.html")
    assert plan.unowned(store, repo) == []
    assert plan.start(store, "b", BOT2, repo).state == RUNNING


def test_a_person_starting_over_loose_changes_has_seen_them_and_the_log_keeps_them(store, repo, finish):
    plan.propose(store, [api_node(id="a"), api_node(id="b", owner="me", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    (repo / "notes.txt").write_text("x")
    plan.start(store, "b", ALEX, repo)
    assert store.node_log("b", ("started",))[0]["detail"]["unowned"] == ["notes.txt"]


def test_a_released_nodes_own_work_is_not_loose_but_its_stray_file_is(store, repo, finish):
    plan.propose(store, [api_node(id="a"), api_node(id="b"), api_node(id="c", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    plan.start(store, "b", BOT, repo)
    (repo / "src/api/users.py").write_text("half done\n")
    (repo / "src/db/schema.py").write_text("stray\n")
    plan.release(store, "b", BOT, "stuck")
    with pytest.raises(Refused, match=r"c cannot start: the checkout has an [^\n]*\n  src/db/schema.py\n"):
        plan.start(store, "c", BOT2, repo)


def test_the_first_node_handed_back_with_a_stray_file_stops_the_next_start_too(store, repo):
    """Found by `graphene run`'s tests: with no node finished yet there was no boundary to compare
    with, and the next node took the stray file for something that had always been there."""
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    (repo / "src/db/schema.py").write_text("stray\n")
    plan.release(store, "a", BOT, "stuck")
    with pytest.raises(Refused, match="b cannot start: the checkout has an [^\n]*\n  src/db/schema.py\n"):
        plan.start(store, "b", BOT2, repo)


def test_what_graphenes_own_run_of_the_check_leaves_behind_is_not_held_against_the_node(store, repo):
    check = "echo run >> .check-cache; grep -q 'return \\[1\\]' src/api/users.py"
    plan.propose(store, [api_node(check=check)], ALEX)
    plan.start(store, "n1", BOT, repo)
    with pytest.raises(Refused, match="failed"):
        plan.finish(store, "n1", BOT)  # the check failed, and left .check-cache behind
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    assert plan.finish(store, "n1", BOT).state == DONE


def test_an_untracked_directory_at_the_start_does_not_hide_a_new_file_in_it(store, repo):
    (repo / "scratch").mkdir()
    (repo / "scratch" / "old.txt").write_text("was here")
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "scratch" / "new.txt").write_text("sneaked in")
    with pytest.raises(Refused, match=r"scratch/new.txt"):
        plan.finish(store, "n1", BOT)


def test_the_contract_is_what_an_executor_is_told(store):
    [node] = plan.propose(store, [api_node(goal="GET /users returns them", signoff=True)], ALEX)
    text = plan.contract(node)
    assert "n1 (revision 1): users endpoint" in text
    assert "`true` passes and a person signs it off" in text
    assert "graphene node done n1" in text and "graphene node release n1" in text
    assert node.owner == AGENT


@pytest.mark.parametrize("act", ["release", "retake"])
def test_a_done_whose_leaf_was_let_go_during_its_check_is_refused_and_says_so(store, repo, monkeypatch, act):
    """Recheck: a check that left a file outside the scope wrote it into the next holder's record, and
    the stale `done` then finished the leaf the person had taken again; a release read "was open"."""
    plan.propose(store, [api_node(check="touch cache.tmp")], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    real = plan.run_check

    def person_acts_meanwhile(command, where, *leave_out):
        plan.release(store, "n1", ALEX, "I will do it myself")
        if act == "retake":
            plan.start(store, "n1", ALEX, repo)
        return real(command, where, *leave_out)

    monkeypatch.setattr(plan, "run_check", person_acts_meanwhile)
    said = "handed back and taken again" if act == "retake" else "handed back"
    with pytest.raises(Refused, match=f"n1 was {said} while its check ran"):
        plan.finish(store, "n1", BOT)
    node = plan.get(store, "n1")
    assert node.state == (RUNNING if act == "retake" else OPEN) and "cache.tmp" not in node.dirty_at_start


def test_undoing_an_edit_to_a_running_leaf_leaves_it_with_its_holder(store, repo):
    """Recheck: undo made every running row it put back open, so undoing the person's edit took the
    leaf from the session holding it. Undoing the drop of a running leaf still hands it back."""
    plan.propose(store, [api_node(), api_node(title="readme", scope=["README.md"])], ALEX)
    plan.start(store, "n1", BOT, repo)
    with plan.undoable(store, ALEX, "node set n1"):
        plan.edit(store, "n1", {"title": "users endpoint, better named"}, ALEX)
    assert plan.undo(store, ALEX) == "node set n1"
    n1 = plan.get(store, "n1")
    assert (n1.state, n1.session_id, n1.title) == (RUNNING, BOT.session_id, "users endpoint")
    plan.start(store, "n2", BOT2, repo)
    with plan.undoable(store, ALEX, "node drop n2"):
        plan.drop(store, "n2", ALEX)
    plan.undo(store, ALEX)
    assert (plan.get(store, "n2").state, plan.get(store, "n2").session_id) == (OPEN, None)


def test_a_leftover_in_a_runs_worktree_is_not_charged_to_a_node_held_in_the_persons_checkout(store, repo):
    """Recheck: a `--parallel` leaf's stray file in its own worktree kept the person's node from being
    done until that worktree was cleaned; the leaf's own boundary answers for it."""
    plan.propose(store, [api_node(), api_node(title="readme", scope=["README.md"])], ALEX)
    plan.start(store, "n2", ALEX, repo)
    tree = repo / ".graphene" / "worktrees" / "n1"
    git(repo, "worktree", "add", "-q", "-b", "graphene/n1", str(tree), "HEAD")
    (tree / "notes.tmp").write_text("scratch\n")
    (repo / "README.md").write_text("# toy, by the person\n")
    assert plan.finish(store, "n2", ALEX).state == DONE


def test_done_release_and_signoff_ask_git_before_the_write_lock_is_taken(store, repo, monkeypatch):
    """Recheck: `done` hashed up to 200 files, `release` diffed the checkout and `signoff` resolved a
    branch while holding the plan's write lock; a hook waiting on it gives up after a quarter second."""
    plan.propose(store, [api_node(signoff=True), api_node(title="readme", scope=["README.md"])], ALEX)
    plan.start(store, "n1", BOT, repo)
    plan.start(store, "n2", BOT2, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "README.md").write_text("# toy, again\n")
    store.log_node("n1", plan._now(), "unlanded", "graphene run", None, None, {"branch": "graphene/n1"})
    seen, real = [], plan._git

    def asked(checkout, *args, **kw):
        seen.append((args[0], store.conn.in_transaction))
        return real(checkout, *args, **kw)

    monkeypatch.setattr(plan, "_git", asked)
    assert plan.finish(store, "n1", BOT).state == REVIEW
    plan.release(store, "n2", BOT2, "not now")
    assert plan.signoff(store, "n1", ALEX).state == DONE
    assert seen and [command for command, locked in seen if locked] == []


def test_an_offer_takes_only_the_paths_it_showed(tmp_path):
    """Recheck 52: the offer hid a brace path and a path its need already writes, and `node widen`
    then took them all and was refused."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    alex, bot = Caller("alex", True), Caller("claude:aaaa1111", False, "s1")
    with Store.open(tmp_path) as store:
        plan.propose(store, [{"id": "n", "title": "n", "scope": ["lib/n.py"], "check": "true"},
                             {"id": "x", "title": "x", "scope": ["x.py"], "check": "true"}],
                     alex)  # fmt: skip
        plan.start(store, "x", bot, tmp_path)
        for path in ("lib/b.py", "{{cookiecutter.slug}}/setup.py", "lib/n.py"):
            store.log_node("x", plan._now(), "denied", None, "s1", None, {"path": path})
        plan.release(store, "x", bot, "it needs lib/b.py")
        plan.edit(store, "x", {"needs": ["n"]}, alex)
        assert plan.offerable(store, plan.get(store, "x")) == ["lib/b.py"]
        assert plan.widen(store, "x", [], alex).scope == ["x.py", "lib/b.py"]


def test_a_reason_naming_many_nodes_is_checked_for_cycles_once(tmp_path, monkeypatch):
    """Recheck 44: a validate for every node the reason named, on every refresh of the screen."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    alex, bot = Caller("alex", True), Caller("claude:aaaa1111", False, "s1")
    with Store.open(tmp_path) as store:
        items = [{"id": f"m{i}", "title": f"m{i}", "scope": [f"m{i}.py"], "check": "true"} for i in range(40)]
        plan.propose(store, [*items, {"id": "x", "title": "x", "scope": ["x.py"], "check": "true"}], alex)
        plan.start(store, "x", bot, tmp_path)
        plan.release(store, "x", bot, "waits on " + " ".join(f"m{i}" for i in range(40)))
        calls, real = [], plan.validate
        monkeypatch.setattr(plan, "validate", lambda *a: calls.append(1) or real(*a))
        [(key, _, argv)] = plan.offers(store, plan.get(store, "x"))
        assert key == "n" and argv.count("--needs") == 40 and len(calls) == 1


# -- what counts at the boundary, and how a refusal reads ----------------------------------------------


def python_leaf(**extra):
    """A leaf whose check leaves a cache outside its scope, as `python -m unittest` leaves __pycache__."""
    check = "mkdir -p cache && echo compiled > cache/users.pyc && grep -q 'return \\[1\\]' src/api/users.py"
    return {"title": "users endpoint", "scope": ["src/api/**"], "check": check, **extra}


def test_what_the_check_makes_again_is_its_own_and_is_neither_counted_nor_committed(store, repo):
    """A Python repo with no .gitignore: the executor ran the tests before `done`, and `done` was
    refused over the __pycache__ they left outside the scope."""
    plan.propose(store, [python_leaf()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "cache").mkdir()
    (repo / "cache/users.pyc").write_text("compiled by the executor's own test run\n")
    assert plan.finish(store, "n1", BOT).state == DONE
    # the executor's, as it left it: the check's own went with the worktree it ran in (it had replaced
    # the executor's, when the check ran in place)
    assert (repo / "cache/users.pyc").read_text() == "compiled by the executor's own test run\n"
    [ended] = store.node_log("n1", ("finished",))
    assert ended["detail"]["changed"] == ["src/api/users.py"]  # what `run` commits
    assert no_check_tree_left(store, repo)


def test_what_the_check_does_not_make_again_is_refused(store, repo):
    plan.propose(store, [python_leaf()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "cache").mkdir()
    (repo / "cache/users.pyc").write_text("x\n")
    (repo / "notes.txt").write_text("the executor's own\n")
    with pytest.raises(Refused, match=r"changed outside its scope \(src/api/\*\*\)[^\n]*\n  notes.txt\n"):
        plan.finish(store, "n1", BOT)
    assert (repo / "notes.txt").read_text() == "the executor's own\n"  # as it was
    assert plan.get(store, "n1").state == RUNNING


def test_a_check_that_is_stopped_leaves_the_checkout_as_it_was_and_its_worktree_goes(store, repo):
    """The executor's new files used to be set aside while the check ran, and put back when it was
    stopped: now nothing in the checkout is moved, and the check's worktree goes however it ends."""
    wrote = repo / ".git" / "check.wrote"
    check = f"echo check > notes.txt && echo check >> README.md && touch {wrote} && sleep 30"
    plan.propose(store, [python_leaf(check=check)], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "notes.txt").write_text("the executor's own\n")
    left = files_in(repo)

    def stop_it():  # once it has written, as a stopped run ends the checks it started
        until = time.monotonic() + 20
        while not wrote.exists() and time.monotonic() < until:
            time.sleep(0.01)
        plan.end_checks()

    threading.Thread(target=stop_it).start()
    with pytest.raises(KeyboardInterrupt):
        plan.finish(store, "n1", BOT)
    assert files_in(repo) == left and no_check_tree_left(store, repo)


def files_in(repo) -> dict[str, bytes]:
    """Every file of the checkout with its content, but git's own and the plan's store."""
    inside = (p for p in repo.rglob("*") if not {".git", ".graphene"} & set(p.relative_to(repo).parts))
    return {str(p.relative_to(repo)): p.read_bytes() for p in inside if p.is_file()}


def no_check_tree_left(store, repo) -> bool:
    listed = subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True)
    left = list((store.path.parent / "worktrees").glob(".check-*"))
    return len(listed.stdout.splitlines()) == 1 and not left


def test_a_check_that_writes_leaves_the_checkout_exactly_as_the_executor_left_it(store, repo):
    """The check runs in a worktree of its own, cut from the leaf's state as git sees it, committed or
    not: whatever it writes, in the scope or out, to a tracked file or a new one, goes with that
    worktree. Run in place, what a check wrote was counted as the executor's change, and committed."""
    check = (
        "grep -q 'return \\[1\\]' src/api/users.py && test -s src/api/helper.py"  # it sees the leaf's work
        " && echo check >> src/api/users.py && echo check >> src/api/helper.py && echo x > src/api/new.py"
        " && echo check >> README.md && rm src/db/schema.py && echo x > by_the_check.txt"
    )
    plan.propose(store, [api_node(check=check)], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "src/api/helper.py").write_text("HELP = 1\n")
    left = files_in(repo)
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
    assert plan.finish(store, "n1", BOT).state == DONE
    assert files_in(repo) == left
    after = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
    assert after.stdout == status.stdout
    [ended] = store.node_log("n1", ("finished",))
    assert ended["detail"]["changed"] == ["src/api/helper.py", "src/api/users.py"]
    assert no_check_tree_left(store, repo)


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file whatever its mode")
def test_a_check_git_cannot_make_a_worktree_for_is_a_failed_check_and_not_a_crash(store, repo):
    """The check's worktree is made by git: when git cannot read the leaf's state, the check did not
    run, which is no pass, and it is said as a refusal (a sub-goal's stays open with it in its log)."""
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "src/api/unreadable.py").write_text("x = 1\n")
    (repo / "src/api/unreadable.py").chmod(0)
    try:
        with pytest.raises(Refused, match=r"`true` failed:\nthe check could not be run: git add -A failed"):
            plan.finish(store, "n1", BOT)
    finally:
        (repo / "src/api/unreadable.py").chmod(0o644)
    assert plan.get(store, "n1").state == RUNNING and no_check_tree_left(store, repo)


def test_what_git_ignores_is_not_in_the_checks_worktree_and_the_check_cannot_change_it(store, repo):
    """A .venv linked into the check's worktree from the checkout was the check's to change: `uv run`
    there re-installed the project into it, which left the checkout's .venv pointing at a worktree
    that was then deleted; and git counted the link as a new file, so a check that wants a clean
    `git status` failed there and passed in the checkout. The check makes its own environment."""
    (repo / ".gitignore").write_text(".venv/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore the environment")
    (repo / ".venv").mkdir()
    (repo / ".venv/project").write_text(f"{repo}\n")  # where an editable install says the project is
    check = 'test -z "$(git status --porcelain)" && test ! -e .venv && mkdir .venv && pwd > .venv/project'
    plan.propose(store, [api_node(check=check)], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    assert plan.finish(store, "n1", BOT).state == DONE
    assert (repo / ".venv/project").read_text() == f"{repo}\n" and no_check_tree_left(store, repo)


def test_a_check_runs_none_of_the_persons_git_hooks(store, repo):
    """Making the check's worktree ran the person's post-checkout hook, once a check, and a hook that
    failed made every check "could not be run": the check's result is the check's own."""
    ran = repo / ".git" / "hook.ran"
    (repo / ".git/hooks").mkdir(exist_ok=True)
    (repo / ".git/hooks/post-checkout").write_text(f"#!/bin/sh\ntouch {ran}\nexit 1\n")
    (repo / ".git/hooks/post-checkout").chmod(0o755)
    assert plan.run_check("true", repo) == (True, "exit 0, no output", [])
    assert not ran.exists() and no_check_tree_left(store, repo)


def slow_checkout(repo, said) -> None:
    """Every checkout of the repo now takes a second and a half, and then writes ``said``: a stand-in
    for a repository large enough that making a worktree takes a while (300,000 files: 39 s)."""
    (repo / ".gitattributes").write_text("*.slow filter=slow\n")
    (repo / "a.slow").write_text("slow\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "slow")
    git(repo, "config", "filter.slow.smudge", f"sleep 1.5; touch {said}; cat")


def test_the_checks_time_limit_covers_making_its_worktree_and_what_git_started_ends_with_it(
    store, repo, monkeypatch
):
    """Making the worktree was held to a cap of git's own (30 s), apart from the check's: on a large
    repository a check that passes was refused as "could not be run". Killed at that cap, git left
    its worktree registered and locked, and the `git reset` it had started wrote on after the call."""
    checked_out = repo / ".git" / "checked-out"
    slow_checkout(repo, checked_out)
    monkeypatch.setattr(plan, "CHECK_TIMEOUT", 0.5)
    assert plan.run_check("true", repo) == (False, "timed out after 0.5 s", [])
    time.sleep(2)  # longer than the checkout would have taken
    assert not checked_out.exists() and no_check_tree_left(store, repo)


def test_a_run_stopped_while_the_checks_worktree_is_made_stops_the_check(store, repo):
    """A stop (``end_checks``) that came while git made the check's worktree was lost: nothing was
    running yet for it to end, and the check ran to its end after the stop, and could pass."""
    checked_out, ran = repo / ".git" / "checked-out", repo / ".git" / "check.ran"
    slow_checkout(repo, checked_out)

    def stop_it():  # once git is writing the worktree
        until = time.monotonic() + 20
        while not list(repo.glob(".graphene/worktrees/.check-*/tree/.git")) and time.monotonic() < until:
            time.sleep(0.01)
        plan.end_checks()

    threading.Thread(target=stop_it).start()
    with pytest.raises(KeyboardInterrupt):
        plan.run_check(f"touch {ran}", repo)
    time.sleep(2)
    assert not ran.exists() and not checked_out.exists() and no_check_tree_left(store, repo)


def test_a_stop_between_two_steps_of_making_the_worktree_stops_the_check(store, repo, monkeypatch):
    """A stop that comes while no step of the check is running, between two of git's, still stops it."""
    ran, real = repo / ".git" / "check.ran", plan.head

    def stopped_meanwhile(checkout):
        plan.end_checks()
        return real(checkout)

    monkeypatch.setattr(plan, "head", stopped_meanwhile)
    with pytest.raises(KeyboardInterrupt):
        plan.run_check(f"touch {ran}", repo)
    assert not ran.exists() and no_check_tree_left(store, repo)


def test_a_check_begun_after_a_stop_runs(store, repo):
    plan.end_checks()
    assert plan.run_check("true", repo)[0]


def test_a_tracked_file_outside_the_scope_is_refused_before_the_check_runs(store, repo, monkeypatch):
    plan.propose(store, [python_leaf()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "README.md").write_text("changed\n")
    (repo / "notes.txt").write_text("x\n")
    monkeypatch.setattr(plan, "run_check", lambda *a: pytest.fail("the check ran"))
    with pytest.raises(Refused, match=r"\n  README.md, notes.txt\n"):
        plan.finish(store, "n1", BOT)
    assert (repo / "notes.txt").exists()


def test_files_git_ignores_never_count(store, repo):
    (repo / ".gitignore").write_text("*.log\nbuild/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore logs")
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "debug.log").write_text("x\n")
    (repo / "build").mkdir()
    (repo / "build/out.o").write_text("x\n")
    assert plan.finish(store, "n1", BOT).state == DONE
    assert store.node_log("n1", ("finished",))[0]["detail"]["changed"] == ["src/api/users.py"]


def test_deleting_a_leftover_that_was_there_when_the_hold_started_is_not_a_change(store, repo, finish):
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["README.md"])], ALEX)
    (repo / "cache").mkdir()
    (repo / "cache/old.pyc").write_text("left by an earlier check\n")
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    plan.start(store, "b", BOT, repo)
    assert "cache/old.pyc" in plan.get(store, "b").dirty_at_start
    (repo / "cache/old.pyc").unlink()  # as a refusal told it to
    (repo / "README.md").write_text("# toy, documented\n")
    assert plan.finish(store, "b", BOT).state == DONE
    assert plan.unowned(store, repo) == []  # and between nodes it is no loose change either


def test_deleting_a_tracked_file_or_reverting_the_persons_edit_still_counts(store, repo):
    (repo / "src/db/schema.py").write_text("TABLES = ['the person was here']\n")  # uncommitted
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    git(repo, "checkout", "--", "src/db/schema.py")  # wipes the person's uncommitted edit
    (repo / "README.md").unlink()
    with pytest.raises(Refused, match=r"\n  README.md, src/db/schema.py\n"):
        plan.finish(store, "n1", BOT)


def test_a_persons_commit_is_not_a_loose_change_and_an_uncommitted_one_is(store, repo, finish):
    """A .gitignore the person committed between leaves blocked every start until `plan ack`."""
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a's work")
    (repo / ".gitignore").write_text("__pycache__/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore caches")
    assert plan.unowned(store, repo) == []
    (repo / "notes.txt").write_text("mine\n")
    assert plan.unowned(store, repo) == ["notes.txt"]
    said = (
        "b cannot start: the checkout has an uncommitted change no node made\n"
        "  notes.txt\n"
        "  put it back, or ask the person: graphene plan ack makes it theirs as it stands, and so does "
        "committing it"
    )
    with pytest.raises(Refused) as first:
        plan.start(store, "b", BOT, repo)
    assert str(first.value) == said
    with pytest.raises(Refused) as again:  # said once: the second time is short
        plan.start(store, "b", BOT, repo)
    assert str(again.value).endswith("\n  put it back, or ask the person: graphene plan ack")
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-qm", "my notes")  # committing it does what ack does
    assert plan.start(store, "b", BOT, repo).state == RUNNING


def test_a_refusal_lectures_once_in_a_hold_and_again_in_the_next(store, repo):
    plan.propose(store, [api_node()], ALEX)
    plan.start(store, "n1", BOT, repo)
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "README.md").write_text("stray\n")
    said = []
    for _ in range(2):
        with pytest.raises(Refused) as no:
            plan.finish(store, "n1", BOT)
        said.append(str(no.value))
    base = plan.get(store, "n1").base_sha[:10]
    assert said[0] == (
        "n1 is not done: changed outside its scope (src/api/**, tests/**), which only the person widens\n"
        "  README.md\n"
        f"  put it back (git checkout {base} -- <path>, or delete a new file), or say why: "
        "graphene node release n1 --why '…'"
    )
    assert said[1] == (
        "n1 is not done: changed outside its scope (src/api/**, tests/**)\n"
        "  README.md\n"
        "  put it back, or say why: graphene node release n1 --why '…'"
    )
    with pytest.raises(Refused) as other:  # another caller meets it for the first time
        plan.finish(store, "n1", ALEX)
    assert "which only the person widens" in str(other.value)
    git(repo, "checkout", "--", "README.md")
    plan.release(store, "n1", BOT, "the README is mine to change")
    plan.start(store, "n1", BOT, repo)
    (repo / "README.md").write_text("stray again\n")
    with pytest.raises(Refused, match="which only the person widens"):  # a new hold: said again
        plan.finish(store, "n1", BOT)


def test_a_refusal_lists_the_paths_that_fit_and_counts_the_rest():
    said = str(plan.refusal("x is not done", [f"src/module_{k}/file.py" for k in range(40)], "do this"))
    what, paths, do = said.split("\n")
    assert what == "x is not done" and do == "  do this"
    assert paths.startswith("  src/module_0/file.py, ") and paths.endswith(" more")
    assert len(paths) <= plan.WIDE + 2
