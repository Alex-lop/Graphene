from __future__ import annotations

import argparse
import platform
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import uvicorn

from .bootstrap import bootstrap_local_run
from .cli.main import (
    _answer,
    _end_rejected_run,
    _feedback,
    _handoff,
    _load,
    _memory,
    _prepare_candidate,
    _promote,
    _reject_candidate,
    _review,
)
from .context.consumer import resume_fresh_consumer
from .demo_adk import (
    ADK_FAKE_PROOF_LABEL,
    AdkFakeError,
    AdkFakeToolCall,
    run_adk_fake,
    validate_distinct_adk_fake_runtimes,
)
from .lineage.explain import explain_path, inspect_run_item
from .lineage.service import ToolCallIdentity
from .lineage.sqlite_lineage_store import SQLiteLineageStore
from .lineage.artifacts import SQLiteArtifactStore
from .package_data import legacy_project_root
from .core_models import (
    GoldenContract,
    LineageEventType,
    LineageOperation,
    VerifiedHead,
)

_ROOT = legacy_project_root()
_GOLDEN = GoldenContract.model_validate_json(
    (_ROOT / "contracts/golden_path.json").read_text()
)
_SCRIPTED_LABEL = (
    "SCRIPTED LOCAL WORKFLOW FIXTURE — NOT INDEPENDENT-AGENT OR GOOGLE ADK PROOF"
)


class DemoError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Decision:
    value: str
    operator_label: str
    rationale: str | None
    human_attestation: bool


@dataclass(slots=True)
class _Viewer:
    url: str
    server: uvicorn.Server
    thread: threading.Thread

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _call(run, number: int) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.handle.model_id,
        tool_call_id=f"demo_call_{number:03d}",
        agent_name="graphene_scripted_local",
        adapter_kind="local",
    )


def _preflight() -> None:
    if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise DemoError(
            "live workflow requires macOS with executable /usr/bin/sandbox-exec\n"
            "Run instead: uv run --frozen graphene demo --driver verified-replay"
        )
    try:
        from .viewer.viewer_app import create_viewer_app  # noqa: F401
    except (ImportError, ModuleNotFoundError) as error:
        raise DemoError("the read-only v2 viewer is unavailable") from error


