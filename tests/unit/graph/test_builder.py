import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from graphene.graph import GraphBuildError, GraphBuilder
from graphene.hashing import canonical_json_sha256, candidate_tree_sha256, sha256_hex
from graphene.core_models import (
    CandidateArtifact,
    ContextDecision,
    ContextPacket,
    FeedbackRecord,
    FileChange,
    GraphEdgeKind,
    GraphMvpContract,
    GraphNodeKind,
    GraphQuery,
    HumanDecision,
    InjectionReceipt,
    MemoryDecisionValue,
    MemoryRef,
    MemoryRevision,
    MemoryState,
    PacketMemory,
    PolicyCheck,
    ProofItem,
    ProofType,
    PromotionReceipt,
    RelatedFile,
    RunRecord,
    RunState,
    ScopeId,
    TaskId,
    TestReceipt as Receipt,
)

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)
BASE_SHA = "a" * 40
ALLOWED_PATHS = ("app/auth/limiter.py", "tests/test_security_policy.py")
ALLOWED_TOOLS = ("read_file", "write_file", "run_fixture_tests")
BASE_LIMITER = (
    b"from app.config import SECURITY_MODE\n"
    b"MAX_ATTEMPTS = 5\n"
    b"WINDOW_SECONDS = 60\n"
)
ORIGIN_LIMITER = BASE_LIMITER.replace(b"MAX_ATTEMPTS = 5", b"MAX_ATTEMPTS = 4")
ADAPTED_LIMITER = BASE_LIMITER.replace(b"WINDOW_SECONDS = 60", b"WINDOW_SECONDS = 90")
SECURITY_TEST = (
    b"from app.auth.limiter import WINDOW_SECONDS\n\n"
    b"def test_window():\n"
    b"    assert WINDOW_SECONDS == 90\n"
)


@pytest.fixture(scope="module")
def contract() -> GraphMvpContract:
    return GraphMvpContract.model_validate_json(
        (ROOT / "contracts/graph_mvp.json").read_text()
    )


def _patch(path: str, old: bytes | None, new: bytes) -> bytes:
    if path == "app/auth/limiter.py" and b"MAX_ATTEMPTS = 4" in new:
        hunk = (
            b"@@ -1,3 +1,3 @@\n"
            b" from app.config import SECURITY_MODE\n"
            b"-MAX_ATTEMPTS = 5\n"
            b"+MAX_ATTEMPTS = 4\n"
            b" WINDOW_SECONDS = 60\n"
        )
    elif path == "app/auth/limiter.py":
        hunk = (
            b"@@ -1,3 +1,3 @@\n"
            b" from app.config import SECURITY_MODE\n"
            b" MAX_ATTEMPTS = 5\n"
            b"-WINDOW_SECONDS = 60\n"
            b"+WINDOW_SECONDS = 90\n"
        )
    else:
        hunk = (
            b"@@ -0,0 +1,4 @@\n"
            b"+from app.auth.limiter import WINDOW_SECONDS\n"
            b"+\n"
            b"+def test_window():\n"
            b"+    assert WINDOW_SECONDS == 90\n"
        )
    metadata = (
        b"new file mode 100644\nindex 0000000..2222222\n--- /dev/null\n"
        if old is None
        else b"index 1111111..2222222 100644\n--- a/" + path.encode() + b"\n"
    )
    return (
        b"diff --git a/"
        + path.encode()
        + b" b/"
        + path.encode()
        + b"\n"
        + metadata
        + b"+++ b/"
        + path.encode()
        + b"\n"
        + hunk
    )


