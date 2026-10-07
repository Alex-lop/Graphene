"""docs/HOW_IT_WORKS.md is the reference a user reads after the README: under 3,000 words, with every
section it promises, in order."""

from pathlib import Path

HOW = (Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text(encoding="utf-8")
SECTIONS = ["The plan", "The board", "The views", "Plan first", "Ask", "Run", "The executors",
            "The meter", "Where each mechanism ends", "The record", "The settings", "Privacy", "FAQ",
            "The rest"]  # fmt: skip


def test_it_is_under_three_thousand_words():
    assert len(HOW.split()) < 3000


def test_every_section_is_there_in_order():
    headings = [line[3:] for line in HOW.splitlines() if line.startswith("## ")]
    assert headings == SECTIONS
