from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
THREAT_MODEL = ROOT / "docs/EXECUTOR_THREAT_MODEL.md"


def test_ci_keeps_supported_and_fail_closed_platform_gates_separate() -> None:
    workflow = WORKFLOW.read_text()
    threat_model = THREAT_MODEL.read_text()

    assert (ROOT / ".python-version").read_text().strip() == "3.13"
    assert "uv==0.11.29" in workflow
    assert workflow.count("uv lock --check") == 3
    assert workflow.count("uv sync --frozen") == 3
    assert "runs-on: macos-15" in workflow
    assert "test -x /usr/bin/sandbox-exec" in workflow
    assert "uv run --frozen ruff check ." in workflow
    assert "tests/unit tests/integration tests/process tests/adversarial" in workflow
    assert "--ignore=tests/process/test_mcp_stdio.py" in workflow
    assert "pytest -q tests/process/test_mcp_stdio.py" in workflow
    assert "graphene --help" in workflow
    assert "graphene --json watch \"$run_id\" --snapshot" in workflow

    # "Generated files leave a clean diff" must actually be able to detect a
    # changed file. `git diff --check` reports whitespace errors and exits 0
    # when a tracked file's content changed, so the step name was a promise the
    # command could not keep.
    assert "git diff --exit-code" in workflow

    assert "runs-on: ubuntu-24.04" in workflow
    assert "tests/process/test_verified_replay.py" in workflow
    assert "graphene demo --driver verified-replay" in workflow
    assert "graphene mission replay taskmaster" in workflow
    assert "test_fixed_tests_cannot_read_ambient_checkout_files" in workflow
    assert "test_fixed_tests_cannot_read_or_write_host_files_or_use_network" in workflow
    assert "pytest -q tests/unit/orchestration/test_process_control.py" in workflow
    assert "firebase emulators:exec --only firestore" in workflow
    assert "GRAPHENE_RUN_FIRESTORE_EMULATOR: \"1\"" in workflow
    assert "tests/integration/test_firestore_emulator.py" in workflow
    assert "google-github-actions/auth" not in workflow
    assert "node --test frontend/test/*.test.mjs" in workflow
    assert "node --test tests/frontend/*.mjs" in workflow
    assert "node --check frontend/src/app.mjs" in workflow
    assert "node --check backend/graphene/viewer/static/reducer.mjs" in workflow
    assert "node --check backend/graphene/orchestration/static/mission_reducer.mjs" in workflow
    assert (ROOT / ".nvmrc").read_text().strip() == "22"

    assert "Linux job is a negative portability gate" in threat_model
    assert "v2 fixed-test workflow remains unsupported and fails" in threat_model
    assert "No CI job uses cloud credentials" in threat_model
    assert "secrets." not in workflow
    assert "id-token: write" not in workflow
    assert "gcloud" not in workflow
    assert " deploy" not in workflow.lower()


def test_the_lint_and_hang_guards_are_locked_not_ambient() -> None:
    """A claim that only reproduces where a linter happens to be installed is not a claim.

    scripts/morning_verify.sh and CI both run ``uv run --frozen ruff check .``;
    ``uv run`` falls through to PATH for binaries missing from the environment,
    so the pin is what makes the PASS mean anything.
    """
    project = (ROOT / "pyproject.toml").read_text()
    lock = (ROOT / "uv.lock").read_text()
    verify = (ROOT / "scripts/morning_verify.sh").read_text()

    assert '"ruff==0.12.0"' in project
    assert '"pytest-timeout==2.4.0"' in project
    assert 'name = "ruff"' in lock
    assert 'name = "pytest-timeout"' in lock
    assert "faulthandler_timeout = 180" in project
    assert "timeout = 600" in project

    # Every step reports its own failure output instead of hiding it in /dev/null.
    assert "uv run --frozen ruff check ." in verify
    assert ">/dev/null 2>&1" not in verify

    # The verdict is computed by the locked interpreter too. Three steps piped
    # their evidence into a bare `python3`, i.e. whatever the developer's PATH
    # yields (/opt/anaconda3 on this machine) decided whether the store, the
    # mission status and the capsule cold-verify passed. Comments may name the
    # ambient interpreter; steps may not.
    ambient = [
        line
        for line in verify.splitlines()
        if "python3" in line and not line.lstrip().startswith("#")
    ]
    assert not ambient, ambient

    # And the verdict is not a single-topology result. `MORNING VERIFY: ALL
    # PASS` printed on four consecutive commits while Linux CI was red on every
    # one of them, because nothing it ran could see another topology. It now
    # calls both parity checks, and reserves the bare "ALL PASS" for a run that
    # actually saw them: a skipped parity check downgrades the verdict line.
    assert "scripts/linux_parity_check.sh" in verify
    assert "scripts/macos_parity_check.sh" in verify
    assert "MORNING VERIFY: PASS ON THIS HOST ONLY" in verify
