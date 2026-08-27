from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphene.execution.adapter import (
    NORTH_STAR_CHECK_COMMAND,
    NORTH_STAR_FINAL_CHECK_COMMAND,
)
from graphene.orchestration.mission_models import CommandTemplate
from graphene.orchestration.sandbox import (
    DockerExecutor,
    DockerUnavailable,
    SandboxError,
    SandboxLimits,
    build_docker_create_argv,
    command_template_sha256,
    materialize_repository_view,
    validate_command_template,
)


TEMPLATE = CommandTemplate(
    template_id="fixture-tests",
    argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
    timeout_seconds=15,
)
IMAGE_ID = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64


def test_create_argv_is_the_complete_frozen_boundary(tmp_path: Path) -> None:
    argv = build_docker_create_argv(
        docker_bin=Path("/usr/bin/docker"),
        image_id=IMAGE_ID,
        workspace=tmp_path.resolve(),
        owner_id="attempt-1",
        container_name="graphene-attempt-1",
        command=validate_command_template(TEMPLATE),
        cwd=None,
        limits=SandboxLimits(),
    )

    assert argv[:2] == ("/usr/bin/docker", "create")
    for exact in (
        ("--network", "none"),
        ("--ipc", "none"),
        ("--user", "65532:65532"),
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges=true"),
        ("--pull", "never"),
        ("--log-driver", "none"),
    ):
        offset = argv.index(exact[0])
        assert argv[offset : offset + 2] == exact
    assert "--read-only" in argv
    assert "--init" in argv
    for option, expected in (
        ("--pids-limit", "64"),
        ("--memory", str(512 * 1024 * 1024)),
        ("--memory-swap", str(512 * 1024 * 1024)),
        ("--cpus", "1.0"),
    ):
        offset = argv.index(option)
        assert argv[offset + 1] == expected
    assert "size=67108864" in argv[argv.index("--tmpfs") + 1]
    assert argv[argv.index("--mount") + 1].endswith(",target=/workspace,readonly")
    assert argv[-7:] == (
        IMAGE_ID,
        "/usr/local/bin/python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    )


def test_template_is_exact_and_digest_is_stable() -> None:
    assert validate_command_template(TEMPLATE)[0] == "/usr/local/bin/python"
    assert command_template_sha256(TEMPLATE) == command_template_sha256(TEMPLATE)
    with pytest.raises(SandboxError, match="frozen"):
        validate_command_template(
            TEMPLATE.model_copy(update={"argv": (*TEMPLATE.argv, "tests")})
        )


@pytest.mark.parametrize(
    ("template_id", "command"),
    [
        ("orders-migration-check", NORTH_STAR_FINAL_CHECK_COMMAND),
        ("orders-migration-task-check", NORTH_STAR_CHECK_COMMAND),
    ],
)
def test_orders_migration_checks_are_frozen(
    template_id: str, command: tuple[str, ...]
) -> None:
    template = CommandTemplate(
        template_id=template_id,
        argv=command,
        timeout_seconds=60,
    )
    assert validate_command_template(template) == (
        "/usr/local/bin/python",
        *command[1:],
    )
    with pytest.raises(SandboxError, match="frozen"):
        validate_command_template(
            template.model_copy(update={"template_id": "fixture-tests"})
        )


def test_repository_view_is_scoped_and_drops_links_and_credentials(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pkg").mkdir()
    (source / "pkg/code.py").write_text("safe = True\n")
    (source / "pkg/ignored.py").write_text("ignored = True\n")
    (source / ".env").write_text("SECRET=canary")
    (source / ".git").mkdir()
    (source / ".git/config").write_text("canary")
    destination = tmp_path / "view"
    copied = materialize_repository_view(
        source,
        destination,
        scopes=("pkg/**", ".env", ".git/**"),
        exclusions=("pkg/ignored.py",),
    )

    assert copied == ("pkg/code.py",)
    assert (destination / "pkg/code.py").read_text() == "safe = True\n"
    assert not (destination / ".env").exists()
    assert not (destination / ".git").exists()


def test_repository_view_rejects_scoped_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "outside").symlink_to(tmp_path / "not-present")
    with pytest.raises(SandboxError, match="symlinks"):
        materialize_repository_view(
            source,
            tmp_path / "view",
            scopes=("outside",),
        )


def test_repository_view_uses_anchored_globs_and_bounded_scanning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "top.py").write_text("selected = True\n")
    (source / "nested").mkdir()
    (source / "nested" / "top.py").write_text("selected = False\n")

    copied = materialize_repository_view(
        source,
        tmp_path / "view",
        scopes=("top.py",),
    )
    assert copied == ("top.py",)

    with pytest.raises(SandboxError, match="scan limit"):
        materialize_repository_view(
            source,
            tmp_path / "bounded-view",
            scopes=("**",),
            limits=SandboxLimits(scan_entries=1),
        )


