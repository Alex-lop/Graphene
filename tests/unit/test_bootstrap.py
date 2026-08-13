from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from graphene.bootstrap import (
    LOCAL_MODEL_ID,
    BootstrapConfigurationError,
    BootstrapConflict,
    bootstrap_local_run,
)
from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.lineage.service import ToolCallIdentity
from graphene.models import (
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    SourceKind,
    TruthKind,
    VerifiedHead,
)

ROOT = Path(__file__).parents[2]


def _bootstrap(runtime: Path):
    runtime.mkdir(mode=0o700, exist_ok=True)
    return bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )


def test_bootstrap_creates_one_authoritative_run_and_usable_service(tmp_path: Path):
    result = _bootstrap(tmp_path / "runtime")

    assert result.database_path.is_file()
    assert stat.S_IMODE(result.database_path.stat().st_mode) == 0o600
    assert result.checkout_root.is_dir()
    assert result.started_event.event_type == LineageEventType.RUN_STARTED
    assert result.started_event.payload == {"state": "STARTING"}
    assert result.started_event.session_id is None
    assert result.started_event.invocation_id is None
    assert result.started_event.model_id is None
    assert result.started_event.tool_call_id is None
    assert result.started_event.repo_id == "graphene-demo"
    assert result.started_event.base_sha == result.handle.base_sha
    assert result.started_event.agent_profile_id == "platform-maintainer@1"
    assert result.started_event.policy_revision == 1
    assert result.started_event.truth_kind == TruthKind.SERVER_DERIVED
    assert result.started_event.authority == LineageAuthority.LIFECYCLE_SERVICE
    assert result.started_event.source_ref.kind == SourceKind.LIFECYCLE_REQUEST
    assert result.started_event.references == ()
    assert result.handle.head == VerifiedHead(
        run_id=result.run_id,
        seq=1,
        event_sha256=result.started_event.event_sha256,
        event_count=1,
    )
    assert result.head == result.handle.head
    assert result.projection.run_id == result.run_id
    assert result.projection.state == "STARTING"
    assert result.store.tail(result.run_id, 0, 256) == (result.started_event,)
    assert result.model_id == LOCAL_MODEL_ID
    assert result.handle.tools == tuple(LineageOperation)
    assert result.handle.write_scope == ("app/auth/limiter.py",)
    assert set(result.handle.write_scope) <= set(result.handle.read_scope)

    source = result.artifacts.resolve(
        result.started_event.source_ref.kind.value,
        result.started_event.source_ref.id,
    )
    assert source is not None
    source_record = json.loads(source)
    assert source_record == {
        "schema_version": 2,
        "action": "run.started",
        "run_id": result.run_id,
        "task_id": "baseline_max_attempts",
        "repo_id": "graphene-demo",
        "base_sha": result.handle.base_sha,
        "agent_profile_id": "platform-maintainer@1",
        "policy_revision": 1,
        "session_id": result.session_id,
        "invocation_id": result.invocation_id,
        "model_id": LOCAL_MODEL_ID,
        "fixture_tree_sha256": result.handle.fixture_policy.tree_sha256,
        "checkout_binding_sha256": sha256_hex(str(result.checkout_root).encode()),
        "database_binding_sha256": sha256_hex(str(result.database_path).encode()),
    }

    read = result.service.read_file(
        result.handle,
        ToolCallIdentity(
            session_id=result.session_id,
            invocation_id=result.invocation_id,
            model_id=result.model_id,
            tool_call_id="tool_call_bootstrap_001",
            agent_name="graphene_local",
            adapter_kind="local",
        ),
        path="app/auth/limiter.py",
    )
    assert "MAX_ATTEMPTS" in read.content
    assert result.store.verify(result.run_id) == result.handle.head


