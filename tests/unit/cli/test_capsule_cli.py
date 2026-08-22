from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphene.cli.main import main
from graphene.cli.mission import _MISSION_COMMANDS, build_parser, initialize
from graphene.orchestration.capsule import CAPSULE_SUFFIX
from graphene.orchestration.scripted import load_scenario, scripted_supported

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_CHECKS = [
    "manifest_file_digests",
    "mission_event_chain",
    "attempt_evidence_chains",
    "receipt_references",
    "receipt_contents",
    "final_bundle",
    "tree_manifest",
    "publication_envelopes",
    "plan_revisions",
    "attempt_coverage",
    "manifest_summary",
]

requires_scripted = pytest.mark.skipif(
    not scripted_supported(),
    reason="capsule export from a scripted-local mission needs the macOS sandbox",
)


def _repository(root: Path) -> Path:
    repository = root / "repo"
    repository.mkdir()
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_AUTHOR_EMAIL": "fixture@graphene.invalid",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_EMAIL": "fixture@graphene.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(("git", "init", "-q", "-b", "main"), cwd=repository, check=True)
    (repository / "README.md").write_text("# Fixture\n")
    subprocess.run(("git", "add", "--all", "--"), cwd=repository, check=True)
    subprocess.run(
        ("git", "commit", "-q", "-m", "base"),
        cwd=repository,
        env=environment,
        check=True,
    )
    return repository


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    if not scripted_supported():
        pytest.skip("scripted-local mission requires the macOS fixture sandbox")
    root = tmp_path_factory.mktemp("capsule-cli")
    state = root / "state"
    repository = _repository(root)
    initialize(repository)
    patch = pytest.MonkeyPatch()
    patch.setenv("GRAPHENE_STATE_DIR", str(state))
    try:
        code, out, err = _run(
            [
                "--json",
                "mission",
                "start",
                "--repo",
                str(repository),
                "--goal",
                load_scenario().goal,
                "--driver",
                "scripted-local",
                "--auto-approve",
            ]
        )
        assert code == 0, err
        started = json.loads(out)
        assert started["status"] == "awaiting_result"
        mission_id = started["mission_id"]
        output = root / "capsules"
        output.mkdir(mode=0o700)
        code, out, err = _run(
            [
                "--json",
                "mission",
                "capsule",
                "export",
                mission_id,
                "--output",
                str(output),
            ]
        )
        assert code == 0, err
        value = json.loads(out)
    finally:
        patch.undo()
    return SimpleNamespace(
        state=state,
        mission_id=mission_id,
        output=output,
        capsule_dir=Path(value["capsule_dir"]),
        value=value,
        patch_sha256=started["candidate_sha256"],
    )


def test_capsule_is_a_mission_command_with_export_and_verify_grammar() -> None:
    assert "capsule" in _MISSION_COMMANDS
    parser = build_parser()

    export = parser.parse_args(
        ["mission", "capsule", "export", "mission_1", "--output", "capsules"]
    )
    assert export.command == "mission"
    assert export.mission_action == "capsule"
    assert export.capsule_action == "export"
    assert export.mission_id == "mission_1"
    assert export.output == Path("capsules")

    verify = parser.parse_args(
        ["mission", "capsule", "verify", "capsules/mission_1.graphene-capsule"]
    )
    assert verify.mission_action == "capsule"
    assert verify.capsule_action == "verify"
    assert verify.capsule_dir == Path("capsules/mission_1.graphene-capsule")

    for argv in (
        ["mission", "capsule"],
        ["mission", "capsule", "export", "mission_1"],
        ["mission", "capsule", "verify"],
        ["mission", "capsule", "export", "mission_1", "--output"],
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)


def test_capsule_help_states_redaction_and_the_verify_command() -> None:
    parser = build_parser()
    mission = parser._subparsers._group_actions[0].choices["mission"]
    capsule = mission._subparsers._group_actions[0].choices["capsule"]
    actions = capsule._subparsers._group_actions[0].choices
    export_help = actions["export"].format_help()
    verify_help = actions["verify"].format_help()

    assert "no prompts, source bytes, diffs, command output" in export_help
    assert "graphene mission capsule verify" in export_help
    assert "never opens the mission store" in verify_help


def test_readme_and_contract_document_the_capsule_command() -> None:
    readme = (ROOT / "README.md").read_text()
    contract = (ROOT / "docs/TASKMASTER_PRODUCT_CONTRACT.md").read_text()

    assert "`graphene mission capsule`" in readme
    assert "graphene mission capsule export MISSION_ID --output DIR" in readme
    assert "graphene mission capsule verify CAPSULE_DIR" in readme
    assert "no prompts, source bytes, diffs, or command output" in readme
    assert "Mission Capsule" in contract
    assert "graphene mission capsule verify" in contract
    assert "never opens the mission store" in contract


