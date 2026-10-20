"""What every screen is built from: a line is a list of styled segments, and a segment may carry an action.

No Textual in here. A `build_*` function takes the model and a width and returns lines; a widget paints
them and turns a click on a segment into that segment's action, so the words on a row are its buttons, and a
test can print a frame or press a segment without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.cells import cell_len, set_cell_size


@dataclass
class Seg:
    text: str
    style: str = ""
    action: str = ""  # "take", "tell", "select:ids", "pick:1", "group:3"...: what a click on it does


@dataclass
class Line:
    segs: list[Seg] = field(default_factory=list)
    row: str = ""  # the model row this line belongs to (a task or a question id)

    def plain(self) -> str:
        return "".join(s.text for s in self.segs)

    def width(self) -> int:
        return span(self.segs)


def span(segs: list[Seg]) -> int:
    """Terminal cells the segments take: a CJK character or an emoji is two, so it is not `len`."""
    return sum(cell_len(s.text) for s in segs)


def seg_at(line: Line, x: int) -> Seg | None:
    at = 0
    for s in line.segs:
        if at <= x < at + cell_len(s.text):
            return s
        at += cell_len(s.text)
    return None


def pad(segs: list[Seg], width: int, style: str = "") -> list[Seg]:
    used = span(segs)
    return segs + ([Seg(" " * (width - used), style)] if used < width else [])


def ljust(text: str, width: int) -> str:
    """`str.ljust` in cells."""
    return text + " " * (width - cell_len(text))


def fit(text: str, width: int) -> str:
    """The text in ``width`` cells: whole, or cut and ending in an ellipsis."""
    if cell_len(text) <= width:
        return text
    return set_cell_size(text, max(width - 1, 0)).rstrip() + "…"


def fit_end(text: str, width: int) -> str:
    """The end of the text in ``width`` cells, with an ellipsis in front: a folder keeps its last part."""
    if cell_len(text) <= width:
        return text
    kept, used = "", 1
    for ch in reversed(text):
        if used + cell_len(ch) > width:
            break
        kept, used = ch + kept, used + cell_len(ch)
    return "…" + kept


def ago(seconds: float) -> str:
    return f"{int(seconds)}s" if seconds < 90 else f"{int(seconds // 60)}m"


def fit_keys(keys: str, width: int) -> str:
    """The keys line in the room there is: whole keys from the left, and the ones that say how to get help and
    how to leave (`? keys`, `q`, `Esc back`) always, so a narrow terminal still says both. `f fork` gives
    way first: a row's bar fit 80 columns before it, and `?` says it."""
    if len(keys) <= width:
        return keys
    pieces = keys.split(" · ")
    tail = [p for p in pieces if p.startswith("? ") or p in ("q", "q quit", "Esc back")][-2:]
    head = [p for p in pieces if p not in tail]
    while head and len(" · ".join([*head, *tail])) > width:
        head.remove("f fork" if "f fork" in head else head[-1])
    return " · ".join([*head, *tail])[:width]
