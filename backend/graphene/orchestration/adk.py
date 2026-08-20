from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import PurePosixPath
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
from pydantic import Field, field_validator, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256
from ..models import BoundedText, FrozenModel, Identifier, RepoPath, Sha256
from .models import (
    ArtifactContract,
    ArtifactRequirement,
    Criterion,
    CriterionVerificationKind,
    Plan,
    ProjectPolicy,
    Task,
    TaskKind,
)
from .validation import PlanValidationError, require_valid_plan

ADK_VERSION = "2.5.0"
LIVE_GEMINI_MODEL = "gemini-3.5-flash"
_APP_NAME = "graphene-taskmaster"
_AGENT_NAME = "graphene_planner"
_USER_ID = "graphene-planner"
_TELEMETRY_LOCK = "ADK_TELEMETRY_IGNORE_RUN_CONFIG"
_ASSEMBLY_TASK_ID = "assemble"
_VERIFICATION_TASK_ID = "verify"
_MAX_EXCERPT_BYTES = 4_096
_MAX_EXCERPTS_BYTES = 32_768


class PlannerError(RuntimeError):
    pass


class PlannerUnavailable(PlannerError):
    pass


class PlannerOutputError(PlannerError):
    pass


class PlanningExcerpt(FrozenModel):
    path: RepoPath
    start_line: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=_MAX_EXCERPT_BYTES)

    @field_validator("text")
    @classmethod
    def text_is_bounded_utf8(cls, value: str) -> str:
        if "\x00" in value or len(value.encode("utf-8")) > _MAX_EXCERPT_BYTES:
            raise ValueError("repository excerpt exceeds its UTF-8 byte limit")
        return value


class PlanningRequest(FrozenModel):
    mission_id: Identifier
    revision: int = Field(ge=1)
    goal: BoundedText
    success_criteria: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)
    # Kept as optional caller correlation hints for API compatibility. ADK owns
    # the actual session and invocation identities recorded in the receipt.
    session_id: Identifier | None = None
    invocation_id: Identifier | None = None
    repository_manifest: tuple[RepoPath, ...] = Field(default=(), max_length=512)
    repository_excerpts: tuple[PlanningExcerpt, ...] = Field(
        default=(), max_length=16
    )
    timeout_seconds: float = Field(default=60, gt=0, le=300)

    @model_validator(mode="after")
    def criteria_are_canonical(self) -> PlanningRequest:
        if self.success_criteria != tuple(sorted(set(self.success_criteria))):
            raise ValueError("success criteria must be sorted and unique")
        if self.repository_manifest != tuple(sorted(set(self.repository_manifest))):
            raise ValueError("repository manifest must be sorted and unique")
        if any(
            any(character in path for character in "*?[")
            for path in self.repository_manifest
        ):
            raise ValueError("repository manifest paths must be exact")
        excerpt_keys = tuple(
            (item.path, item.start_line) for item in self.repository_excerpts
        )
        if excerpt_keys != tuple(sorted(excerpt_keys)) or len(excerpt_keys) != len(
            set(excerpt_keys)
        ):
            raise ValueError("repository excerpts must be sorted and unique")
        if any(
            item.path not in self.repository_manifest
            for item in self.repository_excerpts
        ):
            raise ValueError("repository excerpt path is absent from the manifest")
        if (
            sum(len(item.text.encode("utf-8")) for item in self.repository_excerpts)
            > _MAX_EXCERPTS_BYTES
        ):
            raise ValueError("repository excerpts exceed their total byte limit")
        return self


