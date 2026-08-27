"""Mission Capsule: a portable, redacted, offline-verifiable mission export.

The capsule carries the public hash-chained mission events, every attempt's
evidence chain, the digests of every publication envelope, the trusted check
and sanitized worker-provider receipts, the registered final result bundle,
the plan revisions, and the derived overlap/unknown views. It never carries
prompts, source bytes, diffs, command output, environment values, or
credentials: artifact bytes of every other kind stay in the executor's
private spool and only their digests travel.

``verify_mission_capsule`` recomputes every digest and chain link from the
files alone. It never opens a mission database, a Git repository, or a
network connection, and it says plainly what it did not check.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import TypeAdapter

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..core_models import Identifier, TruthKind
from .evidence import (
    AttemptEvidenceEvent,
    AttemptEvidenceEventType,
    SQLiteAttemptEvidenceStore,
    TrustedCheckReceipt,
)
from .final_bundle import FinalResultBundleV2
from .mission_models import (
    AuthorizationMode,
    Attempt,
    Criterion,
    EvidenceReference,
    GenericEvidenceLink,
    MissionEvent,
    MissionAuthority,
    MissionEventType,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    Plan,
    Task,
    TaskState,
    FinalizationMode,
    plan_policy_decision,
)
from .overlap import measure_overlap
from .mission_reducer import TransitionError, transition_mission

CAPSULE_SCHEMA = "graphene.mission-capsule.v1"
CAPSULE_SUFFIX = ".graphene-capsule"
RECEIPT_KINDS = frozenset(
    {"test-receipt", "worker-provider-interruption", "worker-provider-receipt"}
)
FINAL_BUNDLE_KIND = "final-result-bundle"
REDACTION_NOTE = (
    "Contains no prompts, source bytes, diffs, command output, environment values, "
    "or credentials. Artifact bytes stay in the executor's private spool; only "
    "their digests are included."
)
AUTHORITY_NOTE = "SQLite mission store was the execution authority for this mission."
NOT_VERIFIABLE_OFFLINE = (
    "candidate tree identity against artifact bytes",
    "Gemini provider-side identity",
    "host clock accuracy",
    "producer authenticity",
)
PRODUCER_NOTE = (
    "the capsule carries no signature or external anchor, so verification proves "
    "internal consistency with the hash chains and digests, not who produced "
    "them; producer authenticity comes from the mission store that exported it "
    "(`graphene mission db verify`) or from comparing the manifest head digest "
    "against the operator's recorded mission head"
)

MANIFEST_FILE = "manifest.json"
EVENTS_FILE = "events.ndjson"
ENVELOPES_FILE = "envelopes.json"
FINAL_BUNDLE_FILE = "final-bundle.json"
TREE_MANIFEST_FILE = "tree-manifest.json"
OVERLAP_FILE = "overlap.json"
UNKNOWNS_FILE = "unknowns.json"
VERIFY_FILE = "VERIFY.md"
PLAN_DIRECTORY = "plan"
ATTEMPTS_DIRECTORY = "attempts"
RECEIPTS_DIRECTORY = "receipts"
_CAPSULE_DIRECTORIES = frozenset(
    {PLAN_DIRECTORY, ATTEMPTS_DIRECTORY, RECEIPTS_DIRECTORY}
)

_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600
_MAX_CAPSULE_FILE_BYTES = 64 * 1024 * 1024
_TAIL_LIMIT = 256
_FORBIDDEN_RECEIPT_KEYS = frozenset(
    {
        "apikey",
        "argv",
        "authorization",
        "command",
        "content",
        "credential",
        "env",
        "environment",
        "output",
        "password",
        "patch",
        "prompt",
        "secret",
        "stderr",
        "stdout",
        "token",
    }
)
_IDENTIFIER = TypeAdapter(Identifier)


class CapsuleError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _pretty_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _ndjson(values: Iterable[Any]) -> bytes:
    return b"".join(canonical_json_bytes(value) + b"\n" for value in values)


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _receipt_keys_are_public(value: Any, *, _depth: int = 0) -> bool:
    if _depth > 8:
        return False
    if isinstance(value, dict):
        return all(
            isinstance(key, str)
            and _normalized_key(key) not in _FORBIDDEN_RECEIPT_KEYS
            and _receipt_keys_are_public(item, _depth=_depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_receipt_keys_are_public(item, _depth=_depth + 1) for item in value)
    return True


def _validated_mission_id(mission_id: object) -> str:
    try:
        return _IDENTIFIER.validate_python(mission_id)
    except ValueError as error:
        raise CapsuleError("mission ID is invalid") from error


def _tree_manifest_value(bundle: FinalResultBundleV2 | None) -> dict[str, Any]:
    if bundle is None:
        return {
            "present": False,
            "note": (
                "No FinalResultBundleV2 was registered for this mission; "
                "there is no result tree to describe."
            ),
        }
    return {
        "present": True,
        "bundle_id": bundle.bundle_id,
        "base_commit": bundle.base_commit,
        "candidate_tree_hash_version": bundle.candidate_tree_hash_version,
        "candidate_tree_sha256": bundle.candidate_tree_sha256,
        "changed_paths": list(bundle.changed_paths),
        "mutation_manifest": bundle.mutation_manifest.model_dump(mode="json"),
        "result_commit": bundle.result_commit,
        "result_tree_id": bundle.result_tree_id,
    }


# --------------------------------------------------------------------------- #
# Export: gathering verified state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _AttemptChain:
    attempt: Attempt
    evidence_id: str
    events: tuple[AttemptEvidenceEvent, ...]


@dataclass(frozen=True, slots=True)
class _Receipt:
    reference: EvidenceReference
    content: bytes
    attempt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FinalBundle:
    raw: bytes
    bundle: FinalResultBundleV2
    event: MissionEvent
    reference: EvidenceReference
    decision: dict[str, Any]


def _mission_events(
    store: Any, mission_id: str, head: MissionHead
) -> tuple[MissionEvent, ...]:
    events: list[MissionEvent] = []
    after = 0
    while after < head.seq:
        batch = store.tail(mission_id, after, min(_TAIL_LIMIT, head.seq - after))
        if not batch:
            raise CapsuleError("mission events are incomplete")
        events.extend(batch)
        after = batch[-1].seq
    previous: str | None = None
    for seq, event in enumerate(events, 1):
        if (
            event.seq != seq
            or event.previous_event_sha256 != previous
            or event.mission_id != mission_id
        ):
            raise CapsuleError("mission event chain is invalid")
        previous = event.event_sha256
    if len(events) != head.event_count or previous != head.event_sha256:
        raise CapsuleError("mission events do not match the verified head")
    return tuple(events)


def _recorded_plan_digests(
    events: Iterable[MissionEvent], *, failure: type[Exception] = CapsuleError
) -> dict[int, str]:
    """Collect the digest each ``plan.proposed`` / ``plan.revised`` event records.

    Two events recording different digests for one revision fail closed with
    ``failure`` (``CapsuleError`` during export, ``_CheckFailed`` during cold
    verification) rather than letting the later event win.
    """

    recorded: dict[int, str] = {}
    for event in events:
        if event.event_type not in {
            MissionEventType.PLAN_PROPOSED,
            MissionEventType.PLAN_REVISED,
        }:
            continue
        revision = event.payload.get("plan_revision")
        digest = event.payload.get("plan_sha256")
        if type(revision) is not int or not isinstance(digest, str):
            raise failure("plan event payload is malformed")
        if recorded.setdefault(revision, digest) != digest:
            raise failure(f"plan revision {revision} has conflicting recorded digests")
    return recorded


def _bundle_decision(
    events: tuple[MissionEvent, ...], ready_seq: int, bundle_id: str
) -> dict[str, Any]:
    """Derive the final decision bound to ``bundle_id`` after its ready event."""

    decision: dict[str, Any] = {"state": "pending", "event_seq": None}
    for later in events[ready_seq:]:
        if later.event_type not in {
            MissionEventType.FINAL_CANDIDATE_APPROVED,
            MissionEventType.FINAL_CANDIDATE_REJECTED,
        }:
            continue
        receipt = later.payload.get("decision_receipt")
        if isinstance(receipt, dict) and receipt.get("bundle_id") == bundle_id:
            approved = later.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
            decision = {
                "state": "approved" if approved else "rejected",
                "event_seq": later.seq,
            }
            if isinstance(later.payload.get("decision_mode"), str):
                decision["mode"] = later.payload["decision_mode"]
    return decision


def _rewind_items(
    items: tuple[Any, ...], change: Mapping[str, Any], key: str, model: type
) -> tuple[Any, ...]:
    by_id = {getattr(item, key): item for item in items}
    for value in change["added"]:
        if by_id.pop(value[key], None) is None:
            raise CapsuleError("plan diff does not match the current plan")
    for value in change["changed"]:
        before = model.model_validate(value["before"])
        if getattr(before, key) not in by_id:
            raise CapsuleError("plan diff does not match the current plan")
        by_id[getattr(before, key)] = before
    for value in change["removed"]:
        removed = model.model_validate(value)
        if getattr(removed, key) in by_id:
            raise CapsuleError("plan diff does not match the current plan")
        by_id[getattr(removed, key)] = removed
    return tuple(by_id[identifier] for identifier in sorted(by_id))


def rewind_plan(plan: Plan, diff: Mapping[str, Any]) -> Plan:
    """Reconstruct the previous plan revision from the store's recorded diff.

    The result is accepted only when its canonical digest equals the
    ``previous_plan_sha256`` the store recorded for that diff; a mismatch fails
    closed rather than guessing.
    """

    if (
        diff.get("mission_id") != plan.mission_id
        or diff.get("plan_revision") != plan.revision
        or diff.get("previous_plan_revision") != plan.revision - 1
    ):
        raise CapsuleError("plan diff does not describe this plan revision")
    try:
        previous = Plan(
            mission_id=plan.mission_id,
            revision=plan.revision - 1,
            previous_revision=None if plan.revision == 2 else plan.revision - 2,
            criteria=_rewind_items(
                plan.criteria, diff["criteria"], "criterion_id", Criterion
            ),
            tasks=_rewind_items(plan.tasks, diff["tasks"], "task_id", Task),
            max_concurrency=diff["max_concurrency"]["before"],
        )
    except CapsuleError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise CapsuleError("plan diff is malformed") from error
    if canonical_json_sha256(previous.model_dump(mode="json")) != diff.get(
        "previous_plan_sha256"
    ):
        raise CapsuleError(
            f"plan revision {plan.revision - 1} could not be reconstructed "
            "from its recorded diff"
        )
    return previous


def _plan_revisions(
    store: Any, snapshot: MissionSnapshot, events: tuple[MissionEvent, ...]
) -> tuple[tuple[int, Plan, str], ...]:
    mission_id = snapshot.mission.mission_id
    revisions: dict[int, Plan] = {snapshot.plan.revision: snapshot.plan}
    plan = snapshot.plan
    while plan.revision > 1:
        try:
            diff = store.plan_diff(mission_id, plan.revision - 1, plan.revision)
        except Exception as error:
            raise CapsuleError(
                f"plan diff for revision {plan.revision} is unavailable"
            ) from error
        plan = rewind_plan(plan, diff)
        revisions[plan.revision] = plan
    recorded = _recorded_plan_digests(events)
    if set(recorded) != set(revisions):
        raise CapsuleError("recorded plan revisions do not match the plan history")
    result = []
    for revision in sorted(revisions):
        digest = canonical_json_sha256(revisions[revision].model_dump(mode="json"))
        if recorded[revision] != digest:
            raise CapsuleError(
                f"plan revision {revision} digest does not match its recorded event"
            )
        result.append((revision, revisions[revision], digest))
    return tuple(result)


def _attempt_events(
    evidence: SQLiteAttemptEvidenceStore, evidence_id: str, seq: int
) -> tuple[AttemptEvidenceEvent, ...]:
    events: list[AttemptEvidenceEvent] = []
    after = 0
    while after < seq:
        batch = evidence.tail(evidence_id, after, min(_TAIL_LIMIT, seq - after))
        if not batch:
            raise CapsuleError("attempt evidence is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    return tuple(events)


def _attempt_chains(
    evidence: SQLiteAttemptEvidenceStore, snapshot: MissionSnapshot
) -> tuple[tuple[_AttemptChain, ...], tuple[dict[str, Any], ...]]:
    chains: list[_AttemptChain] = []
    skipped: list[dict[str, Any]] = []
    for attempt in snapshot.attempts:
        link = attempt.evidence_link
        if link is None:
            reason = "attempt has no evidence link"
        elif not isinstance(link, GenericEvidenceLink):
            reason = "legacy evidence link is not exportable as a generic chain"
        else:
            reason = None
        if reason is not None or link is None:
            skipped.append(
                {
                    "attempt_id": attempt.attempt_id,
                    "task_id": attempt.task_id,
                    "state": attempt.state.value,
                    "reason": reason,
                }
            )
            continue
        head = evidence.head(link.evidence_id)
        if head.seq == 0:
            skipped.append(
                {
                    "attempt_id": attempt.attempt_id,
                    "task_id": attempt.task_id,
                    "state": attempt.state.value,
                    "reason": "attempt evidence chain is empty",
                }
            )
            continue
        events = _attempt_events(evidence, link.evidence_id, head.seq)
        previous: str | None = None
        for seq, event in enumerate(events, 1):
            if (
                event.seq != seq
                or event.previous_event_sha256 != previous
                or event.evidence_id != link.evidence_id
                or (event.mission_id, event.task_id, event.attempt_id)
                != (attempt.mission_id, attempt.task_id, attempt.attempt_id)
            ):
                raise CapsuleError(
                    f"attempt evidence chain for {attempt.attempt_id} is invalid"
                )
            previous = event.event_sha256
        if (
            len(events) != head.event_count
            or previous != head.event_sha256
            or events[0].event_type != AttemptEvidenceEventType.ATTEMPT_STARTED
        ):
            raise CapsuleError(
                f"attempt evidence chain for {attempt.attempt_id} does not "
                "match its head"
            )
        chains.append(_AttemptChain(attempt, link.evidence_id, events))
    return tuple(chains), tuple(skipped)


def _provider_call_receipts(
    evidence: SQLiteAttemptEvidenceStore, snapshot: MissionSnapshot
) -> dict[str, object]:
    """Evidence-bound worker provider receipts keyed by attempt, for overlap.

    Only digest-verified, canonical, schema-valid receipts take part, so the
    provider-call overlap basis in ``overlap.json`` cites nothing unbound.
    """

    from .worker_runtime import WorkerProviderReceipt  # lazy: cold verify stays light

    mapping: dict[str, object] = {}
    for attempt in snapshot.attempts:
        for reference in attempt.evidence_refs:
            if reference.kind != "worker-provider-receipt":
                continue
            content = evidence.resolve(reference.kind, reference.id)
            if content is None or sha256_hex(content) != reference.sha256:
                raise CapsuleError(f"receipt {reference.id} is unresolved or changed")
            try:
                receipt = WorkerProviderReceipt.model_validate_json(content)
            except ValueError as error:
                raise CapsuleError(
                    f"receipt {reference.id} is not a worker provider receipt"
                ) from error
            if canonical_json_bytes(receipt.model_dump(mode="json")) != content:
                raise CapsuleError(f"receipt {reference.id} is not canonical")
            if mapping.setdefault(attempt.attempt_id, receipt) != receipt:
                raise CapsuleError(
                    f"attempt {attempt.attempt_id} binds conflicting provider receipts"
                )
    return mapping


def _receipts(
    evidence: SQLiteAttemptEvidenceStore,
    snapshot: MissionSnapshot,
    chains: tuple[_AttemptChain, ...],
) -> tuple[tuple[_Receipt, ...], dict[str, int]]:
    references: dict[str, EvidenceReference] = {}
    attempt_ids: dict[str, set[str]] = {}
    excluded: dict[str, set[str]] = {}

    def consider(reference: EvidenceReference, attempt_id: str) -> None:
        if reference.kind not in RECEIPT_KINDS:
            excluded.setdefault(reference.kind, set()).add(reference.id)
            return
        if references.setdefault(reference.id, reference) != reference:
            raise CapsuleError(f"receipt reference {reference.id} is ambiguous")
        attempt_ids.setdefault(reference.id, set()).add(attempt_id)

    for attempt in snapshot.attempts:
        for reference in attempt.evidence_refs:
            consider(reference, attempt.attempt_id)
    for chain in chains:
        for event in chain.events:
            for reference in event.references:
                consider(reference, chain.attempt.attempt_id)

    receipts: list[_Receipt] = []
    for identifier in sorted(references):
        reference = references[identifier]
        content = evidence.resolve(reference.kind, reference.id)
        if content is None or sha256_hex(content) != reference.sha256:
            raise CapsuleError(f"receipt {identifier} is unresolved or changed")
        try:
            value = json.loads(content)
        except ValueError as error:
            raise CapsuleError(f"receipt {identifier} is not JSON") from error
        if (
            not isinstance(value, dict)
            or canonical_json_bytes(value) != content
            or not _receipt_keys_are_public(value)
        ):
            raise CapsuleError(f"receipt {identifier} is not canonical public JSON")
        if reference.kind == "test-receipt":
            try:
                TrustedCheckReceipt.model_validate(value)
            except ValueError as error:
                raise CapsuleError(
                    f"receipt {identifier} is not a trusted check receipt"
                ) from error
        receipts.append(
            _Receipt(reference, content, tuple(sorted(attempt_ids[identifier])))
        )
    counts = {kind: len(ids) for kind, ids in sorted(excluded.items())}
    return tuple(receipts), counts


def _final_bundle(
    evidence: SQLiteAttemptEvidenceStore, events: tuple[MissionEvent, ...]
) -> _FinalBundle | None:
    ready = tuple(
        event
        for event in events
        if event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    )
    if not ready:
        return None
    event = ready[-1]
    references = tuple(
        item for item in event.references if item.kind == FINAL_BUNDLE_KIND
    )
    if len(references) != 1:
        raise CapsuleError("final result bundle reference is ambiguous")
    reference = references[0]
    raw = evidence.resolve(reference.kind, reference.id)
    if raw is None or sha256_hex(raw) != reference.sha256:
        raise CapsuleError("final result bundle is unresolved or changed")
    try:
        bundle = FinalResultBundleV2.model_validate_json(raw)
    except ValueError as error:
        raise CapsuleError("final result bundle is invalid") from error
    if (
        canonical_json_bytes(bundle.model_dump(mode="json")) != raw
        or bundle.bundle_id != event.payload.get("bundle_id")
        or bundle.bundle_sha256 != event.payload.get("bundle_sha256")
        or bundle.event_head_seq != event.seq - 1
        or bundle.event_head_sha256 != event.previous_event_sha256
    ):
        raise CapsuleError("final result bundle does not match its ready event")
    decision = _bundle_decision(events, event.seq, bundle.bundle_id)
    return _FinalBundle(raw, bundle, event, reference, decision)


def _envelopes(snapshot: MissionSnapshot) -> list[dict[str, Any]]:
    entries = []
    for publication in snapshot.publications:
        artifact = publication.artifact
        entries.append(
            {
                "publication_id": publication.publication_id,
                "plan_revision": publication.plan_revision,
                "task_id": publication.task_id,
                "attempt_id": publication.attempt_id,
                "output_name": publication.output_name,
                "kind": publication.kind,
                "sha256": publication.sha256,
                "artifact_id": None if artifact is None else artifact.artifact_id,
                "media_type": None if artifact is None else artifact.media_type,
                "byte_count": None if artifact is None else artifact.byte_count,
                "artifact_envelope_sha256": (
                    None if artifact is None else artifact.artifact_envelope_sha256
                ),
                "state": publication.state.value,
                "visibility": publication.visibility.value,
                "paths": list(publication.paths),
                "consumers": list(publication.consumers),
            }
        )
    return entries


def _unknowns(snapshot: MissionSnapshot, final: _FinalBundle | None) -> dict[str, Any]:
    return {
        "snapshot_unknowns": list(snapshot.unknowns),
        "bundle_unresolved_unknowns": (
            None if final is None else list(final.bundle.unresolved_unknowns)
        ),
        "note": (
            "Unknowns are recorded, never resolved by inference; a null bundle "
            "list means no final result bundle was registered."
        ),
    }


def _verify_document(mission_id: str) -> str:
    return f"""# Verifying this Graphene mission capsule

