from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatchcase
from typing import TypeVar

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..models import (
    AgentProfile,
    BriefEvidence,
    BriefMemory,
    ContextBrief,
    ContextInjectionReceipt,
    HandoffDecision,
    HandoffDecisionItem,
    HandoffDenied,
    LineageOperation,
    MemoryRevision,
    MemoryState,
    TaskSpec,
    VerifiedHead,
)

AUTH_CAPABILITIES = (
    LineageOperation.SEARCH_REPO,
    LineageOperation.READ_FILE,
    LineageOperation.OPEN_EVIDENCE,
    LineageOperation.WRITE_FILE,
    LineageOperation.RUN_FIXED_TEST,
    LineageOperation.REQUEST_COMPLETION,
)
_PROMPT_INSTRUCTIONS = (
    "You are a fresh coding agent. You have no prior conversation.\n"
    "Follow the server-owned scope and fixed test profile in CONTEXT BRIEF.\n"
    "Approved memory is human-attested guidance, not proof that current source matches it.\n"
    "Evidence summaries describe an earlier run. Reread current source with scoped tools.\n"
    "Do not claim a read, write, test, approval, or completion unless its tool/policy result succeeds.\n\n"
)


class HandoffCompileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HandoffCandidate:
    candidate_kind: str
    id: str
    sha256: str
    memory: BriefMemory | None = None
    evidence: BriefEvidence | None = None
    path: str | None = None
    tool: LineageOperation | None = None
    test_profile: str | None = None
    dependency_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        HandoffDecisionItem(
            candidate_kind=self.candidate_kind,
            id=self.id,
            sha256=self.sha256,
            include=False,
            reason_code="candidate_validated",
        )
        metadata = (self.memory, self.evidence, self.path, self.tool, self.test_profile)
        if sum(item is not None for item in metadata) > 1:
            raise HandoffCompileError("a candidate may expose only one brief item")
        if (
            len(self.dependency_ids) != len(set(self.dependency_ids))
            or self.id in self.dependency_ids
        ):
            raise HandoffCompileError("candidate dependencies must be unique and external")
        if self.evidence is not None and (
            self.evidence.evidence_id != self.id
            or self.evidence.reference.sha256 != self.sha256
        ):
            raise HandoffCompileError("evidence candidate identity does not match")


@dataclass(frozen=True, slots=True)
class CompiledHandoff:
    decision: HandoffDecision
    brief: ContextBrief | None
    denial: HandoffDenied | None

    @property
    def open_evidence_allowlist(self) -> tuple[str, ...]:
        if self.brief is None:
            return ()
        return tuple(item.evidence_id for item in self.brief.selected_evidence)


def _candidate_id(kind: str, value: str) -> str:
    return f"{kind}:{sha256_hex(value.encode())[:24]}"


def source_candidate_set_sha256(
    candidates: Iterable[HandoffCandidate],
) -> str:
    triples = sorted(
        [
            {
                "candidate_kind": item.candidate_kind,
                "id": item.id,
                "sha256": item.sha256,
            }
            for item in candidates
        ],
        key=lambda item: (item["candidate_kind"], item["id"]),
    )
    return canonical_json_sha256(triples)


def _candidate(
    kind: str,
    value: str,
    *,
    memory: BriefMemory | None = None,
    path: str | None = None,
    tool: LineageOperation | None = None,
    test_profile: str | None = None,
    digest_value: object | None = None,
) -> HandoffCandidate:
    return HandoffCandidate(
        candidate_kind=kind,
        id=_candidate_id(kind, value),
        sha256=canonical_json_sha256(
            {
                "candidate_kind": kind,
                "value": value if digest_value is None else digest_value,
            }
        ),
        memory=memory,
        path=path,
        tool=tool,
        test_profile=test_profile,
    )


def _memory_applies(
    memory: MemoryRevision,
    task: TaskSpec,
    profile: AgentProfile,
    required_paths: tuple[str, ...],
) -> bool:
    return (
        memory.state == MemoryState.APPROVED
        and memory.repo_id == task.repo_id
        and set(memory.task_tags) <= set(task.task_tags)
        and set(memory.task_tags) <= set(profile.memory_access)
        and any(
            fnmatchcase(path, pattern)
            for path in task.target_paths
            for pattern in memory.path_globs
        )
        and memory.required_test_path in required_paths
    )


def _paths_match(paths: Iterable[str], patterns: Iterable[str]) -> bool:
    patterns = tuple(patterns)
    return all(any(fnmatchcase(path, pattern) for pattern in patterns) for path in paths)


