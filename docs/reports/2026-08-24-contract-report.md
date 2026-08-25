# Contract report — 2026-08-24

Session executing `GRAPHENE_CONTRACT_DIRECTIVE` (revised for Alex, 2026-08-24).
Read in this order: the reconciliation table, the change table, spend, authority
uses, blockers, Alex's checklist.

`AUTHORITY_DIGEST` = `b74fe862f2d821e75c3781e9bd61fdac5449102b7e8fed55a98a4870e9a35e22`
(SHA-256 of the directive as handed over; the file is gitignored at
`local/GRAPHENE_CONTRACT_DIRECTIVE.md` and `/GRAPHENE_*DIRECTIVE*.md` is now
ignored at the repo root so a stray copy cannot be committed).

**Preflight blocker — CLOSED 2026-08-25.** The Graft comparison memo was never
missing, only misplaced: it sat in `~/Downloads/` and had not been moved to
`local/GRAPHENE_GRAFT_COMPARISON_AND_DIRECTION.md`. It is now at that path
(gitignored), SHA-256
`2a4e32d31ac813685154bc12596470af757228e6b0b846719deba034bf42b86b`, and it has
been read.

**It changes nothing.** Its "minimum winning demo" is the sequence this session
built and rehearsed — proposed DAG as a terminal table with ready frontier and
scopes, approval of an exact revision/digest, two workers overlapping, a
bounded failure and diagnostic retry, assembly and exact verification, `why`,
the isolated result, and an honest Cloud status beat only if that path is
proven. Its "Revamp" list is the work that landed: graph-as-executable-contract
instead of graph-as-visualization, plan output as a real review surface,
planned versus actual, retries consuming failure evidence, planning bound to the
exact snapshot, and context/token benefits stated as hypotheses until
benchmarked — which is why there is no token claim anywhere in this repository.
The memo is also the source of the Graft figures the README attributes to
NanoNets, and it makes the same attribution itself.

## Reconciliation (directive §1)

Fresh-tree verification before any new work: `scripts/morning_verify.sh` on the
inherited handoff tree (`b7b174a` plus four uncommitted files) →
**`MORNING VERIFY: ALL PASS`**, including the full credential-free matrix
(`2056 passed, 5 skipped`), locked `ruff`, both capsules cold-verified from a
fresh clone, and `store.verify` on all 22 missions. The convergence run was not
in flight; the tree was quiescent apart from those four files, which are now
committed as `2b22789`.

| Convergence non-negotiable | Landed? | Reproduced evidence | Inherited debt |
|---|---|---|---|
| Authority: planner bytes bound to `base_sha` | yes | `tests/unit/cli/test_mission.py` base-sha regressions, matrix green | — |
| Authority: trusted checks are the only completion authority | yes | `test_real_stores_reject_fabricated_pass_without_trusted_check` + evidence tests | — |
| Authority: store-level final-result verification | yes | `tests/adversarial/test_final_approval_bundle.py` 3 passed | — |
| Reproducible verification (locked ruff, CI lint step, no swallowed output) | yes | `morning_verify.sh` ALL PASS on a clean PATH | CI Actions run still unobserved (nothing pushed) |
| Seven-verb surface + rewritten CI smoke | yes | `graphene --help`, `.github/workflows/ci.yml` | — |
| Supervisor loop with the 8/10 and 3/3 gates | yes | `evidence/convergence/2026-08-23-completion-gate/` | — |
| One-command demo | yes | `graphene demo`, `graphene demo --live` | no edit beat — closed this session |
| CI green | unobserved | — | **P1: Alex pushes, then watches Actions** |
| Deterministic runner scheduling test | **no** | reproduced failing under load in this session's first matrix | **P0 — closed, see change table** |
| Approval binds all four elements | partial | approval recorded revision only | **P0 — closed** |
| Unapproved revision cannot dispatch | **no** | no approval check existed at dispatch | **P0 — closed** |

