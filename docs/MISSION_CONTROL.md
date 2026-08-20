# Mission Control

## Purpose

Mission Control answers five questions from committed state: what is the goal, what is running or blocked, who owns it, what evidence supports the candidate, and what decision is required.

The accessible task table is primary. The DAG is a secondary projection of explicit committed relationships. Layout, timing, proximity, size, and animation do not establish causality, importance, quality, or correctness.

## Read model

The view exposes bounded task contracts, dependencies, scopes, command-template IDs, attempts, leases/fences, accepted publications, integration, verification, result, resource semantics, and unknowns. Raw prompts, secrets, environment variables, command arguments, source/diffs, stdout/stderr, and chain-of-thought are excluded.

Snapshots and deltas are digest-verified. Cursor expiry or stale transport triggers a fresh committed snapshot. Invalid evidence must quarantine the read side rather than displaying partial success.

## Decisions

The graph and tables are an authenticated read-only projection. Without a separately configured command credential, the UI renders the exact CLI command for a pending gate and remains read-only.

The live browser controls cover plan approval/rejection, pause/resume/cancel, replanning requests, failed-task retry, gate decisions, and final approval/rejection. The server requires a command token distinct from the read token, exact Origin, short-lived same-site CSRF session, typed confirmation, unique command ID, current head, and operator attribution. Final actions also require the displayed immutable bundle ID and route through the same restart-safe finalizer as the CLI. Cancellation is exposed only with the exact-owned cleanup coordinator. A private-input coordinator seam is contract-tested, but one-command live mode does not inject or display it because safe staged-input cleanup is incomplete; use `graphene task input`. Replay and the Cloud Run viewer disable commands. Live operator capture remains pending.

Plan approval, gate decisions, pause/resume, retry/cancel, and final approval/rejection bind current committed state. The result panel shows the pending `FinalResultBundleV2` ID/SHA plus its V2 candidate and verification references. Approval and rejection require that exact bundle ID; rejection creates no commit.

## Replay truth

The checked-in replay is generated and SHA-256 verified. Its metadata fixes `live_agent=false`, `human_attestation=false`, `new_test_execution=false`, `gemini_calls=0`, and `cloud_proof=false`.

The viewer opens on checkpoint zero. Playback pauses at the fixture's pending final-candidate checkpoint and exposes only `Continue with recorded simulated approval`; continuing depicts the fixture's simulated isolated commit through the same projection reducer used by live Mission Control. The replay is not V2 bundle proof.

The replay keeps `human_attestation=false`. Do not describe its final branch as human approval. Product screenshots/GIFs remain absent until a reproducible capture is completed and recorded.

## Accessibility

Statuses use text as well as color. The table, graph, drawer, replay controls, and stale-state messages have keyboard paths and narrow-width behavior. The relationship list remains the accessible alternative to the visual graph.