Schema: `{CAPSULE_SCHEMA}`
Mission: `{mission_id}`

## Command

From a clean checkout of the Graphene repository (Python 3.13 and `uv`):

    uv sync --frozen
    uv run --frozen python -m graphene.orchestration.capsule verify CAPSULE_DIR

`CAPSULE_DIR` is the path of this directory. The command prints a JSON report
with `verified`, an ordered `checks` list (`name`, `ok`, `detail`), and
`not_checked`. Exit status 0 means every check passed, 1 means a check failed
(the first failing check names exactly what disagreed), and 2 means the
capsule itself could not be read.

The verifier opens no mission database, Git repository, or network connection.
Every check is a recomputation over the files in this directory.

## Checks, in order

1. `manifest_file_digests` - every file listed in `manifest.json` exists, is a
   regular file, and has the listed SHA-256 and byte count; no unlisted files
   or symlinks are present.
2. `mission_event_chain` - `events.ndjson` is canonical JSON, seq runs
   contiguously from 1, each `payload_sha256` and `event_sha256` recompute,
   each `previous_event_sha256` links to the prior event, and the last event is
   the manifest head.
3. `attempt_evidence_chains` - every `attempts/<attempt_id>.ndjson` chain obeys
   the same digest and linkage rules, starts with `attempt.started`, and ends at
   the head recorded in the manifest.
