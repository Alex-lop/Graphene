# Product

## User and problem

Graphene is for a solo developer or small technical lead supervising two to five bounded coding workers against one repository. Without a coordinator, that person becomes the scheduler: preventing conflicting edits, relaying accepted context, noticing failures, integrating outputs, and reconstructing whether the candidate is safe.

The product outcome is an inspectable, exact-candidate decision and an optional isolated local result. It is not a transcript, a decorative agent animation, or an autonomous push.

## Product loop

1. The developer supplies a goal, success criteria, repository identity, and deny-by-default policy.
2. A planner proposes a bounded task decomposition; deterministic validation, not the model, decides whether it is admissible.
3. The durable scheduler dispatches only ready, non-conflicting work under exact leases and fencing tokens.
4. Dependencies receive only accepted publications. Integration and verification bind the exact assembled candidate.
5. The mission registers an immutable exact-candidate bundle and pauses for its ID-bound decision. Rejection creates no commit; approval may create only a Graphene-owned isolated local result.

Gate-scoped private input can resume a `needs_input` task through `graphene task input`, which stores bounded bytes privately and commits only the exact reference. A browser-input seam is contract-tested but hidden in one-command live mode because safe staged-input cleanup is not wired. Attempt, worker-time, or artifact exhaustion produces a durable `blocked_budget` explanation and replan-or-cancel action instead of scheduler spin.

## Supported scope

The verified local product path is the checked-in Taskmaster replay plus the macOS scripted fixture. The fixture proves scheduler mechanics, real bounded fixture checks, retry, accepted-only assembly, exact verification, and isolated-result mechanics. It is not independent model behavior or arbitrary-repository support.

The checked-in Gemini path includes a credential-gated typed planner and bounded two-to-five-worker runtime. Credential-free tests run the same ADK worker adapter with deterministic fake models against an isolated disposable repository; that proves local wiring, not Gemini behavior. The 2026-08-23 Gemini run is historical earlier-runtime evidence: two `gemini-3.5-flash` workers completed the North Star mission with evidence-bound provider receipts, and a completion gate of 9/10 ordinary and 3/3 controlled-failure missions finished end to end. Approvals in those runs were operator-delegated (`server_derived`), not TTY-attested. The current recovery runtime is **NOT PROVEN** live; see the [canonical proof table](PROOF.md). The Docker boundary has deterministic argument/ownership tests, but no responsive daemon smoke was captured. The official Firestore emulator production path is verified locally. Cloud Run and real Firestore remain **NOT DEPLOYED — NOT PROVEN**.

The exact supported matrix is:

| Path | Repository/runtime | Status |
|---|---|---|
| Mission replay | Generated sanitized fixture; portable read-only viewer | Verified local |
| Scripted mission | Frozen status-report fixture; macOS `/usr/bin/sandbox-exec` | Verified local |
| Gemini planner/workers | Bounded ADK proposal and worker implementation; explicit credentials/model | Historical earlier-runtime evidence from 2026-08-23 with provider receipts; current recovery runtime **NOT PROVEN** live (see [Proof](PROOF.md)) |
| Generic Docker executor | Narrow Python/pytest contract | Not proven live |
| Firestore emulator | Production create/approve/readiness/claim/heartbeat/completion plus sharded materialization/reconcile | Verified local; not a deployment |
| Cloud control plane | Read-only viewer plus packaged coordinator/client/local-executor protocol | Partial authoritative vertical; real cloud behavior not proven and not deployed |
| Graph economics | Equal-gate three-mode harness | No measured result; not proven |
| Submission video | Truth-labeled script/runbook | Not recorded; not proven |

Arbitrary repositories, installers, arbitrary shell, autonomous PR/push/merge/deploy, visual workflow editing, and per-skill CPU/RAM attribution are outside the supported release.

The terminal-native Taskmaster aliases include `graphene plan show/diff/lint`, `graphene run/status/watch/why`, `graphene cancel/retry/request-replan`, `graphene task input`, and `graphene bundle create/verify`. They reuse the mission store and reducers behind `graphene mission ...`. Before any final decision, Graphene registers one immutable pending `FinalResultBundleV2`; Mission Control, approval, and rejection bind its exact bundle ID. Bundle export writes only a new private-mode output, and verification accepts that file or persisted ID.

## Success boundary

Graphene succeeds only when the store, accepted artifacts, assembled candidate, verification receipt, and final decision all bind. A valid policy path or a generated replay cannot substitute for a real worker, sandbox, model, or cloud proof.
