# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The standing conditions bind the gate: a scope that covers a protected path or a read-only glob
is refused at propose and at edit, a change to one is refused at `done` before the check runs, and
an aside's `**` leaves them out instead of being refused."""

import pytest
from test_plan import ALEX, BOT, api_node, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map import settings as S
from graphene_map.plan import DONE, Refused
from graphene_map.store import Store


@pytest.fixture
def ruled(store):
    S.apply(store, "protected: src/db/**\nreadonly: README.md\n", ALEX)
    return store


@pytest.mark.parametrize(
    "scope, setting, path",
    [
        (["src/**"], "protected", "src/db/schema.py"),
        (["src/db/schema.py"], "protected", "src/db/schema.py"),
        (["**"], "protected", "src/db/schema.py"),
        (["README.md"], "readonly", "README.md"),
    ],
)
def test_propose_refuses_a_scope_that_covers_a_standing_path(ruled, repo, scope, setting, path):
    with pytest.raises(Refused) as no:
        plan.propose(ruled, [api_node(id="a", scope=scope)], BOT, files=plan.tracked(repo))
    assert setting in str(no.value) and path in str(no.value)
    assert plan.nodes(ruled) == []


def test_a_scope_clear_of_them_is_proposed_and_an_edit_into_them_is_refused(ruled, repo):
    plan.propose(ruled, [api_node(id="a")], ALEX, files=plan.tracked(repo))
    with pytest.raises(Refused, match="protected.*src/db/"):
        plan.edit(ruled, "a", {"scope": ["src/**"]}, ALEX, files=plan.tracked(repo))
    with pytest.raises(Refused, match="readonly"):  # also when the text form validates afterwards
        plan.edit(ruled, "a", {"scope": ["README.md"]}, ALEX, check=False)
    assert plan.get(ruled, "a").scope == api_node()["scope"]


def test_done_refuses_a_changed_standing_path_before_the_check_runs(ruled, repo):
    plan.propose(ruled, [api_node(id="a", check="touch ran")], ALEX)
    plan.start(ruled, "a", BOT, repo)
    (repo / "src/api/users.py").write_text("x = 1\n")
    (repo / "README.md").write_text("# changed\n")
    with pytest.raises(Refused) as no:
        plan.finish(ruled, "a", BOT)
    assert "readonly: README.md" in str(no.value) and "README.md" in str(no.value)
    assert not (repo / "ran").exists()
    (repo / "README.md").write_text("# toy\n")
    assert plan.finish(ruled, "a", BOT).state == DONE


def test_an_asides_everything_leaves_them_out_and_is_not_refused(ruled, repo):
    (typed,) = plan.propose(ruled, [{"id": "t", "title": "typo", "scope": ["**"]}], ALEX, aside=True)
    assert plan.as_scoped(typed, plan.standing(ruled)) == ["**", "!src/db/**", "!README.md"]
    plan.start(ruled, "t", ALEX, repo)
    (repo / "src/db/schema.py").write_text("TABLES = [1]\n")
    (repo / "src/api/users.py").write_text("x = 1\n")
    plan.close_aside(ruled, "t", ALEX)
    (last,) = ruled.node_log("t", ("finished",))
    assert last["detail"]["outside"] == ["src/db/schema.py"]


def test_an_aside_is_refused_a_write_to_a_standing_path_by_the_hook(tmp_path):
    import test_gate as G

    repo = G.repo.__wrapped__(tmp_path)
    (repo / "README.md").write_text("# toy\n")
    with Store.open(repo) as store:
        S.apply(store, "protected: src/db/**\nreadonly: README.md\n", ALEX)
        plan.propose(store, [{"title": "other", "scope": ["src/api/**"], "check": "true"}], ALEX)
    G.plan_first(repo, "off")
    G.hook(repo, "UserPromptSubmit", prompt="fix the schema and the readme")
    assert "protected: src/db/**" in G.reason(G.write(repo, "src/db/schema.py"))
    assert "readonly: README.md" in G.reason(G.bash(repo, "echo x > README.md"))
    assert G.write(repo, "src/api/users.py") is None  # the rest of its `**` is still its own


def test_an_aside_that_types_a_standing_scope_is_refused_like_any_leaf(ruled, repo):
    with pytest.raises(Refused, match="protected: src/db/"):
        item = {"id": "t", "title": "t", "scope": ["src/db/**"]}
        plan.propose(ruled, [item], ALEX, files=plan.tracked(repo), aside=True)