def test_bootstrap_exact_restart_reuses_ids_checkout_and_start(tmp_path: Path):
    runtime = tmp_path / "runtime"
    first = _bootstrap(runtime)
    checkout_inode = first.checkout_root.stat().st_ino
    (first.checkout_root / ".git/config").write_text("[safe]\n\tbare = false\n")
    hook = first.checkout_root / ".git/hooks/local-only"
    hook.write_text("auxiliary metadata is not runtime-visible")

    second = _bootstrap(runtime)

    assert second.run_id == first.run_id
    assert second.session_id == first.session_id
    assert second.invocation_id == first.invocation_id
    assert second.started_event == first.started_event
    assert second.checkout_root.stat().st_ino == checkout_inode
    assert second.store.tail(second.run_id, 0, 256) == (first.started_event,)
    assert hook.read_text() == "auxiliary metadata is not runtime-visible"

    namespace = canonical_json_sha256(
        {
            "database_path": str(first.database_path),
            "task_id": "baseline_max_attempts",
            "profile_id": "platform-maintainer@1",
        }
    )
    assert first.run_id == "run_" + sha256_hex(f"run\0{namespace}".encode())[:24]

    alias = runtime / "unused" / ".." / "lineage.sqlite3"
    third = bootstrap_local_run(
        alias,
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )
    assert third.run_id == first.run_id


def test_progressed_read_rehydrates_and_second_bound_task_can_share_database(
    tmp_path: Path,
):
    runtime = tmp_path / "runtime"
    result = _bootstrap(runtime)
    result.service.read_file(
        result.handle,
        ToolCallIdentity(
            session_id=result.session_id,
            invocation_id=result.invocation_id,
            model_id=result.model_id,
            tool_call_id="tool_call_bootstrap_002",
            agent_name="graphene_local",
            adapter_kind="local",
        ),
        path="app/auth/limiter.py",
    )
    before = result.store.verify(result.run_id)

    resumed = _bootstrap(runtime)
    assert resumed.run_id == result.run_id
    assert resumed.head == before
    assert resumed.projection.head_seq == before.seq
    assert resumed.handle._observed_versions["app/auth/limiter.py"]

    assert result.store.verify(result.run_id) == before
    assert result.checkout_root.is_dir()

    with pytest.raises(BootstrapConfigurationError, match="not bound"):
        bootstrap_local_run(
            runtime / "lineage.sqlite3",
            task_id="baseline_max_attempts",
            profile_id="auth-maintainer@1",
            repository_root=ROOT,
        )
    second = bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="adapted_window_seconds",
        profile_id="auth-maintainer@1",
        repository_root=ROOT,
    )
    assert second.run_id != result.run_id
    assert second.store.tail(second.run_id, 0, 256) == (second.started_event,)
    assert second.database_path == result.database_path


def test_progressed_write_rehydrates_only_from_bound_file_version(tmp_path: Path):
    runtime = tmp_path / "runtime"
    result = _bootstrap(runtime)

    def call(value: str) -> ToolCallIdentity:
        return ToolCallIdentity(
            session_id=result.session_id,
            invocation_id=result.invocation_id,
            model_id=result.model_id,
            tool_call_id=value,
            agent_name="graphene_local",
            adapter_kind="local",
        )
    read = result.service.read_file(
        result.handle,
        call("tool_call_restart_read_001"),
        path="app/auth/limiter.py",
    )
    changed = read.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4")
    written = result.service.write_file(
        result.handle,
        call("tool_call_restart_write_001"),
        path="app/auth/limiter.py",
        content=changed,
    )

    resumed = _bootstrap(runtime)

    assert resumed.checkout_root.joinpath("app/auth/limiter.py").read_text() == changed
    assert resumed.handle._observed_versions["app/auth/limiter.py"] == (
        written.after_file_version_id
    )
    assert resumed.handle._written_versions["app/auth/limiter.py"] == (
        written.after_file_version_id
    )


