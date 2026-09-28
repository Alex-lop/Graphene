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
