from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"
SHA256 = re.compile(r"[0-9a-f]{64}").fullmatch


def _invoke(arguments: list[str], *, environment: dict[str, str], cwd: Path):
    return subprocess.run(
        [str(GRAPHENE), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def test_public_run_is_durable_and_visible_after_process_restart(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(
        GRAPHENE_LINEAGE_DB=str(database),
        NO_COLOR="1",
    )

    created = _invoke(
        [
            "--json",
            "run",
            "baseline_max_attempts",
            "--profile",
            "platform-maintainer@1",
        ],
        environment=environment,
        cwd=runtime,
    )

    assert created.returncode == 0, created.stderr.decode(errors="replace")
    assert created.stderr == b""
    result = json.loads(created.stdout)
    assert created.stdout == _canonical(result)
    assert set(result) == {
        "database",
        "projection_sha256",
        "run_id",
        "verified_head",
    }
    assert result["database"] == str(database.resolve())
    assert database.is_file()
    assert SHA256(result["projection_sha256"])
    assert result["verified_head"] == {
        "event_count": 1,
        "event_sha256": result["verified_head"]["event_sha256"],
        "run_id": result["run_id"],
        "seq": 1,
    }
    assert SHA256(result["verified_head"]["event_sha256"])

    watched = _invoke(
        ["--json", "watch", result["run_id"], "--snapshot"],
        environment=environment,
        cwd=runtime,
    )
    assert watched.returncode == 0, watched.stderr.decode(errors="replace")
    assert watched.stderr == b""
    event = json.loads(watched.stdout)
    assert watched.stdout == _canonical(event)
    assert event["run_id"] == result["run_id"]
    assert event["seq"] == 1
    assert event["event_type"] == "run.started"
    assert event["event_sha256"] == result["verified_head"]["event_sha256"]

    first_projection = _invoke(
        ["watch", result["run_id"], "--snapshot"], environment=environment, cwd=runtime
    )
    restarted_projection = _invoke(
        ["watch", result["run_id"], "--snapshot"], environment=environment, cwd=runtime
    )
    assert first_projection.returncode == restarted_projection.returncode == 0
    assert first_projection.stderr == restarted_projection.stderr == b""
    assert first_projection.stdout == restarted_projection.stdout
    assert b"\x1b[" not in first_projection.stdout
