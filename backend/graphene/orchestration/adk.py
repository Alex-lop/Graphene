from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from typing import Literal, Protocol

import google.adk
import google.auth
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.telemetry import ContentCapturingMode, TelemetryConfig
from google.genai import types
from pydantic import Field, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256
from ..models import BoundedText, FrozenModel, Identifier, Sha256
from .models import Plan, ProjectPolicy
from .validation import require_valid_plan

ADK_VERSION = "2.5.0"
LIVE_GEMINI_MODEL = "gemini-3.5-flash"
_APP_NAME = "graphene-taskmaster"
_AGENT_NAME = "graphene_planner"
_USER_ID = "graphene-planner"
_TELEMETRY_LOCK = "ADK_TELEMETRY_IGNORE_RUN_CONFIG"


class PlannerError(RuntimeError):
    pass


class PlannerUnavailable(PlannerError):
    pass


class PlannerOutputError(PlannerError):
    pass


class PlanningRequest(FrozenModel):
    mission_id: Identifier
    revision: int = Field(ge=1)
    goal: BoundedText
    success_criteria: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)
    session_id: Identifier
    invocation_id: Identifier
    timeout_seconds: float = Field(default=60, gt=0, le=300)

    @model_validator(mode="after")
    def criteria_are_canonical(self) -> PlanningRequest:
        if self.success_criteria != tuple(sorted(set(self.success_criteria))):
            raise ValueError("success criteria must be sorted and unique")
        return self


def planning_input_sha256(
    policy: ProjectPolicy,
    *,
    mission_id: str,
    revision: int,
    goal: str,
    success_criteria: Sequence[str],
) -> str:
    return canonical_json_sha256(
        {
            "goal": goal,
            "mission_id": mission_id,
            "policy": policy.model_dump(mode="json"),
            "revision": revision,
            "success_criteria": tuple(sorted(success_criteria)),
        }
    )


class ProviderUsage(FrozenModel):
    source: Literal["provider_reported", "unavailable"]
    prompt_tokens: int | None = Field(default=None, ge=0)
    candidate_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    tool_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def unavailable_has_no_claimed_counts(self) -> ProviderUsage:
        counts = (
            self.prompt_tokens,
            self.candidate_tokens,
            self.thought_tokens,
            self.tool_tokens,
            self.cached_tokens,
            self.total_tokens,
        )
        if self.source == "unavailable" and any(item is not None for item in counts):
            raise ValueError("unavailable provider usage cannot contain token counts")
        if self.source == "provider_reported" and all(item is None for item in counts):
            raise ValueError("provider-reported usage requires a reported count")
        return self


class PlanProposalReceipt(FrozenModel):
    schema_version: Literal[1] = 1
    truth_kind: Literal["model_proposed"] = "model_proposed"
    driver: Literal["adk_fake", "gemini_live"]
    framework: Literal["google_adk"] = "google_adk"
    framework_version: Literal[ADK_VERSION] = ADK_VERSION
    client: Literal["google_genai"] = "google_genai"
    client_version: str = Field(min_length=1, max_length=32)
    mission_id: Identifier
    revision: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_input_sha256: Sha256
    requested_model: Identifier
    returned_model: Identifier
    session_id: Identifier
    invocation_id: Identifier
    credential_mode: Literal["not_applicable", "gemini_api", "vertex_ai"]
    model_call_count: Literal[1] = 1
    input_bytes: int = Field(ge=1)
    output_bytes: int = Field(ge=1)
    telemetry_content_capture: Literal["NO_CONTENT"] = "NO_CONTENT"
    provider_usage: ProviderUsage


class PlanProposal(FrozenModel):
    plan: Plan
    receipt: PlanProposalReceipt


class Planner(Protocol):
    async def propose(
        self,
        policy: ProjectPolicy,
        request: PlanningRequest,
    ) -> PlanProposal: ...


