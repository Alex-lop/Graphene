"""The board as rows of the outline: one screen, the board above the tree.

Directly under the goal and before the first sub-goal, each open item on the board is one row in the
one row grammar (glyph and colour from ``board.look``, its words cut at a word, its id, and its kind
as a verb: asks, assumes, risk, leaves out, note), in the order ``board.groups`` gives, questions
first. What is settled, parked or dropped folds into one row (`✓ 3 settled · 1 parked`), opened with
za or zo like a sub-goal. The screen opens on the first open item, so the person meets the questions
before the tree; j and k walk from the last item into the tree.

A key on an item answers it with the `graphene board` command a person could type (y take, 1..9
pick, d drop, p park or unpark, Enter answer, a note); on a node the same keys keep their tree
meaning. This module says what the rows, the pane and the key hints are; `tui.Watch` wires them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.text import Text

from . import board as B
from . import plan as P
from . import plan_text as T
from . import settings as S


@dataclass(frozen=True)
class Row:
    """A board row's data in the tree, told apart from a node's id: an item, the fold, or the line
    of standing conditions."""

    kind: str  # "item", "fold" or "standing"
    id: str = ""


FOLD, STANDING = Row("fold"), Row("standing")
VERB = {"question": "asks", "assume": "assumes", "risk": "risk", "leave out": "leaves out", "note": "note"}
KIND = {
    "question": "question",
    "assume": "assumption",
    "risk": "risk",
    "leave out": "left out",
    "note": "note",
}
YES = {
    "question": "y yes",
    "assume": "y confirm",
    "risk": "y noted",
    "leave out": "y agree",
    "note": "y take",
}
# each word an item row can read as, in the plan's own colours (whose move): open is the person's,
# settled is done, parked and dropped are nobody's; the fold row has no word, so its glyph says it
LOOK = {
    **{verb: P.LOOK["yours"] for verb in VERB.values()},
    **{state: P.LOOK["done"] for state in (*B.DECIDED, "noted")},
    "parked": P.LOOK["waiting"], "dropped": P.LOOK["waiting"],
    "✓": P.LOOK["done"], "◌": P.LOOK["waiting"],
}  # fmt: skip


@dataclass
class Board:
    """The board as the screen last read it: the open items in display order, what folds, and the
    one line of standing conditions."""

    open: list[dict] = field(default_factory=list)
    folded: list[dict] = field(default_factory=list)
    standing: str | None = None

    def __bool__(self) -> bool:
        return bool(self.open or self.folded or self.standing)

    def get(self, row) -> dict | None:
        if not isinstance(row, Row) or row.kind != "item":
            return None
        return next((it for it in [*self.open, *self.folded] if it["id"] == row.id), None)

    def shape(self) -> list[tuple]:
        """What the tree is built from, for `Watch.draw` to tell when to build it again."""
        return [("board", it["id"], it["state"], it["rev"]) for it in [*self.open, *self.folded]] + (
            [("standing", self.standing)] if self.standing else []
        )


def standing(store) -> str | None:
    """The one line the standing conditions (`graphene config`, settings a person states once) say at
    the board's root and on a view's goal line: `conditions: protected secrets/** · read-only vendor/**
    · never add a dependency`. None when there are none."""
    said = [f"protected {', '.join(S.protected(store))}"] if S.protected(store) else []
    said += [f"read-only {', '.join(S.readonly(store))}"] if S.readonly(store) else []
    said += [f"never {n}" for n in S.never(store)]
    return "conditions: " + " · ".join(said) if said else None


def read(store, shown: bool = False) -> Board:
    """The board as the screen shows it. When it asks nothing (``board.asks``: nothing open, or with
    `board: auto` no question open) there is no board at all, only the standing conditions, unless its
    rows are ``shown`` already: then what was answered here folds, so a key pressed once too often
    lands on the fold and not on a node."""
    if not (shown or B.asks(store)):
        return Board(standing=standing(store))
    groups = B.groups(store)
    folds = ("parked", "settled", "dropped")
    return Board(
        [it for name, group in groups if name not in folds for it in group],
        [it for name, group in groups if name in folds for it in group],
        standing(store),
    )


def word(item: dict) -> str:
    """The word in an item's row: its kind as a verb while it is open, else its state."""
    said = B.reads(item)
    return VERB[item["kind"]] if said == "open" else said