def test_cleanup_rechecks_owner_and_uses_only_full_container_id() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeExecutor(DockerExecutor):
        def _run(self, *arguments: str, timeout: float = 5):
            calls.append(arguments)
            if arguments[0] == "inspect":
                payload = [
                    {
                        "Id": CONTAINER_ID,
                        "Config": {
                            "Labels": {
                                "graphene.owner": "attempt-1",
                                "graphene.executor": "oci-v1",
                            }
                        },
                        "State": {"Running": False, "ExitCode": 0, "OOMKilled": False},
                    }
                ]
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload).encode(), b""
                )
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

    FakeExecutor().cleanup_owned(CONTAINER_ID, "attempt-1")
    assert calls == [
        ("inspect", CONTAINER_ID),
        ("inspect", CONTAINER_ID),
        ("rm", CONTAINER_ID),
    ]


def test_cleanup_refuses_mismatched_ownership() -> None:
    class FakeExecutor(DockerExecutor):
        def _run(self, *arguments: str, timeout: float = 5):
            payload = [
                {
                    "Id": CONTAINER_ID,
                    "Config": {"Labels": {"graphene.owner": "someone-else"}},
                    "State": {"Running": False},
                }
            ]
            return subprocess.CompletedProcess(
                arguments, 0, json.dumps(payload).encode(), b""
            )

    with pytest.raises(SandboxError, match="ownership"):
        FakeExecutor().cleanup_owned(CONTAINER_ID, "attempt-1")


@pytest.mark.parametrize("running", (True, False))
def test_reconcile_owned_removes_running_or_exited_exact_container(
    running: bool,
) -> None:
    calls: list[tuple[str, ...]] = []
    current_running = running
    name = "graphene-" + hashlib.sha256(b"attempt-1").hexdigest()[:24]

    class FakeExecutor(DockerExecutor):
        def _run(self, *arguments: str, timeout: float = 5):
            nonlocal current_running
            calls.append(arguments)
            if arguments[0] == "inspect":
                payload = [
                    {
                        "Id": CONTAINER_ID,
                        "Name": f"/{name}",
                        "Config": {
                            "Labels": {
                                "graphene.owner": "attempt-1",
                                "graphene.executor": "oci-v1",
                            }
                        },
                        "State": {"Running": current_running, "ExitCode": 0},
                    }
                ]
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload).encode(), b""
                )
            if arguments[0] == "kill":
                current_running = False
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

    assert FakeExecutor().reconcile_owned("attempt-1") is True
    assert calls[0] == ("inspect", name)
    assert calls[-2:] == [("inspect", CONTAINER_ID), ("rm", CONTAINER_ID)]
    assert (("kill", CONTAINER_ID) in calls) is running


def test_reconcile_owned_missing_container_is_idempotent() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeExecutor(DockerExecutor):
        def _run(self, *arguments: str, timeout: float = 5):
            calls.append(arguments)
            return subprocess.CompletedProcess(
                arguments, 1, b"", b"Error: No such container"
            )

    assert FakeExecutor().reconcile_owned("attempt-1") is False
    assert len(calls) == 1 and calls[0][0] == "inspect"


@pytest.mark.parametrize(
    ("actual_name", "owner", "executor"),
    [
        (None, "someone-else", "oci-v1"),
        (None, "attempt-1", "other"),
        ("/graphene-someone-else", "attempt-1", "oci-v1"),
    ],
)
def test_reconcile_owned_refuses_name_or_label_mismatch(
    actual_name: str | None, owner: str, executor: str
) -> None:
    calls: list[tuple[str, ...]] = []
    name = "graphene-" + hashlib.sha256(b"attempt-1").hexdigest()[:24]

    class FakeExecutor(DockerExecutor):
        def _run(self, *arguments: str, timeout: float = 5):
            calls.append(arguments)
            payload = [
                {
                    "Id": CONTAINER_ID,
                    "Name": actual_name or f"/{name}",
                    "Config": {
                        "Labels": {
                            "graphene.owner": owner,
                            "graphene.executor": executor,
                        }
                    },
                    "State": {"Running": True},
                }
            ]
            return subprocess.CompletedProcess(
                arguments, 0, json.dumps(payload).encode(), b""
            )

    with pytest.raises(SandboxError, match="ownership"):
        FakeExecutor().reconcile_owned("attempt-1")
    assert len(calls) == 1 and calls[0] == ("inspect", name)


