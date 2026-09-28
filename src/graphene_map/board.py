"""The board: what the person and the planner put up before and beside the tree.

The planner puts up the questions the repository cannot answer (each with the default it would
assume, and options where it sees more than one way), what it assumed, the risks it sees and what it
would leave out; anyone puts up a note. Only the person answers: take the default (confirm an
assumption, agree to a leave-out), pick an option, answer in their own words, park it or drop it.
An answer is told to every executor it is about (``decided``), and a default or an option may carry
effects in the plan's own words (``then:``), applied as the person's edit when it is chosen:

    scope NODE + GLOB, …      NODE's scope takes in the globs
    check NODE: COMMAND       NODE's check becomes the command
    goal NODE + TEXT          NODE's goal ends with the sentence (the person's words, not the model's)
    drop NODE                 NODE leaves the plan
    leaf TITLE under NODE     a proposed leaf under NODE (beside it, when NODE is a leaf), for the
                              person to fill in or prune
    condition GLOB            no leaf may write the glob: the settings' read-only list reads it
                              (``conditions``), so the gate refuses the write and a scope over it

The board lives in the one store, as the plan_meta key ``board`` (a JSON list, in the order the
items were put up), so `graphene plan undo` puts back an answer with everything it changed. Every
act is a ``board`` row in the plan's log, on the node the item is about, else on ``*``.
"""

from __future__ import annotations

import json
import re

from . import plan as P

KEY = "board"  # the plan_meta key; plan.py's undo snapshot holds it
KINDS = ("question", "assume", "risk", "leave out", "note")
_ALIAS = {"assumption": "assume", "leave": "leave out", "left out": "leave out"}
DECIDED = ("taken", "picked", "answered")  # what is told to the executors
SUB = ("default", "option", "then", "about", "answer")
# the groups the board is shown in, in order: what waits on the person first, what is settled last
GROUPS = (
    ("questions", "question"), ("assumptions", "assume"), ("risks", "risk"),
    ("left out", "leave out"), ("notes", "note"),
)  # fmt: skip
_TOLD = {"question": "", "assume": "assumed: ", "risk": "risk: ", "leave out": "left out: ", "note": ""}
_EFFECTS = (
    ("scope", re.compile(r"scope\s+(?P<node>[^\s+]+)\s*\+\s*(?P<arg>.+)")),
    ("check", re.compile(r"check\s+(?P<node>[^\s:]+)\s*:\s*(?P<arg>.+)")),
    ("goal", re.compile(r"goal\s+(?P<node>[^\s+]+)\s*\+\s*(?P<arg>.+)")),
    ("drop", re.compile(r"drop\s+(?P<node>\S+)")),
    # a quoted title is whole ("profile under load"); unquoted, the last "under NODE" names the node
    ("leaf", re.compile(r"leaf\s+(?P<arg>\"[^\"]*\"|'[^']*'|.+?)(?:\s+under\s+(?P<node>\S+))?")),
    ("condition", re.compile(r"condition\s+(?P<arg>.+)")),
)
ORPHAN = "delete them with the item's line to drop it, or put its line back"
FORMS = (
    "scope NODE + GLOB, check NODE: COMMAND, goal NODE + TEXT, drop NODE, leaf TITLE under NODE, or "
    "condition GLOB"
)


def _one(text: str | None) -> str:
    return " ".join(str(text or "").split())


# -- reading the board ----------------------------------------------------------------------------


def items(store) -> list[dict]:
    """Every item ever put up, dropped ones too, in the order they were put up."""
    return json.loads(store.meta(KEY) or "[]")


def _put(store, board: list[dict]) -> None:
    store.set_meta(KEY, json.dumps(board))


def get(store, item_id: str) -> dict:
    found = next((it for it in items(store) if it["id"] == item_id), None)
    if found is None:
        known = ", ".join(it["id"] for it in items(store) if it["state"] != "dropped") or "none yet"
        raise P.Refused(f"no item {item_id} on the board (items: {known})")
    return found


def told(item: dict) -> bool:
    """Is it told to the executors? An answer, and a note the person wrote (their own words need
    no answer); a note an agent wrote is told once the person takes it."""
    return item["state"] in DECIDED or (
        item["kind"] == "note" and item["state"] == "open" and not item["agent"]
    )