def test_tampered_checkout_is_not_rehydrated(tmp_path: Path):
    runtime = tmp_path / "runtime"
    result = _bootstrap(runtime)
    target = result.checkout_root / "app/auth/limiter.py"
    target.write_text(target.read_text() + "\n# uncommitted substitution\n")
    ambient = result.checkout_root / "ambient-canary.txt"
    ambient.write_text("not contract-owned")
    exclude = result.checkout_root / ".git/info/exclude"
    exclude.write_text(exclude.read_text() + "\nambient-canary.txt\n")
    before = result.store.verify(result.run_id)

    with pytest.raises(BootstrapConflict, match="runtime checkout"):
        _bootstrap(runtime)

    assert result.store.verify(result.run_id) == before
    assert "uncommitted substitution" in target.read_text()
    assert ambient.read_text() == "not contract-owned"


@pytest.mark.parametrize(
    ("relative", "replacement"),
    [
        ((".git", "HEAD"), b"ref: refs/heads/substituted\n"),
        ((".git", "refs", "heads", "main"), b"0" * 40 + b"\n"),
    ],
)
def test_checkout_git_identity_substitution_fails_closed(
    tmp_path: Path,
    relative: tuple[str, ...],
    replacement: bytes,
):
    runtime = tmp_path / "runtime"
    result = _bootstrap(runtime)
    target = result.checkout_root.joinpath(*relative)
    target.write_bytes(replacement)
    before = result.store.verify(result.run_id)

    with pytest.raises(BootstrapConflict, match="frozen base"):
        _bootstrap(runtime)

    assert target.read_bytes() == replacement
    assert result.store.verify(result.run_id) == before


def test_unsafe_paths_and_unrelated_runtime_state_are_rejected(tmp_path: Path):
    with pytest.raises(BootstrapConfigurationError, match="absolute"):
        bootstrap_local_run(
            Path("relative.sqlite3"),
            task_id="baseline_max_attempts",
            profile_id="platform-maintainer@1",
            repository_root=ROOT,
        )

    target = tmp_path / "symlink-target"
    target.mkdir(mode=0o700)
    symlink = tmp_path / "runtime-link"
    symlink.symlink_to(target, target_is_directory=True)
    with pytest.raises(BootstrapConfigurationError, match="symlink"):
        bootstrap_local_run(
            symlink / "lineage.sqlite3",
            task_id="baseline_max_attempts",
            profile_id="platform-maintainer@1",
            repository_root=ROOT,
        )
    assert not (target / "lineage.sqlite3").exists()

    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    canary = public / "do-not-touch"
    canary.write_text("preserved")
    with pytest.raises(BootstrapConfigurationError, match="private"):
        bootstrap_local_run(
            public / "lineage.sqlite3",
            task_id="baseline_max_attempts",
            profile_id="platform-maintainer@1",
            repository_root=ROOT,
        )
    assert canary.read_text() == "preserved"

    insecure = tmp_path / "insecure-database"
    insecure.mkdir(mode=0o700)
    database = insecure / "lineage.sqlite3"
    database.write_bytes(b"permission canary")
    database.chmod(0o640)
    with pytest.raises(BootstrapConflict, match="0600"):
        bootstrap_local_run(
            database,
            task_id="baseline_max_attempts",
            profile_id="platform-maintainer@1",
            repository_root=ROOT,
        )
    assert database.read_bytes() == b"permission canary"
    assert stat.S_IMODE(database.stat().st_mode) == 0o640

    repository_link = tmp_path / "repository-link"
    repository_link.symlink_to(ROOT, target_is_directory=True)
    with pytest.raises(BootstrapConfigurationError, match="symlink"):
        bootstrap_local_run(
            tmp_path / "never-created" / "lineage.sqlite3",
            task_id="baseline_max_attempts",
            profile_id="platform-maintainer@1",
            repository_root=repository_link,
        )
    assert not (tmp_path / "never-created").exists()


def test_private_runtime_may_be_the_process_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime = tmp_path / "runtime-cwd"
    runtime.mkdir(mode=0o700)
    monkeypatch.chdir(runtime)

    result = bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )

    assert result.runtime_dir == runtime
    assert result.started_event.seq == 1
