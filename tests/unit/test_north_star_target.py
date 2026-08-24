"""North Star demo target: the repository a live two-worker Gemini mission edits.

Proven here, credential-free:

* the target's own suite passes in a temporary copy under the adapter's
  sanitized environment, writing no bytecode or cache into the tree;
* ``scripts/materialize_north_star.py`` yields a repository whose
  ``.graphene/project.json`` loads through
  ``graphene.cli.mission._load_project_policy`` and binds the frozen fixed
  test command, and it refuses (exit 1, nothing deleted) when the destination
  exists or the target suite fails;
* the renderer modules are absent at base: ``report --format json|markdown``
  exits 1 with a clean ``error:`` line (no traceback), the golden contract
  test in ``tests/test_report_contract.py`` skips, and the CLI already
  dispatches both formats — the mission's work is exactly the two renderer
  modules plus their tests, the only paths the policy lets it write;
* ``goal.json`` and ``GOAL.md`` agree, and ``policy.template.json`` matches
  the documented policy;
* size and hygiene bounds hold: source line count, every tracked file inside
  the planner's 4096-byte excerpt cap, stdlib-only imports, no secrets.

Not proven here: that a live Gemini mission completes on this target.
"""

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
from graphene.execution.adapter import _FIXED_TEST_COMMAND, _sanitized_environment
from graphene.hashing import canonical_json_bytes
from graphene.orchestration.models import CommandTemplate, NetworkMode, ProjectPolicy

ROOT = Path(__file__).resolve().parents[2]
NORTH_STAR = ROOT / "demo" / "north_star"
REPOSITORY = NORTH_STAR / "repository"
GOAL_JSON = NORTH_STAR / "goal.json"
GOAL_MD = NORTH_STAR / "GOAL.md"
TEMPLATE = NORTH_STAR / "policy.template.json"
SCRIPT = ROOT / "scripts" / "materialize_north_star.py"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store")
IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
# graphene.cli.mission._planning_repository_context skips any file larger than
# 4096 bytes, keeps at most 16 excerpts, and stops after 32768 bytes in total.
PLANNER_EXCERPT_BYTES = 4_096
PLANNER_EXCERPT_COUNT = 16
PLANNER_BUDGET_BYTES = 32_768
SECRET_MARKERS = ("api_key", "token=", "password")
SECRET_ALLOWED = {
    "ledger_service/redact.py",
    "tests/test_redact.py",
    "tests/test_report_contract.py",
}
SAMPLE_LEDGER = {
    "items": [{"sku": "BOLT-M8", "name": "M8 bolt"}],
    "movements": [
        {
            "movement_id": "m1",
            "sku": "BOLT-M8",
            "kind": "receipt",
            "quantity": 3,
            "recorded_at": "2024-05-01T09:00:00+00:00",
            "note": "ask ops@example.com",
        }
    ],
}


def _tracked_files() -> tuple[Path, ...]:
    files = []
    for path in sorted(REPOSITORY.rglob("*")):
        if path.is_file() and not (set(path.relative_to(REPOSITORY).parts) & IGNORED_NAMES):
            files.append(path)
    return tuple(files)


def _copy_target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    shutil.copytree(REPOSITORY, target, ignore=IGNORE)
    return target


def _run_in_target(target: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, *argv),
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
    sys.modules[name] = module  # slots dataclasses resolve their module via sys.modules
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


def test_target_suite_passes_in_sanitized_environment(tmp_path: Path) -> None:
    target = _copy_target(tmp_path)
    result = _run_in_target(target, *_FIXED_TEST_COMMAND[1:])
    summary = result.stdout.strip().splitlines()[-1]
    assert result.returncode == 0, result.stdout
    # Exactly the two golden-contract tests skip while the renderers are absent.
    assert re.fullmatch(r"\d+ passed, 2 skipped in [\d.]+s", summary), summary
    leftovers = [p for p in target.rglob("*") if p.name in IGNORED_NAMES or p.suffix == ".pyc"]
    assert leftovers == [], "the sanitized run must not write bytecode or caches"


