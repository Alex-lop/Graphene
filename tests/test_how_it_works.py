"""docs/HOW_IT_WORKS.md is the reference a user reads after the README: under 3,300 words, with every
section it promises, in order. The cap was 3,000 until 10 October 2026, when the reference gained what init does
to a Claude Code session and how to undo it, the run's first line and red first's warnings, and what the record
and the merge message now say; it was raised once, on purpose, after the words that no claim pinned were cut."""

from pathlib import Path

HOW = (Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text(encoding="utf-8")
SECTIONS = ["The plan", "The board", "The views", "Plan first", "Ask", "Run", "The executors",
            "The meter", "Where each mechanism ends", "The record", "The settings", "Privacy", "FAQ",
            "The rest"]  # fmt: skip


def test_it_is_under_the_cap():
    assert len(HOW.split()) < 3300


def test_every_section_is_there_in_order():
    headings = [line[3:] for line in HOW.splitlines() if line.startswith("## ")]
    assert headings == SECTIONS
