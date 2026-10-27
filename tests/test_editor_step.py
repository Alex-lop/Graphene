# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene ask "<sentence>" --step [--after ID | --under ID]`: one sentence, one proposed step, from the
configured planner (Nano when it is Nemotron); it lands as a proposal, whoever asked, and only a person, or
the envelope when auto is on and it fits, accepts it; the first line says `proposed ID: TITLE`. The planner
here is a script, and the Nemotron path is the scripted stand-in: no model is called. The contract's section
"The CLI", shape 5."""

import json
import sys

import pytest
from fake_tokenfactory import Fake
from test_plan_cli import AGENT_ENV, person, repo, runner  # noqa: F401
from test_plan_text_cli import TEXT, person_with

from graphene_map import ask as A
from graphene_map import plan
from graphene_map.cli import build
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.plan import OPEN, PROPOSED
from graphene_map.store import Store

ONE = """
import json, os, sys
open(os.environ["SEEN"], "a").write(json.dumps({"prompt": sys.argv[-1]}) + "\\n")
print("```plan")
print("? document the ids  [docs-ids]")
print("    scope: docs/ids.md")
print("    check: test -f docs/ids.md")
print("```")
"""


def planner(tmp_path, monkeypatch, source=ONE) -> str:
    script = tmp_path / "planner.py"
    script.write_text(source)
    monkeypatch.setenv("SEEN", str(tmp_path / "seen.jsonl"))
    return f"{sys.executable} {script}"


def prompt(tmp_path) -> str:
    return json.loads((tmp_path / "seen.jsonl").read_text().splitlines()[-1])["prompt"]


def planned(repo):
    person_with("plan", "propose", "-", input=TEXT)  # the person's: api, ids and docs in the plan
    return repo


def test_one_sentence_is_one_proposed_step_said_first_by_its_id(repo, tmp_path, monkeypatch):
    planned(repo)
    said = person("ask", "write the ids down", "--step", "--with", planner(tmp_path, monkeypatch))
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines()[0] == "proposed docs-ids: document the ids"
    assert said.stdout.count("proposed docs-ids") == 1  # said once, first
    with Store.open(repo) as store:
        step = plan.get(store, "docs-ids")
        assert step.state == PROPOSED and step.parent is None and step.scope == ["docs/ids.md"]
    assert "propose exactly one leaf, no sub-goal and no second leaf" in prompt(tmp_path)
    assert "The person said: write the ids down" in prompt(tmp_path)


def test_after_puts_the_step_beside_the_task_waiting_on_it(repo, tmp_path, monkeypatch):
    planned(repo)
    said = person("ask", "then write them down", "--step", "--after", "ids", "--with",
                  planner(tmp_path, monkeypatch))  # fmt: skip
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines()[0] == "proposed docs-ids: document the ids"
    with Store.open(repo) as store:
        step, ids = plan.get(store, "docs-ids"), plan.get(store, "ids")
        assert step.parent == ids.parent == "api" and step.needs == ["ids"]  # the planner left it out
        assert step.state == PROPOSED
    assert "It comes after [ids]" in prompt(tmp_path) and "`needs: ids`" in prompt(tmp_path)


def test_under_puts_the_step_under_the_node(repo, tmp_path, monkeypatch):
    planned(repo)
    said = person("ask", "and the docs", "--step", "--under", "api", "--with", planner(tmp_path, monkeypatch))
    assert said.exit_code == 0, said.output
    with Store.open(repo) as store:
        assert plan.get(store, "docs-ids").parent == "api" and plan.get(store, "docs-ids").needs == []
    assert "It goes under [api]" in prompt(tmp_path)


def test_only_a_person_accepts_it_and_the_envelope_when_auto_is_on_and_it_fits(repo, tmp_path, monkeypatch):
    planned(repo)
    person("ask", "write the ids down", "--step", "--with", planner(tmp_path, monkeypatch))
    refused = runner.invoke(build(), ["plan", "accept", "docs-ids"], env=AGENT_ENV)
    assert refused.exit_code == 1  # an agent does not accept
    with Store.open(repo) as store:
        assert plan.get(store, "docs-ids").state == PROPOSED
    assert person("plan", "accept", "docs-ids").exit_code == 0
    with Store.open(repo) as store:
        assert plan.get(store, "docs-ids").state == OPEN
        store.set_meta("settings:auto", "on")  # the envelope: what fits it is accepted at once
    two = ONE.replace("docs-ids", "docs-more").replace("docs/ids.md", "docs/more.md")
    said = person("ask", "more docs", "--step", "--with", planner(tmp_path, monkeypatch, two))
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines()[0] == "proposed docs-more: document the ids"
    with Store.open(repo) as store:
        assert plan.get(store, "docs-more").state == OPEN  # the envelope's, logged as the person's


def test_the_gate_stands_an_agent_does_not_start_the_planner(repo, tmp_path, monkeypatch):
    planned(repo)
    argv = ["ask", "x", "--step", "--with", planner(tmp_path, monkeypatch)]
    said = runner.invoke(build(), argv, env=AGENT_ENV)
    assert said.exit_code == 1 and "asking a planner is the person's" in said.stderr
    assert not (tmp_path / "seen.jsonl").exists()
    for args in (("--after", "ids"), ("--under", "api")):
        said = person("ask", "x", *args, "--with", planner(tmp_path, monkeypatch))
        assert said.exit_code == 2 and "--after and --under place a step" in said.stderr
    said = person("ask", "x", "--step", "--after", "ids", "--under", "api")
    assert said.exit_code == 2 and "--after or --under, not both" in said.stderr


def test_a_planner_that_proposes_a_tree_is_refused_told_so_and_nothing_lands(repo, tmp_path, monkeypatch):
    """One sentence is one step. The first leaf was named and the rest landed with it: the editor had four
    proposals to show for one sentence, under a sub-goal nobody asked for (the editor night's review)."""
    leaf = 'print("? the docs  [the-docs]")\nprint("  ? document the ids  [docs-ids]")'
    tree = ONE.replace('print("? document the ids  [docs-ids]")', leaf)
    tree = tree.replace('print("    scope:', 'print("      scope:')
    tree = tree.replace('print("    check:', 'print("      check:')
    third = 'print("? and a third  [third]")\nprint("    scope: docs/third.md")\nprint("    check: true")\n'
    tree = tree.replace('print("```")\n', third + 'print("```")\n')  # inside the fence, a third node
    planned(repo)
    said = person("ask", "docs", "--step", "--with", planner(tmp_path, monkeypatch, tree))
    assert said.exit_code == 1, said.output
    assert "the planner proposed 3 steps, not one" in said.stderr and "nothing was added" in said.stderr
    assert "proposed" not in said.stdout
    with Store.open(repo) as store:
        assert {n.id for n in plan.nodes(store)} == {"api", "ids", "docs"}  # the plan as it was
    assert "proposed 3 steps, not one" in prompt(tmp_path)  # the planner was told, and asked again
    kept = list((repo / ".graphene" / "runs").glob("ask-*.txt"))
    assert len(kept) == 1 and "[third]" in kept[0].read_text()  # its text kept, as any refused proposal's


def reply(body):
    """The stand-in as Nano: read nothing, answer one node in the planner's own JSON."""
    if not body.get("response_format"):
        return {"content": "I have read enough."}
    node = {"id": "docs-ids", "title": "document the ids", "goal": "a page on the ids", "needs": [],
            "scope": ["docs/ids.md"], "check": "test -f docs/ids.md", "parent": None, "mark": "?"}
    return {"content": json.dumps({"says": "One step.", "goal": None, "board": [], "nodes": [node]})}


@pytest.fixture
def fake(monkeypatch):
    f = Fake([reply] * 20).__enter__()
    for k, v in f.env().items():
        monkeypatch.setenv(k, v)
    tf._listed.cache_clear()
    yield f
    f.__exit__(None, None, None)


def test_with_nemotron_the_step_comes_from_nano_not_the_largest_model(repo, fake):
    planned(repo)
    said = person("ask", "write the ids down", "--step", "--after", "ids", "--with", "nemotron")
    assert said.exit_code == 0, said.output + said.stderr
    assert said.stdout.splitlines()[0] == "proposed docs-ids: document the ids"
    models = [r["model"] for r in fake.requests]
    assert models and all("Nano" in m for m in models), models
    assert "propose exactly one leaf" in fake.requests[0]["messages"][1]["content"]
    with Store.open(repo) as store:
        step = plan.get(store, "docs-ids")
        assert step.state == PROPOSED and step.needs == ["ids"] and step.parent == "api"
    assert A.for_step("nemotron") == "nemotron --model nvidia/Nemotron-3-Nano-fake"  # the host's own Nano
    on_nim = A.for_step("nemotron --endpoint nim")  # another host: a size name, resolved there
    assert on_nim == "nemotron --endpoint nim --model nemotron-nano"
    assert A.for_step("nemotron --model Super") == "nemotron --model Super"  # a model named stands
    assert A.for_step("claude") == "claude" and A.for_step(None) is None


def test_the_harness_stand_in_answers_a_step_with_one_leaf_from_the_sentence(repo, monkeypatch):
    """dev/proof/standin.py serves test_demo_auto's `reply` for every request, so the editor's Add Step
    (`graphene ask --step --after ID -- SENTENCE`) driven through the harness lands one proposal."""
    from test_demo_auto import reply as standin

    planned(repo)
    with Fake([standin] * 20) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        sentence = "a --version flag on the CLI, with a test"
        said = person("ask", "--step", "--after", "ids", "--with", "nemotron", "--", sentence)
        assert said.exit_code == 0, said.output + said.stderr
        assert said.stdout.splitlines()[0] == f"proposed a-version-flag: {sentence}"
        with Store.open(repo) as store:
            step = plan.get(store, "a-version-flag")
            assert step.state == PROPOSED and step.needs == ["ids"] and step.parent == "api"
            assert step.scope == ["wordkit/a_version_flag.py", "tests/test_a_version_flag.py"]
            assert {n.id for n in plan.nodes(store)} == {"api", "ids", "docs", "a-version-flag"}
        # a second sentence is a second leaf of its own, beside the first
        said = person("ask", "--step", "--after", "ids", "--with", "nemotron", "--",
                      "a --help line that names every flag")  # fmt: skip
        assert said.exit_code == 0, said.output + said.stderr
        assert said.stdout.splitlines()[0] == "proposed a-help-line: a --help line that names every flag"


def test_the_flags_have_help_in_the_budget_and_the_reference_names_the_step():
    import typer.main

    command = typer.main.get_command(build()).commands["ask"]
    helps = {p.name: p.help for p in command.params}
    assert all(len(helps[k]) <= 80 for k in ("step", "after", "under")), helps
    how = (__import__("pathlib").Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text()
    assert "--step" in how and "`--after ID`" in how and "`--under ID`" in how
