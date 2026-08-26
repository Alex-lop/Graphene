from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import SQLiteCheckpointRecorder
from graphene.lineage.sqlite_lineage_store import SQLiteLineageStore
from graphene.core_models import (
    LineageAuthority,
    LineageEventType,
    SourceKind,
    VerifiedHead,
)

ROOT = Path(__file__).parents[2]
GRAPHENE = ROOT / ".venv/bin/graphene"
LABEL = (
    "REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — "
    "NOT GEMINI OR INDEPENDENT-AGENT PROOF"
)


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="the production fixed-test demo is macOS-only",
)
def test_adk_fake_demo_uses_two_real_runner_identities_and_no_external_model():
    environment = os.environ.copy()
    environment.update(
        {
            "GOOGLE_API_KEY": "must-not-be-used",
            "GOOGLE_CLOUD_PROJECT": "must-not-be-used",
        }
    )
    completed = subprocess.run(
        (
            str(GRAPHENE),
            "demo",
            "--driver",
            "adk-fake",
            "--no-open",
            "--speed",
            "1000",
            "--exit-after-demo",
            "--automated-fixture",
        ),
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert LABEL in completed.stdout
    assert "Google ADK Runner: real Google ADK 2.5.0" in completed.stdout
    assert "External model dispatches: 0" in completed.stdout
    assert "Gemini calls: 0" in completed.stdout
    runtime = Path(
        next(
            line.removeprefix("Private runtime: ")
            for line in completed.stdout.splitlines()
            if line.startswith("Private runtime: ")
        )
    )
    database = runtime / "lineage.sqlite3"
    try:
        assert b"must-not-be-used" not in database.read_bytes()
        artifacts = SQLiteArtifactStore(database, read_only=True)
        checkpoints = SQLiteCheckpointRecorder(database, read_only=True)
        store = SQLiteLineageStore(
            database,
            artifact_resolver=artifacts.resolve,
            checkpoint_reader=checkpoints.read,
            read_only=True,
        )
        run_ids = tuple(
            path.name
            for path in sorted((runtime / "checkouts").iterdir())
            if path.is_dir()
        )
        assert len(run_ids) == 2
        events = {
            run_id: store.tail(run_id, 0, 256)
            for run_id in run_ids
        }
        assert all(isinstance(store.verify(run_id), VerifiedHead) for run_id in run_ids)
        invocations = tuple(
            (run_id, event)
            for run_id, lineage in events.items()
            for event in lineage
            if event.event_type == LineageEventType.INVOCATION_STARTED
        )
        assert len(invocations) == 2
        assert len({event.session_id for _, event in invocations}) == 2
        assert len({event.invocation_id for _, event in invocations}) == 2
        assert all(
            event.authority == LineageAuthority.ADK_ADAPTER
            and event.source_ref.kind == SourceKind.ADK_EVENT_RECEIPT
            and event.payload
            == {
                "adapter_kind": "adk",
                "framework": "google_adk",
                "framework_version": "2.5.0",
                "status": "started",
            }
            for _, event in invocations
        )
        local_result = next(
            event
            for lineage in events.values()
            for event in lineage
            if event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
        )
        checkout = runtime / "checkouts" / local_result.run_id
        subprocess.run(
            (
                "git",
                "cat-file",
                "-e",
                f"{local_result.payload['local_commit_sha']}^{{commit}}",
            ),
            cwd=checkout,
            check=True,
        )
    finally:
        shutil.rmtree(runtime, ignore_errors=True)