def test_uncertain_create_cleans_only_name_resolved_owned_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_text("safe = True\n")
    calls: list[tuple[str, ...]] = []

    class FakeExecutor(DockerExecutor):
        def _docker(self) -> Path:
            return Path("/usr/bin/true")

        def preflight(self) -> str:
            return IMAGE_ID

        def _run(self, *arguments: str, timeout: float = 5):
            calls.append(arguments)
            if arguments[0] == "inspect":
                name = "graphene-" + hashlib.sha256(b"attempt-1").hexdigest()[:24]
                payload = [
                    {
                        "Id": CONTAINER_ID,
                        "Name": f"/{name}",
                        "Config": {
                            "Labels": {
                                "graphene.owner": "attempt-1",
                                "graphene.executor": "oci-v1",
                            }
                        },
                        "State": {"Running": False, "ExitCode": 0, "OOMKilled": False},
                    }
                ]
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps(payload).encode(), b""
                )
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

    monkeypatch.setattr(
        "graphene.orchestration.sandbox.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, b"not-an-id\n", b""
        ),
    )
    with pytest.raises(SandboxError, match="verified owned container removed"):
        FakeExecutor().execute(
            source=source,
            scopes=("code.py",),
            exclusions=(),
            template=TEMPLATE,
            owner_id="attempt-1",
        )

    assert calls[0][0] == "inspect" and calls[0][1].startswith("graphene-")
    assert calls[1:] == [
        ("inspect", CONTAINER_ID),
        ("inspect", CONTAINER_ID),
        ("rm", CONTAINER_ID),
    ]

    calls.clear()

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr("graphene.orchestration.sandbox.subprocess.run", timed_out)
    with pytest.raises(subprocess.TimeoutExpired):
        FakeExecutor().execute(
            source=source,
            scopes=("code.py",),
            exclusions=(),
            template=TEMPLATE,
            owner_id="attempt-1",
        )
    assert calls[0][0] == "inspect" and calls[0][1].startswith("graphene-")
    assert calls[1:] == [
        ("inspect", CONTAINER_ID),
        ("inspect", CONTAINER_ID),
        ("rm", CONTAINER_ID),
    ]


def test_unavailable_docker_fails_before_repository_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "code.py").write_text("raise AssertionError('must not execute')")
    reached_materialization = False

    def forbidden(*args, **kwargs):
        nonlocal reached_materialization
        reached_materialization = True
        raise AssertionError("materialized before preflight")

    monkeypatch.setattr(
        "graphene.orchestration.sandbox.materialize_repository_view", forbidden
    )
    executor = DockerExecutor(docker_bin=tmp_path / "missing-docker")
    with pytest.raises(DockerUnavailable, match="NOT PROVEN"):
        executor.execute(
            source=source,
            scopes=("code.py",),
            exclusions=(),
            template=TEMPLATE,
            owner_id="attempt-1",
        )
    assert not reached_materialization


def test_attached_output_is_bounded(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(f"#!{sys.executable}\nprint('x' * 1000)\n")
    fake_docker.chmod(0o755)

    class CaptureExecutor(DockerExecutor):
        def _inspect(self, container_id: str, owner_id: str):
            return {"Running": False}

    output, truncated, timed_out = CaptureExecutor(
        docker_bin=fake_docker,
        limits=SandboxLimits(output_bytes=32),
        # Budget, not a stopwatch: the subject here is the 32-byte output
        # cap, and one second is not enough to start a CPython interpreter
        # on a busy machine — the capture then returns b"" and the cap is
        # never exercised. Observed in a full matrix under load.
    )._capture(CONTAINER_ID, "attempt-1", 60)
    assert output == b"x" * 32
    assert truncated
    assert not timed_out


@pytest.mark.skipif(
    os.environ.get("GRAPHENE_RUN_DOCKER_SMOKE") != "1",
    reason=(
        "NOT PROVEN: set GRAPHENE_RUN_DOCKER_SMOKE=1 after building "
        "graphene-executor:py313-pytest to run the real container smoke"
    ),
)
def test_real_docker_executes_only_the_scoped_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "test_pass.py").write_text("def test_pass():\n    assert True\n")

    result = DockerExecutor().execute(
        source=source,
        scopes=("test_pass.py",),
        exclusions=(),
        template=TEMPLATE,
        owner_id="docker-smoke-attempt",
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.oom_killed is False
    assert result.output_truncated is False
    assert result.cleanup_complete is True