4. `receipt_references` - every `test-receipt`, `worker-provider-receipt`, or
   `worker-provider-interruption`
   reference in attempt evidence has a `receipts/<id>.json` whose SHA-256
   matches, and every receipt file is referenced by attempt evidence.
5. `receipt_contents` - each receipt is canonical public JSON; each
   `test-receipt` parses as a `TrustedCheckReceipt` and its event payload equals
   the `check.completed` payload minted by the check runner in that chain.
6. `final_bundle` - `final-bundle.json` (when the manifest says one was
   registered) is canonical, its `bundle_sha256` recomputes, its event head
   points at an event in `events.ndjson` with that seq and digest, the
   `final_result_bundle.ready` event binds it, and its candidate tree digest
   equals the verification receipt's candidate tree digest, which is the
   exported `test-receipt` byte for byte.
7. `tree_manifest` - `tree-manifest.json` equals the tree identity carried by
   the final bundle (or records that none exists).
8. `publication_envelopes` - every entry in `envelopes.json` is bound by an
   `artifact.published` event (and `artifact.accepted` when accepted) carrying
   the same content and envelope digests, and every published artifact in the
   event log appears in `envelopes.json`.
9. `plan_revisions` - each `plan/revision-<n>.json` digest equals the digest
   recorded by the `plan.proposed` / `plan.revised` event for that revision;
   two events recording different digests for one revision fail closed.
10. `attempt_coverage` - every attempt named by a `task.leased` /
    `task.started` / `task.retried` / `task.completed` / `task.failed` /
    `task.cancelled` event was leased exactly once and has either an
    `attempts/<attempt_id>.ndjson` chain or an `attempts_without_evidence`
    entry in the manifest (never both, never neither), and no chain or entry
    names an attempt the event log never leased.
11. `manifest_summary` - the manifest's summary claims recompute from the
    capsule's own bytes: `policy` from `project.created`, the creation source
    from `mission.created`, `mission_status` by replaying the event log's
    status transitions with the reducer's rules, `final_bundle.decision` from
    the `final_candidate.approved` / `final_candidate.rejected` events that
    bind the bundle, each attempt's task, worker, attempt number, fencing
    token, state, and result code from its `task.*` events and its terminal
    evidence event, and every `counts` and `excluded_artifact_kinds` entry
    from the events, chains, receipts, envelopes, and plan files present.

## What is verified offline

Hash-chain integrity and linkage of the public mission events and of every
attempt evidence chain; that receipts, envelopes, plan revisions, and the final
bundle are the exact bytes those chains committed to; that the final bundle's
tree identity is the one the trusted check runner attested; and that the
manifest's summary claims agree with those bytes.

## What is not verifiable offline

- {NOT_VERIFIABLE_OFFLINE[3]}: {PRODUCER_NOTE}.
- {NOT_VERIFIABLE_OFFLINE[0]}: patch and source bytes are not in the capsule,
  so the candidate tree digest is checked against the receipt, not recomputed
  from bytes.
- {NOT_VERIFIABLE_OFFLINE[1]}: worker-provider receipts are sanitized,
  worker-reported records, not a provider-side attestation.
- {NOT_VERIFIABLE_OFFLINE[2]}: timestamps come from the mission store clock.
- `snapshot_sha256`, `exported_at`, `mission.created_at`, and
  `mission.final_outcome` in the manifest: the materialized snapshot digest,
  the export clock, the mission contract's creation time, and the store's
  outcome label cannot be recomputed from the capsule; the final decision is
  verified through `final_bundle.decision` instead.
- Artifacts of excluded kinds (see `excluded_artifact_kinds` in the manifest)
  are present only as digests.
- Materialized task-state replay requires the SQLite mission store; only the
  mission status dimension is replayed here.

## Redaction

{REDACTION_NOTE}

