#!/usr/bin/env python3
"""A person's attention in one run, modelled, and the proposals they changed before any code ran.

    docs/test/attention.py <run-dir> [--arm prompt|tree]

<run-dir> holds runlog.jsonl and repo/.graphene/graphene.db, as newrun.sh makes it; the arm is read
off its name (<task>-<style>-<arm>-<rep>) unless given. Added for the 23 September test, whose
question is attention rather than characters. Nothing here is estimated or asked of a model.

**Typed characters** are what the person wrote, not the commands that carried it:

  prompt, correction, shape, handwork   the whole text: a message, or test 2's logged command
  edit with --edit (a text edit, E)     the characters the saved text added (logline.py counts them)
  edit, reopen, widen, sibling          the values the command carried: --title, --goal, --scope,
                                        --check, --needs, --owner, --note, --why, and any path after
                                        the node id. `graphene node set n2` is a key in graphene watch
  accept, drop, run, review, read       nothing: a key (y, d, R), or reading

The key that makes an act is not counted as a keystroke, in either arm (sending a message is a
key too); M below is the whole cost of an act.

**Acts** are every person entry except `read`: each message, accept, drop, edit, widen, sibling,
run, reopen, handwork and review.

**Person-seconds are MODELLED**, with the keystroke-level model (Card, Moran & Newell 1980):
K = 0.28 s a typed character (an average typist), M = 1.35 s of mental preparation an act, and
reading at 250 words a minute over every word logged as `read` (what the person was shown: the
proposal, the agent's replies, diffs, hand-backs). It is a model of an expert with no errors and
no thinking beyond M. The raw counts are printed beside it and are the numbers that were measured.
`to_run` is the same model up to and including the act that set the work going: the first `run`
in the tree arm, the first `prompt` in the prompt arm, and in a tree-arm run whose session did the
work instead of proposing a tree (no `run` at all), its first `prompt`, with a note saying so.

**Caught before code** (tree arm): every node an agent proposed that the person dropped or edited
before the first `started` in the plan log, each with its contract as proposed (every edit rolled
back) and what the person did to it, for a judge to read against the card. An `undone` after it is
listed too: a drop the person took back is not a catch.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sqlite3
import sys
from pathlib import Path

K, M, WPM = 0.28, 1.35, 250
WHOLE = ("prompt", "correction", "shape", "handwork")
KEYS = ("accept", "drop", "run", "review", "read")
VALUES = ("--title", "--goal", "--scope", "--check", "--needs", "--owner", "--note", "--why")
AGENT = re.compile(r"^(claude|codex|run):|^an agent$")


def typed(entry: dict, notes: list[str]) -> int:
    kind, text = entry.get("type"), str(entry.get("text") or "")
    if isinstance(entry.get("typed"), int):
        return entry["typed"]
    if kind in WHOLE:
        return len(text)
    if kind in KEYS:
        return 0
    try:
        argv = shlex.split(text)
    except ValueError:
        argv = []
    if "graphene" not in argv:
        notes.append(f"a `{kind}` that is not a graphene command was counted whole: {text[:60]!r}")
        return len(text)
    words, count, seen = argv[argv.index("graphene") + 3 :], 0, 0  # after `graphene node set`
    i = 0
    while i < len(words):
        flag, eq, value = words[i].partition("=")
        if flag in VALUES:
            count += len(value) if eq else len(words[i + 1]) if i + 1 < len(words) else 0
            i += 0 if eq else 1
        elif not flag.startswith("-"):
            seen += 1
            count += len(words[i]) if seen > 1 else 0  # the first is the node id: chosen, not typed
        i += 1
    return count


def model(entries: list[dict], notes: list[str]) -> dict:
    acts = [e for e in entries if e.get("type") != "read"]
    chars = sum(typed(e, notes) for e in acts)
    words = sum(len(str(e.get("text") or "").split()) for e in entries if e.get("type") == "read")
    return {
        "typed_chars": chars,
        "acts": len(acts),
        "read_words": words,
        "modelled_seconds": round(K * chars + M * len(acts) + words * 60 / WPM, 1),
    }


def caught(db: Path) -> list[dict]:
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT id, node_id, kind, actor, detail FROM node_log ORDER BY id").fetchall()
    data = {i: json.loads(d) for i, d in conn.execute("SELECT id, data FROM nodes")}
    conn.close()
    start = next((r[0] for r in rows if r[2] == "started"), float("inf"))
    proposed = {r[1] for r in rows if r[2] == "proposed"}
    out: dict[str, dict] = {}
    for rid, node, kind, actor, detail in rows:
        person = actor and not AGENT.match(actor)
        if rid < start and node in proposed and person and kind in ("dropped", "edited"):
            act = {"kind": kind}
            if kind == "edited":
                act["changed"] = json.loads(detail or "{}").get("changed")
            out.setdefault(node, {"node": node, "acts": []})["acts"].append(act)
        elif node in out and kind == "undone":
            out[node]["acts"].append({"kind": "undone"})
    for node, item in out.items():
        was = dict(data.get(node, {}))
        edits = [json.loads(r[4] or "{}") for r in rows if r[1] == node and r[2] == "edited"]
        for detail in reversed(edits):
            for field, (before, _after) in (detail.get("changed") or {}).items():
                was[field] = before
        item["as_proposed"] = {f: was.get(f) for f in ("title", "goal", "scope", "check", "needs", "parent")}
    return list(out.values())


def attention(run: Path, arm: str) -> dict:
    notes: list[str] = []
    entries = []
    for line in (run / "runlog.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    person = [e for e in entries if e.get("who") == "person"]
    cut = None
    for starter in ("prompt",) if arm == "prompt" else ("run", "prompt"):
        cut = next((i for i, e in enumerate(person) if e.get("type") == starter), None)
        if cut is not None:
            break
        notes.append(f"no `{starter}` in the run log: to_run is cut at the next thing that set work going")
    found = caught(run / "repo" / ".graphene" / "graphene.db") if arm != "prompt" else []
    return {
        "arm": arm,
        "model": "keystroke-level model, MODELLED not measured: K=0.28 s/char, M=1.35 s/act, 250 wpm",
        **model(person, notes),
        "to_run": model(person if cut is None else person[: cut + 1], []),
        "caught_before_code": found,
        "caught_before_code_n": len(found),
        "notes": notes,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run")
    ap.add_argument("--arm", choices=("prompt", "tree", "graphene"))
    args = ap.parse_args(argv[1:])
    run = Path(args.run).expanduser().resolve()
    arm = args.arm or run.name.split("-")[-2]
    print(json.dumps(attention(run, arm), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
