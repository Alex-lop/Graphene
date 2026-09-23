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
_NODE = re.compile(r"(?P<mark>[-*+?])\s+(?P<rest>.*)")
_ID = re.compile(r"\s+\[(?P<id>[A-Za-z0-9][\w.-]{0,31})\]\s*$")
_KEY = re.compile(rf"(?P<key>{'|'.join(KEYS)})\s*:(?P<value>.*)", re.IGNORECASE)
_YES, _NO = ("yes", "y", "true", "on"), ("no", "n", "false", "off", "")
_SMALL = {"the", "a", "an", "of", "to", "for", "and", "in", "on", "with", "as", "is", "be"}
HELP = """\
# "-" is a node in the plan, "?" a proposal: make it "-" to accept it. Indent a line under another
# to put it there; delete a line to drop that node, with what is under it; reorder lines to reorder.
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


def _words(value: str, no: int) -> list[str]:
    try:
        return [w for w in shlex.split(value.replace(",", " ")) if w]
    except ValueError as exc:
        raise P.Refused(f"line {no}: {exc} (quote a path with a space in it, and close the quote)") from None


def parse(text: str) -> tuple[str | None, list[Line]]:
    """The plan's goal (a `goal:` line at the left edge) and the node lines, in order. Refuses the
    first line it cannot read, by its number."""
    goal: str | None = None
    lines: list[Line] = []
    stack: list[int] = []  # indexes into lines, the node lines still open for children
    for no, raw in enumerate(text.splitlines(), 1):
        row = raw.expandtabs(4).rstrip()
        body = row.lstrip()
        indent = len(row) - len(body)
        if not body or body.startswith("#"):
            continue
        node = _NODE.fullmatch(body)
        if node:
            rest = node["rest"]
            ident = _ID.search(" " + rest)
            title = (" " + rest)[: ident.start()].strip() if ident else rest.strip()
            if not title:
                raise P.Refused(f"line {no}: a node needs a title after its '{node['mark']}'")
            while stack and lines[stack[-1]].indent >= indent:
                stack.pop()
            lines.append(
                Line(
                    no,
                    indent,
                    ident["id"] if ident else None,
                    node["mark"] == "?",
                    title,
                    stack[-1] if stack else None,
                )  # fmt: skip
            )
            stack.append(len(lines) - 1)
            continue
        owner = next((k for k in reversed(stack) if lines[k].indent < indent), None)
        key = _KEY.fullmatch(body)
        if owner is None:
            if key and key["key"].lower() == "goal" and indent == 0:
                goal = " ".join(filter(None, [goal, key["value"].strip()]))
                continue
            raise P.Refused(
                f"line {no}: {body[:40]!r} is not under a node. A node's line starts with '- ' (or '? ' "
                "for a proposal); its scope:, check: and what it should achieve go indented under it"
            )
        ln = lines[owner]
        if not key:
            ln.goal.append(body)
            continue
        name, value = key["key"].lower(), key["value"].strip()
        if name == "scope":
            ln.scope += _words(value, no)
        elif name == "needs":
            ln.needs += [w for w in _words(value, no) if w != "none"]
        elif name == "check":
            if ln.check is not None:
                raise P.Refused(f"line {no}: [{ln.id or ln.title}] has a check already; join them with &&")
            ln.check = value or None
        elif name == "owner":
            ln.owner = value or P.AGENT
        elif name == "signoff":
            if value.lower() not in (*_YES, *_NO):
                raise P.Refused(f"line {no}: signoff is yes or no, not {value!r}")
            ln.signoff = value.lower() in _YES
        else:
            ln.goal.append(value)
        ln.said.add(name)
    return goal, lines


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
    return ", ".join(w if re.fullmatch(r"[^\s,'\"]+", w) else shlex.quote(w) for w in words)


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
    if root is None:
        goal, proposed = P.goal(store), store.meta("goal:proposed")
        if proposed and not goal:
            lines += [f"goal: {proposed}", "# proposed with the tree: accepting any of it accepts this", ""]
        elif goal:
            lines += [f"goal: {goal}", ""]
        tops = under.get(None, [])
    else:
        tops = [P.get(store, root)]
        if P.goal(store):
            lines += [f"# the plan: {P.goal(store)}", ""]

    def emit(n: P.Node, depth: int) -> None:
        pad, inner = "  " * depth, "  " * depth + "    "
        lines.append(f"{pad}{'?' if n.state == P.PROPOSED else '-'} {' '.join(n.title.split())}  [{n.id}]")
        written[n.id] = {"rev": n.rev, "parent": n.parent, "proposal": n.state == P.PROPOSED, **_stored(n)}
        lines.extend(f"{inner}# {note}" for note in notes(store, n, by_id, under))
        for said in _norm_goal(n.goal if n.goal != n.title else ""):
            plain = not (_NODE.fullmatch(said) or _KEY.fullmatch(said) or said.startswith("#"))
            lines.append(f"{inner}{said}" if plain else f"{inner}goal: {said}")
        if n.scope:
            lines.append(f"{inner}scope: {_globs(n.scope)}")
        if n.check:
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


class Said(list):
    """What an apply changed, one line each, for whoever applied it; ``ids``: the nodes it added or
    changed (their checks are looked at once more afterwards)."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []


def _at(line: Line, refusal: P.Refused) -> P.Refused:
    return P.Refused(f"line {line.no} [{line.id}]: {refusal}")


def _on_line(refusal: P.Refused, lines: list[Line]) -> P.Refused:
    """A refusal from the plan names a node; the person needs the line it is on."""
    said = str(refusal)
    for line in lines:
        if line.id and re.search(rf"(?<![\w.-]){re.escape(line.id)}(?![\w-])", said):
            return _at(line, refusal)
    return refusal


def _fields(line: Line) -> dict:
    return {
        "title": line.title,
        "goal": "\n".join(line.goal),
        "scope": line.scope,
        "check": line.check,
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


def apply(
    store,
    text: str,
    who: P.Caller,
    opened: dict[str, dict] | None = None,
    base_parent: str | None = None,
    files: list[str] | None = None,
    now: str | None = None,
) -> list[str]:
    """Make the plan say what the text says. ``opened`` is what ``render`` wrote (an edit: a node
    it held that the text no longer has is dropped); None is a proposal (only new lines count, and
    a line with the id of a node already in the plan is where the new ones hang). Returns one line
    per change made, for whoever applied it."""
    now = now or P._now()
    goal, lines = parse(text)
    if not lines and goal is None:
        raise P.Refused("the text has no node in it, so nothing was applied")
    everything = {n.id: n for n in P.nodes(store)}
    seen: dict[str, int] = {}
    for line in lines:
        if line.id is None:
            continue
        if line.id in seen:
            raise P.Refused(
                f"line {line.no}: [{line.id}] is on line {seen[line.id]} too. A copied line keeps its "
                "id; take the [id] off the copy and it is a new node"
            )
        seen[line.id] = line.no
        known = everything.get(line.id)
        if known is not None and known.state in P.GONE:
            raise P.Refused(
                f"line {line.no}: [{line.id}] was {known.state}; give this line another id, or none"
            )
        if known is not None and opened is not None and line.id not in opened:
            raise P.Refused(
                f"line {line.no}: [{line.id}] is in the plan, but not in the part of it this text was "
                "opened on; edit a part of the tree that holds both"
            )
    taken = set(everything) | set(seen)
    for line in lines:
        if line.id is None:
            line.id = slug(line.title, taken)
            taken.add(line.id)
    ids = [line.id for line in lines]
    parent_of = {ln.id: (lines[ln.parent].id if ln.parent is not None else base_parent) for ln in lines}
    fresh = [ln for ln in lines if ln.id not in everything]
    kept = [ln for ln in lines if ln.id in everything]
    said = Said()

    if opened is not None:
        for k, ln in enumerate(lines[:-1]):
            nxt, base = lines[k + 1], opened.get(ln.id)
            stole = nxt.parent == k and nxt.id not in everything and (nxt.scope or nxt.check)
            if base and (base["scope"] or base["check"]) and not (ln.scope or ln.check or ln.goal) and stole:
                raise P.Refused(
                    f"line {nxt.no}: the new line sits between [{ln.id}] and [{ln.id}]'s own lines, so "
                    "they would become the new line's. Put it after them (a child goes after its parent's "
                    "scope:, check: and the rest)"
                )
    if opened is None:  # a proposal: what is in the plan already is where the new lines hang
        for ln in kept:
            node = everything[ln.id]
            differ = [k for k in ln.said if _fields(ln)[k] != _stored(node)[k]]
            if differ or ln.goal and "goal" not in ln.said and _fields(ln)["goal"] != _stored(node)["goal"]:
                raise P.Refused(
                    f"line {ln.no}: [{ln.id}] is in the plan already, and this text changes its "
                    f"{', '.join(differ) or 'goal'}. Only the person edits a contract (`graphene plan edit "
                    f"{ln.id}`); write its line without them to put new lines under it"
                )
            text_parent = parent_of[ln.id]
            if ln.parent is not None and text_parent != node.parent:
                raise P.Refused(
                    f"line {ln.no}: [{ln.id}] sits under {node.parent or 'the goal'} in the plan, not under "
                    f"{text_parent}; only the person moves a node"
                )

    with store.claim():
        if goal is not None and goal != P.goal(store):
            if who.person:
                P.set_goal(store, goal, who, now)
                said.append(f"goal: {goal}")
            elif P.propose_goal(store, goal, who, now):
                said.append(f"goal (proposed): {goal}")
            else:
                said.append(f"the plan's goal is the person's and stays: {P.goal(store)}")
        if fresh:
            items = [{"id": ln.id, "parent": parent_of[ln.id], **_fields(ln)} for ln in fresh]
            try:
                added = P.propose(
                    store, items, who, now, files, proposals={ln.id for ln in fresh if ln.proposal}
                )
            except P.Refused as no:
                raise _on_line(no, lines) from None
            for n in added:
                said.append(f"{'proposed' if n.state == P.PROPOSED else 'added'} {n.id}: {n.title}")
                said.ids.append(n.id)
        if opened is not None:
            edited = _edits(store, kept, everything, parent_of, opened, who, now, files)
            said += edited
            said.ids += [line.split(":", 1)[0] for line in edited]
            said += _accepts(store, kept, opened, who, now)
            said += _drops(store, lines, opened, who, now)
            said += _reorder(store, ids, who, now)
    return said


def _edits(store, kept, everything, parent_of, opened, who, now, files) -> list[str]:
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
            P.edit(store, ln.id, changes, who, now, files)
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
                "proposal (delete its line to drop it)"
            )
    return said


