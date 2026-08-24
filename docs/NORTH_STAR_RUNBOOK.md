# North Star runbook

Status (2026-08-23): **RUN LIVE — sections 1–3 and 5 proven, section 4
partially.** The evidence, what flipped, and what did not are in
[`evidence/north_star/2026-08-23-north-star-live.md`](../evidence/north_star/2026-08-23-north-star-live.md)
and `NIGHT_REPORT.md`. Running it surfaced these corrections to the text
below, which is otherwise kept as the procedure:

- Vertex AI serves `gemini-3.5-flash` to this project only with
  `GOOGLE_CLOUD_LOCATION=global` (the regional endpoints return 404); the
  Vertex checklist in 0.2 is therefore `GOOGLE_GENAI_USE_VERTEXAI=true`,
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, valid ADC.
- 3.3: `mission result show` does not print the bundle id; the pending
  `FinalResultBundleV2` is registered and printed by
  `graphene --json bundle create MISSION_ID --output FILE`, whose `bundle_id`
  feeds `approve-result --bundle-id`.
- 1.2: `git status --porcelain` shows the materializer's own untracked
  `.graphene/`; "untouched" means HEAD still equals the base commit and no
  other status line appears.
- `mission start` is idempotent on goal, criteria, and repository; to run the
  same goal again pass `--command-id` (the capture driver used
  `night_run_<dir>_<timestamp>`), or drop a file on `graphene watch inbox`,
  which derives the id from the file's digest.
- The planner needs the explicit rules it now carries (two independent
  roots, no shared `write_paths`, each task passes the suite alone) and the
  demo policy needs `max_attempts` 16; without them the first live plans were
  rejected or could not cover their attempt budget.
- Approvals in an unattended session are `server_derived` with an operator
  label and rationale; `--confirm-human` needs a real TTY and has **not**
  been exercised live.

This is the exact, ordered sequence for the credentialed session that turns
the North Star sentence into evidence:

> Graphene coordinates two real Gemini coding workers, survives one of them
> failing, and proves exactly why the final repository result should be trusted.

Every step names the command, what a pass proves, and what to capture. Capture
only sanitized values (identifiers, digests, counts, status words, the last
line of a test run). Never capture API keys, prompts, worker output, command
output, source bytes, diffs, environment values, or absolute home paths.

Nothing in [`contracts/product_proof.json`](../contracts/product_proof.json) or
the [README proof table](../README.md) flips until section 6 is complete, and
the flip lands **in the same commit** as the captured evidence file.

Companion documents: [Agent runtime](AGENT_RUNTIME.md) (receipts, check
executors, failure laboratory), [Cloud proof plan](CLOUD_PROOF_PLAN.md) (the
separate Cloud Run + Firestore vertical), [Alex cloud setup](ALEX_CLOUD_SETUP.md).

---

## 0. Preconditions

Run everything from the Graphene repository root on macOS. Keep one terminal
for the mission and a second terminal for watching and for the failure
laboratory. For a long session keep the machine awake in a third terminal:

```bash
caffeinate -dims
```

### 0.1 Toolchain

```bash
uv lock --check
uv sync --frozen
uv run --frozen graphene --help
```

Proves: the locked environment resolves and the CLI imports. Capture: nothing.

### 0.1a Known live-contact fixes and quota limits

The Gemini Developer API's `response_schema` field has no `anyOf` support at
all (the model call fails closed with an undetailed `400 INVALID_ARGUMENT`),
and `generate_content_config.response_json_schema` failed identically in
testing despite the SDK documenting full JSON Schema support there. Graphene
no longer asks the API to enforce a schema for the planner or worker
structured output: it embeds the JSON Schema as a prompt instruction instead
(`response_mime_type="application/json"` plus a `describe_output_schema(...)`
block in the agent instruction) and keeps the same strict
`model_validate_json` parse of the returned text as the actual contract; a
malformed response still fails closed with `PlannerOutputError`. This landed
with the full fake-model regression suite green and one confirmed live pass
(see below).

