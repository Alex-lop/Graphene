from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
from graphene.execution import adapter
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.service import (
    RuntimeOperationError,
    ScopedApplicationService,
    ToolCallIdentity,
)
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    EventInput,
    EvidenceKind,
    GoldenContract,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

ROOT = Path(__file__).parents[2]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
CANARY = "EXECUTOR_NON_CONTRACT_CANARY_2f84c91d"
RUN_ID = "run_executor_scope_001"

ATTACKS = {
    "warning": "warnings.warn(stolen())",
    "assertion": "assert False, stolen()",
    "exception": "raise RuntimeError(stolen())",
    "subprocess": (
        "result = subprocess.run(\n"
        '    [sys.executable, "-c", CHILD], capture_output=True, text=True\n'
        ")\n"
        "raise AssertionError(result.stdout + result.stderr)"
    ),
    "timeout": "print(stolen(), flush=True)\nwhile True:\n    pass",
}


def _attack_test(channel: str) -> str:
    body = "\n    ".join(ATTACKS[channel].splitlines())
    names = ("ambient-secret.txt", "ambient-secret-link")
    return f'''import subprocess
import sys
import warnings
from pathlib import Path

NAMES = {names!r}
CHILD = """from pathlib import Path
for name in {names!r}:
    try:
        print(Path(name).read_text())
    except OSError:
        pass
"""

def stolen():
    for name in NAMES:
        try:
            return Path(name).read_text()
        except OSError:
            pass
    return "blocked"

def test_extraction_channel():
    {body}
'''


def _runtime(tmp_path: Path, checkout: Path, policy):
    database = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    source = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "action": "run.started", "run_id": RUN_ID},
    )
    started = store.append(
        RUN_ID,
        VerifiedHead(run_id=RUN_ID, seq=0, event_sha256=None, event_count=0),
        "executor_scope_start_key_001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha="a" * 40,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=source.id,
                sha256=source.sha256,
            ),
            payload={"state": "STARTING"},
        ),
    )
    service = ScopedApplicationService(store, artifacts)
    handle = service.create_handle(
        run_id=RUN_ID,
        repo_id="graphene-demo",
        base_sha="a" * 40,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
        session_id="session_executor_scope_001",
        invocation_id="invocation_executor_scope_001",
        model_id="local-security-falsifier",
        read_scope=tuple(sorted(set(policy.tracked_paths) | set(policy.mutable_paths))),
        write_scope=policy.mutable_paths,
        tools=(LineageOperation.RUN_FIXED_TEST,),
        evidence=(),
        fixed_test_profile="fixture_pytest",
        fixture_policy=policy,
        checkout_root=checkout,
    )
    assert handle.head.event_sha256 == started.event_sha256
    call = ToolCallIdentity(
        session_id=handle.session_id,
        invocation_id=handle.invocation_id,
        model_id=handle.model_id,
        tool_call_id="tool_call_executor_scope_001",
        agent_name="security_falsifier",
        adapter_kind="local",
    )
    return database, artifacts, store, service, handle, call


def _race_nested_directory(monkeypatch, checkout: Path, outside: Path) -> None:
    outside_app = outside / "app"
    shutil.copytree(checkout / "app", outside_app)
    (outside_app / "__init__.py").write_text(f"raise RuntimeError({CANARY!r})\n")
    real_open = adapter.os.open
    raced = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal raced
        if path == "app" and dir_fd is not None and not raced:
            raced = True
            (checkout / "app").rename(checkout / "original-app")
            (checkout / "app").symlink_to(outside_app, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(adapter.os, "open", racing_open)


@pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the claim is limited to the macOS sandbox executor",
)
@pytest.mark.parametrize(
    "scenario",
    (
        "warning",
        "assertion",
        "exception",
        "subprocess",
        "timeout",
        "mutable_symlink",
        "nested_directory_race",
    ),
)
def test_non_contract_bytes_never_escape_test_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
):
    checkout = tmp_path / "checkout"
    shutil.copytree(ROOT / GOLDEN.fixture.root, checkout)
    outside = tmp_path / "outside"
    outside.mkdir()
    host_secret = outside / "host-secret.txt"
    host_secret.write_text(CANARY)
    (checkout / "ambient-secret.txt").write_text(CANARY)
    (checkout / "ambient-secret-link").symlink_to(host_secret)
    policy = GOLDEN.fixture.model_copy(
        update={"test_timeout_seconds": 1 if scenario == "timeout" else 15}
    )

    test_path = checkout / "tests/test_security_policy.py"
    if scenario == "mutable_symlink":
        test_path.symlink_to(host_secret)
    elif scenario == "nested_directory_race":
        _race_nested_directory(monkeypatch, checkout, outside)
    else:
        test_path.write_text(_attack_test(scenario))

    database, _, store, service, handle, call = _runtime(tmp_path, checkout, policy)
    result = None
    failure = None
    try:
        result = service.run_fixed_test(handle, call)
        transient = result.output.encode()
    except RuntimeOperationError as error:
        failure = error
        causes = []
        current: BaseException | None = error
        while current is not None:
            causes.append(str(current))
            current = current.__cause__
        transient = "\n".join(causes).encode()

    assert CANARY.encode() not in transient
    events = store.tail(RUN_ID, 0, 256)
    if result is not None:
        assert "ERROR collecting" not in result.output
    if scenario == "warning":
        assert result is not None and result.exit_code == 0
        assert result.timed_out is False and "blocked" in result.output
    elif scenario in {"assertion", "exception"}:
        assert result is not None and result.exit_code != 0
        assert result.timed_out is False and "blocked" in result.output
    elif scenario == "subprocess":
        assert result is not None and result.exit_code != 0
        assert result.timed_out is False
    elif scenario == "timeout":
        assert result is not None and result.timed_out is True
    else:
        assert failure is not None
        assert events[-1].event_type == LineageEventType.TOOL_FAILED
        if scenario == "nested_directory_race":
            assert (checkout / "app").is_symlink()
    public_events = json.dumps(
        [event.model_dump(mode="json") for event in events], sort_keys=True
    ).encode()
    assert CANARY.encode() not in public_events
    with sqlite3.connect(database) as connection:
        durable_artifacts = b"\n".join(
            bytes(row[0])
            for row in connection.execute(
                "SELECT artifact_bytes FROM lineage_artifacts"
            )
        )
    assert CANARY.encode() not in durable_artifacts
