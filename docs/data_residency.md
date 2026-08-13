# Data residency and privacy boundary

Status: implemented v2 local boundary and metadata-only Firestore adapter, 2026-08-13.

“Public event” means evidence that Graphene may print through `watch`, `replay`, or
`inspect`, and may copy into Firestore. It does not mean anonymously available on
the Internet. Event paths, identifiers, hashes, timestamps, status values, and
reason codes are still data and must come only from the frozen sanitized fixture
or a server-owned identifier source.

The supported trust boundary is an honest host account processing the repository's
frozen sanitized fixture. Arbitrary confidential repositories, secrets embedded in
fixture paths or identifiers, hostile host administrators, and a cloud deployment
without separately reviewed IAM and residency controls are not supported.

## Residency matrix

| Data class | Transient process | Local private artifact | Public event / CLI | Firestore | Logs and errors | Model request or tool result | Retention / deletion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Repository and candidate file contents | Read and edited by scoped tools; candidate bytes also enter the temporary fixed-test view | `file_version`; changed content also contributes to `changeset` and `hunk` | Path, version IDs, byte/line counts, change counts, and hashes only | Full canonical public Event bytes contain the same metadata; no file artifact bytes | Fixed generic failures; content is not included | Exact content is returned only by an authorized `read_file`; authorized hunk content may be returned by `open_evidence` | SQLite and checkout persist until operator removal; no TTL |
| Search query and matches | Query and bounded matched lines exist while the tool runs | `evidence_blob` stores query hash and matched paths/lines; the raw query is not stored | Matching paths, match count, and truncation flag only | Same public Event metadata | Errors use fixed codes | Bounded matched lines are returned to the authorized caller/model | Same as SQLite artifacts; no orphan GC |
| Fixed-test command and output | Frozen command runs in a temporary minimal view; bounded output is returned | `test_receipt` stores command and result metadata; `evidence_blob` stores bounded stdout/stderr | Bound paths, exit/timing/truncation metadata, byte count, and output/receipt hashes only | Same public Event metadata | No raw test output in Graphene diagnostics | Bounded output is intentionally returned by `run_fixed_test` | Temporary view is removed on normal exit; a crash may rely on OS temporary cleanup. Receipts/output persist in SQLite |
| Human feedback and clarification | Exact correction and selected answer exist while the workflow runs | `operator_request`, `feedback`, and `policy_receipt` may contain exact correction, question, and answer | IDs, hunk/scope selection, status, safe counts/reasons, and digests only | Same public Event metadata | Workflow errors are generic | Not automatically sent; approved memory derived from feedback may later enter a brief | Indefinite local retention; no delete API or TTL |
| Memory | Proposed/decided revision is validated in process | `memory_revision` stores exact text, scope, revision, and decision state | Memory ID/revision/status and artifact digest only | Same public Event metadata | Fixed workflow failures | Exact text enters a fresh prompt only when the applicable revision is approved and selected | Indefinite local retention; rejected and superseded revisions are not garbage-collected |
| Handoff decision and context | Compiler handles the complete candidate set; runtime renders the canonical prompt | `handoff_decision`, `context_brief`, and `injection_receipt`. The brief contains task text, approved memory text, evidence summaries, paths, capabilities, and limits; the receipt contains only the prompt hash | Decision/brief/receipt IDs and digests, safe counts/reasons, target identity, and status | Same public Event metadata | Compiler/runtime errors are generic | The initial fresh-agent request contains the complete canonical included-only brief; excluded candidate content is not rendered | Indefinite local retention; failed consumer checkouts are quarantined rather than deleted |
| Evidence and patches | Authorized evidence may be reconstructed or opened | `hunk`, `changeset`, `evidence_blob`, and `promotion_receipt` may contain unified diffs, canonical patch bytes, evidence text, paths, and bound digests | Reference kinds/IDs/digests plus allowlisted paths, counts, status, and candidate/test/promotion hashes | Same public Event metadata | No artifact bytes in normal diagnostics | Only selected evidence on the runtime allowlist is returned by `open_evidence`; evidence summaries may be in the brief | Indefinite local retention; no artifact compaction or orphan collection |
| Runtime/provider model data | Model responses and ADK events exist in memory | `adk_event_receipt`, `mcp_request_receipt`, `local_adapter_receipt`, and `tool_receipt` store server-owned runtime identities and allowlisted metadata | Configured model ID, session/invocation/tool IDs, adapter kind, status, and fixed error code | Same public Event metadata | Durable failures use fixed codes. The ADK adapter re-raises provider exceptions to its trusted host caller, whose logging is external | Provider responses are naturally part of the active model/runtime exchange | Provider-reported model metadata is accepted only when exactly equal to the configured server-owned model ID; mismatch fails without persisting or displaying the raw value. Third-party provider retention is outside this repository |
| Event envelope | Canonical event and CAS request exist while appending/verifying | SQLite `events`, `run_heads`, and idempotency indexes store the full canonical envelope | All fields are public: schema/event/run/sequence/time/idempotency and digest chain; session/invocation/model/tool IDs; repo/base/profile/policy identity; event/truth/authority; reference kinds/IDs/digests; allowlisted payload | Full canonical event bytes plus run head, per-run idempotency index, and global event-ID index | CLI evidence-invalid output includes the run ID, sequence, and a verifier-generated reason | Not automatically included in a model request | Append-only; no event deletion, redaction, or TTL |
| Credentials and environment | Needed only by the external SDK or process configuration | Must not be recorded | Must not appear. CLI configuration/startup failures are fixed messages; successful `graphene run --json` intentionally prints the selected local database path | Not written by the lineage adapter | STDIO diagnostics are fixed tokens. Dependency/provider logging is outside Graphene's guarantee | Provider credentials are transport configuration, not prompt content | Governed by the caller's secret manager and provider, not Graphene |
| Local checkout and coordination state | Checkout is the mutable runtime view; watch cursors coordinate commit-before-display | Checkout lives below the private runtime directory; watch cursors contain sequence numbers only | Not an event payload; the successful JSON run response includes the database path | Not uploaded by the lineage adapter | Paths are suppressed on handled failures | Only scoped file/evidence results cross into model interaction | Active checkout persists. Failed/uncertain checkouts are atomically renamed to quarantine and require operator cleanup. Watch cursor files are removed on normal close |

