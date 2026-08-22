"""Verify an exported capsule from its bytes alone.

``python -m graphene.shadow.verify CAPSULE_DIR`` recomputes every line's
``event_id`` from the canonical ``shadow.event.v1`` encoding, the
``shadow.session.v1`` digest, the SHA-256 and size of every file the manifest
pins (and that nothing unlisted is present), the ``shadow_id``, and a fresh
``segments.v1`` / ``lint.v1`` run over the stream that must equal the stored
``graph.json`` and ``lint.json``. It fails closed on the first mismatch and
never consults the shadow store, so anyone holding the capsule can run it.
"""

from __future__ import annotations

import argparse
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..hashing import canonical_json_bytes, sha256_hex
from .events import ShadowEvent, event_id_for, session_sha256
from .export import (
    CAPSULE_FILES,
    CAPSULE_SCHEMA,
    EVENTS_NAME,
    GRAPH_NAME,
    LINT_NAME,
    MANIFEST_NAME,
    REPORT_NAME,
)
from .lint import LINT_VERSION, LintReport, lint
from .reconstruct import SEGMENTS_VERSION, ShadowGraph, reconstruct
from .store import shadow_id_for

MANIFEST_KEYS: tuple[str, ...] = (
    "schema",
    "shadow_id",
    "session_id",
    "adapter",
    "adapter_version",
    "source_adapter",
    "source_sha256",
    "source_bytes",
    "session_sha256",
    "event_count",
    "heuristics",
    "files",
    "redaction",
)
# Every check the verifier performs, in the order it performs them.
CHECKS: tuple[str, ...] = (
    "manifest",
    "file_digests",
    "event_ids",
    "session_sha256",
    "shadow_id",
    "graph",
    "lint",
    "report",
)
_TEXT_KEYS = (
    "shadow_id",
    "session_id",
    "adapter",
    "adapter_version",
    "source_adapter",
    "source_sha256",
    "session_sha256",
    "redaction",
)
_COUNT_KEYS = ("source_bytes", "event_count")
_HEURISTIC_KEYS = ("segments", "claims", "lint")
_REPORT_HEADER = "GRAPHENE SHADOW REPORT\n"


class CapsuleVerifyError(RuntimeError):
    pass


def _read_regular(path: Path, name: str) -> bytes:
    if path.is_symlink():
        raise CapsuleVerifyError(f"{name} cannot be a symlink")
    try:
        metadata = path.stat()
    except FileNotFoundError as error:
        raise CapsuleVerifyError(f"{name} is missing") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise CapsuleVerifyError(f"{name} is not a regular file")
    return path.read_bytes()


def _load_json(data: bytes, name: str) -> object:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise CapsuleVerifyError(f"{name} is not valid JSON") from error


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def load_manifest(data: bytes) -> dict[str, object]:
    """Parse and shape-check ``manifest.json``; nothing is recomputed here."""

    manifest = _load_json(data, MANIFEST_NAME)
    if not isinstance(manifest, dict):
        raise CapsuleVerifyError(f"{MANIFEST_NAME} must be a JSON object")
    if manifest.get("schema") != CAPSULE_SCHEMA:
        raise CapsuleVerifyError(
            f"{MANIFEST_NAME} schema {manifest.get('schema')!r} is not {CAPSULE_SCHEMA}"
        )
    missing = [key for key in MANIFEST_KEYS if key not in manifest]
    if missing:
        raise CapsuleVerifyError(f"{MANIFEST_NAME} is missing {', '.join(missing)}")
    for key in _TEXT_KEYS:
        if not isinstance(manifest[key], str) or not manifest[key]:
            raise CapsuleVerifyError(
                f"{MANIFEST_NAME} {key} must be a non-empty string"
            )
    for key in _COUNT_KEYS:
        if not _is_count(manifest[key]):
            raise CapsuleVerifyError(
                f"{MANIFEST_NAME} {key} must be a non-negative integer"
            )
    heuristics = manifest["heuristics"]
    if not isinstance(heuristics, dict) or any(
        not isinstance(heuristics.get(key), str) or not heuristics.get(key)
        for key in _HEURISTIC_KEYS
    ):
        raise CapsuleVerifyError(
            f"{MANIFEST_NAME} heuristics must name segments, claims, and lint versions"
        )
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise CapsuleVerifyError(f"{MANIFEST_NAME} files must be a non-empty object")
    for name, entry in files.items():
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\0" in name
            or name == MANIFEST_NAME
        ):
            raise CapsuleVerifyError(
                f"{MANIFEST_NAME} lists an invalid file name {name!r}"
            )
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("sha256"), str)
            or not _is_count(entry.get("bytes"))
        ):
            raise CapsuleVerifyError(
                f"{MANIFEST_NAME} entry for {name} must carry sha256 and bytes"
            )
    return manifest


