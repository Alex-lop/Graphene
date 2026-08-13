from __future__ import annotations

import ast
import base64
import binascii
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from ..hashing import canonical_json_sha256, sha256_hex
from ..models import (
    CandidateArtifact,
    ContextDecision,
    ContextPacket,
    FeedbackRecord,
    GraphEdge,
    GraphEdgeKind,
    GraphMvpContract,
    GraphNode,
    GraphNodeKind,
    GraphProvenance,
    GraphQuery,
    GraphResponse,
    HunkEvidence,
    HumanDecision,
    InjectionReceipt,
    MemoryDecisionValue,
    MemoryRef,
    MemoryRevision,
    MemoryState,
    ProofType,
    RunRecord,
)

_DIFF_HEADER = re.compile(rb"^diff --git a/([^\n\t]+) b/([^\n\t]+)\n$")
_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


class GraphBuildError(ValueError):
    """Authoritative records cannot be projected without inventing evidence."""


@dataclass
class _Projection:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    details: dict[str, GraphNode] = field(default_factory=dict)
    edges: dict[str, GraphEdge] = field(default_factory=dict)
    refs: set[str] = field(default_factory=set)
    optional_nodes: set[str] = field(default_factory=set)
    optional_edges: set[str] = field(default_factory=set)
    run_nodes: dict[str, str] = field(default_factory=dict)
    changesets: dict[str, str] = field(default_factory=dict)
    files: dict[tuple[str, str], str] = field(default_factory=dict)
    hunks: dict[str, HunkEvidence] = field(default_factory=dict)
    memories: dict[tuple[str, int], str] = field(default_factory=dict)


def _stable_id(kind: str, identity: Any) -> str:
    return f"{kind}:{canonical_json_sha256(identity)}"


def _index(items: Iterable[Any], key: Any, label: str) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for item in items:
        item_key = key(item)
        if item_key in result:
            raise GraphBuildError(f"duplicate {label}: {item_key}")
        result[item_key] = item
    return result


def _repo_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        value in {"", "."}
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise GraphBuildError(f"non-canonical repository path: {value!r}")
    return value


