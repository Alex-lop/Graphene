# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""Surviving the judging period, against the recorded fake: judges may test until 15 December, Token
Factory retires models on notice, and Sandboxes are in beta. Every fault here ends the same way: the
leaf comes back with its cause in its record, the run goes on, nothing is left running, and the node
pane says what happened."""

from fake_tokenfactory import MODELS, Fake, call
from test_executor import NANO, SUPER, fake, leaf, plan_of, repo, run_one, script  # noqa: F401

from graphene_map import tokenfactory as tf
from graphene_map.ask import ask, named
from graphene_map.store import Store

ULTRA = "nvidia/Nemotron-3-Ultra-fake"


def listed(*gone: str) -> list[tf.Model]:
    """The fake's model list, less the ids that name any of ``gone``."""
    return [tf.Model(m["id"], 0, 0, m["created"]) for m in MODELS if not any(g in m["id"] for g in gone)]


def test_a_retired_id_falls_back_within_the_family_and_says_which_instead_of_which():
    assert tf.resolve([NANO, SUPER], "executor", listed()) == ([NANO, SUPER], [])
    [used], [said] = tf.resolve(["nvidia/Nemotron-3-Nano-retired"], "executor", listed())
    assert used == NANO  # the same size, as roles picks it: the newest that is not a -fast twin
    assert said.startswith("nvidia/Nemotron-3-Nano-retired is not in Token Factory's list (retired?); "
                           f"the executor uses {NANO} instead, the Nemotron Nano listed.")  # fmt: skip
    assert "`graphene init --executor nemotron` writes the ids listed now" in said
    [used], [said] = tf.resolve(["nvidia/Nemotron-3-Nano-retired"], "executor", listed("Nano"))
    assert used == SUPER and "the nearest size" in said
    [used], _ = tf.resolve(["nvidia/Nemotron-3-Super-retired"], "executor", listed("Super"))
    assert used == ULTRA  # two sizes as near: the larger, so a ladder's rung above stays above
    assert tf.resolve(["meta-llama/gone"], "executor", listed()) == (["meta-llama/gone"], [])
    assert tf.resolve(["nvidia/Nemotron-3-Nano-retired"], "executor", listed("Nemotron")) == (
        ["nvidia/Nemotron-3-Nano-retired"], [])  # fmt: skip
    assert tf.resolve([], "executor", listed()) == ([NANO], [])
    assert tf.resolve([], "planner", listed()) == ([ULTRA], [])
    assert tf.resolve([], "planner", listed("Nemotron")) == ([], [])


def test_a_list_that_has_lost_ultra_plans_with_the_largest_left_and_says_so_in_one_line(repo, monkeypatch):
    proposal = "```plan\n? say hello  [hello]\n    scope: app.py\n    check: true\n```"
    no_ultra = [m for m in MODELS if "Ultra" not in m["id"]]
    said = []
    with Fake([{"content": proposal}], models=no_ultra) as f, Store.open(repo) as store:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
    assert f.requests[0]["model"] == SUPER
    [line] = [s for s in said if "Ultra" in s]
    assert line.strip() == (f"Token Factory lists no Nemotron Ultra; the planner uses {SUPER}, the largest "
                            "Nemotron listed")  # fmt: skip


def test_an_executor_given_a_retired_id_uses_the_nearest_listed_and_its_log_says_so(repo, fake):
    f = fake([script({"greet": [call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")]})] * 5)
    plan_of(repo, leaf())
    done, _ = run_one(repo, "nemotron --model nvidia/Nemotron-3-Nano-retired")
    assert [n.id for n in done] == ["greet"]
    assert {r["model"] for r in f.requests} == {NANO}
    log = next((repo / ".graphene" / "runs").glob("greet-*.txt")).read_text()
    said = "nvidia/Nemotron-3-Nano-retired is not in Token Factory's list (retired?); the executor uses"
    assert f"{said} {NANO} instead" in log
