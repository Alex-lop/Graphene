#!/usr/bin/env python3
"""Append one line to a run log, with the character count taken rather than typed.

    docs/test/logline.py <runlog.jsonl> <person|executor> <type> [text] [--mandated]
    docs/test/logline.py <runlog.jsonl> executor result --from-json <claude-output.json>

`type` is one of prompt, correction, shape, accept, run, review, handwork, result. `--mandated`
marks a correction the card itself forces on both arms, so restarts can be reported both with it
and without. `--from-json` reads a `claude -p --output-format json` result and takes its cost,
turns and session id, so nobody transcribes a number.

With no text and no --from-json, the text is read from standard input, which is how a paragraph
with quotes and newlines in it gets recorded as it was actually typed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

TYPES = ("prompt", "correction", "shape", "accept", "run", "review", "handwork", "result")


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
    else:
        text = " ".join(rest) if rest else sys.stdin.read()
        entry["text"] = text
    entry["chars"] = len(str(entry.get("text") or ""))
    with runlog.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    print(f"logged {who} {kind} ({entry['chars']} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
