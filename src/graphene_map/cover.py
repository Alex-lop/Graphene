"""`graphene plan cover`: the person's words, accounted for.

Nemotron Nano reads the paragraph the person asked with (the last `asked` row, or --paragraph FILE)
beside the plan's text, and says which node carries each clause of it. Graphene keeps a clause only
when its words, spaces and case aside, are in the paragraph, and keeps them as the paragraph has
them: a clause the model invents is dropped. A clause mapped to no node, or to an id the plan does not
have, is uncovered: one row, and one line offering the command that puts the person's own clause,
verbatim, on the nearest leaf. No text the model wrote is ever offered for a leaf.

Everything lives in the plan's log (node "*"): `covered` for each answer read (the clauses kept, each
with its node, and those dropped), `uncovered` for each clause no node carries, `dismissed` for one
the person set aside (never flagged again), and `usage` for the call's bill. GRAPHENE_SHAPE=cover runs
it after each `graphene ask`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Callable
from pathlib import Path

import typer

from . import plan as P
from . import plan_text as T
from . import tokenfactory as tf

ACTOR = "cover:nemotron"
SYSTEM = """\
You account for a person's words. They wrote a paragraph asking for work, and a planner proposed a
plan: a tree of nodes, each with an [id]. Split the paragraph into clauses: each thing the person asked
for, and each condition or constraint they stated. Copy each clause exactly as the paragraph has it, one
unbroken span of its words: never reworded, never summarised. For each clause give "leaf": the id of the
node whose title, goal, scope or check carries it, or null when none does. When leaf is null, give
"nearest": the id of the leaf it belongs on, or null. Answer with the JSON only."""
_CLAUSE = {"type": "object", "additionalProperties": False, "required": ["text", "leaf", "nearest"],
           "properties": {"text": {"type": "string"}, "leaf": {"type": ["string", "null"]},
                          "nearest": {"type": ["string", "null"]}}}  # fmt: skip
FORMAT = {"type": "json_schema", "json_schema": {"name": "clauses", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["clauses"],
    "properties": {"clauses": {"type": "array", "items": _CLAUSE}}}}}  # fmt: skip


def paragraph_of(store) -> str | None:
    """The last paragraph `graphene ask` was given for the plan (not a question about one node)."""
    asked = [e for e in store.node_log("*", ("asked",)) if not e["detail"].get("about")]
    return asked[-1]["detail"].get("note") if asked else None


def last(store) -> list[dict]:
    """The last cover's uncovered clauses, numbered as it printed them (from 1)."""
    runs = store.node_log("*", ("covered",))
    if not runs:
        return []
    run = runs[-1]["detail"]["run"]
    return [e["detail"] for e in store.node_log("*", ("uncovered",)) if e["detail"].get("run") == run]


def standing(store) -> list[dict]:
    """What the screen shows: the last cover's uncovered clauses the person has not set aside."""
    gone = dismissed(store)
    return [u for u in last(store) if u["note"] not in gone]


def dismissed(store) -> set[str]:
    return {e["detail"]["note"] for e in store.node_log("*", ("dismissed",))}


def _nano() -> str:
    try:
        found = tf.roles()
    except tf.Unreachable as no:
        raise P.Refused(f"Nano could not be asked: {no}") from None
    if "nano" not in found:
        raise P.Refused("Token Factory lists no Nemotron Nano for this key; nothing was asked")
    return found["nano"]


def offer(node: P.Node, clause: str) -> str:
    """The command that puts the person's clause, as they wrote it, at the end of the leaf's goal."""
    goal = f"{node.goal.strip().rstrip('.')}; {clause}" if node.goal.strip() else clause
    return f"graphene node set {node.id} --goal {shlex.quote(goal)}"


