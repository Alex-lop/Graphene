"""`graphene plan note "<sentence>"`: a loose sentence the person types finds the one leaf it
constrains, and comes back as the command that would change that leaf.

One Nano call reads the note beside every open or proposed leaf's contract and answers in a JSON
schema: which leaf (or "(new)", or "(none)"), the globs to add to or take out of its scope, a check, and
whether the note belongs in its goal. Graphene checks the answer before anything is shown: the leaf
is open or proposed, an added glob matches a tracked file or falls under the leaf's scope, a removed
glob is in it, a check names nothing no leaf may create, and the change, made and rolled back, is
one the plan takes. Only then is it offered, as the `graphene node set` (or `node add`) that makes
it, and logged as a `suggested` row. Nothing changes until the person runs that command, so `plan
undo` and `plan edit` see an ordinary edit. What a note adds to a goal is the person's own sentence,
never the model's.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from . import plan as P
from . import tokenfactory as tf

MAX_TOKENS = 2048  # Nano reasons before it answers: a cut-off answer is said to be one
TIMEOUT = 30  # seconds: a note is asked once, with no backoff, and a failure is one line (not verified live)
NEW, NONE = "(new)", "(none)"  # the answers that are no leaf: no leaf's id has brackets
WHO = "note:nemotron"  # the actor of its rows; each usage row's `endpoint` says who answered
SYSTEM = """\
A person typed a note about their plan. The plan's leaves still to be done follow, each with its
contract. Say which one leaf the note constrains: its id; "(new)" when it asks for work no leaf
covers; "(none)" when it constrains no leaf. Then only what the note asks of that leaf: scope_add,
the globs to add to its scope (for "(new)", its whole scope); scope_remove, globs to take out, as its
scope writes them; check, a new check command when the note changes how done is shown, else null;
goal_add, true when the note itself belongs in the leaf's goal. why: one sentence."""
_LIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {"name": "note", "strict": True, "schema": {
    "type": "object", "additionalProperties": False,
    "required": ["target", "scope_add", "scope_remove", "check", "goal_add", "why"],
    "properties": {"target": {"type": "string"}, "scope_add": _LIST, "scope_remove": _LIST,
                   "check": {"type": ["string", "null"]}, "goal_add": {"type": "boolean"},
                   "why": {"type": "string"}}}}  # fmt: skip


@dataclass(frozen=True)
class Offer:
    target: str  # a leaf's id, or NEW
    command: str  # what the person types to take it
    why: str  # the model's reason, one sentence
    endpoint: str  # who answered, as the usage row says it: "token factory" or "a stand-in"


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")  # ESC, CR, BEL...: what could redraw a terminal line


def _unkeyed(text: str) -> str:
    from .demo import unkeyed  # here, not above: demo loads the screen's library

    return unkeyed(text)


def _shown(text) -> str:
    """Text as it may reach a terminal or the store: one line, no control character, no key."""
    return _unkeyed(" ".join(_CONTROL.sub(" ", str(text)).split()))


class _Tried(Exception):
    """Raised inside the dry run, so its claim rolls back."""


def _strs(v) -> list[str]:
    if v is not None and not isinstance(v, list):
        raise ValueError(f"a list of globs, not {type(v).__name__}")
    return [s.strip() for s in v or [] if isinstance(s, str) and s.strip()]


def route(store, root: Path, sentence: str, say: Callable[[str], None] = lambda s: None) -> Offer | None:
    """Place a note: the checked offer, or None (``say`` hears why). Call it outside a claim: the
    model is asked with no lock held, and the dry run rolls back only its own transaction."""
    assert not store.conn.in_transaction, "note.route is called outside the plan's write lock"
    if _shown(sentence) != " ".join(_CONTROL.sub(" ", sentence).split()):
        raise P.Refused("the note holds something shaped like a key; it is not sent to a model")
    sentence, hear = _shown(sentence), say
    say = lambda line: hear(_shown(line))  # noqa: E731  (every line said is shown text, model words or not)
    if not sentence:
        raise P.Refused("a note is a sentence: graphene plan note '<what you want kept in mind>'")
    files, everything = P.tracked(root), P.nodes(store)  # git first, never under the lock
    leaves = [n for n in P.leaves(everything) if n.state in (P.OPEN, P.PROPOSED)]
    try:
        chosen, _ = tf.resolve([], "note")  # the smallest Nemotron listed: Nano
        if not chosen:
            raise tf.Unreachable("Token Factory lists no Nemotron model for this key")
        said = tf.chat(chosen[0], [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"The note: {sentence}\n\nThe leaves:\n\n"
             + ("\n\n".join(P.contract(n) for n in leaves) or "(none yet)")},
        ], tag="note", tries=1, timeout=TIMEOUT, temperature=0, max_tokens=MAX_TOKENS,
            response_format={"type": "json_schema", "json_schema": SCHEMA})  # fmt: skip
    except tf.Unreachable as no:
        raise P.Refused(f"the note was not placed: {no}") from None
    usage, endpoint = said["usage"], tf.endpoint()
    store.log_node("*", P._now(), "usage", WHO, None, None, {
        "model": chosen[0], "calls": 1, "prompt_tokens": usage.get("prompt_tokens") or 0,
        "completion_tokens": usage.get("completion_tokens") or 0, "dollars": round(said["dollars"], 6),
        "endpoint": endpoint})  # fmt: skip
    if said.get("finish") == "length":  # one try: a longer cap is the next run's to set, not a retry's
        say(f"the model's answer was cut off at {MAX_TOKENS} tokens; nothing is offered")
        return None
    try:
        a = json.loads(said["message"].get("content") or "")
        target, why = str(a["target"]).strip(), _shown(a.get("why") or "")
    except (ValueError, KeyError, TypeError, AttributeError):
        say("the model's answer is not the JSON it was asked for; nothing is offered")
        return None
    try:  # whatever the model wrote, the command ends in one line, never a traceback
        return _offer(store, root, sentence, a, target, why, leaves, files, everything, endpoint, say)
    except Exception as no:  # noqa: BLE001  (the answer is untrusted; a bug here must not crash the command)
        say(f"the model's answer could not be read ({type(no).__name__}: {no}); nothing is offered")
        return None


