"""The ``ndjson`` adapter: the open ``shadow.event.v1`` format, parsed strictly.

Rule in one line: one JSON object per LF-terminated line, validated field by
field against ``ShadowEvent`` so that the first violation stops ingest with a
message naming the line and the field. Rejected, in order of detection: a
UTF-8 BOM, invalid UTF-8, a blank line, a CR line ending, a line that is not a
JSON object, an unknown or missing field, a wrong JSON type, a schema other
than ``shadow.event.v1``, an unknown ``kind``/``actor``/``provenance``, a
``seq`` that is not contiguous from 1, a ``session_id`` that changes
mid-file, a malformed or mismatched supplied ``event_id``, any value
``ShadowEvent`` refuses (paths, lengths, patterns, control characters, claim
and provenance shape), and a ``derived_from`` entry that is not the
``event_id`` of an earlier record in the same file. A line too deeply nested
to parse, or whose record nests containers deeper than ``MAX_NESTING``
levels, is rejected with the line number rather than escaping as a
``RecursionError``.

``source`` is kept exactly as supplied: the emitter's adapter id and version
travel with every event. Re-ingesting an exported capsule's ``events.ndjson``
reproduces the same shadow id because the stream already carries its claims,
its excerpts are already redacted, and no renumbering occurs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..events import ACTORS, EVENT_FIELDS, KINDS, SHADOW_EVENT_SCHEMA, ShadowEvent
from . import AdapterError, Draft, ParsedSession, validation_message

NDJSON_ADAPTER = "ndjson"
NDJSON_ADAPTER_VERSION = "1.0.0"

_BOM = b"\xef\xbb\xbf"
_EMPTY = "line 1: empty input, a session needs at least one record"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROVENANCES = ("observed", "inferred")
_RESERVED = frozenset(
    {"schema", "seq", "event_id", "provenance", "derived_from", "session_id"}
)
_KNOWN_FIELDS = frozenset(EVENT_FIELDS) | {"event_id"}
# Records are flat except ``source`` and ``claim`` (objects) and the three
# string arrays, so two levels are the deepest a valid record ever needs.
MAX_NESTING = 4

# JSON shape of every identity field; value constraints belong to ShadowEvent.
_STRING = frozenset({"schema", "session_id", "actor", "kind", "provenance"})
_OPTIONAL_STRING = frozenset(
    {
        "ts",
        "tool",
        "call_id",
        "argv_digest",
        "argv_excerpt",
        "check_family",
        "excerpt",
        "content_digest",
    }
)
_INTEGER = frozenset({"seq"})
_OPTIONAL_INTEGER = frozenset({"exit_code"})
_STRING_ARRAY = frozenset({"paths", "outside_paths", "derived_from"})
_OBJECT = frozenset({"source"})
_OPTIONAL_OBJECT = frozenset({"claim"})


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _shape_error(name: str, value: object) -> str | None:
    """The type complaint for one field, or None when the JSON shape is right."""

    if name in _STRING and not isinstance(value, str):
        return f'field "{name}" must be a string'
    if name in _OPTIONAL_STRING and value is not None and not isinstance(value, str):
        return f'field "{name}" must be a string or null'
    if name in _INTEGER and not _is_integer(value):
        return f'field "{name}" must be an integer'
    if name in _OPTIONAL_INTEGER and value is not None and not _is_integer(value):
        return f'field "{name}" must be an integer or null'
    if name in _STRING_ARRAY and (
        not isinstance(value, list) or not all(isinstance(item, str) for item in value)
    ):
        return f'field "{name}" must be an array of strings'
    if name in _OBJECT and not isinstance(value, dict):
        return f'field "{name}" must be an object'
    if name in _OPTIONAL_OBJECT and value is not None and not isinstance(value, dict):
        return f'field "{name}" must be an object or null'
    if name == "event_id" and not isinstance(value, str):
        return 'field "event_id" must be a string'
    return None


def _decode(data: bytes) -> list[str]:
    if data.startswith(_BOM):
        raise AdapterError("line 1: UTF-8 BOM is not allowed")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        line_number = data.count(b"\n", 0, error.start) + 1
        raise AdapterError(f"line {line_number}: invalid UTF-8") from error
    if not text:
        raise AdapterError(_EMPTY)
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()  # the terminating LF of the last record, not a blank line
    return lines


def _record(
    line_number: int, line: str, *, max_nesting: int = MAX_NESTING
) -> dict[str, object]:
    if line.endswith("\r"):
        raise AdapterError(f"line {line_number}: CR line ending")
    if "\r" in line:
        raise AdapterError(f"line {line_number}: carriage return inside the record")
    if not line.strip():
        raise AdapterError(f"line {line_number}: blank line")
    try:
        value = json.loads(line)
    except RecursionError as error:
        raise AdapterError(
            f"line {line_number}: invalid JSON (nesting too deep)"
        ) from error
    except ValueError as error:
        raise AdapterError(f"line {line_number}: invalid JSON ({error})") from error
    if not isinstance(value, dict):
        raise AdapterError(f"line {line_number}: record is not a JSON object")
    if _nesting(value) > max_nesting:
        raise AdapterError(
            f"line {line_number}: record nests containers deeper than "
            f"{max_nesting} levels"
        )
    return value


def _nesting(value: object) -> int:
    """Deepest container level in ``value`` (the record itself is level 1)."""

    deepest = 0
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        current, level = pending.pop()
        if isinstance(current, dict):
            deepest = max(deepest, level)
            pending.extend((item, level + 1) for item in current.values())
        elif isinstance(current, list):
            deepest = max(deepest, level)
            pending.extend((item, level + 1) for item in current)
    return deepest


def _check_fields(line_number: int, record: dict[str, object]) -> None:
    unknown = sorted(set(record) - _KNOWN_FIELDS)
    if unknown:
        named = ", ".join(f'"{name}"' for name in unknown)
        noun = "field" if len(unknown) == 1 else "fields"
        raise AdapterError(f"line {line_number}: unknown {noun} {named}")
    missing = [name for name in EVENT_FIELDS if name not in record]
    if missing:
        raise AdapterError(f'line {line_number}: missing field "{missing[0]}"')
    for name in (*EVENT_FIELDS, "event_id"):
        if name in record:
            complaint = _shape_error(name, record[name])
            if complaint is not None:
                raise AdapterError(f"line {line_number}: {complaint}")
    if record["schema"] != SHADOW_EVENT_SCHEMA:
        raise AdapterError(
            f'line {line_number}: schema must be "{SHADOW_EVENT_SCHEMA}"'
        )
    if record["kind"] not in KINDS:
        raise AdapterError(f'line {line_number}: unknown kind "{record["kind"]}"')
    if record["actor"] not in ACTORS:
        raise AdapterError(f'line {line_number}: unknown actor "{record["actor"]}"')
    if record["provenance"] not in _PROVENANCES:
        raise AdapterError(
            f'line {line_number}: provenance must be "observed" or "inferred"'
        )


def _verified_event(line_number: int, record: dict[str, object]) -> ShadowEvent:
    supplied = record.get("event_id")
    identity = {name: value for name, value in record.items() if name != "event_id"}
    if supplied is not None and not _SHA256.match(str(supplied)):
        raise AdapterError(
            f'line {line_number}: field "event_id" must be a lowercase hex SHA-256'
        )
    try:
        event = ShadowEvent.from_record(identity)
    except ValueError as error:
        raise AdapterError(
            f"line {line_number}: {validation_message(error)}"
        ) from error
    if supplied is not None and supplied != event.event_id:
        raise AdapterError(
            f"line {line_number}: event_id does not match the canonical encoding"
        )
    return event


def _draft(event: ShadowEvent, index_of: dict[str, int]) -> Draft:
    fields = {
        name: value
        for name, value in event.to_record().items()
        if name not in _RESERVED and name != "event_id"
    }
    references = tuple(sorted(index_of[event_id] for event_id in event.derived_from))
    return Draft(fields=fields, provenance=event.provenance, derived_from=references)


class NdjsonAdapter:
    """Parser for the open ``shadow.event.v1`` newline-delimited format."""

    name = NDJSON_ADAPTER
    version = NDJSON_ADAPTER_VERSION

    def parse(self, data: bytes, *, repo: Path | None) -> ParsedSession:
        """Parse one session; ``repo`` is unused because paths arrive normalized."""

        if not isinstance(data, bytes):
            raise AdapterError("ndjson input must be bytes")
        if repo is not None and not isinstance(repo, Path):
            raise AdapterError("repo must be a Path or None")
        drafts: list[Draft] = []
        index_of: dict[str, int] = {}
        session_id: str | None = None
        has_claims = False
        unknown_count = 0
        for line_number, line in enumerate(_decode(data), start=1):
            record = _record(line_number, line)
            _check_fields(line_number, record)
            expected = len(drafts) + 1
            if record["seq"] != expected:
                raise AdapterError(
                    f"line {line_number}: seq {record['seq']} is not contiguous "
                    f"(expected {expected})"
                )
            if session_id is None:
                session_id = str(record["session_id"])
            elif record["session_id"] != session_id:
                raise AdapterError(
                    f'line {line_number}: session_id changed from "{session_id}" '
                    f'to "{record["session_id"]}"'
                )
            event = _verified_event(line_number, record)
            for reference in event.derived_from:
                if reference not in index_of:
                    raise AdapterError(
                        f"line {line_number}: derived_from {reference} does not "
                        "refer to an earlier record in the file"
                    )
            drafts.append(_draft(event, index_of))
            index_of[event.event_id] = len(drafts) - 1
            has_claims = has_claims or event.kind == "claim"
            unknown_count += event.kind == "unknown"
        if session_id is None:
            raise AdapterError(_EMPTY)
        return ParsedSession(
            session_id=session_id,
            drafts=tuple(drafts),
            has_claims=has_claims,
            raw_record_count=len(drafts),
            unknown_count=unknown_count,
            adapter=self.name,
            adapter_version=self.version,
        )


__all__ = ["MAX_NESTING", "NDJSON_ADAPTER", "NDJSON_ADAPTER_VERSION", "NdjsonAdapter"]
