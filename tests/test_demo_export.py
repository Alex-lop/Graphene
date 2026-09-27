"""The demo page (docs/demo/README.md): a real `graphene run --parallel` by executors that keep no
records of their own (no transcript, no hook), exported with `graphene ui --export`, is drawn from
the store alone: the tree, each leaf's state, and each leaf's record, with no check's output in it."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graphene_map import server as ui

CLI = [sys.executable, "-c", "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"]
# One executor for every leaf, as `graphene run --with` starts it: it writes the leaf's file and says
# `done`, except where the loop should show. csv-reader first leaves a note outside its scope, so its
# `done` is refused and the run sends it back; json-reader hands its leaf back with a reason; the
# parser's check fails every time, printing something that must not leave the machine; yaml-reader
# passes and does not land, because the person has a file of that name uncommitted in the checkout.
EXECUTOR = f"""
import os, pathlib, subprocess, sys
node, here = os.environ["GRAPHENE_NODE"], pathlib.Path.cwd()
def graphene(*args):
    subprocess.run({CLI!r} + list(args), check=False)
if node == "json-reader":
    graphene("node", "release", node, "--why", "the json reader needs feeds/parse.py, outside its scope")
    sys.exit()
again = "not accepted" in sys.argv[-1]
if node == "csv-reader":
    (here / "NOTES.md").unlink() if again else (here / "NOTES.md").write_text("a stray note\\n")
body = "raise SystemExit('PRIVATE-4242')\\n" if node == "parser" else "def read():\\n    return []\\n"
(here / "feeds" / (node.replace("-", "_") + ".py")).write_text(body)
graphene("node", "done", node)
"""
PLAN = f"""\
- readers  [readers]
  - a csv reader  [csv-reader]
      scope: feeds/csv_reader.py
      check: test -s feeds/csv_reader.py
  - an xml reader  [xml-reader]
      scope: feeds/xml_reader.py
      check: test -s feeds/xml_reader.py
  - a json reader  [json-reader]
      scope: feeds/json_reader.py
      check: test -s feeds/json_reader.py
  - a yaml reader  [yaml-reader]
      scope: feeds/yaml_reader.py
      check: test -s feeds/yaml_reader.py
  - the parser  [parser]
      scope: feeds/parser.py
      check: {sys.executable} -m feeds.parser
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def graphene(repo, config, *args, stdin=None):
    """The CLI as the person runs it: no agent's mark, and no Claude Code records anywhere."""
    marks = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT")
    env = {k: v for k, v in os.environ.items() if k not in marks}
    env |= {"GRAPHENE_AS": "person:alex", "CLAUDE_CONFIG_DIR": str(config)}
    done = subprocess.run([*CLI, *args], cwd=repo, env=env, input=stdin, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    """One real run, the way the demo is made: a plan, `graphene run --parallel 2`, then the export."""
    tmp = tmp_path_factory.mktemp("demo")
    repo, config = tmp / "feeds", tmp / "claude"
    (repo / "feeds").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "feeds" / "__init__.py").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    graphene(repo, config, "plan", "goal", "the feeds tool reads csv, xml and json")
    graphene(repo, config, "plan", "propose", "-", stdin=PLAN)
    (repo / "feeds" / "yaml_reader.py").write_text("# the person's own, not committed yet\n")
    (tmp / "executor.py").write_text(EXECUTOR)
    executor = f"{sys.executable} {tmp / 'executor.py'}"
    said = graphene(repo, config, "run", "--parallel", "2", "--attempts", "2", "--with", executor)
    assert "run: 2 done, 2 came back (json-reader, parser), 1 in review (yaml-reader)" in said, said
    page = tmp / "site" / "index.html"
    graphene(repo, config, "ui", "--export", str(page))
    return page.read_text(encoding="utf-8"), repo


def inlined(page: str) -> dict:
    start = page.index(ui.DATA_TAG) + len(ui.DATA_TAG)
    return json.loads(page[start : page.index("</script>", start)].replace("<\\/", "</"))