**Free-tier daily quota:** the `gemini-3.5-flash` free tier caps at **20
`generateContent` requests per project per day**
(`generativelanguage.googleapis.com/generate_content_free_tier_requests`,
quota id `GenerateRequestsPerDayPerProjectPerModel-FreeTier`). This is a
*daily* cap, not a short rate window — a `429 RESOURCE_EXHAUSTED` naming this
quota will not clear by waiting a few minutes. One live mission run alone can
spend most of a day's quota (one planner call plus at least one call per
worker). Debugging schema issues against the live API burns quota fast; do it
sparingly and read the error body's `quotaId` before assuming a short
rate-limit and retrying. To avoid the daily cap entirely, switch to Vertex AI
billing (`GOOGLE_GENAI_USE_VERTEXAI=true` with `GOOGLE_CLOUD_PROJECT`,
`GOOGLE_CLOUD_LOCATION`, and valid ADC) against a GCP project with billing
enabled — for example the project used for [the cloud proof
plan](CLOUD_PROOF_PLAN.md), spending the project's Cloud credits instead of
the AI Studio free-tier allowance.

### 0.2 Environment (owner-private shell, never a committed file)

Set exactly these; leave every other Graphene variable unset for this run.

```bash
# Exactly ONE of the two API keys. Two set keys, or zero, fails closed.
export GEMINI_API_KEY='…'          # or: export GOOGLE_API_KEY='…'
unset GOOGLE_GENAI_USE_VERTEXAI    # gemini_api mode; vertex mode is a different checklist

# Live gate for the paid pytest run in section 2 (not needed for the CLI mission).
export GRAPHENE_RUN_LIVE_GEMINI=1

# fixture-tests checks on the gemini-adk path: host sandbox, owned-process registered.
export GRAPHENE_CHECK_EXECUTOR=host-sandbox

# Optional but recommended: a fresh, absolute, symlink-free state directory so the
# proof mission store is isolated from every earlier local mission.
export GRAPHENE_STATE_DIR="$HOME/.graphene/north-star-state"
```

`GRAPHENE_CHECK_EXECUTOR` accepts only `docker` (default) or `host-sandbox`;
anything else fails closed before a worker runs with
`GRAPHENE_CHECK_EXECUTOR must be docker or host-sandbox`. The Docker
alternative needs a responsive daemon and the built immutable image
(`docker build -f docker/executor.Dockerfile -t graphene-executor:py313-pytest .`);
it is **NOT PROVEN** and is not the path this runbook takes.

`host-sandbox` is what makes section 4 possible: the check subprocess of every
attempt runs under `/usr/bin/sandbox-exec` as a registered Graphene-owned
process group, so the failure laboratory can SIGKILL a strongly identified
process instead of guessing by name.

### 0.3 `graphene doctor` expectations

`doctor` needs a repository with a policy, so its first real run is step 1.3.
When you run it, read these fields and stop if any differ:

| Field | Expected |
|---|---|
| `gemini_preflight.configuration_ready` | `true` |
| `gemini_preflight.connectivity_proven` / `live_provider_proven` | `false` — doctor never calls the provider; this is local configuration only |
| `executables.git`, `executables.python`, `executables.sandbox-exec` | all `true` |
| `check_executor` | `{"requested": "host-sandbox", "supported": true, "reason": "macOS sandbox-exec fixture boundary with owned-process registration"}` |
| `policy.status` | `"usable"` |
| `platform_isolation.status` | `"usable"` |
| `modes.gemini-adk.usable` / `.configured` / `.credential_mode` | `true` / `true` / `"gemini_api"` |
| `modes.firestore-cloud.usable` | `false` (unchanged; the cloud vertical is a separate plan) |

`doctor` never echoes an unrecognised `GRAPHENE_CHECK_EXECUTOR` value and never
prints a credential; its JSON is safe to capture whole.

---

## 1. Materialize the target

