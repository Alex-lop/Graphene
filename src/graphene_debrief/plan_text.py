"""The plan as text: one line a node, indentation for the tree, and each node's contract under it.

    goal: customers can download their invoices as PDF

    - the PDF renderer  [pdf]
      - render one invoice to PDF bytes  [render-invoice]
          scope: src/pdf/**, tests/pdf/**
          check: pytest tests/pdf
      ? the invoice template  [template]
          the layout from the design, with the customer's address block
          scope: templates/invoice.html
          check: make lint
          needs: render-invoice

"-" is a node in the plan and "?" a proposal (make it "-" to accept it). A line indented under a
node is its child. Under a node, `scope:` `check:` `needs:` `owner:` and `signoff:` are its contract;
any other line under it says what it should achieve. "#" lines are Graphene's notes and are never
read. The [id] keeps an edit on the node it was made on; a line without one is a new node.

It is the form a person edits (`graphene plan edit`, `E` in `graphene watch`), the form an agent
proposes in (`graphene plan propose -`), and the form `graphene plan --text` prints. What a text
edit does is computed as operations the plan already has (add, edit, accept, drop) and applied in
one transaction: a line Graphene cannot read, or an operation the plan refuses, applies nothing,
and the refusal names the line.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import plan as P

KEYS = ("scope", "check", "needs", "owner", "signoff", "goal")
# Other spellings of a key that are read as it: they say nothing else (and a needs: value that is not
# an id is refused anyway, so prose read as one does not pass).
_SAME = {
    "sign-off": "signoff", "sign off": "signoff", "sign_off": "signoff", "need": "needs",
    "depends on": "needs", "depends_on": "needs", "depends": "needs", "requires": "needs",
    "after": "needs", "blocked by": "needs", "description": "goal",
}  # fmt: skip
# Spellings that are refused with the key they probably mean: their values are paths or commands, and
# a guess would widen a scope or run a sentence as a check.
_NEAR = {
    "paths": "scope", "path": "scope", "files": "scope", "file": "scope", "writes": "scope",
    "checks": "check", "test": "check", "tests": "check", "verify": "check", "done when": "check",
    "done": "check", "acceptance": "check", "deps": "needs", "dependencies": "needs", "assignee": "owner",
}  # fmt: skip
_MARK = re.compile(r"(?P<mark>[-*+?]|\d{1,3}[.)]|•)\s+(?P<rest>.*)")
_ID_AT_END = re.compile(r"\s+\[(?P<id>[^\[\]]{1,40})\](?P<after>\s*(?::|\([^()]*\))?)\s*$")
_ID_FIRST = re.compile(r"\[(?P<id>[A-Za-z0-9][\w.-]{0,31})\]\s+(?P<title>.+)")
_VALID_ID = re.compile(r"[A-Za-z0-9][\w.-]{0,31}")
_KEY = re.compile(
    r"(?:\*\*|__)?(?P<key>[A-Za-z][A-Za-z _-]{0,15}?)(?:\*\*|__)?\s*[:=](?:\*\*|__)?(?:\s+|$)(?P<value>.*)"
)
_BOX = re.compile(r"\[[ xX]\]\s+")
_YES, _NO = ("yes", "y", "true", "on"), ("no", "n", "false", "off", "")
_NONE = ("none", "n/a", "-", "")
_SMALL = {"the", "a", "an", "of", "to", "for", "and", "in", "on", "with", "as", "is", "be"}
HELP = """\
# "-" is a node in the plan, "?" a proposal: make it "-" to accept it. Indent a line under another
# to put it there; delete a node's lines (its own and what is under it) to drop it; reorder to reorder.
# A line with no [id] is a new node; a child goes after its parent's own lines. Under a node: scope:
# the paths it may write; check: a command that exits 0 when it is done; needs: ids it waits on;
# owner: me; signoff: yes. Any other line under a node says what it should achieve. Lines starting
# with # are notes, never read.
# Save and quit to apply. Nothing is applied when a line cannot be read, or when this is emptied."""


@dataclass
class Line:
    """One node as the text says it."""

    no: int  # 1-based, as the person's editor numbers it
    indent: int
    id: str | None
    proposal: bool
    title: str
    parent: int | None = None  # index of the line it is indented under
    scope: list[str] = field(default_factory=list)
    check: str | None = None
    needs: list[str] = field(default_factory=list)
    owner: str = P.AGENT
    signoff: bool = False
    goal: list[str] = field(default_factory=list)
    said: set[str] = field(default_factory=set)  # which keys the text wrote at all
    column: int | None = None  # where its own lines start: they all start there


