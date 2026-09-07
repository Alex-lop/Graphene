"""Export the terminal UI's own SVG of the checked-in replay, and check it for drift."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

# NO_COLOR is read in App.__init__ and the TEXTUAL_* names at textual import
# time; either changes every colour in the exported SVG, so an exported
# variable on a developer's machine would break --check for no real reason.
for _variable in (
    "NO_COLOR",
    "TEXTUAL_THEME",
    "TEXTUAL_FILTERS",
    "TEXTUAL_COLOR_SYSTEM",
    "TEXTUAL_ANIMATIONS",
    "TEXTUAL_PRESS",
):
    os.environ.pop(_variable, None)

from graphene.orchestration.mission_replay import (  # noqa: E402
    load_verified_mission_replay,
)
from graphene.ui.sources import ReplaySource  # noqa: E402
from graphene.ui.tui import GrapheneUI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/assets/tui_replay.svg"
SIZE = (140, 34)
KEYS = ("n", "n", "n", "j", "j", "enter")
TITLE = "graphene ui --replay taskmaster"


async def _render() -> str:
    # Both keyword defaults matter: poll intervals are live-only and
    # autoplay_seconds=None installs no timer, so the frame is decided by KEYS
    # alone and not by how long the pilot took to get there.
    app = GrapheneUI(ReplaySource(load_verified_mission_replay()))
    async with app.run_test(size=SIZE) as pilot:
        for key in KEYS:
            await pilot.press(key)
        await pilot.pause()
        svg = app.export_screenshot(title=TITLE)
        await pilot.press("q")
    return svg


def render() -> str:
    return asyncio.run(_render())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the checked-in terminal UI screenshot."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.check:
        if args.output.read_text(encoding="utf-8") != content:
            raise SystemExit(
                "terminal UI screenshot differs: regenerate with "
                f"python scripts/{Path(__file__).name}"
            )
        return 0
    args.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