def test_verify_rejects_a_missing_capsule_without_touching_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "fresh-state"
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))

    code, out, err = _run(["mission", "capsule", "verify", str(tmp_path / "nope")])

    assert code == 1
    assert out == ""
    assert "MISSION_ERROR: capsule verification failed" in err
    assert not state.exists()


def test_export_fails_closed_for_a_mission_without_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "state"))
    output = tmp_path / "capsules"
    output.mkdir(mode=0o700)

    code, out, err = _run(
        ["mission", "capsule", "export", "mission_missing", "--output", str(output)]
    )

    assert code == 1
    assert out == ""
    assert "MISSION_ERROR: mission attempt evidence is unavailable" in err
    assert list(output.iterdir()) == []


@requires_scripted
def test_export_writes_the_capsule_from_verified_mission_authority(
    exported: SimpleNamespace,
) -> None:
    assert exported.value["status"] == "exported"
    assert exported.value["mission_id"] == exported.mission_id
    assert exported.value["final_bundle_present"] is True
    assert exported.capsule_dir == (
        exported.output / f"{exported.mission_id}{CAPSULE_SUFFIX}"
    )
    assert (exported.capsule_dir / "manifest.json").is_file()
    assert (exported.capsule_dir / "events.ndjson").is_file()
    manifest = json.loads((exported.capsule_dir / "manifest.json").read_bytes())
    assert manifest["mission_id"] == exported.mission_id
    assert manifest["mission_status"] == "awaiting_result"
    assert "patch" in manifest["excluded_artifact_kinds"]
    for path in exported.capsule_dir.rglob("*"):
        if path.is_file():
            assert b"diff --git" not in path.read_bytes(), path


@requires_scripted
def test_verify_prints_every_check_and_verified_without_opening_a_store(
    exported: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_state = tmp_path / "fresh-state"
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(fresh_state))

    code, out, err = _run(["mission", "capsule", "verify", str(exported.capsule_dir)])

    assert code == 0, err
    assert err == ""
    lines = out.splitlines()
    assert lines[0].startswith(f"CAPSULE {exported.mission_id} ")
    checks = [line for line in lines if line.startswith("CHECK ")]
    assert [line.split()[1] for line in checks] == EXPECTED_CHECKS
    assert all(line.split()[2] == "ok=True" for line in checks)
    assert any(line.startswith("NOT_CHECKED ") for line in lines)
    assert lines[-1] == (
        f"VERIFIED {exported.mission_id} checks={len(EXPECTED_CHECKS)}"
    )
    assert not (fresh_state / "missions.sqlite3").exists()
    assert not fresh_state.exists()

    code, out, err = _run(
        ["--json", "mission", "capsule", "verify", str(exported.capsule_dir)]
    )

    assert code == 0, err
    value = json.loads(out)
    assert value["verified"] is True
    assert value["mission_id"] == exported.mission_id
    assert [item["name"] for item in value["checks"]] == EXPECTED_CHECKS
    assert all(item["ok"] for item in value["checks"])
    assert value["not_checked"]
    assert not fresh_state.exists()


@requires_scripted
def test_tampered_capsule_prints_failed_with_exit_one(
    exported: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "fresh-state"))
    tampered = tmp_path / exported.capsule_dir.name
    shutil.copytree(exported.capsule_dir, tampered)
    events = tampered / "events.ndjson"
    lines = events.read_bytes().split(b"\n")
    value = json.loads(lines[0])
    value["recorded_at"] = "2000-01-01T00:00:00+00:00"
    lines[0] = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    events.write_bytes(b"\n".join(lines))

    code, out, err = _run(["mission", "capsule", "verify", str(tampered)])

    assert code == 1
    assert err == ""
    lines = out.splitlines()
    assert "CHECK manifest_file_digests ok=False" in lines[1]
    assert "events.ndjson" in lines[1]
    assert lines[-1] == f"FAILED {exported.mission_id} check=manifest_file_digests"

    code, out, err = _run(["--json", "mission", "capsule", "verify", str(tampered)])

    assert code == 1
    value = json.loads(out)
    assert value["verified"] is False
    assert value["checks"][-1]["ok"] is False
    assert not (tmp_path / "fresh-state").exists()


@requires_scripted
def test_export_refuses_an_existing_capsule_and_relative_output_resolves_to_cwd(
    exported: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(exported.state))

    code, out, err = _run(
        [
            "mission",
            "capsule",
            "export",
            exported.mission_id,
            "--output",
            str(exported.output),
        ]
    )

    assert code == 1
    assert out == ""
    assert "MISSION_ERROR: capsule export failed: capsule directory already exists" in (
        err
    )

    monkeypatch.chdir(tmp_path)
    code, out, err = _run(
        ["mission", "capsule", "export", exported.mission_id, "--output", "."]
    )

    assert code == 0, err
    assert out.startswith("GRAPHENE status=exported ")
    assert f"capsule_dir={tmp_path / exported.capsule_dir.name}" in out
    assert (tmp_path / exported.capsule_dir.name / "manifest.json").is_file()