Non-demo debt explicitly deferred, not worked: the intermittent full-matrix
hang (this session removed the unsupported SQLite root-cause claim but does not
replace it — see the change table), the Docker executor proof,
`benchmarks/graph_economics.py`, and the cloud infrastructure steps that only
Alex can take.

## Change table

| Claim | Commit | Verification command / evidence | Result | Known limitation |
|---|---|---|---|---|
| The convergence run's four uncommitted files are committed rather than inherited as dirt | `2b22789` | `pytest -q tests/unit/orchestration/test_cloud.py` -> `9 passed` | PASS | the live Firestore test still cannot run — nothing is deployed |
| Private artifacts and both authority directives cannot be committed by `git add -A` | `acde4a2`, `(final)` | `git check-ignore -v` names the rule for `bundle.json`, both `GRAPHENE_*DIRECTIVE*.md`, `.claude/`, `.vscode/`, and stray root images | PASS | — |
| **Nothing can dispatch a plan revision nobody approved.** `resume`, the operator retry out of FAILED, and `claim_task` all refuse; the approval event records `base_sha` + `plan_revision` + `plan_sha256` | `f987f33` | `pytest -q tests/adversarial/test_plan_revision.py tests/integration/test_plan_edit_path.py tests/unit/orchestration/test_store.py` -> `37 passed` | PASS — this was a real hole: status RUNNING was standing in for approval | the `claim_task` guard is unreachable through the API after the fix, so its regression neuters the approval lookup rather than driving a sequence into it |
| Editing before execution produces immutable revision N+1 needing its own approval; editing after any attempt is claimed fails closed | `f987f33` | `test_the_plan_cannot_be_edited_once_a_worker_has_claimed_a_node`, `test_a_plan_revision_nobody_approved_cannot_be_dispatched` | PASS | the mid-mission variant survives behind `allow_after_dispatch` and is not reachable from the terminal |
| **The scheduler executes the user's revision, not the proposal** | `f987f33` | `tests/integration/test_plan_edit_path.py::test_the_scheduler_executes_the_users_revision_not_the_proposal` | PASS — the added node ran, its order mattered, its artifact reached the verified result, and every attempt carried `plan_revision=2` | the added node is wired by the test, not by a model |
| Runner scheduling is asserted under an injected clock; the deadline is tested separately | `6f59be3` | `pytest -q tests/unit/orchestration/test_runner.py` -> `11 passed`, and the same file green under eight concurrent `yes` processes | PASS — the old test failed in this session's first matrix under load | — |
| Four TTY CLI helpers no longer fail on host speed | `6f59be3` | `test_retained_promotion_precommit_recovers_after_final_append_failure` failed at load average 23 and passed in isolation in 22.36s against its own 20s window | PASS | pytest-timeout remains the real hang guard |
| A cancellation after a passing check records the stage it reached | `6f59be3` | `test_a_cancellation_after_a_passing_check_records_the_stage_it_reached` — the chain names `store-check-receipt` and `check_completed: true` | PASS | the event is not linked from the attempt row, so `why` does not surface it |
| `plan export`/`revise`/`edit`/`lint`/`diff`/`approve`; canonical YAML round-trips and refuses unknown fields, duplicate keys, anchors | `e7eefbf` | `pytest -q tests/unit/orchestration/test_plan_yaml.py` -> `6 passed`; executed end to end against a real scripted mission | PASS | `plan edit`'s `$EDITOR` path has no test; the export/revise path it delegates to does |
| No raw JSON in human mode on the plan path; the mission table, the full node contract, and a diff that flags scope expansion | `e7eefbf` | `test_plan_show_and_diff_reuse_verified_store_plan_authority` asserts the rendered table contains no JSON braces; real output captured in this session | PASS | `plan diff` is structural, not semantic |
| Dashboard, `why`, and `mission status` all name the active revision and digest; `mission status` is the store-backed orientation view | `e7eefbf` | `pytest -q tests/unit/cli` -> `171 passed`; `mission status` on a real mission printed route, frontier, critical path, changed files, remaining scopes, last failure, blockers, decision, next legal commands | PASS | the frontier before dispatch is labelled `FRONTIER ON APPROVAL`, not claimed as ready |
| `demo --live` stops once, for the user's edit, and approves the revision they made | `0b19345` | `pytest -q tests/unit/test_demo_live.py` -> `6 passed`; `test_mission_subprocess_argv_is_exact` pins `--revision 2` | PASS | **no live run of the new sequence has happened** — three rehearsals and the take are still ahead |
| README leads playground-first with a cited "What Graphene is not"; no token-efficiency or benchmark claim anywhere | `d432397` | `pytest -q tests/unit/test_readme_contract.py tests/unit/test_documentation_truth.py` -> `5 passed`; `grep -rniE 'token[- ]?efficien|nanonets|benchmark'` returns only NOT PROVEN labels and the NanoNets attribution | PASS | no proof label was flipped by that commit |
| Approval binds the digest at intent, not only at record time | `(final)` | `test_plan_approval_binds_the_digest_the_operator_was_shown` — the CLI always passes the digest it read, and refuses a `--plan-sha256` that disagrees | PASS | an approval event written before this build carries no digest and binds by revision only; every approval this build writes carries one |
| The SQLite root cause recorded for the intermittent full-matrix hang is withdrawn as unsupported | `(final)` | Read directly: `sqlite3.connect(..., timeout=5)` and `PRAGMA busy_timeout=5000` in `store.py`, so no mission-store call waits forever; `scripted.py` takes a blocking `flock(LOCK_EX)` where `lineage/observation.py` uses `LOCK_EX \| LOCK_NB` | PASS — a false claim removed | **the real mechanism is not established here and is not claimed**; a separate reliability lane is investigating it |
| Release verification on this tree | `(final)` | `scripts/morning_verify.sh` -> `MORNING VERIFY: ALL PASS` | PASS | one earlier matrix failed on host load only; see the two determinism rows |
| **A SQL `LIKE` against a BLOB made every approved plan unapprovable on Linux** | `8873bab` | `LIKE` on a BLOB matches on SQLite 3.51 (macOS) and matches nothing on 3.46 (Linux CI and the pinned deployment image). `git log -S'event_bytes LIKE'` names `f987f33`, the commit where the Linux CI job went red | PASS — prefilter moved into Python; `scripts/linux_parity_check.sh` -> `LINUX PARITY: ALL PASS` in the pinned image, which reproduces the failure before the fix and passes `b7b174a` | **This shipped on `main` for eight pushes.** It was not only CI: the deployed images could dispatch nothing at all |
| A Linux parity check exists, because macOS verification structurally could not see that | `8873bab`, `378ac72` | `scripts/linux_parity_check.sh` runs the CI Linux job's whole scope in `python:3.13-slim@sha256:ffb752e1…`; it announces how many uncommitted files it overlaid, which caught two of its own defects | PASS | it is a pre-push check nobody is forced to run |
| Two demo defects found by live rehearsal, both fatal on camera | `c758837` | the plan export died on macOS's symlinked temp dir before the edit beat; a `MissionProjectionError` reached the screen as a traceback because the projection quarantines a mission permanently and the dashboard's ride-it-out budget re-hit the same refusal | PASS — `22 passed`; the symlink regression fails without its one-line fix | — |
| **Three consecutive rehearsals of the exact filmed sequence** | `4902d76` | `evidence/contract/2026-08-24-rehearsals/` — three live runs, all exit 0, zero tracebacks, all thirteen beats present in each, distinct revision-2 digests, $0.12 / $0.11 / $0.09 | PASS — the edit beat runs live and repeatably | not the film: the edit is applied by a script rather than typed, and approval is `server_derived` |
| Nine documents called live Gemini unproven after it was proven | `323e7d7` | grep for live-Gemini "not proven"/"not run" across `docs/`, `README.md`, `simplreadme.md` now returns only the failure-laboratory line, which is still true | PASS | no label was flipped; prose was made to agree with labels already flipped on their own evidence |
| The whole `plan` surface is driven through the real parser | `378ac72` | `tests/unit/cli/test_plan_cli.py` -> `8 passed`; two verified to fail when the behaviour regresses | PASS | — |
| The filmed sequence fits §9's two minutes | `09522fd` | one run timed end to end: **77s total**, 47s of it the mission itself; `evidence/contract/2026-08-24-rehearsals/timed-run.txt` | PASS | measured with a scripted edit; a person typing the edit spends the ~40s of headroom, and that has not been timed |

