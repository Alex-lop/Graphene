# North Star live run — 2026-08-23 (night run)

Evidence for the runbook's section 6. Everything here is an identifier, a
digest, a count, a status word, or a timestamp; the raw files cited live
next to this document under `evidence/north_star/` and contain the same
kinds of values only. Prompts, worker output, source bytes, command output,
environment values, and home paths are absent by construction.

Approvals tonight were **operator-delegated, not human-attested**: `plan.approved`
and `final_candidate.approved` carry `truth_kind: server_derived`, operator
label `night-run-delegate`, and the rationale
`Operator-delegated approval under Alex's standing overnight instruction (night directive v2); AUTHORITY_DIGEST=c5b116e77d0b95a87901f3b19ce1d1d86dec077147c9570220e3d44ab48e7a06`.
The TTY `--confirm-human` attestation path remains **NOT PROVEN on a live mission**.

## Session facts

- Graphene source: the commit carrying this file (the live run executed the
  working tree that became this commit series; the fixes it needed are the
  three commits preceding it).
- `uv lock --check`: ok. Baseline matrix on `11251c9`: 1923 passed, 4 skipped.
- Provider: Vertex AI, credential mode `vertex_ai`, location **`global`**
  (`us-central1` returns 404 for `gemini-3.5-flash` on this project — found
  with a free `count_tokens` probe, recorded in `NIGHT_REPORT.md`).
- Check executor: `host-sandbox` (macOS `/usr/bin/sandbox-exec`).
- Doctor: `2026-08-23-doctor-preflight.json` (`configuration_ready: true`,
  `credential_mode: vertex_ai`, `check_executor.supported: true`).
- Section 2's gated pytest (`tests/process/test_gemini_live.py`) was **not**
  run tonight; the budget went to the runbook mission itself. It stays
  credential-gated and skipped in the matrix.

## Mission 1 — `mission_start_5291caad50a8ee7a222a9221` (completed)

Target: the materialized `demo/north_star` ledger service, base commit
`15c3ad525209d3fad796bdd28b842312434a3c3f`, policy
`policy_0fe143f50ccfeb433952e23c` (attempt budget raised to 16 in the same
series — see `NIGHT_REPORT.md`). Target suite before the run: `52 passed`.

| Fact | Value |
|---|---|
| Head | seq **74**, `event_sha256` `33c1599cedc578263c9705fa7817b671aa2835000a337afe74e7a5322f290f55` |
| Requested / returned model | `gemini-3.5-flash` / `gemini-3.5-flash` |
| Plan proposal receipt | `artifact_34a4ab2b2c9b44fad9e711961d6fbdda` sha256 `34a4ab2b…e84279` |
| Plan (revision 1) | work roots `task-json-renderer`, `task-markdown-renderer` (parallel), integration `task-cli-integration`, then `assemble`, `verify` |
| Dispatch batches | `[["task-json-renderer","task-markdown-renderer"],["task-cli-integration"],["assemble"],["verify"]]` |
| Attempts | 5 (3 work, 1 assembly, 1 verification); `execution_mode: gemini_live` |
| Worker sessions / invocations | 3 / 3 (`worker_session_ids`, `worker_invocation_ids` in `approve_plan.json`) |
| `receipt_unknowns` | `[]` |
| Overlap, store clock (`max_window_ms`) | **28 491 ms** (bases `attempt_timestamps`, `lease_timestamps`) |
| Overlap, runtime-stamped provider call (`provider_call_max_window_ms`) | **26 463 ms** |
| Overlap, provider's own clock (`provider_reported_max_window_ms`) | **25 364 ms** (server `create_time` → HTTP `Date`, independent of every Graphene clock; whole-second `Date` makes it an underestimate) |
| Candidate tree sha256 | `32d155ca0dfa565fdca16cb8c685e5edebad8c08b0d295888258e3390310491f` (10 594 bytes) |
| Verification receipt | `artifact_b2a33a2c2f34ae5bace469de9145eb0d` sha256 `b2a33a2c…b7faf`, `checks_passed: true` |
| Bundle | `final_result_e00b5da7fd25207740afe30fc01764d8`, `bundle_sha256` `e00b5da7fd25207740afe30fc01764d8ac531612a493121af3e01b467d2f64ee`, `bundle verify` → `verified: true` |
| Final decision | `approve` (delegated, bundle-bound) → `status: completed` |
| Isolated result | local commit `abed9e5f779a306654cd9c32ed8af952606994ad` at `refs/graphene/results/e84c0b3b9b10a9fc95d7f721` in the Graphene-owned result repository; `pushed: false`, `pull_request_created: false`, `deployed: false` |
| Changed paths | `ledger_service/cli.py`, `ledger_service/report_json.py`, `ledger_service/report_markdown.py`, `tests/test_cli_reports.py`, `tests/test_report_json.py`, `tests/test_report_markdown.py` |
| Target checkout after | `git status --porcelain` → only the materializer's own untracked `.graphene/`; `HEAD` = `15c3ad52…` (base); the only ref is `refs/heads/main` — `source_checkout_unchanged: true` |
| `graphene mission db verify` | `{"mission_count": 2, "verified_missions": 2, "status": "current"}` (the second mission is the failed attempt below) |

