#!/usr/bin/env python3
"""The editor's moves against the cockpit's: every key in `graphene watch`'s `?` help (cockpit/help.py's
GROUPS, read, not copied) against what the extension offers (its package.json commands, and the graph page's
acts), as a table and two counts. The mapping is the table below: a key is covered when the extension does
the same thing from the editor, partly when it does part of it.

    uv run python editors/vscode/e2e/measure/moves.py [editors/vscode/package.json]
"""

import json
import sys
from pathlib import Path

from graphene_map.cockpit.help import GROUPS

# cockpit key -> (what the extension offers, or "", and whether that covers it: "yes", "part", "no")
COVER = {
    "⏎ y": ("graphene.accept (a proposal; no sign-off, no try again)", "part"),
    "1-9 a": ("", "no"),
    "d A": ("graphene.dropStep, graphene.acceptAll", "yes"),
    "t": ("graphene.tell", "yes"),
    "w": ("", "no"),
    "x": ("", "no"),
    "b n r": ("", "no"),
    "r R s": ("graphene.runReady (every ready one; not this one, no split)", "part"),
    "f": ("", "no"),
    "e E": ("graphene.editStep (four boxes; not the whole plan)", "part"),
    "P u D": ("", "no"),
    "+ L": ("graphene.addStep, graphene.link (the graph's dot, dragged)", "yes"),
    "j k": ("the Plan tree, the graph's boxes (click)", "yes"),
    "i": ("the graph's details pane (contract; no output, no diff)", "part"),
    "c g m": ("graphene.openCockpit (a terminal), graphene.showGraph; no map", "part"),
    "v p": ("", "no"),
    "`:` q": ("graphene.auto, graphene.envelope, graphene.stop, graphene.init, each its own command", "part"),
}


def main(manifest: Path) -> None:
    commands = sorted(c["command"] for c in json.loads(manifest.read_text())["contributes"]["commands"])
    rows, counts = [], {"yes": 0, "part": 0, "no": 0}
    for group, keys in GROUPS:
        if group == "marks":
            continue
        for key, what in keys:
            offers, cover = COVER.get(key, ("", "no"))
            counts[cover] += 1
            rows.append(f"| {group} | `{key}` | {what} | {offers or '—'} | {cover} |")
    print("| group | cockpit key | what it does | the editor offers | covered |")
    print("|---|---|---|---|---|")
    print("\n".join(rows))
    total = sum(counts.values())
    print()
    print(f"cockpit moves: {total}. The editor covers {counts['yes']} whole and {counts['part']} in part; "
          f"{counts['no']} not at all.")
    print(f"extension commands ({len(commands)}): {', '.join(c.removeprefix('graphene.') for c in commands)}")


if __name__ == "__main__":
    here = Path(__file__).resolve()
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else here.parents[2] / "package.json")
