from __future__ import annotations

from pathlib import Path

import pytest

from graphene.orchestration.models import CommandTemplate
from graphene.orchestration.sandbox import (
    SandboxError,
    SandboxLimits,
    build_docker_create_argv,
    validate_command_template,
)


@pytest.mark.parametrize(
    "argv",
    (
        ("bash", "-c", "cat /etc/passwd"),
        ("python", "-c", "import os; print(os.environ)"),
        ("python", "-m", "pip", "install", "evil"),
        ("git", "-c", "core.hooksPath=/tmp/hooks", "status"),
        ("/tmp/python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
        ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir=/"),
    ),
)
def test_shell_interpreter_installer_path_and_extra_argv_are_rejected(
    argv: tuple[str, ...],
) -> None:
    try:
        template = CommandTemplate(
            template_id="fixture-tests",
            argv=argv,
            timeout_seconds=15,
        )
    except ValueError:
        return
    with pytest.raises(SandboxError, match="frozen"):
        validate_command_template(template)


def test_host_mount_and_mutable_root_cannot_be_requested(tmp_path: Path) -> None:
    template = CommandTemplate(
        template_id="fixture-tests",
        argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
        timeout_seconds=15,
    )
    argv = build_docker_create_argv(
        docker_bin=Path("/usr/bin/docker"),
        image_id="sha256:" + "a" * 64,
        workspace=tmp_path.resolve(),
        owner_id="attempt-1",
        container_name="graphene-attempt-1",
        command=validate_command_template(template),
        cwd=None,
        limits=SandboxLimits(),
    )
    mounts = [argv[index + 1] for index, item in enumerate(argv) if item == "--mount"]
    assert mounts == [
        f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly"
    ]
    assert "--read-only" in argv
    assert ("--network", "none") == argv[
        argv.index("--network") : argv.index("--network") + 2
    ]


def test_mount_path_delimiters_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="mount"):
        build_docker_create_argv(
            docker_bin=Path("/usr/bin/docker"),
            image_id="sha256:" + "a" * 64,
            workspace=tmp_path / "escape,readonly=false",
            owner_id="attempt-1",
            container_name="graphene-attempt-1",
            command=(
                "/usr/local/bin/python",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ),
            cwd=None,
            limits=SandboxLimits(),
        )
