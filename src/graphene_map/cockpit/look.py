"""How things look: the number an agent goes by, its colour, the glyph of each state, a task's short name."""

from __future__ import annotations

import re

# an agent's colour says which agent, never how it is going: blues, slates, mauve, pink and brown, none of
# them a state's (proven green, running amber, need-you purple, came-back red, proposal cyan), each one
# at least 4.5:1 on the screen's background and on the selected row's
PALETTE = ["#5b8fd4", "#d291bc", "#a3826a", "#a7b4e8", "#b5838d", "#7a9e9f", "#8d99ae", "#8c86d4"]
SPARK = "▁▂▃▄▅▆▇█"

STATE_GLYPH = {
    "running": ("●", "bold #e9c46a"), "review": ("◆", "bold #c77dff"), "came back": ("↩", "bold #ef476f"),
    "ready": ("○", "#d0d0d0"), "waiting": ("◌", "grey50"),
    "proposed": ("+", "#4cc9f0"), "done": ("✓", "#8ab17d"), "yours": ("◇", "bold #c77dff"),
}  # fmt: skip
FLOW_STYLES = {
    "running": "bold #e9c46a", "done": "#8ab17d", "review": "bold #c77dff", "came back": "bold #ef476f",
    "ready": "#d0d0d0", "waiting": "grey50", "proposed": "#4cc9f0", "yours": "bold #c77dff", "edge": "grey42",
    "edge_hot": "bold #4cc9f0",
    "node_sel": "bold #ffffff", "plain": "grey62", "label:plain": "#d8dee9",
    "node": "grey70",
    "label:running": "bold", "label:done": "grey62", "label:waiting": "grey58", "edge_loop": "#e9a23b",
    "glyph:running": "●", "glyph:done": "✓", "glyph:review": "◆", "glyph:came back": "↩", "glyph:ready": "○",
    "glyph:waiting": "◌", "glyph:proposed": "+",
}  # fmt: skip


def color_of(agent: str) -> str:
    """An agent's colour, from its number: agent 1 takes the palette's first, agent 2 the next."""
    return PALETTE[(int(agent) - 1) % len(PALETTE)] if agent.isdigit() and agent != "0" else "white"


def who(agent: str) -> str:
    """How the screen names an agent in words: "agent 2". Agents go by numbers, in the order they took
    their first leaf of the plan, so "agent 2 is stuck" is sayable and says which one started second."""
    return f"agent {agent}" if agent else ""


TRAILING = {"a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "so", "as", "by"}


def short(title: str, words: int = 5) -> str:
    """A glanceable name for a sentence-long title: what comes before a colon, a semicolon or a dash,
    without a leading article, at most ``words`` words (0: as many as it has; a row has the room a box on
    the graph has not), and never ending on a word that wants another ("Add an XML reader and" is "Add an
    XML reader"). A plan's titles are sentences; a screen with almost no text needs a name. A word that
    owns the next one ("views'") brings it."""
    head = re.split(r"[:;]|\s[-–—]\s", title, maxsplit=1)[0].strip()
    parts = head.split()
    if parts and parts[0].lower() in ("the", "a", "an"):
        parts = parts[1:]
    words = words or len(parts)
    keep = words + (len(parts) > words and parts[words - 1].endswith(("'", "’", "'s", "’s")))  # views' files
    parts = parts[:keep]
    while len(parts) > 1 and parts[-1].lower().strip(",.") in TRAILING:
        parts.pop()
    return " ".join(parts) or title
