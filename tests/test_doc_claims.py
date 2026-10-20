"""What the submission draft, the README, HOW_IT_WORKS and the storyboard say, held to what the code and
the recorded results say: each test fails when a sentence goes stale against its source."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def doc(path: str) -> str:
    """The file with its lines joined, so a phrase is found across a line break."""
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


def test_the_submission_reports_the_shaping_studies_board_against_outline_whatever_they_said():
    results = (ROOT / "dev/test/results-2026-09-28-shaping.md").read_text(encoding="utf-8")
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
    for path in ("README.md", "docs/HACKATHON.md", "docs/HOW_IT_WORKS.md", "dev/demo/STORYBOARD.md"):
        said = doc(path)
        assert "about five" not in said and "what it would leave out" not in said, path
        assert "what it assumed, the risks it sees" not in said, path
    assert f"Since prompt version {planner.PROMPT_VERSION}, Ultra" in doc("docs/HACKATHON.md")


def test_the_docs_say_graphene_watch_shows_and_counts_the_board_as_it_does():
    import inspect

    from graphene_map import tui

    source = inspect.getsource(tui)
    assert "board_rows as BR" in source and 'Binding("p", "board(\'p\')"' in source
    assert "on the board" in source  # the status line counts the board's open items
    hackathon, storyboard = doc("docs/HACKATHON.md"), doc("dev/demo/STORYBOARD.md")
    assert "the screen does not yet show it" not in hackathon
    assert "does not show the board" not in storyboard
    assert "In `graphene watch` the items are the first rows under the goal" in hackathon


def test_what_nemotron_sends_says_precheck_uploads_the_checkout_to_sandboxes():
    import inspect

    from graphene_map.nemotron import precheck

    forks = inspect.getsource(precheck._forks)
    assert 'or "contree"' in forks and "S.pack(root)" in forks  # ConTree by default, the checkout packed
    privacy = doc("docs/HOW_IT_WORKS.md").split("## Privacy")[1].split("## ")[0]
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
    assert "naming one implies --classic." in said and "view` setting" not in said


def test_the_drafts_carry_no_integ_only_marker_now_that_every_command_they_named_is_here():
    from typer.testing import CliRunner

    from graphene_map.cli import build

    named = (["board"], ["talk"], ["plan", "changes"], ["plan", "seen"], ["key"], ["config", "edit"],
             ["plan", "cover"], ["plan", "note"], ["plan", "precheck"])  # fmt: skip
    for words in named:
        assert CliRunner().invoke(build(), [*words, "--help"]).exit_code == 0, words
    for path in ("docs/HACKATHON.md", "dev/demo/STORYBOARD.md"):
        said = doc(path)
        assert "integ only" not in said and "For the coordinator" not in said, path
        assert "not yet on `shaping`" not in said, path


def test_the_submission_says_only_taken_picked_and_answered_items_reach_the_executors():
    from graphene_map import board as B

    assert set(B.DECIDED) == {"taken", "picked", "answered"}  # what board.told() passes on, with notes
    said = doc("docs/HACKATHON.md")
    assert "Every answer reaches the executors'" not in said
    assert "a dropped or parked item is told to no one" in said
    assert "Each answer goes to that leaf's executor" not in doc("dev/demo/STORYBOARD.md")


def test_first_lights_model_table_is_the_live_list_the_fixture_keeps():
    """dev/test/first-light.md's NVIDIA models, roles and prices are the fixture's, which came from rung 1's
    access.json (practice, 2026-09-29): the doc and the tests that use the list cannot drift apart."""
    import json

    live = json.loads((ROOT / "tests/fixtures/tokenfactory-models-2026-09-29.json").read_text())
    role = {v: k for k, v in live["roles"].items()}
    rows = re.findall(r"^\| `(nvidia/[^`]+)` \| (\w+) \| ([\d.]+) / ([\d.]+) \|$",
                      (ROOT / "dev/test/first-light.md").read_text(encoding="utf-8"), re.M)  # fmt: skip
    want = [(m["id"], role.get(m["id"], "none"), f"{m['pricing']['prompt'] * 1e6:.2f}",
             f"{m['pricing']['completion'] * 1e6:.2f}") for m in live["data"]]  # fmt: skip
    assert rows == want
    assert "**Practice, not a registered result.**" in doc("dev/test/first-light.md")


def test_the_readme_and_changelog_name_what_first_light_added():
    """A walker found the README and CHANGELOG silent on the direction, `board lookup` and the board's
    setting (walk findings 9, 30, 39)."""
    from typer.testing import CliRunner

    from graphene_map import settings as S
    from graphene_map.cli import build

    for words in (["direction"], ["board", "lookup"]):
        assert CliRunner().invoke(build(), [*words, "--help"]).exit_code == 0, words
    assert S.BOARDS[0] == "auto"  # the first is the value when unset
    for path in ("docs/HOW_IT_WORKS.md", "CHANGELOG.md"):  # the README argues; the reference lists
        assert "`board: auto`" in doc(path), path
    for path in ("docs/HOW_IT_WORKS.md", "CHANGELOG.md"):  # hidden now: "The rest" lists it
        said = doc(path)
        assert "graphene direction" in said, path
    for path in ("docs/HACKATHON.md", "CHANGELOG.md"):  # board lookup is the Nemotron extra's
        assert "board lookup" in doc(path), path
        live = "As practice on 2 October, Nemotron planned a small feature 5 times"
        assert live in " ".join(said.split()), path


def test_the_changelog_names_what_the_feel_pass_changed():
    """A seam reader: the unreleased 0.5.0 entry admitted one of the feel pass's twelve changes; decisions.md
    gave lane C one entry for the pass, a draft in the owner's voice, and none landed."""
    from graphene_map import demo
    from graphene_map import view_time as VT

    said = doc("CHANGELOG.md").split("## 0.4.0")[0]
    assert demo.STAND_IN in said and VT.HELD in said and "planner asked" in said and "the plan of" in said