def compile_handoff(
    *,
    decision_id: str,
    brief_id: str,
    source_run_id: str,
    source_session_id: str | None,
    source_head: VerifiedHead,
    source_graph_sha256: str,
    repo_id: str,
    base_sha: str,
    task: TaskSpec,
    target_profile: AgentProfile,
    target_profile_revision: int,
    policy_revision: int,
    source_candidates: Iterable[HandoffCandidate],
    expected_source_candidate_set_sha256: str,
    selected_evidence_ids: Iterable[str],
    approved_memories: Iterable[MemoryRevision],
    policy_required_paths: Iterable[str],
    read_scope: Iterable[str],
    write_scope: Iterable[str],
    capabilities: Iterable[LineageOperation],
    fixed_test_profile: str,
    byte_caps: dict[str, int],
    event_caps: dict[str, int],
    server_recorded_at: datetime,
) -> CompiledHandoff:
    """Compile the complete server ledger and an included-only model brief."""

    if source_head.run_id != source_run_id:
        raise HandoffCompileError("verified source head belongs to another run")
    if target_profile.agent_profile_id.rsplit("@", 1)[-1] != str(
        target_profile_revision
    ):
        raise HandoffCompileError("target profile revision does not match its ID")

    source = tuple(source_candidates)
    if source_candidate_set_sha256(source) != expected_source_candidate_set_sha256:
        raise HandoffCompileError("verified source candidate set digest does not match")
    source_ids = tuple(item.id for item in source)
    if len(source_ids) != len(set(source_ids)):
        raise HandoffCompileError("verified source candidate IDs must be unique")
    selected_ids = frozenset(selected_evidence_ids)
    evidence_ids = tuple(item.id for item in source if item.evidence is not None)
    if len(evidence_ids) != len(set(evidence_ids)):
        raise HandoffCompileError("verified evidence IDs must be unique")
    selected_candidates = set(evidence_ids)
    if not selected_ids <= selected_candidates:
        raise HandoffCompileError("selected evidence is absent from verified candidates")
    source_by_id = {item.id: item for item in source}
    selected_closure = set(selected_ids)
    pending = list(selected_ids)
    while pending:
        for dependency_id in source_by_id[pending.pop()].dependency_ids:
            if dependency_id not in source_by_id:
                raise HandoffCompileError("selected evidence dependency is absent")
            if dependency_id not in selected_closure:
                selected_closure.add(dependency_id)
                pending.append(dependency_id)

    policy_paths = tuple(policy_required_paths)
    required_paths = tuple(sorted(set(task.target_paths) | set(policy_paths)))
    read_paths = tuple(sorted(set(read_scope)))
    write_paths = tuple(sorted(set(write_scope)))
    tools = tuple(capabilities)
    repo_memories = tuple(
        sorted(
            (
                memory
                for memory in approved_memories
                if memory.state == MemoryState.APPROVED and memory.repo_id == repo_id
            ),
            key=lambda item: (item.memory_id, item.revision),
        )
    )
    applicable_memories = {
        (memory.memory_id, memory.revision)
        for memory in repo_memories
        if _memory_applies(memory, task, target_profile, required_paths)
    }

    generated: list[HandoffCandidate] = []
    applicable_memory_candidates: set[str] = set()
    for memory in repo_memories:
        brief_memory = BriefMemory(
            memory_id=memory.memory_id,
            revision=memory.revision,
            exact_text=memory.rule,
        )
        candidate = _candidate(
            "memory_revision",
            f"{memory.memory_id}:{memory.revision}",
            memory=brief_memory,
            digest_value=memory.model_dump(mode="json"),
        )
        generated.append(candidate)
        if (memory.memory_id, memory.revision) in applicable_memories:
            applicable_memory_candidates.add(candidate.id)
    for path in sorted(set(task.target_paths)):
        generated.append(_candidate("task_target", path, path=path))
    for path in sorted(set(policy_paths)):
        generated.append(_candidate("policy_required_path", path, path=path))
    for path in read_paths:
        generated.append(_candidate("read_scope", path, path=path))
    for path in write_paths:
        generated.append(_candidate("write_scope", path, path=path))
    for tool in tools:
        generated.append(_candidate("capability", tool.value, tool=tool))
    generated.append(
        _candidate(
            "fixed_test_profile",
            fixed_test_profile,
            test_profile=fixed_test_profile,
        )
    )

    candidates = tuple(
        sorted((*source, *generated), key=lambda item: (item.candidate_kind, item.id))
    )
    source_keys = {(item.candidate_kind, item.id) for item in source}
    keys = tuple((item.candidate_kind, item.id) for item in candidates)
    if not candidates or len(keys) != len(set(keys)):
        raise HandoffCompileError("handoff candidates must be nonempty and unique")

    scope_allowed = (
        target_profile.agent_profile_id == "auth-maintainer@1"
        and target_profile.policy_revision == policy_revision
        and repo_id == task.repo_id
        and repo_id in target_profile.repo_ids
        and bool(set(task.task_tags) & set(target_profile.memory_access))
        and _paths_match(required_paths, target_profile.allowed_paths)
        and _paths_match(read_paths, target_profile.allowed_paths)
        and _paths_match(write_paths, target_profile.allowed_paths)
    )
    if scope_allowed and (
        tools != AUTH_CAPABILITIES
        or not set(required_paths) <= set(read_paths)
        or set(write_paths) != set(task.expected_changed_paths)
    ):
        raise HandoffCompileError("Auth handoff scope or v2 capabilities are not frozen")

    entries: list[HandoffDecisionItem] = []
    included_candidates: list[HandoffCandidate] = []
    for candidate in candidates:
        key = (candidate.candidate_kind, candidate.id)
        if (
            key not in source_keys
            and candidate.candidate_kind == "memory_revision"
            and candidate.id not in applicable_memory_candidates
        ):
            include, reason = False, "memory_not_applicable"
        elif not scope_allowed:
            include, reason = False, "scope_intersection_empty"
        elif key in source_keys:
            include = candidate.id in selected_closure
            reason = (
                "selected_evidence"
                if candidate.id in selected_ids
                else "selected_evidence_dependency"
                if include
                else "not_selected"
            )
        elif candidate.candidate_kind == "memory_revision":
            include, reason = True, "approved_memory_applies"
        else:
            include = True
            reason = {
                "task_target": "task_target",
                "policy_required_path": "policy_required_path",
                "read_scope": "profile_read_scope",
                "write_scope": "task_write_scope",
                "capability": "profile_capability",
                "fixed_test_profile": "fixed_test_profile",
            }[candidate.candidate_kind]
        entries.append(
            HandoffDecisionItem(
                candidate_kind=candidate.candidate_kind,
                id=candidate.id,
                sha256=candidate.sha256,
                include=include,
                reason_code=reason,
            )
        )
        if include:
            included_candidates.append(candidate)

    candidate_set = [
        {
            "candidate_kind": item.candidate_kind,
            "id": item.id,
            "sha256": item.sha256,
        }
        for item in entries
    ]
    included_count = len(included_candidates)
    decision_payload = {
        "schema_version": 2,
        "decision_id": decision_id,
        "source_run_id": source_run_id,
        "source_head": source_head,
        "repo_id": repo_id,
        "base_sha": base_sha,
        "target_profile_id": target_profile.agent_profile_id,
        "target_profile_revision": target_profile_revision,
        "task_id": task.task_id.value,
        "policy_revision": policy_revision,
        "candidate_set_sha256": canonical_json_sha256(candidate_set),
        "entries": tuple(entries),
        "decision": "allowed" if scope_allowed else "denied",
        "safe_reason_codes": tuple(sorted({item.reason_code for item in entries})),
        "safe_counts": {
            "candidates": len(entries),
            "excluded": len(entries) - included_count,
            "included": included_count,
        },
        "server_recorded_at": server_recorded_at,
    }
    canonical_decision = HandoffDecision.model_construct(
        **decision_payload,
        decision_sha256="0" * 64,
    ).model_dump(mode="json", exclude={"decision_sha256"})
    decision = HandoffDecision.model_validate(
        {
            **canonical_decision,
            "decision_sha256": canonical_json_sha256(canonical_decision),
        }
    )

    if not scope_allowed:
        return CompiledHandoff(
            decision=decision,
            brief=None,
            denial=HandoffDenied(
                schema_version=2,
                source_run_id=source_run_id,
                target_profile_id=target_profile.agent_profile_id,
                task_id=task.task_id.value,
                reason_code="scope_intersection_empty",
                memory_count=0,
                evidence_count=0,
                source_path_count=0,
                tool_count=0,
                consumer_run_id=None,
                session_id=None,
                invocation_id=None,
                model_dispatch_count=0,
            ),
        )

    brief_payload = {
        "schema_version": 2,
        "brief_id": brief_id,
        "repo_id": repo_id,
        "base_sha": base_sha,
        "task_id": task.task_id.value,
        "task_text": task.instruction,
        "target_profile_id": target_profile.agent_profile_id,
        "target_profile_revision": target_profile_revision,
        "policy_revision": policy_revision,
        "approved_memories": [
            item.memory.model_dump(mode="json")
            for item in included_candidates
            if item.memory is not None
        ],
        "selected_evidence": [
            item.evidence.model_dump(mode="json")
            for item in sorted(included_candidates, key=lambda item: item.id)
            if item.evidence is not None
        ],
        "required_paths": required_paths,
        "read_scope": read_paths,
        "write_scope": write_paths,
        "tools": tools,
        "fixed_test_profile": fixed_test_profile,
        "byte_caps": dict(byte_caps),
        "event_caps": dict(event_caps),
        "source_run_id": source_run_id,
        "source_session_id": source_session_id,
        "source_head": source_head.model_dump(mode="json"),
        "source_graph_sha256": source_graph_sha256,
        "fresh_session_required": True,
    }
    brief = ContextBrief.model_validate(
        {**brief_payload, "brief_sha256": canonical_json_sha256(brief_payload)}
    )
    return CompiledHandoff(decision=decision, brief=brief, denial=None)