## Artifact inventory

All non-`event` evidence kinds are stored as canonical JSON in the
`lineage_artifacts` table of the same local SQLite database. Their bytes are
private even though each referencing Event exposes the kind, content-addressed ID,
and SHA-256 digest.

| Evidence kind | Private contents |
| --- | --- |
| `file_version` | Repository path, file metadata, and exact file content or an absence record |
| `changeset` | Canonical patch bytes, changed paths, file-version bindings, hunk references, and test binding |
| `hunk` | Exact unified-diff evidence and source ranges |
| `tool_receipt` | Server-owned invocation/tool identity, phase, safe payload, and evidence references |
| `test_receipt` | Frozen command, exit/timing/output metadata, changed-path binding, and output reference |
| `feedback` | Exact human correction and selected evidence/hunk/scope |
| `memory_revision` | Exact memory text, scope, revision, state, and decision binding |
| `checkpoint` | Verified prefix and bound promotion-artifact identity/digests |
| `handoff_decision` | Complete candidate IDs/digests, include/exclude decisions, and safe reasons/counts |
| `context_brief` | Included task, memory text, evidence summaries, paths, capabilities, limits, and source identity |
| `injection_receipt` | Consumer identities, decision/brief/prompt digests, model/profile/policy binding, and zero-prior-message assertion |
| `promotion_receipt` | Candidate patch/tree/commit and authoritative fixed-test bindings |
| `evidence_blob` | Bounded search matches, fixed-test output, or other explicitly recorded evidence content |
| `policy_receipt` | Policy inputs/decision metadata and clarification records |
| `operator_request` | Human/lifecycle requests, including exact submitted feedback where applicable |
| `adk_event_receipt` | Server-approved ADK identity and allowlisted lifecycle metadata; never raw mismatching provider model metadata |
| `mcp_request_receipt` | Server-approved MCP identity and allowlisted lifecycle metadata |
| `local_adapter_receipt` | Server-approved local-adapter identity and allowlisted lifecycle metadata |

`event` references point to an earlier committed Event and do not create an
artifact row.

## Storage controls and unresolved deployment work

- Bootstrap requires an absolute, non-symlinked runtime path. The runtime and
  checkout parent are owned mode-`0700`; the SQLite database is a single-link,
  owned regular file created and revalidated as mode-`0600`. SQLite sidecars and
  checkout files rely on the enclosing `0700` directory as their privacy boundary.
- The local artifact store uses WAL and `synchronous=FULL`. Artifact recording may
  precede Event append, so a crash or rejected append can leave an unreferenced
  artifact. No reachability collector, TTL, secure erase, or data-subject deletion
  workflow is implemented.
- Firestore stores full canonical Event envelopes and reciprocal metadata indexes.
  It does not store private artifact bytes; verification depends on an injected
  artifact resolver and optional checkpoint reader. Consequently this repository
  does not yet provide a cold-restart-capable cloud artifact ledger.
- Firestore region, replication, backup, IAM, encryption-key choice, TTL, and
  deletion are deployment configuration and are not set by this adapter. No real
  cloud residency or retention claim is valid until those controls and a durable
  artifact strategy are explicitly approved and tested.
- Graphene emits no application log containing private artifacts. CLI/STDIO handled
  errors are bounded diagnostics, while successful MCP/ADK tool results intentionally
  carry authorized content to the caller/model. SDK, platform, shell redirection,
  and provider logging remain external trust boundaries.
