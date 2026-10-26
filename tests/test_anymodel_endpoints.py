"""Any model behind Graphene's own loop (26 October): the host is a choice, `--endpoint tokenfactory|nim|
ollama|openai`, each pointed at the recorded fake here through its own URL variable. Every call's row names
the endpoint and the model; a host with no Nemotron takes --model, else the first chat model listed, and
says which; a model with no list price is "unpriced", not $0, on every bill and cap; a paid host is guarded
as Token Factory is and a local one is not; the scope's refusal holds whoever answers; no key reaches a
model's command or a check; `graphene key set --endpoint nim` keeps another host's key under its own name."""

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fake_tokenfactory import MODELS, Fake, call
from typer.testing import CliRunner

from graphene_map import plan
from graphene_map.nemotron import keys, night
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.nemotron.executor import Local
from graphene_map.node_record import bill, bill_line
from graphene_map.plan import DONE, Caller
from graphene_map.run import label, named, run_plan
from graphene_map.store import Store

ALEX = Caller("alex", True)
# NIM's list: Nemotron ids in its own spellings, and no prices
NIM = [dict(m, pricing=None) for m in MODELS]
NIM[1]["id"], NIM[3]["id"] = "nvidia/nemotron-3-nano-30b-a3b", "nvidia/llama-3.3-nemotron-super-49b-v1.5"
# Ollama's: no Nemotron, no prices, an embedding model first
OLLAMA = [{"id": "nomic-embed-text", "created": 1}, {"id": "qwen3:8b", "created": 2},
          {"id": "gemma3", "created": 3}]  # fmt: skip
CHECK = "python3 -c 'import app; assert app.greet() == \"hello\"'"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    (root / "app.py").write_text('def greet():\n    return "hi"\n')
    (root / "other.py").write_text("x = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def fake(monkeypatch):
    """``fake(replies, models, key)`` starts the fake and points ``endpoint`` at it: its URL variable, its
    key variable (none for a keyless host), and GRAPHENE_ENDPOINT for this process and the ones it starts."""
    started = []

    def start(replies=(), models=MODELS, key="fake-key", endpoint="tokenfactory"):
        f = Fake(replies, models, key).__enter__()
        e = tf.ENDPOINTS[endpoint]
        monkeypatch.setenv(e.url_env, f.url)
        if key:
            monkeypatch.setenv(e.key_envs[0], key)
        monkeypatch.setenv(tf.ENDPOINT, endpoint)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)
    tf._listed.cache_clear()


def script(steps: list):
    def reply(body):
        k = sum(1 for m in body["messages"] if m["role"] == "assistant")
        return steps[k] if k < len(steps) else {"content": "nothing more"}

    return reply


def plan_of(repo, check=CHECK):
    with Store.open(repo) as store:
        plan.set_goal(store, "a friendlier app", ALEX)
        plan.propose(store, [{"id": "greet", "title": "make greet", "goal": "greet says hello",
                              "scope": ["app.py"], "check": check}], ALEX)  # fmt: skip


def run_one(repo, spec):
    said = []
    with Store.open(repo) as store:
        done = run_plan(store, repo, named(spec), 1, None, said.append, repo / ".graphene" / "runs")
    return done, said


@pytest.mark.parametrize("endpoint, key, listed", [("tokenfactory", "fake-key", MODELS),
                                                   ("nim", "fake-key", NIM), ("ollama", None, OLLAMA),
                                                   ("openai", None, OLLAMA)])  # fmt: skip
