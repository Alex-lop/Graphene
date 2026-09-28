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
from collections.abc import Callable
from pathlib import Path

import typer

from . import plan as P
from . import plan_text as T
from . import tokenfactory as tf

ACTOR = "cover:nemotron"
BRIEF = 30  # seconds Nano is given, asked once: it runs after the proposal has landed, and nobody waits on it
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


# what a terminal acts on rather than shows: C0 and C1 controls, and the marks that turn text around
CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


# where one clause of a paragraph ends and the next begins: a stop or a mark, or a word that joins two
EDGE = set(".,;:!?()[]\"'—–-")
JOIN = {"and", "but", "or", "nor", "so", "then", "yet", "while", "because", "unless", "if", "when", "also"}


def whole(flat: str, words: str, taken: list[range]) -> re.Match | None:
    """Where ``words`` stand in the paragraph as a whole clause (case aside): starting and ending at a
    clause's edge, not a piece of one ("multiply them" out of "do not multiply them"), and not over a
    clause already kept."""
    for found in re.finditer(re.escape(words), flat, re.IGNORECASE):
        before, after = flat[: found.start()].rstrip(), flat[found.end() :].lstrip()
        starts = not before or before[-1] in EDGE or (
            found.start() > len(before) and before.split()[-1].lower() in JOIN
        )  # fmt: skip
        ends = not after or after[0] in EDGE or (found.end() < len(flat) - len(after) and
                                                 after.split()[0].lower() in JOIN)  # fmt: skip
        if starts and ends and not any(found.start() < t.stop and t.start < found.end() for t in taken):
            return found
    return None


def plain(say: Callable[[str], None]) -> Callable[[str], None]:
    """``say``, with nothing in a line that a terminal would act on, and nothing shaped like a key."""
    return lambda line: say(tf.unkeyed(CONTROL.sub("", line)))


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
    """What the screen shows: the last cover's uncovered clauses the person has not set aside, each with
    ``n``, the number `--take N` and `--dismiss N` know it by (it does not move when one is set aside)."""
    gone = dismissed(store)
    return [{**u, "n": n} for n, u in enumerate(last(store), 1) if u["note"] not in gone]


def dismissed(store) -> set[str]:
    return {e["detail"]["note"] for e in store.node_log("*", ("dismissed",))}


def _nano() -> str:
    try:
        found = tf.roles(tf.models(tries=1))
    except tf.Unreachable as no:
        raise P.Refused(f"Nano could not be asked: {no}") from None
    if "nano" not in found:
        raise P.Refused("Token Factory lists no Nemotron Nano for this key; nothing was asked")
    return found["nano"]


def take(store, u: dict, who: P.Caller) -> str:
    """Put an uncovered clause, as the person wrote it, at the end of its nearest leaf's goal as that
    goal is now (read at this moment, so an edit made since the cover ran stays). Says what changed."""
    if not u.get("nearest"):
        raise P.Refused(f"no open leaf is near '{u['note']}': add it in `graphene plan edit`")
    node = P.get(store, u["nearest"])
    if u["note"].lower() in node.goal.lower():
        raise P.Refused(f"{node.id}'s goal carries it already: {node.goal}")
    goal = f"{node.goal.strip().rstrip('.')}; {u['note']}" if node.goal.strip() else u["note"]
    was = node.goal
    node = P.edit(store, node.id, {"goal": goal}, who)
    return f"{node.id} is now revision {node.rev}; goal: {was} → {node.goal}"