def test_materializer_produces_policy_that_mission_start_loads(tmp_path: Path) -> None:
    module = _load_materializer()
    dest = tmp_path / "north-star"
    out, err = io.StringIO(), io.StringIO()
    assert module.main([str(dest)], out, err) == 0, err.getvalue()
    assert err.getvalue() == ""
    assert stat.S_IMODE(dest.stat().st_mode) == 0o700

    root, head, policy = _load_project_policy(dest)
    assert root == dest.resolve()
    assert head == policy.base_sha
    expected_template = CommandTemplate(
        template_id="fixture-tests", argv=_FIXED_TEST_COMMAND, timeout_seconds=60
    )
    assert policy.command_templates == (expected_template,)
    assert policy.allowed_read_globs == ("README.md", "ledger_service/**", "tests/**")
    assert policy.allowed_write_globs == (
        "ledger_service/report_json.py",
        "ledger_service/report_markdown.py",
        "tests/test_report_json.py",
        "tests/test_report_markdown.py",
    )
    assert ".graphene/**" in policy.exclusions and ".git/**" in policy.exclusions
    assert policy.network.mode is NetworkMode.DENY and policy.network.allowed_hosts == ()
    assert (policy.max_concurrency, policy.retry_limit, policy.revision) == (2, 1, 1)
    assert policy.risk_gates == ("final-result", "network", "scope-expansion")

    policy_path = dest / ".graphene" / "project.json"
    assert stat.S_IMODE(policy_path.stat().st_mode) == 0o600
    assert policy_path.read_bytes() == canonical_json_bytes(policy.model_dump(mode="json")) + b"\n"
    assert ProjectPolicy.model_validate_json(policy_path.read_text(encoding="utf-8")) == policy

    assert _git(dest, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert _git(dest, "log", "--format=%an <%ae> %s").strip() == (
        "Graphene North Star <north-star@graphene.invalid> North Star demo target base"
    )
    assert _git(dest, "status", "--porcelain").splitlines() == ["?? .graphene/"]
    assert _git(dest, "remote").strip() == ""

    goal = json.loads(GOAL_JSON.read_text(encoding="utf-8"))
    printed = out.getvalue()
    assert f"uv run --frozen graphene doctor --repo {dest.resolve()}" in printed
    start = next(line for line in printed.splitlines() if "graphene mission start" in line)
    assert start.strip().startswith("uv run --frozen graphene mission start --repo ")
    assert start.endswith("--driver gemini-adk --max-workers 2")
    assert start.count("--success-criterion") == len(goal["success_criteria"])
    assert goal["goal"] in start
    for criterion in goal["success_criteria"]:
        assert criterion in start
    assert "graphene mission approve-plan MISSION_ID --revision 1 --confirm-human" in printed


def test_materializer_refuses_existing_destination(tmp_path: Path) -> None:
    module = _load_materializer()
    dest = tmp_path / "occupied"
    dest.mkdir()
    (dest / "keep.txt").write_text("untouched\n", encoding="utf-8")
    err = io.StringIO()
    assert module.main([str(dest)], io.StringIO(), err) == 1
    assert "already exists" in err.getvalue()
    assert sorted(p.name for p in dest.iterdir()) == ["keep.txt"]


def test_materializer_refuses_when_target_suite_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_materializer()
    broken = _copy_target(tmp_path)
    (broken / "tests" / "test_models.py").open("a", encoding="utf-8").write(
        "\n\ndef test_injected_failure() -> None:\n    assert False\n"
    )
    monkeypatch.setattr(module, "SOURCE", broken)
    dest = tmp_path / "north-star"
    err = io.StringIO()
    assert module.main([str(dest)], io.StringIO(), err) == 1
    assert "target test suite failed" in err.getvalue()
    assert (dest / ".git").is_dir(), "nothing is deleted on failure"
    assert (dest / ".graphene" / "project.json").is_file()


@pytest.mark.parametrize("fmt", ["json", "markdown"])
def test_report_renderers_are_absent_and_cli_fails_cleanly(tmp_path: Path, fmt: str) -> None:
    target = _copy_target(tmp_path)
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps(SAMPLE_LEDGER), encoding="utf-8")
    result = _run_in_target(
        target, "-m", "ledger_service", "--ledger", str(ledger), "report", "--format", fmt
    )
    assert result.returncode == 1
    assert f"error: no {fmt} report renderer (ledger_service.report_{fmt} is missing)" in result.stdout
    assert "Traceback" not in result.stdout
    balances = _run_in_target(target, "-m", "ledger_service", "--ledger", str(ledger), "balances")
    assert (balances.returncode, balances.stdout) == (0, "BOLT-M8\t3\teach\n")


def test_no_report_tests_or_renderers_exist_yet() -> None:
    names = [p.relative_to(REPOSITORY).as_posix() for p in _tracked_files()]
    report_tests = [n for n in names if n.startswith("tests/") and "report" in n]
    assert report_tests == ["tests/test_report_base.py", "tests/test_report_contract.py"]
    assert not [n for n in names if "json" in n or "markdown" in n]
    assert "ledger_service/report_base.py" in names
    for path in _tracked_files():
        if path.suffix == ".py":
            assert "def render_json" not in path.read_text(encoding="utf-8")
            assert "def render_markdown" not in path.read_text(encoding="utf-8")


