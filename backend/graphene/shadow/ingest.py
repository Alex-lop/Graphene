"""The ingest pipeline: source file -> adapter -> drafts -> verified events -> store.

Steps, in order: read the source as a regular file of at most 256 MiB and
digest it; parse it with the named adapter; redact every draft excerpt with
the ingest redaction rules so nothing unredacted can reach the store; when
the source carries no ``claim`` records, run the ``claims.v1`` matcher over
each agent message (its full text when the adapter supplied ``_full_text``,
otherwise its excerpt) and insert one inferred ``claim`` draft directly after
the message that produced it; materialize the drafts into numbered,
identified events; persist them. When the source already contains claims the
emitter is the claim authority and the matcher does not run, which is what
lets an exported capsule re-ingest to the same shadow id.
"""

from __future__ import annotations

import stat
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from ..hashing import sha256_hex
from ..models import FrozenModel
from .adapters import AdapterError, Draft, ParsedSession, adapter_for, materialize
from .claims import CLAIMS_MATCHER, ClaimMatch, extract_claims
from .events import ShadowEvent, ShadowSource
from .redaction import (
    COMMAND_EXCERPT_LIMIT,
    MESSAGE_EXCERPT_LIMIT,
    bounded_excerpt,
    collapse_home,
)
from .store import ShadowStore

SOURCE_SIZE_LIMIT = 256 * 1024 * 1024
FULL_TEXT_FIELD = "_full_text"


class IngestError(AdapterError):
    """The source file or repository argument could not be used at all."""


class IngestResult(FrozenModel):
    shadow_id: str
    created: bool
    adapter: str
    adapter_version: str
    session_id: str
    event_count: int
    observed_count: int
    inferred_count: int
    claim_count: int
    unknown_count: int
    source_sha256: str
    source_bytes: int
    repo_label: str | None
    elapsed_ms: int