def test_each_endpoint_is_pointed_at_the_fake_by_its_own_variable_and_says_who_it_is(fake, endpoint, key,
                                                                                     listed):  # fmt: skip
    f = fake([{"content": "ok"}], listed, key, endpoint)
    assert tf.chosen().name == endpoint and tf.base() == f.url
    assert [m.id for m in tf.models()] == [m["id"] for m in listed]
    # pointed away from its own URL a host is a stand-in; the openai endpoint is whatever URL it is given
    assert tf.endpoint() == ("an openai-compatible host" if endpoint == "openai" else "a stand-in")
    assert tf.stand_in()  # the fake is on this machine: no guard, nothing spent
    said = tf.chat(listed[-1]["id"], [{"role": "user", "content": "hi"}])
    assert said["message"]["content"] == "ok" and said["model"] == listed[-1]["id"]
    assert said["priced"] is (endpoint == "tokenfactory")  # NIM and Ollama list no price


def test_a_host_with_no_nemotron_takes_the_model_given_else_the_first_chat_model_listed_and_says_which(fake):
    fake([], OLLAMA, None, "ollama")
    assert tf.resolve(["gemma3"], "executor") == (["gemma3"], [])  # given: kept, the host's answer decides
    ids, said = tf.resolve([], "executor")  # none given: the first chat model (the embedding one is skipped)
    assert ids == ["qwen3:8b"]
    assert said == ["Ollama lists no Nemotron; the executor uses qwen3:8b, the first model listed "
                    "(--model names another)"]  # fmt: skip
    assert tf.resolve([], "planner")[0] == ["qwen3:8b"]
    assert tf.reach() is None  # reached: a model is listed
    fake([], [], None, "ollama")
    assert tf.resolve([], "planner") == ([], []) and tf.reach() == "Ollama lists no model for this key"


def test_nims_nemotron_ids_are_found_by_size(fake):
    fake([], NIM, "fake-key", "nim")
    assert tf.roles() == {"ultra": "nvidia/Nemotron-3-Ultra-fake", "nano": "nvidia/nemotron-3-nano-30b-a3b",
                          "super": "nvidia/llama-3.3-nemotron-super-49b-v1.5"}  # fmt: skip
    assert tf.resolve([], "executor") == (["nvidia/nemotron-3-nano-30b-a3b"], [])


