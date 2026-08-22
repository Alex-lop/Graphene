# Cloud proof plan

Status: **NOT DEPLOYED — NOT PROVEN**. This document chooses and labels the
architecture for the hackathon's Cloud Run + real Firestore requirement, lists
the minimal owner checklist, and states what evidence flips the label. Nothing
here has been run. Owner actions, billing, IAM, and cleanup detail stay in
[Alex cloud setup](ALEX_CLOUD_SETUP.md); packaging in
[`deploy/cloudrun/README.md`](../deploy/cloudrun/README.md); design truth in
[Firestore and Cloud](FIRESTORE_AND_CLOUD.md).

## 1. The choice: Option 1

The Firestore adapter is not a full `SchedulerStore`: `register_worker`,
`revoke_worker`, `expire_leases`, `enter_awaiting_result`, generic
`claim_task` / `heartbeat` / `complete_attempt`, `pause`, `resume`, and
`cancel` are unsupported, and artifact bytes stay in the executor's private
spool. Half-implementing that parity to run the failure laboratory through
the cloud store would produce a partially trusted store, which is worse than
an honestly scoped one. So:

- **Cloud vertical (Option 1, chosen):** the private coordinator image runs on
  Cloud Run against a real Firestore database and executes the implemented
  production vertical — mission create / exact plan approval / readiness,
  executor-session registration, atomic claim with lease and fence, heartbeat,
  completion, abandon, durable outbox, five-shard materialization and
  reconciliation — driven from this machine by
  `graphene mission executor connect --repo PATH --mission MISSION_ID
  --coordinator-url URL --audience AUDIENCE --workers 2` with Google OIDC.
  Cloud Run never clones or mounts the repository; the two WORK-only Gemini
  executor sessions run here.
- **Failure laboratory and the North Star mission:** run entirely on the
  fully implemented **SQLite authority locally**, per the
  [North Star runbook](NORTH_STAR_RUNBOOK.md).
- **Option 2** (minimal Firestore mutations for a cloud-side failure lab) is
  not started and is not planned before A1–A3 are captured.

### The authority split, README-ready (one sentence)

> The North Star mission, the failure laboratory, and the capsule ran under the local SQLite mission store as the sole execution authority, while the Cloud Run coordinator backed by real Firestore held authority only for the separately recorded `executor connect` vertical (executor registration, claim, heartbeat, completion, and outbox), and neither plane held authority for the other's demo.

The capsule manifest's `authority_note` ("SQLite mission store was the
execution authority for this mission.") is the machine-readable half of that
sentence.

## 2. Minimal owner checklist (condensed from Alex cloud setup §1–8)

One sitting, in order, in an owner-private shell. Replace every placeholder
deliberately; stop if the active account or project differs from the intended
sandbox. Exact variable names only:

1. **Names and limits.** `PROJECT_ID`, `BILLING_ACCOUNT`, `REGION`
   (`us-central1`), `FIRESTORE_LOCATION`, `DATABASE_ID` (dedicated, for
   example `graphene-taskmaster`), `AR_REPOSITORY` (`graphene`),
   `VIEWER_SA` (`graphene-viewer`), `COORDINATOR_SA` (`graphene-coordinator`),
   `EXECUTOR_SA` (`graphene-executor`), `READ_TOKEN_SECRET`
   (`graphene-control-read-token`). Firestore location cannot be moved later.
2. **Identity.** `gcloud auth login`, `gcloud auth application-default login`,
   `gcloud config set project "$PROJECT_ID"`; verify with
   `gcloud auth list --filter=status:ACTIVE`, `gcloud config get-value project`,
   `gcloud billing projects describe "$PROJECT_ID"` (`billingEnabled: true`).
3. **APIs.** Enable only `run`, `firestore`, `aiplatform`, `artifactregistry`,
   `cloudbuild`, `secretmanager`, `iam`, `iamcredentials`, `billingbudgets`
   (`.googleapis.com`).
4. **Database and image repository.** `gcloud firestore databases create
   --database="$DATABASE_ID" --location="$FIRESTORE_LOCATION" --type=firestore-native
   --delete-protection`; `gcloud artifacts repositories create "$AR_REPOSITORY"
   --location="$REGION" --repository-format=docker`.