class GraphBuilder:
    """Pure deterministic projection over already-validated authoritative records."""

    def __init__(
        self,
        contract: GraphMvpContract,
        *,
        runs: Iterable[RunRecord],
        feedback: Iterable[FeedbackRecord] = (),
        memories: Iterable[MemoryRevision] = (),
        context_packets: Iterable[ContextPacket] = (),
        injection_receipts: Iterable[InjectionReceipt] = (),
        after_files: Mapping[tuple[str, str], bytes] | None = None,
    ) -> None:
        self.contract = contract
        self.runs = _index(runs, lambda item: item.run_id, "run ID")
        self.feedback = _index(feedback, lambda item: item.feedback_id, "feedback ID")
        self.memories = _index(
            memories,
            lambda item: (item.memory_id, item.revision),
            "memory revision",
        )
        self.context_packets = _index(
            context_packets,
            lambda item: item.consumer_run_id,
            "context packet consumer run",
        )
        self.injection_receipts = _index(
            injection_receipts,
            lambda item: item.run_id,
            "injection receipt run",
        )
        self.after_files = {
            (run_id, _repo_path(path)): bytes(content)
            for (run_id, path), content in (after_files or {}).items()
        }

    def build(self, run_id: str, query: GraphQuery | None = None) -> GraphResponse:
        query = query or GraphQuery(depth=self.contract.caps.default_depth)
        projection = self._project(run_id, include_imports=query.depth > 0)
        return self._bounded_response(projection, run_id, query)

    def node_detail(self, run_id: str, node_id: str) -> GraphNode | None:
        projection = self._project(run_id, include_imports=True)
        return projection.details.get(node_id)

    def _project(self, run_id: str, *, include_imports: bool) -> _Projection:
        current = self.runs.get(run_id)
        if current is None:
            raise GraphBuildError(f"unknown run: {run_id}")
        if current.repo_id != self.contract.repo_id:
            raise GraphBuildError("current run belongs to another repository")

        packet = self.context_packets.get(run_id)
        memories = self._selected_memories(current, packet)
        relevant_run_ids = {run_id, *(memory.evidence_run_id for memory in memories)}
        relevant_runs: list[RunRecord] = []
        for relevant_id in sorted(relevant_run_ids):
            run = self.runs.get(relevant_id)
            if run is None:
                raise GraphBuildError(f"missing evidence run: {relevant_id}")
            if run.repo_id != self.contract.repo_id:
                raise GraphBuildError("evidence run belongs to another repository")
            relevant_runs.append(run)

        projection = _Projection()
        for run in relevant_runs:
            self._project_run(projection, run)
        for memory in memories:
            self._project_memory(projection, memory)
        if packet is not None:
            self._project_packet(projection, current, packet)
        elif current.injected_memories:
            raise GraphBuildError("memory-bound run is missing its context packet")
        if include_imports:
            self._project_imports(projection, relevant_runs)

        for node in projection.nodes.values():
            if node.source_ref not in projection.refs:
                raise GraphBuildError(f"unresolvable node source_ref: {node.source_ref}")
        for edge in projection.edges.values():
            if edge.source not in projection.nodes or edge.target not in projection.nodes:
                raise GraphBuildError(f"edge has an unresolved endpoint: {edge.id}")
            if edge.source_ref not in projection.refs:
                raise GraphBuildError(f"unresolvable edge source_ref: {edge.source_ref}")
        return projection

    def _selected_memories(
        self, current: RunRecord, packet: ContextPacket | None
    ) -> tuple[MemoryRevision, ...]:
        selected = {(item.memory_id, item.revision) for item in current.injected_memories}
        if packet is not None:
            selected.update(
                (item.memory_id, item.revision) for item in packet.approved_memories
            )
        selected.update(
            key for key, memory in self.memories.items() if memory.evidence_run_id == current.run_id
        )
        result: list[MemoryRevision] = []
        for key in sorted(selected):
            memory = self.memories.get(key)
            if memory is None:
                raise GraphBuildError(f"missing memory revision: {key[0]}@{key[1]}")
            if memory.repo_id != self.contract.repo_id:
                raise GraphBuildError("memory belongs to another repository")
            result.append(memory)
        return tuple(result)

    def _project_run(self, projection: _Projection, run: RunRecord) -> None:
        run_ref = f"runs/{run.run_id}"
        projection.refs.add(run_ref)
        run_node = self._add_node(
            projection,
            kind=GraphNodeKind.AGENT_RUN,
            identity=run.run_id,
            label=run.agent_profile_id or f"Queued {run.task_id.value}",
            repo_id=run.repo_id,
            run_id=run.run_id,
            provenance=GraphProvenance.SERVER_OBSERVED,
            source_ref=run_ref,
            status=run.state.value,
            created_at=self._run_time(run),
            data={
                "agent_profile_id": run.agent_profile_id,
                "task_id": run.task_id.value,
                "base_sha": run.base_sha,
                "allowed_paths": list(run.allowed_paths),
                "allowed_tools": list(run.allowed_tools),
                "session_id": run.session_id,
                "fresh_session": run.fresh_session,
                "model_id": run.model_id,
            },
        )
        projection.run_nodes[run.run_id] = run_node
        candidate = run.candidate
        if candidate is None:
            return

        candidate_ref = f"{run_ref}/candidate"
        patch_ref = f"{candidate_ref}/canonical_patch"
        projection.refs.update({candidate_ref, patch_ref})
        candidate_time = self._candidate_time(run)
        changeset = self._add_node(
            projection,
            kind=GraphNodeKind.CHANGESET,
            identity={
                "run_id": run.run_id,
                "candidate_revision": candidate.candidate_revision,
                "patch": candidate.candidate_patch_sha256,
            },
            label=f"Candidate revision {candidate.candidate_revision}",
            repo_id=run.repo_id,
            run_id=run.run_id,
            provenance=GraphProvenance.SERVER_OBSERVED,
            source_ref=candidate_ref,
            status=run.state.value,
            created_at=candidate_time,
            data={
                "candidate_revision": candidate.candidate_revision,
                "base_commit_sha": candidate.base_commit_sha,
                "candidate_patch_sha256": candidate.candidate_patch_sha256,
                "candidate_tree_sha256": candidate.candidate_tree_sha256,
                "changed_file_count": len(candidate.changed_paths),
                "changed_paths": list(candidate.changed_paths),
                "lifecycle_state": run.state.value,
            },
        )
        projection.changesets[run.run_id] = changeset
        self._add_edge(
            projection,
            source=run_node,
            kind=GraphEdgeKind.PRODUCED,
            target=changeset,
            provenance=GraphProvenance.SERVER_OBSERVED,
            source_ref=candidate_ref,
        )

        file_changes = {change.path: change for change in candidate.file_changes}
        for path in candidate.changed_paths:
            change = file_changes[path]
            file_ref = f"{candidate_ref}/file_changes/{path}"
            projection.refs.add(file_ref)
            file_node = self._add_node(
                projection,
                kind=GraphNodeKind.FILE,
                identity={
                    "run_id": run.run_id,
                    "patch": candidate.candidate_patch_sha256,
                    "path": path,
                },
                label=path,
                repo_id=run.repo_id,
                run_id=run.run_id,
                provenance=GraphProvenance.SERVER_OBSERVED,
                source_ref=file_ref,
                status="created" if change.before_sha256 is None else "modified",
                created_at=candidate_time,
                data={
                    "path": path,
                    "before_sha256": change.before_sha256,
                    "after_sha256": change.after_sha256,
                    "language": self._language(path),
                },
            )
            projection.files[(run.run_id, path)] = file_node

        for hunk in self._parse_hunks(run.run_id, candidate):
            hunk_ref = f"{patch_ref}#hunk={hunk.hunk_id}"
            projection.refs.add(hunk_ref)
            detail = {
                "path": hunk.path,
                "old_start": hunk.old_start,
                "old_lines": hunk.old_lines,
                "new_start": hunk.new_start,
                "new_lines": hunk.new_lines,
                "before_sha256": hunk.before_sha256,
                "after_sha256": hunk.after_sha256,
                "candidate_patch_sha256": hunk.canonical_patch_sha256,
                "exact_hunk_sha256": hunk.exact_hunk_sha256,
                "candidate_revision": hunk.candidate_revision,
                "unified_diff": hunk.unified_diff,
            }
            summary = {key: value for key, value in detail.items() if key != "unified_diff"}
            hunk_node = self._add_node(
                projection,
                kind=GraphNodeKind.HUNK,
                identity=hunk.hunk_id,
                node_id=hunk.hunk_id,
                label=(
                    f"{hunk.path} +{hunk.new_start},{hunk.new_lines}"
                ),
                repo_id=run.repo_id,
                run_id=run.run_id,
                provenance=GraphProvenance.SERVER_DERIVED,
                source_ref=hunk_ref,
                status="exact",
                created_at=candidate_time,
                data=summary,
                detail_data=detail,
            )
            projection.hunks[hunk.hunk_id] = hunk
            self._add_edge(
                projection,
                source=changeset,
                kind=GraphEdgeKind.CONTAINS,
                target=hunk_node,
                provenance=GraphProvenance.SERVER_DERIVED,
                source_ref=patch_ref,
            )
            self._add_edge(
                projection,
                source=hunk_node,
                kind=GraphEdgeKind.MODIFIES,
                target=projection.files[(run.run_id, hunk.path)],
                provenance=GraphProvenance.SERVER_DERIVED,
                source_ref=patch_ref,
            )

        receipt = candidate.test_receipt
        test_ref = f"{candidate_ref}/test_receipt"
        projection.refs.add(test_ref)
        test_node = self._add_node(
            projection,
            kind=GraphNodeKind.TEST_RECEIPT,
            identity={"run_id": run.run_id, "receipt": receipt.receipt_sha256},
            label=receipt.required_test_profile,
            repo_id=run.repo_id,
            run_id=run.run_id,
            provenance=GraphProvenance.SERVER_OBSERVED,
            source_ref=test_ref,
            status="passed" if receipt.candidate_exit_code == 0 and not receipt.timed_out else "failed",
            created_at=self._proof_time(run, ProofType.TEST_COMPLETED) or candidate_time,
            data={
                "required_test_profile": receipt.required_test_profile,
                "command": list(receipt.command),
                "candidate_exit_code": receipt.candidate_exit_code,
                "base_with_new_test_exit_code": receipt.base_with_new_test_exit_code,
                "timed_out": receipt.timed_out,
                "output_sha256": receipt.output_sha256,
                "output_truncated": receipt.output_truncated,
                "base_commit_sha": receipt.base_commit_sha,
                "candidate_patch_sha256": receipt.candidate_patch_sha256,
                "receipt_sha256": receipt.receipt_sha256,
            },
            digest_source=receipt.model_dump(mode="json"),
        )
        self._add_edge(
            projection,
            source=test_node,
            kind=GraphEdgeKind.VALIDATED,
            target=changeset,
            provenance=GraphProvenance.SERVER_OBSERVED,
            source_ref=test_ref,
        )

        for check in sorted(run.policy_checks, key=lambda item: item.policy_check_id):
            if (
                check.run_id != run.run_id
                or check.candidate_patch_sha256 != candidate.candidate_patch_sha256
                or check.test_receipt_sha256 != receipt.receipt_sha256
                or check.context_packet_sha256 != run.context_packet_sha256
            ):
                raise GraphBuildError("policy check does not bind the projected candidate")
            check_ref = f"{run_ref}/policy_checks/{check.policy_check_id}"
            projection.refs.add(check_ref)
            policy_node = self._add_node(
                projection,
                kind=GraphNodeKind.POLICY_CHECK,
                identity={"run_id": run.run_id, "policy_check_id": check.policy_check_id},
                label="Policy allowed" if check.decision == "allowed" else "Completion denied",
                repo_id=run.repo_id,
                run_id=run.run_id,
                provenance=GraphProvenance.SERVER_OBSERVED,
                source_ref=check_ref,
                status=check.decision,
                created_at=check.occurred_at,
                data={
                    "policy_revision": check.policy_revision,
                    "decision": check.decision,
                    "reason_codes": list(check.reason_codes),
                    "candidate_patch_sha256": check.candidate_patch_sha256,
                    "context_packet_sha256": check.context_packet_sha256,
                    "test_receipt_sha256": check.test_receipt_sha256,
                },
                digest_source=check.model_dump(mode="json"),
            )
            self._add_edge(
                projection,
                source=policy_node,
                kind=(
                    GraphEdgeKind.ALLOWED
                    if check.decision == "allowed"
                    else GraphEdgeKind.DENIED
                ),
                target=changeset,
                provenance=GraphProvenance.SERVER_OBSERVED,
                source_ref=check_ref,
            )

        if run.promotion_decision is not None:
            if (
                run.promotion_decision.purpose != "promotion"
                or run.promotion_decision.bound_digest
                != candidate.candidate_patch_sha256
            ):
                raise GraphBuildError("promotion decision does not bind the projected candidate")
            decision_ref = f"{run_ref}/promotion_decision"
            decision_node = self._project_decision(
                projection, run.promotion_decision, decision_ref, run.run_id, run.repo_id
            )
            self._add_edge(
                projection,
                source=decision_node,
                kind=GraphEdgeKind.AUTHORIZED,
                target=changeset,
                provenance=GraphProvenance.HUMAN_ATTESTED,
                source_ref=decision_ref,
            )
        if run.promotion_receipt is not None:
            receipt_ref = f"{run_ref}/promotion_receipt"
            projection.refs.add(receipt_ref)
            promotion = run.promotion_receipt
            promotion_data = promotion.model_dump(mode="json", exclude={"run_id", "expected_run_revision"})
            promotion_node = self._add_node(
                projection,
                kind=GraphNodeKind.PROMOTION_RECEIPT,
                identity={"run_id": run.run_id, "commit_sha": promotion.commit_sha},
                label=f"Promoted {promotion.commit_sha[:8]}",
                repo_id=run.repo_id,
                run_id=run.run_id,
                provenance=GraphProvenance.SERVER_OBSERVED,
                source_ref=receipt_ref,
                status="promoted",
                created_at=(
                    self._proof_time(run, ProofType.CANDIDATE_COMMITTED)
                    or self._run_time(run)
                ),
                data=promotion_data,
                digest_source=promotion.model_dump(mode="json"),
            )
            self._add_edge(
                projection,
                source=changeset,
                kind=GraphEdgeKind.PROMOTED_AS,
                target=promotion_node,
                provenance=GraphProvenance.SERVER_OBSERVED,
                source_ref=receipt_ref,
            )

    def _project_memory(self, projection: _Projection, memory: MemoryRevision) -> None:
        feedback = self.feedback.get(memory.feedback_id)
        if feedback is None:
            raise GraphBuildError(f"missing feedback: {memory.feedback_id}")
        if feedback.run_id != memory.evidence_run_id:
            raise GraphBuildError("feedback does not belong to the memory evidence run")
        if feedback.selected_hunk_id not in projection.hunks:
            raise GraphBuildError("feedback selected_hunk_id does not resolve")

        feedback_ref = f"feedback/{feedback.feedback_id}"
        projection.refs.add(feedback_ref)
        feedback_node = self._add_node(
            projection,
            kind=GraphNodeKind.FEEDBACK,
            identity=feedback.feedback_id,
            label="Human correction",
            repo_id=memory.repo_id,
            run_id=feedback.run_id,
            provenance=GraphProvenance.HUMAN_ATTESTED,
            source_ref=feedback_ref,
            status="submitted",
            created_at=feedback.occurred_at,
            data={
                "feedback_id": feedback.feedback_id,
                "evidence_event_id": feedback.evidence_event_id,
                "exact_correction": feedback.exact_correction,
                "correction_sha256": sha256_hex(feedback.exact_correction.encode()),
                "selected_hunk_id": feedback.selected_hunk_id,
                "selected_scope_id": feedback.selected_scope_id.value,
            },
            digest_source=feedback.model_dump(mode="json"),
        )
        self._add_edge(
            projection,
            source=feedback.selected_hunk_id,
            kind=GraphEdgeKind.TRIGGERED,
            target=feedback_node,
            provenance=GraphProvenance.HUMAN_ATTESTED,
            source_ref=feedback_ref,
        )

        memory_ref = f"memories/{memory.memory_id}/revisions/{memory.revision}"
        projection.refs.add(memory_ref)
        superseded = any(
            other.memory_id == memory.memory_id and other.revision > memory.revision
            for other in self.memories.values()
        )
        memory_node = self._add_node(
            projection,
            kind=GraphNodeKind.MEMORY_REVISION,
            identity={"memory_id": memory.memory_id, "revision": memory.revision},
            label=f"{memory.memory_id} revision {memory.revision}",
            repo_id=memory.repo_id,
            run_id=None,
            provenance=(
                GraphProvenance.HUMAN_ATTESTED
                if memory.decision is not None
                else GraphProvenance.SERVER_DERIVED
            ),
            source_ref=memory_ref,
            status=memory.state.value,
            created_at=feedback.occurred_at,
            data={
                "memory_id": memory.memory_id,
                "revision": memory.revision,
                "exact_text": memory.rule,
                "approval_state": memory.state.value,
                "repo_id": memory.repo_id,
                "path_globs": list(memory.path_globs),
                "task_tags": list(memory.task_tags),
                "supersession_state": "superseded" if superseded else "current",
            },
            digest_source=memory.model_dump(mode="json"),
        )
        projection.memories[(memory.memory_id, memory.revision)] = memory_node
        self._add_edge(
            projection,
            source=feedback_node,
            kind=GraphEdgeKind.LEARNED_AS,
            target=memory_node,
            provenance=GraphProvenance.SERVER_DERIVED,
            source_ref=memory_ref,
        )
        if memory.decision is not None:
            decision_ref = f"{memory_ref}/decision"
            decision_node = self._project_decision(
                projection, memory.decision, decision_ref, None, memory.repo_id
            )
            if memory.decision.value == MemoryDecisionValue.APPROVE:
                self._add_edge(
                    projection,
                    source=decision_node,
                    kind=GraphEdgeKind.APPROVED,
                    target=memory_node,
                    provenance=GraphProvenance.HUMAN_ATTESTED,
                    source_ref=decision_ref,
                )

    def _project_packet(
        self, projection: _Projection, run: RunRecord, packet: ContextPacket
    ) -> None:
        if (
            packet.consumer_run_id != run.run_id
            or packet.consumer_agent_profile_id != run.agent_profile_id
            or packet.task_id != run.task_id
            or packet.repo_id != run.repo_id
            or packet.base_sha != run.base_sha
            or packet.allowed_paths != run.allowed_paths
            or packet.allowed_tools != run.allowed_tools
            or packet.packet_id != run.context_packet_id
            or packet.packet_sha256 != run.context_packet_sha256
            or packet.source_graph_revision != run.source_graph_revision
            or packet.source_graph_hash != run.source_graph_hash
            or packet.selected_node_ids != run.selected_node_ids
        ):
            raise GraphBuildError("context packet does not match its consumer run")
        if any(node_id not in projection.nodes for node_id in packet.selected_node_ids):
            raise GraphBuildError("context packet selected_node_ids do not resolve")

        packet_memories = tuple(
            MemoryRef(memory_id=item.memory_id, revision=item.revision)
            for item in packet.approved_memories
        )
        if (
            packet.decision == ContextDecision.ALLOWED
            and run.injected_memories
            and packet_memories != run.injected_memories
        ):
            raise GraphBuildError("context packet memories do not match the run injection")
        for item in packet.approved_memories:
            memory = self.memories.get((item.memory_id, item.revision))
            if (
                memory is None
                or memory.state != MemoryState.APPROVED
                or item.exact_text != memory.rule
            ):
                raise GraphBuildError("context packet contains an unapproved or changed memory")

        receipt = self.injection_receipts.get(run.run_id)
        if run.injected_memories and receipt is None:
            raise GraphBuildError("injected run is missing its injection receipt")
        if receipt is not None and (
            receipt.session_id != run.session_id
            or receipt.consumer_agent_profile_id != run.agent_profile_id
            or receipt.packet_id != packet.packet_id
            or receipt.packet_sha256 != packet.packet_sha256
            or receipt.source_graph_revision != packet.source_graph_revision
            or receipt.source_graph_hash != packet.source_graph_hash
            or receipt.selected_node_ids != packet.selected_node_ids
            or receipt.memory_revisions != run.injected_memories
        ):
            raise GraphBuildError("injection receipt does not match the packet and run")

        packet_ref = f"context_packets/{packet.packet_id}"
        projection.refs.add(packet_ref)
        packet_node = self._add_node(
            projection,
            kind=GraphNodeKind.CONTEXT_PACKET,
            identity=packet.packet_id,
            label=f"Context for {packet.consumer_agent_profile_id}",
            repo_id=packet.repo_id,
            run_id=run.run_id,
            provenance=GraphProvenance.SERVER_DERIVED,
            source_ref=packet_ref,
            status=packet.decision.value,
            created_at=receipt.occurred_at if receipt is not None else self._run_time(run),
            data=packet.model_dump(mode="json"),
        )
        for item in packet.approved_memories:
            memory_node = projection.memories[(item.memory_id, item.revision)]
            self._add_edge(
                projection,
                source=memory_node,
                kind=GraphEdgeKind.PACKED_IN,
                target=packet_node,
                provenance=GraphProvenance.SERVER_DERIVED,
                source_ref=packet_ref,
            )
        if receipt is not None:
            receipt_ref = f"injection_receipts/{receipt.receipt_id}"
            projection.refs.add(receipt_ref)
            self._add_edge(
                projection,
                source=packet_node,
                kind=GraphEdgeKind.INJECTED_INTO,
                target=projection.run_nodes[run.run_id],
                provenance=GraphProvenance.SERVER_OBSERVED,
                source_ref=receipt_ref,
            )

    def _project_decision(
        self,
        projection: _Projection,
        decision: HumanDecision,
        source_ref: str,
        run_id: str | None,
        repo_id: str,
    ) -> str:
        projection.refs.add(source_ref)
        return self._add_node(
            projection,
            kind=GraphNodeKind.HUMAN_DECISION,
            identity={
                "decision_id": decision.decision_id,
                "purpose": decision.purpose,
                "source_ref": source_ref,
            },
            label=f"Human {decision.value.value}",
            repo_id=repo_id,
            run_id=run_id,
            provenance=GraphProvenance.HUMAN_ATTESTED,
            source_ref=source_ref,
            status=decision.value.value,
            created_at=decision.occurred_at,
            data={
                "decision_id": decision.decision_id,
                "actor": decision.actor,
                "purpose": decision.purpose,
                "decision": decision.value.value,
                "bound_digest": decision.bound_digest,
                "occurred_at": decision.occurred_at.isoformat(),
            },
            digest_source=decision.model_dump(mode="json"),
        )

    def _project_imports(
        self, projection: _Projection, runs: Iterable[RunRecord]
    ) -> None:
        for run in runs:
            parseable: dict[str, ast.AST] = {}
            for (after_run_id, path), content in self.after_files.items():
                if after_run_id != run.run_id:
                    continue
                source_ref = f"runs/{run.run_id}/after_files/{path}"
                projection.refs.add(source_ref)
                try:
                    text = content.decode("utf-8")
                    parseable[path] = ast.parse(text, filename=path)
                except (UnicodeDecodeError, SyntaxError, ValueError):
                    continue

            for (source_run_id, source_path), source_node in sorted(projection.files.items()):
                if source_run_id != run.run_id or source_path not in parseable:
                    continue
                source_bytes = self.after_files[(run.run_id, source_path)]
                if sha256_hex(source_bytes) != projection.nodes[source_node].data["after_sha256"]:
                    continue
                modules: set[str] = set()
                for item in ast.walk(parseable[source_path]):
                    if isinstance(item, ast.Import):
                        modules.update(alias.name for alias in item.names)
                    elif isinstance(item, ast.ImportFrom) and item.level == 0 and item.module:
                        modules.add(item.module)
                for module in sorted(modules):
                    candidates = (
                        f"{module.replace('.', '/')}.py",
                        f"{module.replace('.', '/')}/__init__.py",
                    )
                    target_path = next(
                        (
                            path
                            for path in candidates
                            if (run.run_id, path) in self.after_files and path in parseable
                        ),
                        None,
                    )
                    if target_path is None or target_path == source_path:
                        continue
                    target_node = projection.files.get((run.run_id, target_path))
                    target_ref = f"runs/{run.run_id}/after_files/{target_path}"
                    projection.refs.add(target_ref)
                    if target_node is None:
                        digest = sha256_hex(self.after_files[(run.run_id, target_path)])
                        target_node = self._add_node(
                            projection,
                            kind=GraphNodeKind.FILE,
                            identity={
                                "run_id": run.run_id,
                                "after_file": target_path,
                                "sha256": digest,
                            },
                            label=target_path,
                            repo_id=run.repo_id,
                            run_id=run.run_id,
                            provenance=GraphProvenance.SERVER_OBSERVED,
                            source_ref=target_ref,
                            status="advisory",
                            created_at=self._run_time(run),
                            data={
                                "path": target_path,
                                "before_sha256": digest,
                                "after_sha256": digest,
                                "language": self._language(target_path),
                            },
                            optional=True,
                        )
                        projection.files[(run.run_id, target_path)] = target_node
                    self._add_edge(
                        projection,
                        source=source_node,
                        kind=GraphEdgeKind.IMPORTS,
                        target=target_node,
                        provenance=GraphProvenance.SERVER_DERIVED,
                        source_ref=f"runs/{run.run_id}/after_files/{source_path}",
                        advisory=True,
                        optional=True,
                    )

    def _parse_hunks(
        self, run_id: str, candidate: CandidateArtifact
    ) -> tuple[HunkEvidence, ...]:
        try:
            patch = base64.b64decode(candidate.canonical_patch_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise GraphBuildError("candidate patch is not strict base64") from error
        if sha256_hex(patch) != candidate.candidate_patch_sha256:
            raise GraphBuildError("candidate patch hash does not match its bytes")
        if b"\x00" in patch or b"GIT binary patch" in patch or b"Binary files " in patch:
            raise GraphBuildError("binary patches are not graph evidence")
        try:
            patch.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GraphBuildError("canonical patch must be UTF-8 text") from error

        lines = patch.splitlines(keepends=True)
        starts = [index for index, line in enumerate(lines) if line.startswith(b"diff --git ")]
        if not starts or starts[0] != 0:
            raise GraphBuildError("patch must begin with a diff --git header")
        starts.append(len(lines))
        changes = {change.path: change for change in candidate.file_changes}
        section_paths: list[str] = []
        evidence: list[HunkEvidence] = []
        ordinal = 0

        for section_index in range(len(starts) - 1):
            start, end = starts[section_index], starts[section_index + 1]
            match = _DIFF_HEADER.fullmatch(lines[start])
            if match is None:
                raise GraphBuildError("quoted, renamed, or malformed diff paths are unsupported")
            try:
                old_path = _repo_path(match.group(1).decode("utf-8"))
                path = _repo_path(match.group(2).decode("utf-8"))
            except UnicodeDecodeError as error:
                raise GraphBuildError("diff paths must be UTF-8") from error
            if old_path != path or path not in changes or path in section_paths:
                raise GraphBuildError("patch sections must uniquely match CandidateArtifact paths")
            section_paths.append(path)

            hunk_starts = [
                index
                for index in range(start + 1, end)
                if lines[index].startswith(b"@@ ")
            ]
            if not hunk_starts:
                raise GraphBuildError(f"changed file has no textual hunks: {path}")
            metadata = lines[start + 1 : hunk_starts[0]]
            old_markers = [line for line in metadata if line.startswith(b"--- ")]
            new_markers = [line for line in metadata if line.startswith(b"+++ ")]
            expected_old = b"--- /dev/null\n" if changes[path].before_sha256 is None else f"--- a/{path}\n".encode()
            expected_new = f"+++ b/{path}\n".encode()
            if old_markers != [expected_old] or new_markers != [expected_new]:
                raise GraphBuildError(f"patch file markers do not match CandidateArtifact: {path}")
            allowed_metadata = (b"index ", b"new file mode ", b"--- ", b"+++ ")
            if any(not line.startswith(allowed_metadata) for line in metadata):
                raise GraphBuildError(f"unsupported diff metadata for {path}")

            hunk_starts.append(end)
            for hunk_index in range(len(hunk_starts) - 1):
                hunk_start, hunk_end = hunk_starts[hunk_index], hunk_starts[hunk_index + 1]
                raw = b"".join(lines[hunk_start:hunk_end])
                header = lines[hunk_start].decode("utf-8").rstrip("\n")
                header_match = _HUNK_HEADER.fullmatch(header)
                if header_match is None:
                    raise GraphBuildError(f"malformed unified hunk header in {path}")
                old_start = int(header_match.group(1))
                old_lines = int(header_match.group(2) or 1)
                new_start = int(header_match.group(3))
                new_lines = int(header_match.group(4) or 1)
                actual_old = actual_new = 0
                for body_line in lines[hunk_start + 1 : hunk_end]:
                    if body_line.startswith(b"\\ No newline at end of file"):
                        continue
                    prefix = body_line[:1]
                    if prefix == b" ":
                        actual_old += 1
                        actual_new += 1
                    elif prefix == b"-":
                        actual_old += 1
                    elif prefix == b"+":
                        actual_new += 1
                    else:
                        raise GraphBuildError(f"malformed unified hunk body in {path}")
                if (actual_old, actual_new) != (old_lines, new_lines):
                    raise GraphBuildError(f"hunk line counts do not match its header in {path}")
                exact_hash = sha256_hex(raw)
                ordinal += 1
                hunk_id = _stable_id(
                    GraphNodeKind.HUNK.value,
                    {
                        "run_id": run_id,
                        "candidate_patch_sha256": candidate.candidate_patch_sha256,
                        "path": path,
                        "ordinal": ordinal,
                        "exact_hunk_sha256": exact_hash,
                    },
                )
                change = changes[path]
                evidence.append(
                    HunkEvidence(
                        hunk_id=hunk_id,
                        path=path,
                        old_start=old_start,
                        old_lines=old_lines,
                        new_start=new_start,
                        new_lines=new_lines,
                        before_sha256=change.before_sha256,
                        after_sha256=change.after_sha256,
                        canonical_patch_sha256=candidate.candidate_patch_sha256,
                        exact_hunk_sha256=exact_hash,
                        candidate_revision=candidate.candidate_revision,
                        unified_diff=raw.decode("utf-8"),
                    )
                )
        if tuple(sorted(section_paths)) != candidate.changed_paths:
            raise GraphBuildError("canonical patch paths do not equal changed_paths")
        return tuple(evidence)

    def _bounded_response(
        self, projection: _Projection, current_run_id: str, query: GraphQuery
    ) -> GraphResponse:
        nodes = dict(projection.nodes)
        if query.current_run_only or not query.show_memory_origin:
            nodes = {
                node_id: node
                for node_id, node in nodes.items()
                if node.run_id in {None, current_run_id}
            }
        if query.path_prefix is not None:
            prefix = query.path_prefix.rstrip("/")
            nodes = {
                node_id: node
                for node_id, node in nodes.items()
                if node.kind not in {GraphNodeKind.FILE, GraphNodeKind.HUNK}
                or self._path_matches(node.data["path"], prefix)
            }
        if query.kinds:
            kinds = set(query.kinds)
            nodes = {node_id: node for node_id, node in nodes.items() if node.kind in kinds}
        edges = {
            edge_id: edge
            for edge_id, edge in projection.edges.items()
            if edge.source in nodes and edge.target in nodes
        }

        filtered_node_count = len(nodes)
        filtered_edge_count = len(edges)
        omitted_by_kind: dict[str, int] = {}

        def cap_kind(kind: GraphNodeKind, limit: int, label: str, *, optional_only: bool = False) -> None:
            candidates = [
                node_id
                for node_id, node in nodes.items()
                if node.kind == kind
                and (not optional_only or node_id in projection.optional_nodes)
            ]
            ordered = sorted(candidates, key=lambda node_id: self._node_rank(nodes[node_id], current_run_id, projection))
            for node_id in ordered[limit:]:
                nodes.pop(node_id)
            if len(ordered) > limit:
                omitted_by_kind[label] = len(ordered) - limit

        cap_kind(GraphNodeKind.HUNK, self.contract.caps.max_hunks, "hunks")
        cap_kind(GraphNodeKind.MEMORY_REVISION, self.contract.caps.max_memories, "memories")
        cap_kind(
            GraphNodeKind.FILE,
            self.contract.caps.max_related_files,
            "related_files",
            optional_only=True,
        )

        ordered_nodes = sorted(
            nodes,
            key=lambda node_id: self._node_rank(nodes[node_id], current_run_id, projection),
        )
        nodes = {
            node_id: nodes[node_id]
            for node_id in ordered_nodes[: self.contract.caps.max_nodes]
        }
        candidate_edges = {
            edge_id: edge
            for edge_id, edge in edges.items()
            if edge.source in nodes and edge.target in nodes
        }
        ordered_edges = sorted(
            candidate_edges,
            key=lambda edge_id: (edge_id in projection.optional_edges, edge_id),
        )
        edges = {
            edge_id: candidate_edges[edge_id]
            for edge_id in ordered_edges[: self.contract.caps.max_edges]
        }

        omitted_nodes = filtered_node_count - len(nodes)
        omitted_edges = filtered_edge_count - len(edges)
        omitted_counts = {
            **omitted_by_kind,
            **({"nodes": omitted_nodes} if omitted_nodes else {}),
            **({"edges": omitted_edges} if omitted_edges else {}),
        }
        response_data = {
            "revision": self.contract.graph_revision,
            "nodes": tuple(nodes[node_id] for node_id in sorted(nodes)),
            "edges": tuple(edges[edge_id] for edge_id in sorted(edges)),
            "truncated": bool(omitted_counts),
            "omitted_counts": omitted_counts,
        }
        return GraphResponse(
            **response_data,
            graph_hash=canonical_json_sha256(
                {
                    **response_data,
                    "nodes": [node.model_dump(mode="json") for node in response_data["nodes"]],
                    "edges": [edge.model_dump(mode="json") for edge in response_data["edges"]],
                }
            ),
        )

    def _add_node(
        self,
        projection: _Projection,
        *,
        kind: GraphNodeKind,
        identity: Any,
        label: str,
        repo_id: str,
        run_id: str | None,
        provenance: GraphProvenance,
        source_ref: str,
        status: str,
        created_at: datetime,
        data: dict[str, Any],
        detail_data: dict[str, Any] | None = None,
        digest_source: Any | None = None,
        node_id: str | None = None,
        optional: bool = False,
    ) -> str:
        detail_data = detail_data or data
        allowed = set(self.contract.node_data_fields[kind])
        if set(detail_data) != allowed or not set(data) <= allowed:
            raise GraphBuildError(f"{kind.value} data does not match the frozen allowlist")
        node_id = node_id or _stable_id(kind.value, identity)
        digest = canonical_json_sha256(
            {
                "kind": kind.value,
                "label": label,
                "repo_id": repo_id,
                "run_id": run_id,
                "provenance": provenance.value,
                "source_ref": source_ref,
                "status": status,
                "created_at": created_at.isoformat(),
                "data": detail_data,
                "source": digest_source,
            }
        )
        common = {
            "id": node_id,
            "kind": kind,
            "label": label,
            "repo_id": repo_id,
            "run_id": run_id,
            "provenance": provenance,
            "source_ref": source_ref,
            "digest": digest,
            "status": status,
            "created_at": created_at,
        }
        node = GraphNode(**common, data=data)
        detail = GraphNode(**common, data=detail_data)
        if node_id in projection.nodes and projection.details[node_id] != detail:
            raise GraphBuildError(f"node ID collision: {node_id}")
        projection.nodes[node_id] = node
        projection.details[node_id] = detail
        if optional:
            projection.optional_nodes.add(node_id)
        return node_id

    def _add_edge(
        self,
        projection: _Projection,
        *,
        source: str,
        kind: GraphEdgeKind,
        target: str,
        provenance: GraphProvenance,
        source_ref: str,
        advisory: bool = False,
        optional: bool = False,
    ) -> str:
        content = {
            "source": source,
            "kind": kind.value,
            "target": target,
            "provenance": provenance.value,
            "source_ref": source_ref,
            "advisory": advisory,
        }
        edge_id = _stable_id("edge", content)
        edge = GraphEdge(id=edge_id, digest=canonical_json_sha256(content), **content)
        if edge_id in projection.edges and projection.edges[edge_id] != edge:
            raise GraphBuildError(f"edge ID collision: {edge_id}")
        projection.edges[edge_id] = edge
        if optional:
            projection.optional_edges.add(edge_id)
        return edge_id

    @staticmethod
    def _language(path: str) -> str:
        return "python" if path.endswith(".py") else "unknown"

    @staticmethod
    def _path_matches(path: str, prefix: str) -> bool:
        return path == prefix or path.startswith(f"{prefix}/")

    @staticmethod
    def _proof_time(run: RunRecord, proof_type: ProofType) -> datetime | None:
        return next(
            (item.occurred_at for item in run.proof if item.type == proof_type),
            None,
        )

    def _run_time(self, run: RunRecord) -> datetime:
        candidates = [
            run.created_at,
            *(item.occurred_at for item in run.proof),
            *(item.occurred_at for item in run.policy_checks),
            run.promotion_decision.occurred_at if run.promotion_decision else None,
        ]
        known = [item for item in candidates if item is not None]
        if not known:
            raise GraphBuildError(f"run has no authoritative timestamp: {run.run_id}")
        return min(known)

    def _candidate_time(self, run: RunRecord) -> datetime:
        return (
            self._proof_time(run, ProofType.COMPLETION_DENIED)
            or min((item.occurred_at for item in run.policy_checks), default=None)
            or self._run_time(run)
        )

    @staticmethod
    def _node_rank(
        node: GraphNode, current_run_id: str, projection: _Projection
    ) -> tuple[int, int, str]:
        return (
            1 if node.id in projection.optional_nodes else 0,
            0 if node.run_id in {None, current_run_id} else 1,
            node.id,
        )
