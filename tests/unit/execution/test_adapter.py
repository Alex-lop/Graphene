from __future__ import annotations

import base64
import asyncio
import inspect
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import reviewlatch.execution.adapter as adapter
from reviewlatch.context import build_context_packet
from reviewlatch.execution import (
    EXECUTION_MODE,
    ExecutionError,
    FixtureAccessError,
    GoogleAdkConfig,
    ScopedFixtureTools,
    execute_deterministic_local,
    execute_google_adk,
    fixture_base_sha,
)
from reviewlatch.hashing import canonical_json_sha256, sha256_hex
from reviewlatch.models import (
    GoldenContract,
    GraphMvpContract,
    HumanDecision,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    ProofType,
    RunRecord,
    RunState,
    TaskId,
)
from reviewlatch.store import InMemoryStore

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "demo/fixture"
NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
GRAPH = GraphMvpContract.model_validate_json(
    (ROOT / "contracts/graph_mvp.json").read_text()
)


@pytest.fixture(scope="module")
def base_sha() -> str:
    first = fixture_base_sha(GOLDEN, FIXTURE)
    assert first == fixture_base_sha(GOLDEN, FIXTURE)
    return first


def _approved_memory() -> MemoryRevision:
    spec = GOLDEN.memory
    proposed = MemoryRevision(
        memory_id=spec.memory_id,
        revision=spec.revision,
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
    decision = HumanDecision(
        decision_id="memory_approval_1",
        value=MemoryDecisionValue.APPROVE,
        purpose="memory",
        bound_digest=canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        ),
        occurred_at=NOW,
    )
    return MemoryRevision.model_validate(
        {
            **proposed.model_dump(mode="json"),
            "state": MemoryState.APPROVED,
            "decision": decision,
        }
    )


def _persisted_packet(
    store: InMemoryStore,
    base_sha: str,
    task_id: TaskId,
):
    task = next(item for item in GOLDEN.tasks if item.task_id == task_id)
    profile = {
        TaskId.BASELINE_MAX_ATTEMPTS: "platform-maintainer@1",
        TaskId.ADAPTED_WINDOW_SECONDS: "auth-maintainer@1",
    }[task_id]
    run_id = f"run_{task_id.value}"
    packet = build_context_packet(
        contract=GRAPH,
        task=task,
        consumer_run_id=run_id,
        consumer_agent_profile_id=profile,
        packet_id=f"ctx_{task_id.value}",
        base_sha=base_sha,
        tool_names=GOLDEN.tool_names,
        memories=(_approved_memory(),),
        source_graph_hash="b" * 64,
        selected_node_ids=("node:memory", "node:task"),
    )
    return store.create_context_packet(
        packet,
        f"packet_{sha256_hex(run_id.encode())[:32]}",
        packet.packet_sha256,
    )


def test_scoped_tools_reject_escape_symlinks_scope_and_oversized_writes(
    tmp_path: Path,
):
    root = tmp_path / "fixture"
    shutil.copytree(FIXTURE, root)
    tools = ScopedFixtureTools(
        root,
        allowed_paths=GOLDEN.fixture.mutable_paths,
        policy=GOLDEN.fixture,
    )

    assert "MAX_ATTEMPTS = 5" in tools.read_file("app/auth/limiter.py")
    with pytest.raises(FixtureAccessError):
        tools.read_file("../outside")
    with pytest.raises(FixtureAccessError):
        tools.read_file("docs/security.md")
    with pytest.raises(FixtureAccessError):
        tools.write_file("docs/security.md", "no")
    with pytest.raises(FixtureAccessError):
        tools.write_file(
            "tests/test_security_policy.py",
            "x" * (GOLDEN.fixture.max_write_bytes + 1),
        )

    outside = tmp_path / "outside.py"
    outside.write_text("secret")
    target = root / "tests/test_security_policy.py"
    target.symlink_to(outside)
    with pytest.raises(FixtureAccessError):
        tools.write_file("tests/test_security_policy.py", "overwritten")
    assert outside.read_text() == "secret"