5. **Three service accounts.** Create `$VIEWER_SA`, `$COORDINATOR_SA`,
   `$EXECUTOR_SA`. Viewer: `roles/datastore.viewer` conditioned to
   `projects/$PROJECT_ID/databases/$DATABASE_ID`. Coordinator: the reviewed
   least-privilege Firestore write role on that database only (review before
   granting). Executor: `roles/run.invoker` on the exact coordinator service
   after it exists — never project-wide Firestore access. Deployer:
   `roles/iam.serviceAccountUser` on the exact runtime identities only.
6. **Read token secret** (viewer only): `gcloud secrets create
   "$READ_TOKEN_SECRET"`, add one random version from `openssl rand -hex 32`
   via `--data-file=-`, grant `roles/secretmanager.secretAccessor` to
   `$VIEWER_SA` only. Pin a numeric version, never `latest`.
7. **Local Graphene names** (owner-private shell, never a committed `.env`):
   `GOOGLE_CLOUD_PROJECT="$PROJECT_ID"`, `GOOGLE_CLOUD_LOCATION="$REGION"`,
   `GRAPHENE_FIRESTORE_DATABASE="$DATABASE_ID"`,
   `GRAPHENE_FIRESTORE_NAMESPACE='graphene'`, `GRAPHENE_MISSION_ID`,
   `GRAPHENE_COORDINATOR_URL`, `GRAPHENE_COORDINATOR_AUDIENCE`
   (equal to the URL). Gemini credentials for the executor: either
   `GOOGLE_GENAI_USE_VERTEXAI=true` with project/location and valid ADC, or
   exactly one of `GEMINI_API_KEY` / `GOOGLE_API_KEY` with Vertex mode unset —
   one mode, never both. Read-only preflight: `gcloud firestore databases
   describe`, `gcloud artifacts repositories describe`, `gcloud iam
   service-accounts describe`, `gcloud secrets describe`, `gcloud secrets
   versions describe 1`.
8. **Budget and cap.** `gcloud billing budgets create --budget-amount='10USD'
   --filter-projects="projects/$PROJECT_NUMBER"` with 50/90/100 % thresholds;
   every deploy carries `--max-instances=1 --no-allow-unauthenticated`.

`graphene doctor` (section 0.3 of the runbook) reports
`modes.firestore-cloud.private_coordinator.configuration_ready` and
`outbound_executor.configuration_ready` from these names without probing
anything; `connectivity_proven` and `write_proven` stay `false` until the
evidence in section 6 exists.

## 3. Deriving the OIDC subject for `GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS`

The coordinator binds the immutable Google `sub` claim of the presented
audience-bound ID token to an executor id; email addresses and
client-supplied executor ids are never identity inputs. The bindings value is
a JSON object `{"<sub>": "<executor_id>"}` (1–64 entries; `executor_id`
matches `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`) and is coordinator
configuration, not a client-supplied identity.

The executor's token comes from `google.oauth2.id_token.fetch_id_token` on
this machine's ADC for the exact audience, so the `sub` you bind must be the
`sub` of the identity ADC will present. Use the executor service account for
that identity, never a personal user account:

```bash
export EXECUTOR_SA_EMAIL="$EXECUTOR_SA@$PROJECT_ID.iam.gserviceaccount.com"
gcloud auth application-default login --impersonate-service-account="$EXECUTOR_SA_EMAIL"
```

Operator step — derive the subject without ever writing the token to disk,
history, or a variable (the pipe decodes the payload in memory and prints
only `sub`):

```bash
gcloud auth print-identity-token \
  --impersonate-service-account="$EXECUTOR_SA_EMAIL" \
  --audiences="$GRAPHENE_COORDINATOR_AUDIENCE" \
| python3 -c 'import base64, json, sys
payload = sys.stdin.read().strip().split(".")[1]
payload += "=" * (-len(payload) % 4)
print(json.loads(base64.urlsafe_b64decode(payload))["sub"])'
```

