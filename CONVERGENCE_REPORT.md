# Convergence report — 2026-08-23/24

Session executing `GRAPHENE_CONVERGENCE_DIRECTIVE` v2 (post-audit revision).
Read in this order: the change table, spend, authority uses, blockers, Alex's
handoff checklist.

`AUTHORITY_DIGEST` = `d3468ea0f33db18ed04806a8b1d25704921a05610f8f854d503ab70ee611fedd`
(SHA-256 of the directive as handed over; the file itself is gitignored at
`local/GRAPHENE_CONVERGENCE_DIRECTIVE.md` and never enters a commit). Every
delegated approval below cites `convergence-directive-v2` and that digest.

**One-paragraph summary.** The two §6 authority gates landed before any live
spend: planning now reads Git objects at the bound `base_sha` instead of
worktree bytes (which also removes the intermediate-symlink escape by
construction), and the mission store recomputes a final result bundle itself
and issues its own verification receipt instead of trusting whichever caller
happened to verify. Reproducibility was fixed first — `ruff` is locked, CI runs
it, and `morning_verify.sh` no longer hides a failing step's output. The retry
loop learns: a failed trusted check leaves a redacted structured diagnostic that
the next attempt's prompt carries, and a repeated identical failure signature
terminalizes instead of buying a blind third attempt. The North Star was
narrowed to two disjoint model tasks, deterministic assembly and a golden
contract test, and live missions against the new shape plan in exactly that
shape with zero lint issues.

## Change table

| Change | Commit | Verification command/evidence | Result | Remaining limitation |
|---|---|---|---|---|
| Lock `ruff`/`pytest-timeout`, add the CI lint step, stop `morning_verify.sh` swallowing output (§1.8, §5.1) | `3e9f013` | `env -i PATH=/usr/bin:/bin uv run --frozen ruff check .` on a clean PATH; full matrix `2006 passed, 4 skipped` | PASS — the "ALL PASS" no longer depends on an ambient linter | CI itself unobserved since the step was added; Actions logs still to be read |
| Bind planning to `base_sha`; reject tracked/staged drift; kill the `O_NOFOLLOW` intermediate-symlink escape (§1.1, §6.1) | `9e39bb6` | 5 named regressions in `tests/unit/cli/test_mission.py`; matrix `2010 passed, 4 skipped` | PASS — no path under the repository is opened during planning at all | the drift gate exempts `.graphene/project.json`, as `_load_project_policy` already did |
| Store becomes the final-bundle authority; server-issued verification receipt required at approval and on cold verify (§1.2, §6.2) | `e660518` | `tests/adversarial/test_final_approval_bundle.py` flipped from documenting the hole to enforcing the fix; matrix `2012 passed, 4 skipped` | PASS — the invented `result_tree_id`/mutation bundle is refused unbound and refused when the recompute says no | the recompute still trusts the `TrustedCheckReceipt`'s claim that checks passed; it recomputes trees and manifests, not test results |
| Structured check failure class + redacted diagnostic; shared redaction moved to neutral ground (§8) | `ba86707` | 11 diagnostics tests; `tests/unit/shadow/test_isolation.py` green (it caught the first draft importing shadow from orchestration) | PASS | parsing is pytest-shaped; other templates fall back to a redacted tail |
| Failure-aware single retry: prior attempt id, fence, result code, failed check names, receipt digest, redacted summary; repeat terminalizes (§8) | `54646dd` | 6 tests in `tests/unit/orchestration/test_failure_aware_retry.py`, including a blind-resolver control run that spends all three attempts while the diagnostic-aware run stops at two | PASS | that a live model *repairs* what it is shown is a separate, live claim |
| Live mission dashboard + `mission watch --follow` (§7) | `8150817` | 11 dashboard tests; run against live mission `mission_start_b5f5a6ac…`: real tasks, attempts, fences, `SPEND $0.09` from receipts, exit 0 | PASS | real-TTY in-place redraw is not machine-verified; it shares its logic with the tested plain path |
| North Star narrowed to two disjoint model tasks + deterministic assembly + golden contract (§8) | `561e7f2` | base suite `48 passed, 2 skipped`; reference implementation `50 passed, 0 skipped`; live plan came back as exactly `[implement_json_report, implement_markdown_report] → assemble → verify`, lint `valid`, zero issues | PASS | interpretation recorded in `GOAL.md` "Why this shape" with an explicit escape hatch |
| `--follow` stopped polling a mission that is waiting on a person | `fa5bae8` | caught against the real completed mission; regression `test_follow_stops_when_the_mission_needs_a_person` | PASS | — |
| `graphene demo --live` — the whole story in one terminal; `mission start --inject-check-fault` (§7, §8) | `776bd61` | 5 demo tests; `demo --help` and `mission start --help` executed | PASS | — |
| `why` stopped printing a plan-review caveat that approval had already made false (night §5 wart) | `8a4357a` | `test_plan_review_unknown_clears_once_the_plan_is_approved`; re-run on the live mission | PASS | — |
| **Completion gate: 9/10 ordinary, 3/3 controlled-failure**, labels flipped with evidence (§8) | `6764e30` | `evidence/convergence/2026-08-23-completion-gate/`; `morning_verify.sh --quick` every step PASS; matrix `2046 passed, 4 skipped` | PASS — `north_star` and `survives_one_of_them_failing` are `verified_live` | a store predating the bundle-verification receipt now fails cold verification by design; the night store is affected, its capsule still verifies |
| `graphene demo --live` executed end to end, live, and captured (§7, §8) | `79b387f` | `evidence/convergence/2026-08-23-demo-live/run-1.txt`; zero tracebacks and zero raw JSON asserted over the transcript | PASS | three consecutive rehearsals not yet logged |
| `docs/DEMO_SCRIPT.md` rewritten to ≤ 3 pages against the new surface (§8) | `63b648b` | every command in it executed this session, including `graphene demo --driver verified-replay` | PASS | — |
| Dashboard survives the two-database visibility race; the demo stops measuring its own injected fault (§6.5, §8) | `732bd02` | **three consecutive rehearsals, all exit 0**, after a first attempt that was 1/3; `evidence/convergence/2026-08-23-demo-live/` | PASS | the race itself is unfixed at the writer; the dashboard rides it out and still raises when it never clears |
| Cloud check authority labelled `executor_attested`; abandon disabled; multi-executor refused; Firestore seeding gap closed; emulator **success** path proven (§6.3, §6.4, §9) | `c971254` | matrix `2054 passed, 5 skipped`; real `emulators:exec` run `4 passed` | PASS | nothing hosted — `cloud-run-firestore` stays `not_deployed` |
| Ctrl-C is honoured however the process was launched (found by morning_verify failing twice) | `27d35ea` | `scripts/morning_verify.sh` **ALL PASS** in the backgrounded case that exposed it; the new regression fails without the fix | PASS | — |

