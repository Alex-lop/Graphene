#!/usr/bin/env python3
"""The editor's moves against the cockpit's: every key in `graphene watch`'s `?` help (cockpit/help.py's
GROUPS, read, not copied) against what the extension offers (its package.json commands, and the graph page's
acts), as a table and two counts. The mapping is a table below, one a build: a key is covered when the
extension does the same thing from the editor, partly when it does part of it. The manifest's version picks
the table (0.8.0's for the before, the night's for what came after), and every `graphene.<command>` a table
names must be in the manifest, else the table is another build's and the script says so.

    uv run python editors/vscode/e2e/measure/moves.py [editors/vscode/package.json]
"""

import json
import re
import sys
from pathlib import Path

from graphene_map.cockpit.help import GROUPS

# cockpit key -> (what the extension offers, or "", and whether that covers it: "yes", "part", "no")
COVER = {  # 0.9.0: the editor night's build
    "⏎ y": ("Needs You: each item's own move (a question's default, graphene.accept, graphene.signOff, a hand-back's offers)", "yes"),
    "1-9 a": ("graphene.answer (its options, its default, your own words); graphene.pickFork from a fork's diff (graphene.compareForks)", "yes"),
    "d A": ("graphene.dropStep (a came-back task too), graphene.acceptAll", "yes"),
    "t": ("graphene.tell", "yes"),
    "w": ("Needs You's widen, for a running task the gate stopped and for one that came back", "yes"),
    "x": ("", "no"),
    "b n r": ("graphene.handBack (the task's own offers: a sibling, wait on, reopen)", "yes"),
    "r R s": ("graphene.runReady (every ready one); a hand-back's try again; no split", "part"),
    "f": ("Set Envelope's forks, for every task; not one task", "part"),
    "e E": ("graphene.editStep, graphene.editPlan (the plan as a text tab, refusals on their lines)", "yes"),
    "P u D": ("", "no"),
    "+ L": ("graphene.addStep (a sentence), graphene.link (the graph's dot, dragged)", "yes"),
    "j k": ("the Plan tree, Needs You, Agents, the graph's boxes (keys and clicks)", "yes"),
    "i": ("the graph's pane (contract), graphene.openDiff (its changes); no output, no record", "part"),
    "c g m": ("graphene.openCockpit (a terminal), graphene.showGraph; no map", "part"),
    "v p": ("", "no"),
    "`:` q": ("graphene.auto, envelope, stop, init, addStep and the rest, each its own command", "part"),
}
COVER_080 = {  # 0.8.0: the before (dev/process/editor/before/moves.md)
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
TABLES = {"0.9.0": COVER, "0.8.0": COVER_080}  # the newest at or under the manifest's version is its table


def table_for(version: str) -> dict:
    parts = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
    fits = [v for v in TABLES if parts(v) <= parts(version)]
    return TABLES[max(fits, key=parts)] if fits else COVER_080


def main(manifest: Path) -> int:
    pkg = json.loads(manifest.read_text())
    commands = sorted(c["command"].removeprefix("graphene.") for c in pkg["contributes"]["commands"])
    cover = table_for(pkg["version"])
    named = set(re.findall(r"graphene\.(\w+)", " ".join(offers for offers, _ in cover.values())))
    if missing := sorted(named - set(commands)):
        print(f"the table for {pkg['version']} names commands the manifest lacks: {', '.join(missing)}", file=sys.stderr)
        return 1
    rows, counts = [], {"yes": 0, "part": 0, "no": 0}
    for group, keys in GROUPS:
        if group == "marks":
            continue
        for key, what in keys:
            offers, how = cover.get(key, ("", "no"))
            counts[how] += 1
            rows.append(f"| {group} | `{key}` | {what} | {offers or '—'} | {how} |")
    print("| group | cockpit key | what it does | the editor offers | covered |")
    print("|---|---|---|---|---|")
    print("\n".join(rows))
    total = sum(counts.values())
    print()
    print(f"cockpit moves: {total}. The editor ({pkg['version']}) covers {counts['yes']} whole and "
          f"{counts['part']} in part; {counts['no']} not at all.")
    print(f"extension commands ({len(commands)}): {', '.join(commands)}")
    if rest := sorted(set(commands) - named):
        print(f"not named in the table ({len(rest)}; the `:` row's rest, or no move of the cockpit's): {', '.join(rest)}")
    return 0


if __name__ == "__main__":
    here = Path(__file__).resolve()
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else here.parents[2] / "package.json"))
