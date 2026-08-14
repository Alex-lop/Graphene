from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
THREAT_MODEL = ROOT / "docs/EXECUTOR_THREAT_MODEL.md"


def test_ci_keeps_supported_and_fail_closed_platform_gates_separate() -> None:
    workflow = WORKFLOW.read_text()
    threat_model = THREAT_MODEL.read_text()

    assert (ROOT / ".python-version").read_text().strip() == "3.13"
    assert "uv==0.11.29" in workflow
    assert workflow.count("uv lock --check") == 2
    assert workflow.count("uv sync --frozen") == 2
    assert "runs-on: macos-15" in workflow
    assert "test -x /usr/bin/sandbox-exec" in workflow
    assert "tests/unit tests/integration tests/process tests/adversarial" in workflow
    assert "--ignore=tests/process/test_mcp_stdio.py" in workflow
    assert "pytest -q tests/process/test_mcp_stdio.py" in workflow
    assert "graphene --help" in workflow
    assert "graphene --json watch \"$run_id\" --snapshot" in workflow

    assert "runs-on: ubuntu-24.04" in workflow
    assert "test_fixed_tests_cannot_read_ambient_checkout_files" in workflow
    assert "test_fixed_tests_cannot_read_or_write_host_files_or_use_network" in workflow
    assert "node --test frontend/test/*.test.mjs" in workflow
    assert "node --test tests/frontend/*.mjs" in workflow
    assert "node --check frontend/src/app.mjs" in workflow
    assert "node --check backend/graphene/viewer/static/reducer.mjs" in workflow
    assert (ROOT / ".nvmrc").read_text().strip() == "22"

    assert "Linux job is a negative portability gate" in threat_model
    assert "v2 fixed-test workflow remains unsupported and fails" in threat_model
    assert "No CI job uses cloud credentials" in threat_model
    assert "secrets." not in workflow
    assert "id-token: write" not in workflow
    assert "gcloud" not in workflow
    assert " deploy" not in workflow.lower()
