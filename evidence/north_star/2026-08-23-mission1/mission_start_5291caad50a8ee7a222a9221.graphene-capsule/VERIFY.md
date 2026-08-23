# Verifying this Graphene mission capsule

Schema: `graphene.mission-capsule.v1`
Mission: `mission_start_5291caad50a8ee7a222a9221`

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
4. `receipt_references` - every `test-receipt` / `worker-provider-receipt`
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

- producer authenticity: the capsule carries no signature or external anchor, so verification proves internal consistency with the hash chains and digests, not who produced them; producer authenticity comes from the mission store that exported it (`graphene mission db verify`) or from comparing the manifest head digest against the operator's recorded mission head.
- candidate tree identity against artifact bytes: patch and source bytes are not in the capsule,
  so the candidate tree digest is checked against the receipt, not recomputed
  from bytes.
- Gemini provider-side identity: worker-provider receipts are sanitized,
  worker-reported records, not a provider-side attestation.
- host clock accuracy: timestamps come from the mission store clock.
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

Contains no prompts, source bytes, diffs, command output, environment values, or credentials. Artifact bytes stay in the executor's private spool; only their digests are included.

SQLite mission store was the execution authority for this mission.
