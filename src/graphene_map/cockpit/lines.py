"""What every screen is built from: a line is a list of styled segments, and a segment may carry an action.

No Textual in here. A `build_*` function takes the model and a width and returns lines; a widget paints
them and turns a click on a segment into that segment's action, so the words on a row are its buttons, and a
test can print a frame or press a segment without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Seg:
    text: str
    style: str = ""
    action: str = ""  # "take", "tell", "select:fox", "pick:1", "group:3"...: what a click on it does


@dataclass
class Line:
    segs: list[Seg] = field(default_factory=list)
    row: str = ""  # the model row this line belongs to (a task or a question id)

    def plain(self) -> str:
        return "".join(s.text for s in self.segs)

    def width(self) -> int:
        return sum(len(s.text) for s in self.segs)


def seg_at(line: Line, x: int) -> Seg | None:
    at = 0
    for s in line.segs:
        if at <= x < at + len(s.text):
            return s
        at += len(s.text)
    return None


def pad(segs: list[Seg], width: int, style: str = "") -> list[Seg]:
    used = sum(len(s.text) for s in segs)
    return segs + ([Seg(" " * (width - used), style)] if used < width else [])


def fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)] + "…"


def ago(seconds: float) -> str:
    return f"{int(seconds)}s" if seconds < 90 else f"{int(seconds // 60)}m"
