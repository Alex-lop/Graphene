# Night report — 2026-08-23 live North Star run

Unattended session executing `GRAPHENE_NIGHT_RUN_DIRECTIVE` v2. Read in this
order: checkpoints, commits, what flipped, spend, authority use, blockers,
morning checklist.

`AUTHORITY_DIGEST` = `c5b116e77d0b95a87901f3b19ce1d1d86dec077147c9570220e3d44ab48e7a06`
(SHA-256 of the directive as handed over; the file itself is gitignored under
`local/` and never enters a commit). Every delegated approval below cites it.

**One-paragraph summary.** Two complete live North Star missions ran on
Vertex AI (`gemini-3.5-flash`, location `global`): two real workers each,
evidence-bound provider receipts, overlap measured on three clocks including
the provider's own, exact verification, bundle-bound approval, isolated local
result, `why` chains to approval, capsules that cold-verify from a fresh
clone. The live failure laboratory killed worker B's registered check four
times; each time the runtime recorded the `-9` receipt, left A untouched, and
retried under a strictly higher fence (once the replacement was accepted) —
but no laboratory mission completed afterwards, because the model's later
output failed its own checks, so "survives *and completes*" stays a
rehearsal claim. `graphene watch` (inbox + read-only GitHub poller) landed
with fixture tests, and a dropped `mission.yaml` started a live mission whose
`why` begins at the trigger. The stretch Shadow v0 `claude-code` adapter
landed too (synthetic-fixture proof; the real transcript ingests with zero
unknown records). Spend ≈ **$4.30** of $20. Nothing was pushed.

## 0. Checkpoint timeline (UTC; local is EDT, UTC−4)

| When | Phase | Spend so far | Worker attempts | State / next intent |
|---|---|---|---|---|
| 12:06 | Preflight start | $0.00 | 0 | Directive digest recorded; `GEMINI_API_KEY` blanked in `.env`; secret scan clean; baseline matrix started |
| 12:12 | Preflight done | $0.00 | 0 | Baseline green (1923 passed, 4 skipped); target materialized; doctor ready (`vertex_ai`); Phase 4 watcher build launched in a worktree (zero-cost) |
| 12:29 | Phase 1, first live contact | ≤$0.20 (est.) | 0 | Planner-only failures fixed forward: 404 (location must be `global`); no error detail → sanitized detail added; unsorted model output → canonicalized |
| 12:48 | Phase 1 complete | $1.22 | 6 | `mission_start_5291caad…` completed live; evidence captured; capsule warm-verified |
| 13:17 | Phase 2, first live kill | $2.0 | 11 | `mission_start_38129f17…`: kill landed, fenced retry accepted, integration task then failed on its own. Two more lab runs followed |
| 13:45 | Phase 2 stopped | $3.1 | 21 | Four kills, zero post-recovery completions; retry discipline. Phase 3 cold verification of both capsules passed from a fresh clone |
| 13:56 | Phase 4 merged, demo | $3.5 | 23 | Watcher branch rebased and fast-forwarded; `watch inbox` created live missions from dropped files (`why` begins at the trigger); none completed |
| 14:10 | Wind-down | $4.3 | 32 | Malformed model replies made retryable; receipts preserved on every rejected output; `docs/DEMO_SCRIPT.md`; Shadow v0 claude-code adapter building in a worktree |
| 15:15 | Handoff | $4.3 | 32 | Shadow adapter merged (matrix 2005 passed on its tree); `scripts/morning_verify.sh` full run on the final `main`; no missions in flight, no pollers, registries empty, `caffeinate` stopped; 23 commits ahead of `origin/main`, remotes unchanged |

## 1. Commits (oldest first; every one has the full matrix green on its tree or states otherwise)

