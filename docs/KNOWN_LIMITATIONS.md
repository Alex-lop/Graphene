# Known limitations

This list describes the reviewed release. A limitation moves only when code, deterministic verification, and any required external proof all exist.

| Area | Current status | What closes it |
|---|---|---|
| Real Gemini workers | Runtime implemented and fake-model ADK path verified locally; live provider behavior **NOT PROVEN** | Two distinct credentialed workers, scoped receipts, measured overlap, exact fan-in/result |
| Generic repositories | Narrow initialized-repository runtime exercised locally with fake ADK workers; general support remains unproven | Published repository/runtime matrix plus adversarial scope and live execution proof |
| Fake-ADK vertical slice | Two workers reach exact `awaiting_result` without touching the source checkout and register the pending bundle | Add both terminal decision branches to one end-to-end fake-model matrix |
| Docker execution | **NOT PROVEN** on a responsive daemon | Immutable image build and opt-in smoke on the selected host |
| Result inspection/export | `mission result show/export` verifies the V2-bound candidate and writes a create-only private patch; the stable release matrix is green | Live operator capture |
| Replay final decision | Pending-candidate checkpoint and simulated continuation exist; replay is not V2 bundle proof | Public capture; replay remains fixture proof, not live execution |
| Product media | Metadata present; PNG/GIF missing | Verified replay PNG plus reproducible GIF or documented capture-tool blocker |
| Browser commands | CSRF, idempotency, stale-state, attribution, finalizer, cancellation, and disabled-mode tests pass; private input remains hidden and live proof is pending | Safe staged-input cleanup plus captured verified operator flow |
| Task input | `graphene task input` commits only a digest-bound reference; the browser seam is tested but hidden in one-command live mode | Add safe staged-input cleanup before injecting the browser coordinator, then capture the flow |
| Hard budgets | Attempt, worker-time, and artifact exhaustion commit actionable `blocked_budget` state; no live resource-pressure demo | Exercise replan/cancel recovery in the recorded live path |
| Replanning | Request command only; lower-level linked revision/diff/invalidation store core is tested, but no CLI/model path generates N+1 | Operator-complete generation, review, and reapproval path |
| Artifact closure | V2 envelopes bind direct inputs and accepted publications; transitive `delta`/`cumulative_snapshot` subsumption is not supported | Add closure semantics only when a real plan needs non-flat artifact ancestry |
| Repository mutations | Generic workers support bounded create/update/delete/rename/chmod on regular `100644`/`100755` files; runtime/assembly/final-tree and scripted deletion paths are tested. Symlink/submodule mutations fail closed | Broader repository matrix plus live provider proof |
| Retention | Metadata only; no automatic expiry and purge | Tested purge/retention implementation and operator controls |
| Owned idle STDIO MCP cleanup | Missing | Strong ownership registry and lifecycle tests |
| Firestore cloud scheduler | Official emulator production vertical passes create/approve/readiness/claim/heartbeat/completion/materialization; it is not a full `SchedulerStore` | Add worker revoke/expiry/recovery, generic scheduler completion, awaiting-result, pause/resume/cancel, gate/final parity, then run the shared corpus |
| Cloud-to-local executor | Typed protocol, packaged coordinator, OIDC HTTPS client, artifact fetch, and local executor loop pass credential-free tests | Live authenticated cloud-to-local reconnect/result proof |
| Cloud Run/Firestore | **NOT DEPLOYED** | Explicit owner opt-in and captured authenticated smoke |
| Cloud streaming | Per-client two-second polling | Shared listener/fan-out with measured behavior |
| Cloud artifact authority | Executor-local durable spool only; cross-executor transfer is unsupported | Reviewed private object storage and cold-restart recovery |
| Resource Sentinel | The product Gemini scheduler commits sampled-pressure decisions and a credential-free path proves reduced then restored dispatch. Unsupported/non-owned process sampling stays unavailable | Capture pressure/action evidence in a live provider run |
| V2 artifact/final bundles | Successful publications require V2 envelopes; an immutable pending final bundle is registered before display/approval/rejection, and both decisions bind its ID | Live operator proof only; no format expansion is needed for this release |
| Taskmaster causal query | `graphene why PATH --mission MISSION_ID` verifies current mission authority and reports only committed links/unknowns | Richer TUI navigation and broader query shapes |
| Graph-economics benchmark | Harness and equal-gate contract are tested; results **NOT PROVEN** | Real repeated equal-quality runs with raw receipts, median, and P95 |
| Comprehension study | Not run | Five-person protocol in [Graph necessity evaluation](GRAPH_NECESSITY_EVAL.md) |
| Public demo/video | **NOT PROVEN**; not recorded | Unedited, truth-labeled four-minute demo using only proven paths |
| Terminal-native breadth | Plan lint/show/diff, run/status/watch/why/bundle, cancel/retry/request-replan, and private task input exist; revision-producing replan, arbitrary mission replay, cross-run diff-runs, and a TUI are absent | Add only workflows backed by existing durable authority when the live path needs them |
| Human identity | Confirmed local-terminal truth durably includes a bounded hash of the local OS uid and password-database username in the public operator label; this is not external authentication | Add an authenticated identity provider before claiming external principal assurance |

The legacy Auth protocol tour remains supported as a regression surface, not as Taskmaster proof. Current mission-plan validation rejects its reserved `legacy_auth_v2` attempt link.
