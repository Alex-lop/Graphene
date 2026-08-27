# North Star runbook — Orders recovery proof

This is the runbook for evidence that does **not exist yet**. It is deliberately
ordered so a partial run cannot be described as a completed proof.

## 0. Truth and versions

- Runtime dependency: `google-adk==2.5.0`.
- Requested model: `gemini-3.5-flash`.
- Model/rules source-check date: 2026-08-27.
- Required final status: `completed`, with an isolated local result ref.
- Current live status: no credentialed run, real model-child kill, Codex MCP
  run, or cloud deployment. Exact-SHA package results are run-specific external
  manifests and are not asserted by this checked-in runbook.

Before spending money, re-check the official hackathon eligibility source and
the current Google model catalog. Confirm the exact requested ID, returned
identity behavior, ADK version, access mode, and endpoint. If they cannot be
confirmed, stop only the live claim; credential-free checks remain valid.

Never capture credentials, prompt/source contents, model output, environment
values, or private artifact bytes. Graphene may create an isolated local result
ref only. It must not push, merge, deploy, open a PR, or mutate the target's
current branch, index, worktree, remotes, tags, or settings.

## 1. Establish an exact implementation artifact

Start from the intended committed revision in a clean clone:

```bash
sha="$(git rev-parse HEAD)"
python scripts/reliability/exact_sha_proof.py \
  --expected-sha "$sha" \
  --remote-ref origin/BRANCH \
  --require-clean \
  --output-root /absolute/path/outside/the/checkout
```

Replace `BRANCH` with the pushed branch containing `sha`. Preserve the
SHA-named manifest and its referenced JSON artifacts. The driver refuses a
dirty checkout, a different local revision, a noncanonical origin, or a remote
branch whose tip differs. It also requires both separately installed artifacts
to pass outside the checkout with source-path overrides removed.

## 2. Materialize the Orders target

```bash
runtime="$(mktemp -d)"
chmod 700 "$runtime"
uv run --frozen python scripts/materialize_north_star.py "$runtime/orders-api"
```

The materializer creates a fresh Git repository with the legacy Pydantic API,
immutable tests, and a policy derived from
[`demo/north_star/policy.template.json`](../demo/north_star/policy.template.json).
The mission is:

> Migrate the Orders API from Pydantic's v1 compatibility APIs to native
> Pydantic v2 and freeze its dependency declarations while preserving its
> exact public behavior.

The exact criteria are in
[`demo/north_star/goal.json`](../demo/north_star/goal.json). The allowed writes
are only:

- `orders_api/request_models.py`
- `orders_api/api.py`
- `orders_api/response_models.py`
- `requirements.in`
- `requirements.lock`

The policy denies network access, caps concurrency at two, permits only the
Pytest-free task-local `orders-migration-task-check` and strict final
`orders-migration-check` templates, sets `policy_pre_authorized`, and permits
only `auto_finalize_isolated`.

Record the target base SHA and confirm its worktree is clean before the goal.

## 3. Preflight credentials without making proof claims

Configure exactly one supported credential mode and the selected sandbox. Do
not paste values into evidence.

```bash
export GRAPHENE_RUN_LIVE_GEMINI=1
export GRAPHENE_CHECK_EXECUTOR=host-sandbox  # supported macOS path
uv run --frozen graphene doctor --repo "$runtime/orders-api" --json
```

Doctor proves local configuration only. It does not contact the provider and
does not establish model eligibility, connectivity, or returned identity.
Missing or conflicting credentials must fail closed; there is no fixture
fallback for `gemini-adk`.

## 4. Start through the real MCP surface

Use a fresh `GRAPHENE_STATE_DIR` with mode `0700`. Launch the same installed
`graphene-mcp` entry point verified in section 1, then connect the intended
Codex client. This Codex step is mandatory for the final proof; substituting a
Python MCP client proves protocol behavior only.

Call `start_goal` with:

- `repo`: the absolute Orders target path;
- `goal` and `success_criteria_json`: the exact values from `goal.json`;
- `request_id`: a stable unique idempotency key;
- `driver`: `gemini-adk`;
- `max_workers`: `2`;
- `authorization_mode`: `policy_pre_authorized`; and
- `finalization_mode`: `auto_finalize_isolated`.

