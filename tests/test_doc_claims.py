"""What the submission draft, the README, HOW_IT_WORKS and the storyboard say, held to what the code and
the recorded results say: each test fails when a sentence goes stale against its source."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def doc(path: str) -> str:
    """The file with its lines joined, so a phrase is found across a line break."""
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


def test_the_submission_reports_the_shaping_studies_board_against_outline_whatever_they_said():
    results = (ROOT / "docs/test/results-2026-09-28-shaping.md").read_text(encoding="utf-8")
    said = doc("docs/HACKATHON.md")
    assert "Neither has run" not in said and "where it buys the most" not in said
    rows = re.findall(r"^\| H1: person-s \| (.+?) \| (\d) of 4 \|", results, re.M)
    assert len(rows) == 2  # studies 2 and 3
    for gaps, toward in rows:
        values = [float(v) for v in gaps.split(" / ")]
        assert toward == "0" and all(v > 0 for v in values)  # the board higher on every task
        assert f"+{min(values)} to +{max(values)}" in said
    assert "board higher on 4 of 4 tasks" in said


def test_the_docs_describe_the_planner_prompt_the_code_sends():
    from graphene_map import ask
    from graphene_map.nemotron import planner

    assert "at most three" in " ".join(planner.SYSTEM.split()) and "at most three" in ask.RULES
    how = doc("docs/HOW_IT_WORKS.md")
    assert f"system prompt, version {planner.PROMPT_VERSION})" in how and "at most three items" in how
    for path in ("README.md", "docs/HACKATHON.md", "docs/HOW_IT_WORKS.md", "docs/demo/STORYBOARD.md"):
        said = doc(path)
        assert "about five" not in said and "what it would leave out" not in said, path
        assert "what it assumed, the risks it sees" not in said, path
    assert f"Since prompt version {planner.PROMPT_VERSION}, Ultra" in doc("docs/HACKATHON.md")
    assert "at most three items" in doc("README.md")


def test_the_docs_say_graphene_watch_shows_and_counts_the_board_as_it_does():
    import inspect

    from graphene_map import tui

    source = inspect.getsource(tui)
    assert "board_rows as BR" in source and 'Binding("p", "board(\'p\')"' in source
    assert "on the board" in source  # the status line counts the board's open items
    hackathon, storyboard = doc("docs/HACKATHON.md"), doc("docs/demo/STORYBOARD.md")
    assert "the screen does not yet show it" not in hackathon
    assert "does not show the board" not in storyboard
    assert "In `graphene watch` the items are the first rows under the goal" in hackathon


def test_the_dag_note_the_docs_quote_is_the_one_view_dag_prints_for_their_scratch_plan():
    from graphene_map import plan as P
    from graphene_map import view_dag as V

    def leaf(i, needs=(), scoped=True):
        n = P.Node(
            i, i, scope=[f"{i}.py"] if scoped else [], check="true" if scoped else None, needs=list(needs)
        )
        n.state = P.PROPOSED
        return n

    four = [leaf("xml-reader"), leaf("xml-wire", ["xml-reader"]), leaf("zero-rule"),
            leaf("xml-e2e", ["xml-wire", "zero-rule"])]  # fmt: skip
    five = [*four, leaf("zero-price-product", scoped=False)]  # the board's new leaf: no scope or check yet
    before, after = (V.note(ns, {n.id: P.reads(n, ns) for n in ns}) for ns in (four, five))
    hackathon, storyboard = doc("docs/HACKATHON.md"), doc("docs/demo/STORYBOARD.md")
    assert f"`{before}` on a scratch plan of four proposed leaves" in hackathon
    assert f"`{after}` here" in storyboard and f"`… · {before.split(' · ')[-1]}` before" in storyboard
    assert "2 at once" not in hackathon + storyboard and "Two leaves can start at once" not in storyboard


def test_what_nemotron_sends_says_precheck_uploads_the_checkout_to_sandboxes():
    import inspect

    from graphene_map.nemotron import precheck

    forks = inspect.getsource(precheck._forks)
    assert 'or "contree"' in forks and "S.pack(root)" in forks  # ConTree by default, the checkout packed
    privacy = doc("README.md").split("## Privacy")[1].split("## ")[0]
    assert "With Claude Code or Codex, Graphene sends nothing anywhere." in privacy
    assert "Nemotron on Token Factory is an optional extra; what it sends is in [HACKATHON.md]" in privacy
    sends = doc("docs/HACKATHON.md").split("**What it sends.**")[1].split("**")[0]
    assert "`plan precheck` uploads your checkout to Sandboxes when ConTree's credentials are set" in sends
    assert "whatever the planner" in sends


def test_watch_help_names_no_view_setting_that_no_command_can_set():
    """`config edit` refuses a `view:` line and no command writes one, so --help never sends you to it."""
    from typer.testing import CliRunner

    from graphene_map.cli import build

    said = " ".join(CliRunner().invoke(build(), ["watch", "--help"], env={"COLUMNS": "200"}).stdout.split())
    assert "Left out: the outline." in said and "view` setting" not in said


def test_the_drafts_carry_no_integ_only_marker_now_that_every_command_they_named_is_here():
    from typer.testing import CliRunner

    from graphene_map.cli import build

    named = (["board"], ["talk"], ["plan", "changes"], ["plan", "seen"], ["key"], ["config", "edit"],
             ["plan", "cover"], ["plan", "note"], ["plan", "precheck"])  # fmt: skip
    for words in named:
        assert CliRunner().invoke(build(), [*words, "--help"]).exit_code == 0, words
    for path in ("docs/HACKATHON.md", "docs/demo/STORYBOARD.md"):
        said = doc(path)
        assert "integ only" not in said and "For the coordinator" not in said, path
        assert "not yet on `shaping`" not in said, path


def test_the_submission_says_only_taken_picked_and_answered_items_reach_the_executors():
    from graphene_map import board as B

    assert set(B.DECIDED) == {"taken", "picked", "answered"}  # what board.told() passes on, with notes
    said = doc("docs/HACKATHON.md")
    assert "Every answer reaches the executors'" not in said
    assert "a dropped or parked item is told to no one" in said
    assert "Each answer goes to that leaf's executor" not in doc("docs/demo/STORYBOARD.md")


def test_first_lights_model_table_is_the_live_list_the_fixture_keeps():
    """docs/test/first-light.md's NVIDIA models, roles and prices are the fixture's, which came from rung 1's
    access.json (practice, 2026-09-29): the doc and the tests that use the list cannot drift apart."""
    import json

    live = json.loads((ROOT / "tests/fixtures/tokenfactory-models-2026-09-29.json").read_text())
    role = {v: k for k, v in live["roles"].items()}
    rows = re.findall(r"^\| `(nvidia/[^`]+)` \| (\w+) \| ([\d.]+) / ([\d.]+) \|$",
                      (ROOT / "docs/test/first-light.md").read_text(encoding="utf-8"), re.M)  # fmt: skip
    want = [(m["id"], role.get(m["id"], "none"), f"{m['pricing']['prompt'] * 1e6:.2f}",
             f"{m['pricing']['completion'] * 1e6:.2f}") for m in live["data"]]  # fmt: skip
    assert rows == want
    assert "**Practice, not a registered result.**" in doc("docs/test/first-light.md")


def test_the_readme_and_changelog_name_what_first_light_added():
    """A walker found the README and CHANGELOG silent on the direction, `board lookup` and the board's
    setting (walk findings 9, 30, 39)."""
    from typer.testing import CliRunner

    from graphene_map import settings as S
    from graphene_map.cli import build

    for words in (["direction"], ["board", "lookup"]):
        assert CliRunner().invoke(build(), [*words, "--help"]).exit_code == 0, words
    assert S.BOARDS[0] == "auto"  # the first is the value when unset
    for path in ("README.md", "CHANGELOG.md"):
        said = doc(path)
        assert "graphene direction" in said and "`board: auto`" in said, path
    for path in ("docs/HACKATHON.md", "CHANGELOG.md"):  # board lookup is the Nemotron extra's
        assert "board lookup" in doc(path), path
        live = "As practice on 2 October, Nemotron planned a small feature 5 times"
        assert live in " ".join(said.split()), path


def test_the_docs_say_what_accept_and_r_leave_open_and_that_d_attaches_nothing():
    """Review 2026-09-29 (26, 27, 28): the docs said accept, R and `board take` take every open default
    and leave an agent's note open, and that D attaches a session or opens `:direction attach`."""
    from graphene_map import board as B

    item = {"state": "open", "kind": "question", "default": "no", "then": ["drop legacy"], "agent": True,
            "by": "planner:script"}
    assert not B.has_default(item) and B.has_default({**item, "kind": "note", "default": None, "then": []})
    # what D does is test_d_in_watch_shows_the_direction_across_the_width_live_and_takes_no_key's
    for path in ("README.md", "docs/HOW_IT_WORKS.md", "docs/HACKATHON.md", "CHANGELOG.md"):
        said = doc(path)
        assert "drops a node" in said, path
        assert "or `D` in `graphene watch`" not in said and "opens `:direction attach" not in said, path
        assert "and an agent's note, stay open" not in said, path


