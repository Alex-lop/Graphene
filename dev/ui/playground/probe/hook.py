#!/usr/bin/env python3
"""A PreToolUse hook for the live-note probe: on its second call it puts a note from "the person" next to the
tool result, and says nothing otherwise.

    python3 dev/ui/playground/probe/hook.py COUNTER_FILE      as Claude Code calls it (the event is on stdin)
    python3 dev/ui/playground/probe/hook.py --selftest        proves the behaviour with no model

run_probe.sh runs it against one real `claude -p` agent (Haiku, about half a cent). What it found on
15 October 2026: in five runs where the agent made one tool call per message, the first two files got "x"
and the third got "y": the note reached the agent in the mode `graphene run` uses and changed its next call.
In the one run where it batched all three writes into one message the files were x, x, x: a note is read on
the next model request, so it cannot help calls already in flight.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

NOTE = "NOTE FROM THE PERSON, sent while you work: from now on write the letter y into each file, not x."
AT = 2  # the call that carries the note


def step(state: Path) -> str:
    """Count this call; on the AT-th, the hook's output (JSON for Claude Code), else nothing."""
    n = int(state.read_text()) + 1 if state.exists() else 1
    state.write_text(str(n))
    if n != AT:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": NOTE}})


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "count"
        said = [step(state) for _ in range(3)]
    assert said[0] == "" and said[2] == "", "only the second call speaks"
    out = json.loads(said[1])["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and "write the letter y" in out["additionalContext"]
    print("hook: silent on calls 1 and 3, a note from the person on call 2")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        json.load(sys.stdin)  # the event; this probe does not need what is in it
        text = step(Path(sys.argv[1]))
        if text:
            print(text)
