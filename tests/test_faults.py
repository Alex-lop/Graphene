# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""Surviving the judging period, against the recorded fake: judges may test until 15 December, Token
Factory retires models on notice, and Sandboxes are in beta. Every fault here ends the same way: the
leaf comes back with its cause in its record, the run goes on, nothing is left running, and the node
pane says what happened."""

import re
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest
from fake_faults import Box, everywhere
from fake_tokenfactory import MODELS, Fake, call
from test_executor import NANO, SUPER, fake, git, leaf, plan_of, repo, run_one, script  # noqa: F401
from test_sandbox_state import needs_docker

from graphene_map import plan, sandbox, tui
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


def test_a_planner_in_a_429_storm_adds_nothing_and_says_what_to_do(repo, fake, monkeypatch, tmp_path):
    everywhere(monkeypatch, tmp_path)
    fake([429] * 20)
    with Store.open(repo) as store, pytest.raises(plan.Refused) as no:
        ask(store, repo, "make it say hello", planner("nemotron"), say=lambda s: None)
    said = str(no.value)
    assert said.startswith("nothing was added. no proposal (exit 3): stopped: Token Factory answered 429")
    assert f"(asked {tf.TRIES} times: Token Factory limits how fast this key may ask; wait a minute" in said
    with Store.open(repo) as store:
        assert plan.nodes(store) == []


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


def came_back_with(repo, said: list[str], cause: str, run_says: str | None = None) -> str:
    """greet came back with ``cause`` in its record and on its pane, and the run said so (``run_says``,
    else the cause); farewell landed; no executor is left running; nothing printed a traceback.
    Returns greet's reason."""
    with Store.open(repo) as store:
        assert plan.get(store, "greet").state == plan.OPEN
        assert plan.get(store, "farewell").state == plan.DONE  # the run went on
        why = store.node_log("greet", ("released",))[-1]["detail"]["why"]
        pids = [e["detail"]["pid"] for e in store.node_log(kinds=("attempt",))]
    assert cause in why, why
    assert any(s.startswith("greet ") and (run_says or cause) in s for s in said), said
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


