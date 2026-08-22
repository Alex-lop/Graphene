"""`shadow.event.v1`: the normalized observation record.

The canonical encoding is length-prefixed and domain-separated, mirroring
`graphene.hashing.candidate_tree_sha256`. Every field except `event_id`
participates, including nulls and empty arrays, so two records that differ in
any field never share an identifier. See docs/SHADOW_ADAPTER_SPEC.md.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from struct import pack
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from ..hashing import canonical_json_bytes, sha256_hex
from ..models import FrozenModel, RepoPath, Sha256

SHADOW_EVENT_SCHEMA = "shadow.event.v1"
SHADOW_SESSION_DOMAIN = "shadow.session.v1"

Actor = Literal["agent", "user", "tool", "system"]
Kind = Literal[
    "message",
    "claim",
    "tool_call",
    "tool_result",
    "file_read",
    "file_edit",
    "file_create",
    "file_delete",
    "command_exec",
    "command_result",
    "check_run",
    "check_result",
    "vcs_op",
    "network_op",
    "install_op",
    "unknown",
]
Provenance = Literal["observed", "inferred"]
ClaimCategory = Literal["checks_pass", "build_ok", "verified", "fixed"]

KINDS: tuple[str, ...] = Kind.__args__  # type: ignore[attr-defined]
ACTORS: tuple[str, ...] = Actor.__args__  # type: ignore[attr-defined]
CHECK_KINDS = frozenset({"check_run", "check_result"})

# Every field that participates in the event identifier, in ascending byte
# order. `event_id` itself is excluded.
EVENT_FIELDS: tuple[str, ...] = (
    "actor",
    "argv_digest",
    "argv_excerpt",
    "call_id",
    "check_family",
    "claim",
    "content_digest",
    "derived_from",
    "excerpt",
    "exit_code",
    "kind",
    "outside_paths",
    "paths",
    "provenance",
    "schema",
    "seq",
    "session_id",
    "source",
    "tool",
    "ts",
)
assert EVENT_FIELDS == tuple(sorted(EVENT_FIELDS))

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$")


def _utc_timestamp(value: str) -> str:
    if not _TIMESTAMP.match(value):
        raise ValueError("timestamps must be RFC 3339 UTC with a trailing Z")
    # Python accepts at most six fractional digits; validate calendar fields on
    # a truncated copy without altering the recorded string.
    head, _, fraction = value[:-1].partition(".")
    datetime.fromisoformat(head + ("." + fraction[:6] if fraction else ""))
    return value


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    if list(values) != sorted(set(values)):
        raise ValueError("path and reference arrays must be sorted and unique")
    return values


# C0 and C1 control characters (ESC and every terminal escape sequence start
# with one) and the Unicode line and paragraph separators. A value carrying
# one could forge lines in the lint listing and the report text.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _printable(value: str) -> str:
    if _CONTROL_CHARACTERS.search(value):
        raise ValueError("must not contain control characters")
    return value


def _outside_path(value: str) -> str:
    if not value.strip():
        raise ValueError("outside paths must be printable and non-empty")
    return value


Printable = AfterValidator(_printable)
Timestamp = Annotated[str, AfterValidator(_utc_timestamp)]
SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")]
ShortText = Annotated[str, Field(min_length=1, max_length=128), Printable]
EventPath = Annotated[RepoPath, Printable]
OutsidePath = Annotated[
    str,
    Field(min_length=1, max_length=512),
    Printable,
    AfterValidator(_outside_path),
]
ToolName = Annotated[str, Field(min_length=1, max_length=64), Printable]
CallId = Annotated[str, Field(min_length=1, max_length=128), Printable]
CommandExcerpt = Annotated[str, Field(min_length=1, max_length=200), Printable]
MessageExcerpt = Annotated[str, Field(min_length=1, max_length=280), Printable]


class ShadowClaim(FrozenModel):
    matcher: Literal["claims.v1"]
    category: ClaimCategory
    pattern_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]


class ShadowSource(FrozenModel):
    adapter: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    adapter_version: Annotated[str, Field(pattern=r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")]
    record_ref: ShortText
    raw_type: ShortText


class ShadowEvent(FrozenModel):
    schema_name: Literal["shadow.event.v1"] = Field(alias="schema")
    session_id: SessionId
    seq: Annotated[int, Field(ge=1, le=10_000_000)]
    ts: Timestamp | None
    actor: Actor
    kind: Kind
    paths: Annotated[tuple[EventPath, ...], AfterValidator(_sorted_unique)]
    outside_paths: Annotated[tuple[OutsidePath, ...], AfterValidator(_sorted_unique)]
    tool: ToolName | None
    call_id: CallId | None
    argv_digest: Sha256 | None
    argv_excerpt: CommandExcerpt | None
    exit_code: Annotated[int, Field(ge=-1024, le=1024)] | None
    check_family: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,31}$")] | None
    excerpt: MessageExcerpt | None
    content_digest: Sha256 | None
    claim: ShadowClaim | None
    provenance: Provenance
    derived_from: Annotated[tuple[Sha256, ...], AfterValidator(_sorted_unique)]
    source: ShadowSource
    event_id: Sha256

    @model_validator(mode="after")
    def shape_is_consistent(self) -> ShadowEvent:
        if (self.provenance == "inferred") != bool(self.derived_from):
            raise ValueError(
                "inferred events must cite derived_from and observed events must not"
            )
        if (self.kind == "claim") != (self.claim is not None):
            raise ValueError("claim payload is present exactly on claim events")
        if self.kind == "claim" and self.provenance != "inferred":
            raise ValueError("claims are always inferred")
        if self.check_family is not None and self.kind not in CHECK_KINDS:
            raise ValueError("check_family belongs only to check events")
        if self.event_id != event_id_for(self.identity_fields()):
            raise ValueError("shadow event identifier does not match its content")
        return self

    def identity_fields(self) -> dict[str, object]:
        record = self.model_dump(mode="json", by_alias=True)
        record.pop("event_id")
        return record

    def to_record(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)

    @classmethod
    def create(cls, **fields: object) -> ShadowEvent:
        """Build an event, computing its identifier from the supplied fields."""

        if "event_id" in fields:
            raise ValueError("event_id is derived, not supplied")
        if "schema" in fields:
            raise ValueError("schema is fixed by the event class")
        candidate = dict(fields)
        candidate["schema"] = SHADOW_EVENT_SCHEMA
        candidate.setdefault("paths", ())
        candidate.setdefault("outside_paths", ())
        candidate.setdefault("derived_from", ())
        for optional in (
            "ts",
            "tool",
            "call_id",
            "argv_digest",
            "argv_excerpt",
            "exit_code",
            "check_family",
            "excerpt",
            "content_digest",
            "claim",
        ):
            candidate.setdefault(optional, None)
        draft = _Draft.model_validate(candidate)
        identity = draft.model_dump(mode="json", by_alias=True)
        return cls.model_validate({**identity, "event_id": event_id_for(identity)})

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> ShadowEvent:
        """Validate an external record; a missing event_id is computed."""

        if not isinstance(record, Mapping):
            raise ValueError("shadow records must be JSON objects")
        if "event_id" in record:
            return cls.model_validate(dict(record))
        draft = _Draft.model_validate(dict(record))
        identity = draft.model_dump(mode="json", by_alias=True)
        return cls.model_validate({**identity, "event_id": event_id_for(identity)})


class _Draft(FrozenModel):
    """The identity fields of an event before its identifier exists."""

    schema_name: Literal["shadow.event.v1"] = Field(alias="schema")
    session_id: SessionId
    seq: Annotated[int, Field(ge=1, le=10_000_000)]
    ts: Timestamp | None
    actor: Actor
    kind: Kind
    paths: Annotated[tuple[EventPath, ...], AfterValidator(_sorted_unique)]
    outside_paths: Annotated[tuple[OutsidePath, ...], AfterValidator(_sorted_unique)]
    tool: ToolName | None
    call_id: CallId | None
    argv_digest: Sha256 | None
    argv_excerpt: CommandExcerpt | None
    exit_code: Annotated[int, Field(ge=-1024, le=1024)] | None
    check_family: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,31}$")] | None
    excerpt: MessageExcerpt | None
    content_digest: Sha256 | None
    claim: ShadowClaim | None
    provenance: Provenance
    derived_from: Annotated[tuple[Sha256, ...], AfterValidator(_sorted_unique)]
    source: ShadowSource


def canonical_event_bytes(fields: Mapping[str, object]) -> bytes:
    """Length-prefixed, domain-separated encoding of the identity fields."""

    if set(fields) != set(EVENT_FIELDS):
        unexpected = sorted(set(fields) - set(EVENT_FIELDS))
        missing = sorted(set(EVENT_FIELDS) - set(fields))
        raise ValueError(
            "shadow event identity fields mismatch: "
            f"unexpected={unexpected} missing={missing}"
        )
    encoded = bytearray(SHADOW_EVENT_SCHEMA.encode("ascii") + b"\0")
    encoded += pack(">Q", len(EVENT_FIELDS))
    for name in EVENT_FIELDS:
        name_bytes = name.encode("ascii")
        value_bytes = canonical_json_bytes(fields[name])
        encoded += pack(">Q", len(name_bytes)) + name_bytes
        encoded += pack(">Q", len(value_bytes)) + value_bytes
    return bytes(encoded)


def event_id_for(fields: Mapping[str, object]) -> str:
    return sha256_hex(canonical_event_bytes(fields))


def session_sha256(event_ids: Iterable[str]) -> str:
    """Digest of an ordered event-identifier stream."""

    identifiers = tuple(event_ids)
    digest = hashlib.sha256()
    digest.update(SHADOW_SESSION_DOMAIN.encode("ascii") + b"\0")
    digest.update(pack(">Q", len(identifiers)))
    for identifier in identifiers:
        raw = bytes.fromhex(identifier)
        if len(raw) != 32:
            raise ValueError("event identifiers must be 32-byte digests")
        digest.update(pack(">Q", 32) + raw)
    return digest.hexdigest()


__all__ = [
    "ACTORS",
    "EVENT_FIELDS",
    "KINDS",
    "SHADOW_EVENT_SCHEMA",
    "SHADOW_SESSION_DOMAIN",
    "ShadowClaim",
    "ShadowEvent",
    "ShadowSource",
    "canonical_event_bytes",
    "event_id_for",
    "session_sha256",
]