class WorkIntent(FrozenModel):
    task_id: Identifier
    title: BoundedText
    contract: BoundedText
    criterion_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    dependencies: tuple[Identifier, ...] = Field(default=(), max_length=64)
    assigned_role: Identifier
    read_paths: tuple[RepoPath, ...] = Field(min_length=1, max_length=256)
    write_paths: tuple[RepoPath, ...] = Field(min_length=1, max_length=128)
    command_template_id: Identifier
    priority: int = Field(default=0, ge=-1_000, le=1_000)

    @model_validator(mode="after")
    def collections_are_canonical(self) -> WorkIntent:
        collections = (
            self.criterion_ids,
            self.dependencies,
            self.read_paths,
            self.write_paths,
        )
        if any(items != tuple(sorted(set(items))) for items in collections):
            raise ValueError("work intent collections must be sorted and unique")
        if self.task_id in self.dependencies:
            raise ValueError("work intent cannot depend on itself")
        if any(
            any(character in path for character in "*?[")
            for path in self.write_paths
        ):
            raise ValueError("work intent write paths must be exact")
        return self


class PlanIntent(FrozenModel):
    mission_id: Identifier
    revision: int = Field(ge=1)
    tasks: tuple[WorkIntent, ...] = Field(min_length=2, max_length=254)

    @model_validator(mode="after")
    def graph_is_bounded_and_canonical(self) -> PlanIntent:
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(task_ids)) or len(task_ids) != len(set(task_ids)):
            raise ValueError("work intents must have sorted unique task IDs")
        if {_ASSEMBLY_TASK_ID, _VERIFICATION_TASK_ID} & set(task_ids):
            raise ValueError("work intent uses a reserved task ID")
        known = set(task_ids)
        if any(set(item.dependencies) - known for item in self.tasks):
            raise ValueError("work intent dependency is absent")
        roots = tuple(item for item in self.tasks if not item.dependencies)
        if len(roots) < 2:
            raise ValueError("plan intent requires at least two independent work roots")
        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if set(left.write_paths) & set(right.write_paths):
                    raise ValueError("independent work roots have overlapping writes")
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