@pytest.mark.parametrize(
    ("task_id", "expected_paths", "expects_base_failure", "replacement"),
    [
        (
            TaskId.BASELINE_MAX_ATTEMPTS,
            ("app/auth/limiter.py",),
            False,
            b"MAX_ATTEMPTS = 4",
        ),
        (
            TaskId.ADAPTED_WINDOW_SECONDS,
            ("app/auth/limiter.py", "tests/test_security_policy.py"),
            True,
            b"WINDOW_SECONDS = 90",
        ),
    ],
)
def test_deterministic_local_executor_builds_bound_candidate_and_denial(
    base_sha: str,
    task_id: TaskId,
    expected_paths: tuple[str, ...],
    expects_base_failure: bool,
    replacement: bytes,
):
    store = InMemoryStore()
    packet = _persisted_packet(store, base_sha, task_id)

    result = execute_deterministic_local(
        store=store,
        golden_contract=GOLDEN,
        graph_contract=GRAPH,
        packet=packet,
        fixture_root=FIXTURE,
        session_id=f"session_{task_id.value}",
        occurred_at=NOW,
    )

    candidate = result.candidate
    assert result.execution_mode == EXECUTION_MODE == "deterministic-local"
    assert candidate.base_commit_sha == base_sha
    assert candidate.changed_paths == expected_paths
    assert candidate.test_receipt.candidate_exit_code == 0
    if expects_base_failure:
        assert candidate.test_receipt.base_with_new_test_exit_code not in {None, 0}
    else:
        assert candidate.test_receipt.base_with_new_test_exit_code is None
    patch = base64.b64decode(candidate.canonical_patch_base64)
    assert replacement in patch
    assert candidate.candidate_patch_sha256 == sha256_hex(patch)
    assert result.policy_check.decision == "denied"
    assert result.policy_check.reason_codes == ("human_promotion_required",)
    assert result.policy_check.candidate_patch_sha256 == candidate.candidate_patch_sha256
    assert result.policy_check.test_receipt_sha256 == candidate.test_receipt.receipt_sha256
    assert result.proof[-1].type == ProofType.COMPLETION_DENIED
    assert all(item.payload["execution_mode"] == "deterministic-local" for item in result.proof)
    assert store.get_injection_receipt(packet.consumer_run_id) == result.injection_receipt
    assert result.injection_receipt.persisted_before_model_call is True
    assert bool(result.injection_receipt.memory_revisions) is expects_base_failure

    binding = next(item for item in GRAPH.task_profiles if item.task_id == task_id)
    waiting = RunRecord(
        run_id=packet.consumer_run_id,
        task_id=task_id,
        repo_id=packet.repo_id,
        state=RunState.WAITING_FOR_PROMOTION,
        revision=2,
        agent_profile_id=packet.consumer_agent_profile_id,
        base_sha=packet.base_sha,
        allowed_paths=packet.allowed_paths,
        allowed_tools=packet.allowed_tools,
        fresh_session=binding.fresh_session,
        context_packet_id=packet.packet_id,
        context_packet_sha256=packet.packet_sha256,
        source_graph_revision=packet.source_graph_revision,
        source_graph_hash=packet.source_graph_hash,
        selected_node_ids=packet.selected_node_ids,
        session_id=result.injection_receipt.session_id,
        injected_memories=result.injection_receipt.memory_revisions,
        proof=result.proof,
        policy_checks=(result.policy_check,),
        candidate=candidate,
        created_at=NOW,
    )
    assert waiting.state == RunState.WAITING_FOR_PROMOTION


def test_injection_receipt_is_persisted_before_candidate_execution(
    base_sha: str,
    monkeypatch: pytest.MonkeyPatch,
):
    store = InMemoryStore()
    packet = _persisted_packet(store, base_sha, TaskId.BASELINE_MAX_ATTEMPTS)
    initialize = adapter._initialize_repository
    observed: list[bool] = []

    def assert_receipt_first(*args, **kwargs):
        observed.append(store.get_injection_receipt(packet.consumer_run_id) is not None)
        return initialize(*args, **kwargs)

    monkeypatch.setattr(adapter, "_initialize_repository", assert_receipt_first)
    execute_deterministic_local(
        store=store,
        golden_contract=GOLDEN,
        graph_contract=GRAPH,
        packet=packet,
        fixture_root=FIXTURE,
        session_id="session_ordering",
        occurred_at=NOW,
    )
    assert observed == [True]


