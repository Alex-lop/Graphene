from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ViewReference(ViewModel):
    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ViewHead(ViewModel):
    run_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ViewNode(ViewModel):
    id: str = Field(min_length=1, max_length=400)
    kind: Literal[
        "agent",
        "tool",
        "file",
        "evidence",
        "changeset",
        "feedback",
        "memory",
        "policy",
        "test",
        "human",
        "handoff",
        "promotion",
    ]
    status: str = Field(min_length=1, max_length=128)
    truth_kind: str = Field(min_length=1, max_length=64)
    activity_count: int = Field(ge=0, le=32)
    label: str = Field(min_length=1, max_length=160)
    run_id: str | None = Field(default=None, max_length=128)
    seq: int | None = Field(default=None, ge=1)
    event_id: str | None = Field(default=None, max_length=128)
    source_ref: ViewReference | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewEdge(ViewModel):
    id: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=400)
    target: str = Field(min_length=1, max_length=400)
    kind: str = Field(min_length=1, max_length=64)
    activity_count: int = Field(ge=1, le=32)
    run_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    event_id: str = Field(min_length=1, max_length=128)
    evidence_ref: ViewReference


class GraphSnapshot(ViewModel):
    view_version: Literal[1] = 1
    root_run_id: str = Field(min_length=1, max_length=128)
    heads: tuple[ViewHead, ...] = Field(max_length=16)
    cursor: str = Field(min_length=1, max_length=8_192)
    nodes: tuple[ViewNode, ...] = Field(max_length=320)
    edges: tuple[ViewEdge, ...] = Field(max_length=640)
    omitted_counts: dict[str, int]
    unknowns: tuple[str, ...]
    graph_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GraphDelta(ViewModel):
    op: Literal["upsert_node", "upsert_edge", "set_status", "remove", "reset"]
    id: str | None = Field(default=None, max_length=400)
    run_id: str | None = Field(default=None, max_length=128)
    seq: int | None = Field(default=None, ge=1)
    event_id: str | None = Field(default=None, max_length=128)
    node: ViewNode | None = None
    edge: ViewEdge | None = None
    status: str | None = Field(default=None, max_length=128)
    snapshot: GraphSnapshot | None = None
