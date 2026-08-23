"""Provider-side receipt stamps: the second, Graphene-independent clock.

The runtime brackets every model call on its own clock. These tests prove the
worker also records what the provider said about the call (``response_id``,
server-side ``create_time``, the reply's HTTP ``Date``), that a receipt
without them still validates, and that overlap can be measured on the
provider's clock alone. No network: the SDK call is replaced by a stub.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from graphene.orchestration.overlap import (
    PROVIDER_REPORTED_BASIS,
    measure_overlap,
)
from graphene.orchestration.runtime import WorkerProviderReceipt
from graphene.orchestration.workers.gemini import (
    ProviderStamp,
    StampedGemini,
    provider_stamp,
)
from tests.unit.orchestration.test_overlap import _attempt, _receipt, _snapshot


def _response(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "response_id": "resp-abc123",
        "create_time": datetime(2026, 8, 23, 12, 0, 0, 250_000, tzinfo=UTC),
        "sdk_http_response": SimpleNamespace(
            headers={"Date": "Sun, 23 Aug 2026 12:00:03 GMT", "X-Other": "x"}
        ),
        "text": "never read",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_provider_stamp_reads_identifiers_and_instants_only() -> None:
    stamp = provider_stamp(_response())

    assert stamp == ProviderStamp(
        response_id="resp-abc123",
        create_time="2026-08-23T12:00:00.250Z",
        response_date="2026-08-23T12:00:03.000Z",
    )
    assert "text" not in stamp.model_dump()


@pytest.mark.parametrize(
    "overrides",
    [
        {"response_id": None, "create_time": None, "sdk_http_response": None},
        {"response_id": "", "create_time": "not-a-datetime"},
        {"response_id": "bad value!", "sdk_http_response": SimpleNamespace(headers=None)},
        {"create_time": datetime(2026, 8, 23, 12)},  # naive: refused
        {"sdk_http_response": SimpleNamespace(headers={"Date": "garbage"})},
    ],
)
def test_provider_stamp_is_absent_rather_than_wrong(overrides: dict) -> None:
    stamp = provider_stamp(_response(**overrides))

    for field, value in overrides.items():
        if field == "response_id":
            assert stamp.response_id is None
        elif field == "create_time":
            assert stamp.create_time is None
        else:
            assert stamp.response_date is None
    assert provider_stamp(object()) == ProviderStamp()


def test_stamped_gemini_records_one_stamp_per_call(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-never-sent")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    from google.genai import models as genai_models

    calls: list[dict[str, object]] = []

    async def fake_generate_content(self, **kwargs):  # noqa: ANN001
        calls.append(kwargs)
        return _response(response_id=f"resp-{len(calls)}")

    monkeypatch.setattr(
        genai_models.AsyncModels, "generate_content", fake_generate_content
    )
    model = StampedGemini(model="gemini-3.5-flash")
    assert model.stamps == ()

    async def run() -> None:
        client = model.api_client
        assert client is model.api_client  # cached: one wrapped client
        for _ in range(2):
            await client.aio.models.generate_content(
                model="gemini-3.5-flash", contents="x", config=None
            )

    asyncio.run(run())

    assert [stamp.response_id for stamp in model.stamps] == ["resp-1", "resp-2"]
    assert model.stamps[0].create_time == "2026-08-23T12:00:00.250Z"
    assert model.stamps[0].response_date == "2026-08-23T12:00:03.000Z"
    assert len(calls) == 2 and calls[0]["model"] == "gemini-3.5-flash"


def test_receipt_accepts_and_exposes_provider_window() -> None:
    bare = _receipt("2026-08-23T12:00:00.000Z", "2026-08-23T12:00:05.000Z")
    assert bare.provider_reported_window() is None
    assert bare.provider_response_id is None

    stamped = bare.model_copy(
        update={
            "provider_response_id": "resp-abc123",
            "provider_create_time": "2026-08-23T12:00:00.800Z",
            # Whole-second Date header may precede a sub-second create_time.
            "provider_response_date": "2026-08-23T12:00:00.000Z",
        }
    )
    stamped = WorkerProviderReceipt.model_validate(stamped.model_dump(mode="json"))
    window = stamped.provider_reported_window()
    assert window is not None and window[0] > window[1]

    with pytest.raises(ValueError):
        WorkerProviderReceipt.model_validate(
            {**bare.model_dump(mode="json"), "provider_response_id": "no spaces"}
        )


def _stamped(
    call_started: str, call_ended: str, create_time: str, response_date: str
) -> WorkerProviderReceipt:
    return WorkerProviderReceipt.model_validate(
        {
            **_receipt(call_started, call_ended).model_dump(mode="json"),
            "provider_response_id": "resp-" + create_time[-4:-1],
            "provider_create_time": create_time,
            "provider_response_date": response_date,
        }
    )


def test_overlap_measures_provider_reported_basis_on_the_provider_clock() -> None:
    snapshot = _snapshot(
        attempts=(
            _attempt("attempt-a", "work-a", "worker-a", 0, 6),
            _attempt("attempt-b", "work-b", "worker-b", 1, 7),
        )
    )
    # Provider clock deliberately offset from the runtime clock by a minute:
    # the reported basis must come from the provider stamps alone.
    measurement = measure_overlap(
        snapshot,
        provider_receipts={
            "attempt-a": _stamped(
                "2026-08-23T12:00:00.000Z",
                "2026-08-23T12:00:04.000Z",
                "2026-08-23T12:01:00.250Z",
                "2026-08-23T12:01:03.000Z",
            ),
            "attempt-b": _stamped(
                "2026-08-23T12:00:01.000Z",
                "2026-08-23T12:00:05.000Z",
                "2026-08-23T12:01:01.500Z",
                "2026-08-23T12:01:05.000Z",
            ),
        },
    )

    assert measurement.provider_call_observed is True
    assert measurement.provider_call_max_window_ms == 3000
    assert measurement.provider_reported_observed is True
    assert measurement.provider_reported_max_window_ms == 1500
    assert [(pair.basis, pair.window_ms) for pair in measurement.pairs][-1] == (
        PROVIDER_REPORTED_BASIS,
        1500,
    )
    assert "provider's own clock" in measurement.note

    # One unstamped receipt: the provider-call basis stays, the reported one
    # is simply absent rather than zero-claimed.
    partial = measure_overlap(
        snapshot,
        provider_receipts={
            "attempt-a": _receipt(
                "2026-08-23T12:00:00.000Z", "2026-08-23T12:00:04.000Z"
            ),
            "attempt-b": _stamped(
                "2026-08-23T12:00:01.000Z",
                "2026-08-23T12:00:05.000Z",
                "2026-08-23T12:01:01.500Z",
                "2026-08-23T12:01:05.000Z",
            ),
        },
    )
    assert partial.provider_call_observed is True
    assert partial.provider_reported_observed is False
    assert all(pair.basis != PROVIDER_REPORTED_BASIS for pair in partial.pairs)

    # Disjoint on the provider clock even though the runtime windows overlap:
    # the two clocks can disagree, and the measurement says so.
    disjoint = measure_overlap(
        snapshot,
        provider_receipts={
            "attempt-a": _stamped(
                "2026-08-23T12:00:00.000Z",
                "2026-08-23T12:00:04.000Z",
                "2026-08-23T12:01:00.000Z",
                "2026-08-23T12:01:01.000Z",
            ),
            "attempt-b": _stamped(
                "2026-08-23T12:00:01.000Z",
                "2026-08-23T12:00:05.000Z",
                "2026-08-23T12:01:02.000Z",
                "2026-08-23T12:01:03.000Z",
            ),
        },
    )
    assert disjoint.provider_call_observed is True
    assert disjoint.provider_reported_observed is False
    assert disjoint.provider_reported_max_window_ms == 0


def test_receipt_without_stamps_serializes_byte_identically_to_before() -> None:
    bare = _receipt("2026-08-23T12:00:00.000Z", "2026-08-23T12:00:05.000Z")
    dumped = bare.model_dump(mode="json")

    assert not {
        "provider_response_id",
        "provider_create_time",
        "provider_response_date",
    } & dumped.keys()
    assert WorkerProviderReceipt.model_validate(dumped) == bare
    stamped = _stamped(
        "2026-08-23T12:00:00.000Z",
        "2026-08-23T12:00:05.000Z",
        "2026-08-23T12:00:00.250Z",
        "2026-08-23T12:00:05.000Z",
    ).model_dump(mode="json")
    assert stamped["provider_create_time"] == "2026-08-23T12:00:00.250Z"


def test_rejected_worker_output_still_binds_its_provider_receipt(
    tmp_path, monkeypatch
) -> None:
    """A billed call whose output fails validation must not vanish from evidence."""

    from graphene.cli import mission as mission_cli
    from graphene.orchestration.models import AttemptState, TaskKind
    from graphene.orchestration.runtime import WORKER_PROVIDER_RECEIPT_KIND
    from graphene.orchestration.workers import FileMutation
    from tests.unit.orchestration.test_gemini_mission_runtime import (
        prepare_fake_two_worker_mission,
        quiet_resource_sampler,
    )

    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    # Worker B answers with a mutation outside its leased write path.
    prepared.model_b.bind(
        (
            FileMutation(
                operation="create",
                path=".graphene/generated/elsewhere.txt",
                text="nope\n",
                mode="100644",
            ),
        )
    )
    # policy_rejected is terminal, so the mission fails closed; the evidence
    # of the billed call must still be bound to the failed attempt.
    with pytest.raises(mission_cli.MissionCliError, match="failed closed"):
        mission_cli._execute_adk_mission(
            store=prepared.store,
            mission_id=prepared.mission_id,
            registry=prepared.registry,
            resource_sampler=quiet_resource_sampler,
        )
    snapshot = prepared.store.snapshot(prepared.mission_id)
    kinds = {task.task_id: task.kind for task in snapshot.tasks}
    rejected = [
        attempt
        for attempt in snapshot.attempts
        if kinds[attempt.task_id] == TaskKind.WORK
        and attempt.result_code == "policy_rejected"
    ]
    assert rejected, "worker B's out-of-lease mutation must be rejected"
    evidence = mission_cli._mission_evidence(prepared.store, prepared.mission_id)
    for attempt in rejected:
        assert attempt.state == AttemptState.FAILED
        receipts = [
            item
            for item in attempt.evidence_refs
            if item.kind == WORKER_PROVIDER_RECEIPT_KIND
        ]
        assert len(receipts) == 1
        content = evidence.resolve(receipts[0].kind, receipts[0].id)
        assert content is not None
        receipt = WorkerProviderReceipt.model_validate_json(content)
        assert receipt.driver == "adk_fake" and receipt.output_bytes >= 1


def test_malformed_model_reply_is_retried_under_a_higher_fence(
    tmp_path, monkeypatch
) -> None:
    """A reply that is not a WorkerIntent is a model failure, bounded by retry_limit."""

    from collections.abc import AsyncGenerator

    from google.adk.models import LlmRequest, LlmResponse
    from google.genai import types

    from graphene.cli import mission as mission_cli
    from graphene.orchestration.models import AttemptState, MissionStatus, TaskKind
    from graphene.orchestration.runtime import WORKER_PROVIDER_RECEIPT_KIND
    from graphene.orchestration.workers import DeterministicWorkerModel
    from tests.unit.orchestration.test_gemini_mission_runtime import (
        prepare_fake_two_worker_mission,
        quiet_resource_sampler,
    )

    class TaskAware(DeterministicWorkerModel):
        """Answers for whichever leased path the prompt names; garbles one reply."""

        garble_path: str | None = None

        async def generate_content_async(  # type: ignore[override]
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            prompt = "".join(
                part.text or ""
                for content in llm_request.contents
                for part in content.parts or ()
            )
            leased = [m for m in by_path if m in prompt]
            assert len(leased) == 1, leased
            self.bind((by_path[leased[0]],))
            if leased[0] == self.garble_path:
                self.garble_path = None
                self._calls += 1
                yield LlmResponse(
                    model_version=self.model,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="I cannot comply {")],
                    ),
                )
                return
            async for response in super().generate_content_async(llm_request, stream):
                yield response

    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    by_path = {
        m.path: m for m in (*prepared.model_a.mutations, *prepared.model_b.mutations)
    }
    path_b = prepared.model_b.mutations[0].path
    model_a = TaskAware(model="fixture-worker-a")
    model_b = TaskAware(model="fixture-worker-b", garble_path=path_b)
    from graphene.orchestration.runtime import WorkerRegistry
    from graphene.orchestration.workers import GeminiWorkerAdapter

    registry = WorkerRegistry(
        (
            GeminiWorkerAdapter.fake(worker_id="fake-a", model=model_a),
            GeminiWorkerAdapter.fake(worker_id="fake-b", model=model_b),
        )
    )
    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=registry,
        resource_sampler=quiet_resource_sampler,
    )
    assert result["status"] == MissionStatus.AWAITING_RESULT
    snapshot = prepared.store.snapshot(prepared.mission_id)
    kinds = {task.task_id: task.kind for task in snapshot.tasks}
    rejected = [
        a
        for a in snapshot.attempts
        if kinds[a.task_id] == TaskKind.WORK and a.result_code == "model_output_rejected"
    ]
    assert len(rejected) == 1 and rejected[0].state == AttemptState.FAILED
    retry = next(
        a
        for a in snapshot.attempts
        if a.task_id == rejected[0].task_id and a.attempt_number == 2
    )
    assert retry.state == AttemptState.COMMITTED
    assert retry.fencing_token > rejected[0].fencing_token
    assert any(r.kind == WORKER_PROVIDER_RECEIPT_KIND for r in rejected[0].evidence_refs)
