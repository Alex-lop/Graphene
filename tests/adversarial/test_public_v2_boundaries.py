from __future__ import annotations

import json
import os
import pty
import select
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
        tool_call_id=f"public_boundary_call_{number:03d}",
        agent_name="graphene_local",
        adapter_kind="local",
    )


def _cli(environment: dict[str, str], cwd: Path, *arguments: str) -> dict[str, object]:
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [str(GRAPHENE), "--json", *arguments],
        cwd=cwd,
        env=environment,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    output = bytearray()
    try:
        while process.poll() is None:
            ready, _, _ = select.select([master], [], [], 20)
            if not ready:
                process.kill()
                raise AssertionError("TTY CLI command timed out")
            chunk = os.read(master, 65_536)
            if not chunk:
                break
            output.extend(chunk)
        while select.select([master], [], [], 0)[0]:
            chunk = os.read(master, 65_536)
            if not chunk:
                break
            output.extend(chunk)
    except OSError:
        pass
    finally:
        os.close(master)
    assert process.wait(timeout=1) == 0, output.decode(errors="replace")
    return json.loads(output.decode().replace("\r", "").splitlines()[-1])


def _run_count(database: Path) -> int:
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        return connection.execute("SELECT COUNT(*) FROM run_heads").fetchone()[0]


def test_retried_public_handoff_start_reuses_the_committed_consumer(
    tmp_path: Path,
) -> None:
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
    asked = _cli(
        environment,
        runtime,
        "feedback",
        review["hunks"][0]["hunk_id"],
        "--event",
        review["write_event_ids"][0],
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
    _cli(environment, runtime, "memory", "approve", answered["memory_id"])

    arguments = (
        "handoff",
        source.run_id,
        "--to",
        "auth-maintainer@1",
        "--task",
        "adapted_window_seconds",
        "--start",
    )
    first = _cli(environment, runtime, *arguments)
    runs_after_first = _run_count(database)
    second = _cli(environment, runtime, *arguments)

    assert _run_count(database) == runs_after_first
    assert second == first
