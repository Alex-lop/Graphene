from __future__ import annotations

import json

import pytest

from graphene.shadow.events import ShadowEvent
from graphene.shadow.lint import COVERAGE_NOTE, GOVERNED_CLAIM, GOVERNED_SCOPE, lint
from graphene.shadow.reconstruct import reconstruct
from graphene.shadow.report import TAGLINE, render_report, report_value

_ACTORS = {"message": "user", "check_result": "tool"}
_CLAIM = {"matcher": "claims.v1", "category": "checks_pass", "pattern_id": "tests-pass"}
_PROVENANCE_NOTE = (
    "observed = present in the transcript; inferred = produced by a heuristic "
    "(segments.v1, claims.v1, lint.v1). Inference is labeled, never presented as "
    "evidence."
)


def _event(seq: int, kind: str, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "seq": seq,
        "actor": _ACTORS.get(kind, "agent"),
        "kind": kind,
        "provenance": "observed",
        "source": {
            "adapter": "ndjson",
            "adapter_version": "1.0.0",
            "record_ref": f"line:{seq}",
            "raw_type": "test",
        },
    }
    fields.update(over)
    return ShadowEvent.create(**fields)


def _stream() -> list[ShadowEvent]:
    message = _event(7, "message", actor="agent", excerpt="All tests pass.")
    return [
        _event(1, "message", excerpt="Make the greeting configurable."),
        _event(2, "file_edit", paths=("app/greet.py",)),
        _event(3, "check_run", check_family="pytest", argv_excerpt="pytest -q"),
        _event(4, "check_result", check_family="pytest", exit_code=0),
        _event(5, "install_op", argv_excerpt="uv sync"),
        _event(6, "file_edit", paths=("app/config.py",)),
        message,
        _event(
            8,
            "claim",
            provenance="inferred",
            derived_from=(message.event_id,),
            claim=_CLAIM,
            excerpt=message.excerpt,
        ),
        _event(9, "file_create", paths=(".env",)),
    ]


def _session(**over: object) -> dict[str, object]:
    session: dict[str, object] = {
        "shadow_id": "shadow_" + "a" * 32,
        "adapter": "ndjson",
        "adapter_version": "1.0.0",
        "session_id": "sess-1",
        "source_sha256": "b" * 64,
        "source_bytes": 1234,
        "event_count": 9,
        "session_sha256": "c" * 64,
        "repo_label": None,
        "ingested_at": "2026-08-22T10:00:00Z",
        "summary": {"heuristics": {"claims": "claims.v1"}},
    }
    session.update(over)
    return session


def _value(**session_over: object) -> dict[str, object]:
    events = _stream()
    graph = reconstruct(events)
    return report_value(_session(**session_over), graph, lint(events, graph))


def test_report_value_is_json_ready_and_round_trips():
    value = _value()

    encoded = json.dumps(value, sort_keys=True)
    assert json.loads(encoded) == value
    assert set(value) == {
        "tagline",
        "shadow",
        "graph_summary",
        "lint_version",
        "rules_applied",
        "ratios",
        "findings",
        "rule_counts",
        "coverage_note",
        "provenance_note",
    }
    assert value["tagline"] == TAGLINE
    assert value["shadow"] == _session()
    assert value["graph_summary"] == {
        "segments_version": "segments.v1",
        "session_id": "sess-1",
        "event_count": 9,
        "observed_count": 8,
        "inferred_count": 1,
        "unknown_count": 0,
        "segments": 1,
        "edges": 0,
    }
    assert value["lint_version"] == "lint.v1"
    assert value["coverage_note"] == COVERAGE_NOTE
    assert value["provenance_note"] == _PROVENANCE_NOTE
    assert [ratio["key"] for ratio in value["ratios"]] == [  # type: ignore[index]
        "covered_files",
        "backed_claims",
        "overlap_segments",
    ]
    assert value["rule_counts"] == {
        "claimed-without-evidence": 1,
        "edit-without-check": 2,
        "write-overlap": 0,
        "scope-drift": 1,
        "destructive-unverified": 0,
        "network-or-install": 1,
    }