def reads(item: dict) -> str:
    """The one word an item's state reads as, in the row grammar: open (the person's move), parked,
    dropped, noted (a note of the person's, told as written), or what the answer was."""
    if item["kind"] == "note" and item["state"] == "open" and not item["agent"]:
        return "noted"
    return item["state"]


def look(item: dict) -> tuple[str, str]:
    """The glyph and colour of an item's row, from the plan's own (``P.LOOK``): open waits on the
    person (magenta), a told item is settled (green), a parked one waits on nothing (dim)."""
    word = reads(item)
    if word == "open":
        return P.LOOK["yours"]
    if word in (*DECIDED, "noted"):
        return P.LOOK["done"]
    return P.LOOK["waiting"]


def groups(store) -> list[tuple[str, list[dict]]]:
    """The board in the order it is shown: what is open, kind by kind (questions first), then what
    is parked, then what is settled (answered, and the person's notes), then what was dropped.
    Empty groups are left out."""
    board = items(store)
    out = [
        (name, [it for it in board if it["kind"] == kind and reads(it) == "open"]) for name, kind in GROUPS
    ]
    out += [("parked", [it for it in board if it["state"] == "parked"])]
    out += [("settled", [it for it in board if told(it)])]
    out += [("dropped", [it for it in board if it["state"] == "dropped"])]
    return [(name, shown) for name, shown in out if shown]


def waiting(store) -> tuple[int, str | None]:
    """How many items wait on the person, and the line `graphene plan` says it in (None: none do):
    "the board: 2 questions, 1 risk open (`graphene board`)"."""
    open_ = [(name, group) for name, group in groups(store) if name in dict(GROUPS)]
    if not open_:
        return 0, None
    said = ", ".join(
        f"{len(g)} {name[:-1] if len(g) == 1 and name.endswith('s') else name}" for name, g in open_
    )
    return sum(len(g) for _, g in open_), f"the board: {said} open (`graphene board`)"


def shown(store) -> list[dict]:
    """The items a screen lists, in display order (``groups``), without the dropped ones."""
    return [it for name, group in groups(store) if name != "dropped" for it in group]


def said(item: dict) -> str:
    """An item as the executors are told it: the kind's word, its words, and the answer."""
    answer = _one(item.get("answer"))
    return f"{_TOLD[item['kind']]}{item['text']}" + (f" → {answer}" if answer else "")


def decided(store, node: P.Node | None = None) -> list[str]:
    """What the board decided that an executor of ``node`` is told, one line each: what is about the
    whole plan, and what is about the node or a sub-goal above it."""
    on: set[str | None] = {None}
    if node is not None:
        by_id = {n.id: n for n in P.nodes(store)}
        on |= {node.id, *(a.id for a in P.above(node, by_id))}
    return [said(it) for it in items(store) if told(it) and it.get("about") in on]


def about_gone(store, item: dict) -> bool:
    """Is the node the item is about out of the plan? Then no executor is told it."""
    return bool(item.get("about")) and (store.node_row(item["about"]) or {}).get("state") in (None, *P.GONE)


def dropped(store) -> list[str]:
    """The words of what the person dropped, for a planner that is asked again not to bring it back."""
    return [it["text"] for it in items(store) if it["state"] == "dropped"]


def conditions(store) -> list[str]:
    """The conditions the person chose on the board (``then: condition GLOB``), in the order chosen:
    the settings' read-only list reads them (``settings.readonly``), so the gate refuses a write to one
    and the plan a scope over one, until `plan undo` takes the answer back."""
    return [c for it in items(store) if it["state"] in DECIDED for c in it.get("conditions", [])]


# -- effects --------------------------------------------------------------------------------------


