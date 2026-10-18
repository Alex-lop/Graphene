"""How things look: the names agents go by, their colours, the glyph of each state, a task's short name."""

from __future__ import annotations

import hashlib
import re

NAMES = [
    "fox", "oak", "river", "bee", "crab", "hen", "elm", "ant", "owl", "ivy", "jay", "koi", "lynx", "moth",
    "newt", "otter", "pine", "quail", "reed", "seal", "tern", "vole", "wren", "yak", "zebu", "dove",
]  # fmt: skip
PALETTE = [
    "#f4a261", "#8ab17d", "#5fa8d3", "#e9c46a", "#e76f51", "#c77dff", "#2a9d8f", "#ef476f", "#90be6d",
    "#4cc9f0", "#f9c74f", "#b5838d", "#43aa8b", "#f3722c", "#577590", "#bc6c25",
]  # fmt: skip
SPARK = "▁▂▃▄▅▆▇█"

STATE_GLYPH = {
    "running": ("●", "bold #e9c46a"), "review": ("◆", "bold #c77dff"), "came back": ("↩", "bold #ef476f"),
    "ready": ("○", "#d0d0d0"), "waiting": ("◌", "grey50"),
    "proposed": ("?", "#4cc9f0"), "done": ("✓", "#8ab17d"), "yours": ("◇", "bold #c77dff"),
}  # fmt: skip
FLOW_STYLES = {
    "running": "bold #e9c46a", "done": "#8ab17d", "review": "bold #c77dff", "came back": "bold #ef476f",
    "ready": "#d0d0d0", "waiting": "grey50", "proposed": "#4cc9f0", "yours": "bold #c77dff", "edge": "grey42",
    "edge_hot": "bold #4cc9f0",
    "node_sel": "bold #ffffff", "plain": "grey62", "label:plain": "#d8dee9",
    "node": "grey70",
    "label:running": "bold", "label:done": "grey62", "label:waiting": "grey58", "edge_loop": "#e9a23b",
    "glyph:running": "●", "glyph:done": "✓", "glyph:review": "◆", "glyph:came back": "↩", "glyph:ready": "○",
    "glyph:waiting": "◌", "glyph:proposed": "?",
}  # fmt: skip


def name_for(key: str, taken: set[str]) -> str:
    """A stable name for an agent from a key (its session): the same key, the same name, and never one
    another running agent has while there is a free one."""
    start = int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(NAMES)
    for k in range(len(NAMES)):
        name = NAMES[(start + k) % len(NAMES)]
        if name not in taken:
            return name
    return NAMES[start]


def color_of(name: str) -> str:
    return PALETTE[NAMES.index(name) % len(PALETTE)] if name in NAMES else "white"


TRAILING = {"a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "so", "as", "by"}


def short(title: str, words: int = 5) -> str:
    """A glanceable name for a sentence-long title: what comes before a colon, a semicolon or a dash,
    without a leading article, at most ``words`` words, and never ending on a word that wants another
    ("Add an XML reader and" is "Add an XML reader"). A plan's titles are sentences; a screen with almost
    no text needs a name."""
    head = re.split(r"[:;]|\s[-–—]\s", title, maxsplit=1)[0].strip()
    parts = head.split()
    if parts and parts[0].lower() in ("the", "a", "an"):
        parts = parts[1:]
    parts = parts[:words]
    while len(parts) > 1 and parts[-1].lower().strip(",.") in TRAILING:
        parts.pop()
    return " ".join(parts) or title