def _candidate(
    revision: int,
    files: dict[str, bytes],
    before: dict[str, bytes | None],
    *,
    base_exit: int | None,
    patch: bytes | None = None,
) -> CandidateArtifact:
    patch = patch or b"".join(_patch(path, before[path], files[path]) for path in sorted(files))
    patch_hash = sha256_hex(patch)
    receipt_data = {
        "required_test_profile": "auth-fixture-v1",
        "base_commit_sha": BASE_SHA,
        "candidate_patch_sha256": patch_hash,
        "command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        "candidate_exit_code": 0,
        "base_with_new_test_exit_code": base_exit,
        "timed_out": False,
        "output_sha256": sha256_hex(b"4 passed"),
        "output_byte_count": len(b"4 passed"),
        "output_truncated": False,
        "duration_bucket": "under_1s",
    }
    receipt = Receipt(
        **receipt_data,
        receipt_sha256=canonical_json_sha256(receipt_data),
    )
    return CandidateArtifact(
        candidate_revision=revision,
        base_commit_sha=BASE_SHA,
        canonical_patch_base64=base64.b64encode(patch).decode(),
        candidate_patch_sha256=patch_hash,
        candidate_tree_sha256=candidate_tree_sha256(files),
        candidate_tree_hash_version="graphene.tree.v2",
        changed_paths=tuple(sorted(files)),
        file_changes=tuple(
            FileChange(
                path=path,
                before_sha256=sha256_hex(before[path]) if before[path] is not None else None,
                after_sha256=sha256_hex(files[path]),
            )
            for path in sorted(files)
        ),
        test_receipt=receipt,
    )


def _proof(run_id: str, types: tuple[ProofType, ...], start: datetime) -> tuple[ProofItem, ...]:
    return tuple(
        ProofItem(
            event_id=f"{run_id}_event_{sequence}",
            run_id=run_id,
            sequence=sequence,
            type=proof_type,
            occurred_at=start + timedelta(seconds=sequence),
        )
        for sequence, proof_type in enumerate(types, 1)
    )


def _policy(run_id: str, candidate: CandidateArtifact, when: datetime, context: str | None) -> PolicyCheck:
    return PolicyCheck(
        policy_check_id=f"{run_id}_policy",
        run_id=run_id,
        policy_revision=1,
        decision="denied",
        reason_codes=("human_approval_missing",),
        candidate_patch_sha256=candidate.candidate_patch_sha256,
        context_packet_sha256=context,
        test_receipt_sha256=candidate.test_receipt.receipt_sha256,
        occurred_at=when,
    )


def _origin_run(candidate: CandidateArtifact) -> RunRecord:
    return RunRecord(
        run_id="origin_run",
        task_id=TaskId.BASELINE_MAX_ATTEMPTS,
        repo_id="graphene-demo",
        state=RunState.WAITING_FOR_PROMOTION,
        revision=2,
        agent_profile_id="platform-maintainer@1",
        base_sha=BASE_SHA,
        allowed_paths=ALLOWED_PATHS,
        allowed_tools=ALLOWED_TOOLS,
        session_id="origin_session",
        model_id="gemini-test",
        proof=_proof(
            "origin_run",
            (ProofType.TEST_COMPLETED, ProofType.COMPLETION_DENIED),
            NOW,
        ),
        policy_checks=(_policy("origin_run", candidate, NOW + timedelta(seconds=2), None),),
        candidate=candidate,
        created_at=NOW,
    )


def _approved_memory(selected_hunk_id: str) -> tuple[FeedbackRecord, MemoryRevision]:
    feedback = FeedbackRecord(
        feedback_id="feedback_1",
        run_id="origin_run",
        evidence_event_id="event_1",
        exact_correction="Auth changes require the repository security regression test.",
        selected_hunk_id=selected_hunk_id,
        selected_scope_id=ScopeId.ALL_AUTH,
        occurred_at=NOW + timedelta(seconds=3),
    )
    fields = {
        "memory_id": "mem_auth_review",
        "revision": 1,
        "rule": "Auth changes require a regression test in tests/test_security_policy.py.",
        "repo_id": "graphene-demo",
        "path_globs": ("app/auth/**",),
        "task_tags": ("authentication", "security"),
        "required_test_path": "tests/test_security_policy.py",
        "required_check": "new_test_fails_on_base_and_passes_on_candidate",
        "evidence_run_id": "origin_run",
        "feedback_id": feedback.feedback_id,
    }
    proposed = MemoryRevision(state=MemoryState.PROPOSED, **fields)
    decision = HumanDecision(
        decision_id="memory_decision",
        value=MemoryDecisionValue.APPROVE,
        purpose="memory",
        bound_digest=canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        ),
        occurred_at=NOW + timedelta(seconds=4),
    )
    return feedback, MemoryRevision(
        state=MemoryState.APPROVED,
        decision=decision,
        **fields,
    )