def test_the_changelogs_red_first_bullet_says_what_the_lines_say_now():
    """A seam reader: the unreleased 0.5.0 entry said the header counts the commands, a clause the feel pass
    cut from the header, and nothing of the gloss the per-command line says now."""
    said = doc("CHANGELOG.md").split("## 0.4.0")[0]
    assert "the header counts the commands" not in said and "would pass with nothing done" in said


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
        assert "drops a node" in said or path == "README.md", path  # the README leaves it to the reference
        assert "or `D` in `graphene watch`" not in said and "opens `:direction attach" not in said, path
        assert "and an agent's note, stay open" not in said, path


def test_live_session_names_only_scripts_that_exist_and_practice_steps_the_ladder_knows():
    import importlib.util

    said = doc("dev/test/LIVE_SESSION.md")
    spans = re.findall(r"`([^`]+)`", said)
    scripts = {s for span in spans for s in re.findall(r"[\w./-]+\.(?:py|sh)\b", span)}
    assert {"dev/test/practice.sh", "dev/test/arm_bprime.py", "dev/demo/build.sh"} <= scripts
    for script in scripts:  # a bare name is one of the harnesses beside it
        where = [ROOT / script] if "/" in script else [ROOT / "dev" / d / script for d in ("test", "demo")]
        assert any(p.is_file() for p in where), script
    spec = importlib.util.spec_from_file_location("practice_named", ROOT / "dev/test/practice.py")
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
    said = doc("dev/test/first-light.md")
    assert "In a test run in this repository, ConTree also answered" not in said
    assert "a harness slip, not from the ladder and not practice" in said
    assert "Its only record is the message of commit e5efb4f" in said
    assert "No log of that run was kept" in said


def test_the_readme_says_what_init_does_to_claude_code_and_how_to_undo_it():
    """The first-hour readers of 10 October 2026 found 'plan first' 0 times in the README, no uninstall
    anywhere, and a demo called a recorded run that replays a scripted stand-in. The commands named are
    held to the CLI; R's question is held to its keys by test_tui's
    test_a_run_that_could_start_more_than_one_leaf_asks_first_and_one_leaf_starts_at_once."""
    from typer.testing import CliRunner

    from graphene_map.cli import build

    readme = doc("README.md")
    said = ("`graphene init --remove`", "`graphene plan first off`", "scripted replay",
            "it asks first when more than one task could start")  # fmt: skip
    for phrase in said:
        assert phrase in readme, phrase
    how = doc("docs/HOW_IT_WORKS.md")
    told = ("`graphene init --remove`", "`graphene node diff", "outside Claude Code", "installed editable")
    for phrase in told:
        assert phrase in how, phrase
    runner = CliRunner()
    assert "--remove" in runner.invoke(build(), ["init", "--help"], env={"COLUMNS": "200"}).stdout
    for words in (["node", "diff"], ["plan", "first"]):  # each a command, not only words
        assert runner.invoke(build(), [*words, "--help"]).exit_code == 0, words


