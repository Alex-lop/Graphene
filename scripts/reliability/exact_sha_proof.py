#!/usr/bin/env python3
"""Generate bounded, sanitized proof for one exact Graphene revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_TEST = "tests/unit/orchestration/test_sqlite_lifecycle.py"
SCHEMA = "graphene-exact-sha-proof/v1"
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CANONICAL_ORIGINS = {
    "git@github.com:Alex-lop/Graphene.git",
    "https://github.com/Alex-lop/Graphene.git",
}
PACKAGE_PROBES = (
    "entry-points",
    "verified-demo-replay",
    "mission-replay",
    "replay-ui",
    "installed-north-star-materialization",
    "legacy-cli-bootstrap",
    "mission-mcp-no-key-start-and-reattach",
    "legacy-mcp-initialize",
)
RUNTIME_NO_KEY_NODEIDS = (
    "tests/unit/integrations/test_mission_mcp.py::"
    "test_start_returns_promptly_is_idempotent_and_review_approval_is_nonblocking",
    "tests/process/test_mission_mcp_stdio.py::"
    "test_controller_exit_does_not_stop_auto_finalizing_mission_and_fresh_stdio_reattaches",
    "tests/unit/orchestration/test_store.py::"
    "test_claim_heartbeat_expiry_and_fencing_reject_stale_workers",
    "tests/unit/orchestration/test_failure_laboratory.py::"
    "test_sigkilled_second_worker_retries_under_higher_fence_without_touching_sibling",
    "tests/unit/orchestration/test_gemini_mission_runtime.py::"
    "test_orders_migration_survives_a_root_failure_without_credentials",
    "tests/unit/orchestration/test_causal_query.py::"
    "test_why_reports_only_committed_causal_links_and_explicit_unknowns",
    "tests/unit/orchestration/test_cloud.py::"
    "test_health_and_mission_control_are_read_only_and_honest",
)
_NO_KEY_ENVIRONMENT = (
    "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
    "GEMINI_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GRAPHENE_RUN_CLOUD_SMOKE",
    "GRAPHENE_RUN_LIVE_FIRESTORE",
    "GRAPHENE_GITHUB_TOKEN",
    "SSH_AUTH_SOCK",
)
_RUNTIME_CLAIMS = (
    (
        "mcp-acceptance-latency-idempotency",
        "fixture",
        (RUNTIME_NO_KEY_NODEIDS[0],),
        "MCP start accepted within the bounded latency and duplicate request reused its mission",
    ),
    (
        "controller-disconnect-reattachment",
        "fixture",
        (RUNTIME_NO_KEY_NODEIDS[1],),
        "detached execution survived controller exit and a fresh MCP session reattached",
    ),
    (
        "stale-fence-refusal",
        "unit",
        (RUNTIME_NO_KEY_NODEIDS[2],),
        "expired worker authority was refused after a higher fencing token was issued",
    ),
    (
        "sibling-preservation-higher-fence-retry",
        "fixture",
        (RUNTIME_NO_KEY_NODEIDS[3], RUNTIME_NO_KEY_NODEIDS[4]),
        "bounded fixture recovery preserved the successful sibling and retried under a higher fence",
    ),
    (
        "exact-final-bundle-isolated-result",
        "fixture",
        (RUNTIME_NO_KEY_NODEIDS[1], RUNTIME_NO_KEY_NODEIDS[4]),
        "exact final-bundle evidence produced an isolated result without mutating the source checkout",
    ),
    (
        "causal-why-explicit-unknowns",
        "unit",
        (RUNTIME_NO_KEY_NODEIDS[5],),
        "causal why used committed links and reported absent evidence as explicit unknowns",
    ),
    (
        "stable-cloud-read-handoff-contract",
        "unit",
        (RUNTIME_NO_KEY_NODEIDS[6],),
        "the configured cloud handoff surface stayed read-only and labeled deployment proof absent",
    ),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def verify_source(
    *, expected_sha: str | None, remote_ref: str | None, require_clean: bool
) -> dict[str, object]:
    revision = _git("rev-parse", "--verify", "HEAD^{commit}")
    if not _SHA.fullmatch(revision):
        raise RuntimeError("HEAD is not a full Git object ID")
    if expected_sha is not None and revision != expected_sha.lower():
        raise RuntimeError("HEAD does not match --expected-sha")
    remote_revision: str | None = None
    if remote_ref is not None:
        prefix = "origin/"
        if not remote_ref.startswith(prefix):
            raise RuntimeError("--remote-ref must name an origin branch")
        branch = remote_ref.removeprefix(prefix)
        if _git("check-ref-format", "--branch", branch) != branch:
            raise RuntimeError("--remote-ref branch is invalid")
        if _git("remote", "get-url", "origin") not in _CANONICAL_ORIGINS:
            raise RuntimeError(
                "origin is not the canonical Alex-lop/Graphene repository"
            )
        target = f"refs/heads/{branch}"
        fields = _git("ls-remote", "--exit-code", "origin", target).split()
        if len(fields) != 2 or fields[1] != target or not _SHA.fullmatch(fields[0]):
            raise RuntimeError("canonical remote returned an invalid branch reference")
        remote_revision = fields[0]
        if remote_revision != revision:
            raise RuntimeError("HEAD does not match --remote-ref")
    clean = not _git("status", "--porcelain", "--untracked-files=all")
    if require_clean and not clean:
        raise RuntimeError("source tree does not exactly match HEAD")
    return {
        "git_sha": revision,
        "expected_git_sha": expected_sha.lower() if expected_sha else None,
        "remote_ref": remote_ref,
        "remote_git_sha": remote_revision,
        "remote_ref_matches": remote_ref is not None,
        "canonical_origin_verified": remote_ref is not None,
        "source_tree_clean": clean,
    }


def _digest(value: str | bytes | None) -> dict[str, object]:
    if value is None:
        raw = b""
    elif isinstance(value, bytes):
        raw = value
    else:
        raw = value.encode("utf-8", errors="replace")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _run_once(
    command: list[str],
    *,
    display_command: list[str],
    timeout: float,
    environment: dict[str, str],
    iteration: int | None = None,
) -> tuple[dict[str, object], str | bytes | None]:
    started_at = _now()
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout, stderr = completed.stdout, completed.stderr
        exit_status: int | None = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout, error.stderr
        exit_status = None
        timed_out = True
    duration = time.monotonic() - started
    result: dict[str, object] = {
        "command": display_command,
        "started_at": started_at,
        "duration_seconds": round(duration, 6),
        "exit_status": exit_status,
        "timed_out": timed_out,
        "interpreter_shutdown_clean": not timed_out and exit_status == 0,
        "stdout": _digest(stdout),
        "stderr": _digest(stderr),
    }
    if iteration is not None:
        result["iteration"] = iteration
    return result, stdout


def run_sqlite_campaign(
    *, runs: int, per_run_timeout: float, total_timeout: float
) -> dict[str, object]:
    command = [sys.executable, "-I", "-m", "pytest", "-q", LIFECYCLE_TEST]
    display_command = ["$PYTHON", "-I", "-m", "pytest", "-q", LIFECYCLE_TEST]
    environment = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment.update(
        {
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
        }
    )
    started_at = _now()
    started = time.monotonic()
    results: list[dict[str, object]] = []
    for iteration in range(1, runs + 1):
        remaining = total_timeout - (time.monotonic() - started)
        if remaining <= 0:
            break
        with tempfile.TemporaryDirectory(prefix="graphene-sqlite-proof-") as state:
            run_environment = {**environment, "GRAPHENE_STATE_DIR": state}
            result, _ = _run_once(
                command,
                display_command=display_command,
                timeout=min(per_run_timeout, remaining),
                environment=run_environment,
                iteration=iteration,
            )
            results.append(result)
    duration = time.monotonic() - started
    passed = sum(item["exit_status"] == 0 for item in results)
    shutdowns = sum(item["interpreter_shutdown_clean"] is True for item in results)
    return {
        "schema": "graphene-sqlite-lifecycle-campaign/v1",
        "truth_class": "unit",
        "command": display_command,
        "sanitized_environment": {
            "GRAPHENE_STATE_DIR": "$RUN_PRIVATE_TEMP",
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
        },
        "started_at": started_at,
        "duration_seconds": round(duration, 6),
        "per_run_timeout_seconds": per_run_timeout,
        "total_timeout_seconds": total_timeout,
        "runs_requested": runs,
        "runs_completed": len(results),
        "runs_passed": passed,
        "interpreter_shutdowns_clean": shutdowns,
        "ok": passed == shutdowns == len(results) == runs,
        "runs": results,
    }


def _junit_counts(path: Path) -> dict[str, int] | None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    suites = (root,) if root.tag == "testsuite" else tuple(root.iter("testsuite"))
    return {
        name: sum(int(suite.attrib.get(name, "0")) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }


def run_runtime_no_key(*, timeout: float) -> dict[str, object]:
    environment = dict(os.environ)
    for name in (*_NO_KEY_ENVIRONMENT, "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment.update(
        {
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
        }
    )
    with tempfile.TemporaryDirectory(prefix="graphene-runtime-proof-") as raw:
        private = Path(raw)
        junit = private / "runtime-no-key.xml"
        command = [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            f"--junitxml={junit}",
            *RUNTIME_NO_KEY_NODEIDS,
        ]
        display = [
            "$PYTHON",
            "-I",
            "-m",
            "pytest",
            "-q",
            "--junitxml=$RUN_PRIVATE_TEMP/runtime-no-key.xml",
            *RUNTIME_NO_KEY_NODEIDS,
        ]
        result, _ = _run_once(
            command,
            display_command=display,
            timeout=timeout,
            environment={**environment, "GRAPHENE_STATE_DIR": raw},
        )
        counts = _junit_counts(junit)
    result.update(
        {
            "schema": "graphene-runtime-no-key/v1",
            "truth_class": "fixture",
            "nodeids": list(RUNTIME_NO_KEY_NODEIDS),
            "timeout_seconds": timeout,
            "sanitized_environment": {
                "credential_environment": "removed",
                "GRAPHENE_STATE_DIR": "$RUN_PRIVATE_TEMP",
                "NO_COLOR": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
                "PYTHONNOUSERSITE": "1",
            },
            "results": counts,
            "ok": bool(
                result["interpreter_shutdown_clean"]
                and counts
                == {
                    "tests": len(RUNTIME_NO_KEY_NODEIDS),
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                }
            ),
        }
    )
    return result


def _sanitize_package_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("package verifier did not return an object")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("package verifier did not return artifacts")
    target_base_sha = value.get("north_star_target_base_sha")
    if (
        not isinstance(target_base_sha, str)
        or len(target_base_sha) != 40
        or not _SHA.fullmatch(target_base_sha)
    ):
        raise ValueError("package verifier did not return a target base SHA")
    if len(artifacts) != 2 or any(not isinstance(item, dict) for item in artifacts):
        raise ValueError("package verifier must return one wheel and one sdist")
    sanitized_artifacts: list[dict[str, object]] = []
    kinds: set[str] = set()
    for item in artifacts:
        artifact = item.get("artifact")
        digest = item.get("artifact_sha256")
        probes = item.get("probes")
        if not isinstance(artifact, str):
            raise ValueError("package verifier returned an invalid artifact name")
        kind = (
            "wheel"
            if artifact.endswith(".whl")
            else "sdist"
            if artifact.endswith(".tar.gz")
            else ""
        )
        if not kind or kind in kinds:
            raise ValueError("package verifier must return one wheel and one sdist")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError("package verifier returned an invalid artifact digest")
        if item.get("north_star_target_base_sha") != target_base_sha:
            raise ValueError("installed artifacts materialized different target bases")
        if not isinstance(probes, list) or tuple(probes) != PACKAGE_PROBES:
            raise ValueError("installed artifact probes are incomplete")
        kinds.add(kind)
        sanitized_artifacts.append(
            {
                "artifact": artifact,
                "artifact_sha256": digest,
                "north_star_target_base_sha": target_base_sha,
                "probes": probes,
            }
        )
    if kinds != {"wheel", "sdist"}:
        raise ValueError("package verifier must return one wheel and one sdist")
    return {
        "source_revision": value.get("source_revision"),
        "source_tree_clean": value.get("source_tree_clean"),
        "north_star_target_base_sha": target_base_sha,
        "artifacts": sanitized_artifacts,
    }


def run_package_proof(*, timeout: float) -> dict[str, object]:
    display = ["$PYTHON", "scripts/verify_installed_artifacts.py", "--require-clean"]
    environment = dict(os.environ)
    environment.update({"NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    result, stdout = _run_once(
        [sys.executable, "scripts/verify_installed_artifacts.py", "--require-clean"],
        display_command=display,
        timeout=timeout,
        environment=environment,
    )
    sanitized: dict[str, object] | None = None
    if result["exit_status"] == 0:
        try:
            sanitized = _sanitize_package_result(json.loads(stdout or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            sanitized = None
    result["truth_class"] = "packaged"
    result["sanitized_environment"] = {
        "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result["result"] = sanitized
    result["ok"] = result["exit_status"] == 0 and sanitized is not None
    return result


def _write_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)


def _artifact(path: Path, *, root: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-sha")
    parser.add_argument("--remote-ref")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--per-run-timeout", type=float, default=60.0)
    parser.add_argument("--campaign-timeout", type=float, default=1800.0)
    parser.add_argument("--runtime-timeout", type=float, default=900.0)
    parser.add_argument("--package-timeout", type=float, default=1800.0)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.per_run_timeout <= 0 or args.campaign_timeout <= 0:
        parser.error("runs and timeouts must be positive")
    if args.runtime_timeout <= 0 or args.package_timeout <= 0:
        parser.error("runtime and package timeouts must be positive")
    try:
        source = verify_source(
            expected_sha=args.expected_sha,
            remote_ref=args.remote_ref,
            require_clean=args.require_clean,
        )
    except RuntimeError as error:
        parser.error(str(error))
    source_ok = bool(
        args.expected_sha
        and args.remote_ref
        and args.require_clean
        and source.get("git_sha") == args.expected_sha.lower()
        and source.get("expected_git_sha") == source.get("git_sha")
        and source.get("remote_git_sha") == source.get("git_sha")
        and source.get("remote_ref") == args.remote_ref
        and source.get("remote_ref_matches") is True
        and source.get("canonical_origin_verified") is True
        and source.get("source_tree_clean") is True
    )
    source["proof_gate_satisfied"] = source_ok

    output_root = args.output_root.resolve()
    if output_root == ROOT or output_root.is_relative_to(ROOT):
        parser.error("--output-root must be outside the source tree")
    output = output_root / str(source["git_sha"])
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)

    campaign = run_sqlite_campaign(
        runs=args.runs,
        per_run_timeout=args.per_run_timeout,
        total_timeout=args.campaign_timeout,
    )
    campaign_path = output / "sqlite-lifecycle-campaign.json"
    _write_json(campaign_path, campaign)
    claims: list[dict[str, Any]] = [
        {
            "name": "sqlite-stress-campaign",
            "truth_class": "unit",
            "command": campaign["command"],
            "duration_seconds": campaign["duration_seconds"],
            "exit_status": 0 if campaign["ok"] else 1,
            "artifact": _artifact(campaign_path, root=output),
            "observed_result": {
                key: campaign[key]
                for key in (
                    "runs_requested",
                    "runs_completed",
                    "runs_passed",
                    "interpreter_shutdowns_clean",
                    "ok",
                )
            },
            "claim_permitted": (
                f"{args.runs} isolated SQLite lifecycle runs completed without "
                "a timeout, failure, or interpreter-shutdown wedge"
                if campaign["ok"]
                else "no SQLite lifecycle reliability claim is permitted"
            ),
        }
    ]

    runtime = run_runtime_no_key(timeout=args.runtime_timeout)
    runtime_path = output / "runtime-no-key.json"
    _write_json(runtime_path, runtime)
    runtime_artifact = _artifact(runtime_path, root=output)
    for name, truth_class, nodeids, permitted in _RUNTIME_CLAIMS:
        claims.append(
            {
                "name": name,
                "truth_class": truth_class,
                "command": runtime["command"],
                "duration_seconds": runtime["duration_seconds"],
                "exit_status": runtime["exit_status"],
                "artifact": runtime_artifact,
                "observed_result": {
                    "matrix_ok": runtime["ok"],
                    "nodeids": list(nodeids),
                    "results": runtime["results"],
                },
                "claim_permitted": (
                    permitted
                    if runtime["ok"]
                    else f"no {name.replace('-', ' ')} claim is permitted"
                ),
            }
        )

    package = run_package_proof(timeout=args.package_timeout)
    package_path = output / "installed-package-smoke.json"
    _write_json(package_path, package)
    raw_package_result = package["result"]
    try:
        package_result = _sanitize_package_result(raw_package_result)
    except (TypeError, ValueError):
        package_result = None
    package_ok = bool(
        package["ok"]
        and isinstance(package_result, dict)
        and package_result == raw_package_result
        and package_result.get("source_revision") == source["git_sha"]
        and package_result.get("source_tree_clean") is True
    )
    claims.append(
        {
            "name": "installed-package-smoke",
            "truth_class": "packaged",
            "command": package["command"],
            "duration_seconds": package["duration_seconds"],
            "exit_status": package["exit_status"],
            "artifact": _artifact(package_path, root=output),
            "observed_result": raw_package_result,
            "claim_permitted": (
                "wheel and sdist installed-entry-point probes passed"
                if package_ok
                else "no installed-package claim is permitted"
            ),
        }
    )

    manifest = {
        "schema": SCHEMA,
        "generated_at": _now(),
        "source": source,
        "sanitized_environment": {
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "credentials_inspected": False,
        },
        "claims": claims,
        "unproven": {
            "codex_connected": "not run by this local proof generator",
            "cloud_deployment": "requires separately authorized deployment proof",
            "live_gemini": "requires explicit credentials and owner-approved budget",
            "real_model_kill": "requires an explicitly authorized live provider invocation",
        },
        "ok": source_ok and bool(campaign["ok"]) and bool(runtime["ok"]) and package_ok,
    }
    manifest_path = output / "manifest.json"
    _write_json(manifest_path, manifest)
    print(manifest_path)
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