def effect(line: str, no: int = 0) -> tuple[str, str | None, str | list[str]]:
    """A `then:` line as (verb, node, what): refused when it is not one of the five forms."""
    from . import plan_text as T

    line = _one(line)
    for verb, form in _EFFECTS:
        found = form.fullmatch(line)
        if found:
            node = (found.groupdict().get("node") or "").strip("[]`") or None
            arg = found["arg"] if "arg" in found.groupdict() else ""
            if verb == "condition":  # a read-only glob, read as `graphene config` reads one
                from . import settings as S

                try:
                    return verb, node, [S._glob(no, g) for g in T._words(arg or "", no)]
                except P.Refused as bad:
                    raise P.Refused(str(bad).removeprefix("line 0: ")) from None
            if verb == "scope":
                return verb, node, T._words(arg or "", no)
            if verb in ("leaf", "goal") and len(arg) > 1 and arg[0] == arg[-1] and arg[0] in "'\"":
                arg = arg[1:-1]
            return verb, node, (arg or "").strip()
    raise P.Refused(f"then: {line!r} is not read; an effect is {FORMS}")


def _there(store, node_id: str | None, what: str) -> None:
    if node_id is not None and (store.node_row(node_id) or {}).get("state") in (None, *P.GONE):
        raise P.Refused(f"{what} {node_id}, which is not a node in the plan")


def _apply(store, line: str, who: P.Caller, now: str, files, conditions: list[str]) -> str:
    """One effect, made as the person's edit; returns what it changed, in a line."""
    from . import plan_text as T

    verb, node_id, what = effect(line)
    _there(store, node_id, f"then: {line} names")
    if verb == "scope":
        node = P.get(store, node_id)
        new = [g for g in what if g not in node.scope]
        P.edit(store, node_id, {"scope": [*node.scope, *new]}, who, now, files)
        return f"{node_id}: scope + {', '.join(new) or 'nothing new'}"
    if verb == "check":
        P.edit(store, node_id, {"check": what}, who, now, files)
        return f"{node_id}: check is now {what}"
    if verb == "goal":
        goal = P.goal_plus(P.get(store, node_id).goal, what)
        if goal is None:
            return f"{node_id}: its goal says it already"
        P.edit(store, node_id, {"goal": goal}, who, now, files)
        return f"{node_id}: goal + {what}"
    if verb == "drop":
        P.drop(store, node_id, who, now)
        return f"dropped {node_id}"
    if verb == "leaf":
        everything = P.nodes(store)
        leaf = T.slug(what, {n.id for n in everything})
        parent = node_id
        if node_id and not any(n.parent == node_id and n.state not in P.GONE for n in everything):
            parent = P.get(store, node_id).parent  # a leaf stays a leaf: its work is never left to no one
        P.propose(store, [{"id": leaf, "title": what, "parent": parent}], who, now, files, proposals={leaf})
        if parent != node_id:
            return f"proposed {leaf} beside {node_id}, a leaf, under {parent or 'the goal'}"
        return f"proposed {leaf} under {node_id or 'the goal'}"
    conditions += what
    return f"no leaf may write {', '.join(what)} (read-only, as `graphene config` shows)"


# -- the acts -------------------------------------------------------------------------------------


def _line(at: dict, key: str) -> str:
    return f"line {at[key]}: " if key in at else ""


def _check(store, item: dict, at: dict | None = None) -> None:
    """Refuse an item the board cannot hold: an empty one, options on what is not a question, an
    about: or an effect that names no node in the plan (by its line, in the text form)."""
    at = at or {}
    if item["kind"] not in KINDS:
        raise P.Refused(f"{_line(at, 'item')}a board item is a {', '.join(KINDS)}, not {item['kind']!r}")
    if not item["text"]:
        raise P.Refused(f"{_line(at, 'item')}a {item['kind']} needs its words after the colon")
    if any(not o["text"] for o in item["options"]):
        raise P.Refused(f"{_line(at, 'option')}an option: needs its words")
    if item["options"] and item["kind"] != "question":
        raise P.Refused(
            f"{_line(at, 'option')}option: is a question's; a {item['kind']} has a default: at most"
        )
    try:
        _there(store, item.get("about"), "about:")
    except P.Refused as no:
        raise P.Refused(f"{_line(at, 'about')}{no}") from None
    for line in [*item["then"], *(e for o in item["options"] for e in o["then"])]:
        where = _line(at, f"then {line}")
        try:
            verb, node_id, _ = effect(line, at.get(f"then {line}", 0))
            _there(store, node_id, f"then: {line} names")
        except P.Refused as no:
            raise P.Refused(where + str(no).removeprefix(where)) from None