def test_executor_has_no_model_supplied_policy_or_approval_channel(base_sha: str):
    parameters = inspect.signature(execute_deterministic_local).parameters
    assert not {
        "agent_profile_id",
        "allowed_paths",
        "approval",
        "graph_facts",
        "policy_check",
        "test_success",
    } & parameters.keys()

    store = InMemoryStore()
    packet = _persisted_packet(store, base_sha, TaskId.BASELINE_MAX_ATTEMPTS)
    with pytest.raises(TypeError):
        execute_deterministic_local(
            store=store,
            golden_contract=GOLDEN,
            graph_contract=GRAPH,
            packet=packet,
            fixture_root=FIXTURE,
            session_id="session_forgery",
            occurred_at=NOW,
            policy_check={"decision": "allowed"},
        )


def test_mocked_google_adk_boundary_is_scoped_bound_and_explicitly_unverified(
    base_sha: str,
):
    store = InMemoryStore()
    packet = _persisted_packet(store, base_sha, TaskId.ADAPTED_WINDOW_SECONDS)

    async def mock_invoker(**values):
        assert store.get_injection_receipt(packet.consumer_run_id) is not None
        assert GOLDEN.memory.rule in values["prompt"]
        assert values["expected_adk_version"] == "2.5.0"
        tools = {tool.__name__: tool for tool in values["tools"]}
        limiter = tools["read_file"]("app/auth/limiter.py")
        tools["write_file"](
            "app/auth/limiter.py",
            limiter.replace("WINDOW_SECONDS = 60", "WINDOW_SECONDS = 90"),
        )
        tools["write_file"](
            GOLDEN.memory.required_test_path,
            GOLDEN.memory.expected_security_test_content,
        )
        model_test = tools["run_fixture_tests"]()
        assert model_test["exit_code"] == 0
        assert model_test["authoritative"] is False
        return "gemini-mocked-version"

    result = asyncio.run(
        execute_google_adk(
            config=GoogleAdkConfig(
                mode="google-adk",
                model_id=GOLDEN.model.model_id,
            ),
            store=store,
            golden_contract=GOLDEN,
            graph_contract=GRAPH,
            packet=packet,
            fixture_root=FIXTURE,
            session_id="session_mocked_adk",
            occurred_at=NOW,
            invoker=mock_invoker,
        )
    )

    assert result.execution_mode == "google-adk-mocked"
    assert result.metadata.requested_model_id == GOLDEN.model.model_id
    assert result.metadata.returned_model_id == "gemini-mocked-version"
    assert result.metadata.agent_profile_id == "auth-maintainer@1"
    assert result.metadata.session_id == "session_mocked_adk"
    assert result.metadata.runtime_verified is False
    assert result.candidate.changed_paths == GOLDEN.tasks[1].expected_changed_paths
    assert result.policy_check.decision == "denied"
    assert result.policy_check.reason_codes == ("human_promotion_required",)
    assert all(
        item.payload["execution_mode"] == "google-adk-mocked"
        for item in result.proof
    )


def test_google_adk_rejects_implicit_mode_and_model_claimed_policy(base_sha: str):
    store = InMemoryStore()
    packet = _persisted_packet(store, base_sha, TaskId.ADAPTED_WINDOW_SECONDS)
    called = False

    async def forged_invoker(**values):
        nonlocal called
        called = True
        return {"returned_model_id": "mock", "policy_check": {"decision": "allowed"}}

    with pytest.raises(ExecutionError, match="explicit mode"):
        asyncio.run(
            execute_google_adk(
                config=GoogleAdkConfig(
                    mode="deterministic-local",
                    model_id=GOLDEN.model.model_id,
                ),
                store=store,
                golden_contract=GOLDEN,
                graph_contract=GRAPH,
                packet=packet,
                fixture_root=FIXTURE,
                session_id="session_wrong_mode",
                occurred_at=NOW,
                invoker=forged_invoker,
            )
        )
    assert called is False

    with pytest.raises(ExecutionError, match="invalid model metadata"):
        asyncio.run(
            execute_google_adk(
                config=GoogleAdkConfig(
                    mode="google-adk",
                    model_id=GOLDEN.model.model_id,
                ),
                store=store,
                golden_contract=GOLDEN,
                graph_contract=GRAPH,
                packet=packet,
                fixture_root=FIXTURE,
                session_id="session_forged_claim",
                occurred_at=NOW,
                invoker=forged_invoker,
            )
        )
    assert store.get_injection_receipt(packet.consumer_run_id) is not None