def test_the_submissions_live_record_is_what_the_takes_records_say():
    """docs/HACKATHON.md says what ran live on Token Factory: each count of the takes of 7 to 9 October and of
    the planner's asks is read here from the record it names, and the chart it once promised is gone."""
    said = doc("docs/HACKATHON.md")
    nights = ("meter", "timeline", "loop")  # 7, 8 and 9 October
    records = [(ROOT / f"dev/process/{d}/takes.md").read_text(encoding="utf-8") for d in nights]
    takes = [len(re.findall(r"^\| \d+ \| (?:feeds|report) \|", r, re.M)) for r in records]
    clean = sum(r.count("**Clean") for r in records)
    whole = sum(r.count("**Clean, end to end.**") for r in records)
    assert f"{sum(takes)} more takes" in said and f"({takes[0]}, then {takes[1]}, then {takes[2]})" in said
    assert f"{clean} of the {sum(takes)} takes ran clean, {whole} of them with every task landed" in said
    meter, after = doc("dev/process/meter/takes.md"), doc("dev/process/loop/after.md")
    readable, of = re.search(r"Ultra planned a readable tree in (\d+) of (\d+) takes", meter).groups()
    assert f"{readable} of {of} a readable plan" in said
    plans, asks = re.findall(r"\*\*(\d+) proposals in (\d+) asks", after)[-1]  # round 2, the final build
    assert f"became a plan in {plans} of {asks} asks" in said
    assert "The chart goes here" not in said and "Everything else on the Nemotron path" in said


def test_the_submissions_testing_instructions_name_the_key_the_extra_and_the_init_and_each_is_real():
    """A judge follows the end of docs/HACKATHON.md: every graphene command in its blocks is the CLI's, with
    options it takes; every recording it replays is in the repository and replays as live; the extra it
    installs is pyproject's; and the Nemotron path's key and init are there."""
    import shlex
    import tomllib
    from itertools import takewhile

    from typer.testing import CliRunner

    from graphene_map import demo as D
    from graphene_map.cli import build

    section = (ROOT / "docs/HACKATHON.md").read_text(encoding="utf-8").split("## Testing instructions")[1]
    nemotron = ("graphene key set", "NEBIUS_API_KEY", "graphene init --planner nemotron --executor nemotron")
    for step in nemotron:
        assert step in section, step
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert "nemotron" in extras and "'graphene-map[nemotron]'" in section
    blocks = re.findall(r"^```\n(.*?)^```", section, re.M | re.S)
    lines = [line.split("#")[0].strip() for block in blocks for line in block.splitlines()]
    runner, ran = CliRunner(), 0
    for line in lines:
        words = shlex.split(re.sub(r"^(uvx --from graphene-map |uv run )", "", line))
        for path in [w for w in words if w.startswith("tests/")]:
            assert (ROOT / path).exists(), path
            if path.endswith(".jsonl"):
                assert D.load(ROOT / path)[0]["shown"] == D.LIVE, path  # the section calls them live runs
        if words[:1] != ["graphene"]:
            continue
        sub = list(takewhile(lambda w: re.fullmatch(r"[a-z]+", w), words[1:]))  # the command, not its words
        helped = runner.invoke(build(), [*sub, "--help"], env={"COLUMNS": "200"})
        assert helped.exit_code == 0, line
        for option in [w for w in words if w.startswith("--")]:
            assert option in helped.stdout, (line, option)
        ran += 1
    assert ran >= 8


