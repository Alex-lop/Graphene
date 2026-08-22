"""Fail-closed behavior of the ``ndjson`` adapter and ``materialize``.

Every rejection in docs/SHADOW_ADAPTER_SPEC.md "Fail-closed behavior" is
exercised here, and each assertion checks that the error names the line and
the field or condition at fault.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from graphene.shadow.adapters import (
    ADAPTERS,
    RESERVED_FIELDS,
    AdapterError,
    Draft,
    ParsedSession,
    adapter_for,
    materialize,
)
from graphene.shadow.adapters.ndjson import NdjsonAdapter
from graphene.shadow.events import EVENT_FIELDS, ShadowEvent

ROOT = Path(__file__).parents[3]
SPEC = ROOT / "docs" / "SHADOW_ADAPTER_SPEC.md"
FIXTURE = ROOT / "tests" / "fixtures" / "shadow" / "ndjson" / "session_v1.ndjson"
SOURCE = {
    "adapter": "other-emitter",
    "adapter_version": "2.3.4",
    "record_ref": "line:1",
    "raw_type": "assistant_message",
}
CLAIM = {"matcher": "claims.v1", "category": "checks_pass", "pattern_id": "tests-pass"}


def _record(seq: int, **over: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": "shadow.event.v1",
        "session_id": "sess-1",
        "seq": seq,
        "ts": None,
        "actor": "agent",
        "kind": "message",
        "paths": [],
        "outside_paths": [],
        "tool": None,
        "call_id": None,
        "argv_digest": None,
        "argv_excerpt": None,
        "exit_code": None,
        "check_family": None,
        "excerpt": f"message {seq}",
        "content_digest": f"{seq:02x}" * 32,
        "claim": None,
        "provenance": "observed",
        "derived_from": [],
        "source": {**SOURCE, "record_ref": f"line:{seq}"},
    }
    record.update(over)
    return record


def _event_id(record: dict[str, object]) -> str:
    return ShadowEvent.from_record(record).event_id


def _lines(*records: object) -> bytes:
    return b"".join(json.dumps(record).encode("utf-8") + b"\n" for record in records)


def _parse(data: bytes) -> ParsedSession:
    return NdjsonAdapter().parse(data, repo=None)


def _rejects(data: bytes, message: str) -> None:
    with pytest.raises(AdapterError, match=re.escape(message)):
        _parse(data)


def _spec_example() -> bytes:
    block = re.search(r"```json\n(.*?)```", SPEC.read_text(encoding="utf-8"), re.S)
    assert block is not None, "the adapter spec lost its worked example"
    return block.group(1).encode("utf-8")


# -- registry ----------------------------------------------------------------


def test_registry_holds_only_the_ndjson_adapter() -> None:
    assert set(ADAPTERS) == {"ndjson"}
    adapter = adapter_for("ndjson")
    assert isinstance(adapter, NdjsonAdapter)
    assert adapter is ADAPTERS["ndjson"]
    assert (adapter.name, adapter.version) == ("ndjson", "1.0.0")
    assert issubclass(AdapterError, ValueError)


@pytest.mark.parametrize("name", ("claude-code", "jsonl", "", None, 7))
def test_unknown_format_fails_closed(name: object) -> None:
    with pytest.raises(AdapterError, match=f"unsupported shadow format: {name}"):
        adapter_for(name)  # type: ignore[arg-type]


def test_parse_rejects_non_bytes_and_non_path_repo(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="must be bytes"):
        NdjsonAdapter().parse("{}", repo=None)  # type: ignore[arg-type]
    with pytest.raises(AdapterError, match="repo must be a Path or None"):
        NdjsonAdapter().parse(_lines(_record(1)), repo=str(tmp_path))  # type: ignore[arg-type]
    assert _parse(_lines(_record(1))).raw_record_count == 1
    parsed = NdjsonAdapter().parse(_lines(_record(1)), repo=tmp_path)
    assert parsed.raw_record_count == 1


# -- accepted input ----------------------------------------------------------


def test_spec_worked_example_parses_and_materializes() -> None:
    parsed = _parse(_spec_example())

    assert parsed.session_id == "example-session-1"
    assert parsed.raw_record_count == 5
    assert len(parsed.drafts) == 5
    assert parsed.has_claims is False
    assert parsed.unknown_count == 0
    assert (parsed.adapter, parsed.adapter_version) == ("ndjson", "1.0.0")
    assert [draft.provenance for draft in parsed.drafts] == ["observed"] * 5
    assert all(draft.derived_from == () for draft in parsed.drafts)
    events = materialize(parsed.session_id, parsed.drafts)
    assert [event.seq for event in events] == [1, 2, 3, 4, 5]
    assert [event.kind for event in events] == [
        "message",
        "file_edit",
        "check_run",
        "check_result",
        "message",
    ]
    assert events[2].check_family == "pytest"
    assert events[3].exit_code == 0


def test_fixture_with_supplied_event_ids_round_trips_unchanged() -> None:
    data = FIXTURE.read_bytes()
    supplied = [json.loads(line)["event_id"] for line in data.splitlines()]

    parsed = _parse(data)
    events = materialize(parsed.session_id, parsed.drafts)

    assert parsed.raw_record_count == 30
    assert parsed.has_claims is False
    assert parsed.unknown_count == 1
    assert [event.event_id for event in events] == supplied
    assert [draft.provenance for draft in parsed.drafts].count("inferred") == 1


def test_draft_fields_exclude_assigned_fields_and_keep_source() -> None:
    parsed = _parse(_lines(_record(1)))

    (draft,) = parsed.drafts
    assert set(draft.fields) == set(EVENT_FIELDS) - RESERVED_FIELDS
    assert "event_id" not in draft.fields
    assert draft.fields["source"] == {**SOURCE, "record_ref": "line:1"}
    assert draft.fields["excerpt"] == "message 1"
    assert draft.fields["paths"] == []


def test_derived_from_resolves_to_earlier_draft_indexes() -> None:
    first = _record(1)
    second = _record(2)
    third = _record(
        3,
        kind="claim",
        claim=CLAIM,
        provenance="inferred",
        derived_from=sorted([_event_id(second), _event_id(first)]),
    )

    parsed = _parse(_lines(first, second, third))

    assert parsed.has_claims is True
    assert parsed.drafts[2].provenance == "inferred"
    assert parsed.drafts[2].derived_from == (0, 1)
    assert parsed.drafts[0].derived_from == ()


def test_unknown_records_are_counted_not_dropped() -> None:
    parsed = _parse(
        _lines(
            _record(
                1, kind="unknown", actor="system", excerpt=None, content_digest=None
            ),
            _record(2),
            _record(3, kind="unknown", excerpt=None, content_digest=None),
        )
    )

    assert parsed.unknown_count == 2
    assert parsed.raw_record_count == 3
    assert [draft.fields["kind"] for draft in parsed.drafts] == [
        "unknown",
        "message",
        "unknown",
    ]


def test_missing_final_newline_is_accepted() -> None:
    data = _lines(_record(1), _record(2)).rstrip(b"\n")

    assert _parse(data).raw_record_count == 2


def test_supplied_matching_event_id_is_accepted() -> None:
    record = _record(1)
    record["event_id"] = _event_id(record)

    parsed = _parse(_lines(record))

    assert materialize("sess-1", parsed.drafts)[0].event_id == record["event_id"]


def test_parse_stops_at_the_first_bad_line() -> None:
    _rejects(
        _lines(_record(1), _record(2, kind="dance"), _record(3, actor="ghost")),
        'line 2: unknown kind "dance"',
    )


# -- transport rejections ----------------------------------------------------


def test_blank_lines_are_rejected() -> None:
    _rejects(_lines(_record(1)) + b"\n" + _lines(_record(2)), "line 2: blank line")
    _rejects(_lines(_record(1)) + b"   \n", "line 2: blank line")
    _rejects(_lines(_record(1), _record(2)) + b"\n", "line 3: blank line")
    _rejects(b"\n", "line 1: blank line")


def test_bom_is_rejected() -> None:
    _rejects(b"\xef\xbb\xbf" + _lines(_record(1)), "line 1: UTF-8 BOM is not allowed")


def test_cr_line_endings_are_rejected() -> None:
    crlf = _lines(_record(1)).replace(b"\n", b"\r\n")
    _rejects(crlf, "line 1: CR line ending")
    mixed = _lines(_record(1)) + _lines(_record(2)).replace(b"\n", b"\r\n")
    _rejects(mixed, "line 2: CR line ending")
    _rejects(b'{"a":\r1}\n', "line 1: carriage return inside the record")


def test_invalid_utf8_names_the_line() -> None:
    _rejects(_lines(_record(1)) + b"\xff\xfe\n", "line 2: invalid UTF-8")


def test_empty_input_is_rejected() -> None:
    _rejects(b"", "line 1: empty input")


def test_non_json_and_non_object_lines_are_rejected() -> None:
    _rejects(b"{not json}\n", "line 1: invalid JSON")
    _rejects(_lines(_record(1)) + b"[1, 2]\n", "line 2: record is not a JSON object")
    _rejects(b'"shadow.event.v1"\n', "line 1: record is not a JSON object")
    _rejects(b"42\n", "line 1: record is not a JSON object")
    _rejects(b"null\n", "line 1: record is not a JSON object")


# -- field rejections --------------------------------------------------------


def test_unknown_fields_are_rejected() -> None:
    _rejects(_lines(_record(1, foo=1)), 'line 1: unknown field "foo"')
    _rejects(
        _lines(_record(1), _record(2, foo=1, bar=2)),
        'line 2: unknown fields "bar", "foo"',
    )


@pytest.mark.parametrize("name", EVENT_FIELDS)
def test_every_missing_field_is_named(name: str) -> None:
    record = _record(1)
    del record[name]

    _rejects(_lines(record), f'line 1: missing field "{name}"')


@pytest.mark.parametrize(
    ("over", "message"),
    (
        ({"seq": "1"}, 'field "seq" must be an integer'),
        ({"seq": True}, 'field "seq" must be an integer'),
        ({"seq": 1.0}, 'field "seq" must be an integer'),
        ({"exit_code": "0"}, 'field "exit_code" must be an integer or null'),
        ({"exit_code": False}, 'field "exit_code" must be an integer or null'),
        ({"ts": 5}, 'field "ts" must be a string or null'),
        ({"actor": 1}, 'field "actor" must be a string'),
        ({"kind": None}, 'field "kind" must be a string'),
        ({"session_id": ["sess-1"]}, 'field "session_id" must be a string'),
        ({"paths": "app.py"}, 'field "paths" must be an array of strings'),
        ({"paths": [1]}, 'field "paths" must be an array of strings'),
        ({"outside_paths": None}, 'field "outside_paths" must be an array of strings'),
        ({"derived_from": "abc"}, 'field "derived_from" must be an array of strings'),
        ({"source": []}, 'field "source" must be an object'),
        ({"source": None}, 'field "source" must be an object'),
        ({"claim": "tests-pass"}, 'field "claim" must be an object or null'),
        ({"excerpt": 7}, 'field "excerpt" must be a string or null'),
        ({"event_id": 7}, 'field "event_id" must be a string'),
    ),
)
def test_wrong_json_types_are_rejected(over: dict[str, object], message: str) -> None:
    record = _record(1)
    record.update(over)

    _rejects(_lines(record), f"line 1: {message}")


def test_schema_must_be_exact() -> None:
    message = 'line 1: schema must be "shadow.event.v1"'
    _rejects(_lines(_record(1, schema="shadow.event.v2")), message)
    _rejects(_lines(_record(1, schema="")), message)


def test_unknown_enumerations_are_rejected() -> None:
    _rejects(_lines(_record(1, kind="dance")), 'line 1: unknown kind "dance"')
    _rejects(_lines(_record(1, actor="ghost")), 'line 1: unknown actor "ghost"')
    _rejects(
        _lines(_record(1, provenance="guessed")),
        'line 1: provenance must be "observed" or "inferred"',
    )


def test_seq_must_be_contiguous_from_one() -> None:
    _rejects(_lines(_record(2)), "line 1: seq 2 is not contiguous (expected 1)")
    _rejects(
        _lines(_record(1), _record(3)), "line 2: seq 3 is not contiguous (expected 2)"
    )
    _rejects(
        _lines(_record(1), _record(1)), "line 2: seq 1 is not contiguous (expected 2)"
    )
    _rejects(_lines(_record(0)), "line 1: seq 0 is not contiguous (expected 1)")


def test_session_id_must_not_change() -> None:
    _rejects(
        _lines(_record(1), _record(2, session_id="sess-2")),
        'line 2: session_id changed from "sess-1" to "sess-2"',
    )
    _rejects(_lines(_record(1, session_id="bad id!")), 'line 1: field "session_id"')


@pytest.mark.parametrize(
    ("paths", "field"),
    (
        (["/etc/passwd"], "paths[0]"),
        (["../secret"], "paths[0]"),
        (["app\\greet.py"], "paths[0]"),
        (["app/\0greet.py"], "paths[0]"),
        (["app/b.py", "app/a.py"], "paths"),
        (["app/a.py", "app/a.py"], "paths"),
        ([""], "paths[0]"),
    ),
)
def test_bad_paths_are_rejected(paths: list[str], field: str) -> None:
    data = _lines(_record(1, kind="file_edit", paths=paths))

    _rejects(data, f'line 1: field "{field}"')


def test_unsorted_path_arrays_say_so() -> None:
    _rejects(
        _lines(_record(1, kind="file_edit", paths=["b", "a"])),
        'line 1: field "paths": path and reference arrays must be sorted and unique',
    )
    _rejects(
        _lines(_record(1, kind="file_edit", outside_paths=["~/b", "~/a"])),
        'line 1: field "outside_paths": path and reference arrays must be sorted',
    )


def test_provenance_and_derived_from_must_agree() -> None:
    message = (
        "line 1: inferred events must cite derived_from and observed events must not"
    )
    _rejects(_lines(_record(1, provenance="inferred")), message)
    _rejects(_lines(_record(1, derived_from=["ab" * 32])), message)


def test_supplied_event_id_must_match_the_canonical_encoding() -> None:
    _rejects(
        _lines(_record(1, event_id="0" * 64)),
        "line 1: event_id does not match the canonical encoding",
    )
    record = _record(1)
    record["event_id"] = _event_id(_record(1, excerpt="tampered"))
    _rejects(_lines(record), "line 1: event_id does not match the canonical encoding")
    _rejects(
        _lines(_record(1, event_id="abc")),
        'line 1: field "event_id" must be a lowercase hex SHA-256',
    )
    _rejects(
        _lines(_record(1, event_id="A" * 64)),
        'line 1: field "event_id" must be a lowercase hex SHA-256',
    )


def test_claim_payload_is_present_exactly_on_claims() -> None:
    message = "line 1: claim payload is present exactly on claim events"
    _rejects(_lines(_record(1, claim=CLAIM)), message)
    _rejects(
        _lines(
            _record(1, kind="claim", provenance="inferred", derived_from=["ab" * 32])
        ),
        message,
    )


def test_claims_must_be_inferred() -> None:
    _rejects(
        _lines(_record(1, kind="claim", claim=CLAIM)),
        "line 1: claims are always inferred",
    )


def test_claim_and_source_objects_are_validated_by_field() -> None:
    first = _record(1)
    inferred = _record(
        2,
        kind="claim",
        claim={**CLAIM, "matcher": "claims.v2"},
        provenance="inferred",
        derived_from=[_event_id(first)],
    )
    _rejects(_lines(first, inferred), 'line 2: field "claim.matcher"')
    _rejects(
        _lines(_record(1, source={**SOURCE, "extra": "x"})),
        'line 1: field "source.extra"',
    )
    missing = {key: value for key, value in SOURCE.items() if key != "raw_type"}
    _rejects(_lines(_record(1, source=missing)), 'line 1: field "source.raw_type"')
    _rejects(
        _lines(_record(1, source={**SOURCE, "adapter_version": "v1"})),
        'line 1: field "source.adapter_version"',
    )


def test_check_family_belongs_only_to_check_events() -> None:
    _rejects(
        _lines(_record(1, check_family="pytest")),
        "line 1: check_family belongs only to check events",
    )


def test_value_constraints_name_the_field() -> None:
    _rejects(_lines(_record(1, excerpt="x" * 281)), 'line 1: field "excerpt"')
    _rejects(_lines(_record(1, excerpt="")), 'line 1: field "excerpt"')
    _rejects(
        _lines(_record(1, ts="2026-08-22 10:00:00")),
        'line 1: field "ts": timestamps must be RFC 3339 UTC with a trailing Z',
    )
    _rejects(
        _lines(_record(1, content_digest="zz" * 32)), 'line 1: field "content_digest"'
    )
    _rejects(_lines(_record(1, exit_code=99_999)), 'line 1: field "exit_code"')


def test_derived_from_must_reference_an_earlier_record() -> None:
    first = _record(1)
    second = _record(2)
    unknown = "ab" * 32
    _rejects(
        _lines(
            first,
            _record(
                2,
                kind="claim",
                claim=CLAIM,
                provenance="inferred",
                derived_from=[unknown],
            ),
        ),
        f"line 2: derived_from {unknown} does not refer to an earlier record",
    )
    forward = _record(
        1,
        kind="claim",
        claim=CLAIM,
        provenance="inferred",
        derived_from=[_event_id(second)],
    )
    _rejects(
        _lines(forward, second),
        f"line 1: derived_from {_event_id(second)} does not refer to an earlier record",
    )


# -- materialize -------------------------------------------------------------


def _draft(**over: object) -> Draft:
    fields: dict[str, object] = {
        "ts": None,
        "actor": "agent",
        "kind": "message",
        "paths": (),
        "outside_paths": (),
        "tool": None,
        "call_id": None,
        "argv_digest": None,
        "argv_excerpt": None,
        "exit_code": None,
        "check_family": None,
        "excerpt": "hello",
        "content_digest": "ab" * 32,
        "claim": None,
        "source": SOURCE,
    }
    provenance = over.pop("provenance", "observed")
    derived_from = over.pop("derived_from", ())
    fields.update(over)
    return Draft(fields=fields, provenance=provenance, derived_from=derived_from)  # type: ignore[arg-type]


def test_materialize_numbers_identifies_and_resolves_references() -> None:
    drafts = (
        _draft(),
        _draft(excerpt="second"),
        _draft(
            kind="claim", claim=CLAIM, provenance="inferred", derived_from=(1, 0, 1)
        ),
    )

    events = materialize("sess-9", drafts)

    assert [event.seq for event in events] == [1, 2, 3]
    assert {event.session_id for event in events} == {"sess-9"}
    assert events[2].provenance == "inferred"
    assert events[2].derived_from == tuple(
        sorted((events[0].event_id, events[1].event_id))
    )
    assert events[0].derived_from == ()
    assert all(isinstance(event, ShadowEvent) for event in events)
    assert materialize("sess-9", ()) == ()


def test_materialize_strips_private_fields() -> None:
    events = materialize("sess-9", (_draft(_full_text="All tests pass.", _scratch=1),))

    record = events[0].to_record()
    assert "_full_text" not in record and "_scratch" not in record
    assert set(record) == set(EVENT_FIELDS) | {"event_id"}
    assert events[0] == materialize("sess-9", (_draft(),))[0]


@pytest.mark.parametrize("name", sorted(RESERVED_FIELDS))
def test_materialize_rejects_reserved_fields(name: str) -> None:
    draft = Draft({**_draft().fields, name: "x"}, "observed", ())

    with pytest.raises(AdapterError, match=f'draft 0: field "{name}" is assigned'):
        materialize("sess-9", (draft,))


@pytest.mark.parametrize("reference", (1, 2, -1, True))
def test_materialize_rejects_bad_references(reference: object) -> None:
    drafts = (
        _draft(),
        _draft(
            kind="claim",
            claim=CLAIM,
            provenance="inferred",
            derived_from=(reference,),
        ),
    )
    if reference == 0:
        pytest.skip("zero is a valid earlier reference")

    with pytest.raises(AdapterError, match="draft 1: derived_from index"):
        materialize("sess-9", drafts)


def test_materialize_requires_provenance_to_match_references() -> None:
    with pytest.raises(AdapterError, match="draft 0: inferred drafts cite derived"):
        materialize("sess-9", (_draft(provenance="inferred"),))
    with pytest.raises(AdapterError, match="draft 1: inferred drafts cite derived"):
        materialize("sess-9", (_draft(), _draft(derived_from=(0,))))
    with pytest.raises(AdapterError, match='draft 0: provenance must be "observed"'):
        materialize("sess-9", (_draft(provenance="guessed"),))


def test_materialize_rejects_non_drafts_and_invalid_values() -> None:
    with pytest.raises(AdapterError, match="draft 1: not a Draft record"):
        materialize("sess-9", (_draft(), _draft().fields))  # type: ignore[arg-type]
    with pytest.raises(AdapterError, match="draft 0: fields must be a mapping"):
        materialize("sess-9", (Draft(["excerpt"], "observed", ()),))  # type: ignore[arg-type]
    with pytest.raises(AdapterError, match='draft 0: field "excerpt"'):
        materialize("sess-9", (_draft(excerpt="x" * 281),))
    with pytest.raises(AdapterError, match="draft 0: claim payload is present exactly"):
        materialize("sess-9", (_draft(claim=CLAIM),))


# -- nesting and control characters (review findings) -------------------------


def test_deeply_nested_line_is_a_line_numbered_error_not_a_recursion_error() -> None:
    deep = b"[" * 100_000 + b"]" * 100_000 + b"\n"

    _rejects(deep, "line 1: invalid JSON (nesting too deep)")
    _rejects(_lines(_record(1)) + deep, "line 2: invalid JSON (nesting too deep)")
    nested_field = json.dumps(_record(1)).replace(
        '"claim": null', '"claim": ' + "[" * 100_000 + "]" * 100_000
    )
    _rejects(nested_field.encode() + b"\n", "line 1: invalid JSON (nesting too deep)")


def test_records_nesting_deeper_than_four_levels_are_rejected() -> None:
    message = "line 1: record nests containers deeper than 4 levels"

    _rejects(_lines(_record(1, claim=[[[[[1]]]]])), message)
    _rejects(_lines({**_record(1), "x": {"a": {"b": {"c": {"d": 1}}}}}), message)
    # Three levels is within the bound: the unknown field is what gets named.
    _rejects(_lines({**_record(1), "x": {"a": {"b": 1}}}), 'line 1: unknown field "x"')
    # A valid record (source and the arrays are level two) is unaffected.
    assert _parse(_lines(_record(1))).raw_record_count == 1


@pytest.mark.parametrize(
    ("over", "field"),
    (
        (
            {
                "kind": "file_edit",
                "paths": ["a\n  [claimed-without-evidence] FORGED LINE"],
                "excerpt": None,
                "content_digest": None,
            },
            "paths[0]",
        ),
        (
            {
                "kind": "file_edit",
                "paths": ["a\x1b[31mred"],
                "excerpt": None,
                "content_digest": None,
            },
            "paths[0]",
        ),
        (
            {
                "kind": "file_delete",
                "outside_paths": ["/tmp/x\nHIGH (1)\n  [forged] injected finding"],
                "excerpt": None,
                "content_digest": None,
            },
            "outside_paths[0]",
        ),
        (
            {
                "kind": "file_delete",
                "outside_paths": ["/tmp/\x1b[31mred"],
                "excerpt": None,
                "content_digest": None,
            },
            "outside_paths[0]",
        ),
        ({"tool": "Bash\nINJECTED"}, "tool"),
        ({"tool": "Bash\x00"}, "tool"),
        ({"call_id": "\x1b[31mred"}, "call_id"),
        ({"source": {**SOURCE, "raw_type": "a\nb"}}, "source.raw_type"),
        ({"source": {**SOURCE, "record_ref": "line:1\x1b"}}, "source.record_ref"),
        ({"excerpt": "All tests pass\u2028  high [forged] line"}, "excerpt"),
        ({"excerpt": "Set TOKEN=x in the shell.\tAll tests pass."}, "excerpt"),
        (
            {
                "kind": "command_exec",
                "tool": "Bash",
                "argv_excerpt": "pytest\u2029-q",
                "excerpt": None,
                "content_digest": None,
            },
            "argv_excerpt",
        ),
    ),
)
def test_control_characters_are_rejected_naming_the_field(
    over: dict[str, object], field: str
) -> None:
    _rejects(
        _lines(_record(1, **over)),
        f'line 1: field "{field}": must not contain control characters',
    )