def cover(store, paragraph: str | None = None, say: Callable[[str], None] = print) -> list[dict]:
    """Ask Nano, keep what is the person's, record it, say it. Returns the uncovered rows' details."""
    paragraph, say = tf.unkeyed(paragraph or paragraph_of(store) or ""), plain(say)
    if not (paragraph or "").strip():
        raise P.Refused("no paragraph to account for: `graphene ask` keeps one, or give --paragraph FILE")
    everything = [n for n in P.nodes(store) if n.state not in P.GONE]
    if not everything:
        raise P.Refused("nothing is planned yet: there is no leaf to carry your words")
    model, text = _nano(), T.render(store)[0]
    shown = f"The paragraph:\n{paragraph.strip()}\n\nThe plan:\n{text}"
    ask = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": shown}]
    try:
        said = tf.chat(model, ask, tag="cover", tries=1, timeout=BRIEF, response_format=FORMAT,
                       reasoning_effort="low", temperature=0, max_tokens=4096)  # fmt: skip
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
    flat = tf.unkeyed(CONTROL.sub("", " ".join(paragraph.split())))
    by_id, gone = {n.id: n for n in everything}, dismissed(store)
    leaves = {n.id for n in P.leaves(everything) if n.state in (P.PROPOSED, P.OPEN)}
    kept, dropped, uncovered, odd, pieces, taken = [], [], [], 0, 0, []
    for c in clauses:
        try:  # an item of any other shape is passed over: nothing the model writes breaks the command
            text, leaf, near = c["text"], c.get("leaf"), c.get("nearest")
            words = tf.unkeyed(CONTROL.sub("", " ".join(text.split()))).rstrip(".,;:")
            if not words or not all(v is None or isinstance(v, str) for v in (leaf, near)):
                raise TypeError
        except (TypeError, KeyError, IndexError, AttributeError):
            odd += 1
            continue
        if not re.search(re.escape(words), flat, re.IGNORECASE):  # not the person's words: never offered
            dropped.append(words)
            continue
        head, _, rest = words.partition(" ")
        words = rest if head.lower() in JOIN and rest else words  # "and keep its order": the clause is after
        if any(k["text"].lower() == words.lower() for k in kept):
            continue
        found = whole(flat, words, taken)
        if found is None:  # theirs, but a piece of a clause (or of one kept): its sense may be lost
            pieces += 1
            continue
        clause = found.group(0)  # as the paragraph has it, not as the model wrote it
        taken.append(range(found.start(), found.end()))
        leaf = leaf if leaf in by_id else None
        kept.append({"text": clause, "leaf": leaf})
        if leaf is None and clause not in gone:
            near = near if near in leaves else None
            uncovered.append({"note": clause, "nearest": near})
    run = P._now()
    # what the model made up is counted whole, and a little of it kept to read: never a large row
    read = {"run": run, "clauses": kept, "dropped": [d[:200] for d in dropped[:20]], "invented": len(dropped),
            "pieces": pieces}  # fmt: skip
    with store.claim():
        store.log_node("*", run, "covered", ACTOR, None, None, read)
        for u in uncovered:
            u["run"] = run
            store.log_node("*", run, "uncovered", ACTOR, None, None, u)
    carried = sum(k["leaf"] is not None for k in kept)
    aside, bare = len(kept) - carried - len(uncovered), len(uncovered)
    say(f"your paragraph, in clauses: {len(kept)}; the plan carries {carried}, no leaf carries {bare}"
        + (f"; set aside before: {aside}" if aside else "")
        + (f"; dropped, not your words: {len(dropped)}" if dropped else "")
        + (f"; dropped, a piece of a clause: {pieces}" if pieces else ""))  # fmt: skip
    for k, u in enumerate(uncovered, 1):
        near = u["nearest"]
        then = f"Take it: `graphene plan cover --take {k}` puts it at the end of {near}'s goal" if near else (
            "No open leaf is near it: add it in `graphene plan edit`")  # fmt: skip
        say(f"{k}. You said '{u['note']}'; no leaf carries it. {then}")
    if uncovered:
        say("not wanted? `graphene plan cover --dismiss N` sets clause N aside for good")
    if odd:
        say(f"cover: items of its answer that are not a clause, passed over: {odd}")
    return uncovered


def shaping() -> set[str]:
    return {s.strip() for s in os.environ.get("GRAPHENE_SHAPE", "").split(",") if s.strip()}


def after_ask(store, sentence: str, say: Callable[[str], None]) -> None:
    """GRAPHENE_SHAPE=cover: account for the paragraph once the proposal has landed. What goes wrong
    here is one line; the proposal stands."""
    if "cover" in shaping():
        say = plain(say)
        try:
            cover(store, sentence, say)
        except P.Refused as no:
            say(f"cover: {no}")
        except Exception as no:  # a helper that runs after the proposal landed never takes the ask down
            say(f"cover: it broke ({type(no).__name__}: {no}); the proposal stands")


def command(plan_cli: typer.Typer, run, out) -> None:
    @plan_cli.command("cover")
    def cover_(
        paragraph: Path = typer.Option(None, "--paragraph", exists=True, dir_okay=False,
                                       help="The paragraph, from a file. Default: the last one "
                                       "`graphene ask` was given."),  # fmt: skip
        dismiss: int = typer.Option(None, "--dismiss", help="Set clause N of the last cover aside for good."),
        take_: int = typer.Option(None, "--take", help="Put clause N at the end of its nearest leaf's goal."),
    ) -> None:
        """Nano says which leaf carries each clause of your paragraph; for one no leaf carries, you are
        offered the command that puts your own words, as you wrote them, on the nearest leaf."""
        who, say = P.caller(), plain(out)

        def go(store):
            if not who.person:
                raise P.Refused("cover is the person's: it asks Nano, and spends")
            if dismiss is None and take_ is None:
                return cover(store, paragraph.read_text(encoding="utf-8") if paragraph else None, say)
            now, n = last(store), dismiss or take_
            if not 1 <= n <= len(now):
                raise P.Refused(f"the last cover found {len(now)} clause(s) no leaf carries: no {n}")
            if take_ is not None:
                return say(take(store, now[n - 1], who))
            clause = now[dismiss - 1]["note"]
            if clause in dismissed(store):
                raise P.Refused(f"clause {dismiss} is set aside already: '{clause}'")
            store.log_node("*", P._now(), "dismissed", who.label, None, None, {"note": clause})
            say(f"set aside for good: '{clause}'")

        run(go)