| Commit | Purpose |
|---|---|
| `9a0d1da` | Preflight: `scripts/secret_scan.py` (location-only scanner), preflight doctor evidence, this report |
| `a29152b` | Receipts: provider-side stamps (`response_id`, server `create_time`, HTTP `Date`) via `StampedGemini`; `provider_reported_timestamps` overlap basis; capture script `--mission` mode |
| `c101339` | Failure lab: `scripts/failure_lab.py auto` (unattended, identity-checked kill only once a sibling is accepted) + rehearsal test |
| `c5589b4` | Live-contact fixes: sanitized planner error detail with token counts; canonicalize model ordering; explicit planner rules; planner token cap 16 384 and timeout 120 s; demo policy `max_attempts` 8 → 16 |
| `fc2dbd8` | **Phase 1 evidence + label flip** (`gemini-adk-planner`, `live_gemini` → `verified_live`; `north_star` → `partially_verified_live`) |
| `61e2843` | `why` gains the `prior_attempts` stage (the killed attempt, its fence, result code, receipts) |
| `a3d6a16` | Workers bind the provider receipt even when their output is rejected |
| `a6aef3d` | Failure-lab poller reopens the store after a transient read error |
| `e557715` | **Phase 2/3 evidence + label flip** (failure-recovery leg → `partially_verified_live`; capsule → `verified_live_cold`); `scripts/morning_verify.sh` |
| `6af9587` … `44d9d06` | **Phase 4**: `mission.triggered` event + `store.record_trigger` + `why` trigger stage; `graphene watch inbox` / `watch github` (ETag, backoff, dedupe, fail-closed); 21 fixture tests; README + proof entry (five commits from the worktree agent, rebased, fast-forwarded) |
| `3236cc9` | Malformed model replies retryable (`model_output_rejected`); receipts kept when a mutation is refused at apply time |
| `a407a26` | Watcher derives the mission command id from the trigger digest (each dropped file is its own event) |
| `23eaeca` | **Trigger-demo evidence** (`why` begins at the trigger on a live mission), `docs/DEMO_SCRIPT.md`, `demo/north_star/mission.yaml`, this report |
| `e18553f` | Docs: runbook status + six corrections from the live run; implementation report series table |
| `a9354bd` … `bf16c96` | **Stretch — Shadow v0 `claude-code` adapter** (worktree agent, rebased, fast-forwarded): adapter + synthetic fixture + 43 tests; the real 110-record transcript in `local/shadow/` ingested privately with 0 unknown records (counts only in `contracts/product_proof.json → shadow_agent.real_session_smoke`); label stays `not_proven` overall, `claude_code_adapter: verified_local_on_synthetic_fixture` |
| _(last)_ | This report's final checkpoint (`morning_verify.sh` full run: ALL PASS) |

## 2. What is now proven, with evidence and verify commands

Run from the repo root; the night's store is
`GRAPHENE_STATE_DIR=$HOME/.graphene/north-star-state` (12 missions, all verify).
`scripts/morning_verify.sh` runs everything below in order.

| Claim | Status | Evidence | Verify |
|---|---|---|---|
| Two real Gemini workers, receipts, three-clock overlap, exact verification, bundle-bound approval, isolated result | **`verified_live`** (`mission_start_5291caad50a8ee7a222a9221`; also `…a9d31719`) | `evidence/north_star/2026-08-23-north-star-live.md`, `…/2026-08-23-mission1/` | `graphene --json mission status mission_start_5291caad50a8ee7a222a9221`; `graphene why ledger_service/cli.py --mission …` |
| Failure laboratory: registry-identified SIGKILL, `-9` receipt, sibling untouched, fenced retry accepted, `why` names the killed attempt | **`partially_verified_live`** (`mission_start_38129f17add65609de1c3388`; kills also on `…d2733149`, `…d96b94c5`, `…c8bb3c46`) | `…/2026-08-23-mission4-failure-lab/` (`kill.json`, event list, `why`) | `graphene why ledger_service/report_markdown.py --mission mission_start_38129f17add65609de1c3388` |
| Mission completes after a live recovery | **NOT PROVEN live** — rehearsal only | `tests/unit/orchestration/test_failure_laboratory.py` | `uv run --frozen pytest -q tests/unit/orchestration/test_failure_laboratory.py` |
| Capsule cold-verifies from a clean checkout | **`verified_live_cold`** (both capsules, fresh clone, no store; same laptop) | `cold_verify.json` in both mission directories | `scripts/morning_verify.sh` (clones into a temp dir and verifies) |
| `graphene watch inbox` / `watch github` create missions with the trigger in lineage; deny-by-default | **`verified_local`** on fixtures; **live**: dropped file → mission → `why` starts at `trigger` (`mission_start_a44dcefd7cd8e79e25690611`) | `tests/unit/cli/test_watch.py`, `…/2026-08-23-trigger-demo/` | `uv run --frozen pytest -q tests/unit/cli/test_watch.py tests/unit/orchestration/test_mission_trigger.py` |
| Live GitHub polling | **NOT PROVEN** (env-flag gated, never exercised) | — | — |
| Human-attested (TTY) approval on a live mission | **NOT PROVEN** — every approval tonight was `server_derived`, operator-delegated | every `approve_plan.json` | — |
| Docker, Cloud Run/Firestore, benchmark, media | unchanged (`not_proven` / `not_deployed`) | — | — |