The North Star target is the `ledger_service` package in
`demo/north_star/repository`; the goal and four success criteria live in
[`demo/north_star/GOAL.md`](../demo/north_star/GOAL.md) and its machine twin
`goal.json`. The materializer copies the tree to a new directory, commits a
base, writes the policy, proves the policy loads the way `graphene mission
start` loads it, runs the target's own suite once, and prints the next
commands. `DEST` must not exist.

### 1.1 Materialize

```bash
export DEST="$HOME/north-star-target"        # any new path; absolute, no symlinks
uv run --frozen python scripts/materialize_north_star.py "$DEST"
```

Proves: the copy, `git init -b main` plus base commit, a `.graphene/project.json`
(mode 0600, canonical JSON) whose **only** command template is the frozen
fixed test command `python -m pytest -q -p no:cacheprovider` as
`fixture-tests` with a 60 s timeout, that `_load_project_policy` accepts it
unchanged, and that the target suite passes in the adapter's sanitized
environment. The script stops at the first failure with exit status 1 and
deletes nothing.

It prints exactly this shape (the three commands are the ones you run next;
the script prints `DEST` as the absolute path):

```text
North Star target materialized at DEST
  base commit: <40-hex sha>
  policy: DEST/.graphene/project.json (<policy_id>)
  target tests: <last line of the target's pytest run>
Next commands (run from the Graphene repository):
  uv run --frozen graphene doctor --repo DEST
  uv run --frozen graphene mission start --repo DEST --goal 'Add a redacted JSON status report and a Markdown status report to the ledger CLI; both must pass the existing suite plus new tests.' --success-criterion 'Running ledger_service with report --format json prints one JSON object whose per-item quantities equal the balances command and whose notes have passed through the redaction policy.' --success-criterion 'Running ledger_service with report --format markdown prints a Markdown table with a header row and exactly one row per item, escaping pipe characters inside cells.' --success-criterion 'The existing tests and the new report tests all pass under python -m pytest -q -p no:cacheprovider.' --success-criterion 'No file outside ledger_service/ and tests/ is created or modified.' --driver gemini-adk --max-workers 2
  uv run --frozen graphene mission approve-plan MISSION_ID --revision 1 --confirm-human
```

Capture: the `policy:` line's policy id and the `target tests:` summary line.
The base commit sha is a throwaway repository's sha; record it in the private
evidence notes only.

### 1.2 Confirm the target is clean and the policy is narrow

```bash
git -C "$DEST" status --porcelain=v1          # must print nothing
git -C "$DEST" rev-parse --abbrev-ref HEAD    # main
cat "$DEST/.graphene/project.json"
```

Expected policy facts (from `demo/north_star/policy.template.json`): write
scope `ledger_service/**` and `tests/**`; `network.mode` `deny`;
`max_concurrency` 2; `retry_limit` 1 (so every task gets at most two
attempts, which section 4 relies on); `risk_gates` `final-result`, `network`,
`scope-expansion`; `.graphene/**` and `.git/**` excluded.

### 1.3 Doctor against the target

```bash
uv run --frozen graphene --json doctor --repo "$DEST"
```

Proves: the table in 0.3. Capture: the whole JSON (it is sanitized by design).

---

## 2. Gated live test (paid, ~minutes)

```bash
GRAPHENE_RUN_LIVE_GEMINI=1 uv run --frozen pytest -q tests/process/test_gemini_live.py -p no:cacheprovider
```

The test skips with `NOT PROVEN: set GRAPHENE_RUN_LIVE_GEMINI=1 with one valid
Gemini credential mode …` unless the gate and exactly one credential mode are
set; there is no fake fallback. It builds its own disposable repository with
the `graphene init` default policy (whose only template is `git diff --check
--`), so `GRAPHENE_CHECK_EXECUTOR` and Docker do not affect it, and it uses a
temporary `GRAPHENE_STATE_DIR`, so its mission store disappears afterwards.

What [`tests/process/test_gemini_live.py`](../tests/process/test_gemini_live.py)
asserts now, in order:

1. Proposal: `status == "proposed"`, `review_required`, `requested_model` is
   the live model id, a non-empty `returned_model`, at least two `work` tasks.
2. One explicit plan approval (`truth_kind` server-derived inside pytest; the
   human attestation happens in section 3, not here) runs the mission to
   `awaiting_result` with `execution_mode == "gemini_live"`.
3. Receipts: at least two `worker_session_ids`, `worker_invocation_ids`, and
   `provider_receipts`; every receipt has `driver == "gemini_live"`, the
   requested and a returned model, `input_bytes > 0`, `output_bytes > 0`,
   `usage_source` in `{provider_reported, unavailable}`, and **no** `prompt`
   or `output` key.
4. Overlap: `parallel_overlap_observed is True`, `parallel_overlap.max_window_ms > 0`,
   `provider_call_overlap_observed is True`,
   `parallel_overlap.provider_call_max_window_ms > 0`, and all three bases
   `attempt_timestamps`, `lease_timestamps`, and `provider_call_timestamps`
   appear. Only the provider-call basis measures concurrent model calls; the
   other two measure simultaneous leases on the store clock.
5. Evidence binding: `receipt_unknowns == []`; every
   `provider_receipt_references` entry has kind `worker-provider-receipt`,
   resolves from the evidence store, its bytes hash to the cited `sha256`, and
   parses as a `WorkerProviderReceipt` with `driver == "gemini_live"`.
6. Authority: `store.verify(mission_id) == store.head(mission_id)`; every
   committed `work` attempt carries exactly one `worker-provider-receipt`
   reference; the two work attempts have distinct worker, session,
   invocation, workspace, attempt, and lease identities and distinct
   `(lease_id, fencing_token)` pairs; their `[started_at, ended_at]` windows
   overlap.
7. Fan-in: the committed assembly attempt consumed at least two publications,
   verification consumed exactly one; the mission is `awaiting_result` with
   `final_outcome None`.
8. Sovereignty: the source checkout's `git status`, `HEAD`, symbolic ref,
   remote refs, and README bytes are unchanged.

Capture: only pytest's final summary line (count, outcome word, duration). If it
fails, capture the assertion name and the public `result_code`; never the
traceback body if it contains provider text.

---

## 3. The North Star mission

### 3.1 Start (proposal only; nothing executes yet)

Paste the exact `graphene mission start …` command the materializer printed in
step 1.1 (add `--json` after `graphene` to receive JSON):

```bash
uv run --frozen graphene --json mission start --repo "$DEST" \
  --goal 'Add a redacted JSON status report and a Markdown status report to the ledger CLI; both must pass the existing suite plus new tests.' \
  --success-criterion 'Running ledger_service with report --format json prints one JSON object whose per-item quantities equal the balances command and whose notes have passed through the redaction policy.' \
  --success-criterion 'Running ledger_service with report --format markdown prints a Markdown table with a header row and exactly one row per item, escaping pipe characters inside cells.' \
  --success-criterion 'The existing tests and the new report tests all pass under python -m pytest -q -p no:cacheprovider.' \
  --success-criterion 'No file outside ledger_service/ and tests/ is created or modified.' \
  --driver gemini-adk --max-workers 2
export MISSION_ID='<mission id printed above>'
```

Proves: live Gemini returned a typed plan intent that deterministic validation
compiled into an immutable proposed DAG (`status: proposed`,
`review_required: true`, `requested_model`, `returned_model`, `task_graph`).
Missing or doubled credentials fail closed here with no fixture fallback.

Review before approving — the planner is live, so the plan is not scripted:

```bash
uv run --frozen graphene plan show "$MISSION_ID"
uv run --frozen graphene plan lint "$MISSION_ID"
```

Compare with the "Expected plan shape" in
[`GOAL.md`](../demo/north_star/GOAL.md): two parallel `work` tasks with
disjoint write paths (JSON renderer, Markdown renderer), an integration tail,
and a `fixture-tests` verification. If the plan does not have two independent
work tasks, reject it by not approving; start again (the proposal is durable
and harmless).