def test_a_check_that_hangs_is_stopped_with_all_it_started_and_the_leaf_comes_back_saying_so(
    repo, fake, monkeypatch, tmp_path
):
    """CHECK_TIMEOUT is 1800 s; here it is a second, in the run and in the executor's own `done`."""
    everywhere(monkeypatch, tmp_path, FAULTS_CHECK_TIMEOUT=1)
    pids = tmp_path / "check.pids"
    hangs = leaf(check=f"echo $$ >> {pids}; sleep 600 & echo $! >> {pids}; wait")
    steps = [call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")]

    def works_then_waits(body):
        k = sum(m["role"] == "assistant" for m in body["messages"])
        return steps[k] if k < len(steps) else {"content": "its check never ends; I stop here"}

    _, said = run_two(repo, fake, works_then_waits, greet=hangs)
    why = came_back_with(repo, said, "timed out after 1 s, and was stopped with everything it started: a "
                         "check must end by itself", run_says="greet came back after 3 attempts")  # fmt: skip
    assert why.startswith("3 attempts, the last one refused: greet is not done: `echo $$")
    started = [int(p) for p in pids.read_text().split()]
    assert len(started) >= 4  # a bash and its sleep, for each check the run and the executor ran
    until = time.monotonic() + 10
    while [p for p in started if _alive(p)] and time.monotonic() < until:
        time.sleep(0.1)
    assert not [p for p in started if _alive(p)]


# -- the sandbox --------------------------------------------------------------------------------------------

SANDBOXED = f"nemotron --model {NANO} --placement sandbox"


def test_a_sandbox_that_goes_away_mid_leaf_comes_back_with_its_cause(repo, fake, monkeypatch, tmp_path):
    everywhere(monkeypatch, tmp_path, FAULTS_BOX="fake", FAULTS_RAISE="uname -a")
    _, said = run_two(repo, fake, call("run", command="uname -a"), SANDBOXED)
    why = came_back_with(repo, said, "the sandbox stopped answering mid-leaf (ConnectionResetError: the "
                         "sandbox went away); nothing of this command was brought back: run the leaf again")
    assert why.startswith("the executor stopped: ")


def test_a_sandbox_operation_killed_mid_leaf_comes_back_with_its_cause(repo, fake, monkeypatch, tmp_path):
    """Killed (137) with no list of files, the leaf went on in a sandbox nobody could vouch for."""
    everywhere(monkeypatch, tmp_path, FAULTS_BOX="fake", FAULTS_KILL="uname -a")
    _, said = run_two(repo, fake, call("run", command="uname -a"), SANDBOXED)
    came_back_with(repo, said, "the sandbox's operation was killed mid-leaf (exit 137: out of memory, or "
                   "stopped)")  # fmt: skip


@needs_docker
def test_a_docker_sandbox_killed_mid_leaf_comes_back_leaving_no_container(repo, fake, monkeypatch, tmp_path):
    """The same, in the Docker stand-in: the container running the model's `sleep 30` is killed."""
    here = everywhere(monkeypatch, tmp_path, FAULTS_BOX="killed", FAULTS_KILL="sleep 30")
    monkeypatch.setenv("GRAPHENE_SANDBOX", "docker")
    try:
        _, said = run_two(repo, fake, call("run", command="sleep 30"), SANDBOXED)
        came_back_with(repo, said, "the sandbox's operation was killed mid-leaf (exit 137")
        made = (here / "containers").read_text().split()
        left = subprocess.run(["docker", "ps", "-aq", "--no-trunc"], capture_output=True, text=True).stdout
        assert made and not set(made) & set(left.split())
    finally:
        images = (here / "images").read_text().split() if (here / "images").exists() else []
        subprocess.run(["docker", "rmi", "-f", *images], capture_output=True) if images else None


def test_a_command_the_box_stopped_for_time_says_so_and_brings_nothing_back(repo, monkeypatch, tmp_path):
    """The box's own time limit hands back the image it was given: its list of files was the last
    command's, and was read as this one's (exit 0)."""
    everywhere(monkeypatch, tmp_path)

    class OutOfTime(Box):
        def run(self, image, script, files, timeout):
            if "sleep 999" in script:
                return image, 124, "(the sandbox command ran out of time)"  # as sandbox.Docker does
            return super().run(image, script, files, timeout)

    place = sandbox.Sandbox(repo, ["app.py"], OutOfTime())
    code, out = place.run("sleep 999")
    assert code == 124 and "ran out of time" in out and "nothing was brought back from this command" in out


def test_no_more_than_fifty_sandbox_operations_run_at_once(monkeypatch, tmp_path):
    """Sixty at once from threads: fifty run, ten wait for a slot. A slot is a lock file, so it holds
    across processes too (the thirty-leaf run below)."""
    here = everywhere(monkeypatch, tmp_path, FAULTS_OP=1)
    box = sandbox.Capped(Box())
    threads = [threading.Thread(target=box.run, args=("image", "true", {}, 60)) for _ in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    counts = [int(n) for n in (here / "counts").read_text().split()]
    assert len(counts) == 60 and max(counts) == sandbox.CAP


def test_thirty_leaves_at_parallel_8_with_7_forks_stay_inside_the_cap_and_each_ends_cleanly(
    repo, fake, monkeypatch, tmp_path
):
    """The directive's "--parallel 8 on a thirty-leaf plan, inside the cap", against the fakes: Token
    Factory is the recorded fake, and the sandbox is a box that is nowhere (fake_faults.Box: every
    command and check exits 0 and changes nothing, and each operation takes half a second), not Docker,
    which at 56 conversations at once would take minutes on this machine. Eight executors of seven
    forks are more conversations than the cap has slots. What this shows is the cap across processes
    and how the run ends; the checks here prove nothing. The live run, on Token Factory and in real
    Sandboxes, is still owed: it needs a key and a Sandboxes project."""
    here = everywhere(monkeypatch, tmp_path, FAULTS_BOX="fake", FAULTS_OP=0.5)
    ids = [f"n{k:02}" for k in range(30)]
    back = set(ids[4::5])  # every fifth leaf: each of its forks hands it back

    def reply(body):
        node = re.search(r"^(n\d\d) \(revision", body["messages"][1]["content"], re.M).group(1)
        steps = [call("release", why="it needs the schema too", wants=["schema.py"])] if node in back else [
            call("write", path=f"{node}.py", content="x = 1\n"), call("run", command="true"),
            call("run", command="true"), call("done")]
        k = sum(m["role"] == "assistant" for m in body["messages"])
        return steps[k] if k < len(steps) else {"content": "nothing more"}

    plan_of(repo, *(leaf(i, (f"{i}.py",), "true") for i in ids))
    fake([reply] * 5000)
    run_parallel(lambda: Store.open(repo), repo, repo, 8, named(f"{SANDBOXED} --forks 7"), say=lambda s: None,
                 logs=repo / ".graphene" / "runs")  # fmt: skip
    counts = [int(n) for n in (here / "counts").read_text().split()]
    assert max(counts) <= sandbox.CAP
    with Store.open(repo) as store:
        states = {n.id: n.state for n in plan.nodes(store)}
        pids = [e["detail"]["pid"] for e in store.node_log(kinds=("attempt",))]
        whys = {i: store.node_log(i, ("released",))[-1]["detail"]["why"] for i in back}
    assert {i for i, s in states.items() if s == plan.DONE} == set(ids) - back
    assert {i for i, s in states.items() if s == plan.OPEN} == back
    assert set(whys.values()) == {"it needs the schema too"}
    assert not [p for p in pids if _alive(p)]