Counts: `scripts/morning_verify.sh` on the final `main` → **ALL PASS**:
matrix **2005 passed, 4 opt-in skips** (5 min), MCP 6 passed; ruff / compileall / `git diff --check` clean. Secret scan:
findings only in test fixtures. Recordings: `local/recordings/` (gitignored)
holds the console logs of every live mission (text, not pty capture — no
`tmux`/`asciinema` on this machine and `script`(1) was refused by the session
sandbox).

## 3. Spend log

Pricing source: Google "Gemini Developer API pricing" page
(`ai.google.dev/gemini-api/docs/pricing`, updated 2026-08-13): **Gemini 3.5
Flash, paid tier — $1.50 / 1M input, $9.00 / 1M output, thinking billed as
output.** Vertex per-token pricing is published as identical; the Vertex
pricing page itself rendered empty from this session, so confirm in Cloud
Billing. Costs are computed from each receipt's provider-reported tokens
(output = candidate + thought) and rounded **up** to the cent; cached input
tokens are charged at full price here (conservative).

**Worker attempts with receipts: 32, $2.33** (per-attempt table:
`local/night/spend_all.ndjson`, reproducible with
`local/night/spend.py MISSION_ID…`). Two early worker calls have no receipt
(a rejected reply on `…d2733149` and a refused mutation on `…91df39c0`, both
before the receipt-preservation fixes): ≈ $0.16 estimated. **Planner calls:
12 accepted (one per mission) + 6 rejected/cancelled ≈ 18 × ≈$0.10 = $1.80
estimated** (one measured: 13 032 prompt / 898 + 6 445 output = $0.09).

**Running total ≈ $4.30 (of which ≈ $1.96 estimated).** Caps: $20 session,
~$5 per mission (max single mission: $0.47). The 12-attempt fallback cap did
not bind because receipts give exact token counts; 32 attempts were spent.
Remaining: ≈ $15.70.

| Mission | Role | Outcome | Receipted worker $ |
|---|---|---|---|
| `…66e186ce` | Phase 1 attempt | failed (plan split tests from code) | 0.25 |
| `…5291caad` | **Phase 1** | **completed** | 0.21 |
| `…bda90a16` | lab try | failed on its own, no kill window | 0.14 |
| `…a9d31719` | lab try | **completed** (poller blind; not lab evidence) | 0.14 |
| `…38129f17` | **Phase 2** | kill + fenced retry accepted; integration failed | 0.47 |
| `…d2733149` | lab | kill; retry `adapter_rejected` | 0.10 (+0.08 est.) |
| `…d96b94c5` | lab | kill; retry check failed | 0.17 |
| `…539482aa` | lab | failed before a window | 0.19 |
| `…c8bb3c46` | lab | kill; retry `adapter_rejected` (receipted) | 0.19 |
| `…b6c751ae` | trigger demo | failed (reply rejected, terminal then) | 0.10 |
| `…a44dcefd` | trigger demo | `why` starts at trigger; markdown task failed | 0.21 |
| `…91df39c0` | trigger demo | failed (refused mutation) | 0.16 (+0.08 est.) |

