"""The committed terminal UI SVG is what the generator produces, and is labelled as a replay."""

from __future__ import annotations

from pathlib import Path

from scripts.generate_tui_screenshot import DEFAULT_OUTPUT, render

ROOT = Path(__file__).parents[3]


def test_checked_in_tui_screenshot_exactly_regenerates_and_is_labelled() -> None:
    # Byte-identical on macOS and in the pinned python:3.13-slim image, so this
    # runs unguarded on both CI platforms.
    svg = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert svg == render()

    # What the README claims the frame shows. Rich emits the DAG one character
    # per <text>, so the banner run and the retry glyph are the only anchors;
    # spaces inside a run are non-breaking.
    assert "checkpoint&#160;4/11" in svg
    assert svg.count("↻") == 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/assets/tui_replay.svg" in readme
    assert "NOT A LIVE MODEL MISSION" in readme and "NOT FILMED" in readme