def test_live_session_names_only_scripts_that_exist_and_practice_steps_the_ladder_knows():
    import importlib.util

    said = doc("docs/test/LIVE_SESSION.md")
    spans = re.findall(r"`([^`]+)`", said)
    scripts = {s for span in spans for s in re.findall(r"[\w./-]+\.(?:py|sh)\b", span)}
    assert {"docs/test/practice.sh", "docs/test/arm_bprime.py", "docs/demo/build.sh"} <= scripts
    for script in scripts:  # a bare name is one of the harnesses beside it
        where = [ROOT / script] if "/" in script else [ROOT / "docs" / d / script for d in ("test", "demo")]
        assert any(p.is_file() for p in where), script
    spec = importlib.util.spec_from_file_location("practice_named", ROOT / "docs/test/practice.py")
    practice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(practice)
    usage = set(re.findall(r"practice\.sh (\w+)", practice.__doc__)) - {"N"}  # status, night, prototypes
    knows = {str(n) for n in practice.RUNGS} | set(practice.STEPS) | usage
    named = {m for span in spans for m in re.findall(r"practice\.sh (\w+)", span)}
    assert named and named <= knows, named - knows


def test_first_lights_403_for_a_made_up_key_names_its_source_and_says_it_is_no_practice():
    """first-light.md says each fact names its file. The 403 that a made-up key and project got came from a
    harness slip, not from the ladder: the doc says so and names its only record (a commit message, which
    a shallow clone may not hold, so the test reads the doc only)."""
    said = doc("docs/test/first-light.md")
    assert "In a test run in this repository, ConTree also answered" not in said
    assert "a harness slip, not from the ladder and not practice" in said
    assert "Its only record is the message of commit e5efb4f" in said
    assert "No log of that run was kept" in said