def _read_source(path: Path) -> bytes:
    try:
        metadata = path.stat()
    except FileNotFoundError as error:
        raise IngestError(f"source file not found: {path}") from error
    except OSError as error:
        raise IngestError(f"source file is unavailable: {path}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise IngestError(f"source must be a regular file: {path}")
    if metadata.st_size > SOURCE_SIZE_LIMIT:
        raise IngestError(f"source exceeds the 256 MiB limit: {path}")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise IngestError(f"source file is unavailable: {path}") from error
    if len(data) > SOURCE_SIZE_LIMIT:
        raise IngestError(f"source exceeds the 256 MiB limit: {path}")
    return data


def _repo_label(repo: Path | None) -> str | None:
    if repo is None:
        return None
    if not isinstance(repo, Path) or not repo.is_dir():
        raise IngestError(f"repo must be an existing directory: {repo}")
    return collapse_home(repo.resolve().as_posix())


def _redacted(fields: dict[str, object]) -> dict[str, object]:
    """Bound and scrub the two free-text fields before anything else happens."""

    redacted = dict(fields)
    excerpt = redacted.get("excerpt")
    if isinstance(excerpt, str):
        redacted["excerpt"] = bounded_excerpt(excerpt, MESSAGE_EXCERPT_LIMIT)
    argv_excerpt = redacted.get("argv_excerpt")
    if isinstance(argv_excerpt, str):
        redacted["argv_excerpt"] = bounded_excerpt(argv_excerpt, COMMAND_EXCERPT_LIMIT)
    return redacted


def _is_agent_message(fields: Mapping[str, object]) -> bool:
    return fields.get("kind") == "message" and fields.get("actor") == "agent"


def _claim_source(source: object, position: int) -> dict[str, object]:
    if isinstance(source, ShadowSource):
        record: dict[str, object] = source.model_dump(mode="json")
    elif isinstance(source, Mapping):
        record = dict(source)
    else:
        raise AdapterError(f"draft {position}: message source must be an object")
    record["raw_type"] = "claim"
    return record


def _claim_draft(
    message: Mapping[str, object], position: int, match: ClaimMatch, excerpt: str
) -> Draft:
    return Draft(
        fields={
            "ts": message.get("ts"),
            "actor": "agent",
            "kind": "claim",
            "paths": (),
            "outside_paths": (),
            "tool": None,
            "call_id": message.get("call_id"),
            "argv_digest": None,
            "argv_excerpt": None,
            "exit_code": None,
            "check_family": None,
            "excerpt": excerpt,
            "content_digest": message.get("content_digest"),
            "claim": {
                "matcher": CLAIMS_MATCHER,
                "category": match.category,
                "pattern_id": match.pattern_id,
            },
            "source": _claim_source(message.get("source"), position),
        },
        provenance="inferred",
        derived_from=(position,),
    )


def _prepare_drafts(parsed: ParsedSession) -> tuple[Draft, ...]:
    """Redact every draft and, unless the source has claims, extract them."""

    prepared: list[Draft] = []
    position_of: dict[int, int] = {}
    for index, draft in enumerate(parsed.drafts):
        if not isinstance(draft, Draft):
            raise AdapterError(f"draft {index}: not a Draft record")
        fields = dict(draft.fields)
        full_text = fields.pop(FULL_TEXT_FIELD, None)
        fields = _redacted(fields)
        references: list[int] = []
        for reference in draft.derived_from:
            if reference not in position_of:
                raise AdapterError(
                    f"draft {index}: derived_from index {reference!r} must refer "
                    "to an earlier draft"
                )
            references.append(position_of[reference])
        position = len(prepared)
        position_of[index] = position
        prepared.append(
            Draft(
                fields=fields,
                provenance=draft.provenance,
                derived_from=tuple(sorted(set(references))),
            )
        )
        if parsed.has_claims or not _is_agent_message(fields):
            continue
        text = full_text if isinstance(full_text, str) and full_text else None
        if text is None:
            excerpt = fields.get("excerpt")
            text = excerpt if isinstance(excerpt, str) else None
        if not text:
            continue
        for match in extract_claims(text):
            excerpt = bounded_excerpt(match.sentence, MESSAGE_EXCERPT_LIMIT)
            if excerpt is not None:
                prepared.append(_claim_draft(fields, position, match, excerpt))
    return tuple(prepared)


def ingest_file(
    store: ShadowStore,
    path: Path,
    *,
    fmt: str,
    repo: Path | None,
    now: datetime | None = None,
) -> IngestResult:
    """Ingest one source file into ``store``; see the module docstring."""

    started = time.perf_counter()
    if not isinstance(store, ShadowStore):
        raise TypeError("ingest_file requires a ShadowStore")
    if not isinstance(path, Path):
        raise TypeError("ingest_file requires a Path")
    adapter = adapter_for(fmt)
    repo_label = _repo_label(repo)
    data = _read_source(path)
    source_sha256 = sha256_hex(data)
    parsed = adapter.parse(data, repo=repo)
    events = materialize(parsed.session_id, _prepare_drafts(parsed))
    if not events:
        raise AdapterError(f"{adapter.name} produced no events for {path}")
    counts = _counts(events)
    summary: dict[str, object] = {
        **counts,
        "raw_record_count": parsed.raw_record_count,
        "source_adapter": events[0].source.adapter,
        "source_adapter_version": events[0].source.adapter_version,
        "has_source_claims": parsed.has_claims,
        "heuristics": {"claims": CLAIMS_MATCHER},
    }
    shadow_id, created = store.ingest(
        events,
        adapter=adapter.name,
        adapter_version=adapter.version,
        source_sha256=source_sha256,
        source_bytes=len(data),
        repo_label=repo_label,
        summary=summary,
        now=now,
    )
    return IngestResult(
        shadow_id=shadow_id,
        created=created,
        adapter=adapter.name,
        adapter_version=adapter.version,
        session_id=parsed.session_id,
        source_sha256=source_sha256,
        source_bytes=len(data),
        repo_label=repo_label,
        elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
        **counts,
    )


def _counts(events: tuple[ShadowEvent, ...]) -> dict[str, int]:
    return {
        "event_count": len(events),
        "observed_count": sum(1 for event in events if event.provenance == "observed"),
        "inferred_count": sum(1 for event in events if event.provenance == "inferred"),
        "claim_count": sum(1 for event in events if event.kind == "claim"),
        "unknown_count": sum(1 for event in events if event.kind == "unknown"),
    }


__all__ = [
    "FULL_TEXT_FIELD",
    "SOURCE_SIZE_LIMIT",
    "IngestError",
    "IngestResult",
    "ingest_file",
]
