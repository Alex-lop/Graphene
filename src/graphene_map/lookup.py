"""`graphene board lookup`: what the repository answers is settled from it, before it reaches you.

Nemotron Nano reads each open question on the board beside the repository's files (those the board
names first) and says, for each, whether a file already answers it: which choice the repository makes
(the default, or option N), the file, and one line of it, copied. Graphene keeps an answer only when
that line is in that file as copied (spaces aside), the file is one it sent, and the choice is one the
question offers; otherwise the question stays open. Nothing else is checked, and nothing the model
wrote reaches the plan: a kept answer is the question's own default or option.

A kept answer settles the item by the person's command, marked "from the repo: FILE:LINE", and is told
to executors as any answer is; `graphene board unpark ID` (p on the screen) opens it again. Every call
is a `usage` row under ``ACTOR``. GRAPHENE_SHAPE=lookup runs it after each `graphene ask`; unset, it
runs only when the person types it, so turning it off is leaving the word out.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from . import board as B
from . import cover
from . import plan as P

ACTOR = "lookup:nemotron"
FLAG = "lookup"
BRIEF = 30  # seconds Nano is given, asked once: nobody waits on it
CAP = 40_000  # characters of the repository sent, the files the board names first
LEAST = 12  # characters a quoted line must have: shorter ones (`}`, `pass`) prove nothing
SYSTEM = """\
You answer a planner's questions from a repository where the repository answers them. Each question
has a default and may have numbered options. For each question give "choice": "default" or "option N"
when a file shown already makes that choice (the code, a test, a config, a README says it), with
"file": its path as shown and "line": one line of that file, copied exactly, that shows it. When the
files do not settle it (it asks what the person wants, not what the code already does), give null for
all three. Never guess. Answer with the JSON only."""
_ANSWER = {"type": "object", "additionalProperties": False, "required": ["id", "choice", "file", "line"],
           "properties": {"id": {"type": "string"}, "choice": {"type": ["string", "null"]},
                          "file": {"type": ["string", "null"]},
                          "line": {"type": ["string", "null"]}}}  # fmt: skip
FORMAT = {"type": "json_schema", "json_schema": {"name": "answers", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["answers"],
    "properties": {"answers": {"type": "array", "items": _ANSWER}}}}}  # fmt: skip


def questions(store) -> list[dict]:
    """The open questions on the board: what the repository might answer. The rest are the planner's
    own statements (an assumption, a risk, a leave-out) or the person's notes."""
    return [it for it in B.items(store) if it["kind"] == "question" and B.reads(it) == "open"]


def _flat(text: str) -> str:
    return " ".join(text.split())


def files(root: Path, asked: list[dict], tracked: list[str]) -> dict[str, str]:
    """{path: text} of the repository, up to ``CAP`` characters: the files the questions name (by
    path or by file name) first, then the rest, smallest first. Binary files are left out, and
    anything shaped like a key is masked before it is sent."""
    from . import tokenfactory as tf

    said = " ".join(
        " ".join([it["text"], it["default"] or "", *(o["text"] for o in it["options"])]) for it in asked
    )
    named = [f for f in tracked if f in said or Path(f).name in said.split()]
    rest = sorted((f for f in tracked if f not in named), key=lambda f: _size(root / f))
    out: dict[str, str] = {}
    room = CAP
    for f in [*named, *rest]:
        try:
            text = (root / f).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(text) > room:
            continue
        clean = "\n".join(cover.CONTROL.sub("", line) for line in text.splitlines())  # lines kept whole
        out[f], room = tf.unkeyed(clean), room - len(text)
    return out


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 1 << 30


def shown(asked: list[dict], sent: dict[str, str]) -> str:
    """What Nano reads: each question with its choices, then each file with its path."""
    out = ["The questions:"]
    for it in asked:
        out.append(f"[{it['id']}] {it['text']}")
        out.append(f"  default: {it['default'] or 'yes'}")
        out += [f"  option {k}: {o['text']}" for k, o in enumerate(it["options"], 1)]
    out.append("\nThe repository's files:")
    for path, text in sent.items():
        out += [f"--- {path}", text.rstrip("\n")]
    return "\n".join(out)


def kept(item: dict, answer: dict, sent: dict[str, str]) -> tuple[str, int | None, str] | None:
    """(state, option, "FILE:LINE") when the answer holds: the choice is one the question offers,
    the file was sent, and the quoted line is in it, spaces aside. None: the question stays open."""
    choice = _flat(str(answer.get("choice") or "")).lower()
    path, quoted = answer.get("file"), _flat(str(answer.get("line") or ""))
    if path not in sent or len(quoted) < LEAST:
        return None
    if choice == "default":
        state, option = "taken", None
    elif choice.removeprefix("option ").isdigit() and 1 <= int(choice[7:]) <= len(item["options"]):
        state, option = "picked", int(choice[7:])
    else:
        return None
    found = [no for no, line in enumerate(sent[path].splitlines(), 1) if quoted in _flat(line)]
    return (state, option, f"{path}:{found[0]}") if found else None


def lookup(store, root: Path, say: Callable[[str], None] = print) -> list[dict]:
    """Ask Nano once about every open question; settle each whose answer holds (``kept``), as the
    person. Returns the items settled. Refused when there is nothing to ask or Nano cannot be asked."""
    from . import tokenfactory as tf

    who = P.caller()
    P._person_only(who, "looking up the board's answers in the repository (it spends)")
    asked = questions(store)
    if not asked:
        raise P.Refused("no question is open on the board: nothing to look up")
    tracked = P.tracked(root)
    sent = files(root, asked, tracked)
    say = cover.plain(say)
    model = cover._nano()
    ask = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": shown(asked, sent)}]
    try:
        said = tf.chat(model, ask, tag="lookup", tries=1, timeout=BRIEF, response_format=FORMAT,
                       reasoning_effort="low", temperature=0, max_tokens=2048)  # fmt: skip
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
        answers = json.loads(said["message"].get("content") or "")["answers"]
        assert isinstance(answers, list)
    except (ValueError, KeyError, TypeError, AssertionError):
        say("its answer is not the JSON asked for: every question stays open")
        return []
    by_id, settled = {it["id"]: it for it in asked}, []
    for answer in answers:
        item = by_id.pop(answer.get("id"), None) if isinstance(answer, dict) else None
        holds = kept(item, answer, sent) if item else None
        if holds is None:
            continue
        state, option, where = holds
        try:
            done = B.settle(store, item["id"], state, who, option=option, files=tracked, **{"from": where})
        except P.Refused as no:
            say(f"! {item['id']}: not settled: {' '.join(str(no).split())[:200]}")
            continue
        settled.append(done)
        say(f"settled {done['id']} from the repo ({where}): {done['answer'] or 'yes'}; "
            f"`graphene board unpark {done['id']}` asks you")  # fmt: skip
    say(f"from the repo: {len(settled)} of {len(asked)} open questions settled; the rest stay on the board")
    return settled


def shaped() -> bool:
    return FLAG in os.environ.get("GRAPHENE_SHAPE", "").replace(" ", "").split(",")


def after_proposal(store, root: Path, say: Callable[[str], None]) -> None:
    """`graphene ask` with GRAPHENE_SHAPE=lookup: once the proposal has landed, what the repository
    answers is settled before the board reaches the person. A failure is one line; the ask stands."""
    if not shaped() or not questions(store):
        return
    try:
        lookup(store, root, say)
    except Exception as no:  # the proposal has landed: nothing here may turn that into a failed ask
        say(f"! the board was not looked up in the repository: {' '.join(str(no).split())[:200]}")