The call must return within five seconds after durable acceptance, before model
planning or worker completion. Its response binds the request id, target base
SHA, project-policy revision/digest, driver, authorization request, and
finalization request. A requested mode is not approval.

Disconnect the initiating Codex/MCP process after acceptance. Record that it
has exited. Do not cancel or restart the goal.

## 5. Reattach and verify authorization

Start a fresh Codex/MCP connection and poll `mission_status` using the returned
mission id. The detached supervisor must remain the only live owner or recover
under a higher supervisor generation.

Before work dispatches, Graphene must compile the model proposal, validate it
against the exact policy/base revision, and record a policy-authoritative plan
decision. If the plan exceeds policy it must enter `review_required`; do not
override that result for the demo. MCP `approve_plan` is the optional review
path and records `server_derived` relay truth, not human attestation.

Capture only bounded status fields: supervisor phase/generation, mission
status, plan revision/digest, policy decision digest, task states, head, and
legal next actions.

## 6. Kill one real model child

The live worker launches one private `python -I -m
graphene.orchestration.workers.gemini_child` process per model attempt. It has
no repository API. The parent sends one canonical length-framed request and
the child durably acknowledges provider dispatch before it can become a kill
target.

Run the unattended laboratory while the mission is active:

```bash
uv run --frozen python scripts/failure_lab.py auto MISSION_ID --actor-label demo-operator --timeout 900
```

`auto` waits until one work publication is already accepted and a different
worker has a live, fence-bound, barrier-acknowledged model child. It then sends
`SIGKILL` only through the owned-process registry's exact
pid/process-group/start-time identity. It never kills by process name.

Exit 0 is required. Exit 2 is a refusal and exit 3 means no valid kill
opportunity occurred; neither proves failure recovery.

Preserve the sanitized JSON: mission/task/attempt/worker, fence, pid/pgid,
process start time, request digest, SDK invocation id, provider-dispatch time,
and the accepted sibling publication id. Do not preserve prompts or responses.

## 7. Require selective recovery and completion

Continue polling from the fresh controller. All of these must be true:

1. the killed attempt ends retryable with `provider_interrupted`;
2. its provider outcome is unknown but its repository effect is known absent;
3. the sibling accepted publication is byte-for-byte unchanged;
4. no downstream assembly/verification uses the interrupted attempt;
5. only the interrupted work is retried, with a strictly higher fence and a
   bounded prior-failure diagnostic;
6. the stale fence cannot publish or complete;
7. assembly consumes accepted publications only;
8. verification binds the exact candidate and final bundle;
9. policy-authorized finalization creates only an isolated local result ref;
10. mission status becomes `completed`, all tasks are done, and the supplied
    checkout remains unchanged.

Call `mission_summary`. Call `why` for at least one file from the preserved
sibling and one file from the retry. The retry path must name both attempts and
identify the higher-fence attempt as producer.

## 8. Cold evidence and working change

Run the immutable Orders suite from the isolated result, not the input
checkout. Demonstrate the migrated API's public behavior. Export a mission
capsule and verify it from a fresh process with no mission store:

```bash
graphene mission capsule export MISSION_ID --output "$runtime/capsules"
graphene mission capsule verify "$runtime/capsules/MISSION_ID.graphene-capsule"
```

Capsule verification proves internal digest/chain consistency, not producer
authenticity, provider truth, or host-clock accuracy. Bind the capsule head to
the separately recorded mission head.

## 9. Proof flip checklist

Do not change `NOT PROVEN` until one evidence set contains:

- clean implementation SHA and wheel/sdist hashes;
- exact installed entry point and outside-tree execution environment;
- Codex acceptance latency and initiating-controller exit;
- fresh-client reattachment and supervisor generation/identity;
- policy decision and exact plan/base/policy bindings;
- returned Gemini identity and evidence-bound provider receipts;
- exact real child-kill record and preserved sibling publication;
- higher-fence retry and stale-fence refusal;
- exact candidate/final-bundle/result-ref bindings;
- `completed`, summary, two `why` paths, passing Orders behavior, and unchanged
  target checkout; and
- explicit negatives: no push, merge, PR, deployment, cloud claim, or human
  attestation.

Cloud Run/real Firestore is a separate, still-unproven workstream. A local
Firestore emulator run or a live Gemini run does not flip the cloud row.