## 4. Authority-use log

All approvals: `truth_kind: server_derived`, operator label
`night-run-delegate`, rationale `Operator-delegated approval under Alex's
standing overnight instruction (night directive v2);
AUTHORITY_DIGEST=c5b116e7…`. Targets: only materialized copies of
`demo/north_star` under `$HOME/north-star-target`.

| When | Action | Mission |
|---|---|---|
| 12:06 | Blanked `GEMINI_API_KEY` in `.env` (the one permitted edit; server-side rotation is still Alex's) | — |
| 12:40 | `approve-plan --revision 1` | `…66e186ce` (failed on its own) |
| 12:46 / 12:48 | `approve-plan`; `approve-result --bundle-id final_result_e00b5da7…` → isolated commit `abed9e5f…`, `pushed: false` | `…5291caad` |
| 13:00 | `approve-plan` | `…bda90a16` |
| 13:03 / 13:04 | `approve-plan`; `approve-result --bundle-id final_result_d9e15cfd…` → isolated commit, `pushed: false` | `…a9d31719` |
| 13:14 | `approve-plan`; **`failure_lab.py auto` SIGKILL** of attempt `attempt_8373ffbe…` (pid 47009) at 13:15:32Z | `…38129f17` |
| 13:33, 13:38, 13:44 | `approve-plan`; SIGKILLs at 13:34:06Z, 13:38:32Z, 13:44:47Z | `…d2733149`, `…d96b94c5`, `…c8bb3c46` |
| 13:40 | `approve-plan` (no kill opportunity) | `…539482aa` |
| 13:58, 14:01, 14:04 | `watch inbox --once` created the mission (creation only); then `approve-plan` | `…b6c751ae`, `…a44dcefd`, `…91df39c0` |
| 13:2x | Killed my own stuck poller process (not Graphene-owned) once, before the reopen fix | — |

No push, no remote change, no `.env` edit beyond the blanking, no mission
outside the demo target, no `--confirm-human` (no TTY — and claiming it would
have been a lie).

## 5. Blockers, findings, and open questions (each with a recommended default)

- **Model quality is the ceiling, not Graphene.** 2 of 12 live missions
  completed; the rest failed on the markdown-report task (check failures,
  malformed replies, an out-of-lease mutation). Graphene behaved correctly
  every time (fail closed, retry once under a higher fence, never fabricate).
  Defaults: (a) keep `retry_limit 1` for the lab; (b) for video captures,
  consider `retry_limit 2` in `demo/north_star/policy.template.json`
  (budget 16 covers 5 tasks × 3) or a slightly easier markdown criterion;
  (c) a real feature: feed the retry the previous attempt's check summary.
- **Vertex location.** `gemini-3.5-flash` is served only via
  `GOOGLE_CLOUD_LOCATION=global` for this project. `.env` still says
  `us-central1`; the gitignored loader overrides it. Default: set `global`
  in `.env` and in `docs/ALEX_CLOUD_SETUP.md`. `graphene doctor` reported
  ready without probing; a `doctor --probe` (one free `count_tokens`) is a
  cheap follow-up.
- **Cross-database read race (real).** A concurrent reader can see an
  attempt row before its evidence artifact exists (they live in two SQLite
  files), tripping the sticky read quarantine. The poller now reopens; the
  writer-side fix (write evidence before the row, or one file) is for later.
- **Runbook discrepancies found by running it:** `result show` does not
  print the bundle id (`bundle create` does); `git status` shows the
  materializer's own `.graphene/`; `mission start` is idempotent on its
  arguments (use `--command-id` for a re-run; the watcher now derives it
  from the trigger digest); the directive's "heartbeat loss → lease expiry"
  wording describes the scripted path — on `gemini-adk` the check dies with
  `-9`, the attempt fails, the lease is released `failed`, the retry is
  dispatched (runbook wording holds).
- **Cosmetic wart:** `why` prints `UNKNOWN The model-proposed plan awaits
  operator review.` on completed missions (creation-time unknown never
  cleared). Default: clear it on `plan.approved`.
- **Directive/location discrepancies:** the directive was handed over as
  `docs/GRAPHENE_NIGHT_RUN_DIRECTIVE (1).md` (untracked; a byte-identical
  copy sits at `local/`); delete the `docs/` copy after review. No
  `GRAPHENE_ULTRA_DIRECTIVE.md` exists anywhere. No `tmux`/`asciinema`;
  `script`(1) was refused by the session sandbox, so recordings are console
  logs. `.env` is not auto-loaded; live commands sourced `local/night_env.sh`.
- **Minor exposure:** the SDK's 404 message embedded the GCP project id in a
  traceback that reached `local/recordings/` and this session's transcript.
  It is a project id (already in the directive), not a credential; no
  committed file contains it (grep-checked before every evidence commit).
- **Two full matrices at once can deadlock a process-control test.** With
  a second full `pytest` run going in a worktree on the same laptop, one run
  hung in `tests/process/test_mission_cli.py::…recovers_terminal_evidence…`
  and the other in `tests/unit/orchestration/test_runner.py::…external_cancellation…`
  (a zombie `/bin/sleep` child, 20+ min); each passes alone and the matrix
  run alone is green. Default: run one matrix at a time (`morning_verify.sh`
  does) and add `-o faulthandler_timeout=180` when in doubt so a hang dumps
  its stack.
- **Gated pytest** (`tests/process/test_gemini_live.py`) was not run; its
  budget went to the runbook missions. It remains skipped in the matrix.

## 6. Morning checklist for Alex

1. **Rotate `GEMINI_API_KEY` server-side** (Google AI Studio). The local
   blanking does not revoke it.
2. `git log --oneline origin/main..main` — review commits in the order of §1.
3. `scripts/morning_verify.sh` (≈ 7 min; `--quick` skips the matrix). It
   ends with `MORNING VERIFY: ALL PASS` and the proof table.
4. `git remote -v` must equal the preflight snapshot below; `git status`
   should show only the untracked `.claude/`, `.vscode/`, and the
   `docs/…DIRECTIVE (1).md` copy.
5. Set `GOOGLE_CLOUD_LOCATION=global` in `.env` (see §5).
6. Push when satisfied. Nothing was pushed tonight.
7. The day: film per `docs/DEMO_SCRIPT.md` (beats that need a real TTY or a
   completed laboratory mission are marked RE-CAPTURE); cloud consoles
   (Vertex request metrics + Cloud Billing for 12:29–14:10 UTC confirm the
   receipts); decide on `retry_limit 2` for captures.

### Preflight integrity snapshot

```
origin  git@github.com:Alex-lop/Graphene.git (fetch)
origin  git@github.com:Alex-lop/Graphene.git (push)
HEAD    11251c932f00c07ed4c6198380976463cb5587d7   (origin/main was e1e580d7, one commit behind)
```

### Preflight facts

- Baseline on `11251c9`: `uv lock --check` ok; `uv sync --frozen` 73 resolved /
  69 checked; full credential-free matrix **1923 passed, 4 skipped** in
  316 s; `ruff check .` clean; `compileall` ok; `git diff --check` clean.
- Secret scan: 20 findings, all deliberately fake secrets inside redaction
  test fixtures under `tests/`; none elsewhere. `.env` and `local/` are
  gitignored (`git check-ignore` confirmed).
- Capture-script review: `scripts/capture_north_star_evidence.py` ingests no
  repository files; it cannot include `.env`, `local/`, or credential paths.
- Demo target: `demo/north_star` materialized at `~/north-star-target`
  (policy `policy_0fe143f50ccfeb433952e23c`, suite `52 passed`), re-materialized
  once after the attempt-budget fix (base `15c3ad52…`).
- Doctor (`evidence/north_star/2026-08-23-doctor-preflight.json`):
  `configuration_ready: true`, `credential_mode: vertex_ai`,
  `check_executor: host-sandbox supported`, `policy: usable`; no project id,
  path, or credential in the JSON.