## Spend

Pricing source: `gemini-3.5-flash` paid tier, $1.50/1M input and $9.00/1M output
tokens, thinking billed as output — the same basis as the night run. Cost is
computed from evidence-bound provider receipts and rounded up per receipt
(`local/night/spend.py`).

| Item | Cost | Running total |
|---|---|---|
| All planner calls (22 missions with receipts) | $1.50 | $1.50 |
| All worker calls | $2.38 | **$3.88** |

That is every live mission in this session: the smoke, the 10-mission ordinary
gate, the 3 failure-injected gate missions, and every `graphene demo --live` run
including the three consecutive rehearsals. Nothing else was billed — no cloud
resource was created or enabled.

Cap $40; per-mission ceiling $3 (highest observed: $0.17); soft checkpoint $20.
Planner tokens ARE in this total: the night's ledger read `prompt_tokens` off
the top level of the plan-proposal receipt, where it is always null — the counts
were in `provider_usage` all along. `local/conv/spend.py` reads the right field.

## Authority uses

- Delegated approver under `convergence-directive-v2` (digest above) for live
  Gemini missions on materialized demo targets, after §6.1–2 landed and were
  green. Approvals are recorded `server_derived` with operator label
  `convergence`; no human TTY attestation was claimed.

## Active blockers

- **The cloud vertical was NOT deployed, and this is a decision that needs you.**
  Billing is enabled on the configured project and one account is authenticated,
  but the Cloud Run, Cloud Build, Artifact Registry, Firestore and IAM APIs are
  all disabled, and the configured project is a Gemini-API auto-created
  `gen-lang-client-*` project — not the dedicated sandbox that
  `docs/ALEX_CLOUD_SETUP.md` requires, and that document says to stop if the
  project differs from the intended one. Enabling five APIs and creating a
  Firestore database on the project that also serves your live Gemini quota is
  not a call I should make for you. **Nothing was enabled, created, or billed.**
  Recommended default: create a dedicated sandbox project, then run the ordered
  command list below. Separately, `docs/CLOUD_PROOF_PLAN.md` §5 is right that no
  CLI could seed a mission into Firestore — that software gap is being closed in
  this session so the remaining work is infrastructure only.
