"""Live mission dashboard: one frame per poll, rendered rich or plain.

The frame is a plain value so rendering and the follow loop stay separately
testable; the clock and sleeper are injected so tests never sleep.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.table import Table
from rich.text import Text

from ..orchestration.models import MissionStatus
from ..orchestration.projection import MissionProjectionError
from .render import _fit

# Paid-tier published price for gemini-3.5-flash, USD per token as
# (input, output). Thinking tokens bill as output tokens.
GEMINI_3_5_FLASH_USD_PER_TOKEN = (1.50 / 1e6, 9.00 / 1e6)

# Projection task state -> (human word, glyph).
_STATES: dict[str, tuple[str, str]] = {
    "done": ("accepted", "✓"),
    "running": ("running", "●"),
    "verifying": ("running", "●"),
    "retrying": ("retrying", "↻"),
    "blocked": ("blocked", "○"),
    "needs_input": ("blocked", "○"),
    "queued": ("queued", "○"),
    "ready": ("queued", "○"),
    "failed": ("failed", "✗"),
    "cancelled": ("failed", "✗"),
}

# A live mission writes to two SQLite files, so a poll can land between the two
# writes and the projection refuses the half-state. That is correct of the
# projection and transient for a dashboard: keep the last good frame, poll
# again, and only surface it when it stops being transient.
_MAX_TRANSIENT_POLLS = 40

_TERMINAL: frozenset[str] = frozenset(
    status.value
    for status in (
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
        MissionStatus.REJECTED,
    )
)


@dataclass(frozen=True, slots=True)
class TaskRow:
    task_id: str
    state: str
    glyph: str
    attempt: int
    fence: int


@dataclass(frozen=True, slots=True)
class Frame:
    goal: str
    status: str
    elapsed_seconds: float
    spend_usd: float | None
    rows: tuple[TaskRow, ...]
    latest: str | None
    result: str
    # The mission cannot advance without a person: a gate is open, or it is
    # awaiting the final decision. Following past this point is just polling.
    waiting: bool = False


def spend_from_receipts(
    receipts: Iterable[Any], *, price_per_token: tuple[float, float]
) -> float | None:
    """Receipts are the only cost evidence: no usable receipt means unknown,
    never $0.00. Rounded up per receipt so a paid call is never under-reported.
    """
    input_price, output_price = price_per_token
    total: float | None = None
    for receipt in receipts:
        tokens = (
            receipt.prompt_tokens,
            receipt.candidate_tokens,
            receipt.thought_tokens,
        )
        if all(item is None for item in tokens):
            continue
        prompt, candidate, thought = (item or 0 for item in tokens)
        cost = prompt * input_price + (candidate + thought) * output_price
        total = (total or 0.0) + math.ceil(cost * 100) / 100
    return total


def build_frame(
    snapshot: Any,
    *,
    elapsed_seconds: float,
    spend_usd: float | None,
    latest: str | None,
) -> Frame:
    """Reduce a MissionControlSnapshot to the few values the terminal shows."""
    latest_attempts: dict[str, tuple[int, int]] = {}
    for attempt in snapshot.attempts:
        current = latest_attempts.get(attempt.task_id)
        if current is None or attempt.number > current[0]:
            latest_attempts[attempt.task_id] = (attempt.number, attempt.fencing_token)
    rows = tuple(
        TaskRow(
            task_id=task.task_id,
            state=_STATES.get(task.state, (task.state, "○"))[0],
            glyph=_STATES.get(task.state, (task.state, "○"))[1],
            attempt=latest_attempts.get(task.task_id, (0, 0))[0],
            fence=latest_attempts.get(task.task_id, (0, 0))[1],
        )
        for task in snapshot.tasks
    )
    return Frame(
        goal=snapshot.mission.goal,
        status=snapshot.mission.status,
        elapsed_seconds=elapsed_seconds,
        spend_usd=spend_usd,
        rows=rows,
        latest=latest,
        result=snapshot.result.summary,
        waiting=(
            snapshot.needs_you is not None
            or snapshot.mission.status == MissionStatus.AWAITING_RESULT.value
        ),
    )


def _elapsed(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _header(frame: Frame) -> str:
    spend = "—" if frame.spend_usd is None else f"${frame.spend_usd:.2f}"
    tail = (
        f" | STATUS {frame.status}"
        f" | ELAPSED {_elapsed(frame.elapsed_seconds)}"
        f" | SPEND {spend}"
    )
    # The goal yields so the whole header stays readable at 80 columns.
    return "GOAL " + _fit(frame.goal, max(8, 80 - 5 - len(tail))) + tail


def _cells(row: TaskRow) -> tuple[str, str, str, str]:
    return (
        row.task_id,
        f"{row.glyph} {row.state}",
        f"attempt {row.attempt or '—'}",
        f"fence {row.fence or '—'}",
    )


def render_frame(frame: Frame) -> RenderableType:
    table = Table(box=None, show_header=False, pad_edge=False)
    for row in frame.rows:
        table.add_row(*_cells(row))
    return Group(
        Text(_header(frame)),
        table,
        Text(f"Latest: {frame.latest or '—'}"),
        Text(f"Result: {frame.result}"),
    )


def render_plain(frame: Frame) -> str:
    """ANSI-free rendering for pipes and tests: one line per element."""
    width = max((len(row.task_id) for row in frame.rows), default=0)
    lines = [_header(frame)]
    for row in frame.rows:
        task_id, state, attempt, fence = _cells(row)
        lines.append(f"{task_id:<{width}}  {state:<10}  {attempt}  {fence}")
    lines.append(f"Latest: {frame.latest or '—'}")
    lines.append(f"Result: {frame.result}")
    return "\n".join(lines)


def _finished(frame: Frame, stop: Callable[[], bool] | None) -> bool:
    return (
        frame.status in _TERMINAL
        or frame.waiting
        or (stop is not None and stop())
    )


def follow(
    projection: Any,
    mission_id: str,
    *,
    console: Console,
    spend: Callable[[object], float | None],
    latest: Callable[[object], str | None],
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    poll_seconds: float = 0.25,
    stop: Callable[[], bool] | None = None,
) -> Frame:
    """Poll until the mission is terminal; Ctrl-C hands back the last frame."""
    started = clock()
    transient = 0

    def _poll(previous: Frame | None) -> Frame:
        """One frame, tolerating a projection caught mid-write."""
        nonlocal transient
        while True:
            try:
                snapshot = projection.snapshot(mission_id)
            except MissionProjectionError:
                transient += 1
                if previous is None or transient > _MAX_TRANSIENT_POLLS:
                    raise
                sleeper(poll_seconds)
                continue
            transient = 0
            return build_frame(
                snapshot,
                elapsed_seconds=clock() - started,
                spend_usd=spend(snapshot),
                latest=latest(snapshot),
            )

    frame = _poll(None)
    try:
        if console.is_terminal:
            with Live(render_frame(frame), console=console) as live:
                while not _finished(frame, stop):
                    sleeper(poll_seconds)
                    frame = _poll(frame)
                    live.update(render_frame(frame), refresh=True)
        else:
            shown: Frame | None = None
            while True:
                # Elapsed alone is not news: piped output only grows on change.
                if shown is None or replace(frame, elapsed_seconds=0.0) != replace(
                    shown, elapsed_seconds=0.0
                ):
                    console.print(render_plain(frame))
                    shown = frame
                if _finished(frame, stop):
                    break
                sleeper(poll_seconds)
                frame = _poll(frame)
    except KeyboardInterrupt:
        pass
    return frame
