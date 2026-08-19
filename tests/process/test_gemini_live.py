from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest
from graphene.orchestration.adk import (
    LIVE_GEMINI_MODEL,
    AdkPlanner,
    PlanningRequest,
)
from graphene.orchestration.scripted import load_scenario
from graphene.orchestration.validation import require_valid_plan


@pytest.mark.skipif(
    os.environ.get("GRAPHENE_RUN_LIVE_GEMINI") != "1",
    reason=(
        "NOT PROVEN: set GRAPHENE_RUN_LIVE_GEMINI=1 with valid Gemini credentials "
        "to run the real ADK/Gemini smoke"
    ),
)
def test_real_gemini_proposes_a_valid_bounded_plan() -> None:
    scenario = load_scenario()
    policy, mission, _ = scenario.contracts(
        mission_id="gemini-live-smoke",
        repo_id="taskmaster-live-fixture",
        base_sha="a" * 40,
        created_at=datetime.now(UTC),
    )
    proposal = asyncio.run(
        AdkPlanner.live().propose(
            policy,
            PlanningRequest(
                mission_id=mission.mission_id,
                revision=1,
                goal=mission.goal,
                success_criteria=mission.success_criteria,
                session_id="gemini-live-session",
                invocation_id="gemini-live-invocation",
                timeout_seconds=120,
            ),
        )
    )

    assert proposal.receipt.driver == "gemini_live"
    assert proposal.receipt.requested_model == LIVE_GEMINI_MODEL
    assert proposal.receipt.model_call_count == 1
    assert proposal.receipt.telemetry_content_capture == "NO_CONTENT"
    assert require_valid_plan(policy, proposal.plan).valid is True
