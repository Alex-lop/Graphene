"""Generate the synthetic ``session_v1.ndjson`` fixture with real digests.

Run from the repository root with ``uv run --frozen python
tests/fixtures/shadow/ndjson/generate_session_v1.py``. The session is
invented, not recorded: every event is built with ``ShadowEvent.create`` so
the committed ``event_id`` values are the real canonical digests, and the
output is deterministic so the test suite can regenerate it and compare.

The stream deliberately contains, in this order: a user prompt; edits to
three repository paths (``app/greet.py``, ``app/config.py``,
``tests/test_greet.py``); a passing ``pytest`` check that follows the first two
edits; a second user prompt and a ``TodoWrite`` plan marker; a ``uv sync``
install; an ``rm`` whose ``file_delete`` is inferred from the command and is
never followed by a check; a later edit to the third path with no check
after it; a second edit to ``app/greet.py`` from the later segment; a
``curl`` network call; a write to ``.env``; one ``unknown`` record; a commit;
and a closing agent message "All tests pass." after the last edit. It carries
no ``claim`` records, so ingest runs the ``claims.v1`` matcher itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.shadow.events import ShadowEvent
from graphene.shadow.redaction import (
    COMMAND_EXCERPT_LIMIT,
    MESSAGE_EXCERPT_LIMIT,
    bounded_excerpt,
)

SESSION_ID = "fixture-session-v1"
SOURCE_ADAPTER = "fixture-emitter"
SOURCE_ADAPTER_VERSION = "0.1.0"
OUTPUT = Path(__file__).with_name("session_v1.ndjson")


class _Builder:
    def __init__(self) -> None:
        self.events: list[ShadowEvent] = []

    def add(self, raw_type: str, **fields: object) -> ShadowEvent:
        seq = len(self.events) + 1
        record: dict[str, object] = {
            "session_id": SESSION_ID,
            "seq": seq,
            "provenance": "observed",
            "source": {
                "adapter": SOURCE_ADAPTER,
                "adapter_version": SOURCE_ADAPTER_VERSION,
                "record_ref": f"line:{seq}",
                "raw_type": raw_type,
            },
        }
        record.update(fields)
        event = ShadowEvent.create(**record)
        self.events.append(event)
        return event

    def message(self, ts: str, actor: str, text: str) -> ShadowEvent:
        raw_type = "user_message" if actor == "user" else "assistant_message"
        return self.add(
            raw_type,
            ts=ts,
            actor=actor,
            kind="message",
            excerpt=bounded_excerpt(text, MESSAGE_EXCERPT_LIMIT),
            content_digest=sha256_hex(text.encode("utf-8")),
        )

    def file_op(
        self, ts: str, kind: str, tool: str, call_id: str, *paths: str
    ) -> ShadowEvent:
        return self.add(
            "tool_use",
            ts=ts,
            actor="agent",
            kind=kind,
            paths=tuple(sorted(paths)),
            tool=tool,
            call_id=call_id,
        )

    def command(
        self,
        ts: str,
        kind: str,
        call_id: str,
        command: str,
        *,
        check_family: str | None = None,
    ) -> ShadowEvent:
        return self.add(
            "tool_use",
            ts=ts,
            actor="agent",
            kind=kind,
            tool="Bash",
            call_id=call_id,
            argv_digest=sha256_hex(command.encode("utf-8")),
            argv_excerpt=bounded_excerpt(command, COMMAND_EXCERPT_LIMIT),
            check_family=check_family,
        )

    def result(
        self,
        ts: str,
        kind: str,
        call_id: str,
        exit_code: int,
        *,
        check_family: str | None = None,
    ) -> ShadowEvent:
        return self.add(
            "tool_result",
            ts=ts,
            actor="tool",
            kind=kind,
            tool="Bash",
            call_id=call_id,
            exit_code=exit_code,
            check_family=check_family,
        )


def build_events() -> tuple[ShadowEvent, ...]:
    """The fixture session as verified events, seq 1..30."""

    b = _Builder()
    t = "2026-08-22T10:{:02d}:{:02d}Z".format
    # Segment 1: the first prompt, three edits, one passing check, a backed claim.
    b.message(t(0, 0), "user", "Make the greeting configurable and add a test for it.")
    b.message(t(0, 4), "agent", "I'll read the current greeting module first.")
    b.file_op(t(0, 6), "file_read", "Read", "call-01", "app/greet.py")
    b.add(
        "tool_use",
        ts=t(0, 9),
        actor="agent",
        kind="tool_call",
        tool="Grep",
        call_id="call-02",
        argv_digest=sha256_hex(b"pattern=greet( path=app"),
        argv_excerpt="pattern=greet( path=app",
    )
    b.add(
        "tool_result",
        ts=t(0, 10),
        actor="tool",
        kind="tool_result",
        tool="Grep",
        call_id="call-02",
        exit_code=0,
    )
    b.file_op(t(0, 30), "file_edit", "Edit", "call-03", "app/greet.py")
    b.file_op(t(0, 52), "file_create", "Write", "call-04", "app/config.py")
    b.file_op(t(1, 20), "file_create", "Write", "call-05", "tests/test_greet.py")
    b.command(
        t(1, 40),
        "check_run",
        "call-06",
        "uv run --frozen pytest -q tests/test_greet.py",
        check_family="pytest",
    )
    b.result(t(1, 47), "check_result", "call-06", 0, check_family="pytest")
    b.message(
        t(1, 55),
        "agent",
        "The greeting is configurable. Tests pass for app/greet.py and app/config.py.",
    )
    # Segment 2: the second prompt; segment 3 opens at the plan marker.
    b.message(t(6, 0), "user", "Also remove app/legacy.py and pin the dependencies.")
    b.add(
        "tool_use",
        ts=t(6, 5),
        actor="agent",
        kind="tool_call",
        tool="TodoWrite",
        call_id="call-07",
    )
    b.command(t(6, 10), "command_exec", "call-08", "git status --short")
    b.result(t(6, 11), "command_result", "call-08", 0)
    b.command(t(6, 20), "install_op", "call-09", "uv sync")
    b.result(t(6, 35), "command_result", "call-09", 0)
    remove = b.command(t(6, 50), "command_exec", "call-10", "rm app/legacy.py")
    b.add(
        "tool_use",
        ts=t(6, 50),
        actor="agent",
        kind="file_delete",
        paths=("app/legacy.py",),
        tool="Bash",
        call_id="call-10",
        provenance="inferred",
        derived_from=(remove.event_id,),
    )
    b.result(t(6, 51), "command_result", "call-10", 0)
    b.file_op(t(7, 5), "file_read", "Read", "call-11", "tests/test_greet.py")
    b.file_op(t(7, 30), "file_edit", "Edit", "call-12", "tests/test_greet.py")
    b.file_op(t(7, 50), "file_edit", "Edit", "call-13", "app/greet.py")
    b.command(
        t(8, 0),
        "network_op",
        "call-14",
        "curl -s https://pypi.org/pypi/graphene/json",
    )
    b.result(t(8, 2), "command_result", "call-14", 0)
    b.file_op(t(8, 20), "file_create", "Write", "call-15", ".env")
    b.add(
        "hook_event",
        ts=t(8, 21),
        actor="system",
        kind="unknown",
        tool="Hook",
    )
    b.command(
        t(8, 40),
        "vcs_op",
        "call-16",
        'git add -A && git commit -m "Configurable greeting"',
    )
    b.result(t(8, 41), "command_result", "call-16", 0)
    b.message(
        t(8, 50),
        "agent",
        "All tests pass. The legacy module is removed and the dependencies are pinned.",
    )
    return tuple(b.events)


def render(events: tuple[ShadowEvent, ...]) -> bytes:
    """One canonical JSON record per LF-terminated line, in seq order."""

    return b"".join(canonical_json_bytes(event.to_record()) + b"\n" for event in events)


def main() -> int:
    data = render(build_events())
    OUTPUT.write_bytes(data)
    lines = data.count(b"\n")
    print(f"wrote {OUTPUT} ({lines} lines, {len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