Capture: `mission_id`, `returned_model`, and the task graph as printed by
`plan show` (task ids, kinds, dependencies, write paths).

### 3.2 Approve the plan with a real TTY — this runs the whole mission

```bash
uv run --frozen graphene mission approve-plan "$MISSION_ID" --revision 1 --confirm-human
```

`--confirm-human` is refused unless **both** stdin and stdout are a terminal
(`--confirm-human requires an authenticated local interactive terminal`), and
it binds the operator label to a hash of the local OS principal. This command
blocks: it commits `plan.approved` (human attested) and then executes the
mission in-process — two live Gemini workers in Graphene-owned workspaces,
each attempt's `fixture-tests` check under `host-sandbox`, assembly of the
accepted V2 publications, exact verification, and the registered pending
`FinalResultBundleV2` — returning when the mission reaches
`awaiting_result`. If the process is interrupted while the mission is still
`running`, re-running the identical `approve-plan` command resumes execution;
nothing is repeated without a receipt.

Watch from the second terminal while it runs:

```bash
uv run --frozen graphene --json mission watch "$MISSION_ID" --after-seq 0 --snapshot
uv run --frozen graphene mission status "$MISSION_ID"
uv run --frozen graphene mission open "$MISSION_ID"     # optional local Mission Control
```

Proves, from the returned JSON: `status: awaiting_result`,
`execution_mode: gemini_live`, `attempt_count`, `dispatch_batches`,
`worker_session_ids` and `worker_invocation_ids` (two each),
`provider_receipts` (sanitized), `provider_receipt_references` (one per work
attempt, each citing kind/id/sha256), `receipt_unknowns: []`,
`parallel_overlap` with `max_window_ms > 0` and both bases,
`parallel_overlap_observed: true`, `review_required: true`,
`checkout_mutated: false`.

Capture: that JSON minus nothing — it contains identifiers, digests, counts,
and model names only. Also capture the `watch` tail's event types in order
(`task.leased`, `task.started`, `artifact.published`, `artifact.accepted`,
`assembly.completed`, `verification.completed`, `final_result_bundle.ready`).

### 3.3 Inspect the verified candidate

```bash
uv run --frozen graphene --json mission result show "$MISSION_ID"
export FINAL_RESULT_ID='<bundle_id printed above>'
```

Proves: the exact pending bundle is registered and verified against the
mission head; `approval_binding` is `bundle_id`; the candidate tree digest is
the one the trusted check runner attested; the changed paths are inside
`ledger_service/` and `tests/`. Capture: `bundle_id`, `bundle_sha256`, the
candidate tree sha256, and the changed-path list.

Optional review without touching the checkout:

```bash
uv run --frozen graphene mission result export "$MISSION_ID" \
  --candidate-sha <candidate sha256 from result show> --output "$HOME/north-star-candidate.patch"
git -C "$DEST" apply --check "$HOME/north-star-candidate.patch"   # checks only; applies nothing
```

### 3.4 Approve the exact bundle (TTY)

```bash
uv run --frozen graphene mission approve-result "$MISSION_ID" --bundle-id "$FINAL_RESULT_ID" --confirm-human
uv run --frozen graphene mission status "$MISSION_ID"
git -C "$DEST" status --porcelain=v1        # still nothing
git -C "$DEST" rev-parse HEAD               # still the base commit from step 1.1
```

Proves: the decision binds the displayed bundle id (a stale or mistyped id is
refused), `final_candidate.approved` and `isolated_commit.created` are
committed, the result commit exists only in the Graphene-owned remoteless
result repository, and `DEST` is byte-for-byte untouched. Capture: the
mission's final status, the isolated result reference printed by the command,
and the two `git` lines.

### 3.5 Ask why

Pick one changed path from step 3.3 (for example the JSON renderer the plan
created):

