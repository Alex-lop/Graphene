# Night report — 2026-08-23 live North Star run

Unattended session executing `GRAPHENE_NIGHT_RUN_DIRECTIVE` v2. Read in this
order: checkpoints, commits, what flipped, spend, authority use, blockers,
morning checklist.

`AUTHORITY_DIGEST` = `c5b116e77d0b95a87901f3b19ce1d1d86dec077147c9570220e3d44ab48e7a06`
(SHA-256 of the directive as handed over; the file itself is gitignored under
`local/` and never enters a commit). Every delegated approval below cites it.

## 0. Checkpoint timeline (UTC; local is EDT, UTC−4)

| When | Phase | Spend so far | Attempts | State / next intent |
|---|---|---|---|---|
| 12:06 | Preflight start | $0.00 | 0 | Directive digest recorded; `GEMINI_API_KEY` blanked in `.env`; secret scan clean; baseline matrix started |
| 12:12 | Preflight done | $0.00 | 0 | Baseline green (1923 passed, 4 skipped); target materialized; doctor ready (`vertex_ai`); Phase 4 watcher build launched in a worktree (zero-cost). Next: provider-side receipt stamps, then Phase 1 live run |
| 12:29 | Phase 1, first live contact | ≤$0.20 (est.) | 0 worker attempts | Three planner-only failures, fixed forward: (1) `404 NOT_FOUND` — Vertex serves `gemini-3.5-flash` only through the `global` location for this project (free `count_tokens` probe; `us-central1`/`us-east4`/`us-east5` 404); (2) planner JSON rejected with no detail → sanitized error detail added; (3) detail showed `work intent collections must be sorted and unique` → model ordering is now canonicalized on input. Watcher agent finished Phase 4 on its branch (1944 passed). |
| 12:48 | Phase 1 complete | $1.22 (ceil'd; $0.60 of it estimated) | 6 worker attempts | `mission_start_5291caad…` completed live: receipts, three-clock overlap, bundle-bound delegated approval, isolated result; evidence captured and capsule warm-verified. Next: commit series, merge the watcher branch, Phase 2 failure lab live |

## 1. Commits (oldest first)

| Commit | Purpose |
|---|---|
| `9a0d1da` | Preflight: `scripts/secret_scan.py` (location-only scanner), preflight doctor evidence, this report |
| `a29152b` | Receipts: provider-side stamps (`response_id`, server `create_time`, HTTP `Date`) via `StampedGemini`; `provider_reported_timestamps` overlap basis; capture script `--mission` mode |
| `c101339` | Failure lab: `scripts/failure_lab.py auto` (unattended, identity-checked kill only once a sibling is accepted) + rehearsal test (fake workers, real sandbox-exec) |
| `c5589b4` | Live-contact fixes: sanitized planner error detail with token counts; canonicalize model ordering; explicit planner rules; planner token cap 16 384 and timeout 120 s; demo policy `max_attempts` 8 → 16 |
| _(next)_ | Phase 1 evidence + label flip (same commit) |

## 2. What is proven / what did not flip

**Flipped (Phase 1 commit):** `mission_paths.gemini-adk-planner.status` and
`delivery_gates.live_gemini.status` → `verified_live`; `north_star.status` →
`partially_verified_live`; README rows `Live Gemini` and `North Star`.

Evidence: `evidence/north_star/2026-08-23-north-star-live.md` plus the raw
sanitized outputs and the capsule under `evidence/north_star/2026-08-23-mission1/`.
Verify commands (repo root, `GRAPHENE_STATE_DIR=$HOME/.graphene/north-star-state`):

```bash
uv run --frozen graphene --json mission db verify                    # verified_missions: 2
uv run --frozen graphene --json mission status mission_start_5291caad50a8ee7a222a9221
uv run --frozen graphene why ledger_service/report_json.py --mission mission_start_5291caad50a8ee7a222a9221
uv run --frozen python -m graphene.orchestration.capsule verify \
  evidence/north_star/2026-08-23-mission1/mission_start_5291caad50a8ee7a222a9221.graphene-capsule
shasum -a 256 evidence/north_star/2026-08-23-mission1/mission_start_5291caad50a8ee7a222a9221.graphene-capsule/manifest.json
#   ef4917194fbdc9f2c98628af83743d60750abee44f81b833a492f6fd7e2404b8
```

**Did not flip (and why):** human-attested approval on a live mission (no
TTY tonight — approvals are `server_derived` with the delegation recorded);
live failure laboratory (Phase 2, pending); cold capsule verification
(Phase 3, pending); Docker, Cloud Run/Firestore, benchmark, media (out of
scope tonight). The gated `tests/process/test_gemini_live.py` was not run —
its budget went to the runbook mission; it stays skipped in the matrix.

## 3. Spend log

Pricing source: Google "Gemini Developer API pricing" page
(`ai.google.dev/gemini-api/docs/pricing`, last updated 2026-08-13 UTC):
**Gemini 3.5 Flash, paid tier — $1.50 / 1M input tokens, $9.00 / 1M output
tokens, thinking tokens billed as output.** Vertex AI per-token pricing for the
same model is published as identical; the Vertex pricing page itself was not
machine-readable from this session (it rendered as an empty shell), so the
AI-Studio figure is the cited rate and the morning check should confirm the
Cloud Billing report agrees. Cost per attempt is computed from the receipt's
provider-reported `prompt_tokens` / (`candidate_tokens` + `thought_tokens`)
and rounded **up** to the cent. Planner calls are billed too and are logged
the same way.

| # | When (UTC) | Mission | Role | Model | Input tok | Output tok (incl. thought) | Cost (ceil) | Running total |
|---|---|---|---|---|---|---|---|---|
| p0 | 12:29 | — | planner | gemini-3.5-flash @ us-central1 | 0 | 0 | $0.00 (404, unbilled) | $0.00 |
| p1 | 12:30 | — | planner (rejected: ordering) | gemini-3.5-flash | ~13k (est.) | ~8k (est.) | $0.10 (est.) | $0.10 |
| p2 | 12:32 | — | planner (rejected: ordering) | gemini-3.5-flash | ~13k (est.) | ~8k (est.) | $0.10 (est.) | $0.20 |
| p3 | 12:34 | — | planner (rejected: <2 roots) | gemini-3.5-flash | ~13k (est.) | ~8k (est.) | $0.10 (est.) | $0.30 |
| p4 | 12:35 | — | planner (plan invalid: budget/write overlap) | gemini-3.5-flash | ~13k (est.) | ~8k (est.) | $0.10 (est.) | $0.40 |
| p5 | 12:38 | — | planner (json truncated) | gemini-3.5-flash | 13 032 | 8 175 (730 + 7 445) | $0.10 | $0.50 |
| p6 | 12:39 | `…66e186ce` | planner (accepted) | gemini-3.5-flash | 13 032 (12 190 cached) | 7 343 (898 + 6 445) | $0.09 | $0.59 |
| w1 | 12:40 | `…66e186ce` | worker-1 `add_report_tests` #1 (check failed) | gemini-3.5-flash | 2 010 | 8 047 | $0.08 | $0.67 |
| w2 | 12:40 | `…66e186ce` | worker-2 `implement_report_renderers` #1 (passed) | gemini-3.5-flash | 2 468 | 10 031 | $0.10 | $0.77 |
| w3 | 12:41 | `…66e186ce` | worker-1 `add_report_tests` #2 (check failed) | gemini-3.5-flash | 2 012 | 7 276 | $0.07 | $0.84 |
| p7 | 12:44 | — | planner (cancelled at 60 s wall time; billed, counts unknown) | gemini-3.5-flash | ~13k (est.) | ~8k (est.) | $0.10 (est.) | $0.94 |
| p8 | 12:45 | `…5291caad` | planner (accepted) | gemini-3.5-flash | ~13k (est., receipt `artifact_34a4ab2b…`) | ~7k (est.) | $0.10 (est.) | $1.04 |
| w4 | 12:46 | `…5291caad` | worker-1 `task-json-renderer` #1 | gemini-3.5-flash | 4 327 | 5 277 | $0.05 | $1.09 |
| w5 | 12:46 | `…5291caad` | worker-2 `task-markdown-renderer` #1 | gemini-3.5-flash | 4 317 | 5 454 | $0.05 | $1.14 |
| w6 | 12:47 | `…5291caad` | worker-1 `task-cli-integration` #1 | gemini-3.5-flash | 5 448 | 8 214 | $0.08 | $1.22 |

Estimated rows (planner calls that produced no receipt) are charged at the
measured p5/p6 size, rounded up; the provider's billing report is the
authority for those. Worker attempts used: **6 of 12**. Caps: $20 session,
~$5 per mission. Remaining: ≥ $18.70.

## 4. Authority-use log

| When | Action | Mission | Detail |
|---|---|---|---|
| 12:46 | `mission approve-plan --revision 1` (operator-delegated) | `mission_start_5291caad50a8ee7a222a9221` | `truth_kind: server_derived`, operator label `night-run-delegate`, rationale cites `AUTHORITY_DIGEST`; ran two live workers ($0.18) |
| 12:48 | `mission approve-result --bundle-id final_result_e00b5da7…` (operator-delegated) | `mission_start_5291caad50a8ee7a222a9221` | bundle-bound; created isolated local commit `abed9e5f…` in the Graphene-owned result repo; nothing pushed |
| 12:40 | `mission approve-plan --revision 1` (operator-delegated) | `mission_start_66e186ce9369c149c167a677` | same delegation; mission ended `failed` on its own retry budget (plan flaw), $0.25 |
| 12:06 | Blanked `GEMINI_API_KEY` in `.env` | — | The one permitted `.env` edit (§2). Blanking does **not** revoke the key server-side — Alex must rotate it himself. Doctor afterwards: `configuration_ready: true`, `credential_mode: vertex_ai` |

## 5. Blockers and open questions

- **Directive location discrepancy.** The directive says it lives at
  `local/GRAPHENE_NIGHT_RUN_DIRECTIVE.md`; it was handed over as the untracked
  file `docs/GRAPHENE_NIGHT_RUN_DIRECTIVE (1).md`. A byte-identical copy was
  placed at the `local/` path (same digest); the `docs/` copy is left alone and
  is never staged. Recommended default: delete the `docs/` copy after review so
  it cannot be committed by accident.
- **`GRAPHENE_ULTRA_DIRECTIVE.md` is absent** from the repo and `local/`. Its
  Shadow v0 / demo-target specifications are therefore taken from the runbook,
  `docs/SHADOW_ADAPTER_SPEC.md`, and the current code, which the directive
  ranks above it anyway.
- **No `tmux` / `asciinema` on this machine.** `caffeinate -dims` runs as a
  detached background process for the whole session; terminal recordings use
  `script`(1). Installing tmux was not necessary and was not done.
- **Vertex location.** `gemini-3.5-flash` is served to this project only via
  `GOOGLE_CLOUD_LOCATION=global` (us-central1/us-east4/us-east5 → 404, checked
  with free `count_tokens` calls). `.env` still says `us-central1`; the
  gitignored loader overrides it. Recommended default: set `global` in `.env`
  yourself and note it in `docs/ALEX_CLOUD_SETUP.md`. `graphene doctor`
  reported `configuration_ready: true` because it never probes the provider —
  a `doctor --probe` that makes one free `count_tokens` call would have
  caught this before any spend (not built tonight; zero-cost follow-up).
- **Minor exposure.** The SDK's 404 message embedded the GCP project id in a
  traceback that landed in `local/recordings/` and this session's transcript.
  It is a project id, not a credential, and it already appears in the
  directive; no committed file contains it (checked by grep before every
  evidence commit).
- **Runbook discrepancies found by running it:** (a) 3.3 says `result show`
  prints the bundle id — it does not; `graphene bundle create MISSION_ID
  --output FILE` registers and prints it (the tested path); (b) 1.2 says
  `git status --porcelain` must print nothing after materializing — it prints
  `?? .graphene/` because the materializer writes the policy after the base
  commit; (c) `mission start` is idempotent on its arguments, so a re-run after
  a failed mission returns the failed mission — pass `--command-id` to start a
  fresh one; (d) the directive's Phase 2 wording "heartbeat loss → lease
  expiry" describes the scripted path; on the gemini-adk path the runbook's
  wording holds (check dies with exit -9 → `acceptance_check_failed` → lease
  released `failed` → retry under a higher fence).
- **Cosmetic wart:** `graphene why` prints `UNKNOWN The model-proposed plan
  awaits operator review.` on completed missions because the creation-time
  unknown is never cleared after `plan.approved`. Not a chain gap.
- **`.env` is not auto-loaded by Graphene.** Live commands source a gitignored
  loader (`local/night_env.sh`) that exports only the three Vertex values plus
  the run gates; nothing prints values.

## 6. Morning checklist for Alex

1. Rotate `GEMINI_API_KEY` server-side (Google AI Studio) — blanking the local
   file does not revoke it.
2. `git log --oneline origin/main..main` and review commits in order.
3. `scripts/morning_verify.sh` (lands later tonight) — one command re-runs the
   night's verification.
4. `git remote -v` must equal the preflight snapshot below; `HEAD` is simply
   ahead of `origin/main`.
5. Push when satisfied. Nothing was pushed tonight.

### Preflight integrity snapshot

```
origin  git@github.com:Alex-lop/Graphene.git (fetch)
origin  git@github.com:Alex-lop/Graphene.git (push)
HEAD    11251c932f00c07ed4c6198380976463cb5587d7   (origin/main was e1e580d7, one commit behind)
```

### Preflight facts

- Baseline on `11251c9`: `uv lock --check` ok; `uv sync --frozen` 73 resolved /
  69 checked; `pytest tests/unit tests/integration tests/process
  tests/adversarial --ignore=tests/process/test_mcp_stdio.py` → **1923 passed,
  4 skipped** (the four opt-in gates) in 316 s; `ruff check .` clean;
  `compileall` ok; `git diff --check` clean. No baseline repair was needed.
- Secret scan (`scripts/secret_scan.py --commits 30 --include-untracked`):
  20 findings, all of them deliberately fake secrets inside redaction test
  fixtures under `tests/` (and the same lines in their introducing commits);
  none in source, docs, contracts, or evidence. `.env` and `local/` are
  gitignored (`git check-ignore` confirmed).
- Capture-script review: `scripts/capture_north_star_evidence.py` ingests no
  repository files at all — it builds its own fixture repo and writes only
  identifiers, digests, and counts. It cannot include `.env`, `local/`, or
  credential paths. No change needed.
- Demo target: materialized at `~/north-star-target` from
  `demo/north_star`; policy `policy_0fe143f50ccfeb433952e23c`; target suite
  `52 passed`.
- Doctor (`evidence/north_star/2026-08-23-doctor-preflight.json`):
  `gemini_preflight.configuration_ready: true`, `modes.gemini-adk.credential_mode:
  vertex_ai`, `check_executor.requested: host-sandbox, supported: true`,
  `policy.status: usable`, `platform_isolation.status: usable`. The JSON
  contains no project id, path, or credential.