class _Observation:
    def __init__(self, request: PlanningRequest) -> None:
        self.request = request
        self.calls = 0
        self.returned_models: set[str] = set()
        self.usage: types.GenerateContentResponseUsageMetadata | None = None

    def after_model(
        self,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> None:
        if (
            callback_context.session.id != self.request.session_id
            or callback_context.invocation_id != self.request.invocation_id
            or callback_context.agent_name != _AGENT_NAME
        ):
            raise PlannerOutputError("ADK planner callback identity mismatch")
        self.calls += 1
        if llm_response.model_version:
            self.returned_models.add(llm_response.model_version)
        if llm_response.usage_metadata is not None:
            self.usage = llm_response.usage_metadata
        return None


class AdkPlanner:
    """One-turn typed planner. The Graphene validator remains authoritative."""

    def __init__(
        self,
        *,
        model: BaseLlm | str,
        driver: Literal["adk_fake", "gemini_live"],
        credential_mode: Literal["not_applicable", "gemini_api", "vertex_ai"],
    ) -> None:
        if google.adk.__version__ != ADK_VERSION:
            raise PlannerUnavailable(
                f"Google ADK {ADK_VERSION} is required; found {google.adk.__version__}"
            )
        self._model = model
        self._driver = driver
        self._credential_mode = credential_mode
        self._requested_model = model.model if isinstance(model, BaseLlm) else model

    @classmethod
    def fake(cls, model: BaseLlm) -> AdkPlanner:
        """Inject a deterministic BaseLlm while still exercising the real Runner."""

        return cls(model=model, driver="adk_fake", credential_mode="not_applicable")

    @classmethod
    def live(
        cls,
        *,
        model: str = LIVE_GEMINI_MODEL,
        environ: Mapping[str, str] | None = None,
        adc_probe: Callable[[], object] | None = None,
    ) -> AdkPlanner:
        if model != LIVE_GEMINI_MODEL:
            raise PlannerUnavailable(
                f"live planning requires the explicit model {LIVE_GEMINI_MODEL}"
            )
        credential_mode = _credential_preflight(
            os.environ if environ is None else environ,
            adc_probe=adc_probe,
        )
        return cls(
            model=model,
            driver="gemini_live",
            credential_mode=credential_mode,
        )

    async def propose(
        self,
        policy: ProjectPolicy,
        request: PlanningRequest,
    ) -> PlanProposal:
        if os.environ.get(_TELEMETRY_LOCK, "").strip().lower() in {"1", "true"}:
            raise PlannerUnavailable(
                "ADK telemetry policy override prevents NO_CONTENT enforcement"
            )

        message = _planning_message(policy, request)
        observation = _Observation(request)
        agent = LlmAgent(
            name=_AGENT_NAME,
            description="Produces a model-proposed task DAG for deterministic validation.",
            model=self._model,
            instruction=(
                "Return only a Plan matching the response schema. Use only the supplied "
                "policy identifiers and scopes. The result is a proposal and must include "
                "one assembly task and one downstream verification task."
            ),
            output_schema=Plan,
            include_contents="none",
            tools=[],
            mode="chat",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(
                max_output_tokens=8_192,
            ),
            after_model_callback=observation.after_model,
        )
        sessions = InMemorySessionService()
        await sessions.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=request.session_id,
        )
        runner = Runner(
            app_name=_APP_NAME,
            agent=agent,
            session_service=sessions,
        )
        output_parts: list[str] = []
        try:
            async with asyncio.timeout(request.timeout_seconds):
                async for event in runner.run_async(
                    user_id=_USER_ID,
                    session_id=request.session_id,
                    invocation_id=request.invocation_id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=message)],
                    ),
                    run_config=RunConfig(
                        max_llm_calls=1,
                        telemetry=TelemetryConfig(
                            capture_message_content=ContentCapturingMode.NO_CONTENT
                        ),
                    ),
                ):
                    if event.author != _AGENT_NAME or not event.is_final_response():
                        continue
                    for part in event.content.parts if event.content else ():
                        if part.text and not part.thought:
                            output_parts.append(part.text)
        except PlannerError:
            raise
        except TimeoutError:
            raise PlannerUnavailable(
                "ADK planner exceeded its wall-time limit"
            ) from None
        except Exception:
            raise PlannerUnavailable("ADK planner execution failed") from None
        finally:
            await sessions.delete_session(
                app_name=_APP_NAME,
                user_id=_USER_ID,
                session_id=request.session_id,
            )

        if observation.calls != 1:
            raise PlannerOutputError("ADK planner did not make exactly one model call")
        if len(observation.returned_models) != 1:
            raise PlannerOutputError("ADK returned model identity is ambiguous")
        returned_model = next(iter(observation.returned_models))
        if _canonical_model(returned_model) != _canonical_model(self._requested_model):
            raise PlannerOutputError("ADK returned model identity mismatch")
        raw_output = "".join(output_parts).strip()
        if not raw_output:
            raise PlannerOutputError("ADK planner returned no typed output")
        try:
            plan = Plan.model_validate_json(raw_output)
        except ValueError:
            raise PlannerOutputError("ADK planner output does not match Plan") from None
        if plan.mission_id != request.mission_id or plan.revision != request.revision:
            raise PlannerOutputError("ADK planner output identity mismatch")
        require_valid_plan(policy, plan)

        usage = _provider_usage(
            observation.usage, authoritative=self._driver == "gemini_live"
        )
        return PlanProposal(
            plan=plan,
            receipt=PlanProposalReceipt(
                driver=self._driver,
                client_version=version("google-genai"),
                mission_id=request.mission_id,
                revision=request.revision,
                plan_sha256=canonical_json_sha256(plan.model_dump(mode="json")),
                planning_input_sha256=planning_input_sha256(
                    policy,
                    mission_id=request.mission_id,
                    revision=request.revision,
                    goal=request.goal,
                    success_criteria=request.success_criteria,
                ),
                requested_model=self._requested_model,
                returned_model=_canonical_model(returned_model),
                session_id=request.session_id,
                invocation_id=request.invocation_id,
                credential_mode=self._credential_mode,
                input_bytes=len(message.encode("utf-8")),
                output_bytes=len(raw_output.encode("utf-8")),
                provider_usage=usage,
            ),
        )


