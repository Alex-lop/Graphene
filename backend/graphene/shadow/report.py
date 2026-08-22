"""The shadow report: one JSON-ready value and one plain-text rendering.

The report leads with three defined ratios, never a score; every finding names
its evidence and the provenance of that evidence; high findings carry the
static governed-mode sentence. ``report_value`` builds the value that the
``--json`` path emits verbatim; ``render_report`` is a pure function of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .lint import LintReport
from .reconstruct import ShadowGraph

TAGLINE = "Your agent said the tests passed. Graphene knows whether they actually ran."
DEFAULT_CLAIMS_VERSION = "claims.v1"
_EVIDENCE_IDS = 2
_EVIDENCE_ID_CHARS = 12
_SEVERITY_GROUPS = (("HIGH", "high"), ("WARN", "warn"), ("INFO", "info"))


def provenance_note(
    segments_version: str, claims_version: str, lint_version: str
) -> str:
    return (
        "observed = present in the transcript; inferred = produced by a heuristic "
        f"({segments_version}, {claims_version}, {lint_version}). Inference is "
        "labeled, never presented as evidence."
    )


def _claims_version(session: Mapping[str, object]) -> str:
    summary = session.get("summary")
    heuristics = summary.get("heuristics") if isinstance(summary, Mapping) else None
    version = heuristics.get("claims") if isinstance(heuristics, Mapping) else None
    return version if isinstance(version, str) and version else DEFAULT_CLAIMS_VERSION


def report_value(
    session: Mapping[str, object], graph: ShadowGraph, lint_report: LintReport
) -> dict[str, object]:
    """JSON-ready report value; ``json.dumps`` accepts it without help."""

    if not isinstance(session, Mapping):
        raise TypeError(
            "session must be a mapping such as ShadowSessionRecord.to_dict()"
        )
    if lint_report.segments_version != graph.segments_version:
        raise ValueError("lint report and graph were produced by different heuristics")
    return {
        "tagline": TAGLINE,
        "shadow": dict(session),
        "graph_summary": {
            "segments_version": graph.segments_version,
            "session_id": graph.session_id,
            "event_count": graph.event_count,
            "observed_count": graph.observed_count,
            "inferred_count": graph.inferred_count,
            "unknown_count": graph.unknown_count,
            "segments": len(graph.segments),
            "edges": len(graph.edges),
        },
        "lint_version": lint_report.lint_version,
        "rules_applied": list(lint_report.rules_applied),
        "ratios": [ratio.model_dump(mode="json") for ratio in lint_report.ratios],
        "findings": [
            finding.model_dump(mode="json") for finding in lint_report.findings
        ],
        "rule_counts": dict(lint_report.rule_counts),
        "coverage_note": lint_report.coverage_note,
        "provenance_note": provenance_note(
            graph.segments_version, _claims_version(session), lint_report.lint_version
        ),
    }


def _require(value: Mapping[str, object], key: str) -> object:
    if key not in value:
        raise ValueError(f"report value is missing {key!r}")
    return value[key]


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    item = _require(value, key)
    if not isinstance(item, Mapping):
        raise ValueError(f"report value {key!r} must be an object")
    return item


def _sequence(value: Mapping[str, object], key: str) -> Sequence[object]:
    item = _require(value, key)
    if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
        raise ValueError(f"report value {key!r} must be an array")
    return item


def _text(value: Mapping[str, object], key: str) -> str:
    item = _require(value, key)
    if not isinstance(item, str):
        raise ValueError(f"report value {key!r} must be a string")
    return item


def _display(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    return "-" if item is None else str(item)


def _evidence(finding: Mapping[str, object]) -> str:
    ids = finding.get("event_ids")
    if not isinstance(ids, Sequence) or isinstance(ids, str) or not ids:
        return "none"
    shown = ids[:_EVIDENCE_IDS]
    return ",".join(str(event_id)[:_EVIDENCE_ID_CHARS] for event_id in shown)


def render_report(value: Mapping[str, object]) -> str:
    """Plain-text rendering of ``report_value`` output; no colour, no score."""

    shadow = _mapping(value, "shadow")
    summary = _mapping(value, "graph_summary")
    ratios = _sequence(value, "ratios")
    findings = _sequence(value, "findings")
    adapter = _display(shadow, "adapter")
    if shadow.get("adapter_version") is not None:
        adapter = f"{adapter} {shadow['adapter_version']}"
    session_id = shadow.get("session_id", summary.get("session_id"))
    lines = [
        "GRAPHENE SHADOW REPORT",
        f'"{_text(value, "tagline")}"',
        f"shadow_id      {_display(shadow, 'shadow_id')}",
        f"adapter        {adapter}",
    ]
    if shadow.get("source_adapter") is not None:
        source = str(shadow["source_adapter"])
        if shadow.get("source_adapter_version") is not None:
            source = f"{source} {shadow['source_adapter_version']}"
        lines.append(f"source_adapter {source}")
    lines += [
        f"session_id     {'-' if session_id is None else session_id}",
        f"source_sha256  {_display(shadow, 'source_sha256')}",
        f"events observed={_display(summary, 'observed_count')} "
        f"inferred={_display(summary, 'inferred_count')} "
        f"unknown={_display(summary, 'unknown_count')}",
        f"segments={_display(summary, 'segments')} edges={_display(summary, 'edges')}",
        "",
        "RATIOS",
    ]
    for ratio in ratios:
        if not isinstance(ratio, Mapping):
            raise ValueError("each ratio must be an object")
    width = max((len(str(ratio.get("key", ""))) for ratio in ratios), default=0)
    for ratio in ratios:
        key = str(ratio.get("key", "?")).ljust(width)
        lines.append(
            f"  {key}  {_display(ratio, 'numerator')}/{_display(ratio, 'denominator')}"
            f"  — {_display(ratio, 'definition')}"
        )
    lines += ["", "FINDINGS"]
    for heading, severity in _SEVERITY_GROUPS:
        group = [
            finding
            for finding in findings
            if isinstance(finding, Mapping) and finding.get("severity") == severity
        ]
        lines.append(f"{heading} ({len(group)})")
        if not group:
            lines.append("  none")
        for finding in group:
            lines.append(
                f"  [{_display(finding, 'rule')}] {_display(finding, 'message')}  "
                f"evidence={_evidence(finding)} basis={_display(finding, 'basis')}"
            )
            if severity == "high":
                lines.append(f"    governed: {_display(finding, 'governed_diff')}")
    lines += [
        "",
        "PROVENANCE",
        _text(value, "provenance_note"),
        "",
        _text(value, "coverage_note"),
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "DEFAULT_CLAIMS_VERSION",
    "TAGLINE",
    "provenance_note",
    "render_report",
    "report_value",
]