def test_the_export_of_a_parallel_run_carries_the_tree_and_each_leafs_state_and_record(exported):
    plan = inlined(exported[0])["plan"]
    at = {n["id"]: n for n in plan["nodes"]}
    assert plan["goal"] == "the feeds tool reads csv, xml and json"
    assert list(at) == ["readers", "csv-reader", "xml-reader", "json-reader", "yaml-reader", "parser"]
    readers = at.pop("readers")  # parents first
    assert (readers["sub_goal"], readers["leaves_done"], readers["leaves_total"]) == (True, 2, 5)
    assert {i: n["state"] for i, n in at.items()} == {
        "csv-reader": "done", "xml-reader": "done", "json-reader": "open", "yaml-reader": "review",
        "parser": "open",
    }  # fmt: skip
    # a leaf that came back reads so, and waits on the person, as the terminal says (decision 42)
    assert at["json-reader"]["display_state"] == at["parser"]["display_state"] == "came back"
    assert [w["id"] for w in plan["waiting_on_person"]] == ["json-reader", "yaml-reader", "parser"]
    record = {i: [(e["kind"], e["said"]) for e in n["log"]] for i, n in at.items()}
    # who held it, what it was refused, the check Graphene ran, what changed, and that it landed
    csv = record["csv-reader"]
    assert [kind for kind, _ in csv][:3] == ["added", "started", "attempt"]
    # held by the executor `run` started, named by its command and not by where it lives on this disk,
    # and by that one name in its own acts (its refused `done`) as in the run's
    held = f"run:{Path(sys.executable).name}"
    assert at["csv-reader"]["log"][1]["actor"] == at["csv-reader"]["executor"] == held
    assert {e["actor"] for e in at["csv-reader"]["log"] if e["actor"].startswith("run:")} == {held}
    assert ("refused", "NOTES.md") in csv
    assert ("check_passed", "test -s feeds/csv_reader.py") in csv
    finished, landed = ("finished", "changed: feeds/csv_reader.py"), ("landed", "feeds/csv_reader.py")
    assert csv.index(finished) < csv.index(landed)
    why = "the json reader needs feeds/parse.py, outside its scope"
    assert ("released", why) in record["json-reader"]
    assert at["json-reader"]["waits"][0] == f"handed back: {why}"
    # yaml-reader passed, and git refused its merge: what git said is its record, the checkout by name
    [(_, unlanded)] = [e for e in record["yaml-reader"] if e[0] == "unlanded"]
    assert unlanded.startswith("git merge --no-ff --no-edit failed in feeds: error: The following untracked")
    # the parser came back after its check failed on both attempts, each run by the executor's own
    # `done` and again by the run: the page names the check, never what it printed
    assert record["parser"].count(("check_failed", f"{sys.executable} -m feeds.parser")) == 4
    assert at["parser"]["waits"][0] == (
        "handed back: 2 attempts, the last one refused: parser is not done: "
        f"`{sys.executable} -m feeds.parser` failed:"
    )


def test_the_exported_page_fetches_nothing_holds_no_token_cannot_write_and_keeps_no_check_output(exported):
    exported, repo = exported
    data = inlined(exported)
    assert "PRIVATE-4242" not in exported  # what the parser's check printed, four times, stays here
    assert str(repo) not in exported  # and where the checkout is on this disk
    assert data["plan"]["token"] is None and data["plan"]["writable"] is False
    markup = re.sub(r"<script[^>]*>.*?</script>", "", exported, flags=re.S)  # the page, not its code
    assert not re.search(r'\b(src|href)="(?!data:)', markup)  # its script and style are inlined
    # no Claude Code session to draw a map of: the page keeps that screen shut (Plan.test.tsx)
    assert data["runs"] == [] and data["graph"]["lanes"] == []