def _check_files(capsule: Path, manifest: Mapping[str, object]) -> dict[str, bytes]:
    listed = manifest["files"]
    assert isinstance(listed, dict)
    missing = [name for name in CAPSULE_FILES if name not in listed]
    if missing:
        raise CapsuleVerifyError(f"{MANIFEST_NAME} does not list {', '.join(missing)}")
    present = sorted(entry.name for entry in capsule.iterdir())
    unlisted = [
        name for name in present if name != MANIFEST_NAME and name not in listed
    ]
    if unlisted:
        raise CapsuleVerifyError(f"unlisted file in capsule: {', '.join(unlisted)}")
    contents: dict[str, bytes] = {}
    for name, entry in listed.items():
        data = _read_regular(capsule / name, name)
        if len(data) != entry["bytes"]:
            raise CapsuleVerifyError(
                f"{name} size mismatch: {MANIFEST_NAME} says {entry['bytes']} bytes, "
                f"found {len(data)}"
            )
        if sha256_hex(data) != entry["sha256"]:
            raise CapsuleVerifyError(f"{name} digest mismatch")
        contents[name] = data
    return contents


def parse_events(data: bytes) -> tuple[ShadowEvent, ...]:
    """Re-derive every event_id and re-validate every line of ``events.ndjson``."""

    if not data:
        raise CapsuleVerifyError(f"{EVENTS_NAME} is empty")
    if not data.endswith(b"\n"):
        raise CapsuleVerifyError(f"{EVENTS_NAME} must end with a newline")
    events: list[ShadowEvent] = []
    session_id: str | None = None
    for number, raw in enumerate(data[:-1].split(b"\n"), start=1):
        locator = f"{EVENTS_NAME} line {number}"
        if not raw:
            raise CapsuleVerifyError(f"{locator} is blank")
        record = _load_json(raw, locator)
        if not isinstance(record, dict):
            raise CapsuleVerifyError(f"{locator} is not a JSON object")
        supplied = record.get("event_id")
        if not isinstance(supplied, str):
            raise CapsuleVerifyError(f"{locator} has no event_id")
        identity = {key: value for key, value in record.items() if key != "event_id"}
        try:
            computed = event_id_for(identity)
        except ValueError as error:
            raise CapsuleVerifyError(f"{locator}: {error}") from error
        if computed != supplied:
            raise CapsuleVerifyError(
                f"{locator}: event_id does not match the canonical encoding"
            )
        try:
            event = ShadowEvent.model_validate(record)
        except ValueError as error:
            raise CapsuleVerifyError(
                f"{locator} failed shadow.event.v1 validation"
            ) from error
        if canonical_json_bytes(event.to_record()) != raw:
            raise CapsuleVerifyError(f"{locator} is not canonical JSON")
        if event.seq != number:
            raise CapsuleVerifyError(
                f"{locator}: seq {event.seq} is not contiguous (expected {number})"
            )
        if session_id is None:
            session_id = event.session_id
        elif event.session_id != session_id:
            raise CapsuleVerifyError(f"{locator}: session_id changes mid-stream")
        events.append(event)
    return tuple(events)


def _load_model(data: bytes, name: str, model: type) -> object:
    value = _load_json(data, name)
    try:
        return model.model_validate(value)
    except ValueError as error:
        raise CapsuleVerifyError(f"{name} is not a valid {model.__name__}") from error


