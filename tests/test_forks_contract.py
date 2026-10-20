"""A leaf's `forks:` line and the `forks` setting: the contract field, the plan's text, `node add` and
`node set`, the contract an executor is told, and what refuses a number outside 1 to 8 or forks with no
check to keep one."""

import subprocess

import pytest
from typer.testing import CliRunner

from graphene_map import plan
from graphene_map import plan_text as T
from graphene_map import settings as S
from graphene_map.cli import build
from graphene_map.plan import Caller, Refused
from graphene_map.store import SCHEMA_VERSION, Store

ALEX = Caller("alex", True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_NODE"):
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "api.py").write_text("def users():\n    return []\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start"],
                   cwd=tmp_path, check=True)  # fmt: skip
    monkeypatch.chdir(tmp_path)
    return tmp_path


def person(*args):
    return CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})


def leaf(**extra):
    return {"id": "greet", "title": "greet says hello", "scope": ["api.py"], "check": "true", **extra}


def test_forks_is_a_number_from_one_to_eight_and_unsaid_it_is_not_stored():
    assert plan.from_dict(leaf(forks=3), "x").forks == 3
    assert plan.from_dict(leaf(forks="2"), "x").forks == 2  # the text form hands the number as written
    assert plan.from_dict(leaf(), "x").forks is None and plan.from_dict(leaf(forks=""), "x").forks is None
    for wrong in (0, 9, "nine", -1):
        with pytest.raises(Refused, match=f"forks is a number from 1 to 8, not {wrong!r}"):
            plan.from_dict(leaf(forks=wrong), "x")
    assert "forks" not in plan.to_dict(plan.from_dict(leaf(), "x"))
    assert plan.to_dict(plan.from_dict(leaf(forks=3), "x"))["forks"] == 3
    assert "forks" in plan.EDITABLE and SCHEMA_VERSION == 6  # an older graphene refuses the store in words


def test_more_than_one_fork_needs_a_check_since_a_sign_off_cannot_choose(repo):
    said = "greet: 3 forks need a check to keep one; a sign-off cannot choose"
    with Store.open(repo) as store:
        with pytest.raises(Refused, match=said):
            plan.propose(store, [leaf(check=None, signoff=True, forks=3)], ALEX)
        [n] = plan.propose(store, [leaf(signoff=True, forks=3)], ALEX)
        assert n.forks == 3
        with pytest.raises(Refused, match="greet: 3 forks need a check"):
            plan.edit(store, "greet", {"check": None}, ALEX)
        assert plan.edit(store, "greet", {"forks": 1}, ALEX).forks == 1  # one: the leaf's word over the run's
        assert plan.edit(store, "greet", {"check": None}, ALEX).forks == 1


def test_the_plan_text_reads_and_writes_the_forks_line(repo):
    text = "- greet says hello  [greet]\n    scope: api.py\n    check: true\n    forks: 3\n"
    with Store.open(repo) as store:
        T.apply(store, text, ALEX, None)
        assert plan.get(store, "greet").forks == 3
        shown, opened = T.render(store)
        assert "    forks: 3\n" in shown
        T.apply(store, shown.replace("    forks: 3\n", ""), ALEX, opened)  # the line deleted: unsaid again
        assert plan.get(store, "greet").forks is None
        shown, opened = T.render(store)
        assert "forks:" not in shown
        T.apply(store, shown.replace("check: true\n", "check: true\n    forks: 1\n"), ALEX, opened)
        assert plan.get(store, "greet").forks == 1 and "    forks: 1\n" in T.render(store)[0]
        with pytest.raises(Refused, match="line 4: forks is a number from 1 to 8, not 'nine'"):
            T.apply(store, text.replace("forks: 3", "forks: nine"), ALEX, None)
        with pytest.raises(Refused, match="line 4: forks is a number from 1 to 8, not '0'"):
            T.apply(store, text.replace("forks: 3", "forks: 0"), ALEX, None)
    assert "forks: 3 (agents at once, its check keeps one)" in T.HELP


def test_node_add_and_node_set_take_forks_and_the_contract_says_it_past_one(repo):
    added = person("node", "add", "greet", "--id", "greet", "--scope", "api.py", "--check", "true",
                   "--forks", "3")  # fmt: skip
    assert added.exit_code == 0, added.output
    shown = person("node", "show", "greet").stdout
    assert "  forks:  3   (agents at once, each in its own copy; its check keeps one)\n" in shown
    changed = person("node", "set", "greet", "--forks", "2")
    assert changed.exit_code == 0 and "  forks: 3 → 2" in changed.stdout, changed.output
    assert person("node", "set", "greet", "--forks", "9").exit_code == 2  # the option's own range
    assert person("node", "set", "greet", "--forks", "1").exit_code == 0
    assert "  forks:  1" not in person("node", "show", "greet").stdout  # one agent: nothing to say
    with Store.open(repo) as store:
        assert plan.get(store, "greet").forks == 1
        assert "forks:" not in plan.contract(plan.get(store, "greet"))
    refused = person("node", "add", "bye", "--scope", "bye.py", "--signoff", "--forks", "2")
    assert refused.exit_code == 1 and "2 forks need a check to keep one" in refused.output


def test_the_forks_setting_is_one_to_eight_and_one_is_unsaid_on_the_screen(repo):
    with Store.open(repo) as store:
        assert S.forks(store) == 1 and "forks: 1\n" in S.render(store)
        assert not any(line.startswith("forks") or "forks" in line for line in S.lines_for_screen(store))
        assert "# forks: 1 to 8 agents at once on every leaf" in S.render(store)
        S.apply(store, "forks: 3\n", ALEX)
        assert S.forks(store) == 3 and S.render(store).endswith("review: off\nforks: 3\n")
        assert "size: auto · board: auto · forks: 3" in S.lines_for_screen(store)
        [changed] = store.node_log("*", ("settings",))
        assert changed["detail"] == {"changed": {"forks": ["1", "3"]}}
        with pytest.raises(Refused, match="line 1: forks is 1, 2, 3, 4, 5, 6, 7 or 8, not '9'"):
            S.apply(store, "forks: 9\n", ALEX)
        with pytest.raises(Refused, match="the keys are protected, readonly, never, size, board, review, "
                                          "notify, forks"):
            S.apply(store, "fork: 2\n", ALEX)
        S.apply(store, "forks: 1\n", ALEX)
        assert S.forks(store) == 1 and store.meta("settings:forks") is None  # unset is one