def test_a_leaf_that_a_later_setting_covers_is_refused_at_start_naming_it(store, repo):
    plan.propose(store, [api_node(id="a", scope=["src/**"])], ALEX, files=plan.tracked(repo))
    S.apply(store, "protected: src/db/**\n", ALEX)
    with pytest.raises(Refused, match="protected: src/db/"):
        plan.start(store, "a", BOT, repo)
    assert plan.get(store, "a").state == "open"


def _ignored_env(tmp_path):
    """The README's own example: `.env` is protected and git ignores it."""
    import test_gate as G

    repo = G.repo.__wrapped__(tmp_path)
    (repo / ".gitignore").write_text("build/\n.env\n")
    (repo / ".env").write_text("SECRET=real\n")
    with Store.open(repo) as store:
        S.apply(store, "protected: .env\n", ALEX)
    G.holding(repo)
    return G, repo


def test_a_shell_write_to_a_protected_path_git_ignores_is_refused(tmp_path):
    """A build leftover git ignores is nobody's change, but a standing path is never a leftover."""
    G, repo = _ignored_env(tmp_path)
    assert G.write(repo, ".env") is not None
    for command in ("echo pwned > .env", "cp /dev/null .env"):
        assert "protected: .env" in G.reason(G.bash(repo, command))
    assert G.bash(repo, "echo x > build/out.txt") is None  # a leftover is still nobody's
    changed = {"changedFiles": [str(repo / ".env")]}
    after = G.hook(repo, "PostToolUse", tool_name="Bash", tool_response={"bashEditDiff": changed})
    assert after is not None and after["decision"] == "block" and ".env" in after["reason"]


def test_done_refuses_a_changed_protected_path_git_ignores(tmp_path):
    """git never reports it, so `done` compares it with what it was when the leaf was started."""
    G, repo = _ignored_env(tmp_path)
    (repo / "src/api/users.py").write_text("x = 1\n")
    (repo / ".env").write_text("SECRET=pwned\n")
    with Store.open(repo) as store:
        with pytest.raises(Refused, match=r"it changed \.env, which the setting `protected: \.env`"):
            plan.finish(store, "n1", G.BOT)
    (repo / ".env").write_text("SECRET=real\n")
    with Store.open(repo) as store:
        assert plan.finish(store, "n1", G.BOT).state == DONE


def test_an_asides_record_never_calls_a_standing_path_in_scope(ruled, repo):
    """An aside is a record, not a fence, so it closes; its record judges the scope as it binds, as the
    store's own `outside` does, and never calls a protected path in scope."""
    from graphene_map import node_record as NR

    plan.propose(ruled, [{"id": "t", "title": "typo", "scope": ["**"]}], ALEX, aside=True)
    plan.start(ruled, "t", ALEX, repo)
    (repo / "src/db/schema.py").write_text("TABLES = [1]\n")
    (repo / "src/api/users.py").write_text("x = 1\n")
    plan.close_aside(ruled, "t", ALEX)
    lines = NR.render(NR.node_record(ruled, repo, plan.get(ruled, "t")))
    assert "    outside the scope: src/db/schema.py  (git, when it ended)" in lines
    assert "    in scope: src/api/users.py  (git, when it ended)" in lines
    assert any("had changed under this node, 1 inside its scope" in line for line in lines)
    rolled = NR.rolled_up(ruled, repo, [plan.get(ruled, "t")])
    assert any("2 paths git said had changed under them, 1 inside the scope" in line for line in rolled)


def test_an_aside_is_refused_a_case_variant_of_a_standing_path(tmp_path):
    """On a Mac's disk SECRETS/a.txt is secrets/a.txt: the hook judges what the write reaches."""
    import test_gate as G

    repo = G.repo.__wrapped__(tmp_path)
    with Store.open(repo) as store:
        S.apply(store, "protected: src/db/**\n", ALEX)
        plan.propose(store, [{"title": "other", "scope": ["src/api/**"], "check": "true"}], ALEX)
    G.plan_first(repo, "off")
    G.hook(repo, "UserPromptSubmit", prompt="fix the schema")
    assert "protected: src/db/**" in G.reason(G.write(repo, "SRC/DB/schema.py"))
    assert "protected: src/db/**" in G.reason(G.bash(repo, "echo pwned > src/DB/schema.py"))
    assert G.write(repo, "src/api/users.py") is None