## Spend

| Item | Cost | Running total |
|---|---|---|
| Rehearsal attempt 1 — died on the symlinked temp dir; planner call only | $0.07 | $0.07 |
| Rehearsal attempts 2 and 3 — full sequence, before the traceback fix | $0.24 | $0.31 |
| Rehearsal attempt 4 — died on the projection traceback | $0.09 | $0.40 |
| **Three consecutive clean rehearsals** (`4902d76`) | $0.32 | $0.72 |
| One timed run, to measure the sequence against §9's 2:00 (`09522fd`) | $0.12 | **$0.84** |

Cap $40; per-mission ceiling $5 (highest observed: $0.12); soft checkpoint $20.
Everything else recorded here is credential-free: the plan surface, the
authority gates, the edited-DAG execution proof, and the Linux parity check all
run against deterministic workers and contact no provider.

The two failed attempts are listed because they were paid for and because they
are what found the two demo defects. A rehearsal that fails is the rehearsal
doing its job.

## Authority uses

- Delegated approver under this directive's `AUTHORITY_DIGEST` (above) for the
  live Gemini rehearsals of §9's filmed sequence, run against the materialized
  North Star target. Approvals are recorded `server_derived` under the
  pre-authorized bounded demo policy; no human TTY attestation was claimed. Six
  live runs total, $0.72.