def _log(store, item: dict, act: str, who: P.Caller, now: str, **detail) -> None:
    note = f"{act} {item['id']}: {item['text']}" + (
        f" → {_one(item['answer'])}" if item.get("answer") else ""
    )
    store.log_node(
        item.get("about") or "*", now, "board", who.label, who.session_id, None,
        {"note": note, "item": item["id"], "act": act, **detail},
    )  # fmt: skip


def add(
    store,
    kind: str,
    text: str,
    who: P.Caller,
    default: str | None = None,
    then: list[str] | None = None,
    options: list[dict] | None = None,
    about: str | None = None,
    item_id: str | None = None,
    now: str | None = None,
    at: dict | None = None,
) -> dict:
    """Put an item up, as whoever asks: an agent's is marked as the agent's, and waits on the person."""
    from . import plan_text as T

    now = now or P._now()
    with store.claim():
        board = items(store)
        taken = {it["id"] for it in board} | {n.id for n in P.nodes(store)}
        kind = _ALIAS.get(kind, kind)
        fresh = T.slug(text, taken, kind.replace(" ", "-"))  # a note in Japanese is "note", not "node"
        item = {
            "id": item_id if item_id and item_id not in taken else fresh,
            "kind": kind, "text": _one(text), "default": _one(default) or None,
            "then": [_one(e) for e in then or []],
            "options": [{"text": _one(o["text"]), "then": [_one(e) for e in o.get("then", [])]}
                        for o in options or []],
            "about": about or None, "by": who.label, "agent": not who.person, "state": "open", "answer": None,
            "option": None, "became": [], "conditions": [], "rev": 1, "created_at": now, "updated_at": now,
        }  # fmt: skip
        _check(store, item, at)
        _put(store, [*board, item])
        _log(store, item, "put up", who, now)
    return item


def note(store, words: str, who: P.Caller, about: str | None = None, now: str | None = None) -> dict:
    """A note of the person's is told to the executors as written; an agent's waits on the person."""
    return add(store, "note", words, who, about=about, now=now)


def answer_of(said: str) -> tuple[str, int | None, str | None]:
    """An `answer:` line as (state, option, words): default, option N, parked, or words."""
    said = _one(said)
    low = said.lower()
    if low == "default":
        return "taken", None, None
    if low == "parked":
        return "parked", None, None
    number = re.fullmatch(r"option\s+(\d+)", low)
    if number:
        return "picked", int(number[1]), None
    return "answered", None, said


def spelled(item: dict) -> str | None:
    """The `answer:` line an item's state is written as in the text form (None: no line)."""
    return {"taken": "default", "picked": f"option {item.get('option')}", "parked": "parked"}.get(
        item["state"], item.get("answer") if item["state"] == "answered" else None
    )


def settle(
    store,
    item_id: str,
    state: str,
    who: P.Caller,
    option: int | None = None,
    words: str | None = None,
    files: list[str] | None = None,
    now: str | None = None,
) -> dict:
    """The person answers an item: ``state`` is taken (the default, or yes), picked (``option``, from
    1), answered (``words``), parked, dropped, or open again (only from parked). What the chosen
    default or option says `then:` is applied in the same transaction, as the person's edit."""
    if not who.person:
        raise P.Refused(f"answering the board is the person's, not {who.name}'s")
    now = now or P._now()
    with store.claim():
        board = items(store)
        item = next((it for it in board if it["id"] == item_id), None) or get(store, item_id)
        if item["state"] == "dropped":
            raise P.Refused(f"{item_id} was dropped; `graphene plan undo` brings it back")
        if item["state"] in DECIDED and state != "dropped":
            raise P.Refused(
                f"{item_id} is {item['state']} already ({_one(item['answer']) or 'yes'}); "
                "`graphene plan undo` takes an answer back"
            )
        if state == "open" and item["state"] != "parked":
            raise P.Refused(f"{item_id} is {reads(item)}, not parked")
        if state in DECIDED and about_gone(store, item):  # its answer would be told to no executor
            raise P.Refused(
                f"{item_id} is about {item['about']}, which has left the plan; drop it, or give it another "
                "about: in `graphene plan edit`"
            )
        effects: list[str] = []
        answer = None
        if state == "taken":
            effects, answer = item["then"], item["default"]
        elif state == "picked":
            if not item["options"]:
                raise P.Refused(f"{item_id} has no options to pick from; take its default or answer it")
            if option is None or not 1 <= option <= len(item["options"]):
                raise P.Refused(f"{item_id} has options 1 to {len(item['options'])}, not {option}")
            chosen = item["options"][option - 1]
            effects, answer = chosen["then"], chosen["text"]
        elif state == "answered":
            answer = _one(words)
            if not answer or answer_of(answer)[0] != "answered":
                raise P.Refused(
                    f"say the answer in words; {answer!r} is `graphene board take`, `pick` or `park`"
                    if answer
                    else "an answer needs its words"
                )
        conditions: list[str] = []
        became = [_apply(store, line, who, now, files, conditions) for line in effects]
        item.update(
            state=state, answer=answer, option=option if state == "picked" else None, rev=item["rev"] + 1,
            updated_at=now, became=became or item["became"], conditions=conditions or item["conditions"],
        )  # fmt: skip
        _put(store, board)
        _log(store, item, {"taken": "took", "open": "unparked"}.get(state, state), who, now, became=became)
    return item


