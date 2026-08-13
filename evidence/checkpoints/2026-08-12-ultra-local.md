# Graphene Implementation Checkpoint

- Timestamp / timezone: 2026-08-12T19:03:58-07:00, America/Los_Angeles
- Cycle / stage: Cycle 5 / Stage 4 local boundary
- Audited base SHA: `9057e405c32559628ce5a800d8f1d3aef1d907e3`
- Integrated HEAD: unstaged working tree over the audited base; no commit created
- Working-tree state: implementation and tests are local; no commit, push, deployment, publication, or cloud spend
- Product claim under test: event-first, evidence-bound Graphene is locally executable and fails closed at its trust boundaries
- Gate status: `EXTERNAL_BLOCKED`

## User changes preserved

- Paths: `GRAPHENE_ULTRA_IMPLEMENTATION_LOOP.md`
- Pre-existing diff status: untracked at startup; unchanged, SHA-256 `2ab2c2002fcc54c703c9af5ee8c6081438fdb7e95459b34cb15bd634ffde9829`

## Agent lanes

| Lane | Assignment | Base SHA | Lease/worktree | Status | Returned artifact |
|---|---|---|---|---|---|
| Integrity | Stage 0 boundaries, SQLite lineage, context handoff, and adversarial runtime falsification | `9057e405` | shared, bounded paths | READY after falsification | implementation, regression tests, and two security findings repaired by root |
| Runtime | Installed ADK seam, common service, ADK/MCP adapters, interruption recovery | `9057e405` | shared, bounded paths | READY | implementation plus real-Runner/fake-LLM and official MCP-client tests |
| Security | Stage 0 falsification, reducer, Firestore parity/corruption, promotion substitution | `9057e405` | shared, bounded paths | READY after falsification | implementation plus adversarial/corruption/substitution tests |

## Integrated work

| Patch | Files | Why accepted | Root review |
|---|---|---|---|
| Stage 0 auth/privacy/anchor hardening | app, execution adapter, models, frontend compatibility, adversarial tests | auth precedes lookup; raw output is transient; feedback binds exact same-run evidence | 27 boundary cases plus full suite |
| Versioned event spine and artifacts | v2 models/contract, SQLite lineage/artifact stores | canonical append/CAS/idempotency/verification with bounded public events | corruption, retry, restart, checkpoint tests |
| Verified reducer and read-only CLI | reducer, CLI, renderers | projections derive only from verified events; replay is immutable | deterministic render/replay tests |
| Scoped runtime and adapters | common service, ADK, MCP | one six-operation authority boundary; events commit before responses | real installed ADK Runner with fake LLM and official MCP in-memory client |
| Fresh handoff and Billing denial | context compiler/runtime | included-only brief, fresh identities, zero Billing dispatch | omission, substitution, excluded-evidence, and zero-work tests |
| Crash recovery and promotion | recovery, promotion coordinator | uncertain dispatch/mutation quarantines; human promotion binds exact N/N+1/N+2 heads | crash/CAS and request/receipt substitution tests |
| Firestore parity | per-event transactional adapter | mirrors frozen SQLite semantics without whole-snapshot persistence | adversarial fake-client corruption/retry parity tests |
| Fixed-test containment | execution adapter | denies host paths, writes, network, stdin, parent argv/environment, sysctl, and fork | native `KERN_PROCARGS2` probe plus mutation-uncertainty regressions |

## Rejected or deferred work

| Item | Reason | Revisit condition |
|---|---|---|
| Real Gemini 3.5 Flash call | no authorized Google project, ADC, entitlement, or spend | user supplies authority and credentials |
| Real Firestore / Cloud Run proof | no cloud authorization; local success cannot substitute | user authorizes project writes/deployment |
| Stage 5 README/submission rewrite | earlier real-external gate is not green | all Stage 4 proof gates pass |
| CLI mutation-command wiring | local components are proven independently; wiring the legacy app would enlarge the change without external proof | product chooses v2 as the primary runtime |
| OS-level MCP STDIO proof | official in-memory protocol path is green; no launcher is frozen | a supported terminal-client launch contract is chosen |
| Ruff-wide mechanical rewrite | repository has no Ruff configuration; ad-hoc Ruff reported 71 style findings and 34 unformatted files | project adopts and pins Ruff policy |

