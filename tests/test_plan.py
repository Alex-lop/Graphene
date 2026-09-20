"""The plan binds at the boundary, whoever executes a node: `finish` asks git what changed and runs
the check itself. A real git repo in every test, because git is the mechanism."""

import subprocess

import pytest

from graphene_debrief import plan
from graphene_debrief.plan import AGENT, DONE, OPEN, PROPOSED, REVIEW, RUNNING, Caller, Refused
from graphene_debrief.store import Store

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


def test_start_is_refused_until_what_it_waits_on_is_done(store, repo):
    plan.propose(store, [api_node(id="a"), api_node(id="b", needs=["a"], scope=["README.md"])], ALEX)
    with pytest.raises(Refused, match=r"b waits on a \(open\)"):
        plan.start(store, "b", BOT, repo)
    plan.start(store, "a", BOT, repo)
    with pytest.raises(Refused, match=r"b waits on a \(running\)"):
        plan.start(store, "b", BOT2, repo)
    plan.finish(store, "a", BOT)
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
    with pytest.raises(Refused, match=r"outside its scope .*: notes.txt, src/db/schema.py"):
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


def test_a_sign_off_node_waits_in_review_and_only_a_person_signs(store, repo):
    plan.propose(
        store, [api_node(signoff=True), api_node(title="after", needs=["n1"], scope=["README.md"])], ALEX
    )
    plan.start(store, "n1", BOT, repo)
    assert plan.finish(store, "n1", BOT).state == REVIEW
    with pytest.raises(Refused, match=r"n2 waits on n1 \(review\)"):
        plan.start(store, "n2", BOT, repo)
    with pytest.raises(Refused, match="person's to do"):
        plan.signoff(store, "n1", BOT)
    assert plan.signoff(store, "n1", ALEX).state == DONE
    assert plan.start(store, "n2", BOT, repo).state == RUNNING


def test_reopen_sends_it_back_with_a_note_the_next_executor_is_told(store, repo):
    plan.propose(store, [api_node(signoff=True)], ALEX)
    plan.start(store, "n1", BOT, repo)
    plan.finish(store, "n1", BOT)
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
        "override": "the README edit was mine",
        "outside": ["README.md"],
        "check_passed": False,
    }


def test_a_node_beside_it_in_the_same_checkout_is_not_its_stray_change(store, repo):
    plan.propose(store, [api_node(id="a"), api_node(id="b", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    plan.start(store, "b", BOT2, repo)
    (repo / "README.md").write_text("# b's work\n")
    plan.finish(store, "b", BOT2)
    assert plan.finish(store, "a", BOT).state == DONE


def test_a_paused_plan_binds_nobody_and_starts_nothing(store, repo):
    plan.propose(store, [api_node()], ALEX)
    assert plan.in_force(store)
    with pytest.raises(Refused, match="person's to do"):
        plan.set_paused(store, True, BOT)
    plan.set_paused(store, True, ALEX)
    assert not plan.in_force(store)
    with pytest.raises(Refused, match="paused"):
        plan.start(store, "n1", BOT, repo)


# -- who is asking ------------------------------------------------------------------------------------


def test_an_agents_shell_is_not_a_person():
    assert plan.caller({"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "abcdef1234"}) == Caller(
        "claude:abcdef12", False, "abcdef1234"
    )
    assert plan.caller({"USER": "Alex"}) == Caller("alex", True, None)
    assert plan.caller({"USER": "alex", "GRAPHENE_AS": "person:sam"}).person
    assert plan.caller({"AI_AGENT": "codex_1"}).person is False
    assert plan.caller({"GRAPHENE_AS": "agent:codex"}) == Caller("codex", False, None)


def test_the_contract_is_what_an_executor_is_told(store):
    [node] = plan.propose(store, [api_node(goal="GET /users returns them", signoff=True)], ALEX)
    text = plan.contract(node)
    assert "n1 (revision 1): users endpoint" in text
    assert "`true` passes and a person signs it off" in text
    assert "graphene node done n1" in text and "graphene node release n1" in text
    assert node.owner == AGENT
