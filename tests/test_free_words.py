# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""What the CLI says on its own, unasked: the first step first, one word for a unit of work, and what a
run may cost before it starts."""

from test_plan_cli import person, repo  # noqa: F401  (fixtures)


def test_bare_graphene_in_a_new_repo_names_init_before_ask_and_is_no_error(repo):
    """A stranger's first ten minutes: bare `graphene` named `init` last, after the `ask` that refuses
    until it has run, and exited 1, as if an empty plan were a failure."""
    plain = person()
    said = " ".join(plain.output.split())
    assert plain.exit_code == 0, said
    assert said.startswith("nothing is planned here yet. Start with `graphene init`")
    assert said.index("graphene init") < said.index("graphene ask")


def test_a_finished_plan_says_every_leaf_is_done(repo):
    """The screen and the README say leaf; the next line said "every node is done"."""
    assert person("node", "add", "one", "--id", "l1", "--scope", "api.py", "--check", "true").exit_code == 0
    assert person("node", "start", "l1").exit_code == 0
    (repo / "api.py").write_text("def users():\n    return [1]\n")
    done = person("node", "done", "l1")
    assert "next: nothing; every leaf is done" in done.stdout, done.output
