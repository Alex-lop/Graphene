import json
import os
import shutil
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from graphene.hashing import canonical_json_sha256, candidate_tree_sha256
from graphene.core_models import GoldenContract, GraphMvpContract, RepoPath

ROOT = Path(__file__).parents[2]
CONTRACT_PATH = ROOT / "contracts/golden_path.json"


@pytest.fixture(scope="module")
def contract() -> GoldenContract:
    return GoldenContract.model_validate_json(CONTRACT_PATH.read_text())


def _fixture_hash(contract: GoldenContract) -> str:
    root = ROOT / contract.fixture.root
    return candidate_tree_sha256(
        {path: (root / path).read_bytes() for path in contract.fixture.tracked_paths}
    )


def _run_fixture(contract: GoldenContract, root: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        "NO_COLOR": "1",
        "PATH": os.environ["PATH"],
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    return subprocess.run(
        contract.fixture.fixed_test_command,
        cwd=root,
        text=True,
        capture_output=True,
        timeout=contract.fixture.test_timeout_seconds,
        env=environment,
        check=False,
    )


def _fixture_inventory(root: Path) -> set[str]:
    inventory = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AssertionError(f"fixture symlink is forbidden: {path}")
        if path.is_file():
            inventory.add(path.relative_to(root).as_posix())
    return inventory


def test_contract_freezes_the_only_golden_path(contract: GoldenContract):
    assert contract.product == "Graphene"
    assert contract.model.model_id == "graphene-compatibility-fixture"
    assert contract.model.adk_version == "2.5.0"
    assert contract.tool_names == ("read_file", "write_file", "run_fixture_tests")
    assert contract.fixture.mutable_paths == (
        "app/auth/limiter.py",
        "tests/test_security_policy.py",
    )
    assert [task.task_id for task in contract.tasks] == [
        "baseline_max_attempts",
        "adapted_window_seconds",
    ]
    assert contract.negative_retrieval_case.expected_memory_ids == ()
    assert contract.loop[-1].resulting_state == "graphene_promotion_receipt_recorded"


def test_prompts_and_retrieval_cases_are_deterministic(contract: GoldenContract):
    baseline, adapted = contract.tasks
    baseline_prompt = contract.prompt.template.format(
        task=baseline.instruction,
        memory_context=contract.prompt.no_memory_context,
    )
    memory_context = contract.prompt.approved_memory_template.format(
        memory_id=contract.memory.memory_id,
        revision=contract.memory.revision,
        rule=contract.memory.rule,
    )
    adapted_prompt = contract.prompt.template.format(
        task=adapted.instruction,
        memory_context=memory_context,
    )
    assert contract.memory.memory_id not in baseline_prompt
    assert "[mem_auth_review revision 1]" in adapted_prompt
    assert set(contract.memory.task_tags) <= set(adapted.task_tags)
    assert any(
        fnmatchcase(path, glob)
        for path in adapted.target_paths
        for glob in contract.memory.path_globs
    )

    negative = contract.negative_retrieval_case
    assert not set(contract.memory.task_tags) <= set(negative.task_tags)
    assert not any(
        fnmatchcase(path, glob)
        for path in negative.target_paths
        for glob in contract.memory.path_globs
    )


def test_fixture_contents_are_frozen_and_green(contract: GoldenContract):
    root = ROOT / contract.fixture.root
    assert _fixture_inventory(root) == set(contract.fixture.tracked_paths)
    assert contract.memory.required_test_path not in _fixture_inventory(root)
    assert _fixture_hash(contract) == contract.fixture.tree_sha256
    result = _run_fixture(contract, root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len((result.stdout + result.stderr).encode()) <= (
        contract.fixture.max_test_output_bytes
    )
    assert _fixture_inventory(root) == set(contract.fixture.tracked_paths)


def test_security_test_fails_on_base_and_passes_on_candidate(
    contract: GoldenContract, tmp_path: Path
):
    base = tmp_path / "base"
    candidate = tmp_path / "candidate"
    shutil.copytree(ROOT / contract.fixture.root, base)
    shutil.copytree(base, candidate)

    adapted = next(task for task in contract.tasks if task.task_id == "adapted_window_seconds")
    limiter = candidate / adapted.target_paths[0]
    limiter.write_text(limiter.read_text().replace(adapted.replacement_from, adapted.replacement_to))
    for root in (base, candidate):
        test_path = root / contract.memory.required_test_path
        test_path.write_text(contract.memory.expected_security_test_content)

    base_result = _run_fixture(contract, base)
    candidate_result = _run_fixture(contract, candidate)
    assert base_result.returncode != 0
    assert candidate_result.returncode == 0, candidate_result.stdout + candidate_result.stderr
    assert len((candidate_result.stdout + candidate_result.stderr).encode()) <= (
        contract.fixture.max_test_output_bytes
    )


@pytest.mark.parametrize(
    "path", [".", "../secret", "/tmp/secret", "app\\secret", "app/../secret"]
)
def test_repo_paths_reject_escape(path: str):
    with pytest.raises(ValidationError):
        TypeAdapter(RepoPath).validate_python(path)


def test_contract_json_contains_no_secret_values():
    raw = json.loads(CONTRACT_PATH.read_text())
    assert not any(key in json.dumps(raw).lower() for key in ("api_key", "bearer ", "password"))


def test_post_phase_zero_graph_contract_is_final_and_bounded():
    graph = GraphMvpContract.model_validate_json(
        (ROOT / "contracts/graph_mvp.json").read_text()
    )
    assert canonical_json_sha256(graph.model_dump(mode="json")) == (
        "b8a2875c33171097fca3f2fef93c760c15a035b89d1d9960efc3e7a05b34a9a6"
    )
    assert graph.caps.max_patch_bytes == 102_400
    assert graph.caps.max_nodes == 25
    assert graph.caps.max_edges == 40
    contract_max = GoldenContract.model_validate_json(
        CONTRACT_PATH.read_text()
    ).fixture.max_patch_bytes
    assert contract_max == graph.caps.max_patch_bytes
    assert graph.task_profiles[1].agent_profile_id == "auth-maintainer@1"
    assert {profile.framework for profile in graph.catalog} == {"driver-selected"}
    assert all(
        "gemini" not in profile.model_policy.lower()
        and "adk" not in profile.model_policy.lower()
        for profile in graph.catalog
    )
    assert "denied before runtime construction" in graph.catalog[2].model_policy
    assert "context_packet_sha256" in graph.binding_requirements["promotion"]
