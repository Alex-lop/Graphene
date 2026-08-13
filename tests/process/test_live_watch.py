from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"
PYTHON = ROOT / ".venv/bin/python"


def test_public_watch_streams_commits_then_stops_at_needs_human(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(GRAPHENE_LINEAGE_DB=str(database), NO_COLOR="1")

    created = subprocess.run(
        [
            str(GRAPHENE),
            "--json",
            "run",
            "baseline_max_attempts",
            "--profile",
            "platform-maintainer@1",
        ],
        cwd=runtime,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    run_id = json.loads(created.stdout)["run_id"]

    watcher = subprocess.Popen(
        [str(GRAPHENE), "--json", "watch", run_id],
        cwd=runtime,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        assert watcher.stdout is not None
        first = watcher.stdout.readline()
        assert json.loads(first)["seq"] == 1
        assert watcher.poll() is None

        appended = subprocess.run(
            [
                str(PYTHON),
                "-c",
                "\n".join(
                    (
                        "import os",
                        "from graphene.bootstrap import bootstrap_local_run",
                        "from graphene.lineage.service import ToolCallIdentity",
                        "run = bootstrap_local_run(",
                        "    os.environ['GRAPHENE_LINEAGE_DB'],",
                        "    task_id='baseline_max_attempts',",
                        "    profile_id='platform-maintainer@1',",
                        ")",
                        "def call(value):",
                        "    return ToolCallIdentity(",
                        "        session_id=run.session_id,",
                        "        invocation_id=run.invocation_id,",
                        "        model_id=run.model_id,",
                        "        tool_call_id=value,",
                        "        agent_name='graphene_agent',",
                        "        adapter_kind='local',",
                        "    )",
                        "run.service.read_file(",
                        "    run.handle, call('process_read_001'),",
                        "    path='app/auth/limiter.py',",
                        ")",
                        "run.service.request_completion(",
                        "    run.handle, call('process_completion_001'),",
                        ")",
                    )
                ),
            ],
            cwd=runtime,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert appended.returncode == 0, appended.stderr
        assert appended.stdout == appended.stderr == ""

        remaining, diagnostic = watcher.communicate(timeout=20)
    finally:
        if watcher.poll() is None:
            watcher.terminate()
            watcher.communicate(timeout=5)

    events = [json.loads(line) for line in (first + remaining).splitlines()]
    assert watcher.returncode == 0
    assert diagnostic == ""
    assert [event["seq"] for event in events] == [1, 2, 3, 4, 5]
    assert [event["event_type"] for event in events[-2:]] == [
        "completion.attempted",
        "completion.denied",
    ]

