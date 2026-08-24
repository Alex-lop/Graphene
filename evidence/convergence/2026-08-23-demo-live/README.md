# `graphene demo --live` — the one-take sequence

`run-1.txt` is the first complete end-to-end run. `rehearsal-1..3.txt` are three
**consecutive** rehearsals of the exact same sequence, run back to back with no
edits between them; `rehearsals.ndjson` counts the beats mechanically.

| | 1 | 2 | 3 |
|---|---|---|---|
| Exit code | 0 | 0 | 0 |
| Wall clock | 84 s | 93 s | 85 s |
| Trigger arrived from the inbox | ✓ | ✓ | ✓ |
| Bounded plan shown | ✓ | ✓ | ✓ |
| Retries authorized with a diagnostic | 1 | 2 | 1 |
| Injected check fault fired | ✓ | ✓ | ✓ |
| Result isolated, nothing pushed | ✓ | ✓ | ✓ |
| Generated feature ran, note redacted | ✓ | ✓ | ✓ |
| `why` reached the approval stage | ✓ | ✓ | ✓ |
| Tracebacks | 0 | 0 | 0 |
| Raw JSON lines | 0 | 0 | 0 |

## The two failures that got here

The first attempt at three rehearsals was 1/3, and both failures were worth
keeping.

**Rehearsal 1 died with `MissionProjectionError: mission materialized state
changed during validation`.** A live mission writes two SQLite files, and a
dashboard poll can land between them; the projection is right to refuse a
half-state, and the projection's own two internal retries are not enough at
machine speed against a mission that is actively writing. The dashboard now
keeps the last good frame and polls again, up to 40 consecutive transient
failures — and still raises when a failure never clears, so a genuinely
corrupted store is never hidden. Regressions:
`test_follow_rides_out_a_projection_caught_mid_write` and
`test_follow_surfaces_a_projection_error_that_never_clears`.

**Rehearsal 2 ended `failed`, honestly.** `--inject-check-fault` burns a task's
first attempt on purpose, so at `retry_limit: 1` the model was left with exactly
one real attempt and no recovery — the demo was measuring the injected fault
rather than the product. The North Star policy now ships `retry_limit: 2`:
injected fault, one real attempt, one diagnostic-aware repair. It is never a
blind extra draw, because a repeat of the same failure signature terminalizes
the task immediately. Rehearsal 2 above used both retries and completed.

Note that the demo said so rather than faking it: "The mission ended failed
(subprocess exit 1); skipping the result and feature beats rather than faking
them."

## What these runs do not claim

- The check failure is injected by Graphene and stamped `simulated_fixture` in
  evidence. It is not a Gemini worker dying and must not be narrated as one.
- The 2026-08-23 completion gate (9/10 ordinary, 3/3 controlled-failure) was
  measured at the stricter `retry_limit: 1`; raising it for the demo does not
  retroactively loosen that number.
- Approval is operator-delegated (`server_derived`), not human-attested.
- No cloud service is involved in any of these runs.
