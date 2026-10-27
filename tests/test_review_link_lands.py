"""A write through a symbolic link inside the repo is judged by where it lands, not how it is spelled. A
repo can ship `docs/g -> ../.git` and `docs/cfg -> ../.claude`, tracked by git; a leaf scoped `docs/**` could
then write `docs/g/hooks/pre-commit`, which is `.git/hooks/pre-commit` (a hook that runs on the person's next
commit, and git status never shows it), and `docs/cfg/settings.json`, which holds Graphene's own hooks."""

import os
import subprocess

import pytest
from test_gate import ALEX, BOT, bash, reason, write

from graphene_map import plan
from graphene_map.store import Store


@pytest.fixture
def linked(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/readme.md").write_text("read me\n")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text('{"hooks": {}}\n')
    os.symlink("../.git", tmp_path / "docs/g")  # relative, as a hostile repo ships them
    os.symlink("../.claude", tmp_path / "docs/cfg")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")
    return tmp_path


def holding(repo, scope, aside=False):
    with Store.open(repo) as store:
        [n] = plan.propose(store, [{"title": "docs", "scope": scope, "check": "true"}], ALEX,
                           files=plan.tracked(repo), aside=aside)  # fmt: skip
        plan.start(store, n.id, BOT, repo, attended=True)


def test_a_link_into_git_is_refused_as_git_is_whatever_its_spelling(linked):
    holding(linked, ["docs/**"])
    assert write(linked, "docs/readme.md") is None
    for answer in (write(linked, "docs/g/hooks/pre-commit"),
                   bash(linked, "echo evil > docs/g/hooks/pre-commit"),
                   bash(linked, "cp docs/readme.md docs/g/hooks/post-checkout")):  # fmt: skip
        assert plan.GIT_OWN in reason(answer), answer
    assert not (linked / ".git/hooks/pre-commit").exists()


def test_a_link_into_the_agents_settings_is_judged_as_those_settings(linked):
    holding(linked, ["docs/**"])
    said = reason(write(linked, "docs/cfg/settings.json"))
    assert ".claude/settings.json is outside the scope of the node you hold" in said
    assert "outside the scope" in reason(bash(linked, "echo '{}' > docs/cfg/settings.json"))


def test_a_prompts_leaf_does_not_reach_the_hooks_through_a_link(linked):
    holding(linked, ["**"], aside=True)
    assert "holds the hooks that keep this plan" in reason(write(linked, "docs/cfg/settings.json"))
    assert "holds the hooks that keep this plan" in reason(bash(linked, "echo '{}' > docs/cfg/settings.json"))
