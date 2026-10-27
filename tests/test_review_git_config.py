# ruff: noqa: F811  (pytest fixtures imported from test_gate are named again as arguments)
"""Git's configuration is nobody's to change from a task. `.git/hooks/` is refused, but git also runs hooks
from `core.hooksPath`, and `git config` writes .git/config, which every worktree shares with the person's
checkout (`--global` writes their ~/.gitconfig): a hooksPath, a pager, an alias or a filter set there runs a
command on their machine at their next commit. The shell reader never saw `git config` as a write."""

import pytest
from test_gate import bash, holding, reason, repo  # noqa: F401  (fixtures)


@pytest.mark.parametrize("command", [
    "git config core.hooksPath src/.hooks",
    "git config --local core.hookspath src/.hooks",
    "git config --global core.hooksPath /tmp/hooks",
    "git -C . config set core.hooksPath src/.hooks",
    "git config alias.st '!sh /tmp/evil.sh'",
    "git config --add core.pager 'sh /tmp/evil.sh'",
    "git config --unset core.hooksPath",
    "git config -e",
    "cd src && git config core.hooksPath .hooks",
])  # fmt: skip
def test_a_git_config_that_writes_is_refused_while_a_leaf_is_held(repo, command):
    holding(repo)
    said = reason(bash(repo, command))
    assert "git's own configuration" in said and "runs a command on the person's machine" in said


@pytest.mark.parametrize("command", [
    "git -c core.hooksPath=src/.hooks commit -qm x",
    "git -c core.hookspath=src/.hooks -C . status",
    "git --config-env=core.hooksPath=H commit -qm x",
    "GIT_CONFIG_PARAMETERS=\"'core.hooksPath=src/.hooks'\" git commit -qm x",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=src/.hooks git commit -qm x",
])  # fmt: skip
def test_a_hooks_path_set_for_one_command_or_in_the_environment_is_refused(repo, command):
    holding(repo)
    assert "core.hooksPath" in reason(bash(repo, command))


@pytest.mark.parametrize("command", [
    "git config --get core.hooksPath",
    "git config --list",
    "git config -l --show-origin",
    "git config user.name",
    "git config get core.hooksPath",
    "git commit -qm 'note: core.hooksPath stays unset'",
    "grep -rn hooksPath src/",
    "git status",
])  # fmt: skip
def test_a_read_of_the_configuration_and_a_mention_of_the_words_pass(repo, command):
    holding(repo)
    assert bash(repo, command) is None


def test_without_a_plan_in_force_the_hook_still_says_nothing(repo):
    assert bash(repo, "git config core.hooksPath src/.hooks") is None