def test_the_export_draws_each_leafs_forks_and_never_a_sandboxs_image(tmp_path):
    """The tree of sandboxes: under a leaf, its last attempt's forks as the Nemotron executor logged them,
    the one that passed marked by its state, each with its sandbox's checkpoint, operations and seconds.
    Never the image (the sandbox's own id on the provider's service), nor more of a reason than its first
    line (decision 64)."""
    from graphene_map import plan
    from graphene_map.store import Store

    repo = tmp_path / "feeds"
    repo.mkdir()
    git(repo, "init", "-q")
    image, nano = "3f2a1b9c-0d4e-4f6a-8b8c-9d0e1f2a3b4c", "nvidia/Nemotron-3-Nano-fake"
    run = plan.Caller("run:nemotron", False, "5e55")
    with Store.open(repo) as store:
        plan.set_goal(store, "say hello", plan.Caller("alex", True))
        plan.propose(store, [{"id": "greet", "title": "hello", "scope": ["app.py"], "check": "true"}],
                     plan.Caller("alex", True))  # fmt: skip
        plan.start(store, "greet", run, repo)
        store.log_node("greet", plan._now(), "model", run.label, None, None, {"attempt": 1, "model": nano})
        ends = [("gave up", "it needs other.py\nPRIVATE-4242 from what it read", "made"),
                ("passed", "its check passed first", "forked")]  # fmt: skip
        for k, (state, why, checkpoint) in enumerate(ends, 1):
            store.log_node("greet", plan._now(), "fork", run.label, run.session_id, None,
                           {"fork": k, "of": 2, "model": nano, "state": state, "why": why, "image": image,
                            "checkpoint": checkpoint, "ops": 5 + k, "seconds": 3.5})  # fmt: skip
        page = ui.export_html(store, [])
    [greet] = inlined(page)["plan"]["nodes"]
    assert greet["forks"] == [
        {"fork": 1, "of": 2, "model": nano, "state": "gave up", "why": "it needs other.py",
         "checkpoint": "made", "ops": 6, "seconds": 3.5},
        {"fork": 2, "of": 2, "model": nano, "state": "passed", "why": "its check passed first",
         "checkpoint": "forked", "ops": 7, "seconds": 3.5},
    ]  # fmt: skip
    assert image not in page and "PRIVATE-4242" not in page


def test_the_export_draws_a_fork_its_stopped_run_left_running_as_stopped(tmp_path):
    """:stop or Ctrl-C mid-fork hands the leaf back before the fork threads write their end: the page
    drew such a fork running, with the counts it started with. It is stopped, and why; no count."""
    from graphene_map import plan
    from graphene_map.run import STOPPED
    from graphene_map.store import Store

    repo = tmp_path / "feeds"
    repo.mkdir()
    git(repo, "init", "-q")
    nano, run = "nvidia/Nemotron-3-Nano-fake", plan.Caller("run:nemotron", False, "5e55")
    with Store.open(repo) as store:
        plan.set_goal(store, "say hello", plan.Caller("alex", True))
        plan.propose(store, [{"id": "greet", "title": "hello", "scope": ["app.py"], "check": "true"}],
                     plan.Caller("alex", True))  # fmt: skip
        plan.start(store, "greet", run, repo)
        store.log_node("greet", plan._now(), "model", run.label, None, None, {"attempt": 1, "model": nano})
        store.log_node("greet", plan._now(), "fork", run.label, run.session_id, None,
                       {"fork": 1, "of": 1, "model": nano, "state": "running", "why": "", "image": "x",
                        "checkpoint": "made", "ops": 0, "seconds": 0.0})  # fmt: skip
        plan.release(store, "greet", run, STOPPED)
        page = ui.export_html(store, [])
    [greet] = inlined(page)["plan"]["nodes"]
    why = "its executor was stopped before this fork ended"
    assert greet["forks"] == [
        {"fork": 1, "of": 1, "model": nano, "state": "stopped", "why": why, "checkpoint": "made"}
    ]


def test_the_pages_workflow_publishes_the_demo_only_when_started_by_hand():
    """Nothing deploys by itself: Pages is the owner's to enable, and the workflow's to run on request."""
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "pages.yml").read_text()
    trigger = workflow.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert trigger.strip() == "workflow_dispatch:"
    assert "path: docs/demo\n" in workflow and "test -s docs/demo/index.html" in workflow
