# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""Surviving the judging period, against the recorded fake: judges may test until 15 December, Token
Factory retires models on notice, and Sandboxes are in beta. Every fault here ends the same way: the
leaf comes back with its cause in its record, the run goes on, nothing is left running, and the node
pane says what happened."""

import threading
from types import SimpleNamespace

import pytest
from fake_faults import everywhere
from fake_tokenfactory import MODELS, Fake, call
from test_executor import NANO, SUPER, fake, git, leaf, plan_of, repo, run_one, script  # noqa: F401

from graphene_map import plan, tui
from graphene_map import tokenfactory as tf
from graphene_map.ask import ask
from graphene_map.ask import named as planner
from graphene_map.run import _alive, named, run_parallel
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
        ask(store, repo, "make it say hello", planner("nemotron"), say=said.append)
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


# -- the faults: each hits greet, while farewell lands beside it -----------------------------------------

BYE = "python3 -c 'import bye; assert bye.bye() == \"goodbye\"'"


def faulty(fault):
    """A reply: greet's conversation meets ``fault`` (a reply, or a callable of the request, as the fake
    takes them), and farewell's lands."""
    lands = script({"farewell": [call("edit", path="bye.py", old='"bye"', new='"goodbye"'), call("done")]})

    def reply(body):
        if "greet (revision" in body["messages"][1]["content"]:
            return fault(body) if callable(fault) else fault
        return lands(body)

    return reply