Cross-check: for a service account the `sub` equals its numeric unique id,
`gcloud iam service-accounts describe "$EXECUTOR_SA_EMAIL" --format='value(uniqueId)'`.
The two must agree; if they do not, the ADC identity is not the executor
account and you must not deploy the binding. Then:

```bash
export EXECUTOR_BINDINGS='{"<sub printed above>":"executor-alex-local"}'
```

Treat the subject as configuration rather than a secret, but keep it out of
public docs and screenshots anyway. The deployer needs
`roles/iam.serviceAccountTokenCreator` on `$EXECUTOR_SA_EMAIL` for the
impersonated token mint; grant it to the deployer only.

## 4. Deploy the coordinator (operator template from `deploy/cloudrun/README.md`)

Cloud Run URLs are deterministic, so the audience can be fixed before the
first deploy and verified after it:

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export COORDINATOR_SERVICE='graphene-coordinator'
export COORDINATOR_SERVICE_ACCOUNT="$COORDINATOR_SA@$PROJECT_ID.iam.gserviceaccount.com"
export COORDINATOR_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPOSITORY/graphene-coordinator:taskmaster-v1"
export FIRESTORE_NAMESPACE='graphene'
export COORDINATOR_AUDIENCE="https://$COORDINATOR_SERVICE-$PROJECT_NUMBER.$REGION.run.app"
```

Then the two commands exactly as documented in
[`deploy/cloudrun/README.md`](../deploy/cloudrun/README.md):

```sh
gcloud builds submit . \
  --project="$PROJECT_ID" \
  --config=deploy/cloudrun/coordinator-cloudbuild.yaml \
  --substitutions="_IMAGE=$COORDINATOR_IMAGE"

gcloud run deploy "$COORDINATOR_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$COORDINATOR_IMAGE" \
  --service-account="$COORDINATOR_SERVICE_ACCOUNT" \
  --no-allow-unauthenticated \
  --max-instances=1 \
  --concurrency=8 \
  --port=8080 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GRAPHENE_FIRESTORE_DATABASE=$DATABASE_ID,GRAPHENE_FIRESTORE_NAMESPACE=$FIRESTORE_NAMESPACE,GRAPHENE_COORDINATOR_AUDIENCE=$COORDINATOR_AUDIENCE,GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS=$EXECUTOR_BINDINGS"
```

The image's entrypoint is
`uvicorn graphene.orchestration.cloud:create_private_coordinator_app --factory`;
it fails closed at startup if any of those five variables is missing or
malformed. After deploy:

```bash
gcloud run services describe "$COORDINATOR_SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url,status.latestReadyRevisionName)'
gcloud run services add-iam-policy-binding "$COORDINATOR_SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$EXECUTOR_SA_EMAIL" --role='roles/run.invoker'
export GRAPHENE_COORDINATOR_URL="$COORDINATOR_AUDIENCE"
export GRAPHENE_COORDINATOR_AUDIENCE="$COORDINATOR_AUDIENCE"
```

The printed `status.url` must equal `$COORDINATOR_AUDIENCE`; if it does not,
redeploy with `--update-env-vars=GRAPHENE_COORDINATOR_AUDIENCE=<printed url>`
and use the printed URL for both local variables. `GET /healthz` through
`gcloud run services proxy` proves only that configuration was accepted and
keeps saying `NOT PROVEN`.

## 5. Running the vertical for a real mission

```bash
uv run --frozen graphene mission executor connect \
  --repo "$DEST" --mission "$GRAPHENE_MISSION_ID" \
  --coordinator-url "$GRAPHENE_COORDINATOR_URL" \
  --audience "$GRAPHENE_COORDINATOR_AUDIENCE" --workers 2