def test_the_storyboard_replays_live_recordings_and_pauses_where_their_tasks_come_back():
    """dev/demo/STORYBOARD.md films most of the video from recordings of live runs: each one it names is in
    the repository and replays as live, and the changes it pauses at are where a task came back and was
    widened, and where another came back and its owner was reopened. The narration says both names the rules
    want said aloud."""
    from graphene_map import demo as D

    said = doc("dev/demo/STORYBOARD.md")
    named = sorted(set(re.findall(r"tests/recordings/[\w-]+\.jsonl", said)))
    assert "tests/recordings/loop-nemotron-2.jsonl" in named
    for path in named:
        assert D.load(ROOT / path)[0]["shown"] == D.LIVE, path
    _, changes = D.load(ROOT / "tests/recordings/loop-nemotron-2.jsonl")

    def kinds(n: int) -> set[str]:  # change n, as the replay's top line counts it (`91 of 322`)
        return {row["kind"] for row in changes[n - 1].get("node_log") or []}

    assert "at change 91:" in said and "released" in kinds(91) and "edited" in kinds(92)
    assert "at change 297:" in said and "released" in kinds(297) and "reopened" in kinds(298)
    text = (ROOT / "dev/demo/STORYBOARD.md").read_text(encoding="utf-8")
    narration = " ".join(re.findall(r'^\| \d{2} \|.*\| "(.+)" \|$', text, re.M))
    assert "Token Factory" in narration and "Nemotron" in narration


def test_the_hackathon_kit_names_the_roles_init_gives_nemotron_and_one_built_with_list(monkeypatch):
    """dev/launch/hackathon.md is what the Devpost form and the README's Nemotron section paste: the sizes it
    names for each role are the ones `graphene init --planner nemotron --executor nemotron` writes from Token
    Factory's list (as it stood on 29 September), and its Built with is docs/HACKATHON.md's, item for item."""
    import json

    from graphene_map.nemotron import key_cli, sandbox
    from graphene_map.nemotron import tokenfactory as tf

    live = json.loads((ROOT / "tests/fixtures/tokenfactory-models-2026-09-29.json").read_text())
    listed = [tf.Model(m["id"], m["pricing"]["prompt"], m["pricing"]["completion"]) for m in live["data"]]
    monkeypatch.setattr(tf, "reach", lambda tries=1: None)
    monkeypatch.setattr(tf, "models", lambda tries=1: listed)
    monkeypatch.setattr(sandbox, "configured", lambda: False)
    _, said, _, _ = key_cli.offer()  # "Ultra plans, Nano then Super do the leaves"
    planner, doers = re.fullmatch(r"(\w+) plans, (.+) do the leaves", said).groups()
    first, retry = doers.split(" then ")
    kit = doc("dev/launch/hackathon.md")
    assert f"Nemotron 3 {planner} is the planner" in kit and f"Nemotron 3 {first} does the tasks" in kit
    assert f"steps up to Nemotron 3 {retry}" in kit

    def built(path: str) -> list[str]:
        section = (ROOT / path).read_text(encoding="utf-8").split("## Built with")[1].split("##")[0]
        return [" ".join(item.split()) for item in section.split("·")]

    assert built("dev/launch/hackathon.md") == built("docs/HACKATHON.md")
    assert "nvidia-nemotron (3 Ultra, Super, Nano)" in built("docs/HACKATHON.md")


def test_the_submission_says_nemotron_on_token_factory_before_it_says_claude_code():
    """Stage one of the judging is pass or fail on whether the entry runs on Token Factory with a Nemotron
    model, and a judge may read only the text: What it does names both before it names Claude Code."""
    said = doc("docs/HACKATHON.md").split("## What it does")[1].split("## ")[0]
    first = said.index("Claude Code")
    assert said.index("Nemotron") < first and said.index("Token Factory") < first


def test_every_count_the_hackathon_kits_readme_section_gives_is_one_claims_md_allows():
    """The README section in dev/launch/hackathon.md is pasted as it is, so each "N of M" it says is listed
    under "May be said" in dev/launch/claims.md, which every public sentence answers to."""
    kit = doc("dev/launch/hackathon.md").split("## The README section")[1]
    allowed = doc("dev/launch/claims.md").split("## May be said")[1].split("## May not be said")[0]
    counts = re.findall(r"\b\d+ of \d+\b", kit)
    assert counts
    for count in counts:
        assert count in allowed, count