```bash
uv run --frozen graphene why ledger_service/report_json.py --mission "$MISSION_ID"
uv run --frozen graphene why ledger_service/report_json.py --mission "$MISSION_ID" --json
```

Proves: a first line `WHY <mission_id> <query> matched_by=…`, one `STAGE
<stage> <status>` block per causal link (producer attempt with `worker=`,
`attempt_number=`, `fence=`; `receipt test-receipt … resolvable=True`;
`receipt worker-provider-receipt … resolvable=True`; publication; assembly;
verification; approval), `UNKNOWN` lines for anything not established, and
the closing `TRUST:` line. The JSON form is canonical and carries the same
`links`, `unknowns`, and per-node `worker_id` / `fencing_token` /
`attempt_number`. Capture: both outputs (identifiers and digests only).

---

## 4. Failure laboratory on a second mission

Everything here is the sequence in the directive's A2, steps 1–6, driven by
[`scripts/failure_lab.py`](../scripts/failure_lab.py) (run
`uv run --frozen python scripts/failure_lab.py --help` for the exact flags).
On the `gemini-adk` path workers run in-process; the strongly identified
Graphene-owned process is the attempt's check subprocess, which exists only
while `host-sandbox` runs `fixture-tests` for that attempt. The kill goes
through `OwnedProcessRegistry.signal` — the same identity-checked path
`graphene mission cancel` uses — and refuses when the record belongs to
another mission or the attempt has no live lease. Nothing is killed by name.

### 4.1 Materialize and start a second target

```bash
export DEST2="$HOME/north-star-target-2"
uv run --frozen python scripts/materialize_north_star.py "$DEST2"
# paste the printed `graphene mission start` command for DEST2, then:
export MISSION_ID2='<second mission id>'
uv run --frozen graphene plan show "$MISSION_ID2"      # again: two independent work tasks
```

### 4.2 Terminal 1: approve (blocks and runs)

```bash
uv run --frozen graphene mission approve-plan "$MISSION_ID2" --revision 1 --confirm-human
```

### 4.3 Terminal 2: wait for worker B's check, then kill it

Worker ids on this path are `gemini-worker-1` and `gemini-worker-2`. "A" is
the worker whose publication gets accepted first; "B" is the other one. The
check subprocess exists for a few seconds per attempt, so poll:

```bash
until uv run --frozen python scripts/failure_lab.py list "$MISSION_ID2" | grep -q '"worker_id": "gemini-worker-2"'; do sleep 0.5; done
uv run --frozen python scripts/failure_lab.py list "$MISSION_ID2"
```

`list` prints one object per owned-process record: `attempt_id`,
`worker_id`, `pid`, `pgid`, `started_at`, and the observed executable
(`/usr/bin/sandbox-exec`). Confirm in `graphene mission watch` that A's
`artifact.accepted` has already been committed (if it has not, let this check
finish and catch B's retry instead, or re-run the laboratory; the point is
"kill B while A's publication is already accepted"). Then:

```bash
uv run --frozen python scripts/failure_lab.py kill "$MISSION_ID2" --attempt <attempt_id of gemini-worker-2>
```

`kill` prints exactly what it signalled (mission, attempt, worker, pid, pgid)
and exits 2 if it refused. Capture: the `list` output and the `kill` output.