def _runtime() -> tuple[Path, Path]:
    runtime = Path(tempfile.mkdtemp(prefix="graphene-demo-")).resolve()
    runtime.chmod(0o700)
    return runtime, runtime / "lineage.sqlite3"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_viewer(
    database: Path,
    root_run_id: str,
    *,
    driver: str,
    automated_fixture: bool = False,
) -> _Viewer:
    from .viewer.viewer_app import create_viewer_app

    port = _free_port()
    token = secrets.token_urlsafe(32)
    label = ADK_FAKE_PROOF_LABEL if driver == "adk-fake" else _SCRIPTED_LABEL
    viewer_driver = (
        "scripted-local-automated-fixture"
        if automated_fixture and driver == "scripted-local"
        else driver
    )
    app = create_viewer_app(
        database_path=database,
        root_run_id=root_run_id,
        read_token=token,
        mode_label=(
            f"{label} — SIMULATED OPERATOR / NOT HUMAN ATTESTATION"
            if automated_fixture
            else label
        ),
        driver=viewer_driver,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, name="graphene-viewer", daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            raise DemoError("the read-only viewer failed to start")
        time.sleep(0.01)
    return _Viewer(f"http://127.0.0.1:{port}/viewer/{root_run_id}", server, thread)


def _start_verified_replay() -> tuple[_Viewer, str]:
    from .viewer.viewer_replay import (
        REPLAY_TRUTH_LABEL,
        ReplayEvidenceInvalid,
        create_verified_replay_app,
        load_verified_replay,
    )

    try:
        replay = load_verified_replay()
    except ReplayEvidenceInvalid as error:
        raise DemoError("the checked-in verified replay is invalid") from error
    port = _free_port()
    token = secrets.token_urlsafe(32)
    server = uvicorn.Server(
        uvicorn.Config(
            create_verified_replay_app(token, replay),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(
        target=server.run,
        name="graphene-replay-viewer",
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            raise DemoError("the verified replay viewer failed to start")
        time.sleep(0.01)
    return (
        _Viewer(
            f"http://127.0.0.1:{port}/viewer/{replay.root_run_id}",
            server,
            thread,
        ),
        REPLAY_TRUTH_LABEL,
    )


def run_verified_replay(*, no_open: bool, keep_open: bool = True) -> int:
    viewer, truth_label = _start_verified_replay()
    interrupted = False
    try:
        print(
            f"\n{truth_label}\n"
            "Authoritative lineage writes: 0\n"
            "Human-attested decisions: 0\n"
            "Live agent executions: 0\n"
            "New test executions: 0\n"
            "Google ADK Runner: not used\n"
            "Gemini calls: 0\n"
            f"Viewer: {viewer.url}\n"
            "Press Ctrl-C to stop the viewer.",
            flush=True,
        )
        if not no_open:
            webbrowser.open(viewer.url)
        if keep_open:
            while True:
                time.sleep(3600)
        return 0
    except KeyboardInterrupt:
        interrupted = True
        return 130
    finally:
        viewer.close()
        state = "Replay interrupted" if interrupted else "Replay stopped"
        print(f"\n{state}. No authoritative state was created.", flush=True)


def _packet(title: str, **fields: object) -> None:
    print(f"\nDECISION PACKET — {title}", flush=True)
    for label, value in fields.items():
        rendered = str(value).replace("\n", " ")
        print(f"{label.replace('_', ' ').title()}: {rendered[:512]}", flush=True)


def _gate(
    prompt: str,
    choices: tuple[tuple[str, str], ...],
    input_fn: Callable[[str], str],
    *,
    automated_fixture: bool,
    automated_value: str,
    default: str | None,
    tty_check: Callable[[], bool],
) -> _Decision:
    values = {value for value, _ in choices}
    if automated_value not in values:
        raise DemoError("the automated fixture decision is unavailable")
    for number, (value, consequence) in enumerate(choices, 1):
        print(f"  {number}. {value} — {consequence}", flush=True)
    if automated_fixture:
        print(
            f"\n{prompt}\n"
            "SIMULATED OPERATOR — NOT HUMAN ATTESTATION\n"
            f"Automated fixture decision: {automated_value}\n"
            "This deterministic seam exercises the fixed human-gated transition "
            "but is not evidence that a person decided.",
            flush=True,
        )
        return _Decision(
            automated_value,
            "simulated-fixture",
            "deterministic process fixture",
            False,
        )
    if not tty_check():
        raise DemoError(
            "human attestation requires a real terminal; non-TTY input cannot "
            "create a human-attested decision"
        )
    try:
        suffix = f" [default: {default}]" if default is not None else " (required)"
        answer = input_fn(f"\n{prompt}{suffix}: ").strip().lower()
        if not answer and default is not None:
            answer = default
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            answer = choices[int(answer) - 1][0]
        if answer not in values:
            raise DemoError("operator selected an unavailable decision")
        label = input_fn("Public operator label [local-operator]: ").strip()
        label = label or "local-operator"
        rationale = input_fn("Optional rationale (Enter to omit): ").strip() or None
    except EOFError as error:
        raise DemoError("operator input ended before the gate decision") from error
    if not label or len(label.encode()) > 64:
        raise DemoError("operator label must contain 1 to 64 UTF-8 bytes")
    if rationale is not None and len(rationale.encode()) > 256:
        raise DemoError("operator rationale exceeds 256 UTF-8 bytes")
    return _Decision(answer, label, rationale, True)


def _pause(speed: float, seconds: float = 0.35) -> None:
    time.sleep(seconds / speed)


def run_demo(
    *,
    driver: str = "scripted-local",
    speed: float,
    no_open: bool,
    cleanup: bool,
    keep_open: bool = True,
    automated_fixture: bool = False,
    automated_decisions: tuple[str, str, str] = (
        "all_auth",
        "approve",
        "commit",
    ),
    input_fn: Callable[[str], str] = input,
    tty_check: Callable[[], bool] | None = None,
) -> int:
    if driver == "verified-replay":
        return run_verified_replay(no_open=no_open, keep_open=keep_open)
    if driver not in {"scripted-local", "adk-fake"}:
        raise DemoError(f"unsupported demo driver: {driver}")
    _preflight()
    if automated_fixture and keep_open:
        raise DemoError("the automated fixture seam requires --exit-after-demo")
    if len(automated_decisions) != 3:
        raise DemoError("the automated fixture requires exactly three decisions")
    tty_check = tty_check or (lambda: bool(sys.stdin.isatty() and sys.stdout.isatty()))
    runtime, database = _runtime()
    viewer: _Viewer | None = None
    interrupted = False
    try:
        source = bootstrap_local_run(
            database,
            task_id="baseline_max_attempts",
            profile_id="platform-maintainer@1",
            repository_root=_ROOT,
        )
        if database.stat().st_mode & 0o077:
            raise DemoError("lineage database is not owner-private")
        viewer = _start_viewer(
            database,
            source.run_id,
            driver=driver,
            automated_fixture=automated_fixture,
        )
        preservation = (
            f"Runtime will be deleted after viewer shutdown: {runtime}\n"
            "Press Ctrl-C to stop the viewer."
            if cleanup
            else f"Runtime retained: {runtime}\n"
            "Press Ctrl-C to stop the viewer. Evidence remains on disk."
        )
        mode_label = (
            ADK_FAKE_PROOF_LABEL if driver == "adk-fake" else _SCRIPTED_LABEL
        )
        print(
            f"\n{mode_label}\n"
            + (
                "Google ADK Runner: real Google ADK 2.5.0\n"
                "Deterministic fake model: yes\n"
                "External model dispatches: 0\n"
                "Google credential/project variables: unset during Runner execution\n"
                if driver == "adk-fake"
                else "Google ADK Runner: not used\n"
            )
            + "Gemini calls: 0\n"
            "Evidence source: committed and verified v2 SQLite lineage\n"
            f"Viewer: {viewer.url}\n"
            f"Private runtime: {runtime}\n",
            flush=True,
        )
        if automated_fixture:
            print(
                "AUTOMATED FIXTURE MODE\n"
                "SIMULATED OPERATOR — NOT HUMAN ATTESTATION\n"
                "No human decision proof may be claimed from this run.\n",
                flush=True,
            )
        if not no_open:
            webbrowser.open(viewer.url)

        source_adk = None
        if driver == "adk-fake":
            try:
                source_content = (
                    source.checkout_root / "app/auth/limiter.py"
                ).read_text()
                source_adk = run_adk_fake(
                    source.service,
                    source.handle,
                    role="source",
                    calls=(
                        AdkFakeToolCall(
                            call_id="adk_source_read_001",
                            operation=LineageOperation.READ_FILE,
                            arguments={"path": "app/auth/limiter.py"},
                        ),
                        AdkFakeToolCall(
                            call_id="adk_source_write_001",
                            operation=LineageOperation.WRITE_FILE,
                            arguments={
                                "path": "app/auth/limiter.py",
                                "content": source_content.replace(
                                    "MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"
                                ),
                            },
                        ),
                        AdkFakeToolCall(
                            call_id="adk_source_test_001",
                            operation=LineageOperation.RUN_FIXED_TEST,
                        ),
                        AdkFakeToolCall(
                            call_id="adk_source_completion_001",
                            operation=LineageOperation.REQUEST_COMPLETION,
                        ),
                    ),
                )
            except Exception as error:
                raise DemoError(
                    "adk-fake source Runner failed; no fallback was used"
                ) from error
        else:
            original = source.service.read_file(
                source.handle, _call(source, 1), path="app/auth/limiter.py"
            )
            _pause(speed)
            source.service.write_file(
                source.handle,
                _call(source, 2),
                path="app/auth/limiter.py",
                content=original.content.replace(
                    "MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"
                ),
            )
            _pause(speed)
            if not source.service.run_fixed_test(
                source.handle, _call(source, 3)
            ).passed:
                raise DemoError("the baseline fixed test failed")
            source.service.request_completion(source.handle, _call(source, 4))
        _pause(speed)

        review = _review(database, source.run_id)
        hunk = review["hunks"][0]
        asked = _feedback(
            database,
            argparse.Namespace(
                run_id=source.run_id,
                event_id=review["write_event_ids"][0],
                hunk_id=hunk["hunk_id"],
                message=_GOLDEN.memory.correction,
            ),
        )
        _pause(speed)
        source_events, _ = _load(database, source.run_id)
        asked_event = next(
            event
            for event in source_events
            if event.event_type == LineageEventType.CLARIFICATION_ASKED
            and event.payload.get("question_id") == asked["question_id"]
        )
        _packet(
            "SCOPE",
            decision_id=asked["question_id"],
            focus_anchor=f"event:{source.run_id}:{asked_event.event_id}",
            correction=_GOLDEN.memory.correction,
            hunk=f"{hunk['path']}:{hunk['new_start']} +{hunk['new_lines']} lines",
            why="The exact correction must be explicitly scoped before memory is proposed.",
        )
        scope = _gate(
            "SCOPE GATE: choose the durable memory scope",
            (
                ("all_auth", "may apply to every app/auth/** target"),
                (
                    "rate_limiter_only",
                    "may apply only to app/auth/limiter.py",
                ),
            ),
            input_fn,
            automated_fixture=automated_fixture,
            automated_value=automated_decisions[0],
            default="all_auth",
            tty_check=tty_check,
        )
        answered = _answer(
            database,
            argparse.Namespace(question_id=asked["question_id"], choice=scope.value),
            simulated_fixture=automated_fixture,
            human_attestation=scope.human_attestation,
            operator_label=scope.operator_label,
            operator_rationale=scope.rationale,
        )
        source_events, _ = _load(database, source.run_id)
        proposed = next(
            event
            for event in source_events
            if event.event_type == LineageEventType.MEMORY_PROPOSED
            and event.payload.get("memory_id") == answered["memory_id"]
        )
        _packet(
            "MEMORY",
            decision_id=answered["memory_id"],
            focus_anchor=f"event:{source.run_id}:{proposed.event_id}",
            rule=_GOLDEN.memory.rule,
            scope=(
                "all_auth (app/auth/**)"
                if scope.value == "all_auth"
                else "rate_limiter_only (app/auth/limiter.py)"
            ),
            revision=answered["revision"],
            digest=proposed.payload["memory_sha256"],
            why="Only this immutable scoped revision may enter an authorized handoff.",
        )
        memory = _gate(
            "MEMORY GATE: decide the displayed scoped memory revision",
            (
                ("approve", "the approved revision may enter a later handoff"),
                ("reject", "stop with no approved memory or injected context"),
            ),
            input_fn,
            automated_fixture=automated_fixture,
            automated_value=automated_decisions[1],
            default="approve",
            tty_check=tty_check,
        )
        memory_result = _memory(
            database,
            argparse.Namespace(
                memory_id=answered["memory_id"], memory_action=memory.value
            ),
            simulated_fixture=automated_fixture,
            human_attestation=memory.human_attestation,
            operator_label=memory.operator_label,
            operator_rationale=memory.rationale,
        )
        _pause(speed)
        if memory.value == "reject":
            ended = _end_rejected_run(
                database,
                source.run_id,
                str(memory_result["decision_event_id"]),
                "memory_rejected",
            )
            print(
                "\nMEMORY REJECTED — branch complete and inspectable\n"
                f"Decision ID: {answered['memory_id']}\n"
                f"Scope: {scope.value}\n"
                "State: REJECTED\n"
                f"Terminal event: {ended.event_id}\n"
                "Handoff created: no\n"
                "Consumer runtime created: no\n"
                "Local commit created: no\n"
                f"Viewer: {viewer.url}\n"
                f"{preservation}",
                flush=True,
            )
            if keep_open:
                while True:
                    time.sleep(3600)
            return 0

        billing = _handoff(
            database,
            argparse.Namespace(
                source_run_id=source.run_id,
                profile="billing-observer@1",
                task="adapted_window_seconds",
                start=False,
            ),
        )
        if billing["denial"]["model_dispatch_count"] != 0:
            raise DemoError("Billing denial unexpectedly dispatched a model")
        _pause(speed)
        auth = _handoff(
            database,
            argparse.Namespace(
                source_run_id=source.run_id,
                profile="auth-maintainer@1",
                task="adapted_window_seconds",
                start=True,
            ),
        )
        consumer = resume_fresh_consumer(
            database, auth["consumer_run_id"], repository_root=_ROOT
        )
        if driver == "adk-fake":
            try:
                consumer_content = (
                    consumer.checkout_root / "app/auth/limiter.py"
                ).read_text()
                consumer_adk = run_adk_fake(
                    consumer.service,
                    consumer.handle,
                    role="consumer",
                    calls=(
                        AdkFakeToolCall(
                            call_id="adk_consumer_evidence_001",
                            operation=LineageOperation.OPEN_EVIDENCE,
                            arguments={"evidence_id": hunk["evidence_id"]},
                        ),
                        AdkFakeToolCall(
                            call_id="adk_consumer_read_limiter_001",
                            operation=LineageOperation.READ_FILE,
                            arguments={"path": "app/auth/limiter.py"},
                        ),
                        AdkFakeToolCall(
                            call_id="adk_consumer_read_test_001",
                            operation=LineageOperation.READ_FILE,
                            arguments={"path": "tests/test_security_policy.py"},
                        ),
                        AdkFakeToolCall(
                            call_id="adk_consumer_write_limiter_001",
                            operation=LineageOperation.WRITE_FILE,
                            arguments={
                                "path": "app/auth/limiter.py",
                                "content": consumer_content.replace(
                                    "WINDOW_SECONDS = 60", "WINDOW_SECONDS = 90"
                                ),
                            },
                        ),
                        AdkFakeToolCall(
                            call_id="adk_consumer_write_test_001",
                            operation=LineageOperation.WRITE_FILE,
                            arguments={
                                "path": "tests/test_security_policy.py",
                                "content": (
                                    _GOLDEN.memory.expected_security_test_content
                                ),
                            },
                        ),
                        AdkFakeToolCall(
                            call_id="adk_consumer_test_001",
                            operation=LineageOperation.RUN_FIXED_TEST,
                        ),
                        AdkFakeToolCall(
                            call_id="adk_consumer_completion_001",
                            operation=LineageOperation.REQUEST_COMPLETION,
                        ),
                    ),
                )
                if source_adk is None:
                    raise AdkFakeError("source ADK execution result is missing")
                validate_distinct_adk_fake_runtimes(source_adk, consumer_adk)
            except Exception as error:
                raise DemoError(
                    "adk-fake consumer Runner failed; no fallback was used"
                ) from error
        else:
            consumer.service.open_evidence(
                consumer.handle, _call(consumer, 5), evidence_id=hunk["evidence_id"]
            )
            _pause(speed)
            limiter = consumer.service.read_file(
                consumer.handle, _call(consumer, 6), path="app/auth/limiter.py"
            )
            consumer.service.read_file(
                consumer.handle,
                _call(consumer, 7),
                path="tests/test_security_policy.py",
            )
            _pause(speed)
            consumer.service.write_file(
                consumer.handle,
                _call(consumer, 8),
                path="app/auth/limiter.py",
                content=limiter.content.replace(
                    "WINDOW_SECONDS = 60", "WINDOW_SECONDS = 90"
                ),
            )
            _pause(speed)
            consumer.service.write_file(
                consumer.handle,
                _call(consumer, 9),
                path="tests/test_security_policy.py",
                content=_GOLDEN.memory.expected_security_test_content,
            )
            _pause(speed)
            if not consumer.service.run_fixed_test(
                consumer.handle, _call(consumer, 10)
            ).passed:
                raise DemoError("the consumer fixed retest failed")
            consumer.service.request_completion(consumer.handle, _call(consumer, 11))

        consumer_events, _ = _load(database, consumer.run_id)
        opened = next(
            event
            for event in consumer_events
            if event.event_type == LineageEventType.TOOL_COMPLETED
            and event.payload.get("operation")
            == LineageOperation.OPEN_EVIDENCE.value
        )
        _packet(
            "HANDOFF PROOF",
            billing=(
                f"denied ({billing['denial']['reason_code']}); "
                "model dispatches=0"
            ),
            approved_context=(
                f"scope={scope.value}; brief_sha256={auth['brief_sha256']}; "
                f"fresh_consumer={consumer.run_id}"
            ),
            consumer_reference=(
                f"event={opened.event_id}; "
                f"opened_evidence={opened.payload['evidence_id']}"
            ),
            proof_limit="Delivery and opening were observed; causality was not established.",
        )
        _review(database, consumer.run_id)

        consumer_events, _ = _load(database, consumer.run_id)
        changeset = next(
            event
            for event in consumer_events
            if event.event_type == LineageEventType.CHANGESET_PARSED
        )
        test_receipt = next(
            event
            for event in consumer_events
            if event.event_type == LineageEventType.TEST_RECEIPT_CREATED
        )
        candidate = _prepare_candidate(
            database,
            consumer.run_id,
        )
        consumer_events, _ = _load(database, consumer.run_id)
        candidate_event = next(
            event
            for event in consumer_events
            if event.event_type == LineageEventType.CANDIDATE_CREATED
            and event.payload.get("candidate_id") == candidate.candidate_id
        )
        _packet(
            "PROMOTION",
            candidate_id=candidate.candidate_id,
            focus_anchor=f"event:{consumer.run_id}:{candidate_event.event_id}",
            changed_paths=", ".join(changeset.payload["changed_paths"]),
            test_receipt=(
                f"{test_receipt.payload['receipt_id']} "
                f"sha256={test_receipt.payload['receipt_sha256']} passed=true"
            ),
            candidate_digest=changeset.payload["candidate_patch_sha256"],
            why="The final decision binds this exact candidate and passing fixed-test receipt; rejection creates no commit.",
        )
        final = _gate(
            "CANDIDATE GATE: decide the exact verified bounded candidate",
            (
                (
                    "commit",
                    "Approve and create isolated local commit",
                ),
                ("reject", "record rejection and create no local commit"),
            ),
            input_fn,
            automated_fixture=automated_fixture,
            automated_value=automated_decisions[2],
            default=None,
            tty_check=tty_check,
        )
        if final.value == "reject":
            rejected = _reject_candidate(
                database,
                consumer.run_id,
                simulated_fixture=automated_fixture,
                human_attestation=final.human_attestation,
                operator_label=final.operator_label,
                operator_rationale=final.rationale,
            )
            print(
                "\nCANDIDATE REJECTED — branch complete and inspectable\n"
                f"Decision event ID: {rejected['decision_event_id']}\n"
                f"Candidate ID: {candidate.candidate_id}\n"
                f"Scope: {scope.value}\n"
                f"State: {rejected['state']}\n"
                "Local commit created: no\n"
                "Push / PR / deployment: no\n"
                f"Viewer: {viewer.url}\n"
                f"{preservation}",
                flush=True,
            )
            if keep_open:
                while True:
                    time.sleep(3600)
            return 0
        promoted = _promote(
            database,
            consumer.run_id,
            simulated_fixture=automated_fixture,
            human_attestation=final.human_attestation,
            operator_label=final.operator_label,
            operator_rationale=final.rationale,
        )
        artifacts = SQLiteArtifactStore(database, read_only=True)
        store = SQLiteLineageStore(
            database, artifact_resolver=artifacts.resolve, read_only=True
        )
        inspect_run_item(store, artifacts, source.run_id, hunk["evidence_id"])
        why = explain_path(store, artifacts, consumer.run_id, "app/auth/limiter.py")
        if not {"PACKED_IN", "INJECTED_INTO", "PROMOTED_AS"} <= {
            item["relation"] for item in why["relationships"]
        }:
            raise DemoError(
                "final why path is missing a required explicit relationship"
            )
        heads = (store.verify(source.run_id), store.verify(consumer.run_id))
        if not all(isinstance(head, VerifiedHead) for head in heads):
            raise DemoError("final lineage verification failed")
        print(
            "\nDEMO COMPLETE — committed lineage verified\n"
            f"Origin run: {source.run_id}\n"
            f"Consumer run: {consumer.run_id}\n"
            f"Promotion state: {promoted['state']}\n"
            f"Outcome: {promoted['outcome']}\n"
            f"Local commit SHA: {promoted['local_commit_sha']}\n"
            f"Checkout: {consumer.checkout_root}\n"
            "Verify: git -C "
            f"{consumer.checkout_root} show --stat --oneline "
            f"{promoted['local_commit_sha']}\n"
            "Local isolated commit — not pushed / no PR / no deployment\n"
            f"Viewer: {viewer.url}\n"
            f"{preservation}",
            flush=True,
        )
        if keep_open:
            while True:
                time.sleep(3600)
        return 0
    except KeyboardInterrupt:
        interrupted = True
        return 130
    finally:
        if viewer is not None:
            viewer.close()
        if cleanup:
            shutil.rmtree(runtime, ignore_errors=True)
            print(f"\nRuntime deleted by --cleanup: {runtime}", flush=True)
        else:
            state = "Viewer stopped" if interrupted else "Demo stopped"
            print(f"\n{state}. Runtime retained: {runtime}", flush=True)


__all__ = ["DemoError", "run_demo", "run_verified_replay"]