def _words(value: str, no: int) -> list[str]:
    """Paths or ids, separated by commas or spaces, quoted when they hold either; `# …` ends them."""
    lex = shlex.shlex(value, posix=True)
    lex.whitespace += ","
    lex.whitespace_split = True
    lex.commenters = "#"
    try:
        return [w.strip("`") for w in lex if w.strip("`")]
    except ValueError as exc:
        raise P.Refused(
            f"line {no}: {exc} (quote a path with a space or a comma in it, and close it)"
        ) from None


def _key(body: str, near: bool = True) -> tuple[str, str] | None:
    """A contract line's key, as the key it means, and its value; None when it is not one. A
    spelling that is refused comes back as ("?", the word); ``near``: look for those at all."""
    found = _KEY.fullmatch(body)
    if not found:
        return None
    word = " ".join(found["key"].lower().split())
    if word in KEYS or word in _SAME:
        return _SAME.get(word, word), found["value"].strip()
    if near and word in _NEAR:
        return "?", word
    return None


def _node(body: str, no: int) -> tuple[str, str | None, bool] | None:
    """A node's line: its title, its [id], whether it is a proposal. None when it is not one. A
    numbered line is a node only when it ends in an [id]; otherwise it says what its node is for."""
    marked = _MARK.fullmatch(body)
    if not marked:
        return None
    mark, rest = marked["mark"], _BOX.sub("", marked["rest"], count=1)
    ident, title = None, rest.strip()
    at_end = _ID_AT_END.search(" " + rest)
    first = _ID_FIRST.fullmatch(rest)
    if at_end:
        if not _VALID_ID.fullmatch(at_end["id"]):
            raise P.Refused(
                f"line {no}: [{at_end['id']}] is not an id: letters, digits, '-', '_' and '.', at most 32, "
                "at the very end of the line"
            )
        ident, title = at_end["id"], ((" " + rest)[: at_end.start()] + at_end["after"].lstrip(":")).strip()
    elif first:
        ident, title = first["id"], first["title"].strip()
    if not mark.startswith(("-", "*", "+", "?")):
        if ident is None:
            return None  # "1. read the file": a step of what its node should achieve
        mark = "-"
    if not title:
        raise P.Refused(f"line {no}: a node needs a title after its '{mark}'")
    return title, ident, mark == "?"


def parse(text: str) -> tuple[str | None, list[Line]]:
    """The plan's goal and the node lines, in order. A node's own lines (its contract, and what it
    should achieve) are the lines right under its line, before the next node's, all at one column.
    A line that fits nowhere is refused, by its number, with what to do; it is never given to a node
    it was not written under."""
    goal: list[str] | None = None
    lines: list[Line] = []
    stack: list[int] = []  # indexes into lines, the node lines still open for children
    pending: tuple[Line, str, int] | None = None  # a key whose values are the list under it
    for no, raw in enumerate(text.lstrip("﻿").splitlines(), 1):
        body = raw.lstrip(" \t").rstrip()
        indent = len(raw[: len(raw) - len(raw.lstrip(" \t"))].expandtabs(4))  # tabs only where they indent
        if not body or (body.startswith("#") and not body.startswith("##")) or body.startswith("```"):
            continue
        if body.startswith("##"):
            raise P.Refused(
                f"line {no}: a heading is not read; a sub-goal is a '- ' line, its leaves under it"
            )
        marked = _MARK.fullmatch(body)
        if pending and indent > pending[2] and marked and not _ID_AT_END.search(" " + body):
            _set(pending[0], pending[1], marked["rest"], no)  # `scope:`, then its paths as a list
            continue
        pending = None
        as_key = _key(marked["rest"], near=False) if marked else None  # "- scope: src/**" is a key
        node = None if as_key and not _ID_AT_END.search(" " + body) else _node(body, no)
        if node:
            while stack and lines[stack[-1]].indent >= indent:
                stack.pop()
            lines.append(Line(no, indent, node[1], node[2], node[0], stack[-1] if stack else None))
            stack.append(len(lines) - 1)
            continue
        keyed = as_key or _key(body)
        if keyed and keyed[0] == "goal" and (not lines or indent == 0):
            goal = [*(goal or []), keyed[1]]  # the plan's goal: before any node, or at the left edge
            continue
        if not lines:
            if goal is not None and indent > 0:
                goal.append(body)  # the goal, carried on to the next line
                continue
            raise P.Refused(
                f"line {no}: {body[:40]!r} is not under a node. A node's line starts with '- ' (or '? ' for "
                "a proposal); its scope:, check: and what it should achieve go indented under it"
            )
        last = lines[-1]
        if indent <= last.indent:
            raise P.Refused(
                f"line {no}: {body[:40]!r} is not indented under [{last.id or last.title}], the node just "
                "above it. A node's own lines go right under its line, before its children"
            )
        if last.column is None and indent > last.indent + 4:
            raise P.Refused(
                f"line {no}: {body[:40]!r} is indented as if under a node whose line is gone: deeper than "
                f"[{last.id or last.title}]'s own lines would be. Delete it with that node's line, or put "
                "a node's line above it"
            )
        last.column = last.column if last.column is not None else indent
        if indent < last.column or (keyed and indent != last.column):
            raise P.Refused(
                f"line {no}: {body[:40]!r} does not line up with [{last.id or last.title}]'s other lines; "
                "a node's own lines start at one column"
            )
        if not keyed:
            last.goal.append(body)
            continue
        name, value = keyed
        if name == "?":
            raise P.Refused(f"line {no}: '{value}:' is not read; say it with {_NEAR[value]}:")
        if not value and name in ("scope", "needs", "check"):
            pending = (last, name, indent)
        _set(last, name, value, no)
    return ("\n".join(goal) if goal is not None else None), lines