`sandbox-exec` replaces its own image with the frozen command right after
spawn (same pid, pgid, and start time; `ps comm` changes from
`/usr/bin/sandbox-exec` to the interpreter). The registry binds identity to
pid, process group, and start time and accepts that documented in-place exec
for the recorded wrapper only, so `list` and `kill` act on the exec'd check
group; the deterministic regression in
[Agent runtime](AGENT_RUNTIME.md#failure-laboratory) drives this exact
`kill` against fake ADK workers. If `kill` exits 2, it refused for a stated
reason (no record, foreign mission, no live lease) — read the reason; never
fall back to killing by name. The live run of this sequence with real Gemini
workers stays **NOT PROVEN** until captured.

### 4.4 Expected observable sequence (directive steps 1–6)

Read it from `graphene --json mission watch "$MISSION_ID2" --after-seq 0` and
`graphene mission status "$MISSION_ID2"`; every step is a committed event:

1. B's check subprocess dies while B holds a live lease; the trusted
   `test-receipt` minted by the check runner records `exit_code -9` with
   `acceptance_check_failed`, the attempt ends `failed`, its lease is released
   with reason `failed`, and **no** `artifact.published` exists for that
   attempt.
2. A's `artifact.published` / `artifact.accepted` events and publication row
   are unchanged — same publication id and digests before and after.
3. The assembly task stays blocked (`task.blocked` / no `assembly.started`)
   until B's task has an accepted publication; nothing downstream fabricates
   progress.
4. Bounded recovery is automatic within policy: because the failure is
   retryable and `retry_limit` is 1, the store commits `task.retried` with a
   `retry_at`, and the scheduler dispatches B's task again as
   `attempt_number == 2` with a **strictly higher** `fencing_token`. The stale
   fence cannot publish (the deterministic regression drives
   `store.assert_fence` with the old dispatch and expects the stale-fence
   conflict). `graphene mission retry MISSION_ID --task TASK_ID --confirm-human`
   is the explicit operator path only if the task ends `failed` (retry budget
   exhausted or a non-retryable code); after it, re-run the identical
   `approve-plan` command from 4.2 to resume execution if the runner has
   returned.
5. The mission reaches `awaiting_result`; `approve-plan` returns; exact
   verification passed on the assembled candidate; the pending bundle is
   registered. Then `result show` → `approve-result --bundle-id … --confirm-human`
   exactly as in 3.3–3.4.
6. `graphene why` for a file from A and for a file from B's retry each show
   the unbroken chain, and B's history contains both attempts:

```bash
uv run --frozen graphene why <path produced by A> --mission "$MISSION_ID2" --json
uv run --frozen graphene why <path produced by B's retry> --mission "$MISSION_ID2" --json
uv run --frozen graphene mission db verify
```

Capture: the two `why` JSON outputs; from `mission status`, B's task id, both
attempt ids with `attempt_number` 1 (failed) and 2 (committed) and their
fencing tokens; A's publication id; the ordered event types. `mission db
verify` must report every mission verified.

The credential-free twin of this choreography lives in
`tests/unit/orchestration/test_failure_laboratory.py` (darwin-gated, fake ADK
workers); the live run is what flips the label, the test is what keeps it.

---

## 5. Mission Capsule (cold verification)

Export the failure-laboratory mission (and the first mission if you like):

```bash
mkdir -p "$HOME/north-star-capsules"
uv run --frozen graphene --json mission capsule export "$MISSION_ID2" --output "$HOME/north-star-capsules"
uv run --frozen graphene --json mission capsule verify "$HOME/north-star-capsules/$MISSION_ID2.graphene-capsule"
```

Export writes `<output>/<mission_id>.graphene-capsule/` (directory 0700, files
0600, refuses to overwrite) holding `manifest.json`, `events.ndjson`,
`plan/revision-<n>.json`, `attempts/<attempt_id>.ndjson`,
`receipts/<reference_id>.json` (only `test-receipt` and
`worker-provider-receipt` bytes), `envelopes.json`, `final-bundle.json`,
`tree-manifest.json`, `overlap.json`, `unknowns.json`, and `VERIFY.md`. The
manifest states the redaction note, `excluded_artifact_kinds` with counts,
`not_verifiable_offline`, and the authority note "SQLite mission store was the
execution authority for this mission."

Then from a **clean checkout on another machine or a fresh clone**, with no
mission database present:

```bash
git clone <repository> graphene-verify && cd graphene-verify
uv sync --frozen
uv run --frozen python -m graphene.orchestration.capsule verify /path/to/<mission_id>.graphene-capsule
```

Proves (exit 0, `"verified": true`): manifest file digests; the mission event
chain (contiguous seq, payload and event digests, previous-hash linkage, head
equals the manifest); every attempt evidence chain; every receipt reference
resolves to a file with the cited sha256 and every `test-receipt` equals the
`check.completed` payload the check runner minted; the final bundle's
`bundle_sha256`, event-head binding, and candidate tree digest against the
verification receipt; envelope digests against `artifact.published` /
`artifact.accepted`; plan revision digests. `not_checked` lists what cannot be
verified offline (candidate tree against artifact bytes, Gemini provider-side
identity, host clock). Capture: the verify JSON and
`shasum -a 256 manifest.json`.

---

## 6. What to record for the proof flip

Write one evidence file, `evidence/checkpoints/<date>-north-star-live.md`,
containing only:

- Graphene source commit the session ran on (short sha is fine) and the
  `uv lock --check` result.
- `doctor` JSON from 1.3.
- Section 2: the pytest summary line.
- Mission 1 and mission 2: `mission_id`; head `{seq, event_sha256}` from
  `mission status`; `returned_model`; counts of worker sessions and
  invocations; `parallel_overlap.provider_call_max_window_ms` (the measured
  provider-call overlap the claim cites) alongside
  `parallel_overlap.max_window_ms` and the set of bases;
  `receipt_unknowns` (must be `[]`).
- Sanitized receipt fingerprints: for every `provider_receipt_references`
  entry, `attempt_id`, `worker_id`, `id`, and `sha256` — that sha256 is the
  digest of the `worker-provider-receipt` artifact bytes and equals
  `shasum -a 256 receipts/<id>.json` inside the capsule. Do not paste the
  receipt bodies into public docs; the digests cite them.
- Mission 2 failure-laboratory facts: B's task id, attempt ids and fencing
  tokens for attempts 1 and 2, A's publication id, the `kill` output, the
  ordered event types.
- `bundle_id`, `bundle_sha256`, candidate tree sha256, the isolated result
  reference, and the two `git -C "$DEST" …` lines proving the checkout is
  untouched, for both missions.
- Capsule: `manifest_sha256` from export, the cold `verify` JSON from the
  clean checkout, and the machine/clone it ran on (hostname-free description).
- `mission db verify` result.

Then, **in that same commit**: set
`contracts/product_proof.json` → `mission_paths.gemini-adk-planner.status`
and `delivery_gates.live_gemini.status` to the repository's honest verified
label with the mission ids and receipt digests cited, and change the README
proof-table row `Live Gemini` accordingly; add a row or note for the failure
laboratory and the capsule with the same citations. A label never flips in a
commit that does not carry the evidence it cites, and a partial run flips
nothing.

---

## 7. NOT PROVEN until then

Until section 6 lands, every one of these stays labelled exactly as it is
today:

- Live Gemini two-worker mission: **NO LONGER PENDING.** This ran on
  2026-08-23 with returned model/session/invocation receipts and measured
  overlap, and was rehearsed 3/3 on 2026-08-24. The rest of this section still
  applies to everything below it.
- Live failure laboratory: only the credential-free fake-ADK regression
  exists; no live run has exhibited steps 1–6, and `scripts/failure_lab.py
  kill` against a live host-sandbox check is itself unproven because the
  registry's exact-executable liveness re-check refuses a check that has
  exec'd in place (see section 4.3).
- Capsule of a live run verified cold by a third party from a clean checkout:
  capsule export and verification are tested on deterministic missions only.
- Human-attested plan and result approval on a live mission: the TTY
  attestation path is tested; no live attested decision has been recorded.
- Docker executor (`NOT PROVEN — RESPONSIVE DAEMON AND BUILT IMMUTABLE IMAGE
  REQUIRED`): this runbook deliberately uses `host-sandbox` instead.
- Cloud Run + real Firestore (`NOT DEPLOYED — NOT PROVEN`): see the
  [Cloud proof plan](CLOUD_PROOF_PLAN.md); it is a separate vertical under a
  separate authority and does not flip with this runbook.
- Graph-economics benchmark, four-minute video, and product media: untouched
  by this runbook.
