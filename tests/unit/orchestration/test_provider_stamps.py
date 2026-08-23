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