def _set(line: Line, name: str, value: str, no: int) -> None:
    if name == "scope":
        words = [w for w in _words(value, no) if w.lower() not in _NONE]
        braced = next((w for w in words if "{" in w or "}" in w), None)
        if braced:
            raise P.Refused(f"line {no}: braces are not read in a scope ({braced}); list each glob instead")
        line.scope += words
    elif name == "needs":
        line.needs += [w for w in _words(value, no) if w.lower() not in _NONE]
    elif name == "check":
        if len(value) > 1 and value[0] == value[-1] and value[0] in "`'\"":
            value = value[1:-1].strip()  # a command quoted as a whole is still the command
        if value.lower() in _NONE:
            value = ""
        if value and line.check is not None:
            raise P.Refused(f"line {no}: [{line.id or line.title}] has a check already; join them with &&")
        line.check = value or line.check
    elif name == "owner":
        line.owner = value or P.AGENT
    elif name == "signoff":
        if value.lower() not in (*_YES, *_NO):
            raise P.Refused(f"line {no}: signoff is yes or no, not {value!r}")
        line.signoff = value.lower() in _YES
    else:
        line.goal.append(value)
    line.said.add(name)


# -- the plan, written as text ------------------------------------------------------------------------


def _norm_check(check: str | None) -> str | None:
    """A check as one line (the text has no continuation lines); a stored check with line breaks is
    compared in this form, so an edit elsewhere never rewrites it."""
    if not check:
        return None
    return "; ".join(part.strip() for part in check.splitlines() if part.strip()) or None


def _norm_goal(goal: str) -> list[str]:
    return [line.strip() for line in goal.strip().splitlines() if line.strip()]


def _globs(words: list[str]) -> str:
    """Globs as `_words` reads them back, exactly: quoted when they hold a comma, a space, a quote or
    a backslash."""
    plain = re.compile(r"[\w@%+=:./*?!\[\]^~-]+")
    return ", ".join(w if plain.fullmatch(w) else "'" + w.replace("'", "'\"'\"'") + "'" for w in words)


def _plain(said: str) -> bool:
    """Would this line, under a node, be read back as what the node should achieve? Else it is
    written after a `goal:`, which reads back as that whatever follows it."""
    marked = _MARK.fullmatch(said)
    if said.startswith(("#", "```")) or _key(said) or (marked and _key(marked["rest"], near=False)):
        return False
    try:
        return _node(said, 0) is None
    except P.Refused:
        return False


def clock(stamp: str | None) -> str:
    """A stored UTC time as the person's own clock, hours and minutes."""
    from datetime import datetime

    if not stamp:
        return ""
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
    except ValueError:
        return stamp[11:16]