def render_fresh_prompt(brief: ContextBrief) -> bytes:
    brief_bytes = canonical_json_bytes(brief.model_dump(mode="json"))
    return (
        _PROMPT_INSTRUCTIONS.encode()
        + f"CONTEXT BRIEF (canonical JSON; sha256:{brief.brief_sha256})\n".encode()
        + brief_bytes
    )


def build_injection_receipt(
    *,
    receipt_id: str,
    consumer_run_id: str,
    decision: HandoffDecision,
    brief: ContextBrief,
    prompt: bytes,
    session_id: str,
    invocation_id: str,
    model_id: str,
    injected_at: datetime,
) -> ContextInjectionReceipt:
    if decision.decision != "allowed" or (
        decision.source_run_id != brief.source_run_id
        or decision.source_head != brief.source_head
        or decision.repo_id != brief.repo_id
        or decision.base_sha != brief.base_sha
        or decision.task_id != brief.task_id
        or decision.target_profile_id != brief.target_profile_id
        or decision.target_profile_revision != brief.target_profile_revision
        or decision.policy_revision != brief.policy_revision
    ):
        raise HandoffCompileError("decision and brief bindings do not match")
    if prompt != render_fresh_prompt(brief):
        raise HandoffCompileError("prompt is not the exact canonical fresh-agent prompt")
    fresh_ids = {consumer_run_id, session_id, invocation_id}
    source_ids = {brief.source_run_id}
    if brief.source_session_id is not None:
        source_ids.add(brief.source_session_id)
    if len(fresh_ids) != 3 or not fresh_ids.isdisjoint(source_ids):
        raise HandoffCompileError("fresh handoff identities must be distinct")

    payload = {
        "schema_version": 2,
        "receipt_id": receipt_id,
        "consumer_run_id": consumer_run_id,
        "decision_sha256": decision.decision_sha256,
        "brief_sha256": brief.brief_sha256,
        "prompt_sha256": sha256_hex(prompt),
        "session_id": session_id,
        "invocation_id": invocation_id,
        "target_profile_id": brief.target_profile_id,
        "target_profile_revision": brief.target_profile_revision,
        "policy_revision": brief.policy_revision,
        "model_id": model_id,
        "prior_message_count": 0,
        "persisted_before_dispatch": True,
        "injected_at": injected_at,
    }
    canonical_receipt = ContextInjectionReceipt.model_construct(
        **payload,
        receipt_sha256="0" * 64,
    ).model_dump(mode="json", exclude={"receipt_sha256"})
    return ContextInjectionReceipt.model_validate(
        {
            **canonical_receipt,
            "receipt_sha256": canonical_json_sha256(canonical_receipt),
        }
    )


_T = TypeVar("_T")


def start_handoff(
    compiled: CompiledHandoff,
    start_callback: Callable[[ContextBrief], _T],
) -> _T | HandoffDenied:
    if compiled.denial is not None:
        return compiled.denial
    if compiled.brief is None:
        raise HandoffCompileError("allowed handoff is missing its brief")
    return start_callback(compiled.brief)