def take(store, item_id: str, who: P.Caller, files: list[str] | None = None) -> dict:
    return settle(store, item_id, "taken", who, files=files)


def pick(store, item_id: str, option: int, who: P.Caller, files: list[str] | None = None) -> dict:
    return settle(store, item_id, "picked", who, option=option, files=files)


def answer(store, item_id: str, words: str, who: P.Caller) -> dict:
    return settle(store, item_id, "answered", who, words=words)


def park(store, item_id: str, who: P.Caller) -> dict:
    return settle(store, item_id, "parked", who)


def unpark(store, item_id: str, who: P.Caller) -> dict:
    return settle(store, item_id, "open", who)


def drop(store, item_id: str, who: P.Caller) -> dict:
    return settle(store, item_id, "dropped", who)


def rehome(store, gone: set[str], who: P.Caller, now: str | None = None) -> list[tuple[dict, str]]:
    """What is on the board about a node that left the plan (answered, parked or still open) becomes
    about the whole plan, so it is, or once answered will be, told to every executor rather than to
    none. Returns (item, the node it was about)."""
    now = now or P._now()
    moved = []
    with store.claim():
        board = items(store)
        for item in board:
            if item.get("about") in gone and item["state"] != "dropped":
                moved.append((item, item["about"]))
                item.update(about=None, rev=item["rev"] + 1, updated_at=now)
                _log(store, item, "moved to the whole plan", who, now, was=moved[-1][1])
        _put(store, board)
    return moved


# -- the text form --------------------------------------------------------------------------------


def lines(item: dict) -> list[str]:
    """One item in the plan's text: its line at the left edge, then its own lines under it."""
    return [f"{item['kind']}: {item['text']}  [{item['id']}]", *_own(item, spelled(item))]


def _own(item: dict, answer: str | None) -> list[str]:
    out = []
    if item["default"] or item["then"]:
        out += [f"    default: {item['default'] or ''}".rstrip(), *(f"    then: {e}" for e in item["then"])]
    for o in item["options"]:
        out += [f"    option: {o['text']}", *(f"    then: {e}" for e in o["then"])]
    out += [f"    about: {item['about']}"] if item.get("about") else []
    return out + ([f"    answer: {answer}"] if answer else [])


def _fields(item: dict) -> dict:
    return {k: item.get(k) for k in ("kind", "text", "default", "then", "options", "about")}


def render(store) -> tuple[list[str], dict[str, dict]]:
    """The board's lines for the top of the plan's text (dropped items are not written), and each
    item as it was written, for an edit to be told from what was shown."""
    out: list[str] = []
    written: dict[str, dict] = {}
    for item in items(store):
        if item["state"] == "dropped":
            continue
        out += lines(item)
        written[item["id"]] = {
            **_fields(item),
            "answer": spelled(item),
            "rev": item["rev"],
            "state": item["state"],
        }
    return out, written