def test_the_storyboards_budget_says_what_the_asks_that_ended_in_no_plan_cost_of_the_40_it_counts():
    """dev/demo/STORYBOARD.md pairs "35 of 40 asks" with what an ask that ended without a plan still cost: the
    five of those 40 that did, as dev/process/loop/asks-round2.md records each, not two takes that night."""
    record = (ROOT / "dev/process/loop/asks-round2.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (?:feeds|report) \| \d+ \| (yes|no) \|(?:[^|]*\|){4} ([\d.]+) \|", record, re.M)
    missed = [float(dollars) for proposed, dollars in rows if proposed == "no"]
    assert len(rows) == 40 and len(missed) == 5
    said = doc("dev/demo/STORYBOARD.md")
    planned = f"{len(rows) - len(missed)} of {len(rows)} asks did on 9 October"
    cost = f"${min(missed):.2f} to ${max(missed):.2f} (`dev/process/loop/asks-round2.md`)"
    assert f"{planned}, and an ask without one still cost {cost}" in said


def test_the_storyboards_live_take_runs_nothing_after_a_line_that_fails():
    """A second take into the first take's directory fails at its first line (make_task.py refuses a directory
    that is not empty), and the lines under it ran where the shell stood: the init and a paid ask in the clone
    itself. Each line of the take but the last ends in &&, so the first that fails stops the rest."""
    text = (ROOT / "dev/demo/STORYBOARD.md").read_text(encoding="utf-8")
    block = text.split("**2. The live take")[1].split("\n\n")[1]
    lines = [line.strip() for line in block.splitlines()]
    assert lines[0].startswith("python3 dev/test/make_task.py feeds ") and lines[-1] == "graphene watch"
    assert any(line.startswith("graphene ask ") for line in lines)
    assert all(line.endswith(" &&") for line in lines[:-1]), lines


def test_the_kits_readme_section_and_claims_say_the_live_takes_ran_on_two_repositories():
    """The takes of 7 to 9 October ran the demo on two repositories, feeds and report, as docs/HACKATHON.md
    says; the README section the kit pastes, and claims.md, said they were takes of one small demo task."""
    nights = ("meter", "timeline", "loop")  # 7, 8 and 9 October
    records = [(ROOT / f"dev/process/{d}/takes.md").read_text(encoding="utf-8") for d in nights]
    tasks = [t for r in records for t in re.findall(r"^\| \d+ \| (feeds|report) \|", r, re.M)]
    assert set(tasks) == {"feeds", "report"}
    kit, claims = doc("dev/launch/hackathon.md"), doc("dev/launch/claims.md")
    assert "demo task" not in kit + claims
    assert f"{len(tasks)} demo takes on two small repositories" in kit.split("## The README section")[1]
    assert f"Of {len(tasks)} live demo takes on two small repositories" in claims


def test_the_storyboards_narration_gives_w_the_one_verb_the_screen_does():
    """The night's words give `w` one verb, widen, where it had three (allow, widen it, give it); scene 07
    said "w gives it that file" over a row whose key reads "w widen it"."""
    text = (ROOT / "dev/demo/STORYBOARD.md").read_text(encoding="utf-8")
    narration = " ".join(re.findall(r'^\| \d{2} \|.*\| "(.+)" \|$', text, re.M))
    verbs = re.findall(r"\bw (\w+)", narration)
    assert verbs and all(verb.startswith("widen") for verb in verbs), verbs


def test_compare_says_where_the_diff_is_and_quotes_agent_view_and_agent_teams_as_their_docs_say():
    """docs-audit (18 October): COMPARE said `c` in `graphene watch` shows a sign-off's diff, which is `i`
    then `c` in the cockpit, and it had no row for Claude Code's Agent View or Agent Teams. Each quote in
    their rows is one the field reader took from their docs (dev/process/publish/readers/field.md)."""
    from graphene_map import settings as S
    from graphene_map.cockpit import app as A
    from graphene_map.cockpit import details as D

    assert A.KEYS_TO_VERBS["i"] == "details" and D.KEYS["c"] == "changes" and "every" in S.REVIEWS
    lines = (ROOT / "docs/COMPARE.md").read_text(encoding="utf-8").splitlines()
    graphene = next(line for line in lines if line.startswith("| **Graphene**"))
    assert "`review: every`" in graphene and "`i` then `c` in the cockpit shows its diff" in graphene
    field = doc("dev/process/publish/readers/field.md")
    for name in ("Claude Code Agent View", "Claude Code Agent Teams"):
        row = next(line for line in lines if line.startswith(f"| {name} "))
        quotes = re.findall(r'"([^"]+)"', row)
        assert len(quotes) >= 2, name
        for quote in quotes:
            assert quote in field, quote


