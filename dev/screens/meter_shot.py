#!/usr/bin/env python3
"""`graphene watch`, headless, at 80 and at 120 columns: a text file and an SVG of each.

    dev/screens/meter_shot.py REPO OUT_PREFIX [VIEW]

The screen as the person sees it at that moment, drawn by Textual's pilot the way tests/test_tui.py
drives it, in VIEW when one is named (`graphene watch --view time`). Run it with the graphene under
test (a wheel installed as a tool) and from the person's shell, with no agent's mark, so the `you`
clock is theirs."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from graphene_map.store import Store
from graphene_map.tui import Watch

SIZES = {"80": (80, 24), "120": (120, 36)}


def shoot(repo: Path, out: Path, view: str | None = None) -> None:
    for name, size in SIZES.items():
        app = Watch(repo, lambda: Store.open(repo), every=60, view=view)

        async def go(app=app, name=name, size=size):
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.refresh_plan()
                await pilot.pause()
                rows = app.screen._compositor.render_strips()
                Path(f"{out}-{name}.txt").write_text("\n".join(r.text.rstrip() for r in rows) + "\n")
                app.save_screenshot(filename=f"{out.name}-{name}.svg", path=str(out.parent))

        asyncio.run(go())


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit("usage: meter_shot.py REPO OUT_PREFIX [VIEW]")
    shoot(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), *sys.argv[3:])
