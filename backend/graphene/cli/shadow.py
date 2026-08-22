"""``graphene shadow``: observe, reconstruct, lint, and export agent sessions.

The shadow store is a separate SQLite file beside the mission store under the
Graphene state directory, with its own schema ledger; these commands never
open the mission store. Every failure is one ``SHADOW_ERROR: <message>`` line
on stderr with exit status 1, and adapter messages are shown verbatim because
the precise locator is the fail-closed promise. ``--json`` on a subcommand
selects the canonical one-line JSON output exactly like the global flag.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from ..hashing import canonical_json_bytes
from ..shadow.events import ShadowEvent
from ..shadow.export import ShadowExportError, export_capsule
from ..shadow.lint import RULES, LintReport, lint
from ..shadow.reconstruct import ShadowGraph, graph_to_dot, reconstruct
from ..shadow.report import render_report, report_value
from ..shadow.store import (
    SHADOW_DB_FILENAME,
    ShadowSessionRecord,
    ShadowStore,
    ShadowStoreError,
)
from ..shadow.verify import CapsuleVerifyError
from .mission import MissionCliError, _state_root

FORMATS: tuple[str, ...] = ("claude-code", "ndjson")
_SHADOW_ID = re.compile(r"^shadow_[0-9a-f]{32}$")


class ShadowCliError(RuntimeError):
    pass


def register_commands(commands: argparse._SubParsersAction) -> None:
    shadow = commands.add_parser(
        "shadow",
        allow_abbrev=False,
        help="observe, reconstruct, lint, and export a finished agent session",
        description=(
            "Shadow Agent: code review for agent sessions Graphene did not govern. "
            "Reads a transcript, never the mission store; inference is labeled."
        ),
    )
    actions = shadow.add_subparsers(dest="shadow_action", required=True)

    ingest = actions.add_parser(
        "ingest",
        allow_abbrev=False,
        help="normalize one session transcript into the shadow store",
    )
    ingest.add_argument("path", type=Path, help="transcript file to ingest")
    ingest.add_argument(
        "--format", required=True, choices=FORMATS, help="transcript format"
    )
    ingest.add_argument(
        "--repo", type=Path, help="repository root used to classify touched paths"
    )

    report = actions.add_parser(
        "report", allow_abbrev=False, help="ratios and findings for one session"
    )
    report.add_argument("shadow_id")
    _json_flag(report)

    lint_command = actions.add_parser(
        "lint", allow_abbrev=False, help="run Trust Lint rules over one session"
    )
    lint_command.add_argument("shadow_id")
    lint_command.add_argument(
        "--rule",
        action="append",
        choices=RULES,
        help="restrict to this rule (repeatable); ratios are always computed",
    )
    _json_flag(lint_command)

    graph = actions.add_parser(
        "graph", allow_abbrev=False, help="export the inferred segment graph"
    )
    graph.add_argument("shadow_id")
    graph_format = graph.add_mutually_exclusive_group(required=True)
    graph_format.add_argument(
        "--json",
        action="store_const",
        const="json",
        dest="graph_format",
        help="emit the graph as one canonical JSON line",
    )
    graph_format.add_argument(
        "--dot",
        action="store_const",
        const="dot",
        dest="graph_format",
        help="emit the graph as Graphviz DOT",
    )

    export = actions.add_parser(
        "export",
        allow_abbrev=False,
        help="write a redacted, self-verifying .graphene-shadow capsule",
    )
    export.add_argument("shadow_id")
    export.add_argument(
        "--output",
        required=True,
        type=Path,
        help="directory that receives the new <shadow_id>.graphene-shadow capsule",
    )

    actions.add_parser(
        "list", allow_abbrev=False, help="one line per ingested shadow session"
    )

    verify = actions.add_parser(
        "verify", allow_abbrev=False, help="re-verify one stored session"
    )
    verify.add_argument("shadow_id")


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        dest="shadow_json",
        help="emit one canonical JSON line",
    )


def _store() -> ShadowStore:
    try:
        root = _state_root()
    except MissionCliError as error:
        raise ShadowCliError(str(error)) from error
    return ShadowStore(root / SHADOW_DB_FILENAME)


def _shadow_id(value: str) -> str:
    if not _SHADOW_ID.match(value):
        raise ShadowCliError(
            f"shadow_id must look like shadow_<32 hex characters>, got {value!r}"
        )
    return value


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _fields_line(value: dict[str, object]) -> str:
    fields = " ".join(
        f"{key}={item}"
        for key, item in value.items()
        if not isinstance(item, (dict, list, tuple))
    )
    return f"GRAPHENE {fields}\n"


def _load(
    store: ShadowStore, shadow_id: str
) -> tuple[ShadowSessionRecord, tuple[ShadowEvent, ...], ShadowGraph]:
    record = store.session(shadow_id)
    events = store.events(shadow_id)
    return record, events, reconstruct(events)


def _ingest(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    # The adapters are loaded only by ingest; every other subcommand reads the
    # store without them.
    from ..shadow.ingest import ingest_file

    repo = _absolute(args.repo) if args.repo is not None else None
    result = ingest_file(_store(), _absolute(args.path), fmt=args.format, repo=repo)
    text = _fields_line(
        {
            "shadow_id": result.shadow_id,
            "created": result.created,
            "events": result.event_count,
            "observed": result.observed_count,
            "inferred": result.inferred_count,
            "claims": result.claim_count,
            "unknown": result.unknown_count,
            "elapsed_ms": result.elapsed_ms,
        }
    )
    return result.model_dump(mode="json"), text


def _report(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    record, events, graph = _load(_store(), _shadow_id(args.shadow_id))
    value = report_value(record.to_dict(), graph, lint(events, graph))
    return value, render_report(value)


def render_lint(shadow_id: str, report: LintReport) -> str:
    """Compact, grep-friendly listing: header, ratios, one line per finding."""

    lines = [
        f"GRAPHENE SHADOW LINT shadow_id={shadow_id} lint={report.lint_version} "
        f"segments={report.segments_version}",
        f"rules_applied={','.join(report.rules_applied)}",
    ]
    for ratio in report.ratios:
        lines.append(
            f"ratio {ratio.key}={ratio.numerator}/{ratio.denominator}  "
            f"{ratio.definition}"
        )
    lines.append(f"findings={len(report.findings)}")
    for finding in report.findings:
        seqs = ",".join(str(seq) for seq in finding.seqs) or "-"
        lines.append(
            f"  {finding.severity} [{finding.rule}] seq={seqs} "
            f"basis={finding.basis} {finding.message}"
        )
        if finding.governed_diff is not None:
            lines.append(f"    governed: {finding.governed_diff}")
    lines.append(
        "counts "
        + " ".join(f"{rule}={count}" for rule, count in report.rule_counts.items())
    )
    lines.append(report.coverage_note)
    return "\n".join(lines) + "\n"


def _lint(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    shadow_id = _shadow_id(args.shadow_id)
    _, events, graph = _load(_store(), shadow_id)
    report = lint(events, graph, rules=args.rule or None)
    return report.model_dump(mode="json"), render_lint(shadow_id, report)


def _graph(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    _, _, graph = _load(_store(), _shadow_id(args.shadow_id))
    return graph.model_dump(mode="json"), graph_to_dot(graph)


def _export(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    result = export_capsule(
        _store(), _shadow_id(args.shadow_id), _absolute(args.output)
    )
    return result, _fields_line({"capsule_dir": result["capsule_dir"]})


def _list(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    sessions = _store().sessions()
    text = "".join(
        f"{record.shadow_id} adapter={record.adapter} {record.adapter_version} "
        f"session_id={record.session_id} events={record.event_count} "
        f"ingested_at={record.ingested_at}\n"
        for record in sessions
    )
    return {"sessions": [record.to_dict() for record in sessions]}, text


def _verify(args: argparse.Namespace) -> tuple[dict[str, object], str]:
    value = _store().verify(_shadow_id(args.shadow_id))
    return value, _fields_line(value)


_DISPATCH = {
    "ingest": _ingest,
    "report": _report,
    "lint": _lint,
    "graph": _graph,
    "export": _export,
    "list": _list,
    "verify": _verify,
}


def _wants_json(args: argparse.Namespace, json_mode: bool | None) -> bool:
    selected = getattr(args, "json_mode", False) if json_mode is None else json_mode
    return (
        bool(selected)
        or bool(getattr(args, "shadow_json", False))
        or getattr(args, "graph_format", None) == "json"
    )


def handle(args: argparse.Namespace, *, json_mode: bool | None = None) -> int:
    action = getattr(args, "shadow_action", None)
    if action not in _DISPATCH:
        sys.stderr.write(f"SHADOW_ERROR: unknown shadow action {action!r}\n")
        return 1
    try:
        value, text = _DISPATCH[action](args)
    except KeyboardInterrupt:
        return 130
    except (
        ShadowCliError,
        ShadowStoreError,
        ShadowExportError,
        CapsuleVerifyError,
        ValueError,
        OSError,
    ) as error:
        # AdapterError is a ValueError: its locator-bearing message is shown
        # verbatim.
        sys.stderr.write(f"SHADOW_ERROR: {error}\n")
        return 1
    if _wants_json(args, json_mode):
        sys.stdout.write(canonical_json_bytes(value).decode() + "\n")
    else:
        sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """A standalone parser for tests; ``graphene`` itself registers into main."""

    parser = argparse.ArgumentParser(prog="graphene", allow_abbrev=False)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    register_commands(parser.add_subparsers(dest="command", required=True))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return handle(args, json_mode=args.json_mode)


__all__ = [
    "FORMATS",
    "ShadowCliError",
    "build_parser",
    "handle",
    "main",
    "register_commands",
    "render_lint",
]
