# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene node diff ID [--fork X] --json`: the two revisions and each file's status, for an editor's own
diff editor; a running task, or a running fork, is its own directory against its base and no longer refused.
The contract's section "The CLI", shape 3."""

import json
import os
import signal

from test_forks_run import FORKED, executor, git, go, person, seed
from test_run_live import graphene_run, leaf, repo, states, wait_for  # noqa: F401
from test_state_json import ALEX, BOT

from graphene_map import plan
from graphene_map import run as R
from graphene_map.plan import RUNNING
from graphene_map.store import Store

WRITES_THEN_WAITS = """
import os, pathlib, time
pathlib.Path("api.py").write_text(f"def users():\\n    return ids  # fork {os.environ['GRAPHENE_FORK']}\\n")
pathlib.Path("new.txt").write_text("new\\n")
time.sleep(60)
"""


def diff(*args) -> dict:
    said = person("node", "diff", *args, "--json")
    assert said.exit_code == 0, said.output + said.stderr
    assert said.stdout.count("\n") == 1
    return json.loads(said.stdout)


def test_a_running_task_is_its_directory_against_its_base_new_files_included(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
    (repo / "a.txt").write_text("a, changed\n")
    (repo / "fresh.txt").write_text("new\n")
    head = git(repo, "rev-parse", "HEAD").strip()
    said = diff("a")
    assert said["repo"] == str(repo.resolve()) and said["left"] == head and said["right"] is None
    assert said["files"] == [{"path": "a.txt", "status": "M", "old": None},
                             {"path": "fresh.txt", "status": "A", "old": None}]  # fmt: skip
    assert said["said"] == []
    text = person("node", "diff", "a")  # the text form shows the same, where it was refused before
    assert text.exit_code == 0 and "+a, changed" in text.stdout and "fresh.txt" in text.stdout


def test_a_running_forks_copy_is_shown_against_the_holds_base_and_the_leafs_own_tree_too(repo, monkeypatch):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    base = seed(repo, monkeypatch)
    run = graphene_run(repo, "--forks", "2", "--with", executor(repo, WRITES_THEN_WAITS))
    try:
        assert wait_for(lambda: states(repo) == {"n1": RUNNING}), run.stdout
        trees = repo / ".graphene" / "worktrees"
        assert wait_for(lambda: all((trees / f"n1.{b}" / "new.txt").exists() for b in "ab"))
        for letter in "ab":
            said = diff("n1", "--fork", letter)
            assert said["repo"] == str(trees / f"n1.{letter}") and said["left"] == base
            assert said["right"] is None and said["said"] == []
            assert said["files"] == [{"path": "api.py", "status": "M", "old": None},
                                     {"path": "new.txt", "status": "A", "old": None}]  # fmt: skip
            text = person("node", "diff", "n1", "--fork", letter).stdout
            assert f"# fork {letter}" in text
        own = diff("n1")  # the leaf's own tree, where the kept fork's changes land: nothing in it yet
        assert own["repo"] == str(trees / "n1") and own["left"] == base and own["files"] == []
    finally:
        os.kill(run.pid, signal.SIGINT)
        run.wait(30)


def test_a_landed_leaf_is_its_merge_and_each_forks_ref_is_what_it_tried(repo, monkeypatch):
    seed(repo, monkeypatch)
    go(repo, FORKED, [], forks=R.Forks(3))
    said = diff("n1")
    head = git(repo, "rev-parse", "HEAD").strip()
    assert said["repo"] == str(repo) and said["right"] == head
    assert said["left"] == git(repo, "rev-parse", "HEAD^1").strip()
    assert said["files"] == [{"path": "api.py", "status": "M", "old": None}]  # b, the kept one
    c = diff("n1", "--fork", "c")
    assert c["left"] and c["right"] and c["left"] != c["right"] and len(c["right"]) == 40
    assert c["files"] == [{"path": "api.py", "status": "M", "old": None},
                          {"path": "notes.txt", "status": "D", "old": None}]  # fmt: skip
    gone = person("node", "diff", "n1", "--fork", "z", "--json")
    assert gone.exit_code == 1 and gone.stdout == "" and "has no fork z" in gone.stderr


def test_a_rename_names_the_old_path(repo):
    (repo / "long.txt").write_text("".join(f"line {k}\n" for k in range(40)))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "long")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "*.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
    (repo / "long.txt").rename(repo / "moved.txt")
    said = diff("a")
    assert said["files"] == [{"path": "moved.txt", "status": "R", "old": "long.txt"}]


def test_nothing_to_show_is_exit_1_with_the_refusal_on_stderr_and_nothing_on_stdout(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    said = person("node", "diff", "a", "--json")
    assert said.exit_code == 1 and said.stdout == "" and "nothing has run yet" in said.stderr
    with Store.open(repo) as store:  # running, and its directory is gone: nothing to read yet
        plan.start(store, "a", BOT, repo)
        store.put_node({**store.node_row("a"), "checkout": str(repo / "gone")})
    said = person("node", "diff", "a", "--json")
    assert said.exit_code == 1 and said.stdout == "" and "nothing to show yet" in said.stderr


def test_the_flag_has_help_in_the_budget_and_the_reference_names_it():
    import typer.main

    from graphene_map.cli import build

    node = typer.main.get_command(build()).commands["node"].commands["diff"]
    (flag,) = [p for p in node.params if p.name == "as_json"]
    assert len(flag.help) <= 80 and "JSON" in flag.help
    how = (__import__("pathlib").Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text()
    assert "`graphene node diff ID --json`" in how