def test_goal_json_and_goal_md_agree() -> None:
    goal_text = GOAL_JSON.read_text(encoding="utf-8")
    goal = json.loads(goal_text)
    markdown = GOAL_MD.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", markdown, flags=re.DOTALL)
    assert len(blocks) == 1
    assert blocks[0].strip() == goal_text.strip()
    assert json.loads(blocks[0]) == goal
    prose = markdown.split("```json", 1)[0]
    assert f"> {goal['goal']}\n" in prose
    for index, criterion in enumerate(goal["success_criteria"], 1):
        assert f"{index}. {criterion}\n" in prose
    assert "an expectation, not a fixture" in prose
    assert goal["schema_version"] == 1
    assert 3 <= len(goal["success_criteria"]) <= 4
    assert len(set(goal["success_criteria"])) == len(goal["success_criteria"])
    assert all(1 <= len(text) <= 1024 for text in (goal["goal"], *goal["success_criteria"]))
    module = _load_materializer()
    assert module.load_goal() == (goal["goal"], tuple(goal["success_criteria"]))


def test_policy_template_matches_documented_policy() -> None:
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    placeholders = {key for key, value in template.items() if value == "<materialized>"}
    assert placeholders == {"policy_id", "repo_id", "base_ref", "base_sha", "revision"}
    assert template["schema_version"] == 1
    assert template["allowed_read_globs"] == ["README.md", "ledger_service/**", "tests/**"]
    assert template["allowed_write_globs"] == [
        "ledger_service/report_json.py",
        "ledger_service/report_markdown.py",
        "tests/test_report_json.py",
        "tests/test_report_markdown.py",
    ]
    assert template["exclusions"] == [
        "**/*.key", "**/*.pem", ".env", ".env.*", ".git/**", ".graphene/**"
    ]
    assert template["command_templates"] == [
        {
            "template_id": "fixture-tests",
            "argv": list(_FIXED_TEST_COMMAND),
            "timeout_seconds": 60,
        }
    ]
    assert template["network"] == {"mode": "deny", "allowed_hosts": []}
    assert template["agent_roles"] == ["assembler", "planner", "verifier", "worker"]
    assert (template["max_concurrency"], template["retry_limit"]) == (2, 1)
    assert template["resource_budget"] == {
        "max_worker_seconds": 900,
        "max_attempts": 16,
        "max_artifact_bytes": 10_485_760,
        "soft_managed_rss_bytes": 536_870_912,
        "hard_managed_rss_bytes": 805_306_368,
    }
    assert template["retention"] == {"retain_days": 7, "retain_failed_attempts": True}
    assert template["risk_gates"] == ["final-result", "network", "scope-expansion"]
    assert _load_materializer().load_template() == template


def test_target_size_and_hygiene_bounds() -> None:
    files = _tracked_files()
    names = [p.relative_to(REPOSITORY).as_posix() for p in files]
    source_lines = sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in (REPOSITORY / "ledger_service").glob("*.py")
    )
    test_lines = sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in (REPOSITORY / "tests").glob("*.py")
    )
    assert 350 <= source_lines <= 700, source_lines
    assert 120 <= test_lines <= 400, test_lines
    assert not (REPOSITORY / ".graphene").exists()
    assert not (REPOSITORY / ".git").exists()
    assert not (REPOSITORY / "pyproject.toml").exists()
    assert "README.md" in names and "ledger_service/__init__.py" in names
    assert len(files) <= PLANNER_EXCERPT_COUNT
    oversized = {n: p.stat().st_size for n, p in zip(names, files) if p.stat().st_size > PLANNER_EXCERPT_BYTES}
    assert oversized == {}, f"planner excerpts skip files over 4096 bytes: {oversized}"
    assert sum(p.stat().st_size for p in files) <= PLANNER_BUDGET_BYTES
    for name, path in zip(names, files):
        text = path.read_text(encoding="utf-8")
        if name not in SECRET_ALLOWED:
            hits = [marker for marker in SECRET_MARKERS if marker in text.lower()]
            assert hits == [], f"{name} mentions {hits}"
        if path.suffix == ".py":
            pattern = r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))"
            for match in re.finditer(pattern, text, re.M):
                imported = match.group(1) or match.group(2)
                if imported.startswith("."):
                    continue
                module = imported.split(".")[0]
                assert module in sys.stdlib_module_names | {"ledger_service", "pytest"}, (
                    f"{name} imports non-stdlib module {module}"
                )
    assert os.access(SCRIPT, os.R_OK)