def test_a_run_says_at_its_top_that_it_is_from_before_the_cockpit():
    """The README links A_RUN as a real run, and a judge who opens it finds the tree view of 7 October, not
    the cockpit the README shows: its first line under the title says so."""
    text = (ROOT / "docs/A_RUN.md").read_text(encoding="utf-8")
    title, first = [line for line in text.splitlines() if line.strip()][:2]
    assert title == "# A run on feeds, 7 October 2026"
    assert first == "*This run is from 7 October 2026, before the cockpit: its screens are the older ones.*"


def test_ideas_next_says_what_the_night_did_and_what_is_still_not_done():
    """dev/ui/IDEAS.md still listed sub-goal boxes as not done once the graph drew them from your goal down
    (18 October); on 20 October the graph turned to flow into the goal, with sub-goals as lanes and no box
    for them, and the line says that instead; it stays a three-minute read, under 750 words."""
    from graphene_map.cockpit import flow_view as FV
    from graphene_map.cockpit import flowlayout as F
    from graphene_map.cockpit.look import who

    assert FV.GOAL and F.Lane and not hasattr(FV, "TREE")  # a box for the goal, a lane a sub-goal, no tree
    assert who("2") == "agent 2"  # agents by number
    text = (ROOT / "dev/ui/IDEAS.md").read_text(encoding="utf-8")
    assert len(text.split()) < 750
    done, left = " ".join(text.split("## Next")[1].split()).split(" Not done: ")
    assert "flows into your goal" in done and "agents by number" in done
    for still in ("an hour of real agents on these screens", "Tell on Codex", "the intent graph"):
        assert still in left, still


def test_the_release_notes_are_this_versions_and_every_command_they_name_is_the_clis():
    """dev/launch/release-notes.md is pasted into the GitHub release, and it was 0.5.1's, a version PyPI never
    got. It names pyproject's version and says 0.5.1 was never published; the two install lines are the
    package's and its `graphene-map` command's; it has six to ten bullets, the watch first; each command it
    names, with each option, answers `--help`."""
    import shlex
    import tomllib
    from itertools import takewhile

    from typer.testing import CliRunner

    from graphene_map.cli import build

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    text = (ROOT / "dev/launch/release-notes.md").read_text(encoding="utf-8")
    said = " ".join(text.split())
    assert text.startswith(f"# Graphene {project['version']}\n")
    assert "0.5.1 was tagged on 16 October and never published" in said
    assert "graphene-map" in project["scripts"] and project["name"] == "graphene-map"
    assert "`uv tool install graphene-map`" in said and "`uvx graphene-map demo`" in said
    bullets = re.findall(r"^- \*\*(.+?)\*\*", text.split("## What you get")[1].split("## ")[0], re.M)
    assert 6 <= len(bullets) <= 10 and "watch" in bullets[0]
    runner, ran = CliRunner(), 0
    for span in re.findall(r"`(graphene [^`]+)`", said):
        words = shlex.split(span)
        sub = list(takewhile(lambda w: re.fullmatch(r"[a-z]+", w), words[1:]))  # the command, not its words
        helped = runner.invoke(build(), [*sub, "--help"], env={"COLUMNS": "200"})
        assert helped.exit_code == 0, span
        for option in [w for w in words if w.startswith("--")]:
            assert option in helped.stdout, (span, option)
        ran += 1
    assert ran >= 6


