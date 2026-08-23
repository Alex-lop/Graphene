# Demo script — four minutes, one sentence

> A change appears, Graphene wakes up, coordinates two real Gemini workers,
> survives one of them dying, and hands over a result that proves why it
> should be trusted.

Every beat below points at footage or evidence that **already exists** from
the 2026-08-23 night run (`local/recordings/` is gitignored; the evidence
directories are committed). Beats marked **RE-CAPTURE** have no clean live
footage yet and should be filmed with the commands shown — they spend money
(≈ $0.25–0.60 per mission at tonight's rates; see `NIGHT_REPORT.md` §3).
Nothing in this script fakes a result: where the live run did not reach a
step, the script says so and shows the rehearsal instead.

Environment for every live beat (owner-private shell, never committed):
`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`,
`GOOGLE_CLOUD_LOCATION=global` (the only location serving `gemini-3.5-flash`
for this project), `GRAPHENE_RUN_LIVE_GEMINI=1`,
`GRAPHENE_CHECK_EXECUTOR=host-sandbox`, a fresh `GRAPHENE_STATE_DIR`
(mode 0700). Materialize a fresh target first:
`uv run --frozen python scripts/materialize_north_star.py ~/demo-target`.

## Beat 0 — the category, literally (0:00–0:25)

*"Watching for a change."* A `mission.yaml` lands in a folder; Graphene is
watching.

```bash
uv run --frozen graphene watch inbox --dir ~/demo-inbox --poll 5      # terminal 1, leave running
sed "s|/ABSOLUTE/PATH/TO/north-star-target|$HOME/demo-target|" \
  demo/north_star/mission.yaml > ~/demo-inbox/mission.yaml            # terminal 2
```

On screen: one JSON line — `"status":"created"`, a mission id, the file's
digest. Then `graphene why` later starts with `STAGE trigger established …
Triggered by inbox_file mission.yaml.` Footage: none yet (**RE-CAPTURE** the
`watch inbox` terminal; the evidence of the live trigger is
`evidence/north_star/2026-08-23-trigger-demo/` — `watch_inbox.out`,
`trigger_event.txt`, and the `why` output whose first stage is the trigger,
from mission `mission_start_a44dcefd7cd8e79e25690611`). Note: `--poll` mode
is the same code path as `--once`; the fixture tests drive `--once`.

## Beat 1 — the plan is typed, validated, and *yours to approve* (0:25–0:55)

```bash
uv run --frozen graphene plan show MISSION_ID
uv run --frozen graphene plan lint MISSION_ID
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1 --confirm-human
```

Show the two independent roots with disjoint write paths and the
integration tail. Say out loud that the watcher can only *create*; a human
(or, tonight, a recorded delegate) approves. Footage:
`local/recordings/mission1-north-star.log` holds the planner output and the
validated plan for the completed mission `mission_start_5291caad50a8ee7a222a9221`
(`evidence/north_star/2026-08-23-mission1/plan_show.txt`). **RE-CAPTURE**
with `--confirm-human` on a real TTY — tonight's approvals were
operator-delegated (`server_derived`), which the evidence states.

## Beat 2 — two real workers, overlapping on three clocks (0:55–1:40)

While `approve-plan` runs, the second terminal:

```bash
uv run --frozen graphene --json mission watch MISSION_ID --after-seq 0 --snapshot
```

Freeze on `parallel_overlap`: `max_window_ms` (store clock),
`provider_call_max_window_ms` (runtime-stamped call window), and
`provider_reported_max_window_ms` (Vertex's own `create_time` → `Date`).
Tonight: 28 491 / 26 463 / 25 364 ms. Footage:
`local/recordings/mission1-north-star.log` (the `overlap:` and `receipt:`
lines), evidence `evidence/north_star/2026-08-23-mission1/approve_plan.json`.

## Beat 3 — one worker dies; the mission doesn't (1:40–2:40)

Second mission; in terminal 2, arm the laboratory *before* approving:

```bash
uv run --frozen python scripts/failure_lab.py auto MISSION_ID2 --timeout 900
```

It prints the kill the moment worker A's publication is accepted and worker
B's registered check is alive: pid, pgid, start time, `SIGKILL`, the
sibling's publication id. Then `mission watch` shows `task.retried` →
`task.leased` with `fencing_token 2` → `artifact.accepted` for the retry.
Footage: `local/recordings/mission4-failure-lab-partial-38129f17.log` (the
kill JSON) and `evidence/north_star/2026-08-23-mission4-failure-lab/`
(`kill.json`, `event_types.txt`, the `-9` receipt cited in
`2026-08-23-north-star-live.md`). **Honesty cut:** on every laboratory
mission tonight the *later* task failed on the model's own output, so the
post-recovery completion is shown only by the deterministic rehearsal
(`uv run --frozen pytest -q tests/unit/orchestration/test_failure_laboratory.py`).
**RE-CAPTURE** until a laboratory mission completes, or narrate the rehearsal
as a rehearsal.

## Beat 4 — `why` (2:40–3:20)

```bash
uv run --frozen graphene why ledger_service/report_markdown.py --mission MISSION_ID2
```

Read the stages top to bottom: `trigger` (if dropped), `target`,
`producer_attempt` (`attempt_number=2 fence=2`), **`prior_attempts`** (the
killed attempt, `state=failed result_code=acceptance_check_failed fence=1`,
both receipts `resolvable=True`), then assembly, verification, approval, and
the closing `TRUST:` line. Footage: `evidence/north_star/
2026-08-23-mission4-failure-lab/why_ledger_service_report_markdown.py.txt`
(stops at the unknown assembly because that mission failed later) and
`evidence/north_star/2026-08-23-mission1/why_ledger_service_cli.py.txt`
(the full chain to approval).

## Beat 5 — the result, and the proof that travels (3:20–4:00)

```bash
uv run --frozen graphene bundle create MISSION_ID --output bundle.json
uv run --frozen graphene mission approve-result MISSION_ID --bundle-id FINAL_RESULT_ID --confirm-human
uv run --frozen graphene mission capsule export MISSION_ID --output ./capsules
git clone <repo> /tmp/verify && cd /tmp/verify && uv sync --frozen && \
  uv run --frozen python -m graphene.orchestration.capsule verify ./capsules/MISSION_ID.graphene-capsule
```

Show `pushed: false`, the isolated `refs/graphene/results/…` commit, the
untouched target (`git status` clean, HEAD still the base), then the cold
verify printing `verified: true` in a directory that has never seen the
mission store. Footage: `evidence/north_star/2026-08-23-mission1/
{approve_result.json,target_status.txt,target_head.txt,cold_verify.json}`.
Cloud consoles: show the Vertex AI request metrics and Cloud Billing for
the project for the same minutes — that is the provider-side receipt of the
receipts (not captured tonight; **RE-CAPTURE**).

## What not to say

- Not "human-attested" for tonight's approvals — they are `server_derived`
  under a recorded delegation; film Beat 1 and Beat 5 with `--confirm-human`
  to make that claim.
- Not "survives and completes" unless a laboratory mission reaches
  `completed`; say "survives, retries under a higher fence, and the
  replacement is accepted" — that is what the evidence shows.
- Not "cold-verified on another machine" — a fresh clone on the same laptop.
