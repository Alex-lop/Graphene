from __future__ import annotations

import argparse
import platform
import secrets
import shutil
import socket
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
    _feedback,
    _handoff,
    _load,
    _memory,
    _promote,
    _review,
)
from .context.consumer import resume_fresh_consumer
from .lineage.explain import explain_path, inspect_run_item
from .lineage.service import ToolCallIdentity
from .lineage.store import SQLiteLineageStore
from .lineage.artifacts import SQLiteArtifactStore
from .models import GoldenContract, LineageEventType, VerifiedHead

_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = GoldenContract.model_validate_json(
    (_ROOT / "contracts/golden_path.json").read_text()
)


class DemoError(RuntimeError):
    pass


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
            "scripted-local requires macOS with executable /usr/bin/sandbox-exec"
        )
    try:
        from .viewer.app import create_viewer_app  # noqa: F401
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
    database: Path, root_run_id: str, *, automated_fixture: bool = False
) -> _Viewer:
    from .viewer.app import create_viewer_app

    port = _free_port()
    token = secrets.token_urlsafe(32)
    app = create_viewer_app(
        database_path=database,
        root_run_id=root_run_id,
        read_token=token,
        mode_label=(
            "SCRIPTED LOCAL — SIMULATED OPERATOR / NOT HUMAN ATTESTATION"
            if automated_fixture
            else "SCRIPTED LOCAL"
        ),
        driver=(
            "scripted-local-automated-fixture"
            if automated_fixture
            else "scripted-local"
        ),
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


def _packet(title: str, **fields: object) -> None:
    print(f"\nDECISION PACKET — {title}", flush=True)
    for label, value in fields.items():
        rendered = str(value).replace("\n", " ")
        print(f"{label.replace('_', ' ').title()}: {rendered[:512]}", flush=True)


def _gate(
    prompt: str,
    expected: str,
    input_fn: Callable[[str], str],
    *,
    automated_fixture: bool,
) -> None:
    if automated_fixture:
        print(
            f"\n{prompt}\n"
            "SIMULATED OPERATOR — NOT HUMAN ATTESTATION\n"
            f"Automated fixture decision: {expected}\n"
            "This deterministic seam exercises the fixed human-gated transition "
            "but is not evidence that a person decided.",
            flush=True,
        )
        return
    try:
        answer = input_fn(
            f"\n{prompt}\nType {expected!r} or press Enter for this safe default: "
        )
    except EOFError as error:
        raise DemoError("operator input ended before the gate decision") from error
    if (answer.strip() or expected).lower() != expected:
        raise DemoError("operator declined the demo gate")


def _pause(speed: float, seconds: float = 0.35) -> None:
    time.sleep(seconds / speed)


def run_demo(
    *,
    speed: float,
    no_open: bool,
    cleanup: bool,
    keep_open: bool = True,
    automated_fixture: bool = False,
    input_fn: Callable[[str], str] = input,
) -> int:
    _preflight()
    if automated_fixture and keep_open:
        raise DemoError("the automated fixture seam requires --exit-after-demo")
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
            database, source.run_id, automated_fixture=automated_fixture
        )
        preservation = (
            f"Runtime will be deleted after viewer shutdown: {runtime}\n"
            "Press Ctrl-C to stop the viewer."
            if cleanup
            else f"Runtime retained: {runtime}\n"
            "Press Ctrl-C to stop the viewer. Evidence remains on disk."
        )
        print(
            "\nSCRIPTED LOCAL\n"
            "Google ADK Runner: not used\n"
            "Gemini calls: 0\n"
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

        original = source.service.read_file(
            source.handle, _call(source, 1), path="app/auth/limiter.py"
        )
        _pause(speed)
        source.service.write_file(
            source.handle,
            _call(source, 2),
            path="app/auth/limiter.py",
            content=original.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"),
        )
        _pause(speed)
        if not source.service.run_fixed_test(source.handle, _call(source, 3)).passed:
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
        _packet(
            "SCOPE",
            correction=_GOLDEN.memory.correction,
            proposed_scope="all_auth (app/auth/**)",
            hunk=f"{hunk['path']}:{hunk['new_start']} +{hunk['new_lines']} lines",
            why="The exact correction must be explicitly scoped before memory is proposed.",
        )
        _gate(
            "SCOPE GATE: apply this correction to every app/auth/** change?",
            "all_auth",
            input_fn,
            automated_fixture=automated_fixture,
        )
        answered = _answer(
            database,
            argparse.Namespace(question_id=asked["question_id"], choice="all_auth"),
            simulated_fixture=automated_fixture,
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
            rule=_GOLDEN.memory.rule,
            scope="all_auth (app/auth/**)",
            revision=answered["revision"],
            digest=proposed.payload["memory_sha256"],
            why="Only this immutable scoped revision may enter an authorized handoff.",
        )
        _gate(
            "MEMORY GATE: approve the displayed scoped memory revision?",
            "approve",
            input_fn,
            automated_fixture=automated_fixture,
        )
        _memory(
            database,
            argparse.Namespace(memory_id=answered["memory_id"], memory_action="approve"),
            simulated_fixture=automated_fixture,
        )
        _pause(speed)

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
            content=limiter.content.replace("WINDOW_SECONDS = 60", "WINDOW_SECONDS = 90"),
        )
        _pause(speed)
        consumer.service.write_file(
            consumer.handle,
            _call(consumer, 9),
            path="tests/test_security_policy.py",
            content=_GOLDEN.memory.expected_security_test_content,
        )
        _pause(speed)
        if not consumer.service.run_fixed_test(consumer.handle, _call(consumer, 10)).passed:
            raise DemoError("the consumer fixed retest failed")
        consumer.service.request_completion(consumer.handle, _call(consumer, 11))
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
        _packet(
            "PROMOTION",
            changed_paths=", ".join(changeset.payload["changed_paths"]),
            test_receipt=(
                f"{test_receipt.payload['receipt_id']} "
                f"sha256={test_receipt.payload['receipt_sha256']} passed=true"
            ),
            candidate_digest=changeset.payload["candidate_patch_sha256"],
            why="Promotion binds these exact paths and candidate digest to the passing fixed-test receipt.",
        )
        _gate(
            "PROMOTION GATE: promote the verified bounded candidate?",
            "promote",
            input_fn,
            automated_fixture=automated_fixture,
        )
        promoted = _promote(
            database, consumer.run_id, simulated_fixture=automated_fixture
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
            raise DemoError("final why path is missing a required explicit relationship")
        heads = (store.verify(source.run_id), store.verify(consumer.run_id))
        if not all(isinstance(head, VerifiedHead) for head in heads):
            raise DemoError("final lineage verification failed")
        print(
            "\nDEMO COMPLETE — committed lineage verified\n"
            f"Origin run: {source.run_id}\n"
            f"Consumer run: {consumer.run_id}\n"
            f"Promotion state: {promoted['state']}\n"
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


__all__ = ["DemoError", "run_demo"]
