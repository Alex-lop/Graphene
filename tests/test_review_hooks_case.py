# ruff: noqa: F811  (pytest fixtures imported from test_gate are named again as arguments)
"""The hooks' settings are guarded as a Mac's disk reaches them. A leaf made from a prompt (scope `**`) does
not reach `.claude/settings.json`, which holds the hooks that keep the plan; on a disk that ignores case
`.CLAUDE/settings.json` and `.claude/Settings.json` are the same file, so they are guarded too, as `.git/`
and `.graphene/` already are."""

import pytest
from test_gate import ALEX, BOT, bash, reason, repo, write  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map.store import Store


@pytest.fixture
def aside(repo):
    with Store.open(repo) as store:
        [n] = plan.propose(store, [{"title": "a prompt", "scope": ["**"], "check": "true"}], ALEX, aside=True)
        plan.start(store, n.id, BOT, repo, attended=True)
    return repo


@pytest.mark.parametrize("rel", [".claude/settings.json", ".CLAUDE/settings.json", ".claude/Settings.json",
                                 ".Claude/settings.local.json", ".claude/SETTINGS.LOCAL.JSON"])  # fmt: skip
def test_a_prompts_leaf_does_not_reach_the_hooks_settings_in_any_case(aside, rel):
    assert "holds the hooks that keep this plan" in reason(write(aside, rel))
    assert "holds the hooks that keep this plan" in reason(bash(aside, f"echo '{{}}' > {rel}"))


def test_the_rest_of_the_agents_directory_is_the_prompts_leafs_to_write(aside):
    assert write(aside, ".claude/commands/review.md") is None
