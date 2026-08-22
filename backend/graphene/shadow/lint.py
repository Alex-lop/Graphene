"""Trust Lint over a shadow stream and its reconstruction (``lint.v1``).

Six named rules; each finding carries one sentence, the events it rests on,
and the provenance of that evidence. ``claimed-without-evidence`` (high): a
claim is backed only by an observed passing check between the last preceding
write and the claim. ``edit-without-check`` (warn): a path's last write has no
observed passing check after it. ``write-overlap`` (warn): a path was written
from two or more inferred segments. ``scope-drift`` (high): a write touched a
path outside the repository or a sensitive path. ``destructive-unverified``
(warn): a delete with no observed passing check after it. ``network-or-install``
(info): every install or network operation, surfaced and not judged. The three
ratios are always computed, even when ``rules`` narrows the findings. There is
no composite score and no numeric governed-run estimate.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..models import FrozenModel
from .events import ShadowEvent
from .reconstruct import ShadowGraph

LINT_VERSION = "lint.v1"
RULES: tuple[str, ...] = (
    "claimed-without-evidence",
    "edit-without-check",
    "write-overlap",
    "scope-drift",
    "destructive-unverified",
    "network-or-install",
)
Severity = Literal["high", "warn", "info"]
Basis = Literal["observed", "mixed", "inferred"]
RatioKey = Literal["covered_files", "backed_claims", "overlap_segments"]

COVERAGE_NOTE = (
    "Coverage is coarse in v0: a file counts as covered when an observed passing "
    "check ran after the file's last edit. Graphene did not inspect which tests "
    "exercise which file."
)
GOVERNED_CLAIM = (
    "Under Graphene's governed mode, this claim would have required a trusted "
    "output-bound check attestation and could not have reached DONE."
)
GOVERNED_SCOPE = (
    "Under Graphene's governed mode, this write would have been outside the "
    "task's leased scope and the publication would have been rejected."
)
RATIO_DEFINITIONS: dict[str, str] = {
    "covered_files": (
        "changed files whose last edit was followed by an observed passing check"
    ),
    "backed_claims": (
        "success claims backed by an observed passing check after the last "
        "preceding edit"
    ),
    "overlap_segments": (
        "inferred segments that wrote a path another segment also wrote"
    ),
}

_SEVERITY: dict[str, Severity] = {
    "claimed-without-evidence": "high",
    "edit-without-check": "warn",
    "write-overlap": "warn",
    "scope-drift": "high",
    "destructive-unverified": "warn",
    "network-or-install": "info",
}
_SEVERITY_RANK = {"high": 0, "warn": 1, "info": 2}
_EDIT_KINDS = frozenset({"file_edit", "file_create"})
_WRITE_KINDS = frozenset({"file_edit", "file_create", "file_delete"})
_SURFACED_KINDS = frozenset({"install_op", "network_op"})
_KEY_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".jks"})
_SSH_KEY_PREFIXES = ("id_rsa", "id_ed25519")
_CI_DIRS = (".github/workflows/", ".circleci/")
_CI_FILES = frozenset({".gitlab-ci.yml", "Jenkinsfile", ".travis.yml"})
_LOCKFILES = frozenset(
    {
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "go.sum",
        "Gemfile.lock",
        "composer.lock",
    }
)


class Finding(FrozenModel):
    rule: str
    severity: Severity
    message: str
    event_ids: tuple[str, ...]
    seqs: tuple[int, ...]
    paths: tuple[str, ...]
    segment_ids: tuple[str, ...]
    basis: Basis
    governed_diff: str | None

    @model_validator(mode="after")
    def governed_only_on_high(self) -> Finding:
        if self.rule not in RULES:
            raise ValueError(f"unknown lint rule: {self.rule}")
        if (self.severity == "high") != (self.governed_diff is not None):
            raise ValueError("governed_diff is present exactly on high findings")
        return self


class Ratio(FrozenModel):
    key: RatioKey
    numerator: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    definition: str

    @model_validator(mode="after")
    def bounded(self) -> Ratio:
        if self.numerator > self.denominator:
            raise ValueError("a ratio numerator cannot exceed its denominator")
        return self


class LintReport(FrozenModel):
    lint_version: str
    segments_version: str
    rules_applied: tuple[str, ...]
    ratios: tuple[Ratio, Ratio, Ratio]
    findings: tuple[Finding, ...]
    rule_counts: dict[str, int]
    coverage_note: str

    @model_validator(mode="after")
    def shape_is_consistent(self) -> LintReport:
        keys = tuple(ratio.key for ratio in self.ratios)
        if keys != ("covered_files", "backed_claims", "overlap_segments"):
            raise ValueError(
                "ratios must be covered_files, backed_claims, overlap_segments"
            )
        for finding in self.findings:
            if finding.rule not in self.rules_applied:
                raise ValueError("findings may only come from applied rules")
        return self


def sensitive_reason(path: str) -> str | None:
    """Why a repository path counts as sensitive for scope-drift, or None."""

    name = PurePosixPath(path).name
    if name == ".env" or name.startswith(".env."):
        return "environment file"
    if PurePosixPath(path).suffix in _KEY_SUFFIXES:
        return "key material"
    if name.startswith(_SSH_KEY_PREFIXES):
        return "ssh key"
    lowered = path.lower()
    if "secret" in lowered or "credential" in lowered:
        return "secret-like name"
    if path.startswith(_CI_DIRS) or name in _CI_FILES:
        return "ci configuration"
    if name in _LOCKFILES:
        return "lockfile"
    return None


def _is_passing_check(event: ShadowEvent) -> bool:
    return (
        event.kind == "check_result"
        and event.provenance == "observed"
        and event.exit_code == 0
    )


class _Context:
    """Indexes over one verified stream; fails closed when the graph disagrees."""

    def __init__(self, events: tuple[ShadowEvent, ...], graph: ShadowGraph) -> None:
        if not events:
            raise ValueError("cannot lint an empty shadow session")
        for event in events:
            if not isinstance(event, ShadowEvent):
                raise TypeError("lint accepts only verified shadow events")
        session_id = events[0].session_id
        for index, event in enumerate(events, start=1):
            if event.seq != index:
                raise ValueError(
                    f"shadow event seq {event.seq} breaks contiguity at {index}"
                )
            if event.session_id != session_id:
                raise ValueError(
                    "shadow session identifiers must not change mid-stream"
                )
        if graph.session_id != session_id or graph.event_count != len(events):
            raise ValueError("shadow graph does not describe the supplied events")
        for entry in graph.timeline:
            if events[entry.seq - 1].event_id != entry.event_id:
                raise ValueError(
                    "shadow graph timeline disagrees with the stream at seq "
                    f"{entry.seq}"
                )
        self.events = events
        self.seq_of_id = {event.event_id: event.seq for event in events}
        self.segment_of: dict[int, str] = {}
        for segment in graph.segments:
            for seq in range(segment.start_seq, segment.end_seq + 1):
                self.segment_of[seq] = segment.segment_id
        self.segment_count = len(graph.segments)
        self.passing_checks = [
            event.seq for event in events if _is_passing_check(event)
        ]
        self.write_seqs = [event.seq for event in events if event.kind in _WRITE_KINDS]

    def passing_check_between(self, lower: int, upper: int) -> bool:
        """True when an observed passing check has lower < seq < upper."""

        start = bisect_right(self.passing_checks, lower)
        return start < len(self.passing_checks) and self.passing_checks[start] < upper

    def passing_check_after(self, seq: int) -> bool:
        return bisect_right(self.passing_checks, seq) < len(self.passing_checks)

    def last_write_before(self, seq: int) -> int:
        position = bisect_left(self.write_seqs, seq)
        return self.write_seqs[position - 1] if position else 0

    def seqs_for(self, event_ids: Iterable[str]) -> tuple[int, ...]:
        return tuple(
            sorted(
                self.seq_of_id[event_id]
                for event_id in event_ids
                if event_id in self.seq_of_id
            )
        )

    def segments_for(self, seqs: Iterable[int]) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for seq in sorted(seqs):
            seen.setdefault(self.segment_of[seq], None)
        return tuple(seen)


def _claimed_without_evidence(ctx: _Context) -> tuple[list[Finding], int, int]:
    findings: list[Finding] = []
    backed = total = 0
    for event in ctx.events:
        if event.kind != "claim":
            continue
        total += 1
        last_edit = ctx.last_write_before(event.seq)
        if ctx.passing_check_between(last_edit, event.seq):
            backed += 1
            continue
        category = event.claim.category if event.claim is not None else "unknown"
        excerpt = event.excerpt or "<no excerpt>"
        event_ids = (event.event_id, *event.derived_from)
        seqs = ctx.seqs_for(event_ids)
        if last_edit:
            detail = (
                f" has no observed passing check after the last edit (seq {last_edit})."
            )
        else:
            # Seqs are 1-based; 0 is the "no write yet" sentinel, never an event.
            detail = (
                ": no edit precedes this claim; no observed passing check "
                "precedes it either."
            )
        findings.append(
            Finding(
                rule="claimed-without-evidence",
                severity="high",
                message=f'Claim "{excerpt}" ({category}){detail}',
                event_ids=event_ids,
                seqs=seqs,
                paths=(),
                segment_ids=ctx.segments_for(seqs),
                basis="mixed",
                governed_diff=GOVERNED_CLAIM,
            )
        )
    return findings, backed, total


def _edit_without_check(ctx: _Context) -> tuple[list[Finding], int, int]:
    last_write: dict[str, ShadowEvent] = {}
    for event in ctx.events:
        if event.kind in _EDIT_KINDS:
            for path in event.paths:
                last_write[path] = event
    findings: list[Finding] = []
    ordered = sorted(last_write.items(), key=lambda item: (item[1].seq, item[0]))
    for path, event in ordered:
        if ctx.passing_check_after(event.seq):
            continue
        findings.append(
            Finding(
                rule="edit-without-check",
                severity="warn",
                message=(
                    f"{path} was last edited at seq {event.seq} and no observed "
                    "check passed afterwards."
                ),
                event_ids=(event.event_id,),
                seqs=(event.seq,),
                paths=(path,),
                segment_ids=(ctx.segment_of[event.seq],),
                basis=event.provenance,
                governed_diff=None,
            )
        )
    total = len(last_write)
    return findings, total - len(findings), total


def _write_overlap(ctx: _Context) -> list[Finding]:
    writes: dict[str, list[ShadowEvent]] = {}
    for event in ctx.events:
        if event.kind in _WRITE_KINDS:
            for path in event.paths:
                writes.setdefault(path, []).append(event)
    findings: list[Finding] = []
    ordered = sorted(writes.items(), key=lambda item: (item[1][0].seq, item[0]))
    for path, events in ordered:
        segment_ids = ctx.segments_for(event.seq for event in events)
        if len(segment_ids) < 2:
            continue
        findings.append(
            Finding(
                rule="write-overlap",
                severity="warn",
                message=(
                    f"{path} was written from {len(segment_ids)} inferred segments "
                    f"({', '.join(segment_ids)}); under a governed mission these "
                    "would have been separate leased tasks and the second write "
                    "would have been fenced."
                ),
                event_ids=tuple(event.event_id for event in events),
                seqs=tuple(event.seq for event in events),
                paths=(path,),
                segment_ids=segment_ids,
                basis="inferred",
                governed_diff=None,
            )
        )
    return findings


def _scope_drift(ctx: _Context) -> list[Finding]:
    findings: list[Finding] = []
    for event in ctx.events:
        if event.kind not in _WRITE_KINDS:
            continue
        offending: list[tuple[str, str]] = [
            (path, "outside repository") for path in event.outside_paths
        ]
        for path in event.paths:
            reason = sensitive_reason(path)
            if reason is not None:
                offending.append((path, f"sensitive: {reason}"))
        if not offending:
            continue
        described = "; ".join(f"{path} ({reason})" for path, reason in offending)
        findings.append(
            Finding(
                rule="scope-drift",
                severity="high",
                message=f"{event.kind} at seq {event.seq} wrote {described}.",
                event_ids=(event.event_id,),
                seqs=(event.seq,),
                paths=tuple(path for path, _ in offending),
                segment_ids=(ctx.segment_of[event.seq],),
                basis=event.provenance,
                governed_diff=GOVERNED_SCOPE,
            )
        )
    return findings


def _destructive_unverified(ctx: _Context) -> list[Finding]:
    findings: list[Finding] = []
    for event in ctx.events:
        if event.kind != "file_delete" or ctx.passing_check_after(event.seq):
            continue
        paths = event.paths or event.outside_paths
        named = ", ".join(paths) if paths else "<no path recorded>"
        findings.append(
            Finding(
                rule="destructive-unverified",
                severity="warn",
                message=(
                    f"{named} deleted at seq {event.seq} with no observed check "
                    "afterwards."
                ),
                event_ids=(event.event_id,),
                seqs=(event.seq,),
                paths=tuple(paths),
                segment_ids=(ctx.segment_of[event.seq],),
                basis=event.provenance,
                governed_diff=None,
            )
        )
    return findings


def _network_or_install(ctx: _Context) -> list[Finding]:
    findings: list[Finding] = []
    for event in ctx.events:
        if event.kind not in _SURFACED_KINDS:
            continue
        excerpt = event.argv_excerpt or "no excerpt"
        findings.append(
            Finding(
                rule="network-or-install",
                severity="info",
                message=(
                    f"{event.kind} {event.provenance} at seq {event.seq}: {excerpt} "
                    "(surfaced, not judged)."
                ),
                event_ids=(event.event_id,),
                seqs=(event.seq,),
                paths=tuple(event.paths) + tuple(event.outside_paths),
                segment_ids=(ctx.segment_of[event.seq],),
                basis=event.provenance,
                governed_diff=None,
            )
        )
    return findings


def _select_rules(rules: Iterable[str] | None) -> tuple[str, ...]:
    if rules is None:
        return RULES
    requested = tuple(rules)
    unknown = sorted(set(requested) - set(RULES))
    if unknown:
        raise ValueError(f"unknown lint rule: {', '.join(unknown)}")
    selected = tuple(rule for rule in RULES if rule in requested)
    if not selected:
        raise ValueError("at least one lint rule must be selected")
    return selected


def lint(
    events: Sequence[ShadowEvent],
    graph: ShadowGraph,
    *,
    rules: Iterable[str] | None = None,
) -> LintReport:
    """Apply ``lint.v1``; ratios cover the whole stream regardless of ``rules``."""

    applied = _select_rules(rules)
    ctx = _Context(tuple(events), graph)
    claim_findings, backed, claims = _claimed_without_evidence(ctx)
    edit_findings, covered, changed = _edit_without_check(ctx)
    overlap_findings = _write_overlap(ctx)
    by_rule: dict[str, list[Finding]] = {
        "claimed-without-evidence": claim_findings,
        "edit-without-check": edit_findings,
        "write-overlap": overlap_findings,
        "scope-drift": _scope_drift(ctx),
        "destructive-unverified": _destructive_unverified(ctx),
        "network-or-install": _network_or_install(ctx),
    }
    overlapping = {
        segment_id for finding in overlap_findings for segment_id in finding.segment_ids
    }
    findings = sorted(
        (finding for rule in applied for finding in by_rule[rule]),
        key=lambda finding: (
            _SEVERITY_RANK[finding.severity],
            min(finding.seqs) if finding.seqs else 0,
            RULES.index(finding.rule),
            finding.message,
        ),
    )
    return LintReport(
        lint_version=LINT_VERSION,
        segments_version=graph.segments_version,
        rules_applied=applied,
        ratios=(
            Ratio(
                key="covered_files",
                numerator=covered,
                denominator=changed,
                definition=RATIO_DEFINITIONS["covered_files"],
            ),
            Ratio(
                key="backed_claims",
                numerator=backed,
                denominator=claims,
                definition=RATIO_DEFINITIONS["backed_claims"],
            ),
            Ratio(
                key="overlap_segments",
                numerator=len(overlapping),
                denominator=ctx.segment_count,
                definition=RATIO_DEFINITIONS["overlap_segments"],
            ),
        ),
        findings=tuple(findings),
        rule_counts={rule: len(by_rule[rule]) for rule in applied},
        coverage_note=COVERAGE_NOTE,
    )


__all__ = [
    "COVERAGE_NOTE",
    "GOVERNED_CLAIM",
    "GOVERNED_SCOPE",
    "LINT_VERSION",
    "RATIO_DEFINITIONS",
    "RULES",
    "Basis",
    "Finding",
    "LintReport",
    "Ratio",
    "Severity",
    "lint",
    "sensitive_reason",
]