def test_ollama_needs_no_key_and_a_call_without_one_goes_through(fake, monkeypatch):
    f = fake([{"content": "ok"}], OLLAMA, None, "ollama")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    assert keys.find(tf.chosen().key_envs, tf.chosen().account) is None
    assert tf.chat("qwen3:8b", [{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    assert len(f.requests) == 1
    f.key = "wanted"  # a host that does want one answers 401, and the line says what to set
    with pytest.raises(tf.Unreachable, match="Ollama answered 401"):
        tf.chat("qwen3:8b", [{"role": "user", "content": "hi"}], tries=1)


def test_a_keyed_host_without_a_key_is_one_line_naming_its_variable_and_nothing_is_sent(fake, monkeypatch):
    f = fake([{"content": "ok"}], NIM, "fake-key", "nim")
    monkeypatch.delenv("NVIDIA_API_KEY")
    no_key = r"NVIDIA_API_KEY is not set: NVIDIA NIM needs a key \(build.nvidia.com\)"
    with pytest.raises(tf.Unreachable, match=no_key):
        tf.chat("nvidia/nemotron-3-nano-30b-a3b", [{"role": "user", "content": "hi"}])
    assert f.requests == []
    monkeypatch.setenv("NVIDIA_API_KEY", "with space")
    with pytest.raises(tf.Unreachable, match="graphene key set --endpoint nim"):
        tf.chat("nvidia/nemotron-3-nano-30b-a3b", [{"role": "user", "content": "hi"}])


def test_the_openai_endpoint_needs_its_url_and_the_line_says_so(monkeypatch):
    for mark in night.MARKS:  # the person asks (the shell these tests run in may be an agent's)
        monkeypatch.delenv(mark, raising=False)
    monkeypatch.setenv(tf.ENDPOINT, "openai")
    monkeypatch.delenv("GRAPHENE_OPENAI_BASE_URL", raising=False)
    with pytest.raises(tf.Unreachable, match="GRAPHENE_OPENAI_BASE_URL is not set"):
        tf.chat("gemma3", [{"role": "user", "content": "hi"}])
    monkeypatch.setenv(tf.ENDPOINT, "nowhere")
    with pytest.raises(tf.Unreachable, match="GRAPHENE_ENDPOINT is 'nowhere': the endpoints are tokenfact"):
        tf.base()


def test_a_paid_host_is_guarded_like_token_factory_and_a_host_on_this_machine_is_not(fake, monkeypatch):
    """An agent's call to NIM, or to an OpenAI-compatible URL off this machine, is refused unsent without the
    person's opening, as Token Factory's is; Ollama and a local vLLM are stand-ins, open to anyone."""
    f = fake([{"content": "ok"}] * 3, NIM, "fake-key", "nim")
    for mark in night.MARKS:
        monkeypatch.delenv(mark, raising=False)
    real = dataclasses.replace(tf.ENDPOINTS["nim"], url=f.url)  # the fake, at what NIM's own URL is here
    monkeypatch.setitem(tf.ENDPOINTS, "nim", real)
    monkeypatch.delenv("GRAPHENE_NIM_URL")
    assert tf.endpoint() == "nvidia nim" and not tf.stand_in()
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(tf.Spent, match=r"\(CLAUDECODE\) with no GRAPHENE_AGENT_LIVE_USD: nothing was sent"):
        tf.chat("nvidia/nemotron-3-nano-30b-a3b", [{"role": "user", "content": "hi"}])
    assert f.requests == []
    monkeypatch.setenv(night.OPENING, "1")  # opened by the person: the call goes, and its row names NIM
    said = tf.chat("nvidia/nemotron-3-nano-30b-a3b", [{"role": "user", "content": "hi"}])
    assert said["message"]["content"] == "ok" and not said["priced"]
    rows = [line for line in Path(os.environ[night.LEDGER]).read_text().splitlines()]
    assert '"endpoint": "nvidia nim"' in rows[0] and '"dollars": 0.0' in rows[0]  # unpriced: $0 held
    assert any("(no list price: counted at $0)" in line for line in night.bill())
    monkeypatch.delenv(night.OPENING)
    fake([{"content": "ok"}], OLLAMA, None, "ollama")  # on this machine: an agent may ask it
    assert tf.stand_in()
    assert tf.chat("gemma3", [{"role": "user", "content": "hi"}])["message"]["content"] == "ok"
    monkeypatch.setenv(tf.ENDPOINT, "openai")
    monkeypatch.setenv("GRAPHENE_OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    assert not tf.stand_in()  # a URL off this machine spends: guarded
    monkeypatch.setenv("GRAPHENE_OPENAI_BASE_URL", "http://localhost:8000/v1")
    assert tf.stand_in()  # a vLLM here does not


def test_the_executor_on_another_host_lands_a_leaf_refuses_the_scope_and_bills_it_unpriced(repo, fake):
    """`--with 'nemotron --endpoint openai'` on a host that lists no Nemotron: the first model listed does
    the leaf, a write outside the scope is refused before it happens, and every row names the host and the
    model, with no list price rather than $0."""
    steps = [call("write", path="other.py", content="y = 2\n"),  # outside the scope: refused
             call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")]
    fake([script(steps)] * 6, OLLAMA, None, "openai")
    plan_of(repo)
    done, said = run_one(repo, "nemotron --endpoint openai")
    assert [n.id for n in done] == ["greet"]
    with Store.open(repo) as store:
        assert plan.get(store, "greet").state == DONE
        rows = [e["detail"] for e in store.node_log("greet", ("usage",))]
        denied = store.node_log("greet", ("denied", "refused"))
        line = bill_line(bill(store.node_log("greet")))[0]
        log = Path(store.node_log("greet", ("attempt",))[-1]["detail"]["log"]).read_text()
    assert rows and all(r["endpoint"] == "an openai-compatible host" for r in rows)
    assert all(r["model"] == "qwen3:8b" and r.get("priced") is False and r["dollars"] == 0 for r in rows)
    assert line.endswith("(an OpenAI-compatible host's usage)") and "with no list price)" in line
    assert "the OpenAI-compatible host lists no Nemotron; the executor uses qwen3:8b, the first model" in log
    assert "nemotron executor · qwen3:8b · the OpenAI-compatible host · local placement" in log
    assert "(no list price), 1 writes refused" in log
    assert denied and (repo / "other.py").read_text() == "x = 1\n"


def test_the_executor_on_nim_climbs_nims_own_ladder(repo, fake):
    steps = [call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")]
    fake([script(steps)] * 4, NIM, "fake-key", "nim")
    plan_of(repo)
    done, _ = run_one(repo, "nemotron --endpoint nim")
    assert [n.id for n in done] == ["greet"]
    with Store.open(repo) as store:
        rows = [e["detail"] for e in store.node_log("greet", ("usage",))]
    assert {r["model"] for r in rows} == {"nvidia/nemotron-3-nano-30b-a3b"}  # NIM's Nano, by its own id
    assert {r["endpoint"] for r in rows} == {"a stand-in"}  # the fake stands in for NIM: never credited to it


def test_no_key_of_any_host_reaches_a_models_command_or_a_check(monkeypatch, tmp_path):
    for e in tf.ENDPOINTS.values():
        for name in e.key_envs:
            monkeypatch.setenv(name, "secret-" + name)
    monkeypatch.setenv("KEEP_ME", "yes")
    env = plan.check_env({"PORT": "41000"})
    assert not [k for k in env if k.endswith("_API_KEY")]
    assert env["KEEP_ME"] == "yes" and env["PORT"] == "41000"
    code, out = Local(tmp_path).run("env")
    assert code == 0 and "_API_KEY" not in out and "KEEP_ME=yes" in out


def test_key_set_check_and_remove_take_an_endpoint_and_keep_its_key_under_its_own_name(monkeypatch):
    import typer

    from graphene_map.nemotron import key_cli

    for mark in night.MARKS:  # the person's command, whatever shell runs the tests
        monkeypatch.delenv(mark, raising=False)
    kept = {}
    monkeypatch.setattr(keys, "set", lambda k, account="token-factory", host="": kept.__setitem__(account, k))
    monkeypatch.setattr(keys, "remove", lambda account="token-factory": kept.pop(account))
    cli = typer.Typer()

    @cli.callback()
    def main() -> None: ...

    def fail(message, code=2):
        typer.echo(message, err=True)
        raise typer.Exit(code)

    key_cli.register(cli, fail)
    env = {"GRAPHENE_AS": "person:alex"}
    done = CliRunner().invoke(cli, ["key", "set", "--endpoint", "nim"], env=env, input="nvapi-x\n")
    assert done.exit_code == 0 and "NVIDIA NIM key:" in done.output and kept == {"nim": "nvapi-x"}
    done = CliRunner().invoke(cli, ["key", "remove", "--endpoint", "nim"], env=env)
    assert done.exit_code == 0 and kept == {}
    done = CliRunner().invoke(cli, ["key", "set", "--endpoint", "bogus"], env=env, input="x\n")
    assert done.exit_code == 2 and "no endpoint named 'bogus': the endpoints are tokenfactory" in done.output


def test_the_specs_carry_the_endpoint_to_the_planner_and_the_executor():
    assert "--endpoint nim --model x" in named("nemotron --endpoint nim --model x")
    assert label(named("nemotron --endpoint ollama")) == "nemotron"
    argv = [sys.executable, "-m", "graphene_map.nemotron.executor", "--help"]
    out = subprocess.run(argv, capture_output=True, text=True)
    assert "--endpoint {tokenfactory,nim,ollama,openai}" in out.stdout
