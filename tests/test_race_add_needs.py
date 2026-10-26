# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene node set ID --add-needs OTHER`: a link on the graph. It adds to what a node waits on without
replacing it, refuses a cycle with its reason as `--needs` does, and is the person's as every edit is."""

from test_plan_cli import agent, person, repo  # noqa: F401  (repo: a fixture)

from graphene_map import plan
from graphene_map.store import Store


def three(repo):
    for node_id in ("a", "b", "c"):
        done = person("node", "add", node_id, "--id", node_id, "--scope", f"{node_id}.py", "--check", "true")
        assert done.exit_code == 0, done.output


def needs(repo, node_id):
    with Store.open(repo) as store:
        return plan.get(store, node_id).needs


def test_add_needs_adds_to_what_a_node_waits_on_and_keeps_what_it_waited_on(repo):
    three(repo)
    done = person("node", "set", "b", "--add-needs", "a")
    assert done.exit_code == 0 and "needs: none → a" in done.output, done.output
    assert needs(repo, "b") == ["a"]
    done = person("node", "set", "b", "--add-needs", "c", "--add-needs", "c")  # repeatable; twice is once
    assert done.exit_code == 0 and needs(repo, "b") == ["a", "c"], done.output
    again = person("node", "set", "b", "--add-needs", "a")  # already waits on it: nothing to change
    assert again.exit_code == 0 and "is unchanged" in again.output and needs(repo, "b") == ["a", "c"]
    assert person("node", "set", "b", "--needs", "c").exit_code == 0 and needs(repo, "b") == ["c"]  # replaces


def test_a_link_that_makes_a_cycle_is_refused_with_its_reason(repo):
    three(repo)
    assert person("node", "set", "b", "--add-needs", "a").exit_code == 0
    refused = person("node", "set", "a", "--add-needs", "b")
    assert refused.exit_code == 1 and "the plan has a cycle" in refused.stderr, refused.stderr
    assert "a -> b -> a" in refused.stderr and needs(repo, "a") == []
    missing = person("node", "set", "a", "--add-needs", "zz")
    assert missing.exit_code == 1 and "zz, which is not in the plan" in missing.stderr


def test_needs_and_add_needs_together_are_one_or_the_other(repo):
    three(repo)
    both = person("node", "set", "b", "--needs", "a", "--add-needs", "c")
    assert both.exit_code == 2 and "one or the other" in both.stderr


def test_only_a_person_links_as_only_a_person_edits(repo):
    three(repo)
    refused = agent("node", "set", "b", "--add-needs", "a")
    assert refused.exit_code == 1 and needs(repo, "b") == []
    assert "editing a node's contract" in refused.stderr


def test_add_needs_is_in_the_help_within_its_budget(repo):
    said = " ".join(person("node", "set", "--help").output.replace("│", " ").split())
    assert "--add-needs" in said and "Adds a node it waits on; repeat it." in said