## Verification

| Command | Exit | Result | Evidence path/hash |
|---|---:|---|---|
| `.venv/bin/pytest -q` (pass 1) | 0 | 208 passed, 5 upstream ADK warnings | console transcript |
| same Python command without cleanup (pass 2) | 0 | 208 passed, 5 upstream ADK warnings | console transcript |
| `node --test frontend/test/*.test.mjs` (twice) | 0 | 8 passed each | console transcript |
| three frontend `node --check` commands (twice) | 0 | passed | console transcript |
| deterministic demo, twice without cleanup | 0 | local restart/promotion proof green; cloud labels remain unverified | `/tmp/graphene-stage0-demo.json`, SHA-256 `3ee26724fedd151a024cfc2f84208547df3f55e07ab58498700403a8eae12de5` |
| focused sandbox and write-uncertainty suite | 0 | 22 passed | console transcript |
| focused ADK/MCP/service/recovery/promotion suite | 0 | 55 passed | console transcript |
| `git diff --check && uv lock --check` | 0 | passed | console transcript |
| `uvx ruff check backend/graphene tests demo` | 1 | diagnostic only: 71 findings; no repository Ruff policy | console transcript |

Current redacted manifest: `evidence/2026-08-12-ultra-local-manifest.json`.

## Claim ledger

| Claim | Status | Missing proof |
|---|---|---|
| Live runtime lineage | `LOCAL_GREEN` | real Gemini invocation |
| Verified graph/evidence used by a genuinely fresh agent | `LOCAL_GREEN` | externally recorded real-model flow |
| Billing denial with zero invocation | `LOCAL_GREEN` | deployed-product observation |
| Privacy-safe Firestore persistence | `LOCAL_GREEN` | real Firestore transaction/restart |
| Client-neutral MCP over common service | `LOCAL_GREEN` | OS-level STDIO/disconnect transcript |
| Evidence-bound human promotion | `LOCAL_GREEN` | durable hosted repository commit |
| Real Gemini / Google ADK execution | `EXTERNAL_BLOCKED` | authorized project, credentials, model entitlement, and spend |
| Real Cloud Run / Firestore use | `EXTERNAL_BLOCKED` | deployment and persistence authorization |
| Authenticated real-world human identity | `CUT` | demo bearer identifies only an operator session |
| Malicious-admin tamper resistance | `CUT` | design intentionally assumes an honest host |

## External blockers

- Exact missing authorization or credential: no `gcloud`, ADC, Google project/model configuration, or authority to spend/deploy was available.
- Independent local work still available: product-level v2 app/CLI mutation wiring and an OS-level MCP launcher, both deliberately deferred rather than creating competing runtime truth sources.

## Risks and kill-rule state

- Trigger checked: token/work-data leakage, forged/gapped/cross-run evidence, stale/substituted context or promotion input, Billing work creation, interrupted dispatch, host access, and post-mutation persistence failure.
- Result: no kill rule remains triggered in the local suites. Real-cloud privacy and real-model claims remain explicitly unproved.

## Next action

Authorize one Google project, ADC identity, exact Gemini 3.5 Flash model, Firestore namespace, and bounded spend for the real ADK/Firestore cold-restart experiment.

## Next wave

1. Run one authorized real ADK invocation through the common service and save redacted event/model evidence.
2. Run the same lineage against real Firestore, cold restart, verify, and replay.
3. Only if both pass, wire the v2 runtime as the product entry point and begin Stage 5 documentation.