def _drops(store, lines, opened, who, now) -> list[str]:
    said = []
    present = {ln.id for ln in lines}
    for node_id in opened:
        if node_id in present:
            continue
        node = P.get(store, node_id)
        if node.state in P.GONE:
            continue  # it went with the node it was under
        try:
            P.drop(store, node_id, who, now)
        except P.Refused as no:
            raise P.Refused(f"[{node_id}], whose line was deleted: {no}") from None
        said.append(f"dropped {node_id}: {node.title}")
    return said


def _reorder(store, ids: list[str], who, now) -> list[str]:
    seqs = store.node_seqs()
    places = sorted(seqs[i] for i in ids)
    if [seqs[i] for i in ids] == places:
        return []
    for node_id, seq in zip(ids, places, strict=True):
        store.set_seq(node_id, seq)
    store.log_node("*", now, "reordered", who.label, who.session_id, None, {"order": ids})
    return ["reordered"]


# -- the editor ------------------------------------------------------------------------------------


def run_editor(path: Path) -> int:
    """The person's editor on the file, in this terminal: $VISUAL, then $EDITOR, then vi."""
    command = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    return subprocess.call([*shlex.split(command), str(path)])


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
    ``path``). With no terminal there is no second look: the refusal ends it."""
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
        saved = path.read_text(encoding="utf-8")
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
                    said = apply(store, saved, who, opened, base, files)
        except P.Refused as no:
            if not interactive:
                raise P.Refused(f"{no}. Nothing was applied; your text is kept in {path}") from None
            shown = _annotated(saved, str(no))
            path.write_text(shown, encoding="utf-8")
            first = False
            continue
        path.unlink(missing_ok=True)
        return said
