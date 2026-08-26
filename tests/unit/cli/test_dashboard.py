"""Dashboard frames are proven against a real projection snapshot; only the
follow-loop sequencing and the blocked-state mapping use snapshot-shaped stubs,
because a real mid-poll status change and a real blocked task cost far more
store choreography than they prove.
"""

from __future__ import annotations

import io
import re
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

from graphene.orchestration.mission_projection import MissionProjectionError

from graphene.cli.dashboard import (
    GEMINI_3_5_FLASH_USD_PER_TOKEN,
    Frame,
    build_frame,
    follow,
    render_frame,
    render_plain,
    spend_from_receipts,
)
from graphene.orchestration.mission_models import AttemptResult, TaskKind
from graphene.orchestration.mission_projection import MissionProjection
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore
from tests.unit.orchestration.test_store import (
    NOW,
    _artifacts,
    _command,
    _create,
    _register_worker,
    _success,
    _task_for_snapshot,
)

_ANSI = re.compile(r"\x1b\[")


@pytest.fixture(scope="module")
def mid_mission_snapshot(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """One accepted task, one retrying task, two untouched dependents."""
    store = SQLiteMissionStore(tmp_path_factory.mktemp("dashboard") / "m.sqlite")
    _create(store)
    _register_worker(store, "worker-all", capabilities=tuple(sorted(TaskKind)))
    store.refresh_ready("mission-1", _command("dash-ready"), recorded_at=NOW)
    failed = store.claim_task(
        "mission-1",
        "work-a",
        "worker-all",
        _command("dash-claim-a"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    store.complete_attempt(
        "mission-1",
        failed.attempt_id,
        failed.worker_id,
        failed.lease_id,
        failed.fencing_token,
        AttemptResult(succeeded=False, retryable=True, result_code="retryable"),
        _command("dash-fail-a"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=60,
    )
    done = store.claim_task(
        "mission-1",
        "work-b",
        "worker-all",
        _command("dash-claim-b"),
        recorded_at=NOW + timedelta(seconds=1),
        ttl_seconds=30,
    )
    store.complete_attempt(
        "mission-1",
        done.attempt_id,
        done.worker_id,
        done.lease_id,
        done.fencing_token,
        _success(done, _task_for_snapshot(store, "work-b"), _artifacts(store)),
        _command("dash-done-b"),
        recorded_at=NOW + timedelta(seconds=2),
        retry_backoff_seconds=0,
    )
    return MissionProjection(store).snapshot("mission-1")


def _stub_snapshot(
    status: str = "running",
    tasks: tuple[SimpleNamespace, ...] | None = None,
    *,
    needs_you: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        mission=SimpleNamespace(
            goal="Stub goal",
            status=status,
            plan_revision=2,
            plan_sha256="a" * 64,
            approved_plan_revision=2,
        ),
        tasks=tasks
        if tasks is not None
        else (
            SimpleNamespace(
                task_id="assemble",
                state="blocked",
                dependency_ids=("work-a",),
                blocker_reason=None,
            ),
        ),
        attempts=(),
        needs_you=needs_you,
        result=SimpleNamespace(summary="isolated commit pending"),
    )


def _receipt(
    prompt: int | None, candidate: int | None, thought: int | None
) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=prompt, candidate_tokens=candidate, thought_tokens=thought
    )


def test_header_shows_goal_status_elapsed_and_receipt_spend(
    mid_mission_snapshot: Any,
) -> None:
    spend = spend_from_receipts(
        [_receipt(100_000, 10_000, 5_000)],
        price_per_token=GEMINI_3_5_FLASH_USD_PER_TOKEN,
    )
    assert spend == pytest.approx(0.29)  # 0.285 rounded UP to the cent
    frame = build_frame(
        mid_mission_snapshot, elapsed_seconds=102.4, spend_usd=spend, latest=None
    )
    header = render_plain(frame).splitlines()[0]
    assert header.startswith("GOAL Implement the bounded missi")
    assert header.endswith(" | STATUS running | ELAPSED 01:42 | SPEND $0.29")
    assert len(header) <= 80  # the goal yields, the vitals never do


def test_spend_rounds_up_per_receipt_not_per_total() -> None:
    receipts = [_receipt(100_000, 10_000, 5_000), _receipt(1, 0, None)]
    spend = spend_from_receipts(
        receipts, price_per_token=GEMINI_3_5_FLASH_USD_PER_TOKEN
    )
    assert spend == pytest.approx(0.30)  # 0.29 + 0.01, each receipt ceiled alone


def test_spend_is_em_dash_when_no_receipt(mid_mission_snapshot: Any) -> None:
    assert spend_from_receipts([], price_per_token=(1.0, 1.0)) is None
    assert (
        spend_from_receipts(
            [_receipt(None, None, None)], price_per_token=(1.0, 1.0)
        )
        is None
    )
    frame = build_frame(
        mid_mission_snapshot, elapsed_seconds=0.0, spend_usd=None, latest=None
    )
    plain = render_plain(frame)
    assert "SPEND —" in plain
    assert "$0.00" not in plain


def test_rows_keep_plan_order_and_show_attempt_and_fence(
    mid_mission_snapshot: Any,
) -> None:
    frame = build_frame(
        mid_mission_snapshot,
        elapsed_seconds=0.0,
        spend_usd=None,
        latest="check failed (schema) -> retry authorized",
    )
    assert [row.task_id for row in frame.rows] == [
        "assemble",
        "verify",
        "work-a",
        "work-b",
    ]
    lines = render_plain(frame).splitlines()
    retrying = next(line for line in lines if line.startswith("work-a"))
    assert "↻ retrying" in retrying
    assert "attempt 1" in retrying and "fence 1" in retrying
    accepted = next(line for line in lines if line.startswith("work-b"))
    assert "✓ accepted" in accepted
    untouched = next(line for line in lines if line.startswith("assemble"))
    assert "attempt —" in untouched and "fence —" in untouched
    assert lines[-2] == "Latest: check failed (schema) -> retry authorized"
    assert lines[-1] == "Result: No final result decision has been committed."


def test_blocked_task_renders_ring_and_no_attempt() -> None:
    frame = build_frame(
        _stub_snapshot(), elapsed_seconds=3723.0, spend_usd=None, latest=None
    )
    assert frame.rows[0].glyph == "○" and frame.rows[0].state == "blocked"
    assert frame.rows[0].attempt == 0 and frame.rows[0].fence == 0
    plain = render_plain(frame)
    assert "○ blocked" in plain and "attempt —" in plain
    assert "ELAPSED 01:02:03" in plain  # HH:MM:SS past an hour


def test_render_plain_has_no_ansi_and_fits_80_columns(
    mid_mission_snapshot: Any,
) -> None:
    frame = build_frame(
        mid_mission_snapshot,
        elapsed_seconds=61.0,
        spend_usd=0.31,
        latest="x" * 200,
    )
    plain = render_plain(frame)
    assert _ANSI.search(plain) is None
    assert max(len(line) for line in plain.splitlines()[:-2]) <= 80


def test_render_frame_is_a_rich_renderable(mid_mission_snapshot: Any) -> None:
    frame = build_frame(
        mid_mission_snapshot, elapsed_seconds=1.0, spend_usd=None, latest=None
    )
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    console.print(render_frame(frame))
    output = console.file.getvalue()
    assert "GOAL " in output and "attempt 1" in output


class _SeqProjection:
    """Replays canned snapshots; holds the last one once the tape runs out."""

    def __init__(self, snapshots: list[SimpleNamespace]) -> None:
        self._snapshots = snapshots

    def snapshot(self, mission_id: str) -> SimpleNamespace:
        assert mission_id == "mission-1"
        if len(self._snapshots) > 1:
            return self._snapshots.pop(0)
        return self._snapshots[0]


def _follow(projection: _SeqProjection, sleeper=None) -> tuple[Frame, list[float], str]:
    ticks = iter(range(1000))
    sleeps: list[float] = []
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    frame = follow(
        projection,
        "mission-1",
        console=console,
        spend=lambda _snapshot: None,
        latest=lambda _snapshot: None,
        clock=lambda: float(next(ticks)),
        sleeper=sleeper if sleeper is not None else sleeps.append,
    )
    return frame, sleeps, console.file.getvalue()


def test_follow_polls_via_sleeper_and_stops_at_terminal_status() -> None:
    projection = _SeqProjection(
        [_stub_snapshot("running"), _stub_snapshot("running"), _stub_snapshot("completed")]
    )
    frame, sleeps, _output = _follow(projection)
    assert frame.status == "completed"
    assert sleeps == [0.25, 0.25]


def test_follow_prints_only_changed_frames_when_piped() -> None:
    projection = _SeqProjection(
        [_stub_snapshot("running"), _stub_snapshot("running"), _stub_snapshot("completed")]
    )
    _frame, _sleeps, output = _follow(projection)
    # Second running frame differs only in elapsed: printed once, not twice.
    assert output.count("GOAL ") == 2
    assert output.count("STATUS running") == 1
    assert output.count("STATUS completed") == 1


def test_follow_keyboard_interrupt_returns_last_frame() -> None:
    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    projection = _SeqProjection([_stub_snapshot("running")])
    frame, _sleeps, output = _follow(projection, sleeper=interrupt)
    assert frame.status == "running"
    assert output.count("GOAL ") == 1


def test_follow_stops_when_the_mission_needs_a_person() -> None:
    """A mission awaiting the operator will not advance on its own: stop, do not poll.

    Caught against a real completed mission — `awaiting_result` is not a terminal
    MissionStatus, so the first `--follow` polled forever after the work was done.
    """
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    projection = _SeqProjection(
        [_stub_snapshot("awaiting_result"), _stub_snapshot("awaiting_result")]
    )
    slept: list[float] = []

    frame = follow(
        projection,
        "mission-1",
        console=console,
        spend=lambda _s: None,
        latest=lambda _s: None,
        clock=lambda: 0.0,
        sleeper=slept.append,
    )

    assert frame.waiting is True
    assert frame.status == "awaiting_result"
    assert slept == []

    gated = follow(
        _SeqProjection([_stub_snapshot("running", needs_you=object())]),
        "mission-1",
        console=console,
        spend=lambda _s: None,
        latest=lambda _s: None,
        clock=lambda: 0.0,
        sleeper=slept.append,
    )
    assert gated.waiting is True
    assert slept == []


class _ScriptedProjection:
    """Replays a script of snapshots and MissionProjectionErrors, in order."""

    def __init__(self, script: list[object]) -> None:
        self._script = script
        self.calls = 0

    def snapshot(self, mission_id: str) -> SimpleNamespace:
        self.calls += 1
        step = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        if isinstance(step, Exception):
            raise step
        return step


def test_follow_rides_out_a_projection_caught_mid_write() -> None:
    """A live mission writes two SQLite files; a poll can land between them.

    Caught by a real rehearsal of `graphene demo --live`, which died with
    "mission materialized state changed during validation" while the mission was
    still running. The projection is right to refuse a half-state; a dashboard
    polling a moving store must expect it and keep the last good frame.
    """
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    error = MissionProjectionError("mission materialized state changed")
    projection = _ScriptedProjection(
        [
            _stub_snapshot("running"),
            error,
            error,
            error,
            _stub_snapshot("completed"),
        ]
    )
    slept: list[float] = []

    frame = follow(
        projection,
        "mission-1",
        console=console,
        spend=lambda _s: None,
        latest=lambda _s: None,
        clock=lambda: 0.0,
        sleeper=slept.append,
    )

    assert frame.status == "completed"
    assert projection.calls == 5
    # Three transient polls plus the loop's own tick between frames.
    assert len(slept) == 4


def test_follow_surfaces_a_projection_error_that_never_clears() -> None:
    """Transient is forgiven; permanent is not. A corrupted store still shouts."""
    console = Console(file=io.StringIO(), force_terminal=False, width=100)
    error = MissionProjectionError("mission materialized state changed")

    # Failing on the very first poll has no last-good frame to keep: it raises.
    with pytest.raises(MissionProjectionError):
        follow(
            _ScriptedProjection([error]),
            "mission-1",
            console=console,
            spend=lambda _s: None,
            latest=lambda _s: None,
            clock=lambda: 0.0,
            sleeper=lambda _s: None,
        )

    # And a failure that never clears eventually raises rather than spinning.
    with pytest.raises(MissionProjectionError):
        follow(
            _ScriptedProjection([_stub_snapshot("running"), error]),
            "mission-1",
            console=console,
            spend=lambda _s: None,
            latest=lambda _s: None,
            clock=lambda: 0.0,
            sleeper=lambda _s: None,
        )


def test_follow_reopens_a_projection_that_quarantined_itself() -> None:
    """Caught by a live rehearsal that died mid-mission with a traceback.

    `MissionProjection` refuses a mission for the rest of its life once it has
    seen inconsistent evidence. That is right for a viewer and fatal for the
    follow loop's ride-it-out budget, which otherwise spends every retry on the
    same sticky refusal. Reopening re-runs every check on a fresh instance, so
    a transient mid-write race recovers — and evidence that is genuinely bad is
    refused again, because nothing about the check is skipped.
    """

    class _PoisonsItself:
        """One good snapshot, then quarantined for good, like the real thing."""

        def __init__(self) -> None:
            self.calls = 0
            self.poisoned = False

        def snapshot(self, mission_id: str) -> Any:
            self.calls += 1
            if self.poisoned:
                raise MissionProjectionError("mission evidence is quarantined")
            self.poisoned = True
            return _stub_snapshot("running")

    def run(projection, reopen) -> Frame:
        return follow(
            projection,
            "mission-1",
            console=Console(file=io.StringIO(), force_terminal=False, width=100),
            spend=lambda snapshot: None,
            latest=lambda snapshot: None,
            clock=lambda: 0.0,
            sleeper=lambda seconds: None,
            poll_seconds=0,
            reopen=reopen,
        )

    reopened: list[_SeqProjection] = []

    def reopen() -> _SeqProjection:
        healthy = _SeqProjection([_stub_snapshot("completed")])
        reopened.append(healthy)
        return healthy

    frame = run(_PoisonsItself(), reopen)
    assert frame.status == "completed"
    assert reopened, "the loop must reopen rather than retry the same refusal"

    # Without `reopen`, the retry budget is spent on the identical refusal.
    with pytest.raises(MissionProjectionError):
        run(_PoisonsItself(), None)
