# Shadow adapter specification: `shadow.event.v1`

Status: v0 specification, 2026-08-22. This is the open integration surface for the [Shadow Agent](SHADOW.md). Any agent, wrapper, or CI harness that can write newline-delimited JSON can emit a session that `graphene shadow ingest --format ndjson` accepts.

## Transport

- UTF-8 text, one JSON object per line, LF line endings, no BOM.
- Every object is one `shadow.event.v1` record. Blank lines are rejected.
- Records for one session must be contiguous, in `seq` order, starting at 1 with no gaps.
- A file may contain exactly one session.
- Unknown top-level fields are rejected. Unknown `kind` values are rejected; emitters that cannot classify an event must use `kind: "unknown"` so the record is surfaced rather than dropped.

## Record fields

| Field | Type | Rule |
|---|---|---|
| `schema` | string | Exactly `"shadow.event.v1"` |
| `session_id` | string | 1–128 characters from `[A-Za-z0-9._-]` |
| `seq` | integer | ≥ 1; contiguous from 1 within the file |
| `ts` | string or null | RFC 3339 UTC timestamp (`YYYY-MM-DDTHH:MM:SS[.fff]Z`) when the source provides one |
| `actor` | string | One of `agent`, `user`, `tool`, `system` |
| `kind` | string | One of the kinds below |
| `paths` | array of string | Repository-relative canonical POSIX paths; no leading `/`, no `..`, no backslash, no NUL; may be empty; sorted and unique |
| `outside_paths` | array of string | Paths outside the repository that the event touched, with the home directory collapsed to `~`; sorted and unique; may be empty |
| `tool` | string or null | Source tool name, ≤ 64 characters |
| `call_id` | string or null | Correlates a `tool_call` with its `tool_result` and with events derived from either; ≤ 128 characters |
| `argv_digest` | string or null | Lowercase hex SHA-256 of the full command text encoded as UTF-8 |
| `argv_excerpt` | string or null | ≤ 200 characters of the command after redaction; never the full environment and never secrets |
| `exit_code` | integer or null | Process exit status when the source provides it |
| `check_family` | string or null | For `check_run`/`check_result` only: the runner family that was recognized (for example `pytest`, `node-test`, `npm-test`, `go-test`, `cargo-test`, `make-test`, `ruff`, `mypy`, `eslint`, `tsc`) |
| `excerpt` | string or null | ≤ 280 characters of redacted message text; used for `message` and `claim` |
| `content_digest` | string or null | Lowercase hex SHA-256 of the full original text an excerpt was taken from |
| `claim` | object or null | For `claim` only: `{"matcher": "claims.v1", "category": "<checks_pass|build_ok|verified|fixed>", "pattern_id": "<id>"}` |
| `provenance` | string | `observed` or `inferred` |
| `derived_from` | array of string | `event_id` values of the events this record was derived from; required non-empty when `provenance` is `inferred`, must be empty when `observed` |
| `source` | object | `{"adapter": "<id>", "adapter_version": "<semver>", "record_ref": "<bounded locator>", "raw_type": "<source record type>"}`; each string ≤ 128 characters |
| `event_id` | string (optional on input) | Lowercase hex SHA-256 computed as below. If present it must match the recomputed value or ingest fails closed. |

## Kinds

| Kind | Meaning |
|---|---|
| `message` | A human or agent message. Only a digest and a bounded excerpt are kept. |
| `claim` | A success assertion extracted from an agent message. Always `inferred`. |
| `tool_call` | A tool invocation that no more specific kind describes. |
| `tool_result` | The result of a tool invocation that no more specific kind describes. |
| `file_read` | A read of one or more paths. |
| `file_edit` | A modification of an existing path. |
| `file_create` | Creation of a path. |
| `file_delete` | Deletion or rename of a path; renames list both the old and the new path. |
| `command_exec` | A shell command was issued. |
| `command_result` | A shell command returned; `exit_code` when known. |
| `check_run` | A recognized test, lint, or type-check runner was issued. |
| `check_result` | A recognized runner returned; `exit_code` when known. |
| `vcs_op` | A version-control operation (commit, push, checkout, reset, rebase, stash, merge). |
| `network_op` | A command that reaches the network (curl, wget, HTTP clients, package registries). |
| `install_op` | A package installation or global tool installation. |
| `unknown` | A source record the adapter could not classify. It is surfaced, never dropped. |

## Provenance rules

- `observed` means the event is literally present in the source. A `command_exec` for a shell call, a `file_edit` for an editor tool call, and a `check_run` for a shell call whose command matched a runner family are all observed: the call is in the transcript, and the classification is a deterministic function of the observed text.
- `inferred` means a heuristic produced the record. Claims, file operations parsed out of shell commands (`sed -i`, redirections, `rm`, `mv`), segment boundaries, and dependency edges are inferred. Inferred records must cite the observed records they came from in `derived_from`.
- A report never presents an inferred record as evidence.

## Canonical encoding and `event_id`

`event_id` is the SHA-256 of a length-prefixed, domain-separated encoding of every field except `event_id`:

```text
digest = SHA-256(
    "shadow.event.v1" || 0x00
    || be64(N)
    || for each field name in ascending byte order (N fields):
         be64(len(name)) || name
         || be64(len(value)) || value
)
```

where `value` is the canonical JSON encoding of the field's value: keys sorted, separators `,` and `:` with no whitespace, non-ASCII preserved (no `\u` escaping), NaN and infinity rejected, encoded as UTF-8. `null` values are encoded as the four bytes `null`. `be64` is an unsigned 64-bit big-endian integer. Every field in the record table except `event_id` participates, including fields whose value is `null` or an empty array.

