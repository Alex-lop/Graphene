from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatchcase

from ..hashing import canonical_json_sha256
from ..models import (
    AgentProfile,
    ContextDecision,
    ContextPacket,
    GraphMvpContract,
    MemoryRevision,
    MemoryState,
    RelatedFile,
    TaskId,
    TaskSpec,
)
from .handoff import (
    AUTH_CAPABILITIES,
    CompiledHandoff,
    HandoffCandidate,
    HandoffCompileError,
    build_injection_receipt,
    compile_handoff,
    render_fresh_prompt,
    source_candidate_set_sha256,
    start_handoff,
)

_PROFILE_IDS = (
    "platform-maintainer@1",
    "auth-maintainer@1",
    "billing-observer@1",
)


def load_catalog(contract: GraphMvpContract) -> tuple[AgentProfile, ...]:
    """Return the contract-owned catalog after checking its frozen identities."""
    profile_ids = tuple(profile.agent_profile_id for profile in contract.catalog)
    if profile_ids != _PROFILE_IDS or any(
        binding.agent_profile_id not in profile_ids for binding in contract.task_profiles
    ):
        raise ValueError("catalog profiles and task bindings must match the frozen contract")
    return contract.catalog


def profile_for_task(contract: GraphMvpContract, task_id: TaskId) -> AgentProfile:
    catalog = {profile.agent_profile_id: profile for profile in load_catalog(contract)}
    binding = next(
        (binding for binding in contract.task_profiles if binding.task_id == task_id),
        None,
    )
    if binding is None:
        raise ValueError(f"task has no catalog binding: {task_id}")
    return catalog[binding.agent_profile_id]


def _matches(path: str, globs: Iterable[str]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in globs)


def _memory_applies(
    memory: MemoryRevision,
    task: TaskSpec,
    profile: AgentProfile,
    effective_paths: tuple[str, ...],
) -> bool:
    return (
        memory.state == MemoryState.APPROVED
        and memory.repo_id == task.repo_id
        and set(memory.task_tags) <= set(task.task_tags)
        and set(memory.task_tags) <= set(profile.memory_access)
        and any(_matches(path, memory.path_globs) for path in task.target_paths)
        and memory.required_test_path in effective_paths
    )


def build_context_packet(
    *,
    contract: GraphMvpContract,
    task: TaskSpec,
    consumer_run_id: str,
    consumer_agent_profile_id: str,
    packet_id: str,
    base_sha: str,
    tool_names: Iterable[str],
    memories: Iterable[MemoryRevision],
    source_graph_hash: str,
    related_files: Iterable[RelatedFile] = (),
    selected_node_ids: Iterable[str] = (),
) -> ContextPacket:
    catalog = {profile.agent_profile_id: profile for profile in load_catalog(contract)}
    try:
        profile = catalog[consumer_agent_profile_id]
    except KeyError as error:
        raise ValueError(f"unknown agent profile: {consumer_agent_profile_id}") from error

    bound_profile = profile_for_task(contract, task.task_id)
    requested_paths = tuple(task.expected_changed_paths)
    effective_paths = tuple(
        path for path in requested_paths if _matches(path, profile.allowed_paths)
    )
    effective_tools = tuple(tool for tool in tool_names if tool in profile.allowed_tools)
    allowed = (
        profile.agent_profile_id == bound_profile.agent_profile_id
        and task.repo_id == contract.repo_id
        and task.repo_id in profile.repo_ids
        and bool(requested_paths)
        and effective_paths == requested_paths
        and bool(effective_tools)
        and all(_matches(path, profile.allowed_paths) for path in task.target_paths)
    )

    if allowed:
        packet_memories = [
            {
                "memory_id": memory.memory_id,
                "revision": memory.revision,
                "exact_text": memory.rule,
            }
            for memory in sorted(memories, key=lambda item: (item.memory_id, item.revision))
            if _memory_applies(memory, task, profile, effective_paths)
        ]
        packet_files = [
            item.model_dump(mode="json")
            for item in sorted(related_files, key=lambda item: (item.path, item.reason))
            if item.path in effective_paths
        ]
        packet_node_ids = tuple(sorted(selected_node_ids))
        decision = ContextDecision.ALLOWED
    else:
        effective_paths = ()
        effective_tools = ()
        packet_memories = []
        packet_files = []
        packet_node_ids = ()
        decision = ContextDecision.DENIED_OUT_OF_SCOPE

    payload = {
        "packet_id": packet_id,
        "consumer_run_id": consumer_run_id,
        "consumer_agent_profile_id": profile.agent_profile_id,
        "task_id": task.task_id.value,
        "repo_id": task.repo_id,
        "base_sha": base_sha,
        "allowed_paths": effective_paths,
        "allowed_tools": effective_tools,
        "approved_memories": packet_memories,
        "related_files": packet_files,
        "required_test_profile": contract.required_test_profile,
        "source_graph_revision": contract.graph_revision,
        "source_graph_hash": source_graph_hash,
        "selected_node_ids": packet_node_ids,
        "decision": decision.value,
    }
    return ContextPacket.model_validate(
        {**payload, "packet_sha256": canonical_json_sha256(payload)}
    )


__all__ = [
    "AUTH_CAPABILITIES",
    "CompiledHandoff",
    "HandoffCandidate",
    "HandoffCompileError",
    "build_context_packet",
    "build_injection_receipt",
    "compile_handoff",
    "load_catalog",
    "profile_for_task",
    "render_fresh_prompt",
    "source_candidate_set_sha256",
    "start_handoff",
]
