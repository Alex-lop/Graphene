"""Draw a mission DAG top-to-bottom with box-drawing edges.

Pure functions over the Mission Control snapshot model: no store, no terminal,
no Textual. The TUI, the `--once` dump, and the snapshot tests all render
through here, so what the tests assert is what the screen shows.

Layout is longest-path layering with dummy pass-through nodes for edges that
skip a layer (the assembly node depends on every work node, which are rarely
all in one layer), one barycenter pass per layer to reduce crossings, and a
three-row connector zone between layers: a stub down from each parent, a bus
row of horizontals, and an arrow into each child. Connector cells carry a
direction bitmask so that merges and crossings pick the right box character
instead of overwriting each other.

Hard rule, tested: the rendered text never contains an `->` sequence. Edges
are drawn, not spelled.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from rich.text import Text

# Task states as the projection emits them (TaskStateValue), one glyph and one
# style each. The vocabulary is Graphene's, not a paraphrase of it.
STATE_STYLES: dict[str, tuple[str, str]] = {
    "queued": ("○", "grey62"),
    "ready": ("◐", "cyan"),
    "running": ("●", "yellow"),
    "blocked": ("!", "dark_orange"),
    "retrying": ("↻", "yellow"),
    "needs_input": ("!", "dark_orange"),
    "verifying": ("?", "blue"),
    "done": ("✓", "green"),
    "failed": ("✗", "red"),
    "cancelled": ("⊘", "magenta"),
}
_UNKNOWN_STATE = ("·", "white")

_UP, _DOWN, _LEFT, _RIGHT = 1, 2, 4, 8
_BOX: dict[int, str] = {
    _UP: "│", _DOWN: "│", _UP | _DOWN: "│",
    _LEFT: "─", _RIGHT: "─", _LEFT | _RIGHT: "─",
    _DOWN | _RIGHT: "┌", _DOWN | _LEFT: "┐", _UP | _RIGHT: "└", _UP | _LEFT: "┘",
    _UP | _DOWN | _RIGHT: "├", _UP | _DOWN | _LEFT: "┤",
    _DOWN | _LEFT | _RIGHT: "┬", _UP | _LEFT | _RIGHT: "┴",
    _UP | _DOWN | _LEFT | _RIGHT: "┼",
}
_CARD_ROWS = 4  # top border, label, state, bottom border
_GAP_ROWS = 3  # stub, bus, arrow
_GAP_COLS = 2


@dataclass(frozen=True)
class DagNode:
    node_id: str
    state: str
    kind: str = "work"
    detail: str | None = None  # e.g. the stage a cancelled attempt reached
    selected: bool = False


@dataclass
class _Slot:
    """One column slot in a layer: a real card or a dummy pass-through."""

    node_id: str | None  # None for a dummy
    width: int
    x: int = 0  # left edge, assigned after ordering

    @property
    def center(self) -> int:
        return self.x + self.width // 2


@dataclass
class _Layout:
    layers: list[list[_Slot]] = field(default_factory=list)
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    width: int = 0


def _card_width(node: DagNode) -> int:
    return max(len(node.node_id), len(_state_line(node))) + 4


def _state_line(node: DagNode) -> str:
    glyph, _ = STATE_STYLES.get(node.state, _UNKNOWN_STATE)
    text = f"{glyph} {node.state}"
    if node.detail:
        text += f" · {node.detail}"
    return text


def _layer_of(nodes: Mapping[str, DagNode], deps: Mapping[str, tuple[str, ...]]) -> dict[str, int]:
    """Longest-path layering; dependencies always sit in an earlier layer."""

    layers: dict[str, int] = {}

    def visit(node_id: str, trail: tuple[str, ...]) -> int:
        if node_id in layers:
            return layers[node_id]
        if node_id in trail:
            raise ValueError(f"dependency cycle through {node_id}")
        parents = [d for d in deps.get(node_id, ()) if d in nodes]
        depth = 0 if not parents else 1 + max(visit(p, trail + (node_id,)) for p in parents)
        layers[node_id] = depth
        return depth

    for node_id in nodes:
        visit(node_id, ())
    return layers


def _build_layout(nodes: Mapping[str, DagNode], deps: Mapping[str, tuple[str, ...]]) -> _Layout:
    layer_of = _layer_of(nodes, deps)
    depth = (max(layer_of.values()) + 1) if layer_of else 0
    layers: list[list[_Slot]] = [[] for _ in range(depth)]
    slot_of: dict[str, tuple[int, int]] = {}
    for node_id in nodes:  # snapshot order is sorted, so this is deterministic
        layer = layer_of[node_id]
        layers[layer].append(_Slot(node_id, _card_width(nodes[node_id])))
        slot_of[node_id] = (layer, len(layers[layer]) - 1)

    # Edges parent -> child, with dummies for every skipped layer.
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for child_id in nodes:
        for parent_id in deps.get(child_id, ()):
            if parent_id not in nodes:
                continue
            upstream = slot_of[parent_id]
            target_layer = layer_of[child_id]
            for layer in range(layer_of[parent_id] + 1, target_layer):
                layers[layer].append(_Slot(None, 1))
                dummy = (layer, len(layers[layer]) - 1)
                edges.append((upstream, dummy))
                upstream = dummy
            edges.append((upstream, slot_of[child_id]))

    # One top-down barycenter pass: order each layer by the mean position of
    # its parents in the layer above, then assign x positions.
    parents_of: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for parent, child in edges:
        parents_of.setdefault(child, []).append(parent)
    position: dict[tuple[int, int], float] = {}
    remap: dict[tuple[int, int], tuple[int, int]] = {}
    for layer_index, layer in enumerate(layers):
        keyed = list(enumerate(layer))
        if layer_index:
            def key(item: tuple[int, _Slot]) -> tuple[float, int]:
                parents = parents_of.get((layer_index, item[0]), [])
                if not parents:
                    return (float(item[0]), item[0])
                return (sum(position[remap[p]] for p in parents) / len(parents), item[0])
            keyed.sort(key=key)
        x = 0
        ordered: list[_Slot] = []
        for new_index, (old_index, slot) in enumerate(keyed):
            slot.x = x
            x += slot.width + _GAP_COLS
            ordered.append(slot)
            remap[(layer_index, old_index)] = (layer_index, new_index)
            position[(layer_index, new_index)] = float(slot.center)
        layers[layer_index] = ordered
    edges = [(remap[p], remap[c]) for p, c in edges]

    width = max((s.x + s.width for layer in layers for s in layer), default=0)
    for layer in layers:  # centre every layer under the widest one
        span = layer[-1].x + layer[-1].width if layer else 0
        shift = (width - span) // 2
        for slot in layer:
            slot.x += shift
    return _Layout(layers=layers, edges=edges, width=width)


class _Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.chars: list[list[str]] = [[" "] * width for _ in range(height)]
        self.styles: list[list[str | None]] = [[None] * width for _ in range(height)]
        self.masks: dict[tuple[int, int], int] = {}

    def put(self, x: int, y: int, text: str, style: str | None = None) -> None:
        for offset, char in enumerate(text):
            if 0 <= x + offset < self.width and 0 <= y < self.height:
                self.chars[y][x + offset] = char
                self.styles[y][x + offset] = style

    def connect(self, x: int, y: int, mask: int) -> None:
        merged = self.masks.get((x, y), 0) | mask
        self.masks[(x, y)] = merged
        self.put(x, y, _BOX[merged], "grey70")

    def text(self) -> Text:
        out = Text()
        for y in range(self.height):
            row = "".join(self.chars[y]).rstrip()
            line = Text()
            for x, char in enumerate(row):
                line.append(char, self.styles[y][x])
            out.append(line)
            if y < self.height - 1:
                out.append("\n")
        return out


def render_dag(nodes: Iterable[DagNode], deps: Mapping[str, tuple[str, ...]]) -> Text:
    """Render the DAG as styled text; `.plain` is what the tests inspect."""

    by_id = {node.node_id: node for node in nodes}
    if not by_id:
        return Text("(no tasks)")
    layout = _build_layout(by_id, deps)
    depth = len(layout.layers)
    height = depth * _CARD_ROWS + max(depth - 1, 0) * _GAP_ROWS
    canvas = _Canvas(layout.width, height)

    for layer_index, layer in enumerate(layout.layers):
        top = layer_index * (_CARD_ROWS + _GAP_ROWS)
        for slot in layer:
            if slot.node_id is None:  # dummy: a plain vertical through the card rows
                for row in range(_CARD_ROWS):
                    canvas.connect(slot.center, top + row, _UP | _DOWN)
                continue
            node = by_id[slot.node_id]
            glyph_style = STATE_STYLES.get(node.state, _UNKNOWN_STATE)[1]
            border = "bold white" if node.selected else "grey70"
            inner = slot.width - 2
            corner = ("┏", "┓", "┗", "┛", "━", "┃") if node.selected else ("┌", "┐", "└", "┘", "─", "│")
            canvas.put(slot.x, top, corner[0] + corner[4] * inner + corner[1], border)
            canvas.put(slot.x, top + 1, corner[5] + f" {node.node_id}".ljust(inner) + corner[5], border)
            canvas.put(slot.x + 1, top + 1, f" {node.node_id}", "bold")
            canvas.put(slot.x, top + 2, corner[5] + " " * inner + corner[5], border)
            canvas.put(slot.x + 2, top + 2, _state_line(node), glyph_style)
            canvas.put(slot.x, top + 3, corner[2] + corner[4] * inner + corner[3], border)

    for (p_layer, p_index), (c_layer, c_index) in layout.edges:
        parent = layout.layers[p_layer][p_index]
        child = layout.layers[c_layer][c_index]
        bottom = p_layer * (_CARD_ROWS + _GAP_ROWS) + _CARD_ROWS - 1
        px, cx = parent.center, child.center
        stub, bus, arrow = bottom + 1, bottom + 2, bottom + 3
        if parent.node_id is not None:  # the stub leaves through the bottom border
            canvas.put(px, bottom, "┳" if by_id[parent.node_id].selected else "┬", "grey70")
        canvas.connect(px, stub, _UP | _DOWN)
        if px == cx:
            canvas.connect(px, bus, _UP | _DOWN)
        else:
            lo, hi = sorted((px, cx))
            canvas.connect(px, bus, _UP | (_RIGHT if cx > px else _LEFT))
            for x in range(lo + 1, hi):
                canvas.connect(x, bus, _LEFT | _RIGHT)
            canvas.connect(cx, bus, _DOWN | (_LEFT if cx > px else _RIGHT))
        if child.node_id is None:
            canvas.connect(cx, arrow, _UP | _DOWN)
        else:
            canvas.put(cx, arrow, "▼", "grey70")
    return canvas.text()


def render_banner(
    *,
    mission_id: str,
    status: str,
    plan_revision: int,
    plan_sha256: str | None,
    approved_plan_revision: int | None,
    source: str | None = None,
) -> Text:
    """Mission id, plan revision, digest, and the signed/unsigned state."""

    signed = approved_plan_revision is not None and approved_plan_revision == plan_revision
    banner = Text()
    banner.append("GRAPHENE ", "bold")
    banner.append(mission_id, "bold cyan")
    banner.append(f"  ·  {status}", "white")
    if source:
        banner.append(f"  ·  {source}", "grey62")
    banner.append("\n")
    banner.append(f"PLAN v{plan_revision}", "bold")
    digest = (plan_sha256 or "")[:12] or "no digest"
    banner.append(f"  digest {digest}", "white")
    if signed:
        banner.append(f"  ·  SIGNED — revision {approved_plan_revision} approved", "bold green")
    elif approved_plan_revision is not None:
        banner.append(
            f"  ·  UNSIGNED — revision {approved_plan_revision} was signed, v{plan_revision} is not",
            "bold red",
        )
    else:
        banner.append("  ·  UNSIGNED — nothing runs until you sign", "bold red")
    return banner


def nodes_from_snapshot(snapshot: object, *, stages: Mapping[str, str] | None = None, selected: str | None = None) -> tuple[list[DagNode], dict[str, tuple[str, ...]]]:
    """Adapt a MissionControlSnapshot (or anything with `.tasks`) to DagNodes."""

    nodes: list[DagNode] = []
    deps: dict[str, tuple[str, ...]] = {}
    for task in snapshot.tasks:  # type: ignore[attr-defined]
        detail = (stages or {}).get(task.task_id)
        nodes.append(
            DagNode(
                node_id=task.task_id,
                state=str(task.state),
                kind=str(task.kind),
                detail=detail,
                selected=task.task_id == selected,
            )
        )
        deps[task.task_id] = tuple(task.dependency_ids)
    return nodes, deps


def assert_no_arrow_art(text: str) -> None:
    """The renderer draws edges; it never spells them. Fails on `->`."""

    if "->" in text:
        raise AssertionError("rendered output contains '->' text art")
