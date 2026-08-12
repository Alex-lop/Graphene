from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Awaitable, Callable

from ..context import profile_for_task
from ..hashing import canonical_json_sha256, candidate_tree_sha256, sha256_hex
from ..models import (
    MAX_PATCH_BYTES,
    MAX_TEST_OUTPUT_BYTES,
    CandidateArtifact,
    ContextDecision,
    ContextPacket,
    FileChange,
    FixturePolicy,
    GoldenContract,
    GraphMvpContract,
    InjectionReceipt,
    MemoryRef,
    PolicyCheck,
    ProofItem,
    ProofType,
    TaskId,
    TaskSpec,
    TestReceipt,
)
from ..store import Store

EXECUTION_MODE = "deterministic-local"
_FIXED_TEST_COMMAND = (
    "python",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
)
_DURATION = re.compile(r"\bin \d+(?:\.\d+)?s\b")


class ExecutionError(RuntimeError):
    pass


class FixtureAccessError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TestRun:
    exit_code: int
    timed_out: bool
    output: str
    output_truncated: bool


@dataclass(frozen=True, slots=True)
class DeterministicExecution:
    execution_mode: str
    injection_receipt: InjectionReceipt
    candidate: CandidateArtifact
    proof: tuple[ProofItem, ...]
    policy_check: PolicyCheck


@dataclass(frozen=True, slots=True)
class GoogleAdkConfig:
    mode: str
    model_id: str
    app_name: str = "reviewlatch"
    user_id: str = "reviewlatch-demo"


@dataclass(frozen=True, slots=True)
class GoogleAdkMetadata:
    requested_model_id: str
    returned_model_id: str | None
    agent_profile_id: str
    session_id: str
    adk_version: str
    runtime_verified: bool


@dataclass(frozen=True, slots=True)
class GoogleAdkExecution:
    execution_mode: str
    metadata: GoogleAdkMetadata
    injection_receipt: InjectionReceipt
    candidate: CandidateArtifact
    proof: tuple[ProofItem, ...]
    policy_check: PolicyCheck


AdkInvoker = Callable[..., Awaitable[str | None]]


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256_hex("\0".join(parts).encode())[:24]
    return f"{prefix}:{digest}"


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        value in {"", "."}
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise FixtureAccessError("path must be canonical and relative")
    return path


class ScopedFixtureTools:
    """The only file boundary exposed by the controlled local executor."""

    def __init__(
        self,
        root: Path,
        *,
        allowed_paths: tuple[str, ...],
        policy: FixturePolicy,
    ) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise FixtureAccessError("fixture root must be a directory")
        self.allowed_paths = frozenset(allowed_paths)
        self.mutable_paths = frozenset(policy.mutable_paths)
        self.max_write_bytes = policy.max_write_bytes

    def _resolve(self, relative_path: str, *, write: bool) -> Path:
        relative = _relative_path(relative_path)
        if relative_path not in self.allowed_paths:
            raise FixtureAccessError("path is outside the context packet allowlist")
        if write and relative_path not in self.mutable_paths:
            raise FixtureAccessError("path is outside the fixture write allowlist")

        candidate = self.root.joinpath(*relative.parts)
        cursor = self.root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise FixtureAccessError("fixture symlinks are forbidden")
        resolved = candidate.resolve(strict=False)
        if resolved != self.root and self.root not in resolved.parents:
            raise FixtureAccessError("path escapes the fixture root")
        return candidate

    def read_file(self, relative_path: str) -> str:
        """Read one UTF-8 file allowed by the persisted context packet."""

        path = self._resolve(relative_path, write=False)
        if not path.is_file():
            raise FixtureAccessError("file does not exist")
        return path.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> str:
        """Write UTF-8 content to one allowlisted fixture path."""

        encoded = content.encode()
        if len(encoded) > self.max_write_bytes:
            raise FixtureAccessError("write exceeds the fixture byte cap")
        path = self._resolve(relative_path, write=True)
        if not path.parent.is_dir():
            raise FixtureAccessError("parent directory does not exist")
        if path.exists() and not path.is_file():
            raise FixtureAccessError("write target must be a file")
        path.write_bytes(encoded)
        return sha256_hex(encoded)