def planning_context_sha256(request: PlanningRequest) -> str:
    return canonical_json_sha256(
        {
            "repository_excerpts": tuple(
                item.model_dump(mode="json") for item in request.repository_excerpts
            ),
            "repository_manifest": request.repository_manifest,
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
    planning_context_sha256: Sha256 | None = None
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
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.calls = 0
        self.invocation_ids: set[str] = set()
        self.returned_models: set[str] = set()
        self.usage: types.GenerateContentResponseUsageMetadata | None = None

    def after_model(
        self,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> None:
        if (
            callback_context.session.id != self.session_id
            or callback_context.agent_name != _AGENT_NAME
        ):
            raise PlannerOutputError("ADK planner callback identity mismatch")
        self.invocation_ids.add(callback_context.invocation_id)
        self.calls += 1
        if llm_response.model_version:
            self.returned_models.add(llm_response.model_version)
        if llm_response.usage_metadata is not None:
            self.usage = llm_response.usage_metadata
        return None

    def observe_invocation(self, invocation_id: str | None) -> None:
        if invocation_id:
            self.invocation_ids.add(invocation_id)

    def invocation_id(self) -> str:
        if len(self.invocation_ids) != 1:
            raise PlannerOutputError("ADK invocation identity is ambiguous")
        return next(iter(self.invocation_ids))


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

        _validate_repository_context(policy, request)
        message = _planning_message(policy, request)
        sessions = InMemorySessionService()
        session = await sessions.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
        )
        observation = _Observation(session.id)
        agent = LlmAgent(
            name=_AGENT_NAME,
            description="Proposes bounded work intent for deterministic compilation.",
            model=self._model,
            instruction=(
                "Return only a PlanIntent matching the response schema. Propose at least "
                "two independent work roots, using only supplied roles, command template "
                "and criterion IDs, and repository evidence. Graphene deterministically adds assembly, "
                "verification, artifacts, retries, and concurrency."
            ),
            output_schema=PlanIntent,
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
                    session_id=session.id,
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
                    observation.observe_invocation(event.invocation_id)
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
                session_id=session.id,
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
            intent = PlanIntent.model_validate_json(raw_output)
            plan = compile_plan_intent(policy, request, intent)
        except ValueError:
            if self._driver != "adk_fake":
                raise PlannerOutputError(
                    "ADK planner output does not match PlanIntent"
                ) from None
            # Compatibility for existing injected fakes. Live Gemini must always
            # return the narrower intent schema.
            try:
                plan = Plan.model_validate_json(raw_output)
            except ValueError:
                raise PlannerOutputError(
                    "ADK planner output does not match PlanIntent"
                ) from None
        if plan.mission_id != request.mission_id or plan.revision != request.revision:
            raise PlannerOutputError("ADK planner output identity mismatch")
        if tuple(sorted(item.description for item in plan.criteria)) != (
            request.success_criteria
        ):
            raise PlannerOutputError("ADK planner criterion coverage mismatch")
        try:
            require_valid_plan(policy, plan)
        except PlanValidationError as error:
            raise PlannerOutputError(f"compiled plan is invalid: {error}") from None

        invocation_id = observation.invocation_id()

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
                planning_context_sha256=planning_context_sha256(request),
                requested_model=self._requested_model,
                returned_model=_canonical_model(returned_model),
                session_id=session.id,
                invocation_id=invocation_id,
                credential_mode=self._credential_mode,
                input_bytes=len(message.encode("utf-8")),
                output_bytes=len(raw_output.encode("utf-8")),
                provider_usage=usage,
            ),
        )


def compile_plan_intent(
    policy: ProjectPolicy,
    request: PlanningRequest,
    intent: PlanIntent,
) -> Plan:
    """Compile model judgment into Graphene-owned task and artifact boilerplate."""

    if intent.mission_id != request.mission_id or intent.revision != request.revision:
        raise PlannerOutputError("ADK planner output identity mismatch")
    roles = set(policy.agent_roles)
    if "assembler" not in roles or "verifier" not in roles:
        raise PlannerOutputError("policy requires assembler and verifier roles")
    templates = {item.template_id for item in policy.command_templates}
    if any(item.assigned_role not in roles for item in intent.tasks):
        raise PlannerOutputError("work intent role is not allowed")
    if any(item.command_template_id not in templates for item in intent.tasks):
        raise PlannerOutputError("work intent command is not allowed")
    criterion_descriptions = {
        criterion_id(description): description for description in request.success_criteria
    }
    referenced_criteria = {
        criterion_id for item in intent.tasks for criterion_id in item.criterion_ids
    }
    if referenced_criteria != set(criterion_descriptions):
        raise PlannerOutputError("work intent criterion coverage is incomplete")

    artifact_names = {
        item.task_id: f"work-{canonical_json_sha256(item.task_id)[:24]}"
        for item in intent.tasks
    }
    attempt_limit = policy.retry_limit + 1
    work_tasks = []
    for item in intent.tasks:
        inputs = tuple(
            ArtifactRequirement(
                producer_task_id=dependency,
                name=artifact_names[dependency],
                kind="patch",
            )
            for dependency in item.dependencies
        )
        work_tasks.append(
            Task(
                task_id=item.task_id,
                title=item.title,
                contract=item.contract,
                dependencies=item.dependencies,
                assigned_role=item.assigned_role,
                read_paths=item.read_paths,
                write_paths=item.write_paths,
                allowed_commands=(item.command_template_id,),
                inputs=inputs,
                expected_outputs=(
                    ArtifactContract(
                        name=artifact_names[item.task_id],
                        kind="patch",
                        paths=item.write_paths,
                    ),
                ),
                acceptance_checks=(item.command_template_id,),
                priority=item.priority,
                attempt_limit=attempt_limit,
            )
        )

    shared_read_paths = tuple(
        sorted(
            {
                path
                for item in intent.tasks
                for path in (*item.read_paths, *item.write_paths)
            }
        )
    )
    default_check = policy.command_templates[0].template_id
    deterministic_semantics = (
        policy.command_templates[0].argv
        in {
            ("python", "-m", "pytest", "-q"),
            ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
        }
        and policy.command_templates[0].cwd is None
    ) or (
        # Legacy policies without a typed final gate remain compatible; the
        # default real policy does declare final-result and therefore cannot
        # turn its structural git-diff check into a semantic success claim.
        "final-result" not in policy.risk_gates
    )
    criteria = tuple(
        Criterion(
            criterion_id=criterion_id,
            description=description,
            producer_task_ids=tuple(
                item.task_id
                for item in intent.tasks
                if criterion_id in item.criterion_ids
            ),
            verification_kind=(
                CriterionVerificationKind.DETERMINISTIC_CHECK
                if deterministic_semantics
                else CriterionVerificationKind.HUMAN_GATE
            ),
            verifier_task_id=(
                _VERIFICATION_TASK_ID if deterministic_semantics else None
            ),
            verifier_id=default_check if deterministic_semantics else "final-result",
        )
        for criterion_id, description in sorted(criterion_descriptions.items())
    )
    assembly_inputs = tuple(
        ArtifactRequirement(
            producer_task_id=item.task_id,
            name=artifact_names[item.task_id],
            kind="patch",
        )
        for item in intent.tasks
    )
    assembly = Task(
        task_id=_ASSEMBLY_TASK_ID,
        title="Assemble candidate",
        contract="Assemble every accepted work artifact into one candidate patch.",
        kind=TaskKind.ASSEMBLY,
        dependencies=tuple(item.task_id for item in intent.tasks),
        assigned_role="assembler",
        read_paths=shared_read_paths,
        allowed_commands=(default_check,),
        inputs=assembly_inputs,
        expected_outputs=(ArtifactContract(name="candidate", kind="patch"),),
        acceptance_checks=(default_check,),
        priority=-1,
        attempt_limit=attempt_limit,
    )
    verification = Task(
        task_id=_VERIFICATION_TASK_ID,
        title="Verify candidate",
        contract="Verify the assembled candidate with the policy-bound check.",
        kind=TaskKind.VERIFICATION,
        dependencies=(_ASSEMBLY_TASK_ID,),
        assigned_role="verifier",
        read_paths=shared_read_paths,
        allowed_commands=(default_check,),
        inputs=(
            ArtifactRequirement(
                producer_task_id=_ASSEMBLY_TASK_ID,
                name="candidate",
                kind="patch",
            ),
        ),
        expected_outputs=(
            ArtifactContract(name="verification", kind="test-receipt"),
        ),
        acceptance_checks=(default_check,),
        priority=-2,
        attempt_limit=attempt_limit,
    )
    plan = Plan(
        mission_id=request.mission_id,
        revision=request.revision,
        previous_revision=request.revision - 1 if request.revision > 1 else None,
        criteria=criteria,
        tasks=tuple(
            sorted(
                (*work_tasks, assembly, verification), key=lambda task: task.task_id
            )
        ),
        max_concurrency=min(policy.max_concurrency, len(intent.tasks)),
    )
    try:
        require_valid_plan(policy, plan)
    except PlanValidationError as error:
        raise PlannerOutputError(f"compiled plan is invalid: {error}") from None
    return plan


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


def _validate_repository_context(
    policy: ProjectPolicy, request: PlanningRequest
) -> None:
    for path in request.repository_manifest:
        candidate = PurePosixPath(path)
        allowed = any(
            candidate.full_match(pattern) for pattern in policy.allowed_read_globs
        )
        excluded = any(candidate.full_match(pattern) for pattern in policy.exclusions)
        if not allowed or excluded:
            raise PlannerOutputError("repository context is outside policy")


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
        "success_criteria": tuple(
            {
                "criterion_id": criterion_id(description),
                "description": description,
            }
            for description in request.success_criteria
        ),
        "policy": policy_view,
        "repository_evidence": {
            "manifest": request.repository_manifest,
            "excerpts": tuple(
                item.model_dump(mode="json") for item in request.repository_excerpts
            ),
        },
    }
    return canonical_json_bytes(payload).decode("utf-8")


def criterion_id(description: str) -> str:
    return f"criterion-{canonical_json_sha256(description)[:24]}"


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
