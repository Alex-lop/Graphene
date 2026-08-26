from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core_models import Identifier, RepoPath, ScopeId

ReviewSectionKey = Literal[
    "attention",
    "candidate",
    "verified_evidence",
    "human_intervention",
    "inherited_context",
    "outcome",
    "unknown",
]
ViewStage = Literal[
    "source_work",
    "human_correction_scope",
    "approved_handoff",
    "consumer_work",
    "candidate_decision",
    "local_result",
]
RelationshipClass = Literal[
    "verified_support",
    "authorization",
    "context_transfer",
    "handoff_continuation",
    "integrity",
    "membership",
]


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ViewReference(ViewModel):
    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ViewMemoryScope(ViewModel):
    memory_id: Identifier
    revision: int = Field(ge=1)
    scope_id: ScopeId
    path_globs: tuple[RepoPath, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def paths_are_canonical(self) -> ViewMemoryScope:
        if self.path_globs != tuple(sorted(set(self.path_globs))):
            raise ValueError("memory scope paths must be sorted and unique")
        return self


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
        "result",
    ]
    status: str = Field(min_length=1, max_length=128)
    truth_kind: str = Field(min_length=1, max_length=64)
    activity_count: int = Field(ge=0, le=32)
    label: str = Field(min_length=1, max_length=160)
    run_id: str | None = Field(default=None, max_length=128)
    seq: int | None = Field(default=None, ge=1)
    event_id: str | None = Field(default=None, max_length=128)
    recorded_at: datetime | None = Field(default=None, exclude_if=lambda value: value is None)
    source_ref: ViewReference | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    stage: ViewStage | None = Field(default=None, exclude_if=lambda value: value is None)


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
    relationship_class: RelationshipClass | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    support_path: bool | None = Field(default=None, exclude_if=lambda value: value is None)


class ReviewFact(ViewModel):
    id: str = Field(min_length=1, max_length=160)
    section: ReviewSectionKey
    status: Literal["established", "not_established", "pending", "historical"]
    text: str = Field(min_length=1, max_length=512)
    truth_kind: str = Field(min_length=1, max_length=64)
    node_ids: tuple[str, ...] = Field(max_length=32)
    edge_ids: tuple[str, ...] = Field(max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewSection(ViewModel):
    key: ReviewSectionKey
    title: str = Field(min_length=1, max_length=80)
    facts: tuple[ReviewFact, ...] = Field(max_length=24)


class ViewCounts(ViewModel):
    total_nodes: int = Field(ge=0)
    visible_nodes: int = Field(ge=0)
    filtered_nodes: int = Field(ge=0)
    collapsed_nodes: int = Field(ge=0)
    omitted_nodes: int = Field(ge=0)
    total_edges: int = Field(ge=0)
    visible_edges: int = Field(ge=0)


class ReviewBrief(ViewModel):
    attention: ReviewFact
    sections: tuple[ReviewSection, ...] = Field(min_length=7, max_length=7)
    changed_paths: tuple[str, ...] = Field(max_length=32)
    bound_paths: tuple[str, ...] = Field(max_length=32)
    stage: ViewStage
    outcome_kind: Literal[
        "not_established",
        "graphene_receipt_only",
        "isolated_local_commit",
        "rejected",
        "failed",
    ]
    counts: ViewCounts


class VerifiedSupportPath(ViewModel):
    root_node_id: str = Field(min_length=1, max_length=400)
    label: str = Field(min_length=1, max_length=160)
    node_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    edge_ids: tuple[str, ...] = Field(max_length=128)


class GraphSnapshot(ViewModel):
    view_version: Literal[1] = 1
    root_run_id: str = Field(min_length=1, max_length=128)
    heads: tuple[ViewHead, ...] = Field(max_length=16)
    cursor: str = Field(min_length=1, max_length=8_192)
    nodes: tuple[ViewNode, ...] = Field(max_length=320)
    edges: tuple[ViewEdge, ...] = Field(max_length=640)
    omitted_counts: dict[str, int]
    unknowns: tuple[str, ...]
    review_brief: ReviewBrief | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    support_paths: tuple[VerifiedSupportPath, ...] | None = Field(
        default=None, max_length=16, exclude_if=lambda value: value is None
    )
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
    remove_kind: Literal["node", "edge"] | None = None

    @model_validator(mode="after")
    def operation_payload_matches(self) -> "GraphDelta":
        valid = {
            "upsert_node": (
                self.node is not None
                and self.id == self.node.id
                and self.edge is self.status is self.snapshot is self.remove_kind is None
            ),
            "upsert_edge": (
                self.edge is not None
                and self.id == self.edge.id
                and self.node is self.status is self.snapshot is self.remove_kind is None
            ),
            "set_status": (
                self.id is not None
                and self.status is not None
                and self.node is self.edge is self.snapshot is self.remove_kind is None
            ),
            "remove": (
                self.id is not None
                and self.remove_kind is not None
                and self.node is self.edge is self.status is self.snapshot is None
            ),
            "reset": (
                self.snapshot is not None
                and self.id
                is self.run_id
                is self.seq
                is self.event_id
                is self.node
                is self.edge
                is self.status
                is self.remove_kind
                is None
            ),
        }[self.op]
        if not valid:
            raise ValueError("delta payload does not match its operation")
        return self