def verify_capsule(path: Path) -> dict[str, object]:
    """Verify one capsule directory; raises ``CapsuleVerifyError`` on mismatch."""

    capsule = path if path.is_absolute() else Path.cwd() / path
    if capsule.is_symlink():
        raise CapsuleVerifyError(f"capsule path cannot be a symlink: {capsule}")
    if not capsule.is_dir():
        raise CapsuleVerifyError(f"capsule directory not found: {capsule}")
    manifest_bytes = _read_regular(capsule / MANIFEST_NAME, MANIFEST_NAME)
    manifest = load_manifest(manifest_bytes)
    contents = _check_files(capsule, manifest)

    events = parse_events(contents[EVENTS_NAME])
    if len(events) != manifest["event_count"]:
        raise CapsuleVerifyError(
            f"event count mismatch: {MANIFEST_NAME} says {manifest['event_count']}, "
            f"{EVENTS_NAME} has {len(events)}"
        )
    if events[0].session_id != manifest["session_id"]:
        raise CapsuleVerifyError(
            f"session_id mismatch: {MANIFEST_NAME} says {manifest['session_id']}, "
            f"{EVENTS_NAME} carries {events[0].session_id}"
        )
    digest = session_sha256(event.event_id for event in events)
    if digest != manifest["session_sha256"]:
        raise CapsuleVerifyError("session digest mismatch")
    shadow_id = str(manifest["shadow_id"])
    expected = shadow_id_for(
        str(manifest["adapter"]), str(manifest["adapter_version"]), digest
    )
    if expected != shadow_id:
        raise CapsuleVerifyError(
            f"shadow_id {shadow_id} does not match the adapter and session digest "
            f"(expected {expected})"
        )

    heuristics = manifest["heuristics"]
    assert isinstance(heuristics, dict)
    if heuristics["segments"] != SEGMENTS_VERSION or heuristics["lint"] != LINT_VERSION:
        raise CapsuleVerifyError(
            f"capsule heuristics segments={heuristics['segments']} "
            f"lint={heuristics['lint']} are not the ones this Graphene implements "
            f"({SEGMENTS_VERSION}, {LINT_VERSION})"
        )
    graph = reconstruct(events)
    if _load_model(contents[GRAPH_NAME], GRAPH_NAME, ShadowGraph) != graph:
        raise CapsuleVerifyError(
            f"{GRAPH_NAME} does not match {SEGMENTS_VERSION} over {EVENTS_NAME}"
        )
    lint_report = lint(events, graph)
    if _load_model(contents[LINT_NAME], LINT_NAME, LintReport) != lint_report:
        raise CapsuleVerifyError(
            f"{LINT_NAME} does not match {LINT_VERSION} over {EVENTS_NAME}"
        )
    try:
        report = contents[REPORT_NAME].decode("utf-8")
    except UnicodeDecodeError as error:
        raise CapsuleVerifyError(f"{REPORT_NAME} is not UTF-8") from error
    if not report.startswith(_REPORT_HEADER) or shadow_id not in report:
        raise CapsuleVerifyError(
            f"{REPORT_NAME} is not the shadow report for {shadow_id}"
        )

    listed = manifest["files"]
    assert isinstance(listed, dict)
    return {
        "shadow_id": shadow_id,
        "capsule_dir": str(capsule),
        "session_id": events[0].session_id,
        "event_count": len(events),
        "session_sha256": digest,
        "manifest_sha256": sha256_hex(manifest_bytes),
        "files": {name: entry["sha256"] for name, entry in sorted(listed.items())},
        "checks": list(CHECKS),
        "verified": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m graphene.shadow.verify",
        allow_abbrev=False,
        description=(
            "Recompute every digest in an exported shadow capsule; fails closed."
        ),
    )
    parser.add_argument(
        "capsule", type=Path, help="path to a <shadow_id>.graphene-shadow directory"
    )
    args = parser.parse_args(argv)
    try:
        result = verify_capsule(args.capsule)
    except CapsuleVerifyError as error:
        sys.stderr.write(f"SHADOW_ERROR: {error}\n")
        return 1
    sys.stdout.write(canonical_json_bytes(result).decode() + "\n")
    return 0


__all__ = [
    "CHECKS",
    "MANIFEST_KEYS",
    "CapsuleVerifyError",
    "load_manifest",
    "main",
    "parse_events",
    "verify_capsule",
]


if __name__ == "__main__":
    raise SystemExit(main())
