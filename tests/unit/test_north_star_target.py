"""Checks for the materialized Orders API Pydantic migration target."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from graphene.cli.mission import _load_project_policy
from graphene.execution.adapter import (
    NORTH_STAR_CHECK_COMMAND,
    NORTH_STAR_FINAL_CHECK_COMMAND,
    _FIXED_TEST_COMMAND,
    _sanitized_environment,
)
from graphene.hashing import canonical_json_bytes
from graphene.orchestration.mission_models import (
    CommandTemplate,
    NetworkMode,
    ProjectPolicy,
)

ROOT = Path(__file__).resolve().parents[2]
NORTH_STAR = ROOT / "demo" / "north_star"
REPOSITORY = NORTH_STAR / "repository"
GOAL_JSON = NORTH_STAR / "goal.json"
GOAL_MD = NORTH_STAR / "GOAL.md"
TEMPLATE = NORTH_STAR / "policy.template.json"
SCRIPT = ROOT / "scripts" / "materialize_north_star.py"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store")
IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
EXPECTED_WRITES = (
    "orders_api/api.py",
    "orders_api/request_models.py",
    "orders_api/response_models.py",
    "requirements.in",
    "requirements.lock",
)
PLANNER_EXCERPT_BYTES = 4_096
PLANNER_EXCERPT_COUNT = 16
PLANNER_BUDGET_BYTES = 32_768


def _tracked_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(REPOSITORY.rglob("*"))
        if path.is_file()
        and not set(path.relative_to(REPOSITORY).parts).intersection(IGNORED_NAMES)
    )


def _copy_target(tmp_path: Path, name: str = "target") -> Path:
    target = tmp_path / name
    shutil.copytree(REPOSITORY, target, ignore=IGNORE)
    return target


def _run_in_target(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, *_FIXED_TEST_COMMAND[1:]),
        cwd=target,
        env=_sanitized_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
        check=False,
    )


def _load_materializer() -> ModuleType:
    name = "graphene_test_materialize_north_star"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=True,
    ).stdout


def _replace(path: Path, *changes: tuple[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in changes:
        assert old in text
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def _migrate_request_side(target: Path) -> None:
    _replace(
        target / "orders_api" / "request_models.py",
        (
            "from pydantic.v1 import BaseModel, Field, validator",
            "from pydantic import BaseModel, ConfigDict, Field, field_validator",
        ),
        ("regex=", "pattern="),
        (
            '@validator("sku", pre=True)\n    def normalize_sku',
            '@field_validator("sku", mode="before")\n'
            "    @classmethod\n"
            "    def normalize_sku",
        ),
        (
            "items: list[OrderItem] = Field(min_items=1)",
            "items: list[OrderItem] = Field(min_length=1)",
        ),
        (
            '    class Config:\n        extra = "forbid"',
            '    model_config = ConfigDict(extra="forbid")',
        ),
    )
    _replace(
        target / "orders_api" / "api.py",
        ("CreateOrder.parse_obj(payload)", "CreateOrder.model_validate(payload)"),
    )


def _migrate_response_side(target: Path) -> None:
    _replace(
        target / "orders_api" / "response_models.py",
        (
            "from pydantic.v1 import BaseModel",
            "from pydantic import BaseModel, ConfigDict",
        ),
        (
            "    class Config:\n        allow_mutation = False",
            "    model_config = ConfigDict(frozen=True)",
        ),
        ("response.dict()", 'response.model_dump(mode="json")'),
    )


def _assert_suite_passes(target: Path) -> None:
    result = _run_in_target(target)
    assert result.returncode == 0, result.stdout
    assert re.fullmatch(r"5 passed in [\d.]+s", result.stdout.strip().splitlines()[-1])
    checked = subprocess.run(
        (sys.executable, *NORTH_STAR_CHECK_COMMAND[1:]),
        cwd=target,
        env=_sanitized_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout
    assert checked.stdout == "orders migration verified\n"


def _run_final_check(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, *NORTH_STAR_FINAL_CHECK_COMMAND[1:]),
        cwd=target,
        env=_sanitized_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )


def test_target_suite_passes_without_writing_cache(tmp_path: Path) -> None:
    target = _copy_target(tmp_path)
    _assert_suite_passes(target)
    leftovers = [
        path
        for path in target.rglob("*")
        if path.name in IGNORED_NAMES or path.suffix == ".pyc"
    ]
    assert leftovers == []


def test_untouched_baseline_fails_the_final_gate(tmp_path: Path) -> None:
    checked = _run_final_check(_copy_target(tmp_path))
    assert checked.returncode != 0


@pytest.mark.parametrize("migration", [_migrate_request_side, _migrate_response_side])
def test_two_disjoint_source_roots_each_pass_the_full_suite(
    tmp_path: Path, migration
) -> None:  # type: ignore[no-untyped-def]
    target = _copy_target(tmp_path)
    migration(target)
    _assert_suite_passes(target)


def test_completed_migration_activates_the_no_legacy_contract(tmp_path: Path) -> None:
    target = _copy_target(tmp_path)
    _migrate_request_side(target)
    _migrate_response_side(target)
    (target / "requirements.in").write_text("pydantic==2.13.4\n", encoding="utf-8")
    (target / "requirements.lock").write_text(
        "# Native Pydantic v2 runtime resolved from requirements.in.\n"
        "pydantic==2.13.4\n",
        encoding="utf-8",
    )
    _assert_suite_passes(target)
    checked = _run_final_check(target)
    assert checked.returncode == 0, checked.stdout
    assert checked.stdout == "orders migration verified\n"


def test_target_tests_use_the_locked_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_materializer()
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = tuple(argv)
        return subprocess.CompletedProcess(
            list(argv), 0, "orders migration verified\n", None
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.run_target_tests(tmp_path)
    assert captured["argv"] == (sys.executable, *NORTH_STAR_CHECK_COMMAND[1:])


def test_materializer_produces_loadable_exact_policy(tmp_path: Path) -> None:
    module = _load_materializer()
    dest = tmp_path / "orders-api"
    out, err = io.StringIO(), io.StringIO()
    assert module.main([str(dest)], out, err) == 0, err.getvalue()
    assert err.getvalue() == ""
    assert stat.S_IMODE(dest.stat().st_mode) == 0o700

    root, head, policy = _load_project_policy(dest)
    assert root == dest.resolve() and head == policy.base_sha
    assert policy.command_templates == (
        CommandTemplate(
            template_id="orders-migration-check",
            argv=NORTH_STAR_FINAL_CHECK_COMMAND,
            timeout_seconds=60,
        ),
        CommandTemplate(
            template_id="orders-migration-task-check",
            argv=NORTH_STAR_CHECK_COMMAND,
            timeout_seconds=60,
        ),
    )
    assert policy.allowed_read_globs == (
        "README.md",
        "orders_api/**",
        "requirements.in",
        "requirements.lock",
        "tests/**",
    )
    assert policy.allowed_write_globs == EXPECTED_WRITES
    assert (
        policy.network.mode is NetworkMode.DENY and policy.network.allowed_hosts == ()
    )
    assert (policy.max_concurrency, policy.retry_limit, policy.revision) == (2, 1, 1)
    assert policy.schema_version == 2
    assert policy.authorization_mode == "policy_pre_authorized"
    assert policy.finalization_mode == "auto_finalize_isolated"
    assert policy.risk_gates == ("network", "scope-expansion")

    policy_path = dest / ".graphene" / "project.json"
    assert stat.S_IMODE(policy_path.stat().st_mode) == 0o600
    assert (
        policy_path.read_bytes()
        == canonical_json_bytes(policy.model_dump(mode="json")) + b"\n"
    )
    assert (
        ProjectPolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
        == policy
    )
    assert _git(dest, "log", "--format=%an <%ae> %s").strip() == (
        "Graphene Orders Demo <orders-demo@graphene.invalid> "
        "Orders API migration target base"
    )
    assert _git(dest, "status", "--porcelain").splitlines() == ["?? .graphene/"]
    assert "Orders API target materialized" in out.getvalue()
    assert "MCP start_goal" in out.getvalue()
    assert '"authorization_mode": "policy_pre_authorized"' in out.getvalue()
    assert "approve-plan" not in out.getvalue()


def test_materialized_base_commit_is_reproducible(tmp_path: Path) -> None:
    module = _load_materializer()
    first = _copy_target(tmp_path, "first")
    second = _copy_target(tmp_path, "second")
    module.commit_base(first)
    module.commit_base(second)

    assert _git(first, "rev-parse", "HEAD") == _git(second, "rev-parse", "HEAD")


def test_materializer_refuses_existing_or_broken_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_materializer()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("untouched\n", encoding="utf-8")
    err = io.StringIO()
    assert module.main([str(occupied)], io.StringIO(), err) == 1
    assert "already exists" in err.getvalue()
    assert sorted(path.name for path in occupied.iterdir()) == ["keep.txt"]

    broken = _copy_target(tmp_path, "broken-source")
    (broken / "requirements.in").write_text("pydantic>=1\n", encoding="utf-8")
    monkeypatch.setattr(module, "SOURCE", broken)
    dest = tmp_path / "broken-dest"
    err = io.StringIO()
    assert module.main([str(dest)], io.StringIO(), err) == 1
    assert "target test suite failed" in err.getvalue()
    assert (dest / ".git").is_dir() and (dest / ".graphene/project.json").is_file()


def test_goal_policy_and_plan_shape_agree() -> None:
    goal_text = GOAL_JSON.read_text(encoding="utf-8")
    goal = json.loads(goal_text)
    markdown = GOAL_MD.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", markdown, flags=re.DOTALL)
    assert blocks == [goal_text.strip()]
    assert _load_materializer().load_goal() == (
        goal["goal"],
        tuple(goal["success_criteria"]),
    )
    assert "Work task A (parallel)" in markdown
    assert "Work task B (parallel)" in markdown
    assert "Integration task C depends on A and B" in markdown
    assert "an expectation, not a fixture" in markdown

    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert template["allowed_write_globs"] == list(EXPECTED_WRITES)
    assert template["command_templates"] == [
        {
            "template_id": "orders-migration-check",
            "argv": list(NORTH_STAR_FINAL_CHECK_COMMAND),
            "timeout_seconds": 60,
        },
        {
            "template_id": "orders-migration-task-check",
            "argv": list(NORTH_STAR_CHECK_COMMAND),
            "timeout_seconds": 60,
        }
    ]
    assert template["network"] == {"mode": "deny", "allowed_hosts": []}
    assert (template["max_concurrency"], template["retry_limit"]) == (2, 1)
    assert _load_materializer().load_template() == template


def test_target_is_small_visible_and_has_no_embedded_secrets() -> None:
    files = _tracked_files()
    names = [path.relative_to(REPOSITORY).as_posix() for path in files]
    assert names == [
        "README.md",
        "orders_api/__init__.py",
        "orders_api/api.py",
        "orders_api/request_models.py",
        "orders_api/response_models.py",
        "orders_api/verify_migration.py",
        "requirements.in",
        "requirements.lock",
        "tests/__init__.py",
        "tests/test_api.py",
        "tests/test_migration_contract.py",
        "tests/test_models.py",
    ]
    assert not (REPOSITORY / ".graphene").exists()
    assert not (REPOSITORY / ".git").exists()
    assert len(files) <= PLANNER_EXCERPT_COUNT
    assert all(path.stat().st_size <= PLANNER_EXCERPT_BYTES for path in files)
    assert sum(path.stat().st_size for path in files) <= PLANNER_BUDGET_BYTES
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(marker in text for marker in ("api_key", "token=", "password"))
    assert os.access(SCRIPT, os.R_OK)