def run_two(repo, fake, fault, spec=f"nemotron --model {NANO}", greet=None):
    """greet and farewell at once, each in its worktree, as `graphene run --parallel 2` runs them."""
    (repo / "bye.py").write_text('def bye():\n    return "bye"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "bye")
    plan_of(repo, greet or leaf(), leaf("farewell", ("bye.py",), BYE))
    f = fake([faulty(fault)] * 200)
    said = []
    run_parallel(lambda: Store.open(repo), repo, repo, 2, named(spec), say=said.append,
                 logs=repo / ".graphene" / "runs")  # fmt: skip
    return f, said


def pane(repo, node_id: str) -> str:
    """The node pane `graphene watch` draws for it (``tui.detail``), its words run together."""
    with Store.open(repo) as store:
        nodes = plan.nodes(store)
        back = {n.id for n in nodes if plan.came_back(store, n)}
        words = {n.id: plan.reads(n, nodes, back) for n in nodes}
        s = SimpleNamespace(nodes=nodes, by_id={n.id: n for n in nodes}, under=plan.kids(nodes, drawn=True),
                            words=words, root_path=repo)  # fmt: skip
        return " ".join(str(tui.detail(store, s.by_id[node_id], s)).split())


def came_back_with(repo, said: list[str], cause: str) -> str:
    """greet came back with ``cause`` in its record, in what the run said and on its pane; farewell
    landed; no executor is left running; nothing printed a traceback. Returns greet's reason."""
    with Store.open(repo) as store:
        assert plan.get(store, "greet").state == plan.OPEN
        assert plan.get(store, "farewell").state == plan.DONE  # the run went on
        why = store.node_log("greet", ("released",))[-1]["detail"]["why"]
        pids = [e["detail"]["pid"] for e in store.node_log(kinds=("attempt",))]
    assert cause in why, why
    assert any(s.startswith("greet ") and cause in s for s in said), said
    shown = pane(repo, "greet")
    assert "greet · came back" in shown and " ".join(cause.split()) in shown, shown
    assert not [p for p in pids if _alive(p)]
    logs = "".join(p.read_text() for p in (repo / ".graphene" / "runs").glob("greet-*.txt"))
    assert "Traceback" not in logs
    return why


def test_a_429_storm_comes_back_with_what_to_do_and_the_run_goes_on(repo, fake, monkeypatch, tmp_path):
    everywhere(monkeypatch, tmp_path)  # no wait through the backoff, in the executor's process too
    f, said = run_two(repo, fake, 429)
    why = came_back_with(repo, said, "Token Factory answered 429 to POST /chat/completions")
    assert why.startswith("the executor stopped: ")
    assert f"asked {tf.TRIES} times: Token Factory limits how fast this key may ask; wait a minute" in why
    assert sum("greet (revision" in r["messages"][1]["content"] for r in f.requests) == tf.TRIES


def test_5xx_errors_come_back_saying_whose_fault_it_is_and_the_run_goes_on(repo, fake, monkeypatch, tmp_path):
    everywhere(monkeypatch, tmp_path)
    _, said = run_two(repo, fake, 503)
    why = came_back_with(repo, said, "Token Factory answered 503 to POST /chat/completions")
    assert f"asked {tf.TRIES} times: the fault is on Token Factory's side; try again later" in why


def test_a_completion_that_never_answers_comes_back_and_the_run_goes_on(repo, fake, monkeypatch, tmp_path):
    everywhere(monkeypatch, tmp_path, FAULTS_TIMEOUT=1)  # a second, in every executor, not 300

    def never(body):
        threading.Event().wait(3)  # longer than the executor waits
        return {"content": "too late"}

    _, said = run_two(repo, fake, never)
    why = came_back_with(repo, said, "Token Factory could not be reached")
    assert "no answer in 1 s, asked 2 times: try again later, or ask for a shorter answer" in why


def test_a_429_storm_that_meets_every_fork_comes_back_once_with_its_cause(repo, fake, monkeypatch, tmp_path):
    """A fork is a thread: Token Factory's refusal there was a traceback in the log, and the leaf went
    round the run's attempts to be refused for a change nobody made."""
    everywhere(monkeypatch, tmp_path)
    _, said = run_two(repo, fake, 429, f"nemotron --model {NANO} --forks 2")
    why = came_back_with(repo, said, "Token Factory answered 429 to POST /chat/completions")
    assert why.startswith("the executor stopped: ")


LATER = "or name a larger model with another --model"
NOT_JSON = {"content": None, "tool_calls": [{"id": "call_1", "type": "function",
            "function": {"name": "edit", "arguments": '{"path": "app.py", "old": '}}]}  # fmt: skip


@pytest.mark.parametrize(
    "fault, steps, told, cause",
    [
        ({"content": "Let me think about greet at length", "_finish": "length"}, 40,
         "Your answer was cut off at the token limit",
         "the model answered three times without calling a tool, the last cut off at the token limit (16384 "
         f"tokens): raise --max-tokens, {LATER}"),
        ({"content": "app.py looks fine to me."}, 40, "Use a tool.",
         f"the model answered three times without calling a tool: {LATER}"),
        (NOT_JSON, 3, "edit could not take those arguments",
         "the model used all 3 steps without finishing (the last it was told: edit could not take those"),
        (call("frobnicate", path="app.py"), 3, "there is no tool 'frobnicate'",
         "the model used all 3 steps without finishing (the last it was told: there is no tool 'frobnicate'"),
    ],
    ids=["cut off", "text only", "arguments not JSON", "no such tool"],
)  # fmt: skip
def test_a_model_that_misfires_is_told_and_when_it_gives_up_the_leaf_comes_back_saying_why(
    repo, fake, fault, steps, told, cause
):
    f, said = run_two(repo, fake, fault, f"nemotron --model {NANO} --steps {steps}")
    why = came_back_with(repo, said, cause)
    assert why.startswith("the executor stopped: the model ")  # not a check refused on untouched code
    asked = [r for r in f.requests if "greet (revision" in r["messages"][1]["content"]]
    assert len(asked) == 3 and all(told in r["messages"][-1]["content"] for r in asked[1:])  # told, and on


def test_a_model_that_gives_up_on_a_lower_rung_goes_up_the_ladder_before_the_leaf_comes_back(repo, fake):
    f = fake([{"content": "nothing to do here, I think"}] * 20)
    plan_of(repo, leaf())
    done, _ = run_one(repo, f"nemotron --model {NANO} --model {SUPER}", attempts=3)
    assert done == []
    assert [r["model"] for r in f.requests] == [NANO] * 3 + [SUPER] * 3  # the run judged, and climbed
    with Store.open(repo) as store:
        why = store.node_log("greet", ("released",))[-1]["detail"]["why"]
        assert len(store.node_log("greet", ("attempt",))) == 2  # the last rung is not sent round again
    assert why == f"the executor stopped: the model answered three times without calling a tool: {LATER}"


def test_forks_that_all_give_up_come_back_saying_why_each_did(repo, fake):
    text = {"content": "app.py looks fine to me."}
    _, said = run_two(repo, fake, text, f"nemotron --model {NANO} --forks 2")
    why = came_back_with(repo, said, "no fork's check passed (2 forks): fork 1: the model answered three")
    assert "; fork 2: the model answered three times without calling a tool" in why