def _bundle(contract: GraphMvpContract):
    origin_candidate = _candidate(
        1,
        {"app/auth/limiter.py": ORIGIN_LIMITER},
        {"app/auth/limiter.py": BASE_LIMITER},
        base_exit=None,
    )
    origin = _origin_run(origin_candidate)
    origin_builder = GraphBuilder(contract, runs=(origin,))
    origin_hunk = next(
        node for node in origin_builder.build(origin.run_id).nodes if node.kind == GraphNodeKind.HUNK
    )
    feedback, memory = _approved_memory(origin_hunk.id)
    source_graph = GraphBuilder(
        contract,
        runs=(origin,),
        feedback=(feedback,),
        memories=(memory,),
    ).build(origin.run_id)
    memory_node_id = next(
        node.id for node in source_graph.nodes if node.kind == GraphNodeKind.MEMORY_REVISION
    )

    adapted_candidate = _candidate(
        2,
        {
            "app/auth/limiter.py": ADAPTED_LIMITER,
            "tests/test_security_policy.py": SECURITY_TEST,
        },
        {
            "app/auth/limiter.py": BASE_LIMITER,
            "tests/test_security_policy.py": None,
        },
        base_exit=1,
    )
    packet_data = {
        "packet_id": "ctx_1",
        "consumer_run_id": "adapted_run",
        "consumer_agent_profile_id": "auth-maintainer@1",
        "task_id": TaskId.ADAPTED_WINDOW_SECONDS,
        "repo_id": "graphene-demo",
        "base_sha": BASE_SHA,
        "allowed_paths": ALLOWED_PATHS,
        "allowed_tools": ALLOWED_TOOLS,
        "approved_memories": (
            PacketMemory(
                memory_id=memory.memory_id,
                revision=memory.revision,
                exact_text=memory.rule,
            ),
        ),
        "related_files": (RelatedFile(path="app/auth/limiter.py", reason="task target"),),
        "required_test_profile": "auth-fixture-v1",
        "source_graph_revision": source_graph.revision,
        "source_graph_hash": source_graph.graph_hash,
        "selected_node_ids": (memory_node_id,),
        "decision": ContextDecision.ALLOWED,
    }
    packet = ContextPacket(
        **packet_data,
        packet_sha256=canonical_json_sha256(
            ContextPacket.model_construct(**packet_data, packet_sha256="0" * 64).model_dump(
                mode="json", exclude={"packet_sha256"}
            )
        ),
    )
    injection_data = {
        "receipt_id": "injection_1",
        "run_id": "adapted_run",
        "session_id": "adapted_session",
        "consumer_agent_profile_id": "auth-maintainer@1",
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "source_graph_revision": packet.source_graph_revision,
        "source_graph_hash": packet.source_graph_hash,
        "selected_node_ids": packet.selected_node_ids,
        "memory_revisions": (MemoryRef(memory_id=memory.memory_id, revision=memory.revision),),
        "persisted_before_model_call": True,
        "occurred_at": NOW + timedelta(seconds=5),
    }
    injection = InjectionReceipt(
        **injection_data,
        receipt_sha256=canonical_json_sha256(
            InjectionReceipt.model_construct(
                **injection_data, receipt_sha256="0" * 64
            ).model_dump(mode="json", exclude={"receipt_sha256"})
        ),
    )
    promotion_decision = HumanDecision(
        decision_id="promotion_decision",
        value=MemoryDecisionValue.APPROVE,
        purpose="promotion",
        bound_digest=adapted_candidate.candidate_patch_sha256,
        occurred_at=NOW + timedelta(seconds=9),
    )
    promotion = PromotionReceipt(
        run_id="adapted_run",
        base_commit_sha=BASE_SHA,
        candidate_patch_sha256=adapted_candidate.candidate_patch_sha256,
        candidate_tree_sha256=adapted_candidate.candidate_tree_sha256,
        candidate_tree_hash_version=adapted_candidate.candidate_tree_hash_version,
        memory_id=memory.memory_id,
        memory_revision=memory.revision,
        context_packet_id=packet.packet_id,
        context_packet_sha256=packet.packet_sha256,
        source_graph_revision=packet.source_graph_revision,
        source_graph_hash=packet.source_graph_hash,
        selected_node_ids=packet.selected_node_ids,
        test_receipt_sha256=adapted_candidate.test_receipt.receipt_sha256,
        human_decision_id=promotion_decision.decision_id,
        expected_run_revision=2,
        commit_sha="c" * 40,
        commit_metadata={"message": "Promote adapted candidate"},
    )
    adapted = RunRecord(
        run_id="adapted_run",
        task_id=TaskId.ADAPTED_WINDOW_SECONDS,
        repo_id="graphene-demo",
        state=RunState.COMPLETED,
        revision=4,
        agent_profile_id="auth-maintainer@1",
        base_sha=BASE_SHA,
        allowed_paths=ALLOWED_PATHS,
        allowed_tools=ALLOWED_TOOLS,
        fresh_session=True,
        context_packet_id=packet.packet_id,
        context_packet_sha256=packet.packet_sha256,
        source_graph_revision=packet.source_graph_revision,
        source_graph_hash=packet.source_graph_hash,
        selected_node_ids=packet.selected_node_ids,
        session_id=injection.session_id,
        model_id="gemini-test",
        injected_memories=injection.memory_revisions,
        proof=_proof(
            "adapted_run",
            (
                ProofType.TEST_COMPLETED,
                ProofType.COMPLETION_DENIED,
                ProofType.PROMOTION_APPROVED,
                ProofType.CANDIDATE_COMMITTED,
            ),
            NOW + timedelta(seconds=5),
        ),
        policy_checks=(
            _policy(
                "adapted_run",
                adapted_candidate,
                NOW + timedelta(seconds=7),
                packet.packet_sha256,
            ),
        ),
        candidate=adapted_candidate,
        promotion_decision=promotion_decision,
        promotion_receipt=promotion,
        created_at=NOW + timedelta(seconds=5),
    )
    return origin, adapted, feedback, memory, packet, injection


