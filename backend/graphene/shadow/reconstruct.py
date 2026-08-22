"""Segment reconstruction of a shadow event stream (``segments.v1``).

Heuristic ``segments.v1``: segment 1 opens at seq 1 as ``session_start``. A
new segment opens at a user message (``user_message``, labelled with the
message excerpt), at an agent plan marker (``plan_marker``: a ``TodoWrite``,
``update_plan`` or ``plan`` tool event, or an agent message whose excerpt
starts with ``## Plan`` or ``Plan:``), or at a timestamped event more than
``GAP_SECONDS`` after the previous timestamped event (``gap``). A user message
that follows nothing but user messages merges into the open segment instead
of opening an empty one. When several rules apply to one event the precedence
is user_message, plan_marker, gap. Edges are read-after-write on paths: a path
written in an earlier segment and read or edited in a later one (``file_edit``
reads before it writes; ``file_create`` does not). Every segment and edge is a
reconstruction and carries ``provenance="inferred"``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from ..models import FrozenModel
from .events import ShadowEvent
from .redaction import bounded_excerpt

SEGMENTS_VERSION = "segments.v1"
# A gap longer than 15 minutes between consecutive timestamped events starts a
# new segment.
GAP_SECONDS = 900
LABEL_LIMIT = 120
PLAN_TOOLS = frozenset({"TodoWrite", "update_plan", "plan"})
PLAN_PREFIXES = ("## Plan", "Plan:")

_WRITE_KINDS = frozenset({"file_edit", "file_create"})
_COMMAND_KINDS = frozenset({"command_exec", "vcs_op", "network_op", "install_op"})
_CHECK_KINDS = frozenset({"check_run", "check_result"})

Boundary = Literal["session_start", "user_message", "gap", "plan_marker"]


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    if list(values) != sorted(set(values)):
        raise ValueError("path tuples must be sorted and unique")
    return values


def _ascending(values: tuple[int, ...]) -> tuple[int, ...]:
    if list(values) != sorted(set(values)):
        raise ValueError("seq tuples must be ascending and unique")
    return values


Seq = Annotated[int, Field(ge=1)]
SortedPaths = Annotated[tuple[str, ...], AfterValidator(_sorted_unique)]
SortedSeqs = Annotated[tuple[Seq, ...], AfterValidator(_ascending)]


def segment_id_for(index: int) -> str:
    """``seg_0001`` style identifier for a 1-based segment index."""

    if index < 1:
        raise ValueError("segment indexes are 1-based")
    return f"seg_{index:04d}"


class ShadowSegment(FrozenModel):
    """A contiguous seq range the heuristic treats as one unit of work."""

    segment_id: str
    index: Seq
    start_seq: Seq
    end_seq: Seq
    boundary: Boundary
    label: Annotated[str, Field(min_length=1, max_length=LABEL_LIMIT)] | None
    paths_read: SortedPaths
    paths_written: SortedPaths
    paths_deleted: SortedPaths
    command_seqs: SortedSeqs
    check_seqs: SortedSeqs
    claim_seqs: SortedSeqs
    event_count: Seq
    provenance: Literal["inferred"] = "inferred"

    @model_validator(mode="after")
    def shape_is_consistent(self) -> ShadowSegment:
        if self.segment_id != segment_id_for(self.index):
            raise ValueError("segment_id must be derived from the segment index")
        if self.end_seq < self.start_seq:
            raise ValueError("a segment must end at or after its start")
        if self.event_count != self.end_seq - self.start_seq + 1:
            raise ValueError("segment event_count must match its seq range")
        for seqs in (self.command_seqs, self.check_seqs, self.claim_seqs):
            if seqs and (seqs[0] < self.start_seq or seqs[-1] > self.end_seq):
                raise ValueError("segment seq references must fall inside the segment")
        return self


class ShadowEdge(FrozenModel):
    """A later segment consumed a path an earlier segment wrote."""

    src: str
    dst: str
    paths: Annotated[SortedPaths, Field(min_length=1)]
    relation: Literal["read_after_write"] = "read_after_write"
    provenance: Literal["inferred"] = "inferred"


class TimelineEntry(FrozenModel):
    """One non-message event placed in its segment."""

    seq: Seq
    event_id: str
    kind: str
    provenance: str
    ts: str | None
    check_family: str | None
    exit_code: int | None
    paths: SortedPaths
    outside_paths: SortedPaths
    segment_id: str


class ShadowGraph(FrozenModel):
    segments_version: str
    session_id: str
    event_count: Seq
    observed_count: Annotated[int, Field(ge=0)]
    inferred_count: Annotated[int, Field(ge=0)]
    unknown_count: Annotated[int, Field(ge=0)]
    segments: Annotated[tuple[ShadowSegment, ...], Field(min_length=1)]
    edges: tuple[ShadowEdge, ...]
    timeline: tuple[TimelineEntry, ...]

    @model_validator(mode="after")
    def shape_is_consistent(self) -> ShadowGraph:
        if self.observed_count + self.inferred_count != self.event_count:
            raise ValueError("observed and inferred counts must sum to event_count")
        if self.unknown_count > self.event_count:
            raise ValueError("unknown_count cannot exceed event_count")
        expected_start = 1
        for index, segment in enumerate(self.segments, start=1):
            if segment.index != index or segment.start_seq != expected_start:
                raise ValueError("segments must be contiguous and 1-based")
            expected_start = segment.end_seq + 1
        if expected_start - 1 != self.event_count:
            raise ValueError("segments must cover every event exactly once")
        index_of = {segment.segment_id: segment.index for segment in self.segments}
        for edge in self.edges:
            if edge.src not in index_of or edge.dst not in index_of:
                raise ValueError("edges must reference known segments")
            if index_of[edge.src] >= index_of[edge.dst]:
                raise ValueError("edges must point from an earlier to a later segment")
        previous_seq = 0
        for entry in self.timeline:
            if entry.seq <= previous_seq or entry.seq > self.event_count:
                raise ValueError("timeline entries must be in ascending seq order")
            if entry.segment_id not in index_of:
                raise ValueError("timeline entries must reference known segments")
            previous_seq = entry.seq
        return self


@dataclass(slots=True)
class _OpenSegment:
    index: int
    start_seq: int
    boundary: Boundary
    label: str | None
    end_seq: int = 0
    event_count: int = 0
    only_user_messages: bool = True
    read: set[str] = field(default_factory=set)
    written: set[str] = field(default_factory=set)
    edited: set[str] = field(default_factory=set)
    deleted: set[str] = field(default_factory=set)
    command_seqs: list[int] = field(default_factory=list)
    check_seqs: list[int] = field(default_factory=list)
    claim_seqs: list[int] = field(default_factory=list)

    @property
    def segment_id(self) -> str:
        return segment_id_for(self.index)

    def absorb(self, event: ShadowEvent) -> None:
        self.end_seq = event.seq
        self.event_count += 1
        if not _is_user_message(event):
            self.only_user_messages = False
        if event.kind == "file_read":
            self.read.update(event.paths)
        elif event.kind in _WRITE_KINDS:
            self.written.update(event.paths)
            if event.kind == "file_edit":
                self.edited.update(event.paths)
        elif event.kind == "file_delete":
            self.deleted.update(event.paths)
        if event.kind in _COMMAND_KINDS:
            self.command_seqs.append(event.seq)
        elif event.kind in _CHECK_KINDS:
            self.check_seqs.append(event.seq)
        elif event.kind == "claim":
            self.claim_seqs.append(event.seq)

    def freeze(self) -> ShadowSegment:
        return ShadowSegment(
            segment_id=self.segment_id,
            index=self.index,
            start_seq=self.start_seq,
            end_seq=self.end_seq,
            boundary=self.boundary,
            label=self.label,
            paths_read=tuple(sorted(self.read)),
            paths_written=tuple(sorted(self.written)),
            paths_deleted=tuple(sorted(self.deleted)),
            command_seqs=tuple(self.command_seqs),
            check_seqs=tuple(self.check_seqs),
            claim_seqs=tuple(self.claim_seqs),
            event_count=self.event_count,
        )


def _is_user_message(event: ShadowEvent) -> bool:
    return event.actor == "user" and event.kind == "message"


def _is_plan_marker(event: ShadowEvent) -> bool:
    if event.actor != "agent":
        return False
    if event.tool in PLAN_TOOLS:
        return True
    if event.kind == "message" and event.excerpt:
        return event.excerpt.lstrip().startswith(PLAN_PREFIXES)
    return False


def _parse_timestamp(value: str) -> datetime:
    # Validated RFC 3339 UTC; fractions beyond microseconds are truncated for
    # arithmetic only.
    head, _, fraction = value[:-1].partition(".")
    text = head + ("." + fraction[:6] if fraction else "")
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _boundary_for(
    event: ShadowEvent, current: _OpenSegment | None, previous_ts: datetime | None
) -> Boundary | None:
    if current is None:
        return "session_start"
    if _is_user_message(event):
        return None if current.only_user_messages else "user_message"
    if _is_plan_marker(event):
        return "plan_marker"
    if previous_ts is not None and event.ts is not None:
        elapsed = (_parse_timestamp(event.ts) - previous_ts).total_seconds()
        if elapsed > GAP_SECONDS:
            return "gap"
    return None


def _label_for(event: ShadowEvent, boundary: Boundary) -> str | None:
    if boundary == "gap":
        return None
    text = event.excerpt or (event.tool if boundary == "plan_marker" else None)
    return bounded_excerpt(text, LABEL_LIMIT) if text else None


def reconstruct(events: Sequence[ShadowEvent]) -> ShadowGraph:
    """Apply ``segments.v1`` to a contiguous single-session event stream."""

    stream = tuple(events)
    if not stream:
        raise ValueError("cannot reconstruct an empty shadow session")
    for event in stream:
        if not isinstance(event, ShadowEvent):
            raise TypeError("reconstruct accepts only verified shadow events")
    session_id = stream[0].session_id
    for index, event in enumerate(stream, start=1):
        if event.seq != index:
            raise ValueError(
                f"shadow event seq {event.seq} breaks contiguity at {index}"
            )
        if event.session_id != session_id:
            raise ValueError("shadow session identifiers must not change mid-stream")

    opened: list[_OpenSegment] = []
    segment_of: dict[int, str] = {}
    previous_ts: datetime | None = None
    for event in stream:
        current = opened[-1] if opened else None
        boundary = _boundary_for(event, current, previous_ts)
        if boundary is not None or current is None:
            current = _OpenSegment(
                index=len(opened) + 1,
                start_seq=event.seq,
                boundary=boundary or "session_start",
                label=_label_for(event, boundary or "session_start"),
            )
            opened.append(current)
        current.absorb(event)
        segment_of[event.seq] = current.segment_id
        if event.ts is not None:
            previous_ts = _parse_timestamp(event.ts)

    edges: list[ShadowEdge] = []
    for position, src in enumerate(opened):
        if not src.written:
            continue
        for dst in opened[position + 1 :]:
            shared = src.written & (dst.read | dst.edited)
            if shared:
                edges.append(
                    ShadowEdge(
                        src=src.segment_id,
                        dst=dst.segment_id,
                        paths=tuple(sorted(shared)),
                    )
                )

    timeline = tuple(
        TimelineEntry(
            seq=event.seq,
            event_id=event.event_id,
            kind=event.kind,
            provenance=event.provenance,
            ts=event.ts,
            check_family=event.check_family,
            exit_code=event.exit_code,
            paths=event.paths,
            outside_paths=event.outside_paths,
            segment_id=segment_of[event.seq],
        )
        for event in stream
        if event.kind != "message"
    )
    return ShadowGraph(
        segments_version=SEGMENTS_VERSION,
        session_id=session_id,
        event_count=len(stream),
        observed_count=sum(1 for event in stream if event.provenance == "observed"),
        inferred_count=sum(1 for event in stream if event.provenance == "inferred"),
        unknown_count=sum(1 for event in stream if event.kind == "unknown"),
        segments=tuple(segment.freeze() for segment in opened),
        edges=tuple(edges),
        timeline=timeline,
    )


def _dot_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _dot_label(parts: Sequence[str]) -> str:
    return '"' + "\\n".join(_dot_string(part) for part in parts) + '"'


def graph_to_dot(graph: ShadowGraph) -> str:
    """Graphviz digraph of the segments; every node and edge is marked inferred."""

    lines = [
        "digraph shadow {",
        f"  // {graph.segments_version}: every node and edge below is a "
        'reconstruction, provenance="inferred"',
        f"  graph [label={_dot_label([f'session {graph.session_id}'])} rankdir=LR];",
        "  node [shape=box];",
    ]
    for segment in graph.segments:
        text = segment.label if segment.label else f"({segment.boundary})"
        label = _dot_label(
            [segment.segment_id, text, f"writes={len(segment.paths_written)}"]
        )
        lines.append(
            f'  "{_dot_string(segment.segment_id)}" '
            f'[label={label} provenance="inferred"];'
        )
    for edge in graph.edges:
        shown = list(edge.paths[:3])
        if len(edge.paths) > 3:
            shown.append(f"+{len(edge.paths) - 3} more")
        lines.append(
            f'  "{_dot_string(edge.src)}" -> "{_dot_string(edge.dst)}" '
            f'[label={_dot_label(shown)} provenance="inferred"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


__all__ = [
    "GAP_SECONDS",
    "LABEL_LIMIT",
    "PLAN_PREFIXES",
    "PLAN_TOOLS",
    "SEGMENTS_VERSION",
    "Boundary",
    "ShadowEdge",
    "ShadowGraph",
    "ShadowSegment",
    "TimelineEntry",
    "graph_to_dot",
    "reconstruct",
    "segment_id_for",
]
