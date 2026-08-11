from datetime import datetime, timezone
from pathlib import Path

import pytest

from reviewlatch.context import build_context_packet, load_catalog, profile_for_task
from reviewlatch.hashing import canonical_json_sha256
from reviewlatch.models import (
    ContextDecision,
    GoldenContract,
    GraphMvpContract,
    HumanDecision,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    RelatedFile,
    TaskSpec,
)

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
GRAPH = GraphMvpContract.model_validate_json(
    (ROOT / "contracts/graph_mvp.json").read_text()
)
BASE_SHA = "a" * 40
GRAPH_HASH = "b" * 64


def _memory(state: MemoryState, memory_id: str = "mem_auth_review") -> MemoryRevision:
    spec = GOLDEN.memory
    proposed = MemoryRevision(
        memory_id=memory_id,
        revision=1,
        state=MemoryState.PROPOSED,
        rule=spec.rule,
        repo_id=spec.repo_id,
        path_globs=spec.path_globs,
        task_tags=spec.task_tags,
        required_test_path=spec.required_test_path,
        required_check=spec.required_check,
        evidence_run_id="baseline_run",
        feedback_id="feedback_1",
    )
    if state == MemoryState.PROPOSED:
        return proposed
    decision = HumanDecision(
        decision_id=f"decision_{state.value}",
        value=(
            MemoryDecisionValue.APPROVE
            if state == MemoryState.APPROVED
            else MemoryDecisionValue.REJECT
        ),
        purpose="memory",
        bound_digest=canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        ),
        occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    return MemoryRevision.model_validate(
        {**proposed.model_dump(mode="json"), "state": state, "decision": decision}
    )


def _build(task: TaskSpec, profile: str, **overrides: object):
    values = {
        "contract": GRAPH,
        "task": task,
        "consumer_run_id": "adapted_run",
        "consumer_agent_profile_id": profile,
        "packet_id": "ctx_adapted",
        "base_sha": BASE_SHA,
        "tool_names": GOLDEN.tool_names,
        "memories": (_memory(MemoryState.APPROVED),),
        "source_graph_hash": GRAPH_HASH,
        "related_files": (
            RelatedFile(path="app/auth/limiter.py", reason="task target"),
            RelatedFile(path="docs/security.md", reason="out of scope"),
        ),
        "selected_node_ids": ("node:z", "node:a"),
    }
    values.update(overrides)
    return build_context_packet(**values)


def _assert_denied(packet) -> None:
    assert packet.decision == ContextDecision.DENIED_OUT_OF_SCOPE
    assert packet.allowed_paths == ()
    assert packet.allowed_tools == ()
    assert packet.approved_memories == ()
    assert packet.related_files == ()
    assert packet.selected_node_ids == ()


def test_catalog_and_task_bindings_are_the_frozen_three_profiles():
    assert tuple(profile.agent_profile_id for profile in load_catalog(GRAPH)) == (
        "platform-maintainer@1",
        "auth-maintainer@1",
        "billing-observer@1",
    )
    assert profile_for_task(GRAPH, GOLDEN.tasks[0].task_id).agent_profile_id == (
        "platform-maintainer@1"
    )
    assert profile_for_task(GRAPH, GOLDEN.tasks[1].task_id).agent_profile_id == (
        "auth-maintainer@1"
    )
    with pytest.raises(ValueError, match="frozen contract"):
        load_catalog(GRAPH.model_copy(update={"catalog": GRAPH.catalog[:2]}))


def test_auth_packet_has_exact_scope_memory_text_and_graph_ids():
    packet = _build(GOLDEN.tasks[1], "auth-maintainer@1")

    assert packet.consumer_run_id == "adapted_run"
    assert packet.decision == ContextDecision.ALLOWED
    assert packet.allowed_paths == (
        "app/auth/limiter.py",
        "tests/test_security_policy.py",
    )
    assert packet.allowed_tools == GOLDEN.tool_names
    assert [(item.memory_id, item.revision, item.exact_text) for item in packet.approved_memories] == [
        ("mem_auth_review", 1, GOLDEN.memory.rule)
    ]
    assert tuple(item.path for item in packet.related_files) == ("app/auth/limiter.py",)
    assert packet.selected_node_ids == ("node:a", "node:z")
    assert packet.packet_sha256 == canonical_json_sha256(
        packet.model_dump(mode="json", exclude={"packet_sha256"})
    )


def test_origin_scope_cannot_be_expanded_by_the_later_memory():
    packet = _build(
        GOLDEN.tasks[0],
        "platform-maintainer@1",
        consumer_run_id="baseline_run",
        packet_id="ctx_baseline",
    )

    assert packet.decision == ContextDecision.ALLOWED
    assert packet.allowed_paths == ("app/auth/limiter.py",)
    assert packet.approved_memories == ()


def test_billing_profile_is_denied_and_receives_nothing():
    _assert_denied(_build(GOLDEN.tasks[1], "billing-observer@1"))


@pytest.mark.parametrize(
    "updates",
    [
        {
            "target_paths": ("docs/security.md",),
            "expected_changed_paths": ("docs/security.md",),
        },
        {"repo_id": "another-repo"},
    ],
)
def test_auth_wrong_path_or_repo_is_denied(updates):
    task = TaskSpec.model_validate({**GOLDEN.tasks[1].model_dump(), **updates})
    _assert_denied(_build(task, "auth-maintainer@1"))


def test_pending_and_rejected_memories_are_not_selected():
    packet = _build(
        GOLDEN.tasks[1],
        "auth-maintainer@1",
        memories=(
            _memory(MemoryState.PROPOSED),
            _memory(MemoryState.REJECTED),
        ),
    )

    assert packet.decision == ContextDecision.ALLOWED
    assert packet.approved_memories == ()


def test_packet_hash_is_deterministic_for_reordered_graph_inputs():
    files = (
        RelatedFile(path="app/auth/limiter.py", reason="task target"),
        RelatedFile(path="tests/test_security_policy.py", reason="required test"),
    )
    first = _build(
        GOLDEN.tasks[1],
        "auth-maintainer@1",
        related_files=files,
        selected_node_ids=("node:z", "node:a"),
    )
    second = _build(
        GOLDEN.tasks[1],
        "auth-maintainer@1",
        related_files=reversed(files),
        selected_node_ids=("node:a", "node:z"),
    )

    assert first == second
    assert first.packet_sha256 == second.packet_sha256