A session digest is `SHA-256("shadow.session.v1" || 0x00 || be64(count) || for each event in seq order: be64(32) || raw event_id bytes)`. The export capsule records it.

## Redaction requirements

Emitters must never include: prompts or system instructions, hidden reasoning, file contents, full command output, environment variables, credentials, tokens, or private keys. Graphene additionally scrubs, at ingest, any excerpt that matches its secret patterns (bearer tokens, `KEY=`/`TOKEN=`/`SECRET=`/`PASSWORD=` assignments, AWS/Google/GitHub/Slack/OpenAI/Anthropic-style key prefixes, PEM blocks) and replaces the match with `<redacted>`. Redaction is applied before persistence; nothing unredacted is ever written to the shadow store.

## Worked example

A minimal session: the agent edits a file, runs the tests, and says they passed.

```json
{"schema":"shadow.event.v1","session_id":"example-session-1","seq":1,"ts":"2026-08-22T10:00:00Z","actor":"user","kind":"message","paths":[],"outside_paths":[],"tool":null,"call_id":null,"argv_digest":null,"argv_excerpt":null,"exit_code":null,"check_family":null,"excerpt":"Make the greeting configurable.","content_digest":"d8a2fcfb4f4f0d5f3c2c0a0b3ab0e0fd6f4b0a6b3f3e5a2b1f9a5d2c4e8b7a6c","claim":null,"provenance":"observed","derived_from":[],"source":{"adapter":"ndjson","adapter_version":"1.0.0","record_ref":"line:1","raw_type":"user_message"}}
{"schema":"shadow.event.v1","session_id":"example-session-1","seq":2,"ts":"2026-08-22T10:00:05Z","actor":"agent","kind":"file_edit","paths":["app/greet.py"],"outside_paths":[],"tool":"Edit","call_id":"call-1","argv_digest":null,"argv_excerpt":null,"exit_code":null,"check_family":null,"excerpt":null,"content_digest":null,"claim":null,"provenance":"observed","derived_from":[],"source":{"adapter":"ndjson","adapter_version":"1.0.0","record_ref":"line:2","raw_type":"tool_use"}}
{"schema":"shadow.event.v1","session_id":"example-session-1","seq":3,"ts":"2026-08-22T10:00:09Z","actor":"agent","kind":"check_run","paths":[],"outside_paths":[],"tool":"Bash","call_id":"call-2","argv_digest":"0f4a1c0d1c2c8f4b0b2a0a6bd0b4a2b0d4e8f0a1b2c3d4e5f60718293a4b5c6d","argv_excerpt":"pytest -q","exit_code":null,"check_family":"pytest","excerpt":null,"content_digest":null,"claim":null,"provenance":"observed","derived_from":[],"source":{"adapter":"ndjson","adapter_version":"1.0.0","record_ref":"line:3","raw_type":"tool_use"}}
{"schema":"shadow.event.v1","session_id":"example-session-1","seq":4,"ts":"2026-08-22T10:00:14Z","actor":"tool","kind":"check_result","paths":[],"outside_paths":[],"tool":"Bash","call_id":"call-2","argv_digest":"0f4a1c0d1c2c8f4b0b2a0a6bd0b4a2b0d4e8f0a1b2c3d4e5f60718293a4b5c6d","argv_excerpt":null,"exit_code":0,"check_family":"pytest","excerpt":null,"content_digest":null,"claim":null,"provenance":"observed","derived_from":[],"source":{"adapter":"ndjson","adapter_version":"1.0.0","record_ref":"line:4","raw_type":"tool_result"}}
{"schema":"shadow.event.v1","session_id":"example-session-1","seq":5,"ts":"2026-08-22T10:00:20Z","actor":"agent","kind":"message","paths":[],"outside_paths":[],"tool":null,"call_id":null,"argv_digest":null,"argv_excerpt":null,"exit_code":null,"check_family":null,"excerpt":"Done. All tests pass.","content_digest":"7c3b0e1b5d2f6a9c8e7d6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c","claim":null,"provenance":"observed","derived_from":[],"source":{"adapter":"ndjson","adapter_version":"1.0.0","record_ref":"line:5","raw_type":"assistant_message"}}
```

Ingest computes each `event_id`, extracts a `claim` event (`provenance: inferred`, `derived_from` the `seq: 5` message) and, because an observed `check_result` with `exit_code: 0` follows the last `file_edit`, `claimed-without-evidence` does not fire. Remove lines 3 and 4 and it does. Digests in this example are illustrative placeholders; the checked-in fixture under `tests/fixtures/shadow/` carries real values.

## Fail-closed behavior

Ingest stops with a precise error, and persists nothing, when:

- a line is not a JSON object, or `schema` is not exactly `shadow.event.v1`;
- a required field is missing, a field has the wrong type, or an unknown field is present;
- `seq` is not contiguous from 1, or `session_id` changes mid-file;
- a path is absolute, contains `..`, a backslash, or NUL, or the `paths` array is unsorted or has duplicates;
- `provenance` is `inferred` with an empty `derived_from`, or `observed` with a non-empty one;
- a supplied `event_id` does not match the recomputed digest;
- `claim` is present on a non-claim kind, or absent on a `claim`.

## Versioning

The schema name carries the version. A future `shadow.event.v2` is a new schema; `v1` records are never silently reinterpreted. Adapters carry their own `adapter_version`, recorded in every event's `source`, so a report always says which parser produced it.