def _offer(store, root, sentence, a, target, why, leaves, files, everything, endpoint, say) -> Offer | None:
    if target == NONE:
        say(f"it constrains no leaf: {why}" if why else "it constrains no leaf; nothing is offered")
        return None
    node = next((n for n in leaves if n.id == target), None)
    if target != NEW and node is None:
        say(f"the model named {target!r}, which is not an open or proposed leaf; nothing is offered")
        return None
    scope, add, remove = node.scope if node else [], _strs(a.get("scope_add")), _strs(a.get("scope_remove"))
    check = a["check"].strip() if isinstance(a.get("check"), str) else ""
    if any(_CONTROL.search(w) for w in (*add, *remove, check)):  # a command must be what it looks like
        say("the model's answer holds control characters; nothing is offered")
        return None
    if any(_unkeyed(w) != w for w in (*add, *remove, check)):
        say("the model's answer holds something shaped like a key; nothing is offered")
        return None
    for g in add:
        bare = g.lstrip("!")
        if not any(P.in_scope(f, [bare]) for f in files) and not P.in_scope(bare.rstrip("/*") or bare, scope):
            say(f"{g} matches no file git tracks and is not under {target}'s scope; nothing is offered")
            return None
    for g in remove:
        if g not in scope:
            say(f"{g} is not in {target}'s scope; nothing is offered")
            return None
    fresh = [g for g in scope if g not in remove] + [g for g in add if g not in scope]
    if node is None:
        if not (fresh and check):  # else `node add` makes a heading with no work under it
            say("a new leaf needs a scope and a check, and the model did not give both; nothing is offered")
            return None
        changes = {"title": sentence, "scope": fresh, "check": check}
    else:
        changes = {**({"scope": fresh} if fresh != scope else {}),
                   **({"check": check} if check and check != node.check else {})}  # fmt: skip
        base = node.goal or node.title
        if a.get("goal_add") is True and sentence not in base:
            changes["goal"] = f"{base}; {sentence}"  # the person's words, as typed
        if not changes:
            say(f"it names {target} but asks no change of it; nothing is offered")
            return None
    if "check" in changes:
        tried = dataclasses.replace(node, **changes) if node else P.from_dict(changes, "new")
        missing = P.unreachable(tried, files, root, everything)
        if missing:
            say(f"the check it drafted {P.unreachable_said(missing)}; nothing is offered")
            return None
    person = P.Caller(P.person_name(), True)
    try:  # made and rolled back: what the command would meet, it meets here first
        with store.claim():
            now = P.get(store, target) if node else None
            if now and now.rev != node.rev:  # offered from what the model read, it would undo the edit
                say(f"{target} changed while the model was asked (revision {node.rev}, now {now.rev}); "
                    "nothing is offered: place the note again")  # fmt: skip
                return None
            if node is None:
                P.propose(store, [changes], person, files=files)
            else:
                P.edit(store, target, changes, person, files=files)
            raise _Tried
    except _Tried:
        pass
    except P.Refused as no:
        say(f"the plan would refuse it ({no}); nothing is offered")
        return None
    words = ["node", "add"] if node is None else ["node", "set", target]
    words += [w for g in changes.get("scope", []) for w in ("--scope", g)]
    words += [w for key in ("check", "goal") if key in changes for w in (f"--{key}", changes[key])]
    words += ["--", sentence] if node is None else []  # the title last, after --: a note may start with -
    command = shlex.join(["graphene", *words])
    store.log_node(node.id if node else "*", P._now(), "suggested", WHO, None, None, {
        "note": sentence, "command": command, "reason": why, "rev": node.rev if node else None,
        "endpoint": endpoint})  # fmt: skip
    return Offer(target, command, why, endpoint)


def register(plan_cli: typer.Typer, root, open_store, fail) -> None:
    @plan_cli.command("note")
    def note_(sentence: str = typer.Argument(..., help="What to keep in mind, in your words.")) -> None:
        """Place a note: a model finds the leaf it constrains and prints the command that would change
        that leaf. Nothing changes until you run it."""
        try:
            P._person_only(P.caller(), "placing a note (a model call)")
            with open_store(root()) as store:
                offer = route(store, root(), sentence, say=typer.echo)
        except P.Refused as no:
            fail(str(no), 1)
        if offer is None:
            raise typer.Exit(1)
        live = offer.endpoint == "token factory"  # never said of a stand-in's answer
        who = "Nemotron on Token Factory" if live else "a stand-in, not Token Factory,"
        where = "finds no leaf for it: a new one" if offer.target == NEW else f"places it on {offer.target}"
        typer.echo(f"{who} {where}: {offer.why}" if offer.why else f"{who} {where}")
        typer.echo(f"take it:  {offer.command}")
