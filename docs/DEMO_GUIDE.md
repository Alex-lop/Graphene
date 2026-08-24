# Demo guide

## Verified replay

```bash
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

Permanent truth label:

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The replay is portable and read-only. It illustrates scheduler state, two overlapping fixture workers, a denied unsafe command, bounded retry, accepted-only fan-in, assembly, verification, a pending final-candidate checkpoint, and a simulated result. It is not captured execution or V2 bundle proof.

The viewer opens at checkpoint zero. Playback pauses at the exact verified candidate; **Continue with recorded simulated approval** advances only to the fixture's recorded branch and never attests a human action.

## Scripted local fixture

On macOS with executable `/usr/bin/sandbox-exec`:

```bash
uv run --frozen graphene init --repo /path/to/disposable-repo
uv run --frozen graphene mission start \
  --repo /path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports to the fixture CLI." \
  --driver scripted-local
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1
```

The first command persists a proposal. An interactive TTY can attest approval; automation is `server_derived`, and `--auto-approve` is `simulated_fixture`. The fixture does not edit the supplied repository and proves no Gemini/cloud behavior.

## Conditional live paths

Live proof is opt-in and never substituted with replay/fakes:

```bash
uv run --frozen graphene mission demo
GRAPHENE_RUN_LIVE_GEMINI=1 uv run --frozen pytest -q tests/process/test_gemini_live.py
GRAPHENE_RUN_DOCKER_SMOKE=1 uv run --frozen pytest -q tests/unit/orchestration/test_sandbox.py
```

`graphene mission demo` selects the live `gemini-adk` Taskmaster path, defaults to two workers, and persists a model-proposed plan for explicit approval. The gated process smoke now covers the full two-worker mission, distinct provider/session/invocation/workspace/lease identities, measured overlap, accepted-only assembly, verification, and source-checkout sovereignty. It has been **RUN LIVE** (2026-08-23, and rehearsed 3/3 on 2026-08-24); even so, do not present the implementation or fake-model tests as live Gemini proof — the live claim rests on the receipts in `evidence/`, not on them. Docker was not run on a responsive daemon. The official Firestore emulator production path is separately **VERIFIED_LOCAL (3 passed)**. Real cloud proof requires the [owner checklist](ALEX_CLOUD_SETUP.md).

## Four-minute story

1. State the scheduling problem and show the goal/policy.
2. Show a validated DAG and explain that the model proposes while Graphene validates.
3. Show distinct worker/workspace/lease ownership and measured overlap only from a proof mode that actually produced it.
4. Show one policy denial and one explicitly labeled deterministic fault/repair.
5. Show accepted-only fan-in, exact assembly, and verification.
6. Stop at the final decision; explain reject, then approve the exact displayed bundle ID only in a separate valid branch.
7. Show that the user checkout and remote remain untouched.
8. Show cloud/Gemini proof only if authenticated receipts were captured.

The graph-economics harness has no measured result, and the four-minute submission video has not been recorded. Both remain **NOT PROVEN**.

## Product media

Required paths are `docs/assets/mission-control-hero.png`, `docs/assets/mission-control-replay.gif`, and [`docs/assets/demo-capture.json`](assets/demo-capture.json). The replay now has the required pending final decision, but the image/GIF remain intentionally absent until a reproducible capture is completed.

Capture at a stable viewport with the truth banner visible, secrets/usernames/absolute paths excluded, and checkpoint zero as the GIF start. `demo-capture.json` records the verified source replay SHA-256, viewport, pending-candidate checkpoint, and the in-app Browser blocker; add the capture command and output digests only after capture succeeds.

If a reproducible GIF remains unavailable, ship only the verified PNG and record the blocker. Never substitute a mockup.

Representative redacted output shapes—not logs—remain in the superseded [demo transcript](demo_transcript.md).