def split(text: str) -> tuple[str, list[dict]]:
    """The board's lines taken out of a plan's text (each left as an empty line, so every other line
    keeps its number), and the items they say. An item's line is keyed at the left edge; its own
    lines are the indented ones under it, up to the next line at the left edge or the next node."""
    from . import plan_text as T

    kept = text.lstrip("﻿").splitlines()
    found: list[dict] = []
    item: dict | None = None
    choice: dict | None = None
    tree = False  # a node's line was seen: indented lines from here on are the tree's
    for no, raw in enumerate(kept, 1):
        body = raw.strip()
        if not body or body.startswith("#") or body.startswith(T._FENCE):
            continue
        keyed = T._KEY.fullmatch(body)
        word = " ".join(keyed["key"].lower().replace("_", " ").replace("-", " ").split()) if keyed else ""
        word = _ALIAS.get(word, word)
        if raw[:1] not in (" ", "\t") or T._MARK.fullmatch(body):
            item = None
            if not (keyed and word in KINDS):
                tree = tree or not (keyed and word == "goal")
                continue
            value = keyed["value"].strip()
            at_end = T._ID_AT_END.search(" " + value)
            ident = at_end["id"].strip("`*#_ ") if at_end else None
            if ident and not T._VALID_ID.fullmatch(ident):
                raise P.Refused(
                    f"line {no}: [{ident}] is not an id: letters, digits, '-', '_' and '.', at most 32"
                )
            text_ = (" " + value)[: at_end.start()].strip() if at_end else value
            item = {"kind": word, "text": _one(text_), "id": ident, "default": None, "then": [],
                    "options": [], "about": None, "answer": None, "at": {"item": no}, "no": no,
                    "own": []}  # fmt: skip
            choice = None
            found.append(item)
        elif item is None:
            if keyed and word in SUB and not tree:
                raise P.Refused(f"line {no}: these lines belong to no board item; {ORPHAN}")
            continue
        elif keyed and word in SUB:
            item["own"].append((no, _one(body)))
            value = _one(keyed["value"])
            if word in ("default", "about", "answer") and word in item["at"]:
                raise P.Refused(
                    f"line {no}: [{item['id'] or item['text'][:30]}] has its {word}: on line "
                    f"{item['at'][word]} already"
                )
            item["at"].setdefault(word, no)
            if word == "default":
                item["default"], choice = value or None, item
            elif word == "option":
                item["options"].append({"text": value, "then": []})
                choice = item["options"][-1]
            elif word == "then":
                if choice is None:
                    raise P.Refused(
                        f"line {no}: then: goes under the default: or option: it is the effect of"
                    )
                choice["then"].append(value)
                item["at"][f"then {value}"] = no
            elif word == "about":
                item["about"] = value.strip("[]`") or None
            else:
                item["answer"] = value
        elif not keyed and len(item["at"]) == 1:
            item["text"] = _one(f"{item['text']} {body}")  # its words, carried on to the next line
        else:
            raise P.Refused(
                f"line {no}: {body[:40]!r} is under a {item['kind']}, whose own lines are default:, option:, "
                "then:, about: and answer:"
            )
        kept[no - 1] = ""
    return "\n".join(kept), found