## The systemic finding

`scripts/morning_verify.sh` printed `MORNING VERIFY: ALL PASS` on four
consecutive commits while the Linux CI job was red on every one of them, and
while the images this product deploys to Cloud Run could not dispatch a single
task. It is a macOS result by construction and structurally cannot see a defect
that only appears on an older SQLite. The three lanes working tonight made the
same mistake three separate times in three different forms: each ran a real
check in an environment that could not falsify the claim being made.

`scripts/linux_parity_check.sh` is the answer to the specific instance. The
general form is worth stating plainly for whoever reads this next: **a green
check is only evidence in the environment it ran in**, and this repository
deploys to an environment older than the one it is developed on, by pin, until
someone deliberately repins.

## Not done, and honestly labelled

- **The live edit beat has never run.** `demo --live` now contains it and its
  parts are tested credential-free, but no live Gemini mission has executed the
  new sequence. Three consecutive rehearsals and the filmed take are the
  remaining work, and they are the only things that can make the demo row a
  live claim.
- **Cloud eligibility gate: not met.** Unchanged from the convergence handoff —
  see blockers.
- **`plan edit`'s `$EDITOR` path is untested.** It delegates to the tested
  export/revise path, and the filmed demo does not use it (the demo exports,
  pauses, and compiles), so this is labelled rather than closed.
- **The cancellation stage is not reachable from `why`.** It is in the attempt
  evidence chain; linking it needs a stage field on `AttemptResult`.

## Environment note

Another agent ran full-matrix hunts in three separate clones under
`~/Desktop/graphene-nightwatch*` for most of this session, taking the machine's
load average to 32 and starving two of this session's verification runs. Those
processes were never signalled or waited on. One legacy TTY test failed purely
on that load, which is what surfaced the fourth determinism debt.

## Staged by other lanes, for Alex to decide — not taken

A reliability lane worked in separate clones tonight and produced commits this
session did not write, review line by line, or merge. They are recorded here so
the decision is one word rather than an investigation, and **not** taken on a
peer's recommendation:

- `af9f7e0` on `helper/reliability-night-watch-b7b174a` at
  `~/Desktop/graphene-nightwatch` (no remote, by design) is reported to fix the
  macOS CI job's single failure —
  `test_materializer_produces_policy_that_mission_start_loads` failing with
  `No module named pytest`, caused by
  `scripts/materialize_north_star.py` resolving out of the locked virtualenv.
  That lane reports it cherry-picks clean onto `fa302a1`. This session did not
  apply or verify it.
- Nine of that branch's eleven commits are reported to apply clean; `aee2e73`
  conflicts on `.gitignore` and `6ac0b07` depends on it. That lane recommends
  **not** taking `bc2a8ce`, whose work `6f59be3` did differently here.

Also unresolved and explicitly not claimed either way: that lane saw
`tests/unit/orchestration/test_provider_stamps.py::test_malformed_model_reply_is_retried_under_a_higher_fence`
fail once on its branch. It ran eight times here, three of them under
deliberate CPU load, and passed every time. Not reproduced; not called a flake.

## Active blockers

- ~~The Graft comparison memo is absent~~ — **closed**, see preflight above.
- **Cloud: the infrastructure is built, the proof is not captured.** Re-checked
  read-only on 2026-08-25. This is much further along than the convergence
  handoff recorded, because the setup was done after that report was written.

  Present and correct: project `dauntless-host-506507-g2` — a dedicated
  project, not the Gemini-API `gen-lang-client-*` one the setup guide says to
  stop on; all five APIs enabled; Firestore `graphene-taskmaster`
  (FIRESTORE_NATIVE, us-central1); Artifact Registry `graphene`; the three
  service accounts; the `graphene-control-read-token` secret; and the
  coordinator built, deployed and `Ready` at revision
  `graphene-coordinator-00002-6mm` with `maxScale=1`.

  Three things are missing, and the first two are why no evidence exists:

  1. **Nothing may invoke the coordinator.** `gcloud run services
     get-iam-policy graphene-coordinator` returns **zero bindings**. The
     executor service account has no `roles/run.invoker` on the service, which
     `docs/ALEX_CLOUD_SETUP.md` names as the one role it should have. The
     authenticated round trip cannot happen.
  2. **Firestore is empty** — zero collections. No mission has been seeded, so
     `graphene mission executor connect` has never run and none of the evidence
     `docs/CLOUD_PROOF_PLAN.md` §6 requires exists.
  3. **The local side is unwired.** All eight `GRAPHENE_*` cloud variables in
     `.env` are present as keys with empty values.

  **A hazard that is specific to this repository's current state.** The
  deployed image was built at `2026-08-24T09:24:56Z` from a source tree whose
  `backend/graphene/orchestration/store.py` is byte-identical to `b7b174a` —
  before this session. That is fortunate: it means the running coordinator does
  **not** carry the BLOB-`LIKE` defect. But `origin/main` is `fa302a1`, which
  **does** carry it and not the fix. **Rebuilding the coordinator from
  `origin/main` as it stands would produce an image that cannot dispatch
  anything.** Push through `ec309ea` first, or do not rebuild.

- **CI is unobserved for this session's fixes.** `fa302a1` is pushed; the eight
  commits that fix the red Linux job are not.

## Alex's checklist

1. Push (nothing in this session was pushed; no remote was touched). The tip
   fixes the Linux CI job that has been red since `f987f33`; the macOS job's
   remaining failure is the one `af9f7e0` above is reported to fix, and that
   decision is yours.
2. Watch CI — and note that `scripts/linux_parity_check.sh` now tells you what
   the Linux job will say before you push, if Docker is running.
3. `scripts/morning_verify.sh` from a fresh frozen clone.
4. Run the complete propose → inspect → edit → diff → approve → execute demo.
5. Confirm the filmed worker and result evidence names the approved revision
   and digest.
6. Film inside the freeze window (feature freeze 2026-08-29 00:00 ET).
7. Choose cloud teardown versus approved keep-alive — today that decision is
   only about whether to run the setup list at all, because nothing is
   deployed.
