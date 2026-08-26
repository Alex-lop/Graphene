from __future__ import annotations

from pathlib import Path

import pytest
from graphene.bootstrap import bootstrap_local_run
from graphene.lineage.lineage_reducer import ProjectionError, reduce_events
from graphene.lineage.service import RuntimeServiceError, ToolCallIdentity
from graphene.core_models import VerifiedHead

ROOT = Path(__file__).parents[2]


def _call(run, call_id: str) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.model_id,
        tool_call_id=call_id,
        agent_name="graphene_agent_b",
        adapter_kind="local",
    )


def test_stale_read_cannot_be_overwritten_after_external_same_path_mutation(
    tmp_path: Path,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    run = bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )
    path = "app/auth/limiter.py"
    target = run.checkout_root / path
    observed = run.service.read_file(
        run.handle,
        _call(run, "agent_b_read_001"),
        path=path,
    )
    externally_mutated = observed.content.replace(
        "MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 6"
    )
    stale_write = observed.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4")
    target.write_text(externally_mutated)

    try:
        run.service.write_file(
            run.handle,
            _call(run, "agent_b_stale_write_001"),
            path=path,
            content=stale_write,
        )
    except RuntimeServiceError:
        assert target.read_text() == externally_mutated
        return

    verified = run.store.verify(run.run_id)
    assert isinstance(verified, VerifiedHead)
    with pytest.raises(ProjectionError, match="file-version lineage"):
        reduce_events(run.store.tail(run.run_id, 0, verified.seq))
    assert target.read_text() == stale_write
    pytest.fail(
        "stale Agent-B write mutated checkout and committed an unreducible stream"
    )