- **A load-dependent hang exists in the mission store under concurrency.** One full-matrix
  run wedged in `test_unexpected_runner_failure_is_committed_and_releases_leases`
  with worker threads blocked in `sqlite3.connect` / `close`, once inside
  `assert_fence` and once with a thread in `store.snapshot`'s connection close
  while the main thread was in `_connect` from `heartbeat`. Twelve isolated
  runs of the implicated file passed, and the full matrix completed cleanly
  eight times today, so it is intermittent — roughly two hits in ten full runs.
  `faulthandler_timeout = 180` produced both stack dumps, and
  `timeout_method = "thread"` hard-kills it (the default signal method cannot —
  the main thread's `ThreadPoolExecutor` shutdown waits on the stuck threads
  forever). Not root-caused; the shape points at WAL checkpoint/shm contention
  when transient connections are opened and closed per operation.
  Recommended default: leave the guards, publish the limitation, and re-run
  `morning_verify.sh` if it reports a matrix timeout rather than a real failure.
- **CI status is unobserved.** Nothing was pushed, so no Actions run has
  exercised the new ruff step, the hang guards, or any of today's code. This is
  the first thing to watch after the push.

## The cloud vertical: exactly what is left, and who decides

The software gap is closed. `orchestration/cloud_seed.py` runs the seeding
sequence `docs/CLOUD_PROOF_PLAN.md` §5 said nothing implemented, the successful
completion path is proven against the official Firestore emulator, and the two
transitions the protocol cannot honestly support now fail closed with named
errors. What remains is infrastructure, and it starts with a decision only you
should make.

**Decide first:** the configured project is a Gemini-API auto-created
`gen-lang-client-*` project — the same one serving your live Gemini quota — and
`docs/ALEX_CLOUD_SETUP.md` says to stop if the project differs from the intended
sandbox. Recommended default: create a dedicated sandbox project.

Then, in order (every one of these WRITES, and the marked ones BILL):

1. `gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com iam.googleapis.com billingbudgets.googleapis.com --project="$PROJECT_ID"`
2. `gcloud firestore databases create --database="$DATABASE_ID" --location="$FIRESTORE_LOCATION" --edition=standard --type=firestore-native --delete-protection` *(BILLS)*
3. `gcloud artifacts repositories create "$AR_REPOSITORY" --location="$REGION" --repository-format=docker` *(BILLS storage)*
4. Three service accounts and their IAM grants — see `docs/ALEX_CLOUD_SETUP.md` §§30–145
5. `gcloud billing budgets create --budget-amount='10USD'` with 50/90/100% thresholds — **do this before the deploy, not after**
6. Derive the audience from the project number, then
   `gcloud builds submit . --config=deploy/cloudrun/coordinator-cloudbuild.yaml --substitutions="_IMAGE=$COORDINATOR_IMAGE"` *(BILLS build minutes)*
7. `gcloud run deploy "$COORDINATOR_SERVICE" --image="$COORDINATOR_IMAGE" --service-account=… --no-allow-unauthenticated --min-instances=0 --max-instances=1 --concurrency=8 --port=8080 --set-env-vars=…`
8. `gcloud run services add-iam-policy-binding "$COORDINATOR_SERVICE" --member="serviceAccount:$EXECUTOR_SA_EMAIL" --role='roles/run.invoker'`
9. Seed the mission with `orchestration.cloud_seed.seed_mission` against the live
   `FirestoreMissionStore`, then
   `graphene mission executor connect --repo PATH --mission MISSION_ID --coordinator-url … --audience … --workers 1`

`--workers 1`, not 2: a second concurrent executor session is refused by design.
When the evidence is captured, either tear the service down or record the
decision to keep it alive through judging — `min-instances=0` means an idle
service bills essentially nothing, but the decision should still be explicit.

## Alex's handoff checklist

1. Push (nothing in this session was pushed; no remote was touched).
2. Watch CI — the ruff step and the pytest hang guards are new.
3. `scripts/morning_verify.sh` from a fresh frozen clone.
4. `graphene demo` and `graphene demo --live`.
5. Film the one-take script.
6. Choose and record cloud teardown versus approved judging keep-alive — but
   note that **nothing is deployed**, so today that decision is only about
   whether to run the list above at all.