```

`connect` runs the local preflight (Git, Google ADK, one Gemini credential
mode, usable policy), requires the mission to exist **locally** in `running`
state with a verified head and a policy/base binding identical to `--repo`,
then registers two WORK-only sessions (`outbound-work-1`, `outbound-work-2`)
with the coordinator, sending that verified local head as `expected_head`.
The coordinator's Firestore store enforces `expected_head` against the
mission it holds, so the mission must already exist in Firestore —
created, approved, and readiness-refreshed — with the **same** head.

Two honest gaps must be closed or worked around before this runs; both are
open work, not labels:

- **Seeding.** No CLI seeds a mission into Firestore. The only implemented
  path is the Python API the emulator test uses
  (`FirestoreMissionStore.initialize_namespace_schema` → `create_mission` →
  `approve_plan` → `refresh_ready`, see
  [`tests/integration/test_firestore_emulator.py`](../tests/integration/test_firestore_emulator.py)),
  and nothing yet demonstrates that a mission created that way and the same
  mission in the local SQLite store produce identical event digests and
  therefore an identical head. Until a seeding command exists and is tested
  against the emulator, the vertical is driven the way the emulator test
  drives it, and the authority sentence must say so.
- **Checks.** The outbound executor reads `GRAPHENE_CHECK_EXECUTOR` through
  the same selection as the local ADK path and fails closed on an
  unsupported value before registering a worker: `docker` needs the executor
  image built and the daemon responsive (itself **NOT PROVEN**);
  `host-sandbox` runs `fixture-tests` under macOS `sandbox-exec` with the
  check subprocess registered in the mission's owned-process registry. A
  repository whose only command template is the `graphene init` default
  `git diff --check --` is checked in-process either way. The outbound
  host-sandbox route has a credential-free unit path only; no live outbound
  check has run.

The result JSON is sanitized by construction: `status: executor_stopped`,
`authenticated_coordinator_round_trip`, `scope:
work_only_first_cloud_vertical`, `mission_completion_claimed: false`,
`worker_ids`, `capabilities: ["work"]`, `claimed`,
`completed_work_attempts`, and `final_heads`.

The separately gated live Firestore smoke is independent of the coordinator
and runs first:

```bash
GRAPHENE_RUN_LIVE_FIRESTORE=1 GRAPHENE_RUN_CLOUD_SMOKE=1 \
GRAPHENE_LIVE_FIRESTORE_PROJECT="$PROJECT_ID" \
GRAPHENE_LIVE_FIRESTORE_DATABASE="$DATABASE_ID" \
GRAPHENE_LIVE_FIRESTORE_NAMESPACE='livesmoke' \
  uv run --frozen pytest -q tests/integration/test_firestore_live.py -p no:cacheprovider
```

It refuses `FIRESTORE_EMULATOR_HOST`, uses a fresh suffixed namespace, and
cleans up exactly what it wrote.

## 6. Sanitized evidence to capture

- Cloud Run: service name, region, `status.latestReadyRevisionName`, the image
  digest from `gcloud artifacts docker images describe`, `--max-instances=1`
  and `--no-allow-unauthenticated` visible in `gcloud run services describe`.
- `GET /healthz` body via the authenticated proxy (it says `NOT PROVEN`; that
  is the point — configuration accepted, nothing more).
- Firestore: database id, namespace, the mission document id and its committed
  head `{seq, event_sha256}`, and a console screenshot or `gcloud firestore`
  export of `<namespace>_missions/<mission_id>` and its state-root/shard
  documents. Those documents contain labels, ids, and digests only; still crop
  anything that is not Graphene's.
- Executor: the `connect` result JSON above; `claimed >= 2`,
  `completed_work_attempts >= 2`, `authenticated_coordinator_round_trip: true`,
  `final_heads` matching the Firestore head.
- Provider: returned model, session and invocation ids, and usage source from
  the local worker-provider receipts (digests cited as in the runbook).
- The pytest summary line of the live Firestore smoke.
- Never: ID tokens, the bindings value, the read token, prompts, worker
  output, command output, source bytes, private artifact bytes, or absolute
  home paths.

## 7. Label

`contracts/product_proof.json` → `mission_paths.cloud-run-firestore.status`
and `delivery_gates.live_cloud.status`, and the README row
`Cloud Run + real Firestore`, stay **`NOT DEPLOYED — NOT PROVEN`** until every
item in section 6 is captured and referenced from the same commit that flips
them, together with the one-sentence authority split from section 1 placed in
the README. Packaging, unit tests, the verified official emulator run, a
health check, or a partial capture flip nothing.
