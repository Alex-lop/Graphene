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
    from graphene_map import ask, planner

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


def test_the_readme_s_privacy_says_precheck_uploads_the_checkout_to_sandboxes():
    import inspect

    from graphene_map import precheck

    forks = inspect.getsource(precheck._forks)
    assert 'or "contree"' in forks and "S.pack(root)" in forks  # ConTree by default, the checkout packed
    privacy = doc("README.md").split("## Privacy")[1].split("## ")[0]
    assert "`plan precheck` uploads your checkout to Sandboxes when ConTree's credentials are set" in privacy
    assert "whatever the planner" in privacy
