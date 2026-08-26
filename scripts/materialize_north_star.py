#!/usr/bin/env python3
"""Materialize the North Star demo target for a live Graphene mission.

Usage::

    uv run --frozen python scripts/materialize_north_star.py DEST

Steps, in order; the script stops at the first failure with exit status 1
and never deletes anything it created:

1. copy ``demo/north_star/repository`` to ``DEST`` (which must not exist;
   it is created with mode 0700);
2. ``git init -b main`` there, set a repository-local identity, and commit
   "North Star demo target base";
3. write ``DEST/.graphene/project.json`` (mode 0600, canonical JSON) by
   taking ``graphene.cli.mission._default_policy`` for that repository and
   overlaying the scope, command, budget, and gate fields from
   ``demo/north_star/policy.template.json``;
4. prove the policy loads through ``graphene.cli.mission._load_project_policy``
   exactly as ``graphene mission start`` would load it, and that its only
   command template is the frozen fixed test command;
5. run the target's own test suite once, inside ``DEST``, with the adapter's
   sanitized environment;
6. print the exact next commands.

The goal and success criteria come from ``demo/north_star/goal.json``.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from graphene.cli.mission import (
    MissionCliError,
    _default_policy,
    _git_root,
    _load_project_policy,
)
from graphene.execution.adapter import _FIXED_TEST_COMMAND, _sanitized_environment
from graphene.hashing import canonical_json_bytes
from graphene.orchestration.mission_models import ProjectPolicy

ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = ROOT / "demo" / "north_star"
SOURCE = NORTH_STAR / "repository"
GOAL_PATH = NORTH_STAR / "goal.json"
TEMPLATE_PATH = NORTH_STAR / "policy.template.json"
PLACEHOLDER = "<materialized>"
MATERIALIZED_FIELDS = frozenset(
    {"policy_id", "repo_id", "base_ref", "base_sha", "revision"}
)
GIT_USER_NAME = "Graphene North Star"
GIT_USER_EMAIL = "north-star@graphene.invalid"
BASE_COMMIT_MESSAGE = "North Star demo target base"
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".DS_Store"
)
MAX_TEXT_LENGTH = 1_024
MAX_CRITERIA = 32


class MaterializeError(RuntimeError):
    """A step failed; the destination is left exactly as it was."""


@dataclass(frozen=True, slots=True)
class MaterializedTarget:
    repository: Path
    base_sha: str
    policy_path: Path
    policy: ProjectPolicy
    goal: str
    success_criteria: tuple[str, ...]
    test_summary: str

    @property
    def commands(self) -> tuple[str, str, str]:
        repo = str(self.repository)
        start = ["uv", "run", "--frozen", "graphene", "mission", "start"]
        start += ["--repo", repo, "--goal", self.goal]
        for criterion in self.success_criteria:
            start += ["--success-criterion", criterion]
        start += ["--driver", "gemini-adk", "--max-workers", "2"]
        return (
            shlex.join(["uv", "run", "--frozen", "graphene", "doctor", "--repo", repo]),
            shlex.join(start),
            "uv run --frozen graphene mission approve-plan MISSION_ID "
            "--revision 1 --confirm-human",
        )


def _bounded_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaterializeError(f"{label} must be a non-empty string")
    if len(value) > MAX_TEXT_LENGTH or value != value.strip():
        raise MaterializeError(f"{label} must be trimmed and at most 1024 characters")
    return value


def load_goal(path: Path = GOAL_PATH) -> tuple[str, tuple[str, ...]]:
    """Read the mission goal and its success criteria from goal.json."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MaterializeError(f"cannot read {path}: {error}") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise MaterializeError(f"{path} must be a schema_version 1 object")
    goal = _bounded_text(document.get("goal"), "goal")
    raw = document.get("success_criteria")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CRITERIA:
        raise MaterializeError("success_criteria must list 1 to 32 sentences")
    criteria = tuple(_bounded_text(item, "success criterion") for item in raw)
    if len(set(criteria)) != len(criteria):
        raise MaterializeError("success criteria must be unique")
    return goal, criteria


