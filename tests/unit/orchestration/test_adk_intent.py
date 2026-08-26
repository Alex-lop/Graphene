from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from graphene.orchestration.adk_planner import (
    AdkPlanner,
    PlanIntent,
    describe_output_schema,
    PlannerOutputError,
    PlanningExcerpt,
    PlanningRequest,
    WorkIntent,
    compile_plan_intent,
    criterion_id,
    planning_context_sha256,
)
from graphene.orchestration.mission_models import TaskKind
from pydantic import PrivateAttr

from .test_adk import _contracts


class _IntentLlm(BaseLlm):
    _raw: str = PrivateAttr()
    _schema: object = PrivateAttr(default=None)
    _prompt: str = PrivateAttr(default="")
    _calls: int = PrivateAttr(default=0)

    def bind(self, intent: PlanIntent) -> None:
        self._raw = intent.model_dump_json()

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        assert stream is False
        self._calls += 1
        self._schema = llm_request.config.system_instruction
        self._prompt = "".join(
            part.text or ""
            for content in llm_request.contents
            for part in content.parts or ()
        )
        yield LlmResponse(
            model_version=self.model,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=self._raw)],
            ),
        )


def _intent() -> PlanIntent:
    return PlanIntent(
        mission_id="mission-001",
        revision=1,
        tasks=(
            WorkIntent(
                task_id="code",
                title="Implement change",
                contract="Implement the bounded source change.",
                criterion_ids=(criterion_id("The bound test passes."),),
                assigned_role="implementer",
                read_paths=("src/change.py",),
                write_paths=("src/change.py",),
                command_template_id="unit-check",
                priority=20,
            ),
            WorkIntent(
                task_id="tests",
                title="Add tests",
                contract="Add focused coverage for the bounded source change.",
                criterion_ids=(criterion_id("The bound test passes."),),
                assigned_role="implementer",
                read_paths=("tests/test_change.py",),
                write_paths=("tests/test_change.py",),
                command_template_id="unit-check",
                priority=10,
            ),
        ),
    )


def test_intent_is_compiled_with_bounded_context_and_adk_owned_ids() -> None:
    policy, _ = _contracts()
    request = PlanningRequest(
        mission_id="mission-001",
        revision=1,
        goal="Implement the bounded outcome.",
        success_criteria=("The bound test passes.",),
        session_id="caller-session",
        invocation_id="caller-invocation",
        repository_manifest=("src/change.py", "tests/test_change.py"),
        repository_excerpts=(
            PlanningExcerpt(
                path="src/change.py",
                start_line=1,
                text="def change():\n    return False\n",
            ),
        ),
    )
    intent = _intent()
    fake = _IntentLlm(model="fixture-model")
    fake.bind(intent)

    proposal = asyncio.run(AdkPlanner.fake(fake).propose(policy, request))

    assert describe_output_schema(PlanIntent) in (fake._schema or "")
    assert "src/change.py" in fake._prompt
    assert "return False" in fake._prompt
    assert proposal.plan == compile_plan_intent(policy, request, intent)
    assert tuple(task.task_id for task in proposal.plan.tasks) == (
        "assemble",
        "code",
        "tests",
        "verify",
    )
    assembly = proposal.plan.tasks[0]
    verification = proposal.plan.tasks[-1]
    assert assembly.kind == TaskKind.ASSEMBLY
    assert assembly.dependencies == ("code", "tests")
    assert verification.kind == TaskKind.VERIFICATION
    assert verification.dependencies == ("assemble",)
    assert proposal.plan.criteria[0].criterion_id == criterion_id(
        "The bound test passes."
    )
    assert proposal.plan.criteria[0].producer_task_ids == ("code", "tests")
    assert proposal.plan.max_concurrency == 2
    assert proposal.receipt.session_id != request.session_id
    assert proposal.receipt.invocation_id != request.invocation_id
    assert proposal.receipt.invocation_id.startswith("e-")
    assert proposal.receipt.planning_context_sha256 == planning_context_sha256(
        request
    )
    assert "return False" not in proposal.receipt.model_dump_json()


def test_repository_context_outside_policy_is_rejected_before_the_model() -> None:
    policy, _ = _contracts()
    request = PlanningRequest(
        mission_id="mission-001",
        revision=1,
        goal="Implement the bounded outcome.",
        success_criteria=("The bound test passes.",),
        repository_manifest=("private/secret.py",),
    )
    fake = _IntentLlm(model="fixture-model")
    fake.bind(_intent())

    with pytest.raises(PlannerOutputError, match="outside policy"):
        asyncio.run(AdkPlanner.fake(fake).propose(policy, request))
    assert fake._calls == 0


def test_compiler_rejects_uncovered_or_unknown_criterion_ids() -> None:
    policy, _ = _contracts()
    request = PlanningRequest(
        mission_id="mission-001",
        revision=1,
        goal="Implement the bounded outcome.",
        success_criteria=("The bound test passes.",),
    )
    intent = _intent()
    first = intent.tasks[0].model_copy(update={"criterion_ids": ("criterion-other",)})
    invalid = intent.model_copy(update={"tasks": (first, intent.tasks[1])})

    with pytest.raises(PlannerOutputError, match="coverage is incomplete"):
        compile_plan_intent(policy, request, invalid)


def test_sanitized_validation_detail_names_locations_and_types_only() -> None:
    from graphene.orchestration.adk_planner import PlanIntent, sanitized_validation_detail

    secret_looking = "AIza" + "x" * 35
    try:
        PlanIntent.model_validate_json(
            '{"mission_id": "%s", "revision": 0, "tasks": []}' % secret_looking
        )
    except ValueError as error:
        detail = sanitized_validation_detail(error)
    else:  # pragma: no cover - the input above is invalid by construction
        raise AssertionError("expected a validation error")

    assert secret_looking not in detail
    assert "revision:greater_than_equal" in detail
    assert "tasks:too_short" in detail
    assert sanitized_validation_detail(ValueError("plain")) == "ValueError"


def test_live_model_ordering_is_canonicalized_not_rejected() -> None:
    from graphene.orchestration.adk_planner import PlanIntent

    def work(task_id: str, write: str, deps: list[str]) -> dict:
        return {
            "task_id": task_id,
            "title": "t",
            "contract": "c",
            "criterion_ids": ["criterion-2", "criterion-1", "criterion-2"],
            "dependencies": deps,
            "assigned_role": "worker",
            "read_paths": ["ledger_service/cli.py", "README.md"],
            "write_paths": [write, "tests/test_" + write.split("/")[-1]],
            "command_template_id": "fixture-tests",
        }

    intent = PlanIntent.model_validate(
        {
            "mission_id": "mission-1",
            "revision": 1,
            "tasks": [
                work("zeta", "ledger_service/z.py", []),
                work("alpha", "ledger_service/a.py", []),
                work("tail", "ledger_service/cli.py", ["zeta", "alpha"]),
            ],
        }
    )

    assert [item.task_id for item in intent.tasks] == ["alpha", "tail", "zeta"]
    assert intent.tasks[0].criterion_ids == ("criterion-1", "criterion-2")
    assert intent.tasks[0].read_paths == ("README.md", "ledger_service/cli.py")
    assert intent.tasks[1].dependencies == ("alpha", "zeta")
