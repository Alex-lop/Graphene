"""Redacted, self-verifying export of one shadow session (``capsule.v1``).

A capsule is a new ``<shadow_id>.graphene-shadow`` directory holding the
verified event stream, the ``segments.v1`` reconstruction, the ``lint.v1``
report, the rendered text report, a ``VERIFY.md`` with the exact commands that
re-derive every digest, and a manifest that pins every other file by SHA-256
and size. Nothing leaves the store that did not enter it redacted, so the
ingest-time redaction is the export-time redaction. ``events.ndjson`` is
canonical ``shadow.event.v1`` lines in seq order and re-ingests to the same
``shadow_id`` because the stream already carries its inferred claims.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from ..hashing import canonical_json_bytes, sha256_hex
from .events import SHADOW_EVENT_SCHEMA, SHADOW_SESSION_DOMAIN, ShadowEvent
from .lint import LintReport, lint
from .reconstruct import ShadowGraph, reconstruct
from .report import DEFAULT_CLAIMS_VERSION, render_report, report_value
from .store import ShadowStore

CAPSULE_SCHEMA = "graphene.shadow.capsule.v1"
CAPSULE_SUFFIX = ".graphene-shadow"
MANIFEST_NAME = "manifest.json"
EVENTS_NAME = "events.ndjson"
GRAPH_NAME = "graph.json"
LINT_NAME = "lint.json"
REPORT_NAME = "report.txt"
VERIFY_NAME = "VERIFY.md"
# Every file the manifest pins, in the order they are written.
CAPSULE_FILES: tuple[str, ...] = (
    EVENTS_NAME,
    GRAPH_NAME,
    LINT_NAME,
    REPORT_NAME,
    VERIFY_NAME,
)
REDACTION_NOTE = (
    "ingest-time; no prompts, source bytes, command output, environment, or "
    "credentials are present"
)
_DIR_MODE = 0o700
_FILE_MODE = 0o600


class ShadowExportError(RuntimeError):
    pass


def claims_version(session: Mapping[str, object]) -> str:
    """The claim matcher recorded at ingest, or the default when absent."""

    summary = session.get("summary")
    heuristics = summary.get("heuristics") if isinstance(summary, Mapping) else None
    version = heuristics.get("claims") if isinstance(heuristics, Mapping) else None
    return version if isinstance(version, str) and version else DEFAULT_CLAIMS_VERSION


def capsule_name(shadow_id: str) -> str:
    return f"{shadow_id}{CAPSULE_SUFFIX}"


def events_ndjson(events: tuple[ShadowEvent, ...]) -> bytes:
    """One canonical ``shadow.event.v1`` record per line, in seq order."""

    return b"".join(canonical_json_bytes(event.to_record()) + b"\n" for event in events)


def verify_markdown(manifest: Mapping[str, object]) -> str:
    """The human procedure that re-derives every digest in the capsule."""

    shadow_id = str(manifest["shadow_id"])
    heuristics = manifest["heuristics"]
    if not isinstance(heuristics, Mapping):
        raise ShadowExportError("manifest heuristics must be an object")
    name = capsule_name(shadow_id)
    lines = [
        "# Verifying this capsule",
        "",
        f"Capsule `{name}`, schema `{manifest['schema']}`.",
        "",
        "Everything here was derived from the redacted shadow store of work that",
        "Graphene observed but did not govern. `graph.json` and `lint.json` are",
        "reconstructions and say so on every record; nothing in this directory is",
        "mission evidence.",
        "",
        "Run the commands below from the directory that contains the capsule.",
        "",
        "## 1. Recompute every digest",
        "",
        "```bash",
        f"uv run --frozen python -m graphene.shadow.verify {name}",
        "```",
        "",
        "The verifier fails closed on the first mismatch. It recomputes, in order:",
        "",
        f"- every line's `event_id` in `{EVENTS_NAME}` from the documented",
        f'  `{SHADOW_EVENT_SCHEMA}` encoding: SHA-256 of `"{SHADOW_EVENT_SCHEMA}"`,',
        "  a NUL byte, the big-endian 64-bit field count, then for each field in",
        "  ascending byte order its length-prefixed name and length-prefixed",
        "  canonical JSON value (sorted keys, `,`/`:` separators, UTF-8);",
        f'- the session digest: SHA-256 of `"{SHADOW_SESSION_DOMAIN}"`, a NUL byte,',
        "  the big-endian 64-bit event count, then each 32-byte `event_id` in seq",
        "  order prefixed by its big-endian 64-bit length;",
        "- the SHA-256 and byte size of every file listed in `manifest.json`, and",
        "  that no unlisted file is present;",
        "- the `shadow_id`: `shadow_` plus the first 32 hex characters of the",
        "  SHA-256 of the canonical JSON object `{adapter, adapter_version,",
        "  session_sha256}`;",
        f"- that `{GRAPH_NAME}` and `{LINT_NAME}` equal a fresh "
        f"`{heuristics['segments']}` and `{heuristics['lint']}` run over "
        f"`{EVENTS_NAME}`.",
        "",
        'Expected output is one JSON line containing `"verified":true` and',
        f'`"shadow_id":"{shadow_id}"`.',
        "",
        "## 2. Re-ingest the stream",
        "",
        "```bash",
        f"uv run --frozen graphene shadow ingest {name}/{EVENTS_NAME} --format ndjson",
        "```",
        "",
        f"This prints `shadow_id={shadow_id}` again: the stream already contains",
        "its claim events, so no claim extraction and no renumbering occurs and",
        "the same normalized events yield the same identifier.",
        "",
        "## Expected values",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| `shadow_id` | `{shadow_id}` |",
        f"| `session_id` | `{manifest['session_id']}` |",
        f"| `adapter` | `{manifest['adapter']} {manifest['adapter_version']}` |",
        f"| `source_adapter` | `{manifest['source_adapter']}` |",
        f"| `event_count` | `{manifest['event_count']}` |",
        f"| `session_sha256` | `{manifest['session_sha256']}` |",
        f"| `source_sha256` | `{manifest['source_sha256']}` |",
        "",
        f"Redaction: {manifest['redaction']}.",
        "",
    ]
    return "\n".join(lines)


def _resolve_output(output_dir: Path) -> Path:
    base = output_dir if output_dir.is_absolute() else Path.cwd() / output_dir
    if base.is_symlink():
        raise ShadowExportError(f"export output directory cannot be a symlink: {base}")
    if base.exists() and not base.is_dir():
        raise ShadowExportError(f"export output path is not a directory: {base}")
    base.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
    return base


def _create_capsule_dir(base: Path, shadow_id: str) -> Path:
    capsule = base / capsule_name(shadow_id)
    if capsule.is_symlink() or capsule.exists():
        raise ShadowExportError(f"capsule directory already exists: {capsule}")
    try:
        capsule.mkdir(mode=_DIR_MODE)
    except FileExistsError as error:
        raise ShadowExportError(
            f"capsule directory already exists: {capsule}"
        ) from error
    os.chmod(capsule, _DIR_MODE)
    return capsule


def _write_new(path: Path, data: bytes) -> None:
    """Create-new write with mode 0o600; an existing path fails closed."""

    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, _FILE_MODE
        )
    except FileExistsError as error:
        raise ShadowExportError(f"capsule file already exists: {path}") from error
    with os.fdopen(descriptor, "wb") as handle:
        os.fchmod(descriptor, _FILE_MODE)
        handle.write(data)


def build_manifest(
    session: Mapping[str, object],
    events: tuple[ShadowEvent, ...],
    graph: ShadowGraph,
    lint_report: LintReport,
    files: Mapping[str, bytes],
) -> dict[str, object]:
    """The manifest value; ``files`` pins every other capsule file by digest."""

    if not events:
        raise ShadowExportError("a capsule needs at least one event")
    source = events[0].source
    source_adapter = session.get("source_adapter")
    source_adapter_version = session.get("source_adapter_version")
    return {
        "schema": CAPSULE_SCHEMA,
        "shadow_id": session["shadow_id"],
        "session_id": session["session_id"],
        "adapter": session["adapter"],
        "adapter_version": session["adapter_version"],
        "source_adapter": (
            source_adapter if isinstance(source_adapter, str) else source.adapter
        ),
        "source_adapter_version": (
            source_adapter_version
            if isinstance(source_adapter_version, str)
            else source.adapter_version
        ),
        "source_sha256": session["source_sha256"],
        "source_bytes": session["source_bytes"],
        "session_sha256": session["session_sha256"],
        "event_count": len(events),
        "heuristics": {
            "segments": graph.segments_version,
            "claims": claims_version(session),
            "lint": lint_report.lint_version,
        },
        "files": {
            name: {"sha256": sha256_hex(data), "bytes": len(data)}
            for name, data in files.items()
        },
        "redaction": REDACTION_NOTE,
    }


def export_capsule(
    store: ShadowStore, shadow_id: str, output_dir: Path
) -> dict[str, object]:
    """Write ``<output_dir>/<shadow_id>.graphene-shadow/``; fail if it exists."""

    record = store.session(shadow_id)
    events = store.events(shadow_id)
    session = record.to_dict()
    if session.get("event_count") != len(events):
        raise ShadowExportError(f"shadow session {shadow_id} event count mismatch")
    graph = reconstruct(events)
    lint_report = lint(events, graph)
    report = render_report(report_value(session, graph, lint_report))

    contents: dict[str, bytes] = {
        EVENTS_NAME: events_ndjson(events),
        GRAPH_NAME: canonical_json_bytes(graph.model_dump(mode="json")) + b"\n",
        LINT_NAME: canonical_json_bytes(lint_report.model_dump(mode="json")) + b"\n",
        REPORT_NAME: report.encode("utf-8"),
    }
    manifest = build_manifest(session, events, graph, lint_report, contents)
    contents[VERIFY_NAME] = verify_markdown(manifest).encode("utf-8")
    manifest = build_manifest(session, events, graph, lint_report, contents)
    manifest_bytes = canonical_json_bytes(manifest) + b"\n"

    capsule = _create_capsule_dir(_resolve_output(output_dir), shadow_id)
    for name in CAPSULE_FILES:
        _write_new(capsule / name, contents[name])
    _write_new(capsule / MANIFEST_NAME, manifest_bytes)
    return {
        "shadow_id": shadow_id,
        "capsule_dir": str(capsule),
        "manifest_sha256": sha256_hex(manifest_bytes),
        "files": sorted((*CAPSULE_FILES, MANIFEST_NAME)),
    }


__all__ = [
    "CAPSULE_FILES",
    "CAPSULE_SCHEMA",
    "CAPSULE_SUFFIX",
    "EVENTS_NAME",
    "GRAPH_NAME",
    "LINT_NAME",
    "MANIFEST_NAME",
    "REDACTION_NOTE",
    "REPORT_NAME",
    "VERIFY_NAME",
    "ShadowExportError",
    "build_manifest",
    "capsule_name",
    "claims_version",
    "events_ndjson",
    "export_capsule",
    "verify_markdown",
]