def test_rendered_report_has_tagline_header_and_counts():
    text = render_report(_value())
    lines = text.splitlines()

    assert lines[0] == "GRAPHENE SHADOW REPORT"
    assert lines[1] == f'"{TAGLINE}"'
    assert TAGLINE in text
    assert "shadow_id      shadow_" + "a" * 32 in text
    assert "adapter        ndjson 1.0.0" in text
    assert "session_id     sess-1" in text
    assert "source_sha256  " + "b" * 64 in text
    assert "events observed=8 inferred=1 unknown=0" in text
    assert "segments=1 edges=0" in text
    assert all(ch.isascii() or ch == "—" for ch in text)


def test_rendered_ratios_carry_values_and_definitions():
    text = render_report(_value())

    assert "RATIOS" in text
    assert (
        "  covered_files     1/3  — changed files whose last edit was followed by "
        "an observed passing check"
    ) in text
    assert (
        "  backed_claims     0/1  — success claims backed by an observed passing "
        "check after the last preceding edit"
    ) in text
    assert (
        "  overlap_segments  0/1  — inferred segments that wrote a path another "
        "segment also wrote"
    ) in text


def test_high_findings_carry_the_governed_sentence_and_evidence_prefixes():
    value = _value()
    text = render_report(value)
    findings = value["findings"]
    assert isinstance(findings, list)
    claim = next(f for f in findings if f["rule"] == "claimed-without-evidence")
    drift = next(f for f in findings if f["rule"] == "scope-drift")

    assert "FINDINGS" in text
    assert "HIGH (2)" in text
    assert "WARN (2)" in text
    assert "INFO (1)" in text
    evidence = ",".join(event_id[:12] for event_id in claim["event_ids"][:2])
    assert (
        f"  [claimed-without-evidence] {claim['message']}  "
        f"evidence={evidence} basis=mixed"
    ) in text
    assert f"    governed: {GOVERNED_CLAIM}" in text
    assert f"    governed: {GOVERNED_SCOPE}" in text
    drift_evidence = drift["event_ids"][0][:12]
    assert f"  [scope-drift] {drift['message']}  evidence={drift_evidence}" in text
    assert "[edit-without-check] app/config.py was last edited at seq 6" in text
    assert "[network-or-install] install_op observed at seq 5: uv sync" in text
    warn_block = text.split("WARN (2)")[1].split("INFO (1)")[0]
    assert "governed:" not in warn_block


def test_rendered_report_ends_with_provenance_note_and_coverage_footer():
    text = render_report(_value())
    lines = text.splitlines()

    assert "PROVENANCE" in lines
    assert lines[lines.index("PROVENANCE") + 1] == _PROVENANCE_NOTE
    assert lines[-1] == COVERAGE_NOTE
    assert text.endswith(COVERAGE_NOTE + "\n")


def test_render_shows_source_adapter_and_empty_groups():
    events = [
        _event(1, "file_edit", paths=("a.py",)),
        _event(2, "check_result", exit_code=0),
    ]
    graph = reconstruct(events)
    value = report_value(
        _session(source_adapter="claude-code", source_adapter_version="0.1.0"),
        graph,
        lint(events, graph),
    )

    text = render_report(value)

    assert "source_adapter claude-code 0.1.0" in text
    assert "HIGH (0)\n  none\n" in text
    assert "WARN (0)\n  none\n" in text
    assert "INFO (0)\n  none\n" in text
    assert "governed:" not in text


def test_render_report_accepts_the_json_round_trip_of_the_value():
    value = _value()

    assert render_report(json.loads(json.dumps(value))) == render_report(value)


def test_render_report_fails_closed_on_malformed_values():
    value = _value()
    missing = {key: item for key, item in value.items() if key != "coverage_note"}
    with pytest.raises(ValueError, match="missing 'coverage_note'"):
        render_report(missing)
    with pytest.raises(ValueError, match="'ratios' must be an array"):
        render_report({**value, "ratios": "1/2"})
    with pytest.raises(ValueError, match="'shadow' must be an object"):
        render_report({**value, "shadow": None})


def test_report_value_fails_closed_on_mismatched_inputs():
    events = _stream()
    graph = reconstruct(events)
    report = lint(events, graph)
    other = graph.model_copy(update={"segments_version": "segments.v0"})

    with pytest.raises(ValueError, match="different heuristics"):
        report_value(_session(), other, report)
    with pytest.raises(TypeError, match="mapping"):
        report_value("not a session", graph, report)  # type: ignore[arg-type]