{AUTHORITY_NOTE}
"""


# --------------------------------------------------------------------------- #
# Export: writing the capsule
# --------------------------------------------------------------------------- #


def _make_private_directory(path: Path) -> None:
    os.mkdir(path, _DIRECTORY_MODE)
    os.chmod(path, _DIRECTORY_MODE)


def _write_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        _FILE_MODE,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, _FILE_MODE)


def export_mission_capsule(
    *,
    store: Any,
    evidence: SQLiteAttemptEvidenceStore,
    mission_id: str,
    output_dir: Path,
    now: datetime | None = None,
) -> dict[str, object]:
    """Write ``<output_dir>/<mission_id>.graphene-capsule`` from verified state."""

    mission_id = _validated_mission_id(mission_id)
    if not isinstance(evidence, SQLiteAttemptEvidenceStore):
        raise CapsuleError(
            "capsule export requires the mission's SQLite attempt evidence store"
        )
    bound = getattr(store, "artifact_resolver", None)
    if bound is None and hasattr(store, "bind_artifact_resolver"):
        store.bind_artifact_resolver(evidence)
    elif bound is not evidence:
        raise CapsuleError(
            "capsule export evidence store is not the mission's bound resolver"
        )
    exported_at = datetime.now(UTC) if now is None else now
    if exported_at.utcoffset() is None:
        raise CapsuleError("capsule export time must be timezone-aware")
    exported_at = exported_at.astimezone(UTC)

    output_dir = Path(output_dir)
    try:
        metadata = output_dir.lstat()
    except OSError as error:
        raise CapsuleError("capsule output directory is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise CapsuleError(
            "capsule output directory must be an existing non-symlink directory"
        )
    capsule_dir = output_dir / f"{mission_id}{CAPSULE_SUFFIX}"
    if capsule_dir.is_symlink() or capsule_dir.exists():
        raise CapsuleError("capsule directory already exists")

    try:
        snapshot = store.snapshot(mission_id)
        head = store.verify(mission_id)
    except Exception as error:
        raise CapsuleError(
            f"mission could not be verified for export: {error}"
        ) from error
    if head != snapshot.head:
        raise CapsuleError("mission changed during capsule export")
    events = _mission_events(store, mission_id, head)
    plans = _plan_revisions(store, snapshot, events)
    chains, skipped = _attempt_chains(evidence, snapshot)
    receipts, excluded = _receipts(evidence, snapshot, chains)
    final = _final_bundle(evidence, events)
    overlap = measure_overlap(
        snapshot, provider_receipts=_provider_call_receipts(evidence, snapshot)
    ).model_dump(mode="json")

    files: dict[str, bytes] = {}
    files[EVENTS_FILE] = _ndjson(event.model_dump(mode="json") for event in events)
    plan_entries = []
    for revision, plan, digest in plans:
        name = f"{PLAN_DIRECTORY}/revision-{revision}.json"
        files[name] = _pretty_json(
            {
                "mission_id": mission_id,
                "plan_revision": revision,
                "plan_sha256": digest,
                "plan": plan.model_dump(mode="json"),
            }
        )
        plan_entries.append({"revision": revision, "plan_sha256": digest, "file": name})
    attempt_entries = []
    for chain in chains:
        name = f"{ATTEMPTS_DIRECTORY}/{chain.attempt.attempt_id}.ndjson"
        files[name] = _ndjson(event.model_dump(mode="json") for event in chain.events)
        attempt_entries.append(
            {
                "attempt_id": chain.attempt.attempt_id,
                "task_id": chain.attempt.task_id,
                "worker_id": chain.attempt.worker_id,
                "attempt_number": chain.attempt.attempt_number,
                "fencing_token": chain.attempt.fencing_token,
                "state": chain.attempt.state.value,
                "result_code": chain.attempt.result_code,
                "evidence_id": chain.evidence_id,
                "event_count": len(chain.events),
                "event_sha256": chain.events[-1].event_sha256,
                "file": name,
            }
        )
    receipt_entries = []
    for receipt in receipts:
        name = f"{RECEIPTS_DIRECTORY}/{receipt.reference.id}.json"
        files[name] = receipt.content
        receipt_entries.append(
            {
                "id": receipt.reference.id,
                "kind": receipt.reference.kind,
                "sha256": receipt.reference.sha256,
                "bytes": len(receipt.content),
                "attempt_ids": list(receipt.attempt_ids),
                "file": name,
            }
        )
    files[ENVELOPES_FILE] = _pretty_json(_envelopes(snapshot))
    if final is None:
        final_entry: dict[str, Any] = {
            "present": False,
            "note": "No FinalResultBundleV2 was registered for this mission.",
        }
    else:
        files[FINAL_BUNDLE_FILE] = final.raw
        final_entry = {
            "present": True,
            "file": FINAL_BUNDLE_FILE,
            "bundle_id": final.bundle.bundle_id,
            "bundle_sha256": final.bundle.bundle_sha256,
            "event_seq": final.event.seq,
            "event_head_seq": final.bundle.event_head_seq,
            "reference": final.reference.model_dump(mode="json"),
            "decision": final.decision,
        }
    files[TREE_MANIFEST_FILE] = _pretty_json(
        _tree_manifest_value(None if final is None else final.bundle)
    )
    files[OVERLAP_FILE] = _pretty_json(overlap)
    files[UNKNOWNS_FILE] = _pretty_json(_unknowns(snapshot, final))
    files[VERIFY_FILE] = _verify_document(mission_id).encode("utf-8")

    manifest = {
        "schema": CAPSULE_SCHEMA,
        "mission_id": mission_id,
        "exported_at": exported_at.isoformat(),
        "mission_status": snapshot.mission.status.value,
        "mission": {
            "status": snapshot.mission.status.value,
            "final_outcome": snapshot.mission.final_outcome,
            "creation_source": snapshot.mission.creation_source,
            "plan_revision": snapshot.plan.revision,
            "created_at": snapshot.mission.created_at.isoformat(),
        },
        "head": {
            "seq": head.seq,
            "event_count": head.event_count,
            "event_sha256": head.event_sha256,
        },
        "snapshot_sha256": snapshot.snapshot_sha256,
        "policy": {
            "policy_id": snapshot.policy.policy_id,
            "revision": snapshot.policy.revision,
            "policy_sha256": snapshot.policy.policy_sha256,
            "base_sha": snapshot.policy.base_sha,
            "repo_id": snapshot.policy.repo_id,
        },
        "plan_revisions": plan_entries,
        "attempts": attempt_entries,
        "attempts_without_evidence": list(skipped),
        "receipts": receipt_entries,
        "excluded_artifact_kinds": excluded,
        "final_bundle": final_entry,
        "counts": {
            "events": len(events),
            "plan_revisions": len(plan_entries),
            "attempts": len(snapshot.attempts),
            "attempt_evidence_chains": len(chains),
            "attempt_evidence_events": sum(len(chain.events) for chain in chains),
            "receipts": len(receipt_entries),
            "publications": len(snapshot.publications),
            "leases": len(snapshot.leases),
            "gates": len(snapshot.gates),
            "excluded_artifacts": sum(excluded.values()),
        },
        "files": {
            name: {"sha256": sha256_hex(content), "bytes": len(content)}
            for name, content in sorted(files.items())
        },
        "redaction": REDACTION_NOTE,
        "not_verifiable_offline": list(NOT_VERIFIABLE_OFFLINE),
        "authority_note": AUTHORITY_NOTE,
    }
    manifest_bytes = _pretty_json(manifest)

    try:
        os.mkdir(capsule_dir, _DIRECTORY_MODE)
    except FileExistsError as error:
        raise CapsuleError("capsule directory already exists") from error
    except OSError as error:
        raise CapsuleError("capsule directory could not be created") from error
    # From here on the directory is ours: any failure, including the chmod that
    # makes it private, removes it so a retry never finds a stale empty capsule.
    try:
        os.chmod(capsule_dir, _DIRECTORY_MODE)
        for directory in (PLAN_DIRECTORY, ATTEMPTS_DIRECTORY, RECEIPTS_DIRECTORY):
            _make_private_directory(capsule_dir / directory)
        for name in sorted(files):
            _write_private_file(capsule_dir / name, files[name])
        _write_private_file(capsule_dir / MANIFEST_FILE, manifest_bytes)
    except OSError as error:
        shutil.rmtree(capsule_dir, ignore_errors=True)
        raise CapsuleError("capsule could not be written") from error
    return {
        "status": "exported",
        "schema": CAPSULE_SCHEMA,
        "mission_id": mission_id,
        "capsule_dir": str(capsule_dir),
        "manifest_sha256": sha256_hex(manifest_bytes),
        "head": manifest["head"],
        "counts": manifest["counts"],
        "final_bundle_present": final is not None,
        "files": [*sorted(files), MANIFEST_FILE],
        "redaction": REDACTION_NOTE,
    }


# --------------------------------------------------------------------------- #
# Cold verification
# --------------------------------------------------------------------------- #


class _CheckFailed(Exception):
    pass


@dataclass
class _Verification:
    capsule_dir: Path
    manifest: dict[str, Any]
    mission_id: str
    files: dict[str, bytes] = field(default_factory=dict)
    events: tuple[MissionEvent, ...] = ()
    events_by_seq: dict[int, MissionEvent] = field(default_factory=dict)
    chains: dict[str, tuple[AttemptEvidenceEvent, ...]] = field(default_factory=dict)
    receipts: dict[str, tuple[str, bytes]] = field(default_factory=dict)
    bundle: FinalResultBundleV2 | None = None
    envelopes: list[dict[str, Any]] = field(default_factory=list)
    attempt_log: dict[str, tuple[MissionEvent, ...]] = field(default_factory=dict)
    attempts_without_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    not_checked: list[str] = field(default_factory=list)


def _relative_name(capsule_dir: Path, path: Path) -> str:
    return path.relative_to(capsule_dir).as_posix()


def _read_capsule_file(path: Path) -> bytes:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise _CheckFailed(f"{path.name} is not a regular file")
    if metadata.st_size > _MAX_CAPSULE_FILE_BYTES:
        raise _CheckFailed(f"{path.name} exceeds the capsule file size bound")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    with os.fdopen(descriptor, "rb") as handle:
        return handle.read()


def _safe_relative_name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise _CheckFailed("manifest lists a malformed file name")
    parsed = PurePosixPath(name)
    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in name
        or "\0" in name
        or parsed.as_posix() != name
    ):
        raise _CheckFailed(f"manifest lists an unsafe file name {name!r}")
    return name


def _load_json_lines(raw: bytes, label: str) -> list[tuple[int, dict[str, Any], bytes]]:
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    parsed = []
    for number, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except ValueError as error:
            raise _CheckFailed(f"{label} line {number} is not JSON") from error
        if not isinstance(value, dict) or canonical_json_bytes(value) != line:
            raise _CheckFailed(f"{label} line {number} is not canonical JSON")
        parsed.append((number, value, line))
    return parsed


def _check_chained_value(
    value: dict[str, Any], number: int, previous: str | None, label: str
) -> None:
    if value.get("seq") != number:
        raise _CheckFailed(
            f"{label} seq {value.get('seq')!r} at line {number} breaks contiguity"
        )
    if value.get("payload_sha256") != canonical_json_sha256(value.get("payload")):
        raise _CheckFailed(f"{label} seq {number} payload digest does not match")
    without_digest = {key: item for key, item in value.items() if key != "event_sha256"}
    if value.get("event_sha256") != canonical_json_sha256(without_digest):
        raise _CheckFailed(f"{label} seq {number} event digest does not match")
    if value.get("previous_event_sha256") != previous:
        raise _CheckFailed(
            f"{label} seq {number} does not link to its predecessor digest"
        )


def _check_manifest_files(context: _Verification) -> str:
    listed = context.manifest.get("files")
    if not isinstance(listed, dict):
        raise _CheckFailed("manifest has no file table")
    found: dict[str, Path] = {}
    found_directories: set[str] = set()
    for root, directories, names in os.walk(context.capsule_dir, followlinks=False):
        root_path = Path(root)
        for entry in directories:
            path = root_path / entry
            if stat.S_ISLNK(path.lstat().st_mode):
                raise _CheckFailed(
                    f"{_relative_name(context.capsule_dir, path)} is a symlink"
                )
            found_directories.add(_relative_name(context.capsule_dir, path))
        for entry in names:
            path = root_path / entry
            metadata = path.lstat()
            relative = _relative_name(context.capsule_dir, path)
            if stat.S_ISLNK(metadata.st_mode):
                raise _CheckFailed(f"{relative} is a symlink")
            if not stat.S_ISREG(metadata.st_mode):
                raise _CheckFailed(f"{relative} is not a regular file")
            if relative != MANIFEST_FILE:
                found[relative] = path
    if found_directories != _CAPSULE_DIRECTORIES:
        raise _CheckFailed(
            f"capsule directory set does not match the layout: "
            f"missing={sorted(_CAPSULE_DIRECTORIES - found_directories)} "
            f"unlisted={sorted(found_directories - _CAPSULE_DIRECTORIES)}"
        )
    expected = {_safe_relative_name(name) for name in listed}
    if set(found) != expected:
        missing = sorted(expected - set(found))
        unlisted = sorted(set(found) - expected)
        raise _CheckFailed(
            f"manifest file set does not match the directory: "
            f"missing={missing} unlisted={unlisted}"
        )
    for name in sorted(expected):
        described = listed[name]
        content = _read_capsule_file(found[name])
        if (
            not isinstance(described, dict)
            or described.get("sha256") != sha256_hex(content)
            or described.get("bytes") != len(content)
        ):
            raise _CheckFailed(f"file {name} digest does not match the manifest")
        context.files[name] = content
    return f"{len(expected)} files match their manifest digests"


def _check_mission_events(context: _Verification) -> str:
    raw = context.files.get(EVENTS_FILE)
    if raw is None:
        raise _CheckFailed(f"{EVENTS_FILE} is missing")
    previous: str | None = None
    events: list[MissionEvent] = []
    for number, value, _line in _load_json_lines(raw, "mission event"):
        _check_chained_value(value, number, previous, "mission event")
        try:
            event = MissionEvent.model_validate(value)
        except ValueError as error:
            raise _CheckFailed(f"mission event seq {number} is invalid") from error
        if event.mission_id != context.mission_id:
            raise _CheckFailed(f"mission event seq {number} names another mission")
        previous = event.event_sha256
        events.append(event)
    head = context.manifest.get("head")
    if (
        not events
        or not isinstance(head, dict)
        or len(events) != head.get("event_count")
        or events[-1].seq != head.get("seq")
        or events[-1].event_sha256 != head.get("event_sha256")
    ):
        raise _CheckFailed("mission event chain head does not match the manifest")
    context.events = tuple(events)
    context.events_by_seq = {event.seq: event for event in events}
    return (
        f"{len(events)} hash-chained mission events recomputed; head seq "
        f"{events[-1].seq} sha256 {events[-1].event_sha256[:12]}"
    )


def _check_attempt_chains(context: _Verification) -> str:
    entries = context.manifest.get("attempts")
    if not isinstance(entries, list):
        raise _CheckFailed("manifest has no attempt table")
    described: set[str] = set()
    total = 0
    for entry in entries:
        attempt_id = entry.get("attempt_id")
        name = f"{ATTEMPTS_DIRECTORY}/{attempt_id}.ndjson"
        if entry.get("file") != name:
            raise _CheckFailed(f"attempt {attempt_id} file name is not canonical")
        raw = context.files.get(name)
        if raw is None:
            raise _CheckFailed(f"attempt evidence file {name} is missing")
        label = f"attempt {attempt_id} evidence"
        previous: str | None = None
        events: list[AttemptEvidenceEvent] = []
        for number, value, _line in _load_json_lines(raw, label):
            _check_chained_value(value, number, previous, label)
            try:
                event = AttemptEvidenceEvent.model_validate(value)
            except ValueError as error:
                raise _CheckFailed(f"{label} seq {number} is invalid") from error
            if (
                event.evidence_id != entry.get("evidence_id")
                or event.mission_id != context.mission_id
                or event.task_id != entry.get("task_id")
                or event.attempt_id != attempt_id
            ):
                raise _CheckFailed(f"{label} seq {number} names another attempt")
            previous = event.event_sha256
            events.append(event)
        if (
            not events
            or events[0].event_type != AttemptEvidenceEventType.ATTEMPT_STARTED
        ):
            raise _CheckFailed(f"{label} does not start with attempt.started")
        if len(events) != entry.get("event_count") or previous != entry.get(
            "event_sha256"
        ):
            raise _CheckFailed(f"{label} head does not match the manifest")
        context.chains[attempt_id] = tuple(events)
        described.add(name)
        total += len(events)
    for name in context.files:
        if name.startswith(f"{ATTEMPTS_DIRECTORY}/") and name not in described:
            raise _CheckFailed(f"attempt evidence file {name} is not in the manifest")
    return f"{len(entries)} attempt evidence chains recomputed ({total} events)"


def _check_receipt_references(context: _Verification) -> str:
    entries = context.manifest.get("receipts")
    if not isinstance(entries, list):
        raise _CheckFailed("manifest has no receipt table")
    by_id = {entry.get("id"): entry for entry in entries}
    referenced: dict[str, EvidenceReference] = {}
    for events in context.chains.values():
        for event in events:
            for reference in event.references:
                if reference.kind not in RECEIPT_KINDS:
                    continue
                if referenced.setdefault(reference.id, reference) != reference:
                    raise _CheckFailed(
                        f"receipt reference {reference.id} is ambiguous across "
                        "attempt evidence"
                    )
    for identifier in sorted(referenced):
        reference = referenced[identifier]
        name = f"{RECEIPTS_DIRECTORY}/{identifier}.json"
        content = context.files.get(name)
        if content is None:
            raise _CheckFailed(
                f"receipt {identifier} ({reference.kind}) has no receipts file"
            )
        if sha256_hex(content) != reference.sha256:
            raise _CheckFailed(
                f"receipt {identifier} digest does not match its evidence reference"
            )
        entry = by_id.get(identifier)
        if (
            entry is None
            or entry.get("kind") != reference.kind
            or entry.get("sha256") != reference.sha256
            or entry.get("file") != name
        ):
            raise _CheckFailed(f"receipt {identifier} is not in the manifest")
        context.receipts[identifier] = (reference.kind, content)
    for name in context.files:
        if name.startswith(f"{RECEIPTS_DIRECTORY}/"):
            identifier = name[len(RECEIPTS_DIRECTORY) + 1 :].removesuffix(".json")
            if identifier not in referenced:
                raise _CheckFailed(
                    f"receipt file {name} is not referenced by attempt evidence"
                )
    for identifier in by_id:
        if identifier not in referenced:
            raise _CheckFailed(
                f"manifest receipt {identifier} is not referenced by attempt evidence"
            )
    return f"{len(referenced)} receipt files match their evidence references"


def _check_worker_provider_receipt(identifier: str, content: bytes) -> None:
    # Lazy: the runtime module pulls in the sandbox stack, which a cold verifier
    # only needs when a capsule actually carries a worker-provider receipt.
    from .worker_runtime import WorkerProviderReceipt

    try:
        receipt = WorkerProviderReceipt.model_validate_json(content)
    except ValueError as error:
        raise _CheckFailed(
            f"worker provider receipt {identifier} is not a valid WorkerProviderReceipt"
        ) from error
    if canonical_json_bytes(receipt.model_dump(mode="json")) != content:
        raise _CheckFailed(
            f"worker provider receipt {identifier} is not the canonical bytes of "
            "its WorkerProviderReceipt"
        )


def _check_worker_provider_interruption(identifier: str, content: bytes) -> None:
    from .worker_runtime import WorkerProviderInterruption

    try:
        interruption = WorkerProviderInterruption.model_validate_json(content)
    except ValueError as error:
        raise _CheckFailed(
            f"worker provider interruption {identifier} is not a valid "
            "WorkerProviderInterruption"
        ) from error
    if canonical_json_bytes(interruption.model_dump(mode="json")) != content:
        raise _CheckFailed(
            f"worker provider interruption {identifier} is not the canonical bytes "
            "of its WorkerProviderInterruption"
        )


def _check_receipt_contents(context: _Verification) -> str:
    checks = 0
    provider_receipts = 0
    provider_interruptions = 0
    for identifier, (kind, content) in sorted(context.receipts.items()):
        try:
            value = json.loads(content)
        except ValueError as error:
            raise _CheckFailed(f"receipt {identifier} is not JSON") from error
        if not isinstance(value, dict) or canonical_json_bytes(value) != content:
            raise _CheckFailed(f"receipt {identifier} is not canonical JSON")
        if not _receipt_keys_are_public(value):
            raise _CheckFailed(f"receipt {identifier} contains a non-public key")
        if kind == "worker-provider-receipt":
            _check_worker_provider_receipt(identifier, content)
            provider_receipts += 1
            continue
        if kind == "worker-provider-interruption":
            _check_worker_provider_interruption(identifier, content)
            provider_interruptions += 1
            continue
        if kind != "test-receipt":
            raise _CheckFailed(f"receipt {identifier} has unsupported kind {kind!r}")
        try:
            receipt = TrustedCheckReceipt.model_validate(value)
        except ValueError as error:
            raise _CheckFailed(
                f"test receipt {identifier} is not a valid trusted check receipt"
            ) from error
        minted = [
            event
            for events in context.chains.values()
            for event in events
            if event.event_type == AttemptEvidenceEventType.CHECK_COMPLETED
            and any(reference.id == identifier for reference in event.references)
        ]
        if not minted:
            raise _CheckFailed(
                f"test receipt {identifier} was not minted by a check.completed event"
            )
        expected = receipt.event_payload(sha256_hex(content))
        for event in minted:
            if event.payload != expected:
                raise _CheckFailed(
                    f"test receipt {identifier} does not match its check.completed "
                    "payload"
                )
            if (receipt.mission_id, receipt.task_id, receipt.attempt_id) != (
                event.mission_id,
                event.task_id,
                event.attempt_id,
            ):
                raise _CheckFailed(f"test receipt {identifier} names another attempt")
        checks += 1
    return (
        f"{len(context.receipts)} receipts are canonical public JSON; "
        f"{checks} trusted check receipts match their check.completed payloads; "
        f"{provider_receipts} worker provider receipts are canonical "
        f"WorkerProviderReceipt bytes; {provider_interruptions} worker provider "
        "interruptions are canonical WorkerProviderInterruption bytes"
    )


def _check_final_bundle(context: _Verification) -> str:
    entry = context.manifest.get("final_bundle")
    if not isinstance(entry, dict):
        raise _CheckFailed("manifest has no final bundle entry")
    if not entry.get("present"):
        if FINAL_BUNDLE_FILE in context.files:
            raise _CheckFailed(
                f"{FINAL_BUNDLE_FILE} is present but the manifest says none was "
                "registered"
            )
        context.not_checked.append(
            "final result bundle: the manifest records that none was registered"
        )
        return "no final result bundle registered (manifest says absent)"
    raw = context.files.get(FINAL_BUNDLE_FILE)
    if raw is None:
        raise _CheckFailed(f"{FINAL_BUNDLE_FILE} is missing")
    try:
        bundle = FinalResultBundleV2.model_validate_json(raw)
    except ValueError as error:
        raise _CheckFailed(
            "final bundle is invalid or its bundle_sha256 does not recompute"
        ) from error
    if canonical_json_bytes(bundle.model_dump(mode="json")) != raw:
        raise _CheckFailed("final bundle bytes are not canonical")
    if bundle.bundle_id != entry.get("bundle_id") or bundle.bundle_sha256 != entry.get(
        "bundle_sha256"
    ):
        raise _CheckFailed("final bundle identity does not match the manifest")
    reference = entry.get("reference")
    if (
        not isinstance(reference, dict)
        or reference.get("kind") != FINAL_BUNDLE_KIND
        or reference.get("sha256") != sha256_hex(raw)
    ):
        raise _CheckFailed(
            "final bundle bytes do not match the manifest evidence reference"
        )
    if bundle.mission_id != context.mission_id:
        raise _CheckFailed("final bundle names another mission")
    head_event = context.events_by_seq.get(bundle.event_head_seq)
    if head_event is None or head_event.event_sha256 != bundle.event_head_sha256:
        raise _CheckFailed(
            f"final bundle event head seq {bundle.event_head_seq} is not in the "
            "mission event chain with that digest"
        )
    ready = context.events_by_seq.get(entry.get("event_seq"))
    if (
        ready is None
        or ready.event_type != MissionEventType.FINAL_RESULT_BUNDLE_READY
        or ready.seq != bundle.event_head_seq + 1
        or ready.previous_event_sha256 != bundle.event_head_sha256
        or ready.payload.get("bundle_id") != bundle.bundle_id
        or ready.payload.get("bundle_sha256") != bundle.bundle_sha256
        or not any(
            item.kind == FINAL_BUNDLE_KIND and item.sha256 == sha256_hex(raw)
            for item in ready.references
        )
    ):
        raise _CheckFailed("final_result_bundle.ready event does not bind this bundle")
    receipt = bundle.verification_receipt
    if (
        bundle.candidate_tree_sha256 != receipt.candidate_tree_sha256
        or bundle.candidate_tree_hash_version != receipt.candidate_tree_hash_version
    ):
        raise _CheckFailed(
            "final bundle candidate tree does not match the verification receipt"
        )
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    if sha256_hex(receipt_bytes) != bundle.verification_reference.content_sha256:
        raise _CheckFailed(
            "final bundle verification receipt digest does not match its reference"
        )
    exported = context.receipts.get(bundle.verification_reference.artifact_id)
    if exported is None or exported != ("test-receipt", receipt_bytes):
        raise _CheckFailed(
            "final bundle verification receipt is not the exported test receipt"
        )
    policy = context.manifest.get("policy")
    if (
        not isinstance(policy, dict)
        or bundle.policy_id != policy.get("policy_id")
        or bundle.policy_revision != policy.get("revision")
        or bundle.policy_sha256 != policy.get("policy_sha256")
        or bundle.base_commit != policy.get("base_sha")
    ):
        raise _CheckFailed("final bundle policy binding does not match the manifest")
    context.bundle = bundle
    return (
        f"final bundle {bundle.bundle_id} recomputed; bound to event head seq "
        f"{bundle.event_head_seq}; candidate tree "
        f"{bundle.candidate_tree_sha256[:12]} matches the verification receipt"
    )


def _check_tree_manifest(context: _Verification) -> str:
    raw = context.files.get(TREE_MANIFEST_FILE)
    if raw is None:
        raise _CheckFailed(f"{TREE_MANIFEST_FILE} is missing")
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise _CheckFailed(f"{TREE_MANIFEST_FILE} is not JSON") from error
    if context.bundle is None:
        if not isinstance(value, dict) or value.get("present") is not False:
            raise _CheckFailed(
                "tree manifest claims a result tree but no final bundle is registered"
            )
        return "tree manifest records no result tree (no final bundle)"
    if value != _tree_manifest_value(context.bundle):
        raise _CheckFailed("tree manifest does not match the final bundle")
    return (
        f"tree manifest matches the final bundle: "
        f"{len(context.bundle.changed_paths)} changed paths, result tree "
        f"{context.bundle.result_tree_id[:12]}"
    )


_PUBLICATION_KEYS = (
    "artifact_bytes_sha256",
    "artifact_proof_sha256",
    "attempt_id",
    "kind",
    "output_name",
    "publication_id",
    "task_id",
)


def _check_envelopes(context: _Verification) -> str:
    raw = context.files.get(ENVELOPES_FILE)
    if raw is None:
        raise _CheckFailed(f"{ENVELOPES_FILE} is missing")
    try:
        entries = json.loads(raw)
    except ValueError as error:
        raise _CheckFailed(f"{ENVELOPES_FILE} is not JSON") from error
    if not isinstance(entries, list):
        raise _CheckFailed(f"{ENVELOPES_FILE} is not a list")
    published: dict[str, MissionEvent] = {}
    accepted: dict[str, MissionEvent] = {}
    rejected: set[str] = set()
    for event in context.events:
        publication_id = event.payload.get("publication_id")
        if event.event_type == MissionEventType.ARTIFACT_PUBLISHED:
            if publication_id in published:
                raise _CheckFailed(f"publication {publication_id} published twice")
            published[publication_id] = event
        elif event.event_type == MissionEventType.ARTIFACT_ACCEPTED:
            accepted[publication_id] = event
        elif event.event_type == MissionEventType.ARTIFACT_REJECTED:
            rejected.add(publication_id)
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        publication_id = entry.get("publication_id")
        event = published.get(publication_id)
        if event is None:
            raise _CheckFailed(
                f"publication {publication_id} has no artifact.published event"
            )
        expected = {
            "artifact_bytes_sha256": entry.get("sha256"),
            "artifact_proof_sha256": entry.get("artifact_envelope_sha256"),
            "attempt_id": entry.get("attempt_id"),
            "kind": entry.get("kind"),
            "output_name": entry.get("output_name"),
            "publication_id": publication_id,
            "task_id": entry.get("task_id"),
        }
        if {key: event.payload.get(key) for key in _PUBLICATION_KEYS} != expected:
            raise _CheckFailed(
                f"publication {publication_id} digests do not match its "
                "artifact.published event"
            )
        if not any(
            item.kind == "artifact-envelope-v2"
            and item.id == publication_id
            and item.sha256 == entry.get("artifact_envelope_sha256")
            for item in event.references
        ):
            raise _CheckFailed(
                f"publication {publication_id} envelope digest is not referenced "
                "by its event"
            )
        state = entry.get("state")
        if state == "accepted":
            acceptance = accepted.get(publication_id)
            if (
                acceptance is None
                or {key: acceptance.payload.get(key) for key in _PUBLICATION_KEYS}
                != expected
            ):
                raise _CheckFailed(
                    f"publication {publication_id} is marked accepted without a "
                    "matching artifact.accepted event"
                )
        elif state == "rejected":
            if publication_id not in rejected:
                raise _CheckFailed(
                    f"publication {publication_id} is marked rejected without an "
                    "artifact.rejected event"
                )
        elif state != "published":
            raise _CheckFailed(
                f"publication {publication_id} has unknown state {state!r}"
            )
        by_id[publication_id] = entry
    missing = sorted(set(published) - set(by_id))
    if missing:
        raise _CheckFailed(
            f"publications {missing} are in the event log but not in {ENVELOPES_FILE}"
        )
    if context.bundle is not None:
        for publication in (
            context.bundle.candidate_publication,
            context.bundle.verification_publication,
        ):
            entry = by_id.get(publication.publication_id)
            if (
                entry is None
                or entry.get("sha256") != publication.sha256
                or entry.get("artifact_envelope_sha256")
                != publication.published_reference().artifact_envelope_sha256
                or entry.get("state") != "accepted"
            ):
                raise _CheckFailed(
                    f"final bundle publication {publication.publication_id} is not "
                    "an accepted exported envelope"
                )
    context.envelopes = entries
    return f"{len(entries)} publication envelopes match their artifact events"


def _check_plan_revisions(context: _Verification) -> str:
    entries = context.manifest.get("plan_revisions")
    if not isinstance(entries, list) or not entries:
        raise _CheckFailed("manifest has no plan revisions")
    revisions = [entry.get("revision") for entry in entries]
    if revisions != list(range(1, len(entries) + 1)):
        raise _CheckFailed("plan revisions are not contiguous from 1")
    recorded = _recorded_plan_digests(context.events, failure=_CheckFailed)
    validated: str | None = None
    for event in context.events:
        if event.event_type == MissionEventType.PLAN_REVISED:
            revision = event.payload.get("plan_revision")
            if event.payload.get("previous_plan_revision") != revision - 1:
                raise _CheckFailed(
                    f"plan revision {revision} event does not link to its predecessor"
                )
        elif event.event_type == MissionEventType.PLAN_VALIDATED:
            validated = event.payload.get("plan_sha256")
    digests: dict[int, str] = {}
    for entry in entries:
        revision = entry["revision"]
        name = f"{PLAN_DIRECTORY}/revision-{revision}.json"
        if entry.get("file") != name:
            raise _CheckFailed(f"plan revision {revision} file name is not canonical")
        raw = context.files.get(name)
        if raw is None:
            raise _CheckFailed(f"plan revision {revision} file is missing")
        try:
            value = json.loads(raw)
        except ValueError as error:
            raise _CheckFailed(f"plan revision {revision} file is not JSON") from error
        if not isinstance(value, dict) or "plan" not in value:
            raise _CheckFailed(f"plan revision {revision} file has no plan")
        digest = canonical_json_sha256(value["plan"])
        if (
            value.get("plan_revision") != revision
            or value.get("plan_sha256") != digest
            or entry.get("plan_sha256") != digest
        ):
            raise _CheckFailed(
                f"plan revision {revision} digest does not match its recorded sha256"
            )
        try:
            plan = Plan.model_validate(value["plan"])
        except ValueError as error:
            raise _CheckFailed(f"plan revision {revision} is invalid") from error
        if plan.revision != revision or plan.mission_id != context.mission_id:
            raise _CheckFailed(f"plan revision {revision} names another revision")
        if recorded.get(revision) != digest:
            raise _CheckFailed(
                f"plan revision {revision} digest is not recorded by a plan event"
            )
        if revision == 1 and validated != digest:
            raise _CheckFailed("plan revision 1 was not validated with this digest")
        digests[revision] = digest
    if set(recorded) != set(digests):
        raise _CheckFailed("plan events record revisions the capsule does not carry")
    mission = context.manifest.get("mission")
    if not isinstance(mission, dict) or mission.get("plan_revision") != revisions[-1]:
        raise _CheckFailed("manifest current plan revision is not the last revision")
    if context.bundle is not None and (
        digests.get(context.bundle.plan_revision) != context.bundle.plan_sha256
    ):
        raise _CheckFailed(
            "final bundle plan digest does not match the exported plan revision"
        )
    return f"{len(entries)} plan revisions match their recorded digests"


_ATTEMPT_EVENT_TYPES = frozenset(
    {
        MissionEventType.TASK_LEASED,
        MissionEventType.TASK_STARTED,
        MissionEventType.TASK_RETRIED,
        MissionEventType.TASK_COMPLETED,
        MissionEventType.TASK_FAILED,
        MissionEventType.TASK_CANCELLED,
    }
)
_ATTEMPT_TERMINAL_EVENT_TYPES = frozenset(
    {
        MissionEventType.TASK_RETRIED,
        MissionEventType.TASK_COMPLETED,
        MissionEventType.TASK_FAILED,
        MissionEventType.TASK_CANCELLED,
    }
)
_ATTEMPT_LEASE_FIELDS = ("task_id", "worker_id", "attempt_number", "fencing_token")
# Events that end every in-flight attempt without naming it: the store abandons
# leased/running attempts on a plan revision and cancels them with the mission.
_ATTEMPT_SWEEP_EVENT_TYPES = frozenset(
    {MissionEventType.OPERATOR_CANCELLED, MissionEventType.PLAN_REVISED}
)
# The mission-status dimension of ``reducer.reduce_events``, mirrored so a cold
# verifier can replay ``mission_status`` without the store or its task rows.
_STATUS_TARGETS: dict[MissionEventType, MissionStatus] = {
    MissionEventType.PLAN_APPROVED: MissionStatus.RUNNING,
    MissionEventType.PLAN_REJECTED: MissionStatus.REJECTED,
    MissionEventType.OPERATOR_PAUSED: MissionStatus.PAUSED,
    MissionEventType.OPERATOR_RESUMED: MissionStatus.RUNNING,
    MissionEventType.OPERATOR_CANCELLED: MissionStatus.CANCELLED,
    MissionEventType.FINAL_CANDIDATE_READY: MissionStatus.AWAITING_RESULT,
    MissionEventType.FINAL_CANDIDATE_REJECTED: MissionStatus.REJECTED,
    MissionEventType.ISOLATED_COMMIT_CREATED: MissionStatus.COMPLETED,
}
_FAILURE_EVENT_TYPES = frozenset(
    {MissionEventType.ASSEMBLY_FAILED, MissionEventType.VERIFICATION_FAILED}
)
_SETTLED_STATUSES = frozenset({MissionStatus.FAILED, MissionStatus.CANCELLED})


@dataclass(frozen=True, slots=True)
class _ExpectedAttempt:
    """What the public event log says about one attempt."""

    lease: dict[str, Any]
    states: frozenset[str]
    result_code: Any
    terminal: AttemptEvidenceEventType | None


def _attempts_in_log(
    events: tuple[MissionEvent, ...],
) -> dict[str, tuple[MissionEvent, ...]]:
    named: dict[str, list[MissionEvent]] = {}
    for event in events:
        if event.event_type not in _ATTEMPT_EVENT_TYPES:
            continue
        attempt_id = event.payload.get("attempt_id")
        if not isinstance(attempt_id, str):
            if event.event_type == MissionEventType.TASK_LEASED:
                raise _CheckFailed(f"task.leased seq {event.seq} names no attempt")
            continue
        named.setdefault(attempt_id, []).append(event)
    for attempt_id, items in named.items():
        leases = [
            item for item in items if item.event_type == MissionEventType.TASK_LEASED
        ]
        if len(leases) != 1 or items[0] is not leases[0]:
            raise _CheckFailed(
                f"attempt {attempt_id} is not leased exactly once before its task "
                "events"
            )
    return {attempt_id: tuple(items) for attempt_id, items in named.items()}


def _expected_attempt(
    items: tuple[MissionEvent, ...], events: tuple[MissionEvent, ...]
) -> _ExpectedAttempt:
    leased = items[0]
    lease = {key: leased.payload.get(key) for key in _ATTEMPT_LEASE_FIELDS}
    terminal_events = [
        item for item in items if item.event_type in _ATTEMPT_TERMINAL_EVENT_TYPES
    ]
    terminal: AttemptEvidenceEventType | None = None
    if terminal_events:
        last = terminal_events[-1]
        code = last.payload.get("result_code")
        if last.event_type == MissionEventType.TASK_COMPLETED:
            states = {"committed"}
            terminal = AttemptEvidenceEventType.ATTEMPT_COMPLETED
        elif last.event_type == MissionEventType.TASK_CANCELLED:
            states = {"cancelled"}
        elif code == "lease_expired":
            states = {"abandoned"}
        else:
            states = {"failed"}
            terminal = AttemptEvidenceEventType.ATTEMPT_FAILED
        return _ExpectedAttempt(lease, frozenset(states), code, terminal)
    sweep = next(
        (
            event
            for event in events[leased.seq :]
            if event.event_type in _ATTEMPT_SWEEP_EVENT_TYPES
        ),
        None,
    )
    if sweep is None:
        return _ExpectedAttempt(lease, frozenset({"leased", "running"}), None, None)
    if sweep.event_type == MissionEventType.OPERATOR_CANCELLED:
        return _ExpectedAttempt(
            lease, frozenset({"cancelled"}), "mission_cancelled", None
        )
    return _ExpectedAttempt(lease, frozenset({"abandoned"}), "plan_revised", None)


def _replay_mission_status(
    events: tuple[MissionEvent, ...], target_revision: int
) -> MissionStatus:
    created = [
        event
        for event in events
        if event.event_type == MissionEventType.MISSION_CREATED
    ]
    if len(created) != 1:
        raise _CheckFailed("event log does not record exactly one mission.created")
    try:
        status = MissionStatus(created[0].payload.get("status"))
    except ValueError as error:
        raise _CheckFailed("mission.created records an unknown status") from error
    active_revision = 1
    for event in events:
        kind = event.event_type
        try:
            if kind == MissionEventType.PLAN_REVISED:
                revision = event.payload.get("plan_revision")
                if type(revision) is not int:
                    raise _CheckFailed(f"plan.revised seq {event.seq} has no revision")
                active_revision = revision
            elif kind in _STATUS_TARGETS:
                status = transition_mission(status, _STATUS_TARGETS[kind])
            elif kind == MissionEventType.OPERATOR_REPLAN_REQUESTED:
                if status == MissionStatus.RUNNING:
                    status = transition_mission(status, MissionStatus.PAUSED)
            elif kind in _FAILURE_EVENT_TYPES and status not in _SETTLED_STATUSES:
                status = transition_mission(status, MissionStatus.FAILED)
            if (
                not isinstance(event.payload.get("task_id"), str)
                or active_revision != target_revision
            ):
                continue
            task_failed = kind == MissionEventType.TASK_FAILED or (
                kind == MissionEventType.GATE_DECIDED
                and event.payload.get("task_state") == TaskState.FAILED.value
            )
            if task_failed and status not in _SETTLED_STATUSES:
                status = transition_mission(status, MissionStatus.FAILED)
        except TransitionError as error:
            raise _CheckFailed(
                f"mission status replay is illegal at seq {event.seq}: {error}"
            ) from error
    return status


def _check_attempt_coverage(context: _Verification) -> str:
    context.attempt_log = _attempts_in_log(context.events)
    declared = context.manifest.get("attempts_without_evidence")
    if not isinstance(declared, list):
        raise _CheckFailed("manifest has no attempts_without_evidence table")
    without: dict[str, dict[str, Any]] = {}
    for entry in declared:
        attempt_id = entry.get("attempt_id") if isinstance(entry, dict) else None
        if not isinstance(attempt_id, str) or attempt_id in without:
            raise _CheckFailed(
                f"attempts_without_evidence entry {attempt_id!r} is malformed or "
                "repeated"
            )
        without[attempt_id] = entry
    chained = set(context.chains)
    for attempt_id in sorted(chained & set(without)):
        raise _CheckFailed(
            f"attempt {attempt_id} has an evidence chain but is also declared "
            "without evidence"
        )
    for attempt_id in sorted(set(context.attempt_log) - chained - set(without)):
        raise _CheckFailed(
            f"attempt {attempt_id} is leased in {EVENTS_FILE} but has neither an "
            "evidence chain nor an attempts_without_evidence entry"
        )
    for attempt_id in sorted((chained | set(without)) - set(context.attempt_log)):
        raise _CheckFailed(
            f"attempt {attempt_id} is in the manifest but {EVENTS_FILE} never leased it"
        )
    context.attempts_without_evidence = without
    return (
        f"{len(context.attempt_log)} leased attempts: {len(chained)} evidence "
        f"chains, {len(without)} declared without evidence"
    )


def _check_attempt_entry(
    context: _Verification, entry: dict[str, Any], fields: tuple[str, ...]
) -> None:
    attempt_id = entry["attempt_id"]
    expected = _expected_attempt(context.attempt_log[attempt_id], context.events)
    for key in fields:
        if entry.get(key) != expected.lease[key]:
            raise _CheckFailed(
                f"attempt {attempt_id} {key} {entry.get(key)!r} does not match its "
                "task.leased event"
            )
    if entry.get("state") not in expected.states:
        raise _CheckFailed(
            f"attempt {attempt_id} state {entry.get('state')!r} does not match its "
            f"task events (expected {' or '.join(sorted(expected.states))})"
        )
    if "result_code" in entry and entry.get("result_code") != expected.result_code:
        raise _CheckFailed(
            f"attempt {attempt_id} result_code {entry.get('result_code')!r} does "
            "not match its task events"
        )
    chain = context.chains.get(attempt_id)
    if expected.terminal is not None and chain is not None:
        last = chain[-1]
        if (
            last.event_type != expected.terminal
            or last.payload.get("result_code") != expected.result_code
        ):
            raise _CheckFailed(
                f"attempt {attempt_id} terminal evidence event does not match its "
                "task events"
            )


def _check_manifest_summary(context: _Verification) -> str:
    manifest = context.manifest
    events = context.events
    projects = [
        event
        for event in events
        if event.event_type == MissionEventType.PROJECT_CREATED
    ]
    created = [
        event
        for event in events
        if event.event_type == MissionEventType.MISSION_CREATED
    ]
    if len(projects) != 1 or len(created) != 1:
        raise _CheckFailed(
            "event log does not record exactly one project.created and mission.created"
        )
    policy = manifest.get("policy")
    expected_policy = {
        "base_sha": projects[0].payload.get("base_sha"),
        "policy_id": projects[0].payload.get("policy_id"),
        "policy_sha256": projects[0].payload.get("policy_sha256"),
        "repo_id": projects[0].payload.get("repo_id"),
        "revision": projects[0].payload.get("policy_revision"),
    }
    if policy != expected_policy:
        raise _CheckFailed("manifest policy does not match the project.created event")
    mission = manifest.get("mission")
    if not isinstance(mission, dict):
        raise _CheckFailed("manifest has no mission summary")
    if mission.get("creation_source") != created[0].payload.get("creation_source"):
        raise _CheckFailed(
            "manifest mission creation_source does not match the mission.created event"
        )
    try:
        policy_decision = plan_policy_decision(events, mission["plan_revision"])
    except (KeyError, TypeError, ValueError) as error:
        raise _CheckFailed("event log policy decision is invalid") from error
    if policy_decision is not None:
        recorded_plans = _recorded_plan_digests(events, failure=_CheckFailed)
        if (
            policy_decision.policy_id != expected_policy["policy_id"]
            or policy_decision.policy_revision != expected_policy["revision"]
            or policy_decision.policy_sha256 != expected_policy["policy_sha256"]
            or policy_decision.base_sha != expected_policy["base_sha"]
            or recorded_plans.get(policy_decision.plan_revision)
            != policy_decision.plan_sha256
        ):
            raise _CheckFailed("policy decision does not bind the manifest authority")
        approvals = tuple(
            event
            for event in events
            if event.event_type == MissionEventType.PLAN_APPROVED
            and event.payload.get("plan_revision") == policy_decision.plan_revision
        )
        if len(approvals) > 1 or (
            approvals
            and (
                approvals[0].payload.get("plan_sha256") != policy_decision.plan_sha256
                or approvals[0].payload.get("base_sha") != policy_decision.base_sha
                or approvals[0].payload.get("policy_decision_sha256")
                != policy_decision.decision_sha256
            )
        ):
            raise _CheckFailed("plan approval does not bind the policy decision")
        is_policy_grant = bool(approvals) and (
            approvals[0].truth_kind == TruthKind.POLICY_AUTHORITATIVE
            and approvals[0].authority == MissionAuthority.POLICY_ENGINE
        )
        if (
            policy_decision.effective_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
            and not is_policy_grant
        ) or (
            approvals
            and policy_decision.effective_mode == AuthorizationMode.REVIEW_REQUIRED
            and is_policy_grant
        ):
            raise _CheckFailed("plan approval authority disagrees with policy decision")
    status = _replay_mission_status(events, mission["plan_revision"])
    if (
        manifest.get("mission_status") != status.value
        or mission.get("status") != status.value
    ):
        raise _CheckFailed(
            f"manifest mission_status {manifest.get('mission_status')!r} does not "
            f"match the event log replay ({status.value})"
        )

    final_entry = manifest["final_bundle"]
    decision_text = "no final bundle"
    if context.bundle is not None:
        expected_decision = _bundle_decision(
            events, final_entry["event_seq"], context.bundle.bundle_id
        )
        if final_entry.get("decision") != expected_decision:
            raise _CheckFailed(
                f"manifest final_bundle.decision {final_entry.get('decision')!r} "
                f"does not match the final_candidate events ({expected_decision})"
            )
        decision_text = f"final decision {expected_decision['state']}"
        if expected_decision["state"] == "approved" and (
            policy_decision is not None
            and policy_decision.finalization_mode
            == FinalizationMode.AUTO_FINALIZE_ISOLATED
        ):
            final_event = events[expected_decision["event_seq"] - 1]
            if (
                expected_decision.get("mode") != FinalizationMode.AUTO_FINALIZE_ISOLATED
                or final_event.payload.get("policy_decision_sha256")
                != policy_decision.decision_sha256
                or final_event.truth_kind != TruthKind.POLICY_AUTHORITATIVE
                or final_event.authority != MissionAuthority.POLICY_ENGINE
            ):
                raise _CheckFailed("automatic final approval authority is invalid")

    for entry in manifest["attempts"]:
        _check_attempt_entry(context, entry, _ATTEMPT_LEASE_FIELDS)
    for entry in context.attempts_without_evidence.values():
        _check_attempt_entry(context, entry, ("task_id",))

    seen: dict[str, set[str]] = {}
    for chain in context.chains.values():
        for event in chain:
            for reference in event.references:
                if reference.kind not in RECEIPT_KINDS:
                    seen.setdefault(reference.kind, set()).add(reference.id)
    recomputed_excluded = {kind: len(ids) for kind, ids in sorted(seen.items())}
    excluded = manifest.get("excluded_artifact_kinds")
    if not isinstance(excluded, dict) or not all(
        isinstance(count, int) for count in excluded.values()
    ):
        raise _CheckFailed("manifest excluded_artifact_kinds is malformed")
    if not context.attempts_without_evidence:
        if excluded != recomputed_excluded:
            raise _CheckFailed(
                f"manifest excluded_artifact_kinds {excluded} does not match the "
                f"attempt evidence references ({recomputed_excluded})"
            )
    else:
        if any(
            excluded.get(kind, 0) < count for kind, count in recomputed_excluded.items()
        ):
            raise _CheckFailed(
                f"manifest excluded_artifact_kinds {excluded} counts fewer "
                f"artifacts than the attempt evidence references "
                f"({recomputed_excluded})"
            )
        context.not_checked.append(
            "excluded_artifact_kinds exact counts: "
            f"{len(context.attempts_without_evidence)} attempts without evidence "
            "chains may reference artifacts the capsule cannot see"
        )

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise _CheckFailed("manifest has no counts table")
    plan_files = [
        name for name in context.files if name.startswith(f"{PLAN_DIRECTORY}/")
    ]
    expected_counts = {
        "events": len(events),
        "plan_revisions": len(plan_files),
        "attempts": len(context.attempt_log),
        "attempt_evidence_chains": len(context.chains),
        "attempt_evidence_events": sum(len(chain) for chain in context.chains.values()),
        "receipts": len(context.receipts),
        "publications": len(context.envelopes),
        "leases": sum(
            1 for event in events if event.event_type == MissionEventType.TASK_LEASED
        ),
        "gates": len(
            {
                str(event.payload.get("gate_id"))
                for event in events
                if event.event_type == MissionEventType.GATE_REQUESTED
            }
        ),
        "excluded_artifacts": sum(excluded.values()),
    }
    if len(plan_files) != len(manifest["plan_revisions"]):
        raise _CheckFailed(
            "manifest plan_revisions table does not match the plan files"
        )
    for key, value in expected_counts.items():
        if counts.get(key) != value:
            raise _CheckFailed(
                f"manifest counts.{key} {counts.get(key)!r} does not match the "
                f"capsule contents ({value})"
            )
    unverifiable = sorted(set(counts) - set(expected_counts))
    if unverifiable:
        raise _CheckFailed(f"manifest counts has unverifiable entries {unverifiable}")
    return (
        f"manifest summary recomputed: policy and creation source from the first "
        f"events, mission_status {status.value} by status replay, {decision_text}, "
        f"{len(manifest['attempts'])} attempt rows and "
        f"{len(context.attempts_without_evidence)} attempts without evidence match "
        f"their task events, {len(expected_counts)} counts match"
    )


_CHECKS: tuple[tuple[str, Callable[[_Verification], str]], ...] = (
    ("manifest_file_digests", _check_manifest_files),
    ("mission_event_chain", _check_mission_events),
    ("attempt_evidence_chains", _check_attempt_chains),
    ("receipt_references", _check_receipt_references),
    ("receipt_contents", _check_receipt_contents),
    ("final_bundle", _check_final_bundle),
    ("tree_manifest", _check_tree_manifest),
    ("publication_envelopes", _check_envelopes),
    ("plan_revisions", _check_plan_revisions),
    ("attempt_coverage", _check_attempt_coverage),
    ("manifest_summary", _check_manifest_summary),
)


def _load_manifest(capsule_dir: Path) -> dict[str, Any]:
    path = capsule_dir / MANIFEST_FILE
    try:
        raw = _read_capsule_file(path)
    except (OSError, _CheckFailed) as error:
        raise CapsuleError("capsule manifest is unavailable") from error
    try:
        manifest = json.loads(raw)
    except ValueError as error:
        raise CapsuleError("capsule manifest is not JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != CAPSULE_SCHEMA:
        raise CapsuleError("capsule manifest schema is not supported")
    head = manifest.get("head")
    if (
        not isinstance(head, dict)
        or type(head.get("seq")) is not int
        or head.get("seq") != head.get("event_count")
        or not isinstance(head.get("event_sha256"), str)
    ):
        raise CapsuleError("capsule manifest head is malformed")
    return manifest


def verify_mission_capsule(capsule_dir: Path) -> dict[str, object]:
    """Recompute every digest and chain link from the capsule files alone."""

    capsule_dir = Path(capsule_dir)
    try:
        metadata = capsule_dir.lstat()
    except OSError as error:
        raise CapsuleError("capsule directory is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise CapsuleError("capsule path is not a directory")
    manifest = _load_manifest(capsule_dir)
    try:
        mission_id = _validated_mission_id(manifest.get("mission_id"))
    except CapsuleError as error:
        raise CapsuleError("capsule manifest mission ID is invalid") from error
    context = _Verification(capsule_dir, manifest, mission_id)
    checks: list[dict[str, object]] = []
    verified = True
    for name, check in _CHECKS:
        try:
            detail = check(context)
        except _CheckFailed as failure:
            checks.append({"name": name, "ok": False, "detail": str(failure)})
            verified = False
            break
        except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
            checks.append(
                {
                    "name": name,
                    "ok": False,
                    "detail": (
                        f"capsule data for this check is malformed "
                        f"({type(error).__name__})"
                    ),
                }
            )
            verified = False
            break
        checks.append({"name": name, "ok": True, "detail": detail})
    excluded = manifest.get("excluded_artifact_kinds")
    excluded_text = (
        ", ".join(f"{kind}={count}" for kind, count in sorted(excluded.items()))
        if isinstance(excluded, dict) and excluded
        else "none"
    )
    not_checked = [
        f"{NOT_VERIFIABLE_OFFLINE[3]}: {PRODUCER_NOTE}",
        f"{NOT_VERIFIABLE_OFFLINE[0]} (patch and source bytes are not in the capsule)",
        f"{NOT_VERIFIABLE_OFFLINE[1]} (provider receipts are sanitized, "
        "worker-reported records)",
        f"{NOT_VERIFIABLE_OFFLINE[2]} (timestamps are the mission store clock)",
        "manifest snapshot_sha256 (the store's materialized snapshot digest cannot "
        "be recomputed from the capsule)",
        "manifest exported_at (the export clock) and mission.created_at (the "
        "mission contract is carried only as its digest)",
        "manifest mission.final_outcome (the store's outcome label; the final "
        "decision is verified through final_bundle.decision instead)",
        f"artifact bytes of excluded kinds: {excluded_text} (digests only)",
        f"{OVERLAP_FILE} and {UNKNOWNS_FILE} are derived views; only their file "
        "digests are checked",
        "mission materialized task-state replay (requires the SQLite mission "
        "store; only the mission status dimension is replayed offline)",
        *context.not_checked,
    ]
    return {
        "schema": CAPSULE_SCHEMA,
        "mission_id": mission_id,
        "capsule_dir": str(capsule_dir),
        "verified": verified,
        "checks": checks,
        "not_checked": not_checked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m graphene.orchestration.capsule",
        description="Cold-verify an exported Graphene mission capsule.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser(
        "verify", help="recompute every digest and chain link in a capsule"
    )
    verify.add_argument("capsule_dir", help="path of a *.graphene-capsule directory")
    args = parser.parse_args(argv)
    try:
        value = verify_mission_capsule(Path(args.capsule_dir))
    except CapsuleError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0 if value["verified"] else 1


__all__ = [
    "AUTHORITY_NOTE",
    "CAPSULE_SCHEMA",
    "CAPSULE_SUFFIX",
    "CapsuleError",
    "NOT_VERIFIABLE_OFFLINE",
    "PRODUCER_NOTE",
    "RECEIPT_KINDS",
    "REDACTION_NOTE",
    "export_mission_capsule",
    "main",
    "rewind_plan",
    "verify_mission_capsule",
]


if __name__ == "__main__":
    raise SystemExit(main())