def _credential_preflight(
    environ: Mapping[str, str],
    *,
    adc_probe: Callable[[], object] | None,
) -> Literal["gemini_api", "vertex_ai"]:
    vertex = environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
    api_keys = tuple(
        name for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY") if environ.get(name)
    )
    if vertex in {"1", "true"}:
        missing = [
            name
            for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
            if not environ.get(name)
        ]
        if missing:
            raise PlannerUnavailable(
                "Vertex AI credentials require GOOGLE_CLOUD_PROJECT and "
                "GOOGLE_CLOUD_LOCATION"
            )
        probe = adc_probe or google.auth.default
        try:
            probe()
        except Exception:
            raise PlannerUnavailable(
                "Vertex AI application default credentials are unavailable"
            ) from None
        return "vertex_ai"
    if vertex not in {"", "0", "false"}:
        raise PlannerUnavailable("GOOGLE_GENAI_USE_VERTEXAI has an invalid value")
    if len(api_keys) != 1:
        raise PlannerUnavailable(
            "Gemini API planning requires exactly one of GOOGLE_API_KEY or GEMINI_API_KEY"
        )
    return "gemini_api"


def _canonical_model(model: str) -> str:
    return model.removeprefix("models/")


def _planning_message(policy: ProjectPolicy, request: PlanningRequest) -> str:
    policy_view = {
        "policy_id": policy.policy_id,
        "policy_revision": policy.revision,
        "repository_id": policy.repo_id,
        "allowed_read_globs": policy.allowed_read_globs,
        "allowed_write_globs": policy.allowed_write_globs,
        "exclusions": policy.exclusions,
        "command_template_ids": tuple(
            item.template_id for item in policy.command_templates
        ),
        "network_mode": policy.network.mode.value,
        "allowed_network_hosts": policy.network.allowed_hosts,
        "agent_roles": policy.agent_roles,
        "max_concurrency": policy.max_concurrency,
        "retry_limit": policy.retry_limit,
        "resource_budget": policy.resource_budget.model_dump(mode="json"),
        "risk_gates": policy.risk_gates,
    }
    payload = {
        "mission_id": request.mission_id,
        "revision": request.revision,
        "previous_revision": request.revision - 1 if request.revision > 1 else None,
        "goal": request.goal,
        "success_criteria": request.success_criteria,
        "policy": policy_view,
    }
    return canonical_json_bytes(payload).decode("utf-8")


def _provider_usage(
    usage: types.GenerateContentResponseUsageMetadata | None,
    *,
    authoritative: bool,
) -> ProviderUsage:
    if not authoritative or usage is None:
        return ProviderUsage(source="unavailable")
    counts = (
        usage.prompt_token_count,
        usage.candidates_token_count,
        usage.thoughts_token_count,
        usage.tool_use_prompt_token_count,
        usage.cached_content_token_count,
        usage.total_token_count,
    )
    if all(value is None for value in counts):
        return ProviderUsage(source="unavailable")
    return ProviderUsage(
        source="provider_reported",
        prompt_tokens=counts[0],
        candidate_tokens=counts[1],
        thought_tokens=counts[2],
        tool_tokens=counts[3],
        cached_tokens=counts[4],
        total_tokens=counts[5],
    )
