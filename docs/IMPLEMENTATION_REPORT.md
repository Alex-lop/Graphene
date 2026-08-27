# Recovery runtime implementation report

Status: this report records implementation behavior and verification
boundaries, not a release. Commit-specific installed-artifact proof is emitted
as an external SHA-named manifest; credentialed Gemini, Codex-driven, and cloud
proof remain separate.

## Product decision

> **Agents stop. The mission doesn't.**

Graphene now targets one recovery story: accept an ordinary bounded coding goal,
continue beyond controller loss, isolate live model calls, preserve accepted
sibling work, retry only failed work under a higher fence, verify the exact
candidate, and auto-finalize to an isolated local result. The runtime still has
no push, merge, PR, deployment, publication, or target-checkout mutation
authority.

The hero target is the Orders API Pydantic v1-compatibility migration under
`demo/north_star`, not the older ledger-service story and not
`graphene demo --live`. That command still follows the legacy
watcher/edit/review demo; its resources are packaged, but it is not the hero.

## Implemented seams and current proof

| Area | Implemented | Current proof boundary |
|---|---|---|
| MCP | Seven tools with `start_goal` first; stable request id; explicit criteria; live `gemini-adk` default; deprecated `plan_goal`; status/summary/why reads | Official Python MCP client, fixtures, and source checkout. Codex not driven |
| Durable supervisor | Private digest-bound request/state/process records; detached session leader; prompt acceptance; exact-owner liveness; higher-generation restart; stdio-independent recovery; isolated two-attempt planner journal | Credential-free scripted and planner-crash process tests. No current live provider mission |
| Authorization | Project policy schema v2; requested `policy_pre_authorized`; recomputed plan-policy decision; atomic policy-authoritative approval; `review_required` fallback | Store/validation tests. No live Orders decision capture |
| Finalization | Policy-bound `auto_finalize_isolated`; exact pending bundle; isolated result ref; `completed` supervisor state | Fixture/store paths. No credentialed current-tree completion |
| Live child | `python -I` child, canonical length-framed request/result, no repository API, one ADK call, content capture disabled, sanitized errors | Protocol/fake tests. No returned current live identity |
| Kill barrier | Durable provider-dispatch acknowledgement; exact pid/pgid/start/executable registry; interruption evidence; known-absent repository effect | Unit/protocol logic. No real model child killed |
| Selective retry | Accepted sibling fan-in, retryable interruption, higher fence, stale refusal, bounded diagnostic, exact assembly/verification | Existing fake/check fixtures. Full live choreography pending |
| Orders hero | Materializer, exact goal/criteria, five-file write policy, immutable suite, no network, two workers/one retry | Target and policy tests only |
| Packaging | Shared installed-resource resolver; North Star materializer/target; minimal legacy resources; wheel/sdist isolated verifier; clean expected-SHA/canonical-remote proof gate | Run-specific truth belongs to the external SHA manifest or CI result |
| UI | Read-only mission projection includes supervisor/retry/result state | Replay and fixture checks; live hero not captured |

## Runtime versions

- Python: `>=3.13,<3.14`
- Google ADK: `google-adk==2.5.0`
- Requested Gemini model: `gemini-3.5-flash`
- Model/rules source-check: 2026-08-27

The model ID is a request, not proof of returned identity or present
eligibility. Re-check the official rules and catalog before any live call or
claim change.

## Credential-free checks observed

- Focused package/resource, CI-contract, bootstrap, live-demo-refusal, and
  verified-replay tests: 22 passed.
- Focused ruff and `git diff --check`: passed for the packaging slice.
- `scripts/verify_installed_artifacts.py` verifies wheel and sdist outside the
  checkout with source-path overrides removed. Diagnostic working-tree runs do
  not count as exact-SHA proof.
- MCP protocol/supervisor/policy/child/failure tests exist in the moving tree;
  aggregate results belong in the final handoff only after the tree freezes.

No test result here is attached to a new Git SHA. Historical counts and the
2026-08-23 live runs are not restated as current proof.

## Installed artifact matrix

The verifier:

1. builds an sdist from the checkout;
2. builds the wheel from that sdist;
3. installs wheel and sdist into separate virtual environments;
4. executes from outside the repository with `PYTHONPATH`, `PYTHONHOME`, and
   `VIRTUAL_ENV` removed and private HOME/state/runtime directories;
5. imports the legacy resource bundle and checks pytest is absent from runtime
   requirements;
6. materializes the packaged Orders target and runs its fixed Pytest-free
   acceptance check;
7. drives installed MCP `start_goal` without credentials, disconnects, starts a
   fresh stdio server, and reattaches to the same terminal no-key mission; and
8. runs both entry points, replay/UI, legacy CLI, and legacy MCP initialization.

The exact-SHA driver additionally requires the expected clean revision and a
matching canonical remote ref. It writes its manifest outside the checkout so
the artifact does not invalidate or make a self-referential commit claim.

## What remains external

The proof is incomplete until one clean committed implementation:

- builds and passes the installed-artifact matrix in CI;
- is started through the actual Codex MCP client;
- returns promptly and survives that controller disconnect;
- runs two eligible real Gemini workers through ADK 2.5.0;
- kills one barrier-acknowledged model child;
- preserves the accepted sibling and retries only the victim under a higher
  fence;
- reaches exact verification, isolated result, and `completed`;
- demonstrates the working Orders migration, summary, and two causal `why`
  paths; and
- captures sanitized current-SHA evidence.

Docker, Cloud Run/real Firestore, benchmark results, current screenshot/GIF,
and film remain separate and `NOT PROVEN`.