def counts(board: Board) -> str:
    """The fold row's words: `3 settled · 1 parked · 1 dropped`."""
    states = [B.reads(it) for it in board.folded]
    settled = sum(s not in ("parked", "dropped") for s in states)
    said = [f"{settled} settled"] if settled else []
    return " · ".join(said + [f"{states.count(s)} {s}" for s in ("parked", "dropped") if s in states])


def rows(board: Board) -> dict:
    """Each board row's cells, as `Watch.relabel` keeps a node's: (glyph, word, title, id, bold,
    inside). The fold row and the standing row have no id and no word."""
    out = {Row("item", it["id"]): (B.look(it)[0], word(it), it["text"], it["id"], False, "")
           for it in [*board.open, *board.folded]}  # fmt: skip
    if board.folded:
        glyph = "✓" if any(B.reads(it) not in ("parked", "dropped") for it in board.folded) else "◌"
        out[FOLD] = (glyph, "", counts(board), "", False, "")
    if board.standing:
        out[STANDING] = ("◌", "", board.standing, "", False, "")
    return out


def widths(board: Board) -> list[int]:
    """The columns each board row's words want, as `Watch.size_panes` counts a node's."""
    return [6 + len(it["text"]) for it in [*board.open, *board.folded]]


def goal(text: str, board: Board) -> str:
    """The goal line of a view other than the outline (tree, graph): how many items on the board
    wait on the person, then the standing conditions, first, so a cut goal never hides them."""
    n = len(board.open)
    return " · ".join([*([f"◇ {n} open on the board"] if n else []), *filter(None, [board.standing]), text])


def landing(was: list[str], board: Board, at, fresh: bool):
    """Where the cursor goes when the board changed: onto the first open item when there were none
    and the cursor is on the goal (or the screen just opened); after an item under the cursor is
    answered, onto the next open one, and after the last, onto the settled fold, where y and a mean
    what they meant on the board a moment ago (on a proposed node y accepts it, and a adds a node),
    or into the tree (``TREE``) when nothing folded. None: it stays."""
    now = [it["id"] for it in board.open]
    if now and not was and fresh:
        return Row("item", now[0])
    if isinstance(at, Row) and at.kind == "item" and at.id in was and at.id not in now:
        rest = [i for i in was[was.index(at.id) + 1 :] if i in now] + now
        return Row("item", rest[0]) if rest else (FOLD if board.folded else TREE)
    return None


TREE = Row("tree")  # `landing`'s word for the first row of the tree itself


# -- keys -----------------------------------------------------------------------------------------


def argv(item: dict, key: str) -> list[str]:
    """The `graphene board` command a key runs on an item: y take, 1..9 pick, d drop, p park (on a
    parked item, unpark). A command that cannot apply says why, as the command line would."""
    parked = item["state"] == "parked" or bool(item.get("from"))  # p opens either for the person again
    return {
        "y": ["board", "take", item["id"]],
        "d": ["board", "drop", item["id"]],
        "p": ["board", "unpark" if parked else "park", item["id"]],
    }.get(key) or ["board", "pick", item["id"], key]