### Sanitized receipt fingerprints (`worker-provider-receipt`)

Each `sha256` is the digest of the receipt bytes and equals
`shasum -a 256 receipts/<id>.json` inside the capsule. Token counts are the
provider's (`usage_source: provider_reported`); costs are rounded up.

| attempt | worker | receipt id | sha256 | prompt / candidate / thought tokens | runtime call window (UTC) | provider `response_id` / `create_time` → `Date` |
|---|---|---|---|---|---|---|
| `attempt_2d6b86bfd40bbb9b0a6300e46eb748da` (`task-json-renderer`) | `gemini-worker-1` | `artifact_eabc601ecb4bb9f39d3f9a1dd523f187` | `eabc601ecb4bb9f39d3f9a1dd523f1874f5b6f097ead44189834d6c1b2634950` | 4327 / 1109 / 4168 | 12:46:46.319 → 12:47:13.257 | `t-uKatyXJsWJl7oPjNGysAI` / 12:46:47.625 → 12:47:13 |
| `attempt_333a2fef6b2812b2ec8614b397f37e29` (`task-markdown-renderer`) | `gemini-worker-2` | `artifact_dfe9ac14ac68427b6ea5485156735dce` | `dfe9ac14ac68427b6ea5485156735dce8afe1faa9ce74ed9beda63fbb0ba7a70` | 4317 / 1137 / 4317 | 12:46:46.794 → 12:47:15.048 | `t-uKarvrJoLHl7oPutzB4Qk` / 12:46:47.636 → 12:47:15 |
| `attempt_2f50d5853f564ebf702920cee6eaa504` (`task-cli-integration`) | `gemini-worker-1` | `artifact_f7e0b0ded5ae36424375491f5f9bbec6` | `f7e0b0ded5ae36424375491f5f9bbec637952d3f68ad0a8eacf1c0645785a651` | 5448 / 2189 / 6025 | 12:47:16.980 → 12:47:54.192 | `1euKasCuB8TLsbwP4c03` / 12:47:17.120 → 12:47:54 |

Dual-source overlap, read straight off the table: the two renderer calls
overlap from 12:46:46.794 to 12:47:13.257 on the runtime clock (26 463 ms)
and from 12:46:47.636 to 12:47:13 on the provider's clock (25 364 ms). The
integration call starts after both, as the plan requires, and its windows
overlap nothing (`window_ms: 0` pairs).

### `graphene why`