def notes(store, node: P.Node, by_id: dict[str, P.Node], under: dict) -> list[str]:
    """What is true of the node right now, for the person reading its contract: its state, what it
    waits on, and why it came back. Written as "#" lines; never read back."""
    out: list[str] = []
    mine = under.get(node.id) or []
    if mine:
        leaves = [c for c in P.below(node.id, list(by_id.values())) if not under.get(c.id)]
        done = sum(1 for c in leaves if c.state == P.DONE)
        out.append(f"{done}/{len(leaves)} done" + ("" if node.state != P.DONE else "; done"))
        return out
    if node.state == P.PROPOSED:
        out.append(f"proposed by {node.proposed_by}")
    elif node.state == P.RUNNING:
        where = node.checkout or ""
        tree = f" in {where[where.index('.graphene') :]}" if ".graphene" in where else ""
        out.append(f"running: {node.executor} since {clock(node.started_at)}{tree}")
    elif node.state == P.REVIEW:
        out.append(f"its check passed; it waits for your sign-off (graphene node signoff {node.id})")
    elif node.state == P.DONE:
        out.append(f"done {clock(node.finished_at)}")
    elif node.state == P.OPEN:
        blockers = P.unmet(node, by_id)
        if blockers:
            out.append("waits on " + ", ".join(b.id for b in blockers))
        last = (store.node_log(node.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
        if last["kind"] == "released":
            out.append("handed back: " + " ".join(str(last["detail"].get("why", "")).split()))
            wanted = P.wanted(store, node)
            if wanted:
                out.append("it wanted, outside its scope: " + ", ".join(wanted))
        elif last["kind"] == "reopened":
            out.append("sent back: " + " ".join(str(last["detail"].get("note", "")).split()))
    return out


def render(store, root: str | None = None, alone: bool = False) -> tuple[str, dict[str, dict]]:
    """The text of the whole plan, of one subtree (``root``), or of one node without its children
    (``alone``). Returns the text and the nodes written into it, each as it was written: an edit
    applies to those and nothing else, only what the person changed in the text is changed, and a
    change to a node someone else changed meanwhile is refused rather than written over theirs."""
    alive = [n for n in P.nodes(store) if n.state not in P.GONE and not n.aside]
    by_id = {n.id: n for n in alive}
    under = P.kids(alive, drawn=True)
    lines: list[str] = []
    written: dict[str, dict] = {}
    goal, proposed = P.goal(store), store.meta("goal:proposed")
    shown = _norm_goal(goal or (proposed or "") if root is None else "")
    if root is None:
        lines += [f"goal: {line}" for line in shown]
        if proposed and not goal:
            lines.append("# proposed with the tree: accepting any of it accepts this")
        lines += [""] if shown else []
        written["*goal"] = {"goal": "\n".join(shown)}  # an id never has a star: the goal as it was shown
        tops = under.get(None, [])
    else:
        tops = [P.get(store, root)]
        if tops[0].state in P.GONE:
            raise P.Refused(f"{root} is {tops[0].state}; there is nothing of it to edit")
        lines += [f"# the plan: {line}" for line in _norm_goal(goal)] + ([""] if goal else [])

    def emit(n: P.Node, depth: int) -> None:
        pad, inner = "  " * depth, "  " * depth + "    "
        lines.append(f"{pad}{'?' if n.state == P.PROPOSED else '-'} {' '.join(n.title.split())}  [{n.id}]")
        written[n.id] = {"rev": n.rev, "parent": n.parent, "proposal": n.state == P.PROPOSED, **_stored(n)}
        lines.extend(f"{inner}# {note}" for note in notes(store, n, by_id, under))
        for said in _norm_goal(n.goal if n.goal != n.title else ""):
            lines.append(f"{inner}{said}" if _plain(said) else f"{inner}goal: {said}")
        if n.scope:
            lines.append(f"{inner}scope: {_globs(n.scope)}")
        if _norm_check(n.check):
            lines.append(f"{inner}check: {_norm_check(n.check)}")
        if n.needs:
            lines.append(f"{inner}needs: {', '.join(n.needs)}")
        if n.owner != P.AGENT:
            lines.append(f"{inner}owner: {n.owner}")
        if n.signoff:
            lines.append(f"{inner}signoff: yes")
        if not alone:
            for child in under.get(n.id, []):
                if not child.aside:
                    emit(child, depth + 1)

    for n in tops:
        emit(n, 0)
    return "\n".join(lines).rstrip() + "\n", written


# -- a text, applied --------------------------------------------------------------------------------


def slug(title: str, taken: set[str]) -> str:
    """A readable id from a title: it names the node's branch too (graphene/<id>)."""
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in _SMALL] or ["node"]
    base = "-".join(words[:3])[:24].strip("-") or "node"
    out, k = base, 2
    while out in taken:
        out, k = f"{base}-{k}", k + 1
    return out


def apply(
    store,
    text: str,
    who: P.Caller,
    opened: dict[str, dict] | None = None,
    base_parent: str | None = None,
    files: list[str] | None = None,
    now: str | None = None,
    alone: bool = False,
) -> Said:
    """Make the plan say what the text says. ``opened`` is what ``render`` wrote (an edit: a node
    it held that the text no longer has is dropped); None is a proposal (only new lines count, and
    a line with the id of a node already in the plan is where the new ones hang). ``alone``: the text
    held one node without its children. Returns one line per change made, for whoever applied it."""
    now = now or P._now()
    goal, lines = parse(text)
    if not lines and goal is None:
        raise P.Refused("the text has no node in it, so nothing was applied")
    everything = {n.id: n for n in P.nodes(store)}
    _ids(lines, everything, opened)
    taken = set(everything) | {ln.id for ln in lines if ln.id}
    for line in lines:
        if line.id is None:
            line.id = slug(line.title, taken)
            taken.add(line.id)
    parent_of = {ln.id: (lines[ln.parent].id if ln.parent is not None else base_parent) for ln in lines}
    fresh = [ln for ln in lines if ln.id not in everything]
    kept = [ln for ln in lines if ln.id in everything]
    _guard_shape(lines, fresh, everything, opened, parent_of, who)
    said = Said()
    with store.claim():
        said += _goal(store, goal, who, now, opened)
        if fresh:
            containers = {lines[ln.parent].id for ln in lines if ln.parent is not None}
            items = [{"id": ln.id, "parent": parent_of[ln.id], **_fields(ln)} for ln in fresh]
            try:
                added = P.propose(
                    store, items, who, now, files, proposals={ln.id for ln in fresh if ln.proposal},
                    containers=containers,
                )  # fmt: skip
            except P.Refused as no:
                raise _on_line(no, lines) from None
            for n in added:
                said.append(f"{'proposed' if n.state == P.PROPOSED else 'added'} {n.id}: {n.title}")
                said.ids.append(n.id)
        if opened is not None:
            edited = _edits(store, kept, parent_of, opened, who, now, files)
            said += edited
            said.ids += [line.split(":", 1)[0] for line in edited]
            said += _accepts(store, kept, opened, who, now)
            said += _drops(store, lines, opened, who, now, alone)
            said += _reorder(store, lines, who, now)
            if store.meta("goal:proposed") and not P.nodes(store, (P.PROPOSED,)):
                store.set_meta("goal:proposed", None)  # its tree is gone, so is the planner's sentence
        try:
            P.validate(P.nodes(store), set(said.ids))  # the tree as it is now, after every move
        except P.Refused as no:
            raise _on_line(no, lines) from None
    return said


def _ids(lines: list[Line], everything: dict[str, P.Node], opened: dict | None) -> None:
    seen: dict[str, int] = {}
    for line in lines:
        if line.id is None:
            continue
        if line.id in seen:
            raise P.Refused(
                f"line {line.no}: [{line.id}] is on line {seen[line.id]} too. An [id] at the end of a line "
                "names one node: take it off the copy and it is a new node, or give each its own"
            )
        seen[line.id] = line.no
        known = everything.get(line.id)
        if known is not None and known.state in P.GONE:
            since = opened is not None and line.id in opened
            raise P.Refused(
                f"line {line.no}: [{line.id}] was {known.state}"
                + (" since this text was opened; delete its line" if since else "; give this line another id")
            )
        if known is not None and opened is not None and line.id not in opened:
            raise P.Refused(
                f"line {line.no}: [{line.id}] is in the plan, but not in the part of it this text was "
                "opened on; edit a part of the tree that holds both"
            )


def _guard_shape(lines, fresh, everything, opened, parent_of, who) -> None:
    """What a text says that it probably did not mean, refused with how to say it."""
    by_index = {id(ln): k for k, ln in enumerate(lines)}
    for ln in fresh:
        parent = lines[ln.parent] if ln.parent is not None else None
        has_kids = any(other.parent == by_index[id(ln)] for other in lines)
        if parent and (parent.scope or parent.check) and not (ln.scope or ln.check or ln.signoff or has_kids):
            raise P.Refused(
                f"line {ln.no}: '{ln.title}' is a new node under [{parent.id}] with nothing to do: no scope "
                f"and no check. If it says what [{parent.id}] should achieve, write it without its '- '"
            )
        if not who.person and ln.owner not in (P.AGENT, "me", P.person_name()):
            raise P.Refused(
                f"line {ln.no}: owner: names a person, and '{ln.owner}' is not the person here. An agent's "
                "leaf has no owner: line; owner: me is the person"
            )
    if opened is None:
        for ln in lines:
            node = everything.get(ln.id)
            if node is None:
                continue
            differ = [k for k in ln.said if _fields(ln)[k] != _stored(node)[k]]
            if differ:
                raise P.Refused(
                    f"line {ln.no}: [{ln.id}] is in the plan already, and this text changes its "
                    f"{', '.join(differ)}. Only the person edits a contract (`graphene plan edit {ln.id}`); "
                    "write its line without them to put new lines under it"
                )
            if ln.parent is not None and parent_of[ln.id] != node.parent:
                raise P.Refused(
                    f"line {ln.no}: [{ln.id}] sits under {node.parent or 'the goal'} in the plan, not under "
                    f"{parent_of[ln.id]}; only the person moves a node"
                )
        return
    present = {ln.id for ln in lines}
    for k, ln in enumerate(lines):
        base = opened.get(ln.id)
        nxt = lines[k + 1] if k + 1 < len(lines) else None
        if base and nxt is not None and nxt.parent == k and nxt.id not in everything:
            # a new line typed right under an existing node's line takes the lines that were the
            # node's own when they sit where the node's own lines are written (four spaces in)
            empty = not (ln.scope or ln.check or ln.goal or ln.needs or ln.signoff or ln.owner != P.AGENT)
            was = base["scope"] or base["check"] or base["goal"] or base["needs"] or base["signoff"]
            if empty and was and nxt.column == ln.indent + 4:
                raise P.Refused(
                    f"line {nxt.no}: the new line sits between [{ln.id}] and [{ln.id}]'s own lines, so they "
                    "would become the new line's. Put it after them: a child goes after its parent's scope:, "
                    "check: and the rest"
                )
        if (
            base
            and base["parent"] != parent_of[ln.id]
            and base["parent"] in opened
            and base["parent"] not in present
        ):
            raise P.Refused(
                f"line {ln.no}: [{ln.id}]'s parent [{base['parent']}] was deleted, and [{ln.id}] would now "
                f"be under {parent_of[ln.id] or 'the goal'} only because of where its line sits. Delete it "
                "with its parent, or move it where it should go in a save of its own"
            )


def _goal(store, goal: str | None, who: P.Caller, now: str, opened: dict | None) -> list[str]:
    """The goal line, compared three ways as every node is: only a change the text makes counts, a
    planner's sentence stays a proposal until a node is accepted, and one set elsewhere meanwhile is
    never written over."""
    if goal is None:
        return []
    goal = "\n".join(_norm_goal(goal))
    if opened is not None:
        was = opened.get("*goal", {}).get("goal", "")
        if goal == was:
            return []
        now_shown = "\n".join(_norm_goal(P.goal(store) or store.meta("goal:proposed") or ""))
        if now_shown != was:
            raise P.Refused(
                "the plan's goal was changed by someone else since this text was opened; open it again"
            )
    if goal == "\n".join(_norm_goal(P.goal(store))):
        return []
    if who.person:
        P.set_goal(store, goal, who, now)
        return [f"goal: {goal}"]
    if P.propose_goal(store, goal, who, now):
        return [f"goal (proposed): {goal}"]
    return [f"the plan's goal is the person's and stays: {P.goal(store)}"]


class Said(list):
    """What an apply changed, one line each, for whoever applied it; ``ids``: the nodes it added or
    changed (their checks are looked at once more afterwards)."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []


def _at(line: Line, refusal: P.Refused) -> P.Refused:
    return P.Refused(f"line {line.no} [{line.id}]: {refusal}")


def _on_line(refusal: P.Refused, lines: list[Line]) -> P.Refused:
    """A refusal from the plan names a node, first; the person needs the line it is on."""
    said = str(refusal)
    first = re.match(r"([\w.-]+)[: ]", said)
    by_id = {line.id: line for line in lines if line.id}
    if first and first[1] in by_id:
        return _at(by_id[first[1]], refusal)
    for line in lines:
        if line.id and re.search(rf"(?<![\w.-]){re.escape(line.id)}(?![\w-])", said):
            return _at(line, refusal)
    return refusal


def _fields(line: Line) -> dict:
    return {
        "title": line.title,
        "goal": "\n".join(_norm_goal("\n".join(line.goal))),
        "scope": line.scope,
        "check": _norm_check(line.check),
        "needs": line.needs,
        "owner": line.owner,
        "signoff": line.signoff,
    }


def _stored(node: P.Node) -> dict:
    return {
        "title": " ".join(node.title.split()),
        "goal": "\n".join(_norm_goal(node.goal if node.goal != node.title else "")),
        "scope": list(node.scope),
        "check": _norm_check(node.check),
        "needs": list(node.needs),
        "owner": node.owner,
        "signoff": node.signoff,
    }


def _edits(store, kept, parent_of, opened, who, now, files) -> list[str]:
    """Only what the person changed in the text (against the text as it was opened) is changed; a
    node someone else changed since then is refused, never written over."""
    said = []
    for ln in kept:
        base = opened[ln.id]
        mine = {**_fields(ln), "parent": parent_of[ln.id]}
        changes = {k: v for k, v in mine.items() if v != base[k]}
        if not changes:
            continue
        if P.get(store, ln.id).rev != base["rev"]:
            raise P.Refused(
                f"line {ln.no}: [{ln.id}] was changed by someone else since this text was opened; "
                "open it again, and your change is made on what it says now"
            )
        if "parent" in changes:
            changes["parent"] = changes["parent"] or "none"
        try:
            P.edit(store, ln.id, changes, who, now, files, check=False)
        except P.Refused as no:
            raise _at(ln, no) from None
        moved = f"moved under {parent_of[ln.id] or 'the goal'}" if "parent" in changes else ""
        rest = [k for k in changes if k != "parent"]
        said.append(
            f"{ln.id}: " + "; ".join(filter(None, [moved, ", ".join(rest) + (" changed" if rest else "")]))
        )
    return said


def _accepts(store, kept, opened, who, now) -> list[str]:
    said = []
    for ln in kept:
        base = opened[ln.id]
        if base["proposal"] and not ln.proposal:
            if P.get(store, ln.id).state != P.PROPOSED:
                continue  # accepted meanwhile, or as the one above another: it is what the text says
            try:
                for n in P.accept(store, [ln.id], who, now, exact=True):
                    said.append(f"accepted {n.id}" + ("" if n.id == ln.id else f" (it is above {ln.id})"))
            except P.Refused as no:
                raise _at(ln, no) from None
        elif not base["proposal"] and ln.proposal:
            raise P.Refused(
                f"line {ln.no}: [{ln.id}] is in the plan already; a node does not go back to being a "
                "proposal (delete its lines to drop it)"
            )
    return said


def _drops(store, lines, opened, who, now, alone: bool) -> list[str]:
    """The nodes whose lines were deleted, dropped: what needs another is dropped first, so deleting
    both is one save; a node that moved on since the text was opened, or that has nodes under it the
    text did not show, is refused rather than dropped from under whoever holds it."""
    present = {ln.id for ln in lines}
    going = [i for i in opened if i != "*goal" and i not in present]
    everything = P.nodes(store)
    by_id = {n.id: n for n in everything}
    for node_id in going:
        node, base = by_id[node_id], opened[node_id]
        if node.state in P.GONE:
            continue
        unseen = [c.id for c in P.below(node_id, everything) if c.id not in opened and c.state not in P.GONE]
        if (
            node.rev != base["rev"]
            or (node.state == P.PROPOSED) != base["proposal"]
            or node.state == P.RUNNING
        ):
            raise P.Refused(
                f"[{node_id}], whose lines were deleted, changed since this text was opened (it is "
                f"{node.state} now); open it again"
            )
        if unseen:
            where = "the node you opened" if alone else "this text"
            raise P.Refused(
                f"[{node_id}], whose lines were deleted, has {', '.join(unseen[:5])} under it, which {where} "
                f"did not show; `graphene plan edit {node_id}` shows them, or `graphene node drop {node_id}`"
            )
    order = [n.id for n in reversed(P.order([by_id[i] for i in going]))]  # what needs another goes first
    said = []
    for node_id in order:
        node = P.get(store, node_id)
        if node.state in P.GONE:
            continue  # it went with the node it was under
        try:
            P.drop(store, node_id, who, now)
        except P.Refused as no:
            raise P.Refused(f"[{node_id}], whose lines were deleted: {no}") from None
        said.append(f"dropped {node_id}: {node.title}")
    return said


def _reorder(store, lines: list[Line], who, now) -> list[str]:
    """Siblings in the order the text writes them; nothing when no sibling moved."""
    seqs = store.node_seqs()
    moved = []
    groups: dict[int | None, list[str]] = {}
    for ln in lines:
        groups.setdefault(ln.parent, []).append(ln.id)
    for ids in groups.values():
        places = sorted(seqs[i] for i in ids)
        if [seqs[i] for i in ids] != places:
            for node_id, seq in zip(ids, places, strict=True):
                store.set_seq(node_id, seq)
            moved += ids
    if not moved:
        return []
    store.log_node("*", now, "reordered", who.label, who.session_id, None, {"order": moved})
    return ["reordered"]


# -- the editor ------------------------------------------------------------------------------------


def run_editor(path: Path) -> int:
    """The person's editor on the file, in this terminal: $VISUAL, then $EDITOR, then vi."""
    command = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    try:
        return subprocess.call([*shlex.split(command), str(path)])
    except (OSError, ValueError) as no:
        raise P.Refused(
            f"cannot run your editor ({command}): {getattr(no, 'strerror', None) or no}; set $EDITOR"
        ) from None


_REFUSED = "# ^ refused: "


def _annotated(text: str, refusal: str) -> str:
    """The person's text with the refusal written under the line it is about (numbered as they saw
    it), and the refusal of the save before taken out: they fix it where it is, in their editor."""
    lines = text.splitlines()
    found = re.match(r"line (\d+)(?: \[[^\]]*\])?: ", refusal)
    note = refusal[found.end() :] if found else refusal
    marked = [(line, False) for line in lines]
    at = min(int(found[1]), len(lines)) if found else 0
    indent = " " * (len(lines[at - 1]) - len(lines[at - 1].lstrip())) if found and at else ""
    marked.insert(at, (indent + _REFUSED + " ".join(note.split()), True))
    return "\n".join(line for line, new in marked if new or not line.lstrip().startswith(_REFUSED)) + "\n"


def edit_path(root: Path, node: str | None) -> Path:
    """A file of its own for each edit: two at once never read each other's, and a text kept after a
    refusal is never written over by the next edit."""
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / ".graphene" / "edits" / f"{node or 'plan'}-{stamp}-{os.getpid()}.txt"


def edit_loop(
    open_store: Callable,
    root: str | None,
    alone: bool,
    who: P.Caller,
    files: list[str],
    path: Path,
    where: str,
    editor: Callable[[Path], int] = run_editor,
    interactive: bool = True,
) -> Said:
    """Open the plan (or ``root``'s subtree, or ``root`` ``alone``) in the editor and apply what is
    saved. Refused, the text goes back to the editor with the reason under its line, until it
    applies or the person saves it unchanged (then nothing is applied and the text is kept at
    ``path``). A node someone changed meanwhile: the text is kept, and the next save is made on the
    plan as it is then. With no terminal there is no second look: the refusal ends it."""
    with open_store() as store:
        text, opened = render(store, root, alone)
        base = P.get(store, root).parent if root is not None else None
    head = f"# {where} · save and quit to apply; quit without saving to leave it as it is\n\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    shown = head + text + "\n" + HELP + "\n"
    path.write_text(shown, encoding="utf-8")
    first = True
    while True:
        code = editor(path)
        try:
            saved = path.read_text(encoding="utf-8")
        except OSError:
            raise P.Refused(f"{path} is gone; nothing was applied") from None
        if code != 0:
            raise P.Refused(f"the editor exited with {code}; nothing was applied (your text is in {path})")
        if saved == shown:
            if first:
                path.unlink(missing_ok=True)
                return Said()
            raise P.Refused(f"nothing was applied; your text is kept in {path}")
        try:
            with open_store() as store:
                with P.undoable(store, who, "plan edit" + (f" {root}" if root else "")):
                    said = apply(store, saved, who, opened, base, files, alone=alone)
        except P.Refused as no:
            if not interactive:
                raise P.Refused(f"{no}. Nothing was applied; your text is kept in {path}") from None
            refusal = str(no)
            if "changed by someone else" in refusal:
                with open_store() as store:  # the next save is made on the plan as it is now
                    opened = render(store, root, alone)[1]
                refusal += (
                    " (it now says what `graphene plan --text` shows; save again to make your change on that)"
                )
            shown = _annotated(saved, refusal)
            path.write_text(shown, encoding="utf-8")
            first = False
            continue
        path.unlink(missing_ok=True)
        return said
