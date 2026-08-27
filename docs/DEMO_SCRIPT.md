# Demo script — Agents stop. The mission doesn't.

Status: shot plan only. The credentialed current-SHA take has not run.

The autonomous hero begins at MCP `start_goal`. Do not use
`graphene demo --live` for this claim: that command still drives the legacy
watcher and interactive plan-edit/review path. Its North Star resources are
packaged, but it neither proves the detached MCP lifecycle nor the new
policy-pre-authorized Orders flow.

## Truth card

Show this before the terminal:

> LIVE TAKE REQUIRED — `google-adk==2.5.0`, requested
> `gemini-3.5-flash`, source-checked 2026-08-27. No current live Gemini,
> model-kill, Codex, cloud, or exact-SHA claim until this take and its evidence
> pass. The checked-in no-key replay is a labelled fixture.

## Setup, off camera

1. Check out the intended committed implementation in a clean clone.
2. Run `scripts/reliability/exact_sha_proof.py` with the expected SHA, matching
   canonical `origin/BRANCH`, `--require-clean`, and an output root outside the
   checkout; retain its SHA-named manifest and artifact hashes.
3. Install that exact artifact.
4. Materialize the Orders target with
   `python scripts/materialize_north_star.py DEST`.
5. Configure exactly one valid credential mode and the supported check
   executor without printing values.
6. Use a fresh private `GRAPHENE_STATE_DIR`.
7. Open three panes: Codex/MCP controller, read-only `graphene ui`, and the
   failure-lab command.

If any step is unavailable, film the verified replay with its fixture label;
do not substitute it into the live story.

## Beat 1 — the ordinary repository problem

Show the unmodified Orders API and run its immutable suite. Say:

> “This service is pinned to Pydantic 2 but still uses the v1 compatibility
> layer. We need native v2 request and response models plus exact dependency
> declarations without changing public behavior.”

Show the checked-in policy: five exact write files, no network, one frozen test
command, concurrency two, bounded retries, `policy_pre_authorized`, and
`auto_finalize_isolated`.

## Beat 2 — Codex starts and leaves

Through the actual Codex MCP connection, call `start_goal` with the exact goal
and success criteria from `demo/north_star/goal.json`, a stable request id,
`driver=gemini-adk`, two workers, policy pre-authorization, and isolated
auto-finalization.

The call must return after durable acceptance in under five seconds. Point to
the accepted request id, base SHA, policy revision/digest, mission id, and next
instruction to poll. Do not call this an approved plan yet.

Then terminate the initiating Codex/MCP process. Say:

> “The controller stopped. The mission did not.”

## Beat 3 — a fresh controller reattaches

Start a new Codex/MCP connection and call `mission_status` with the same
mission id. Show the detached supervisor generation and the compiled plan.

Explain that pre-authorization became effective only after Graphene validated
the exact plan inside policy and recorded the policy decision. If the mission
reports `review_required`, stop the autonomous take; do not approve it by
script and continue as if policy had allowed it.

Open `graphene ui` read-only. Show two disjoint work roots feeding integration,
assembly, and verification.

## Beat 4 — accepted work survives a real child death

Wait until one work publication is accepted and another worker is inside a
barrier-acknowledged live Gemini child. Run:

```bash
python scripts/failure_lab.py auto MISSION_ID --actor-label demo-operator --timeout 900
```

Show only the sanitized returned identity: attempt, worker, task, fence,
pid/pgid/start time, request digest, SDK invocation id, provider-dispatch time,
and accepted sibling publication id.

Say:

> “Graphene killed one exact owned model child, never a process name. The
> provider outcome is unknown, but the child had no repository API, so its
> repository effect is known absent.”

Exit 2 or 3 is not a demo success. A check-process kill, fake worker, injected
check failure, or cancelled controller is not a substitute for this beat.

## Beat 5 — only the failed work returns

In Mission Control, show:

- the sibling publication remains accepted and unchanged;
- the victim attempt ends `provider_interrupted` and publishes nothing;
- only its task returns as attempt 2;
- the fence increases;
- the retry receives a bounded diagnostic; and
- assembly stays blocked until the retry publication is accepted.

Do not say “exactly once.” The provider outcome is unknown. The safe claim is
selective repository recovery under a higher fence.

## Beat 6 — verified completion

Let Graphene assemble accepted publications, run the immutable checks, bind the
exact candidate/final bundle, and policy-finalize to an isolated result ref.
The terminal state must be `completed`; `awaiting_result` is incomplete.

Show that the supplied Orders checkout remains unchanged. Run the Orders tests
and one public behavior example from the isolated result. Call
`mission_summary`.

Call `why` once for an accepted-sibling file and once for a retried file. The
latter must show the failed attempt and the higher-fence producer.

Say:

> “Accepted work survived. Only failed work was replaced. The exact candidate
> passed, and the result is isolated for review.”

## Beat 7 — close with the proof boundary

Show the clean implementation SHA, wheel/sdist hashes, mission head, result ref,
and capsule verification. End with:

> “Agents stop. The mission doesn't. This proves one local Orders mission on
> this exact build. It does not prove Cloud Run, general repositories, human
> attestation, a benchmark, or autonomous delivery.”

## No-key fallback

If credentials or eligibility are unavailable, run:

```bash
graphene mission replay taskmaster
```

Keep the visible label:

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

This fallback demonstrates UI/replay only and must not reuse the live narration.