def apply(store, found: list[dict], who: P.Caller, opened: dict | None, files=None, now=None) -> list[str]:
    """Make the board say what the text says. ``opened`` is what ``render`` wrote (an edit: a changed
    answer is the person's answer, an item whose lines were deleted is dropped); None is a proposal
    (only new items count; one already on the board, unchanged, is passed over). Returns one line
    per change, for whoever applied it."""
    now = now or P._now()
    if opened is not None:
        _orphans(found, opened)
    said: list[str] = []
    board = {it["id"]: it for it in items(store)}
    gone = {_one(it["text"]).lower(): it["id"] for it in board.values() if it["state"] == "dropped"}
    seen: dict[str, int] = {}
    for f in found:
        at = f["at"]
        if opened is None and not who.person and _one(f["text"]).lower() in gone:
            said.append(
                f"not put up again: {f['text']} (the person dropped it as {gone[_one(f['text']).lower()]})"
            )
            continue
        if f["id"] in seen:
            raise P.Refused(
                f"line {f['no']}: [{f['id']}] is on line {seen[f['id']]} too; give each its own id"
            )
        if f["id"]:
            seen[f["id"]] = f["no"]
        known = board.get(f["id"] or "")
        if known is not None and opened is not None and f["id"] not in opened:
            raise P.Refused(
                f"line {f['no']}: [{f['id']}] is on the board already; give this line another id, or none"
            )
        if known is not None and opened is None and known["state"] != "dropped":
            if _fields(f) != _fields(known) or (f["answer"] and _one(f["answer"]) != _one(spelled(known))):
                raise P.Refused(
                    f"line {f['no']}: [{f['id']}] is on the board already, and this text changes it; the "
                    "person edits the board (`graphene plan edit`), or give this line another id"
                )
            continue
        if known is None or (known["state"] == "dropped" and opened is None):
            if f["answer"] and not who.person:
                raise P.Refused(f"line {at['answer']}: answering the board is the person's, not {who.name}'s")
            item = add(store, f["kind"], f["text"], who, f["default"], f["then"], f["options"], f["about"],
                       None if known else f["id"], now, at)  # fmt: skip
            said.append(f"put up {item['id']}: {item['text']}")
            if f["answer"]:
                said += _answered(store, item["id"], f["answer"], who, files, now, at)
            continue
        base = opened[f["id"]]
        if _fields(f) != {k: base[k] for k in _fields(f)}:
            if known["rev"] != base["rev"]:
                raise P.Refused(
                    f"line {f['no']}: [{f['id']}] was changed by someone else since this text was opened"
                )
            _check(store, f, at)
            _reword(store, f, who, now)
            said.append(f"{f['id']}: changed")
        if _one(f["answer"]) != _one(base["answer"]):
            if get(store, f["id"])["state"] != base["state"]:
                raise P.Refused(
                    f"line {at.get('answer', f['no'])}: [{f['id']}] was changed by someone else since this "
                    "text was opened"
                )
            said += _answered(store, f["id"], f["answer"], who, files, now, at)
    for item_id, base in (opened or {}).items():
        if item_id in seen or board.get(item_id, {"state": "dropped"})["state"] == "dropped":
            continue
        if board[item_id]["rev"] != base["rev"]:
            raise P.Refused(
                f"[{item_id}], whose lines were deleted, was changed by someone else since this text was "
                "opened"
            )
        settle(store, item_id, "dropped", who, now=now)
        said.append(f"dropped {item_id}: {board[item_id]['text']}")
    return said


def _orphans(found: list[dict], opened: dict[str, dict]) -> None:
    """Refuse the own lines of an item whose line alone was deleted: they are left under the item
    written above it, where they would silently become that item's."""
    ids, seen = list(opened), {f["id"] for f in found}
    for f in found:
        k = ids.index(f["id"]) if f["id"] in opened else len(ids)
        if k + 1 >= len(ids) or ids[k + 1] in seen:
            continue
        mine = [_one(x) for x in _own(opened[f["id"]], opened[f["id"]]["answer"])]
        theirs = [_one(x) for x in _own(opened[ids[k + 1]], opened[ids[k + 1]]["answer"])]
        got = [body for _, body in f["own"]]
        if theirs and got[: len(mine) + len(theirs)] == mine + theirs:
            raise P.Refused(
                f"line {f['own'][len(mine)][0]}: these lines belong to no board item ([{ids[k + 1]}]'s own "
                f"line was deleted); {ORPHAN}"
            )


def _answered(store, item_id: str, spelled_: str | None, who, files, now, at: dict) -> list[str]:
    state, option, words = answer_of(spelled_) if spelled_ else ("open", None, None)
    try:
        item = settle(store, item_id, state, who, option, words, files, now)
    except P.Refused as no:
        raise P.Refused(f"{_line(at, 'answer') or _line(at, 'item')}{no}") from None
    return [f"{reads(item)} {item_id}" + (f": {'; '.join(item['became'])}" if item["became"] else "")]


def _reword(store, found: dict, who: P.Caller, now: str) -> None:
    """The person rewrote an item's own words, default, options or effects: they replace the old."""
    with store.claim():
        board = items(store)
        item = next(it for it in board if it["id"] == found["id"])
        item.update(_fields(found), rev=item["rev"] + 1, updated_at=now)
        _put(store, board)
        _log(store, item, "edited", who, now)
