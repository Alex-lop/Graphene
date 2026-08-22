# Shadow ndjson fixture

`session_v1.ndjson` is **synthetic**. No agent produced it and no repository
named in it exists; it was written by hand, in the shape of a Claude Code
session, so the Shadow Agent test suite has a deterministic `shadow.event.v1`
stream whose digests are real. It is the only fixture behind the
"credential-free tests pass on the synthetic ndjson fixture" status line, and
it proves nothing about any real transcript.

## Regenerating

```bash
uv run --frozen python tests/fixtures/shadow/ndjson/generate_session_v1.py
```

The generator builds every record with `ShadowEvent.create`, so each
committed `event_id` is the canonical digest of its record, and it renders
each record as canonical JSON (sorted keys, no whitespace) followed by LF.
`tests/unit/shadow/test_ingest.py` regenerates the stream in-process and
asserts the committed bytes are identical; edit the generator, rerun it, and
commit both files together.

## What the session contains

Thirty observed-or-inferred records for `session_id` `fixture-session-v1`,
emitted by the fictional `fixture-emitter 0.1.0` (so the stored
`source_adapter` differs from the ingesting `ndjson 1.0.0` adapter):

| seq | what | why it is there |
|---|---|---|
| 1 | user prompt | opens segment 1 |
| 6, 7, 8 | edits to `app/greet.py`, `app/config.py`, `tests/test_greet.py` | the three written paths |
| 9, 10 | `pytest` check run and passing result | covers the first two edits |
| 11 | agent message "Tests pass for ..." | a claim ingest can back with seq 10 |
| 12, 13 | second user prompt, `TodoWrite` | a `user_message` and a `plan_marker` boundary |
| 16 | `uv sync` | an `install_op` for `network-or-install` |
| 18, 19 | `rm app/legacy.py` and the inferred `file_delete` derived from it | `destructive-unverified`; an inferred record citing its observed source |
| 22 | later edit to `tests/test_greet.py` | the third path, never checked afterwards |
| 23 | second edit to `app/greet.py` | `write-overlap` across segments and a read-after-write edge |
| 24 | `curl` | a `network_op` |
| 26 | write to `.env` | `scope-drift` |
| 27 | `unknown` record | surfaced, never dropped |
| 28 | `git commit` | a `vcs_op` |
| 30 | agent message "All tests pass." | a claim with no check after the last edit: `claimed-without-evidence` |

The file carries **no** `claim` records. Ingest therefore runs the
`claims.v1` matcher and inserts two inferred claims (after seq 11 and seq 30),
so the stored session has 32 events. Re-ingesting the exported
`events.ndjson` of that session, which already contains the claims, yields the
same shadow id.
