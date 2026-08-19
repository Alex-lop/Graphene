from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.runners import Runner
from google.genai import types
from graphene.orchestration.adk import (
    LIVE_GEMINI_MODEL,
    AdkPlanner,
    PlannerOutputError,
    PlannerUnavailable,
    PlanningRequest,
    planning_input_sha256,
)
from graphene.hashing import canonical_json_sha256
from graphene.orchestration.models import (
    ArtifactContract,
    ArtifactRequirement,
    CommandTemplate,
    NetworkPolicy,
    Plan,
    ProjectPolicy,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
)
from pydantic import PrivateAttr


def _contracts() -> tuple[ProjectPolicy, Plan]:
    policy = ProjectPolicy(
        policy_id="policy-001",
        revision=1,
        repo_id="repo-001",
        base_ref="main",
        base_sha="a" * 40,
        allowed_read_globs=("src/**", "tests/**"),
        allowed_write_globs=("src/**", "tests/**"),
        exclusions=(),
        command_templates=(
            CommandTemplate(
                template_id="unit-check",
                argv=("python", "-m", "pytest", "-q"),
                timeout_seconds=30,
            ),
        ),
        network=NetworkPolicy(),
        agent_roles=("assembler", "implementer", "verifier"),
        max_concurrency=2,
        retry_limit=1,
        resource_budget=ResourceBudget(
            max_worker_seconds=120,
            max_attempts=8,
            max_artifact_bytes=1_048_576,
        ),
        retention=RetentionPolicy(retain_days=7),
    )
    tasks = (
        Task(
            task_id="assemble",
            title="Assemble",
            contract="Assemble the accepted implementation artifact.",
            kind=TaskKind.ASSEMBLY,
            dependencies=("implement",),
            assigned_role="assembler",
            read_paths=("src/**", "tests/**"),
            allowed_commands=("unit-check",),
            inputs=(
                ArtifactRequirement(
                    producer_task_id="implement",
                    name="implementation",
                    kind="patch",
                ),
            ),
            expected_outputs=(
                ArtifactContract(name="candidate", kind="patch"),
            ),
            acceptance_checks=("unit-check",),
            priority=10,
            attempt_limit=2,
        ),
        Task(
            task_id="implement",
            title="Implement",
            contract="Implement the bounded change and its tests.",
            assigned_role="implementer",
            read_paths=("src/**", "tests/**"),
            write_paths=("src/change.py", "tests/test_change.py"),
            allowed_commands=("unit-check",),
            expected_outputs=(
                ArtifactContract(
                    name="implementation",
                    kind="patch",
                    paths=("src/change.py", "tests/test_change.py"),
                ),
            ),
            acceptance_checks=("unit-check",),
            priority=20,
            attempt_limit=2,
        ),
        Task(
            task_id="verify",
            title="Verify",
            contract="Verify the assembled candidate with the bound check.",
            kind=TaskKind.VERIFICATION,
            dependencies=("assemble",),
            assigned_role="verifier",
            read_paths=("src/**", "tests/**"),
            allowed_commands=("unit-check",),
            inputs=(
                ArtifactRequirement(
                    producer_task_id="assemble",
                    name="candidate",
                    kind="patch",
                ),
            ),
            expected_outputs=(
                ArtifactContract(name="verification", kind="receipt"),
            ),
            acceptance_checks=("unit-check",),
            priority=0,
            attempt_limit=2,
        ),
    )
    return policy, Plan(
        mission_id="mission-001",
        revision=1,
        tasks=tasks,
        max_concurrency=2,
    )


def _request(*, goal: str = "Implement the bounded outcome.") -> PlanningRequest:
    return PlanningRequest(
        mission_id="mission-001",
        revision=1,
        goal=goal,
        success_criteria=("The bound test passes.",),
        session_id="session-001",
        invocation_id="invocation-001",
    )


class _PlanLlm(BaseLlm):
    _raw: str = PrivateAttr()
    _returned_model: str = PrivateAttr()
    _calls: int = PrivateAttr(default=0)
    _saw_schema: bool = PrivateAttr(default=False)
    _last_temperature: float | None = PrivateAttr(default=None)

    def bind(self, raw: str, *, returned_model: str | None = None) -> None:
        self._raw = raw
        self._returned_model = returned_model or self.model

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        assert stream is False
        self._calls += 1
        self._saw_schema = llm_request.config.response_schema is not None
        self._last_temperature = llm_request.config.temperature
        yield LlmResponse(
            model_version=self._returned_model,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=self._raw)],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=101,
                candidates_token_count=202,
                total_token_count=303,
            ),
        )