def test_the_release_notes_do_not_say_only_claude_code_refuses_the_write_their_demo_shows_nemotron_refuse():
    """The notes said a write outside a task's files is refused before it happens only with Claude Code; the
    demo they point at is a Nemotron run whose write tool refused agent 1's words.py before it was made.
    Nemotron's edit and write refuse a path outside the scope (nemotron/executor.py, its first layer); a
    command it runs outside a Sandbox is caught at done, as a Codex write is."""
    import json

    from graphene_map import demo as D

    rows = [json.loads(line) for line in D.SHIPPED.read_text(encoding="utf-8").splitlines() if line][1:]
    executor = next(r["plan_meta"]["executor"] for r in rows if "executor" in (r.get("plan_meta") or {}))
    denied = [json.loads(e["detail"]) for r in rows for e in r.get("node_log") or [] if e["kind"] == "denied"]
    assert executor.startswith("nemotron ") and {"path": "words.py", "how": "write"} in denied
    said = doc("dev/launch/release-notes.md")
    assert "refused before it happens only with Claude Code" not in said
    assert "refused before it happens by Claude Code's hooks and by Nemotron's edit and write" in said


def test_contributing_runs_the_suite_as_ci_does_and_each_file_it_points_at_does_what_it_says():
    """CONTRIBUTING said the suite takes about 18 minutes in one process, with -n auto "where pytest-xdist is
    installed"; the dev group installs it and CI runs -n auto. Its Python is pyproject's, and the files its
    lines on looking at a screen and recording the demo point at do what they say."""
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    said = doc("CONTRIBUTING.md")
    assert pyproject["project"]["requires-python"] == ">=3.12" and "Python 3.12 or newer" in said
    assert any(dep.startswith("pytest-xdist") for dep in pyproject["dependency-groups"]["dev"])
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for command in ("uv sync --all-extras", "uv run ruff check", "uv run pytest -q -n auto"):
        assert command in said and command in ci, command
    assert "about 18 minutes" not in said
    assert "app.run_test(size=" in (ROOT / "tests/test_cockpit_app.py").read_text(encoding="utf-8")
    assert "app.save_screenshot(" in (ROOT / "dev/screens/meter_shot.py").read_text(encoding="utf-8")
    recipe = "RECORD_DEMO=src/graphene_map/demo.jsonl uv run pytest tests/test_demo_script.py"
    script = (ROOT / "tests/test_demo_script.py").read_text(encoding="utf-8")
    assert recipe in said and 'os.environ.get("RECORD_DEMO")' in script


def test_the_demo_docs_describe_the_recording_graphene_ships_as_it_is(tmp_path):
    """dev/demo/README.md said the shipped recording was 29 September's, and the video's step 4 had one task
    come back; the recording of 19 October has two sub-goals, four tasks, three agents at once, a task that
    comes back, is widened and runs again, and one that waits on two. Each is read from the recording."""
    import json

    from graphene_map import demo as D
    from graphene_map import plan as P
    from graphene_map.store import Store

    head, lines = D.load(D.SHIPPED)
    repo = D.repository(tmp_path, head)
    D.last_frame(repo, lines)
    with Store.open(repo) as store:
        nodes = P.nodes(store)
    rows = [row for line in lines for row in line.get("node_log") or []]
    under = {n.parent for n in nodes if n.parent}
    goals, tasks = [n for n in nodes if n.id in under], [n for n in nodes if n.id not in under]
    runs = [json.loads(row["detail"])["summary"] for row in rows if row["kind"] == "run"]
    at_once = max(int(n) for summary in runs for n in re.findall(r"(\d+) of \d+ at once", summary))
    back = {row["node_id"] for row in rows if row["kind"] == "released"}
    scopes = [(row["node_id"], json.loads(row["detail"])["changed"].get("scope")) for row in rows
              if row["kind"] == "edited"]  # fmt: skip
    wider = {node for node, scope in scopes if scope and len(scope[1]) > len(scope[0])}
    started = [row["node_id"] for row in rows if row["kind"] == "started"]
    assert back & wider == {"greet"} and started.count("greet") == 2  # back, widened, and run again
    assert [n.id for n in tasks if len(n.needs) == 2] == ["hello-bye"]
    say = {2: "two", 3: "three", 4: "four"}
    readme, video = doc("dev/demo/README.md"), doc("dev/launch/video.md")
    assert head["recorded"].startswith("2026-10-19") and "made on 19 October 2026 (UTC)" in readme
    assert f"a plan of {say[len(goals)]} sub-goals and {say[len(tasks)]} tasks" in readme
    assert f"{say[at_once].capitalize()} agents start at once" in readme
    assert "it is widened and tried again as agent 1" in readme and "The fourth task waits on two" in readme
    step = video.split("4. **")[1].split("5. **")[0]
    assert f"{say[len(goals)]} sub-goals, {say[len(tasks)]} tasks. {say[at_once].capitalize()} agents" in step
    assert "is widened and tried again as agent 1" in step and "the two it waits on have landed" in step