def hints(item: dict, room: int) -> list[str]:
    """The bottom line on an item: what each key would do HERE, in words, every key kept in sight at
    80 columns (the default's and the options' words give way first)."""
    state = B.reads(item)
    if state == "dropped":
        return ["dropped: u undoes it if it was your last act", "a note"]
    rest = ["d drop", "p unpark" if state == "parked" else "p park", "Enter answer", "a note"]
    if state == "noted":  # the person's own note: told as written, so there is nothing to take or answer
        return ["noted: u undoes your last act", "d drop", "p park", "a note"]
    if item.get("from"):  # the repository answered it: one key gives it back to the person
        return [f"{state} from the repo: p asks you", "d drop", "a note"]
    if state not in ("open", "parked"):
        return [f"{state}: u undoes your last act", "d drop", "a note"]
    many = len(item["options"]) > 3
    choices = [("y take", item["default"])] if item["default"] else [(YES[item["kind"]], "")]
    choices += (
        [(f"1-{len(item['options'])} pick", "")]
        if many
        else [(f"{k} pick", o["text"]) for k, o in enumerate(item["options"], 1)]
    )
    left = room - sum(len(r) + 3 for r in rest) - sum(len(k) + 3 for k, _ in choices)
    worded = [k for k, w in choices if w]
    each = left // max(len(worded), 1) - 2
    if each < 12 and worded:  # too little for every choice's words: the first choice's alone
        worded, each = worded[:1], left - 2
    return [f"{k}: {T.elide(w, each)}" if k in worded and each >= 8 else k for k, w in choices] + rest


# -- the side pane --------------------------------------------------------------------------------


def pane(board: Board, row: Row, by_id: dict, wide: int) -> Text:
    """The item under the cursor, whole: its words, its kind, who put it up, its default and each
    option with its effects, what it is about; settled, what was decided and what it changed. On the
    fold row, what was decided, one line each."""
    from .tui import Pane

    out = Pane(wide)
    if row == STANDING:
        out.text(board.standing or "", "bold")
        out.text("standing conditions: every plan runs under them (graphene config)", "dim")
        return out.render()
    if row == FOLD:
        out.text(f"the board: {counts(board)}", "bold")
        out.text("told to executors as decided: lines; parked and dropped are told to no one", "dim")
        out.gap()
        for it in board.folded:
            glyph, colour = B.look(it)
            out.text(Text.assemble((f"{glyph} {B.reads(it)} ", colour), (it["id"], "dim"), f"  {B.said(it)}"))
        return out.render()
    item = board.get(row)
    if item is None:
        return out.render()
    state = B.reads(item)
    out.text(item["text"], "bold")
    head = Text.assemble((item["id"], "dim"), f" · {KIND[item['kind']]} · ", (state, B.look(item)[1]))
    out.text(head.append(f" · put up by {P.said_by(item['by'])}"))
    out.gap()
    if state not in ("open", "parked"):  # what was decided first: it is what executors are told
        if item.get("answer") or state in B.DECIDED:
            how = {"taken": "the default", "picked": f"option {item.get('option')}", "answered": "your words"}
            how = f"  ({how.get(state, state)})"
            out.field("decided", Text.assemble(item.get("answer") or "yes", (how, "dim")))
        if item.get("from"):
            out.field("from the repo", Text.assemble(item["from"], ("  p asks you instead", "dim")))
        for line in item["became"] if state in B.DECIDED else []:
            out.field("changed", line)
        node = by_id.get(item.get("about") or "")
        whom = f"the executors of {item['about']} and under it" if item.get("about") else "every executor"
        told = f"to {whom}, as a decided: line" if B.told(item) else "to no one"
        if item.get("about") and (node is None or node.state in P.GONE):
            told = (
                f"to no one: {item['about']} has left the plan (`graphene plan edit` gives it another about:)"
            )
        out.field("told", told)
        out.gap()
    if item["default"] or item["then"]:
        key = "y default" if state in ("open", "parked") else "default"
        out.field(key, _then(item["default"] or "yes", item["then"]))
    for k, option in enumerate(item["options"], 1):
        out.field(str(k), _then(option["text"], option["then"]))
    if item.get("about"):
        node = by_id.get(item["about"])
        out.field("about", Text.assemble(item["about"], (f"  {node.title}" if node else "", "dim")))
    return out.render()


def _then(said: str, effects: list[str]) -> Text:
    return Text("\n").join([Text(said), *(Text(f"then: {e}", "dim") for e in effects)])
