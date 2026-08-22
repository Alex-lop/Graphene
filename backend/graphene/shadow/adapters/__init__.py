"""Shadow adapters: turn a source transcript into ``shadow.event.v1`` drafts.

An adapter parses raw bytes into a ``ParsedSession`` of ``Draft`` records
that carry every event field except the ones the pipeline assigns
(``schema``, ``seq``, ``event_id``, ``provenance``, ``derived_from`` and
``session_id`` are assigned by ``materialize``). Drafts refer to one another
by list index; ``materialize`` numbers them 1..n, resolves those indexes to
event identifiers, and computes each identifier. Draft field names that start
with ``_`` are private to the pipeline and are stripped before an event is
created, so they can never be persisted. Every failure is an ``AdapterError``
whose message names the record locator and the field or condition at fault.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, NamedTuple, Protocol

from pydantic import ValidationError

from ..events import ShadowEvent

# Fields ``materialize`` assigns; a draft must not carry them.
RESERVED_FIELDS = frozenset(
    {"schema", "seq", "event_id", "provenance", "derived_from", "session_id"}
)
PRIVATE_PREFIX = "_"

Provenance = Literal["observed", "inferred"]


class AdapterError(ValueError):
    """A source record could not be turned into a verified shadow event."""


class Draft(NamedTuple):
    fields: dict[str, object]
    provenance: Provenance
    derived_from: tuple[int, ...]


class ParsedSession(NamedTuple):
    session_id: str
    drafts: tuple[Draft, ...]
    has_claims: bool
    raw_record_count: int
    unknown_count: int
    adapter: str
    adapter_version: str


class Adapter(Protocol):
    name: str
    version: str

    def parse(self, data: bytes, *, repo: Path | None) -> ParsedSession: ...


def validation_message(error: ValueError) -> str:
    """One line naming the offending field, from a pydantic or plain error."""

    if not isinstance(error, ValidationError):
        return str(error)
    first = error.errors()[0]
    message = str(first["msg"])
    prefix = "Value error, "
    if message.startswith(prefix):
        message = message[len(prefix) :]
    location = ""
    for part in first["loc"]:
        if isinstance(part, int):
            location += f"[{part}]"
        else:
            location += f".{part}" if location else str(part)
    return f'field "{location}": {message}' if location else message


def materialize(session_id: str, drafts: Sequence[Draft]) -> tuple[ShadowEvent, ...]:
    """Number drafts 1..n, resolve derived_from indexes, and compute event ids.

    Private (``_``-prefixed) draft fields are dropped; reserved fields, forward
    or self references, and provenance that disagrees with ``derived_from``
    fail closed with the draft index in the message.
    """

    events: list[ShadowEvent] = []
    for index, draft in enumerate(drafts):
        if not isinstance(draft, Draft):
            raise AdapterError(f"draft {index}: not a Draft record")
        if not isinstance(draft.fields, Mapping):
            raise AdapterError(f"draft {index}: fields must be a mapping")
        fields = {
            name: value
            for name, value in draft.fields.items()
            if not name.startswith(PRIVATE_PREFIX)
        }
        reserved = sorted(RESERVED_FIELDS & set(fields))
        if reserved:
            raise AdapterError(
                f'draft {index}: field "{reserved[0]}" is assigned by materialize'
            )
        if draft.provenance not in ("observed", "inferred"):
            raise AdapterError(
                f'draft {index}: provenance must be "observed" or "inferred"'
            )
        references = tuple(sorted(set(draft.derived_from)))
        for reference in references:
            if (
                isinstance(reference, bool)
                or not isinstance(reference, int)
                or reference < 0
                or reference >= index
            ):
                raise AdapterError(
                    f"draft {index}: derived_from index {reference!r} must refer "
                    "to an earlier draft"
                )
        if (draft.provenance == "inferred") != bool(references):
            raise AdapterError(
                f"draft {index}: inferred drafts cite derived_from and observed "
                "drafts do not"
            )
        derived_ids = tuple(sorted({events[ref].event_id for ref in references}))
        try:
            event = ShadowEvent.create(
                session_id=session_id,
                seq=index + 1,
                provenance=draft.provenance,
                derived_from=derived_ids,
                **fields,
            )
        except ValueError as error:
            raise AdapterError(f"draft {index}: {validation_message(error)}") from error
        events.append(event)
    return tuple(events)


def _builtin_adapters() -> dict[str, Adapter]:
    # Imported here so the adapter module can import the draft types above.
    from .ndjson import NdjsonAdapter

    adapter = NdjsonAdapter()
    return {adapter.name: adapter}


# ``claude-code`` is NOT implemented yet; only the open ndjson format is here.
ADAPTERS: dict[str, Adapter] = _builtin_adapters()


def adapter_for(name: str) -> Adapter:
    """The registered adapter instance for ``name``; unknown names fail closed."""

    adapter = ADAPTERS.get(name) if isinstance(name, str) else None
    if adapter is None:
        raise AdapterError(f"unsupported shadow format: {name}")
    return adapter


__all__ = [
    "ADAPTERS",
    "PRIVATE_PREFIX",
    "RESERVED_FIELDS",
    "Adapter",
    "AdapterError",
    "Draft",
    "ParsedSession",
    "Provenance",
    "adapter_for",
    "materialize",
    "validation_message",
]