def test_fake_uses_real_runner_typed_output_and_sanitized_receipt(monkeypatch) -> None:
    policy, plan = _contracts()
    fake = _PlanLlm(model="fixture-model")
    fake.bind(plan.model_dump_json())
    captured_run_configs = []
    original = Runner.run_async

    async def recording_run(self, **kwargs):
        captured_run_configs.append(kwargs["run_config"])
        async for event in original(self, **kwargs):
            yield event

    monkeypatch.setattr(Runner, "run_async", recording_run)
    request = _request(goal="Implement canary-secret-goal without leaking it.")

    proposal = asyncio.run(AdkPlanner.fake(fake).propose(policy, request))

    assert proposal.plan == plan
    assert fake._calls == 1
    assert fake._saw_schema is True
    assert fake._last_temperature is None
    assert proposal.receipt.driver == "adk_fake"
    assert proposal.receipt.mission_id == request.mission_id
    assert proposal.receipt.revision == request.revision
    assert proposal.receipt.plan_sha256 == canonical_json_sha256(
        plan.model_dump(mode="json")
    )
    assert proposal.receipt.planning_input_sha256 == planning_input_sha256(
        policy,
        mission_id=request.mission_id,
        revision=request.revision,
        goal=request.goal,
        success_criteria=request.success_criteria,
    )
    assert proposal.receipt.truth_kind == "model_proposed"
    assert proposal.receipt.provider_usage.source == "unavailable"
    assert proposal.receipt.provider_usage.total_tokens is None
    assert captured_run_configs[0].max_llm_calls == 1
    telemetry = captured_run_configs[0].telemetry
    assert telemetry.resolved_content_capturing_mode.value == "NO_CONTENT"
    assert telemetry.should_add_content_to_legacy_spans is False
    receipt = proposal.receipt.model_dump_json()
    assert "canary-secret-goal" not in receipt
    assert "python" not in receipt
    assert "Implement the bounded change" not in receipt


def test_invalid_or_mismatched_model_output_is_rejected() -> None:
    policy, plan = _contracts()
    wrong_identity = plan.model_copy(update={"mission_id": "mission-other"})
    fake = _PlanLlm(model="fixture-model")
    fake.bind(wrong_identity.model_dump_json())
    with pytest.raises(PlannerOutputError, match="output identity mismatch"):
        asyncio.run(AdkPlanner.fake(fake).propose(policy, _request()))

    mismatch = _PlanLlm(model="fixture-model")
    mismatch.bind(plan.model_dump_json(), returned_model="different-model")
    with pytest.raises(PlannerOutputError, match="model identity mismatch"):
        asyncio.run(AdkPlanner.fake(mismatch).propose(policy, _request()))


def test_live_credentials_are_preflighted_without_fallback() -> None:
    with pytest.raises(PlannerUnavailable, match="exactly one"):
        AdkPlanner.live(environ={})
    with pytest.raises(PlannerUnavailable, match="explicit model"):
        AdkPlanner.live(model="gemini-2.5-flash", environ={"GOOGLE_API_KEY": "x"})
    with pytest.raises(PlannerUnavailable, match="exactly one"):
        AdkPlanner.live(
            environ={"GOOGLE_API_KEY": "x", "GEMINI_API_KEY": "y"}
        )

    assert isinstance(
        AdkPlanner.live(environ={"GOOGLE_API_KEY": "not-recorded"}),
        AdkPlanner,
    )
    probes = []
    assert isinstance(
        AdkPlanner.live(
            environ={
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
                "GOOGLE_CLOUD_PROJECT": "project",
                "GOOGLE_CLOUD_LOCATION": "us-central1",
            },
            adc_probe=lambda: probes.append(True),
        ),
        AdkPlanner,
    )
    assert probes == [True]
    assert LIVE_GEMINI_MODEL == "gemini-3.5-flash"


def test_ambient_telemetry_override_fails_before_model_call(monkeypatch) -> None:
    policy, plan = _contracts()
    fake = _PlanLlm(model="fixture-model")
    fake.bind(plan.model_dump_json())
    monkeypatch.setenv("ADK_TELEMETRY_IGNORE_RUN_CONFIG", "true")

    with pytest.raises(PlannerUnavailable, match="NO_CONTENT"):
        asyncio.run(AdkPlanner.fake(fake).propose(policy, _request()))
    assert fake._calls == 0
