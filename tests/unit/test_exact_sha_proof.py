from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.reliability import exact_sha_proof


SHA = "a" * 40


def test_source_gate_refuses_dirty_or_mismatched_revisions(monkeypatch) -> None:
    def git(*arguments: str) -> str:
        if arguments[0] == "status":
            return "?? local.txt"
        if arguments[:2] == ("check-ref-format", "--branch"):
            return "proof"
        if arguments[:3] == ("remote", "get-url", "origin"):
            return "git@github.com:Alex-lop/Graphene.git"
        if arguments[0] == "ls-remote":
            return f"{'b' * 40}\trefs/heads/proof"
        return SHA

    monkeypatch.setattr(exact_sha_proof, "_git", git)

    with pytest.raises(RuntimeError, match="exactly match HEAD"):
        exact_sha_proof.verify_source(
            expected_sha=SHA, remote_ref=None, require_clean=True
        )
    with pytest.raises(RuntimeError, match="remote-ref"):
        exact_sha_proof.verify_source(
            expected_sha=SHA, remote_ref="origin/proof", require_clean=False
        )
    with pytest.raises(RuntimeError, match="expected-sha"):
        exact_sha_proof.verify_source(
            expected_sha="c" * 40, remote_ref=None, require_clean=False
        )


def test_source_gate_reads_canonical_remote_instead_of_tracking_ref(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def git(*arguments: str) -> str:
        calls.append(arguments)
        if arguments[:2] == ("check-ref-format", "--branch"):
            return "proof"
        if arguments[:3] == ("remote", "get-url", "origin"):
            return "https://github.com/Alex-lop/Graphene.git"
        if arguments[0] == "ls-remote":
            return f"{SHA}\trefs/heads/proof"
        if arguments[0] == "status":
            return ""
        return SHA

    monkeypatch.setattr(exact_sha_proof, "_git", git)
    source = exact_sha_proof.verify_source(
        expected_sha=SHA, remote_ref="origin/proof", require_clean=True
    )

    assert source["remote_git_sha"] == SHA
    assert (
        "ls-remote",
        "--exit-code",
        "origin",
        "refs/heads/proof",
    ) in calls
    assert not any(
        call[:2] == ("rev-parse", "--verify") and "origin/" in call[-1]
        for call in calls
    )


def test_source_gate_refuses_noncanonical_origin(monkeypatch) -> None:
    def git(*arguments: str) -> str:
        if arguments[:2] == ("check-ref-format", "--branch"):
            return "proof"
        if arguments[:3] == ("remote", "get-url", "origin"):
            return "git@github.com:someone/fork.git"
        return SHA

    monkeypatch.setattr(exact_sha_proof, "_git", git)

    with pytest.raises(RuntimeError, match="canonical Alex-lop/Graphene"):
        exact_sha_proof.verify_source(
            expected_sha=SHA, remote_ref="origin/proof", require_clean=False
        )


def test_campaign_is_bounded_and_records_isolated_interpreter_shutdowns(
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], float]] = []

    def run(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        return subprocess.CompletedProcess(command, 0, "3 passed\n", "")

    monkeypatch.setattr(exact_sha_proof.subprocess, "run", run)
    campaign = exact_sha_proof.run_sqlite_campaign(
        runs=3, per_run_timeout=2.0, total_timeout=5.0
    )

    assert campaign["ok"] is True
    assert campaign["runs_passed"] == campaign["interpreter_shutdowns_clean"] == 3
    assert all(command[1:4] == ["-I", "-m", "pytest"] for command, _ in calls)
    assert all(0 < timeout <= 2 for _, timeout in calls)
    serialized = json.dumps(campaign)
    assert "3 passed" not in serialized
    assert "$RUN_PRIVATE_TEMP" in serialized


def test_no_key_matrix_requires_every_explicit_node_without_skips(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def run_once(command, *, environment, **_):
        captured["command"] = command
        captured["environment"] = environment
        junit = Path(
            next(
                item.split("=", 1)[1]
                for item in command
                if item.startswith("--junitxml=")
            )
        )
        junit.write_text(
            f'<testsuite tests="{len(exact_sha_proof.RUNTIME_NO_KEY_NODEIDS)}" '
            'failures="0" errors="0" skipped="0"/>',
            encoding="utf-8",
        )
        return (
            {
                "command": ["$PYTHON", "-m", "pytest"],
                "started_at": "2026-01-01T00:00:00+00:00",
                "duration_seconds": 1.0,
                "exit_status": 0,
                "timed_out": False,
                "interpreter_shutdown_clean": True,
                "stdout": {"bytes": 0, "sha256": "0" * 64},
                "stderr": {"bytes": 0, "sha256": "0" * 64},
            },
            "",
        )

    monkeypatch.setattr(exact_sha_proof, "_run_once", run_once)
    result = exact_sha_proof.run_runtime_no_key(timeout=30)

    assert result["ok"] is True
    assert result["results"] == {
        "tests": len(exact_sha_proof.RUNTIME_NO_KEY_NODEIDS),
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    command = captured["command"]
    assert all(nodeid in command for nodeid in exact_sha_proof.RUNTIME_NO_KEY_NODEIDS)
    environment = captured["environment"]
    assert all(name not in environment for name in exact_sha_proof._NO_KEY_ENVIRONMENT)


def test_manifest_is_sha_named_and_marks_credentialed_truth_unproven(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        exact_sha_proof,
        "verify_source",
        lambda **_: {
            "git_sha": SHA,
            "expected_git_sha": SHA,
            "remote_ref": "origin/proof",
            "remote_git_sha": SHA,
            "remote_ref_matches": True,
            "canonical_origin_verified": True,
            "source_tree_clean": True,
        },
    )
    monkeypatch.setattr(
        exact_sha_proof,
        "run_sqlite_campaign",
        lambda **_: {
            "schema": "graphene-sqlite-lifecycle-campaign/v1",
            "truth_class": "unit",
            "command": ["$PYTHON", "-m", "pytest"],
            "started_at": "2026-01-01T00:00:00+00:00",
            "duration_seconds": 1.0,
            "runs_requested": 20,
            "runs_completed": 20,
            "runs_passed": 20,
            "interpreter_shutdowns_clean": 20,
            "ok": True,
            "runs": [],
        },
    )
    monkeypatch.setattr(
        exact_sha_proof,
        "run_package_proof",
        lambda **_: {
            "truth_class": "packaged",
            "command": ["$PYTHON", "scripts/verify_installed_artifacts.py"],
            "duration_seconds": 2.0,
            "exit_status": 0,
            "result": {
                "source_revision": SHA,
                "source_tree_clean": True,
                "north_star_target_base_sha": "b" * 40,
                "artifacts": [
                    {
                        "artifact": "graphene.whl",
                        "artifact_sha256": "c" * 64,
                        "north_star_target_base_sha": "b" * 40,
                        "probes": list(exact_sha_proof.PACKAGE_PROBES),
                    },
                    {
                        "artifact": "graphene.tar.gz",
                        "artifact_sha256": "d" * 64,
                        "north_star_target_base_sha": "b" * 40,
                        "probes": list(exact_sha_proof.PACKAGE_PROBES),
                    },
                ],
            },
            "ok": True,
        },
    )
    monkeypatch.setattr(
        exact_sha_proof,
        "run_runtime_no_key",
        lambda **_: {
            "truth_class": "fixture",
            "command": ["$PYTHON", "-m", "pytest"],
            "duration_seconds": 3.0,
            "exit_status": 0,
            "results": {
                "tests": len(exact_sha_proof.RUNTIME_NO_KEY_NODEIDS),
                "failures": 0,
                "errors": 0,
                "skipped": 0,
            },
            "ok": True,
        },
    )

    assert exact_sha_proof.main(["--output-root", str(tmp_path)]) == 1
    unbound_path = Path(capsys.readouterr().out.strip())
    assert json.loads(unbound_path.read_text(encoding="utf-8"))["ok"] is False

    assert exact_sha_proof.main(
        [
            "--output-root",
            str(tmp_path),
            "--expected-sha",
            SHA,
            "--remote-ref",
            "origin/proof",
            "--require-clean",
        ]
    ) == 0
    manifest_path = Path(capsys.readouterr().out.strip())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_path.parent.name == SHA
    assert manifest["source"]["git_sha"] == SHA
    assert manifest["source"]["proof_gate_satisfied"] is True
    assert manifest["claims"][-1]["observed_result"][
        "north_star_target_base_sha"
    ] == "b" * 40
    assert manifest["claims"][0]["truth_class"] == "unit"
    assert {
        "mcp-acceptance-latency-idempotency",
        "controller-disconnect-reattachment",
        "stale-fence-refusal",
        "sibling-preservation-higher-fence-retry",
        "exact-final-bundle-isolated-result",
        "causal-why-explicit-unknowns",
        "stable-cloud-read-handoff-contract",
    } <= {claim["name"] for claim in manifest["claims"]}
    assert manifest["unproven"]["live_gemini"].startswith("requires explicit")
    assert "real_model_kill" in manifest["unproven"]


def test_package_sanitizer_rejects_artifact_target_base_drift() -> None:
    with pytest.raises(ValueError, match="different target bases"):
        exact_sha_proof._sanitize_package_result(
            {
                "north_star_target_base_sha": "b" * 40,
                "artifacts": [
                    {
                        "artifact": "graphene.whl",
                        "artifact_sha256": "c" * 64,
                        "north_star_target_base_sha": "c" * 40,
                        "probes": list(exact_sha_proof.PACKAGE_PROBES),
                    },
                    {
                        "artifact": "graphene.tar.gz",
                        "artifact_sha256": "d" * 64,
                        "north_star_target_base_sha": "b" * 40,
                        "probes": list(exact_sha_proof.PACKAGE_PROBES),
                    },
                ],
            }
        )


@pytest.mark.parametrize(
    ("artifacts", "message"),
    [
        ([], "one wheel and one sdist"),
        ([{"artifact": "graphene.whl"}], "one wheel and one sdist"),
        (["not-an-object", {}], "one wheel and one sdist"),
        (
            [
                {
                    "artifact": "graphene.whl",
                    "artifact_sha256": "c" * 64,
                    "north_star_target_base_sha": "b" * 40,
                    "probes": [],
                },
                {
                    "artifact": "graphene.tar.gz",
                    "artifact_sha256": "d" * 64,
                    "north_star_target_base_sha": "b" * 40,
                    "probes": list(exact_sha_proof.PACKAGE_PROBES),
                },
            ],
            "probes are incomplete",
        ),
    ],
)
def test_package_sanitizer_rejects_partial_or_malformed_artifacts(
    artifacts, message
) -> None:
    with pytest.raises(ValueError, match=message):
        exact_sha_proof._sanitize_package_result(
            {
                "north_star_target_base_sha": "b" * 40,
                "artifacts": artifacts,
            }
        )
