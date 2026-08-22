"""Encoding vectors and shape rules for `shadow.event.v1`.

The reference encoder below is written from docs/SHADOW_ADAPTER_SPEC.md using
only struct, json, and hashlib, so a change to the module's encoding cannot
silently re-derive the digests these tests expect.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from struct import pack

import pytest

from graphene.shadow.events import (
    ACTORS,
    EVENT_FIELDS,
    KINDS,
    SHADOW_EVENT_SCHEMA,
    SHADOW_SESSION_DOMAIN,
    ShadowClaim,
    ShadowEvent,
    ShadowSource,
    canonical_event_bytes,
    event_id_for,
    session_sha256,
)

SOURCE: dict[str, str] = {
    "adapter": "ndjson",
    "adapter_version": "1.0.0",
    "record_ref": "line:1",
    "raw_type": "user_message",
}
CLAIM: dict[str, str] = {
    "matcher": "claims.v1",
    "category": "checks_pass",
    "pattern_id": "tests-pass",
}
DIGEST_A = "ab" * 32
DIGEST_B = "cd" * 32

# The specification's first worked-example line with a fixed content digest.
# The pinned identifier and byte length were produced by `_reference_bytes`,
# not by the module under test.
VECTOR_RECORD: dict[str, object] = {
    "schema": "shadow.event.v1",
    "session_id": "vector-session",
    "seq": 1,
    "ts": "2026-08-22T10:00:00Z",
    "actor": "user",
    "kind": "message",
    "paths": [],
    "outside_paths": [],
    "tool": None,
    "call_id": None,
    "argv_digest": None,
    "argv_excerpt": None,
    "exit_code": None,
    "check_family": None,
    "excerpt": "Make the greeting configurable.",
    "content_digest": "d8" * 32,
    "claim": None,
    "provenance": "observed",
    "derived_from": [],
    "source": SOURCE,
}
VECTOR_EVENT_ID = "d2669902a0bc7be1372a9f2de238c95259fde526278b00ef9e3562705d5b0bd1"
VECTOR_BYTES_LENGTH = 809

SESSION_VECTOR_IDS = ("00" * 32, "ff" * 32, "0123456789abcdef" * 4)
SESSION_VECTOR_DIGEST = (
    "369c475602f4aceb671cd85c292e74adfb1084d7f5f8752fa71400fe138235df"
)
EMPTY_SESSION_DIGEST = (
    "796d0a72f21f1612f70a732e0c6747ecfd150e3f022cdd5b8d22c5ff75f555ee"
)


def _reference_bytes(fields: Mapping[str, object]) -> bytes:
    """The spec encoding: domain, be64 count, then sorted name/value pairs."""

    encoded = b"shadow.event.v1\0" + pack(">Q", len(fields))
    for name in sorted(fields):
        name_bytes = name.encode("ascii")
        value_bytes = json.dumps(
            fields[name],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        encoded += pack(">Q", len(name_bytes)) + name_bytes
        encoded += pack(">Q", len(value_bytes)) + value_bytes
    return encoded


def _reference_session_digest(event_ids: Iterable[str]) -> str:
    identifiers = tuple(event_ids)
    encoded = b"shadow.session.v1\0" + pack(">Q", len(identifiers))
    for identifier in identifiers:
        encoded += pack(">Q", 32) + bytes.fromhex(identifier)
    return hashlib.sha256(encoded).hexdigest()


def _event(**over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "seq": 1,
        "ts": "2026-08-22T10:00:00Z",
        "actor": "agent",
        "kind": "message",
        "excerpt": "Done.",
        "content_digest": DIGEST_A,
        "provenance": "observed",
        "source": SOURCE,
    }
    fields.update(over)
    return ShadowEvent.create(**fields)


# -- canonical encoding ------------------------------------------------------


def test_vector_record_matches_reference_encoder_and_pinned_digest() -> None:
    expected = _reference_bytes(VECTOR_RECORD)

    assert len(expected) == VECTOR_BYTES_LENGTH
    assert hashlib.sha256(expected).hexdigest() == VECTOR_EVENT_ID
    assert canonical_event_bytes(VECTOR_RECORD) == expected
    assert event_id_for(VECTOR_RECORD) == VECTOR_EVENT_ID

    event = ShadowEvent.from_record(VECTOR_RECORD)
    assert event.event_id == VECTOR_EVENT_ID
    assert event.to_record() == {**VECTOR_RECORD, "event_id": VECTOR_EVENT_ID}


def test_created_events_match_the_reference_encoder() -> None:
    event = _event(
        kind="file_edit",
        paths=("src/app.py", "tests/test_app.py"),
        outside_paths=("~/notes.txt",),
        tool="Edit",
        call_id="call-1",
        excerpt=None,
        content_digest=None,
    )
    identity = event.identity_fields()

    assert set(identity) == set(EVENT_FIELDS)
    assert canonical_event_bytes(identity) == _reference_bytes(identity)
    assert event.event_id == hashlib.sha256(_reference_bytes(identity)).hexdigest()


def test_domain_prefix_and_field_count_lead_the_encoding() -> None:
    encoded = canonical_event_bytes(VECTOR_RECORD)

    assert SHADOW_EVENT_SCHEMA == "shadow.event.v1"
    assert len(EVENT_FIELDS) == 20
    assert "event_id" not in EVENT_FIELDS
    assert encoded.startswith(b"shadow.event.v1\0" + pack(">Q", 20))


def test_field_order_is_sorted_bytewise_and_independent_of_input_order() -> None:
    assert list(EVENT_FIELDS) == sorted(EVENT_FIELDS)
    encoded = canonical_event_bytes(VECTOR_RECORD)
    positions = [
        encoded.index(pack(">Q", len(name)) + name.encode("ascii"))
        for name in EVENT_FIELDS
    ]
    assert positions == sorted(positions)

    reversed_record = dict(reversed(list(VECTOR_RECORD.items())))
    assert canonical_event_bytes(reversed_record) == encoded


def test_null_and_empty_array_encode_differently() -> None:
    with_null = canonical_event_bytes({**VECTOR_RECORD, "claim": None})
    with_empty = canonical_event_bytes({**VECTOR_RECORD, "claim": []})

    assert with_null != with_empty
    assert pack(">Q", 4) + b"null" in with_null
    assert pack(">Q", 2) + b"[]" in with_empty
    assert event_id_for({**VECTOR_RECORD, "claim": None}) != event_id_for(
        {**VECTOR_RECORD, "claim": []}
    )


def test_canonical_json_keeps_non_ascii_and_sorts_nested_keys() -> None:
    encoded = canonical_event_bytes({**VECTOR_RECORD, "excerpt": "café ✓"})

    assert "café ✓".encode() in encoded
    assert b"\\u" not in encoded
    # Nested keys sort bytewise: "raw_type" precedes "record_ref".
    assert (
        b'{"adapter":"ndjson","adapter_version":"1.0.0",'
        b'"raw_type":"user_message","record_ref":"line:1"}'
    ) in encoded


def test_identity_field_set_is_enforced() -> None:
    with pytest.raises(ValueError, match=r"unexpected=\['event_id'\]"):
        canonical_event_bytes({**VECTOR_RECORD, "event_id": VECTOR_EVENT_ID})
    missing = dict(VECTOR_RECORD)
    del missing["ts"]
    with pytest.raises(ValueError, match=r"missing=\['ts'\]"):
        canonical_event_bytes(missing)


def test_every_identity_field_changes_the_identifier() -> None:
    base = _event()
    variants = (
        _event(seq=2),
        _event(ts=None),
        _event(actor="user"),
        _event(kind="tool_call"),
        _event(excerpt="Done!"),
        _event(content_digest=DIGEST_B),
        _event(session_id="sess-2"),
        _event(tool="Bash"),
        _event(call_id="call-9"),
        _event(source={**SOURCE, "record_ref": "line:2"}),
        _event(source={**SOURCE, "adapter_version": "1.0.1"}),
    )

    identifiers = {base.event_id, *(variant.event_id for variant in variants)}
    assert len(identifiers) == len(variants) + 1


# -- identifier verification -------------------------------------------------


def test_supplied_event_id_mismatch_fails_closed() -> None:
    record = _event().to_record()

    with pytest.raises(ValueError, match="identifier does not match its content"):
        ShadowEvent.from_record({**record, "event_id": "0" * 64})
    with pytest.raises(ValueError, match="identifier does not match its content"):
        ShadowEvent.from_record({**record, "seq": 2})
    with pytest.raises(ValueError, match="should match pattern"):
        ShadowEvent.from_record({**record, "event_id": "not-a-digest"})


def test_from_record_computes_a_missing_id_and_round_trips() -> None:
    event = _event()
    record = event.to_record()
    del record["event_id"]

    assert ShadowEvent.from_record(record) == event
    assert ShadowEvent.from_record(event.to_record()) == event
    assert ShadowEvent.from_record(json.loads(json.dumps(event.to_record()))) == event
    assert set(event.to_record()) == {*EVENT_FIELDS, "event_id"}


def test_from_record_rejects_non_objects_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="must be JSON objects"):
        ShadowEvent.from_record(["not", "an", "object"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ShadowEvent.from_record({**_event().to_record(), "foo": 1})
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        _event(foo=1)
    with pytest.raises(ValueError, match="shadow.event.v1"):
        ShadowEvent.from_record({**VECTOR_RECORD, "schema": "shadow.event.v2"})


# -- shape rules -------------------------------------------------------------


@pytest.mark.parametrize("paths", (("b.py", "a.py"), ("a.py", "a.py")))
def test_unsorted_or_duplicate_paths_raise(paths: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="sorted and unique"):
        _event(kind="file_edit", paths=paths)


def test_unsorted_derived_from_and_outside_paths_raise() -> None:
    with pytest.raises(ValueError, match="sorted and unique"):
        _event(provenance="inferred", derived_from=(DIGEST_B, DIGEST_A))
    with pytest.raises(ValueError, match="sorted and unique"):
        _event(kind="file_edit", outside_paths=("~/b.txt", "~/a.txt"))


@pytest.mark.parametrize(
    "path", ("/etc/passwd", "../escape.py", "a\\b.py", "./a.py", "a//b.py", "", ".")
)
def test_noncanonical_repository_paths_raise(path: str) -> None:
    with pytest.raises(ValueError):
        _event(kind="file_edit", paths=(path,))


@pytest.mark.parametrize("outside", ("", "   ", "a\0b"))
def test_blank_or_nul_outside_paths_raise(outside: str) -> None:
    with pytest.raises(ValueError):
        _event(kind="file_edit", outside_paths=(outside,))


def test_inferred_requires_derived_from_and_observed_forbids_it() -> None:
    with pytest.raises(ValueError, match="inferred events must cite derived_from"):
        _event(provenance="inferred")
    with pytest.raises(ValueError, match="observed events must not"):
        _event(provenance="observed", derived_from=(DIGEST_A,))

    inferred = _event(provenance="inferred", derived_from=(DIGEST_A,))
    assert inferred.provenance == "inferred"
    assert inferred.derived_from == (DIGEST_A,)


def test_claim_payload_is_present_exactly_on_claim_events() -> None:
    with pytest.raises(ValueError, match="claim payload is present exactly on claim"):
        _event(claim=CLAIM)
    with pytest.raises(ValueError, match="claim payload is present exactly on claim"):
        _event(kind="claim", provenance="inferred", derived_from=(DIGEST_A,))
    with pytest.raises(ValueError, match="claims are always inferred"):
        _event(kind="claim", claim=CLAIM)

    claim = _event(
        kind="claim", claim=CLAIM, provenance="inferred", derived_from=(DIGEST_A,)
    )
    assert claim.claim == ShadowClaim(**CLAIM)


@pytest.mark.parametrize(
    "override",
    (
        {"matcher": "claims.v2"},
        {"category": "maybe"},
        {"pattern_id": "Tests-Pass"},
        {"pattern_id": ""},
    ),
)
def test_claim_payload_shape_is_validated(override: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        _event(
            kind="claim",
            claim={**CLAIM, **override},
            provenance="inferred",
            derived_from=(DIGEST_A,),
        )


def test_check_family_belongs_only_to_check_events() -> None:
    with pytest.raises(ValueError, match="check_family belongs only to check events"):
        _event(kind="command_exec", check_family="pytest")
    with pytest.raises(ValueError, match="check_family belongs only to check events"):
        _event(kind="message", check_family="pytest")

    for kind in ("check_run", "check_result"):
        assert _event(kind=kind, check_family="pytest").check_family == "pytest"
    with pytest.raises(ValueError):
        _event(kind="check_run", check_family="PyTest")


def test_create_rejects_event_id_and_schema() -> None:
    with pytest.raises(ValueError, match="event_id is derived, not supplied"):
        _event(event_id="0" * 64)
    with pytest.raises(ValueError, match="schema is fixed by the event class"):
        _event(schema="shadow.event.v1")

    event = _event()
    assert event.schema_name == "shadow.event.v1"
    assert event.to_record()["schema"] == "shadow.event.v1"


def test_create_defaults_optional_fields_to_none_or_empty() -> None:
    event = ShadowEvent.create(
        session_id="s",
        seq=1,
        actor="tool",
        kind="unknown",
        provenance="observed",
        source=SOURCE,
    )

    assert event.paths == ()
    assert event.outside_paths == ()
    assert event.derived_from == ()
    assert event.ts is None
    assert event.tool is None
    assert event.call_id is None
    assert event.argv_digest is None
    assert event.argv_excerpt is None
    assert event.exit_code is None
    assert event.check_family is None
    assert event.excerpt is None
    assert event.content_digest is None
    assert event.claim is None
    assert event.to_record()["paths"] == []
    assert event.to_record()["derived_from"] == []


def test_events_are_frozen() -> None:
    event = _event()
    with pytest.raises(ValueError):
        event.seq = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "ts",
    (
        "2026-08-22T10:00:00Z",
        "2026-08-22T10:00:00.5Z",
        "2026-08-22T10:00:00.123456789Z",
    ),
)
def test_accepts_rfc3339_utc_timestamps_unchanged(ts: str) -> None:
    assert _event(ts=ts).ts == ts


@pytest.mark.parametrize(
    "ts",
    (
        "2026-08-22T10:00:00+00:00",
        "2026-08-22 10:00:00Z",
        "2026-08-22T10:00:00",
        "2026-13-01T00:00:00Z",
        "2026-08-22T10:00:00.Z",
    ),
)
def test_rejects_non_utc_or_invalid_timestamps(ts: str) -> None:
    with pytest.raises(ValueError):
        _event(ts=ts)


@pytest.mark.parametrize(
    "override",
    (
        {"adapter": "Claude-Code"},
        {"adapter": ""},
        {"adapter_version": "1.0"},
        {"adapter_version": "v1.0.0"},
        {"record_ref": ""},
        {"raw_type": "x" * 129},
    ),
)
def test_source_fields_are_validated(override: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        ShadowSource(**{**SOURCE, **override})


def test_vocabulary_matches_the_specification() -> None:
    assert ACTORS == ("agent", "user", "tool", "system")
    assert KINDS == (
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
    )
    with pytest.raises(ValueError):
        _event(kind="thought")
    with pytest.raises(ValueError):
        _event(actor="model")


# -- session digest ----------------------------------------------------------


def test_session_sha256_matches_reference_and_pinned_vector() -> None:
    assert SHADOW_SESSION_DOMAIN == "shadow.session.v1"
    assert _reference_session_digest(SESSION_VECTOR_IDS) == SESSION_VECTOR_DIGEST
    assert session_sha256(SESSION_VECTOR_IDS) == SESSION_VECTOR_DIGEST
    assert session_sha256(iter(SESSION_VECTOR_IDS)) == SESSION_VECTOR_DIGEST
    assert session_sha256(reversed(SESSION_VECTOR_IDS)) != SESSION_VECTOR_DIGEST
    assert session_sha256(()) == EMPTY_SESSION_DIGEST
    assert _reference_session_digest(()) == EMPTY_SESSION_DIGEST


@pytest.mark.parametrize("bad", ("ab" * 16, "ab" * 33, ""))
def test_session_sha256_rejects_identifiers_that_are_not_32_bytes(bad: str) -> None:
    with pytest.raises(ValueError, match="32-byte"):
        session_sha256((DIGEST_A, bad))


def test_session_sha256_rejects_non_hex_identifiers() -> None:
    with pytest.raises(ValueError):
        session_sha256(("zz" * 32,))