def test_projects_the_exact_evidence_spine_deterministically(contract: GraphMvpContract):
    origin, adapted, feedback, memory, packet, injection = _bundle(contract)
    first = GraphBuilder(
        contract,
        runs=(origin, adapted),
        feedback=(feedback,),
        memories=(memory,),
        context_packets=(packet,),
        injection_receipts=(injection,),
    )
    second = GraphBuilder(
        contract,
        runs=(adapted, origin),
        feedback=(feedback,),
        memories=(memory,),
        context_packets=(packet,),
        injection_receipts=(injection,),
    )
    graph = first.build(adapted.run_id)
    rebuilt = second.build(adapted.run_id)

    assert graph == rebuilt
    assert [node.id for node in graph.nodes] == sorted(node.id for node in graph.nodes)
    assert [edge.id for edge in graph.edges] == sorted(edge.id for edge in graph.edges)
    assert {edge.kind for edge in graph.edges} >= {
        GraphEdgeKind.PRODUCED,
        GraphEdgeKind.CONTAINS,
        GraphEdgeKind.MODIFIES,
        GraphEdgeKind.TRIGGERED,
        GraphEdgeKind.LEARNED_AS,
        GraphEdgeKind.APPROVED,
        GraphEdgeKind.PACKED_IN,
        GraphEdgeKind.INJECTED_INTO,
        GraphEdgeKind.VALIDATED,
        GraphEdgeKind.DENIED,
        GraphEdgeKind.AUTHORIZED,
        GraphEdgeKind.PROMOTED_AS,
    }
    node_ids = {node.id for node in graph.nodes}
    assert all(edge.source in node_ids and edge.target in node_ids for edge in graph.edges)
    assert all(edge.source_ref for edge in graph.edges)

    hunk = next(node for node in graph.nodes if node.kind == GraphNodeKind.HUNK)
    assert "unified_diff" not in hunk.data
    detail = first.node_detail(adapted.run_id, hunk.id)
    assert detail is not None
    assert detail.data["unified_diff"].startswith("@@ ")
    assert sha256_hex(detail.data["unified_diff"].encode()) == detail.data["exact_hunk_sha256"]
    assert detail.digest == hunk.digest

    decisions = first.build(
        adapted.run_id,
        GraphQuery(kinds=(GraphNodeKind.HUMAN_DECISION,)),
    )
    assert len(decisions.nodes) == 2
    assert decisions.edges == ()
    assert not decisions.truncated
    assert decisions.omitted_counts == {}


