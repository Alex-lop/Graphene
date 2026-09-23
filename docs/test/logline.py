#!/usr/bin/env python3
"""Append one line to a run log, with the character count taken rather than typed.

    docs/test/logline.py <runlog.jsonl> <person|executor> <type> [text] [--mandated]
    docs/test/logline.py <runlog.jsonl> executor result --from-json <claude-output.json>
    docs/test/logline.py <runlog.jsonl> person edit --edit <before.txt> <after.txt>

`type` is one of prompt, correction, shape, accept, run, review, handwork, result, and (added 23
September, for the tree arm) drop, edit, widen, sibling, reopen, and read. `read` is not an act:
its text is what the person was shown, and only its words are counted. `--mandated` marks a
correction the card itself forces on both arms, so restarts can be reported both with it and
without. `--from-json` reads a `claude -p --output-format json` result and takes its cost, turns
and session id, so nobody transcribes a number.

`--edit` is a text edit of the plan (`E` in `graphene watch`): the logged text is the diff, and
`typed` is the characters the after-text has that the before-text did not (a character-level diff),
so a person is counted for what they wrote, not for the lines their editor rewrapped.

With no text and no --from-json, the text is read from standard input, which is how a paragraph
with quotes and newlines in it gets recorded as it was actually typed.
"""

from __future__ import annotations

import difflib
import json
import sys
import time
from pathlib import Path

TYPES = (
    "prompt", "correction", "shape", "accept", "run", "review", "handwork", "result",
    "drop", "edit", "widen", "sibling", "reopen", "read",
)  # fmt: skip


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        sys.stderr.write(__doc__)
        return 2
    runlog, who, kind, rest = Path(argv[1]), argv[2], argv[3], argv[4:]
    if who not in ("person", "executor") or kind not in TYPES:
        sys.stderr.write(f"who is person or executor; type is one of {', '.join(TYPES)}\n")
        return 2
    entry: dict = {"t": time.time(), "who": who, "type": kind}
    if "--mandated" in rest:
        entry["mandated"] = True
        rest = [a for a in rest if a != "--mandated"]
    if rest[:1] == ["--from-json"]:
        data = json.loads(Path(rest[1]).read_text(encoding="utf-8"))
        entry.update(
            text=str(data.get("result") or "")[:2000],
            cost_usd=data.get("total_cost_usd", data.get("cost_usd")),
            turns=data.get("num_turns", data.get("turns")),
            session_id=data.get("session_id"),
        )
    elif rest[:1] == ["--edit"]:
        before, after = (Path(f).read_text(encoding="utf-8") for f in rest[1:3])
        ops = difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
        entry["typed"] = sum(j2 - j1 for tag, _, _, j1, j2 in ops if tag in ("insert", "replace"))
        entry["deleted"] = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag in ("delete", "replace"))
        diff = difflib.unified_diff(before.splitlines(), after.splitlines(), "before", "after", lineterm="")
        entry["text"] = "\n".join(diff)
    else:
        text = " ".join(rest) if rest else sys.stdin.read()
        entry["text"] = text
    entry["chars"] = entry.get("typed", len(str(entry.get("text") or "")))
    with runlog.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    print(f"logged {who} {kind} ({entry['chars']} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
