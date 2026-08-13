from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from google.genai import types

from graphene.bootstrap import bootstrap_local_run
from graphene.cli.main import main
from graphene.hashing import canonical_json_bytes
from graphene.integrations.adk import AdkRuntimeAdapter
from graphene.lineage.service import RuntimeIdentityError
from graphene.models import LineageEventType

ROOT = Path(__file__).parents[2]
CANARY = "PRIVATE_PROVIDER_MODEL_CANARY_8f63a7"


class _CanaryRunner:
    async def run_async(self, **kwargs):
        del kwargs
        yield SimpleNamespace(model_version=CANARY)


def test_provider_model_metadata_never_reaches_durable_or_public_bytes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    run = bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )
    adapter = AdkRuntimeAdapter(run.service, run.handle, agent_name="graphene_agent")

    async def invoke() -> tuple[list[object], Exception | None]:
        observed: list[object] = []
        try:
            observed = [
                event
                async for event in adapter.run_async(
                    _CanaryRunner(),
                    user_id="graphene-user",
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Execute now.")],
                    ),
                )
            ]
        except Exception as error:  # noqa: BLE001 - trust-boundary result under test
            return observed, error
        return observed, None

    observed, error = asyncio.run(invoke())
    assert observed == []
    assert isinstance(error, RuntimeIdentityError)
    assert CANARY not in str(error)

    events = run.store.tail(run.run_id, 0, 256)
    assert events[-1].event_type == LineageEventType.INVOCATION_FAILED
    public_bytes = b"\n".join(
        canonical_json_bytes(event.model_dump(mode="json")) for event in events
    )
    assert CANARY.encode() not in public_bytes

    with sqlite3.connect(run.database_path) as connection:
        artifact_bytes = b"\n".join(
            row[0]
            for row in connection.execute(
                "SELECT artifact_bytes FROM lineage_artifacts ORDER BY artifact_id"
            )
        )
    assert CANARY.encode() not in artifact_bytes

    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(run.database_path))
    assert main(["inspect", events[-1].event_id, "--run", run.run_id]) == 0
    output = capsys.readouterr()
    assert CANARY not in output.out
    assert CANARY not in output.err
