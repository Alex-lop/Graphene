from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from graphene.bootstrap import bootstrap_local_run
from graphene.lineage.service import ToolCallIdentity
from graphene.models import GoldenContract

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)


def _call(run, number: int) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.model_id,
        tool_call_id=f"cli_human_call_{number:03d}",
        agent_name="graphene_local",
        adapter_kind="local",
    )


def _cli(environment: dict[str, str], cwd: Path, *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [str(GRAPHENE), "--json", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stderr == b""
    return json.loads(result.stdout)


def test_public_human_commands_reach_billing_denial_and_fresh_auth(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    source = bootstrap_local_run(
        database,
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )
    read = source.service.read_file(
        source.handle,
        _call(source, 1),
        path="app/auth/limiter.py",
    )
    source.service.write_file(
        source.handle,
        _call(source, 2),
        path="app/auth/limiter.py",
        content=read.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"),
    )
    assert source.service.run_fixed_test(source.handle, _call(source, 3)).passed
    source.service.request_completion(source.handle, _call(source, 4))

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["GRAPHENE_LINEAGE_DB"] = str(database)
    review = _cli(environment, runtime, "review", source.run_id)
    hunk = review["hunks"][0]
    write_event_id = review["write_event_ids"][0]
    asked = _cli(
        environment,
        runtime,
        "feedback",
        hunk["hunk_id"],
        "--event",
        write_event_id,
        "--run",
        source.run_id,
        "--message",
        GOLDEN.memory.correction,
    )
    answered = _cli(
        environment,
        runtime,
        "answer",
        asked["question_id"],
        "--choice",
        "all_auth",
    )
    approved = _cli(
        environment,
        runtime,
        "memory",
        "approve",
        answered["memory_id"],
    )
    assert approved["state"] == "approved"

    with closing(sqlite3.connect(database)) as connection:
        runs_before = connection.execute("SELECT COUNT(*) FROM run_heads").fetchone()[0]
    billing = _cli(
        environment,
        runtime,
        "handoff",
        source.run_id,
        "--to",
        "billing-observer@1",
        "--task",
        "adapted_window_seconds",
    )
    assert billing["decision"]["decision"] == "denied"
    assert billing["denial"]["model_dispatch_count"] == 0
    assert billing["denial"]["consumer_run_id"] is None
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM run_heads").fetchone()[0]
            == runs_before
        )

    auth = _cli(
        environment,
        runtime,
        "handoff",
        source.run_id,
        "--to",
        "auth-maintainer@1",
        "--task",
        "adapted_window_seconds",
        "--start",
    )
    assert auth["consumer_run_id"] != source.run_id
    assert (
        len({auth["consumer_run_id"], auth["session_id"], auth["invocation_id"]}) == 3
    )

    inspected = _cli(
        environment,
        runtime,
        "inspect",
        hunk["evidence_id"],
        "--run",
        source.run_id,
    )
    why = _cli(
        environment,
        runtime,
        "why",
        "app/auth/limiter.py",
        "--run",
        source.run_id,
    )
    assert inspected["item"]["type"] == "artifact"
    assert {item["relation"] for item in why["relationships"]} >= {
        "TRIGGERED",
        "APPROVED",
    }