def _sanitized_environment() -> dict[str, str]:
    return {
        "COLUMNS": "80",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _sanitize_output(output: str, root: Path, cap: int) -> tuple[str, bool]:
    sanitized = _DURATION.sub("in <duration>s", output.replace(str(root), "<fixture>"))
    raw = sanitized.encode()
    if len(raw) <= cap:
        return sanitized, False
    return raw[:cap].decode(errors="ignore"), True


def run_fixture_tests(root: Path, policy: FixturePolicy) -> TestRun:
    if policy.fixed_test_command != _FIXED_TEST_COMMAND:
        raise ExecutionError("fixture test command is not the frozen command")
    try:
        result = subprocess.run(
            policy.fixed_test_command,
            cwd=root,
            env=_sanitized_environment(),
            capture_output=True,
            text=True,
            timeout=policy.test_timeout_seconds,
            check=False,
        )
        exit_code = result.returncode
        timed_out = False
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = -1
        timed_out = True
        output = _text(error.stdout) + _text(error.stderr)

    output, truncated = _sanitize_output(
        output,
        root,
        min(policy.max_test_output_bytes, MAX_TEST_OUTPUT_BYTES),
    )
    return TestRun(exit_code, timed_out, output, truncated)


def _git_environment() -> dict[str, str]:
    return {
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_AUTHOR_EMAIL": "fixture@reviewlatch.invalid",
        "GIT_AUTHOR_NAME": "ReviewLatch Fixture",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_EMAIL": "fixture@reviewlatch.invalid",
        "GIT_COMMITTER_NAME": "ReviewLatch Fixture",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", os.defpath),
    }


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ("git", "-c", "core.autocrlf=false", "-c", "core.filemode=false", *args),
        cwd=root,
        env=_git_environment(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode:
        message, _ = _sanitize_output(_text(result.stderr), root, 2048)
        raise ExecutionError(f"git command failed: {message.strip()}")
    return result.stdout


def _validate_fixture(contract: GoldenContract, fixture_root: Path) -> None:
    tracked = set(contract.fixture.tracked_paths)
    actual: set[str] = set()
    for path in fixture_root.rglob("*"):
        if path.is_symlink():
            raise ExecutionError("source fixture cannot contain symlinks")
        if path.is_file():
            actual.add(path.relative_to(fixture_root).as_posix())
    if actual != tracked:
        raise ExecutionError("source fixture inventory does not match the frozen contract")
    files = {path: (fixture_root / path).read_bytes() for path in tracked}
    if candidate_tree_sha256(files) != contract.fixture.tree_sha256:
        raise ExecutionError("source fixture bytes do not match the frozen contract")


def _initialize_repository(
    contract: GoldenContract,
    fixture_root: Path,
    destination: Path,
) -> str:
    _validate_fixture(contract, fixture_root)
    shutil.copytree(fixture_root, destination)
    _git(destination, "init", "--quiet", "--initial-branch=main")
    _git(destination, "add", "--all")
    tree = _git(destination, "write-tree").decode().strip()
    commit = _git(
        destination,
        "commit-tree",
        tree,
        "-m",
        "ReviewLatch deterministic fixture baseline",
    ).decode().strip()
    _git(destination, "update-ref", "refs/heads/main", commit)
    return commit


def fixture_base_sha(contract: GoldenContract, fixture_root: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="reviewlatch-base-") as temporary:
        return _initialize_repository(contract, fixture_root, Path(temporary) / "fixture")


def persist_injection_receipt(
    store: Store,
    packet: ContextPacket,
    *,
    session_id: str,
    occurred_at: datetime | None = None,
) -> InjectionReceipt:
    if packet.decision != ContextDecision.ALLOWED:
        raise ExecutionError("denied context cannot be injected")
    persisted = store.get_context_packet(packet.consumer_run_id)
    if persisted != packet:
        raise ExecutionError("context packet must be persisted before injection")

    memories = tuple(
        MemoryRef(memory_id=memory.memory_id, revision=memory.revision)
        for memory in packet.approved_memories
    )
    existing = store.get_injection_receipt(packet.consumer_run_id)
    if existing is not None:
        if (
            existing.run_id != packet.consumer_run_id
            or existing.session_id != session_id
            or existing.consumer_agent_profile_id != packet.consumer_agent_profile_id
            or existing.packet_id != packet.packet_id
            or existing.packet_sha256 != packet.packet_sha256
            or existing.source_graph_revision != packet.source_graph_revision
            or existing.source_graph_hash != packet.source_graph_hash
            or existing.selected_node_ids != packet.selected_node_ids
            or existing.memory_revisions != memories
        ):
            raise ExecutionError("run already has a different injection receipt")
        return existing

    payload = {
        "receipt_id": _stable_id("injection", packet.consumer_run_id, packet.packet_sha256),
        "run_id": packet.consumer_run_id,
        "session_id": session_id,
        "consumer_agent_profile_id": packet.consumer_agent_profile_id,
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "source_graph_revision": packet.source_graph_revision,
        "source_graph_hash": packet.source_graph_hash,
        "selected_node_ids": packet.selected_node_ids,
        "memory_revisions": memories,
        "persisted_before_model_call": True,
        "occurred_at": occurred_at or datetime.now(timezone.utc),
    }
    canonical_payload = InjectionReceipt.model_construct(
        **payload, receipt_sha256="0" * 64
    ).model_dump(mode="json", exclude={"receipt_sha256"})
    receipt = InjectionReceipt.model_validate(
        {
            **canonical_payload,
            "receipt_sha256": canonical_json_sha256(canonical_payload),
        }
    )
    return store.create_injection_receipt(
        receipt,
        f"inject_{receipt.receipt_sha256[:32]}",
        receipt.receipt_sha256,
    )


def _task_for_packet(contract: GoldenContract, packet: ContextPacket):
    task = next((item for item in contract.tasks if item.task_id == packet.task_id), None)
    if task is None:
        raise ExecutionError("context packet references an unknown task")
    return task


def _validate_packet(
    golden: GoldenContract,
    graph: GraphMvpContract,
    packet: ContextPacket,
) -> tuple[TaskSpec, bool, int]:
    task = _task_for_packet(golden, packet)
    profile = profile_for_task(graph, task.task_id)
    if (
        packet.decision != ContextDecision.ALLOWED
        or packet.consumer_agent_profile_id != profile.agent_profile_id
        or packet.repo_id != golden.repo_id
        or packet.repo_id != task.repo_id
        or packet.allowed_paths != task.expected_changed_paths
        or packet.allowed_tools != golden.tool_names
        or packet.required_test_profile != graph.required_test_profile
        or packet.source_graph_revision != graph.graph_revision
    ):
        raise ExecutionError("context packet does not match the frozen execution scope")

    expected_memory = golden.memory
    injected = bool(packet.approved_memories)
    if injected and (
        task.task_id != TaskId.ADAPTED_WINDOW_SECONDS
        or len(packet.approved_memories) != 1
        or packet.approved_memories[0].memory_id != expected_memory.memory_id
        or packet.approved_memories[0].revision != expected_memory.revision
        or packet.approved_memories[0].exact_text != expected_memory.rule
        or not packet.selected_node_ids
    ):
        raise ExecutionError("packet memory does not match the frozen approved revision")
    return task, injected, profile.policy_revision


def _base_test_result(
    golden: GoldenContract,
    fixture_root: Path,
    test_content: bytes,
    destination: Path,
) -> TestRun:
    shutil.copytree(fixture_root, destination)
    test_path = destination / golden.memory.required_test_path
    test_path.write_bytes(test_content)
    return run_fixture_tests(destination, golden.fixture)


def _proof_items(
    *,
    packet: ContextPacket,
    receipt: InjectionReceipt,
    changes: tuple[FileChange, ...],
    test_receipt: TestReceipt,
    policy_check: PolicyCheck,
    occurred_at: datetime,
    execution_mode: str,
) -> tuple[ProofItem, ...]:
    items: list[ProofItem] = []

    def append(proof_type: ProofType, payload: dict[str, object], evidence=()) -> None:
        sequence = len(items) + 1
        items.append(
            ProofItem(
                event_id=_stable_id(
                    "event", packet.consumer_run_id, str(sequence), proof_type.value
                ),
                run_id=packet.consumer_run_id,
                sequence=sequence,
                evidence_event_ids=tuple(evidence),
                type=proof_type,
                occurred_at=occurred_at,
                payload={"execution_mode": execution_mode, **payload},
            )
        )

    if receipt.memory_revisions:
        append(
            ProofType.MEMORY_INJECTED,
            {
                "injection_receipt_id": receipt.receipt_id,
                "injection_receipt_sha256": receipt.receipt_sha256,
                "packet_sha256": packet.packet_sha256,
                "memory_revisions": [
                    item.model_dump(mode="json") for item in receipt.memory_revisions
                ],
            },
        )
    write_ids: list[str] = []
    for change in changes:
        append(
            ProofType.FILE_WRITTEN,
            {
                "path": change.path,
                "before_sha256": change.before_sha256,
                "after_sha256": change.after_sha256,
            },
            (items[-1].event_id,) if items else (),
        )
        write_ids.append(items[-1].event_id)
    append(
        ProofType.TEST_COMPLETED,
        {
            "test_receipt_sha256": test_receipt.receipt_sha256,
            "required_test_profile": test_receipt.required_test_profile,
            "candidate_exit_code": test_receipt.candidate_exit_code,
            "base_with_new_test_exit_code": test_receipt.base_with_new_test_exit_code,
        },
        write_ids,
    )
    append(
        ProofType.COMPLETION_DENIED,
        {
            "policy_check_id": policy_check.policy_check_id,
            "decision": policy_check.decision,
            "reason_codes": list(policy_check.reason_codes),
            "candidate_patch_sha256": policy_check.candidate_patch_sha256,
            "context_packet_sha256": policy_check.context_packet_sha256,
            "test_receipt_sha256": policy_check.test_receipt_sha256,
        },
        (items[-1].event_id,),
    )
    return tuple(items)


def _finalize_candidate(
    *,
    golden: GoldenContract,
    packet: ContextPacket,
    task: TaskSpec,
    memory_injected: bool,
    fixture_root: Path,
    candidate_root: Path,
    temporary_root: Path,
    base_sha: str,
) -> tuple[CandidateArtifact, tuple[FileChange, ...]]:
    candidate_test = run_fixture_tests(candidate_root, golden.fixture)
    if candidate_test.timed_out or candidate_test.exit_code != 0:
        raise ExecutionError("candidate failed the fixed test profile")

    base_test_exit: int | None = None
    if memory_injected:
        security_test = (candidate_root / golden.memory.required_test_path).read_bytes()
        base_test = _base_test_result(
            golden,
            fixture_root,
            security_test,
            temporary_root / "base-test",
        )
        if base_test.timed_out or base_test.exit_code == 0:
            raise ExecutionError("new security test must fail on the base fixture")
        base_test_exit = base_test.exit_code

    _git(candidate_root, "add", "--all")
    changed_paths = tuple(
        path.decode()
        for path in _git(
            candidate_root,
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "HEAD",
            "--",
        ).split(b"\0")
        if path
    )
    expected_paths = task.expected_changed_paths if memory_injected else task.target_paths
    if changed_paths != tuple(sorted(expected_paths)):
        raise ExecutionError("candidate changed paths do not match the frozen task")
    patch = _git(candidate_root, "diff", "--binary", "--cached", "HEAD", "--")
    if not patch or len(patch) > min(golden.fixture.max_patch_bytes, MAX_PATCH_BYTES):
        raise ExecutionError("candidate patch is empty or exceeds the byte cap")
    patch_sha = sha256_hex(patch)

    changes = tuple(
        FileChange(
            path=path,
            before_sha256=(
                sha256_hex((fixture_root / path).read_bytes())
                if (fixture_root / path).is_file()
                else None
            ),
            after_sha256=sha256_hex((candidate_root / path).read_bytes()),
        )
        for path in changed_paths
    )
    receipt_payload = {
        "required_test_profile": packet.required_test_profile,
        "base_commit_sha": base_sha,
        "candidate_patch_sha256": patch_sha,
        "command": golden.fixture.fixed_test_command,
        "candidate_exit_code": candidate_test.exit_code,
        "base_with_new_test_exit_code": base_test_exit,
        "timed_out": candidate_test.timed_out,
        "output": candidate_test.output,
        "output_truncated": candidate_test.output_truncated,
    }
    test_receipt = TestReceipt.model_validate(
        {
            **receipt_payload,
            "receipt_sha256": canonical_json_sha256(receipt_payload),
        }
    )
    candidate = CandidateArtifact(
        candidate_revision=1,
        base_commit_sha=base_sha,
        canonical_patch_base64=base64.b64encode(patch).decode(),
        candidate_patch_sha256=patch_sha,
        candidate_tree_sha256=candidate_tree_sha256(
            {path: (candidate_root / path).read_bytes() for path in changed_paths}
        ),
        changed_paths=changed_paths,
        file_changes=changes,
        test_receipt=test_receipt,
    )
    return candidate, changes


def _execution_evidence(
    *,
    packet: ContextPacket,
    injection: InjectionReceipt,
    candidate: CandidateArtifact,
    changes: tuple[FileChange, ...],
    policy_revision: int,
    timestamp: datetime,
    execution_mode: str,
) -> tuple[PolicyCheck, tuple[ProofItem, ...]]:
    policy_check = PolicyCheck(
        policy_check_id=_stable_id(
            "policy", packet.consumer_run_id, candidate.candidate_patch_sha256
        ),
        run_id=packet.consumer_run_id,
        policy_revision=policy_revision,
        decision="denied",
        reason_codes=("human_promotion_required",),
        candidate_patch_sha256=candidate.candidate_patch_sha256,
        context_packet_sha256=packet.packet_sha256,
        test_receipt_sha256=candidate.test_receipt.receipt_sha256,
        occurred_at=timestamp,
    )
    proof = _proof_items(
        packet=packet,
        receipt=injection,
        changes=changes,
        test_receipt=candidate.test_receipt,
        policy_check=policy_check,
        occurred_at=timestamp,
        execution_mode=execution_mode,
    )
    return policy_check, proof


def execute_deterministic_local(
    *,
    store: Store,
    golden_contract: GoldenContract,
    graph_contract: GraphMvpContract,
    packet: ContextPacket,
    fixture_root: Path,
    session_id: str,
    occurred_at: datetime | None = None,
) -> DeterministicExecution:
    """Execute the two frozen tasks without a model and label the result honestly."""

    task, memory_injected, policy_revision = _validate_packet(
        golden_contract, graph_contract, packet
    )
    timestamp = occurred_at or datetime.now(timezone.utc)
    injection = persist_injection_receipt(
        store, packet, session_id=session_id, occurred_at=timestamp
    )

    with tempfile.TemporaryDirectory(prefix="reviewlatch-execution-") as temporary:
        temporary_root = Path(temporary)
        candidate_root = temporary_root / "candidate"
        base_sha = _initialize_repository(golden_contract, fixture_root, candidate_root)
        if base_sha != packet.base_sha:
            raise ExecutionError("context packet base SHA does not match the frozen fixture")
        tools = ScopedFixtureTools(
            candidate_root,
            allowed_paths=packet.allowed_paths,
            policy=golden_contract.fixture,
        )
        target = task.target_paths[0]
        before = tools.read_file(target)
        if before.count(task.replacement_from) != 1:
            raise ExecutionError("frozen task replacement must occur exactly once")
        tools.write_file(target, before.replace(task.replacement_from, task.replacement_to))
        if memory_injected:
            tools.write_file(
                golden_contract.memory.required_test_path,
                golden_contract.memory.expected_security_test_content,
            )
        candidate, changes = _finalize_candidate(
            golden=golden_contract,
            packet=packet,
            task=task,
            memory_injected=memory_injected,
            fixture_root=fixture_root,
            candidate_root=candidate_root,
            temporary_root=temporary_root,
            base_sha=base_sha,
        )

    policy_check, proof = _execution_evidence(
        packet=packet,
        injection=injection,
        candidate=candidate,
        changes=changes,
        policy_revision=policy_revision,
        timestamp=timestamp,
        execution_mode=EXECUTION_MODE,
    )
    return DeterministicExecution(
        execution_mode=EXECUTION_MODE,
        injection_receipt=injection,
        candidate=candidate,
        proof=proof,
        policy_check=policy_check,
    )


def _prompt(golden: GoldenContract, task: TaskSpec, packet: ContextPacket) -> str:
    if packet.approved_memories:
        memory_context = "\n".join(
            golden.prompt.approved_memory_template.format(
                memory_id=memory.memory_id,
                revision=memory.revision,
                rule=memory.exact_text,
            )
            for memory in packet.approved_memories
        )
    else:
        memory_context = golden.prompt.no_memory_context
    return golden.prompt.template.format(
        task=task.instruction,
        memory_context=memory_context,
    )


def _model_tools(
    scoped: ScopedFixtureTools,
    policy: FixturePolicy,
) -> tuple[Callable[..., object], ...]:
    def model_test_runner() -> dict[str, object]:
        """Run the fixed fixture tests; final acceptance is rerun by the server."""

        result = run_fixture_tests(scoped.root, policy)
        return {
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "output": result.output,
            "output_truncated": result.output_truncated,
            "authoritative": False,
        }

    model_test_runner.__name__ = "run_fixture_tests"
    return scoped.read_file, scoped.write_file, model_test_runner


async def _installed_google_adk_invoker(
    *,
    config: GoogleAdkConfig,
    prompt: str,
    session_id: str,
    tools: tuple[Callable[..., object], ...],
    expected_adk_version: str,
) -> str | None:
    import google.adk
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    if google.adk.__version__ != expected_adk_version:
        raise ExecutionError("installed Google ADK version differs from the contract")
    sessions = InMemorySessionService()
    await sessions.create_session(
        app_name=config.app_name,
        user_id=config.user_id,
        session_id=session_id,
    )
    agent = LlmAgent(
        name="reviewlatch_agent",
        model=config.model_id,
        instruction=prompt,
        tools=list(tools),
        mode="chat",
    )
    runner = Runner(
        app_name=config.app_name,
        agent=agent,
        session_service=sessions,
    )
    returned_model_id: str | None = None
    saw_event = False
    async for event in runner.run_async(
        user_id=config.user_id,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="Execute the frozen task now.")],
        ),
    ):
        saw_event = True
        if event.model_version:
            returned_model_id = event.model_version
    if not saw_event:
        raise ExecutionError("Google ADK returned no events")
    return returned_model_id