def test_imports_require_explicit_matching_parseable_after_bytes(contract: GraphMvpContract):
    origin, adapted, feedback, memory, packet, injection = _bundle(contract)
    common = {
        "runs": (origin, adapted),
        "feedback": (feedback,),
        "memories": (memory,),
        "context_packets": (packet,),
        "injection_receipts": (injection,),
    }
    assert GraphEdgeKind.IMPORTS not in {
        edge.kind for edge in GraphBuilder(contract, **common).build(adapted.run_id).edges
    }

    builder = GraphBuilder(
        contract,
        **common,
        after_files={
            (adapted.run_id, "app/auth/limiter.py"): ADAPTED_LIMITER,
            (adapted.run_id, "app/config.py"): b"SECURITY_MODE = True\n",
        },
    )
    depth_zero = builder.build(adapted.run_id, GraphQuery(depth=0))
    depth_one = builder.build(adapted.run_id, GraphQuery(depth=1))
    assert GraphEdgeKind.IMPORTS not in {edge.kind for edge in depth_zero.edges}
    imports = [edge for edge in depth_one.edges if edge.kind == GraphEdgeKind.IMPORTS]
    assert len(imports) == 1
    assert imports[0].advisory


def _many_hunk_patch(count: int) -> bytes:
    hunks = b"".join(
        f"@@ -{line} +{line} @@\n-old_{line}\n+new_{line}\n".encode()
        for line in range(1, count + 1)
    )
    return (
        b"diff --git a/app/auth/limiter.py b/app/auth/limiter.py\n"
        b"index 1111111..2222222 100644\n"
        b"--- a/app/auth/limiter.py\n"
        b"+++ b/app/auth/limiter.py\n"
        + hunks
    )


def test_strict_patch_validation_and_honest_hunk_cap(contract: GraphMvpContract):
    candidate = _candidate(
        1,
        {"app/auth/limiter.py": b"after\n"},
        {"app/auth/limiter.py": b"before\n"},
        base_exit=None,
        patch=_many_hunk_patch(13),
    )
    run = _origin_run(candidate)
    graph = GraphBuilder(contract, runs=(run,)).build(run.run_id)
    assert len([node for node in graph.nodes if node.kind == GraphNodeKind.HUNK]) == 12
    assert graph.truncated
    assert graph.omitted_counts == {"hunks": 1, "nodes": 1, "edges": 2}
    assert len(graph.nodes) <= 25
    assert len(graph.edges) <= 40

    filtered = GraphBuilder(contract, runs=(run,)).build(
        run.run_id,
        GraphQuery(kinds=(GraphNodeKind.AGENT_RUN,)),
    )
    assert len(filtered.nodes) == 1
    assert not filtered.truncated

    malformed = _candidate(
        1,
        {"app/auth/limiter.py": b"after\n"},
        {"app/auth/limiter.py": b"before\n"},
        base_exit=None,
        patch=_many_hunk_patch(1).replace(b"@@ -1 +1 @@", b"@@ -1,2 +1 @@"),
    )
    with pytest.raises(GraphBuildError, match="line counts"):
        GraphBuilder(contract, runs=(_origin_run(malformed),)).build("origin_run")