`why_ledger_service_report_json.py.{txt,json}` (worker A's file) and
`why_ledger_service_cli.py.{txt,json}` (the integration file) each show an
unbroken chain: `target` → `producer_attempt` (worker id, `attempt_number=1`,
`fence=1`, `test-receipt` and `worker-provider-receipt` both
`resolvable=True`) → `assembly_candidate` → `verification` → `approval`, with
the closing `TRUST:` line. The single `UNKNOWN` line repeats the mission's
creation-time note (`The model-proposed plan awaits operator review.`), which
the store never clears after approval — a cosmetic wart recorded in
`NIGHT_REPORT.md`, not a gap in the chain.

### Capsule

`mission_start_5291caad50a8ee7a222a9221.graphene-capsule/` (22 files,
180 KB) — `manifest.json` sha256
`ef4917194fbdc9f2c98628af83743d60750abee44f81b833a492f6fd7e2404b8`.
Warm `graphene mission capsule verify`: `verified: true`. The **cold**
verification from a clean checkout is recorded separately in
`NIGHT_REPORT.md` (Phase 3) and by `scripts/morning_verify.sh`.

## Mission 0 — `mission_start_66e186ce9369c149c167a677` (failed; kept for the record)

The first plan that passed validation split the tests from the code they
test into two "independent" roots, so `add_report_tests` could never pass
`fixture-tests` in its own isolated workspace: attempt 1 (fence 1) and the
automatic retry, attempt 2 (fence 2), both ended `acceptance_check_failed`
with `test-receipt` and `worker-provider-receipt` evidence, while
`implement_report_renderers` (`gemini-worker-2`) passed; the mission ended
`failed` when the retry budget ran out, and nothing downstream ran. This is
bounded failure behaving as designed, and it is why the planner instruction
now states that every task must pass the suite by itself. Its three receipts
(sha256 `d186913c…daf1e`, `afb7900c…a93e108`, `ea40227e…5e2f9`) are in the
same mission store and verify (`verified_missions: 2`). It is **not** a
failure-laboratory run: nothing was killed; the check failed on its own.

## Phase 2 — live failure laboratory (Mission 4, `mission_start_38129f17add65609de1c3388`)

Driven unattended by `scripts/failure_lab.py auto` (commit `c101339`, hardened
in `a6aef3d`): it polls the store and the owned-process registry and kills
only when a running work attempt's sibling already holds an accepted
publication. Raw outputs and the capsule: `2026-08-23-mission4-failure-lab/`.

| Step (directive §7 / runbook 4.4) | What the record shows |
|---|---|
| A accepted before the kill | `task_json_report` attempt `…63330404` (`gemini-worker-1`, fence 1): `artifact.accepted` seq 38, `publication_210020a3af14cc5dac31ac8b4409e071` |
| B holds a live lease with a registered check | `task_markdown_report` attempt `attempt_8373ffbe1ffef817b422c3ed26b0e960` (`gemini-worker-2`, fence 1): `task.leased` seq 15; registry record pid = pgid = 47009, executable `/usr/bin/sandbox-exec`, start time recorded |
| Identity re-verified, then `SIGKILL` | `registry.signal` re-checked pid / pgid / start time / exec-in-place wrapper immediately before `killpg`; `killed_at` **2026-08-23T13:15:32.097Z** (`kill.json`; `transient_read_errors: 1` — the poller reopened the store once) |
| Trusted receipt records the kill | `test-receipt` `artifact_9660f9dbe1d227b922c6bc92bdd85eb5`: `exit_code -9`, `acceptance_check_failed`, `timed_out false`; lease `…26b0e960` released with reason `failed`; no `artifact.published` for that attempt |
| A survives untouched | `publication_210020a3…` is the same accepted row before and after; `why ledger_service/report_json.py` chains to attempt `…63330404` |
| Descendants blocked | `assemble` / `task_integrate_reports` have no attempt until B's task is accepted (seq 40–41 only record the dependency on A) |
| Retry under a higher fence | `task.retried` seq 43 (`acceptance_check_failed`) → `task.leased` seq 46, attempt `attempt_397c5a0c0615787ae83ef2d0f98a51d2` on the *other* worker (`gemini-worker-1`), **fence 2** |
| Replacement publishes, stale fence cannot | `artifact.published`/`accepted` seq 55–56, `publication_b9d48d91691777c154553590e152be4b`; the fence-1 lease is released; `why` names attempt 2 as producer |
| `why` includes B's failed attempt | `why_ledger_service_report_markdown.py.txt`: `STAGE producer_attempt` = attempt `…f98a51d2` (`attempt_number=2 fence=2`), `STAGE prior_attempts` = attempt `…26b0e960` (`state=failed result_code=acceptance_check_failed fence=1`) with both its receipts resolvable |
| Mission completes → verification → approval | **Did not happen.** The integration task `task_integrate_reports` then failed its own acceptance check twice (attempts `…ba5e8216` fence 1, `…7dd0149b` fence 2, both `exit 1`, model output quality, unrelated to the kill) and the mission ended `failed` at head seq 84 (`2f4b0c56ae0a3d05719eee5fec80b8ee05d1b4b53b4ef7c7f14f4510b337cfaa`) |

Receipts for the attempts above (`worker-provider-receipt` sha256 / provider `response_id`):
`task_json_report` #1 `3892e53397756d758e3e95e5cf4e950f13c6ff53f05f82ce591f159c5215490d` / `O_KKasKmMezql7oP49nz4AQ`;
`task_markdown_report` #1 (killed) `87208831ace7128b215efdd4a92db280ca3b910eda5302bc93dbe11990ad7e02` / `O_KKaq34MaG3sbwP9cm9AQ`;
`task_markdown_report` #2 (retry) `9b7916d912ef78116bcd9564376e065a186ac4e4bb1ea01733a339ec3bd194a9` / `dfKKavGzCOzql7oP49nz4AQ`;
`task_integrate_reports` #1/#2 `fcbf2f25…06d450` / `32faaac7…6f9dfa`.

The same kill landed on three more missions (`…d2733149`, `…d96b94c5`,
`…c8bb3c46`, kill JSON and console logs in `local/recordings/`); in each the
fenced retry was dispatched and then failed on the model's own output
(`adapter_rejected` or a failed check). Two other lab attempts never reached
a kill window (`…bda90a16` failed on its own; `…a9d31719` completed while the
first, non-reopening poller was blind — that is a second complete live
mission, not lab evidence). Retry discipline stopped the laboratory after
the third post-kill failure of the same signature.

**What this flips:** the failure-recovery leg becomes `partially_verified_live`
— SIGKILL through the registry, the `-9` receipt, the untouched sibling, the
automatic retry under a strictly higher fence, the accepted replacement, and
a `why` chain that names the killed attempt are all live facts. **What it
does not flip:** mission completion after recovery (exact verification,
approval, isolated result) was not observed live on any laboratory mission;
that leg rests on the fake-model rehearsal (`tests/unit/orchestration/
test_failure_laboratory.py`, labelled REHEARSAL — NOT PROOF).

## Phase 3 — cold verification from a clean checkout

A fresh `git clone` of this repository into a temporary directory (commit
`a6aef3d`, no `GRAPHENE_STATE_DIR`, no mission store), `uv sync --frozen`,
then `uv run --frozen python -m graphene.orchestration.capsule verify …` on:

- Mission 1's capsule from the clone's own tree
  (`manifest.json` sha256 `ef4917194fbdc9f2c98628af83743d60750abee44f81b833a492f6fd7e2404b8`) → `verified: true`, 11 checks
  (`manifest_file_digests`, `mission_event_chain`, `attempt_evidence_chains`,
  `receipt_references`, `receipt_contents`, `final_bundle`, `tree_manifest`,
  `publication_envelopes`, `plan_revisions`, `attempt_coverage`,
  `manifest_summary`), 10 `not_checked` items stated by the verifier.
- Mission 4's capsule (`manifest.json` sha256
  `1d1ac81f27e6bf2ec4f72972b642326d09c706b684d7be1fe3a6598470df62ef`) → `verified: true`, 11 checks.

Machine: Darwin arm64 (this laptop; no second machine was available). The
sanitized verifier outputs are `cold_verify.json` in each mission directory.
Redaction check before committing: location-only secret scan clean; no home
paths or project ids in any committed evidence file.

## What this flips, and what it does not

Flips (in this commit): `contracts/product_proof.json`
`mission_paths.gemini-adk-planner.status`, `delivery_gates.live_gemini.status`,
`north_star.status` (partially — the live two-worker leg), and the README
`Live Gemini` row.

Flips (Phase 2/3 commit): `north_star.legs.survives_one_of_them_failing` →
`partially_verified_live`; `mission_capsule.status` → `verified_live_cold`
(live missions, clean checkout); README rows.

Does **not** flip: mission completion after a live recovery, human-attested
approval on a live mission, Docker, Cloud Run/Firestore, benchmark, and
media. Each stays labelled until its own evidence lands.