def test_the_videos_step_4_plays_what_it_narrates_within_its_seconds():
    """Step 4 narrates the shipped replay up to the task that waits on two starting, which `graphene demo`
    reaches 48 s after it opens, at its own speed, in a step of 20 s: it names a speed that gets there."""
    from graphene_map import demo as D
    from graphene_map.cockpit.replay import opening

    step = doc("dev/launch/video.md").split("4. **")[1].split("5. **")[0]
    begin, end = (int(s) for s in re.match(r"(\d+) to (\d+) s", step).groups())
    typed = re.search(r"Type `graphene demo --speed (\d+)`", step)
    assert typed, step
    _head, lines = D.load(D.SHIPPED, float(typed[1]))
    starts = next(line["at"] for line in lines for row in line.get("node_log") or []
                  if row["kind"] == "started" and row["node_id"] == "hello-bye")  # fmt: skip
    assert starts - opening(lines) <= end - begin


def test_the_scene_tapes_press_the_cockpits_keys_not_the_classic_screens():
    """dev/demo/scenes pressed September's keys, which the cockpit reads as other verbs: `gg` opens the graph
    twice, `zR` runs every ready task, a `/` search types r (run the task), u (undo), n, i and g. A tape now
    presses the cockpit's own key for what its scene does, and scene 04 films only when the screen has a
    question's or a risk's row, which the cockpit marks `?` and `!` where the classic screen said "asks"."""
    from cockpit_scene import scene

    from graphene_map.cockpit import app as A
    from graphene_map.cockpit.rows import build_cockpit

    scenes = sorted((ROOT / "dev/demo/scenes").glob("[0-9][0-9]-*.tape"))
    tapes = {tape.name[:2]: tape.read_text(encoding="utf-8") for tape in scenes}
    typed = {n: [k for k in re.findall(r'^Type "([^"]*)"$', t, re.M) if k != "M"] for n, t in tapes.items()}
    for n, keys in typed.items():  # M is tmux's mark, after its Ctrl+B
        assert not [k for k in keys if k in ("gg", "zR") or k.startswith("/")], n
        assert "\nTab\n" not in tapes[n], n
    assert typed["05"] == ["g", "m", "c"]  # the graph, the map, back to the cockpit
    assert typed["06"][0] == "E" and typed["06"][-2:] == ["A", "y"]  # the plan in the editor; accept all
    assert (A.KEYS_TO_VERBS["E"], A.KEYS_TO_VERBS["A"]) == ("edit-plan", "accept-all")
    only = re.search(r"^# only if: /(.+)/$", tapes["04"], re.M)[1]
    for selected in ("q", "ids"):
        m = scene()
        m.selected = selected
        assert {line.row for line in build_cockpit(m, 120) if re.search(only, line.plain())} == {"q"}


def test_scene_08_films_when_the_cockpit_shows_a_task_that_came_back():
    """Scene 08's `# only if:` looked for "came back", the classic row's word. The cockpit's row of a task
    that came back says its reason and `⏎ try again`; "came back" is only in a run's last line on the news,
    for six seconds, so a take whose task came back mostly skipped the scene that widens and reruns it."""
    from cockpit_scene import scene

    from graphene_map.cockpit.rows import build_cockpit

    tape = (ROOT / "dev/demo/scenes/08-came-back.tape").read_text(encoding="utf-8")
    only = re.search(r"^# only if: /(.+)/$", tape, re.M)[1]
    for width in (80, 120):
        m = scene()
        assert not [line for line in build_cockpit(m, width) if re.search(only, line.plain())]
        m.tasks["tests"].state, m.tasks["tests"].note = "came back", "the word lives in words.py"
        assert {line.row for line in build_cockpit(m, width) if re.search(only, line.plain())} == {"tests"}