def cover(store, paragraph: str | None = None, say: Callable[[str], None] = print) -> list[dict]:
    """Ask Nano, keep what is the person's, record it, say it. Returns the uncovered rows' details."""
    paragraph = paragraph or paragraph_of(store)
    if not (paragraph or "").strip():
        raise P.Refused("no paragraph to account for: `graphene ask` keeps one, or give --paragraph FILE")
    everything = [n for n in P.nodes(store) if n.state not in P.GONE]
    if not everything:
        raise P.Refused("nothing is planned yet: there is no leaf to carry your words")
    model, text = _nano(), T.render(store)[0]
    shown = f"The paragraph:\n{paragraph.strip()}\n\nThe plan:\n{text}"
    ask = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": shown}]
    try:
        said = tf.chat(model, ask, tag="cover", response_format=FORMAT, reasoning_effort="low",
                       temperature=0, max_tokens=4096)  # fmt: skip
    except tf.Unreachable as no:
        raise P.Refused(f"Nano could not be asked: {no}") from None
    usage, whose = said["usage"], tf.endpoint()
    bill = {"model": model, "calls": 1, "prompt_tokens": usage.get("prompt_tokens") or 0,
            "completion_tokens": usage.get("completion_tokens") or 0, "dollars": round(said["dollars"], 6),
            "endpoint": whose}  # fmt: skip
    store.log_node("*", P._now(), "usage", ACTOR, None, None, bill)
    by = "Token Factory" if whose == "token factory" else "a stand-in, not Token Factory"
    say(f"Nano ({model}, answered by {by}): {bill['prompt_tokens']} in, {bill['completion_tokens']} out, "
        f"${bill['dollars']:.4f} at list price")  # fmt: skip
    try:
        clauses = json.loads(said["message"].get("content") or "")["clauses"]
        assert isinstance(clauses, list)
    except (ValueError, KeyError, TypeError, AssertionError):
        say("its answer is not the JSON asked for: nothing is recorded")
        return []
    flat, by_id, gone = " ".join(paragraph.split()), {n.id: n for n in everything}, dismissed(store)
    leaves = {n.id for n in P.leaves(everything) if n.state in (P.PROPOSED, P.OPEN)}
    kept, dropped, uncovered = [], [], []
    for c in clauses:
        c = c if isinstance(c, dict) else {}
        words = " ".join(str(c.get("text") or "").split()).rstrip(".,;:")
        found = re.search(re.escape(words), flat, re.IGNORECASE) if words else None
        if found is None:  # not the person's words: dropped, never offered
            dropped.append(words)
            continue
        clause = found.group(0)  # as the paragraph has it, not as the model wrote it
        if clause in (k["text"] for k in kept):
            continue
        leaf = c.get("leaf") if c.get("leaf") in by_id else None
        kept.append({"text": clause, "leaf": leaf})
        if leaf is None and clause not in gone:
            near = c.get("nearest") if c.get("nearest") in leaves else None
            uncovered.append({"note": clause, "nearest": near})
    run = P._now()
    read = {"run": run, "clauses": kept, "dropped": dropped}
    with store.claim():
        store.log_node("*", run, "covered", ACTOR, None, None, read)
        for u in uncovered:
            u["run"] = run
            store.log_node("*", run, "uncovered", ACTOR, None, None, u)
    carried = sum(k["leaf"] is not None for k in kept)
    aside, bare = len(kept) - carried - len(uncovered), len(uncovered)
    say(f"your paragraph, in clauses: {len(kept)}; the plan carries {carried}, no leaf carries {bare}"
        + (f"; set aside before: {aside}" if aside else "")
        + (f"; dropped, not your words: {len(dropped)}" if dropped else ""))  # fmt: skip
    for k, u in enumerate(uncovered, 1):
        take = f"Take it: `{offer(by_id[u['nearest']], u['note'])}`" if u["nearest"] else (
            "No open leaf is near it: add it in `graphene plan edit`")  # fmt: skip
        say(f"{k}. You said '{u['note']}'; no leaf carries it. {take}")
    if uncovered:
        say("not wanted? `graphene plan cover --dismiss N` sets clause N aside for good")
    return uncovered


def shaping() -> set[str]:
    return {s.strip() for s in os.environ.get("GRAPHENE_SHAPE", "").split(",") if s.strip()}


def after_ask(store, sentence: str, say: Callable[[str], None]) -> None:
    """GRAPHENE_SHAPE=cover: account for the paragraph once the proposal has landed. What goes wrong
    here is one line; the proposal stands."""
    if "cover" in shaping():
        try:
            cover(store, sentence, say)
        except P.Refused as no:
            say(f"cover: {no}")


def command(plan_cli: typer.Typer, run, out) -> None:
    @plan_cli.command("cover")
    def cover_(
        paragraph: Path = typer.Option(None, "--paragraph", exists=True, dir_okay=False,
                                       help="The paragraph, from a file. Default: the last one "
                                       "`graphene ask` was given."),  # fmt: skip
        dismiss: int = typer.Option(None, "--dismiss", help="Set clause N of the last cover aside for good."),
    ) -> None:
        """Nano says which leaf carries each clause of your paragraph; for one no leaf carries, you are
        offered the command that puts your own words, as you wrote them, on the nearest leaf."""
        who = P.caller()

        def go(store):
            if not who.person:
                raise P.Refused("cover is the person's: it asks Nano, and spends")
            if dismiss is None:
                return cover(store, paragraph.read_text(encoding="utf-8") if paragraph else None, out)
            now = last(store)
            if not 1 <= dismiss <= len(now):
                raise P.Refused(f"the last cover found {len(now)} clause(s) no leaf carries: no {dismiss}")
            clause = now[dismiss - 1]["note"]
            store.log_node("*", P._now(), "dismissed", who.label, None, None, {"note": clause})
            out(f"set aside for good: '{clause}'")

        run(go)