def load_template(path: Path = TEMPLATE_PATH) -> dict[str, object]:
    """Read the policy template; exactly the identity fields are placeholders."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MaterializeError(f"cannot read {path}: {error}") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise MaterializeError(f"{path} must be a schema_version 1 object")
    placeholders = {key for key, value in document.items() if value == PLACEHOLDER}
    if placeholders != MATERIALIZED_FIELDS:
        raise MaterializeError(
            "policy template placeholders must be exactly "
            + ", ".join(sorted(MATERIALIZED_FIELDS))
        )
    return document


def _git_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": os.environ.get("HOME", ""),
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repository: Path, *args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise MaterializeError("git is unavailable")
    try:
        result = subprocess.run(
            (executable, *args),
            cwd=repository,
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MaterializeError(f"git {args[0]} could not run: {error}") from error
    if result.returncode:
        raise MaterializeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def copy_target(dest: Path) -> None:
    if dest.exists() or dest.is_symlink():
        raise MaterializeError(f"{dest} already exists; refusing to touch it")
    if not dest.parent.is_dir():
        raise MaterializeError(f"{dest.parent} is not a directory")
    if not SOURCE.is_dir():
        raise MaterializeError(f"source tree {SOURCE} is missing")
    if (SOURCE / ".graphene").exists() or (SOURCE / ".git").exists():
        raise MaterializeError("source tree must not contain .graphene or .git")
    try:
        dest.mkdir(mode=0o700)
        shutil.copytree(SOURCE, dest, ignore=COPY_IGNORE, dirs_exist_ok=True)
        os.chmod(dest, 0o700)
    except OSError as error:
        raise MaterializeError(f"copy to {dest} failed: {error}") from error


def commit_base(dest: Path) -> None:
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "config", "user.name", GIT_USER_NAME)
    _git(dest, "config", "user.email", GIT_USER_EMAIL)
    _git(dest, "add", "--all", "--")
    _git(dest, "commit", "-q", "-m", BASE_COMMIT_MESSAGE)


def build_policy(root: Path, base_sha: str) -> ProjectPolicy:
    """Default policy for ``root`` with the template's non-identity fields."""
    default = _default_policy(root, base_sha)
    data = default.model_dump(mode="json")
    for key, value in load_template().items():
        if value != PLACEHOLDER:
            data[key] = value
    try:
        policy = ProjectPolicy.model_validate(data)
    except ValueError as error:
        raise MaterializeError(f"policy template is invalid: {error}") from error
    for key in MATERIALIZED_FIELDS:
        if getattr(policy, key) != getattr(default, key):
            raise MaterializeError(f"policy {key} drifted from the default")
    return policy


def write_policy(dest: Path) -> tuple[Path, Path, ProjectPolicy, str]:
    try:
        root, base_sha = _git_root(dest)
    except MissionCliError as error:
        raise MaterializeError(f"destination is not a usable repository: {error}") from error
    policy = build_policy(root, base_sha)
    directory = root / ".graphene"
    path = directory / "project.json"
    payload = canonical_json_bytes(policy.model_dump(mode="json")) + b"\n"
    try:
        directory.mkdir(mode=0o755)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        reloaded = ProjectPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MaterializeError(f"project policy could not be written: {error}") from error
    if reloaded != policy or path.read_bytes() != payload:
        raise MaterializeError("project policy did not round-trip")
    return root, path, policy, base_sha


def check_policy_loads(root: Path, policy: ProjectPolicy, base_sha: str) -> None:
    """Load the policy the way ``graphene mission start`` does."""
    try:
        loaded_root, head, loaded = _load_project_policy(root)
    except MissionCliError as error:
        raise MaterializeError(f"graphene would reject the policy: {error}") from error
    if loaded_root != root or head != base_sha or loaded != policy:
        raise MaterializeError("loaded policy does not match the written policy")
    templates = loaded.command_templates
    if len(templates) != 1 or templates[0].argv != _FIXED_TEST_COMMAND:
        raise MaterializeError("fixture-tests must be the frozen fixed test command")


def run_target_tests(root: Path) -> str:
    """Run the frozen test command once in the sanitized environment.

    argv[0] is the literal "python" the executor substitutes for the running
    interpreter (``adapter._sandboxed_test_command`` does the same). Leaving it
    to PATH would not do that: ``.venv/bin/python`` is a symlink to the base
    interpreter, so resolving it escapes the locked environment and runs the
    target suite under whatever pytest that base happens to have -- green on a
    developer box, "No module named pytest" on a clean runner.
    """
    try:
        result = subprocess.run(
            (sys.executable, *_FIXED_TEST_COMMAND[1:]),
            cwd=root,
            env=_sanitized_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MaterializeError(f"target test suite could not run: {error}") from error
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    summary = lines[-1] if lines else "(no output)"
    if result.returncode or " passed" not in summary:
        raise MaterializeError(
            f"target test suite failed (exit {result.returncode}):\n{result.stdout}"
        )
    return summary


def materialize(dest: Path, stdout: IO[str] | None = None) -> MaterializedTarget:
    out = stdout if stdout is not None else sys.stdout
    goal, criteria = load_goal()
    load_template()
    copy_target(dest)
    commit_base(dest)
    root, policy_path, policy, base_sha = write_policy(dest)
    check_policy_loads(root, policy, base_sha)
    summary = run_target_tests(root)
    target = MaterializedTarget(
        repository=root,
        base_sha=base_sha,
        policy_path=policy_path,
        policy=policy,
        goal=goal,
        success_criteria=criteria,
        test_summary=summary,
    )
    print(f"North Star target materialized at {root}", file=out)
    print(f"  base commit: {base_sha}", file=out)
    print(f"  policy: {policy_path} ({policy.policy_id})", file=out)
    print(f"  target tests: {summary}", file=out)
    print("Next commands (run from the Graphene repository):", file=out)
    for command in target.commands:
        print(f"  {command}", file=out)
    return target


def main(
    argv: list[str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="materialize_north_star",
        description=__doc__.split("\n\n", 1)[0],
        allow_abbrev=False,
    )
    parser.add_argument("dest", type=Path, help="new directory for the target repo")
    args = parser.parse_args(argv)
    try:
        materialize(args.dest, stdout)
    except MaterializeError as error:
        print(f"materialize: {error}", file=stderr if stderr is not None else sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