async def execute_google_adk(
    *,
    config: GoogleAdkConfig,
    store: Store,
    golden_contract: GoldenContract,
    graph_contract: GraphMvpContract,
    packet: ContextPacket,
    fixture_root: Path,
    session_id: str,
    occurred_at: datetime | None = None,
    invoker: AdkInvoker | None = None,
) -> GoogleAdkExecution:
    """Opt-in ADK seam; model text never becomes policy, test, or graph truth."""

    if config.mode != "google-adk" or config.model_id != golden_contract.model.model_id:
        raise ExecutionError("Google ADK requires explicit mode and the frozen model ID")
    task, memory_injected, policy_revision = _validate_packet(
        golden_contract, graph_contract, packet
    )
    timestamp = occurred_at or datetime.now(timezone.utc)
    injection = persist_injection_receipt(
        store, packet, session_id=session_id, occurred_at=timestamp
    )
    runtime_verified = invoker is None
    invoke = invoker or _installed_google_adk_invoker

    with tempfile.TemporaryDirectory(prefix="reviewlatch-adk-") as temporary:
        temporary_root = Path(temporary)
        candidate_root = temporary_root / "candidate"
        base_sha = _initialize_repository(golden_contract, fixture_root, candidate_root)
        if base_sha != packet.base_sha:
            raise ExecutionError("context packet base SHA does not match the frozen fixture")
        scoped = ScopedFixtureTools(
            candidate_root,
            allowed_paths=packet.allowed_paths,
            policy=golden_contract.fixture,
        )
        try:
            returned_model_id = await invoke(
                config=config,
                prompt=_prompt(golden_contract, task, packet),
                session_id=session_id,
                tools=_model_tools(scoped, golden_contract.fixture),
                expected_adk_version=golden_contract.model.adk_version,
            )
        except Exception as error:
            raise ExecutionError(
                "Google ADK invocation failed; no model result was accepted"
            ) from error
        if returned_model_id is not None and not isinstance(returned_model_id, str):
            raise ExecutionError("Google ADK returned invalid model metadata")
        candidate, changes = _finalize_candidate(
            golden=golden_contract,
            packet=packet,
            task=task,
            memory_injected=memory_injected,
            fixture_root=fixture_root,
            candidate_root=candidate_root,
            temporary_root=temporary_root,
            base_sha=base_sha,
        )

    execution_mode = "google-adk" if runtime_verified else "google-adk-mocked"
    policy_check, proof = _execution_evidence(
        packet=packet,
        injection=injection,
        candidate=candidate,
        changes=changes,
        policy_revision=policy_revision,
        timestamp=timestamp,
        execution_mode=execution_mode,
    )
    return GoogleAdkExecution(
        execution_mode=execution_mode,
        metadata=GoogleAdkMetadata(
            requested_model_id=config.model_id,
            returned_model_id=returned_model_id,
            agent_profile_id=packet.consumer_agent_profile_id,
            session_id=session_id,
            adk_version=golden_contract.model.adk_version,
            runtime_verified=runtime_verified,
        ),
        injection_receipt=injection,
        candidate=candidate,
        proof=proof,
        policy_check=policy_check,
    )
