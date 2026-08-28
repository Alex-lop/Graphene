# Alex cloud setup

Status: owner checklist only. Running these commands can create billable resources and IAM grants. Graphene has not run them and remains **NOT DEPLOYED — NOT PROVEN**.

Use a dedicated sandbox project. Replace every placeholder deliberately, keep values out of Git/screenshots, and stop if the active account/project differs from the intended target.

## 1. Choose immutable locations and spending limits

Choose the billing account, project, Cloud Run/Artifact Registry region, and Firestore location first. Firestore location cannot be casually moved later. Prefer a dedicated named database so cleanup cannot target unrelated default data.

```bash
export PROJECT_ID='YOUR_DEDICATED_PROJECT_ID'
export BILLING_ACCOUNT='YOUR_BILLING_ACCOUNT_ID'
export REGION='us-central1'
export FIRESTORE_LOCATION='us-central1'
export DATABASE_ID='graphene-taskmaster'
export AR_REPOSITORY='graphene'
export SERVICE='graphene-control'
export COORDINATOR_SERVICE='graphene-coordinator'
export VIEWER_SA='graphene-viewer'
export COORDINATOR_SA='graphene-coordinator'
export EXECUTOR_SA='graphene-executor'
export DEPLOYER_PRINCIPAL='user:YOUR_DEPLOYER_EMAIL'
export READ_TOKEN_SECRET='graphene-control-read-token'
```

These placeholders are examples, not an authorized project selection.

## 2. Authenticate and verify identity

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project "$PROJECT_ID"
gcloud auth list --filter=status:ACTIVE
gcloud config get-value project
gcloud billing projects describe "$PROJECT_ID"
```

The active account, project, and `billingEnabled: true` must match the chosen sandbox. ADC serves local client libraries; `gcloud auth login` serves the CLI. See Google’s [ADC command reference](https://cloud.google.com/sdk/gcloud/reference/auth/application-default) and [billing verification](https://cloud.google.com/billing/docs/how-to/verify-billing-enabled).

## 3. Enable only required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  billingbudgets.googleapis.com \
  --project="$PROJECT_ID"
```

Review the enabled list; do not add adjacent APIs “just in case.” Google documents multi-service enablement in [Service Usage](https://cloud.google.com/service-usage/docs/enable-disable).

## 4. Create the database and image repository

```bash
gcloud firestore databases create \
  --project="$PROJECT_ID" \
  --database="$DATABASE_ID" \
  --location="$FIRESTORE_LOCATION" \
  --edition=standard \
  --type=firestore-native \
  --delete-protection

gcloud artifacts repositories create "$AR_REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --repository-format=docker \
  --description='Graphene private control-plane images'
```

If either resource already exists, describe and verify it instead of recreating it. References: [Firestore database management](https://cloud.google.com/firestore/docs/manage-databases) and [Artifact Registry repository creation](https://cloud.google.com/artifact-registry/docs/repositories/create-repos).

## 5. Create three service identities

```bash
for service_account in "$VIEWER_SA" "$COORDINATOR_SA" "$EXECUTOR_SA"; do
  gcloud iam service-accounts create "$service_account" \
    --project="$PROJECT_ID" \
    --display-name="$service_account"
done
```

Purpose and minimum grants:

| Identity | Grant | Scope |
|---|---|---|
| Viewer | `roles/datastore.viewer` | Project binding conditioned to the exact database |
| Coordinator | `roles/datastore.user` | Project binding conditioned to the exact database |
| Executor | `roles/run.servicesInvoker` | Exact coordinator Cloud Run service only; no Firestore role |
| Executor, Vertex mode only | `roles/aiplatform.user` | Selected proof project; omit for API-key mode |
| Deployer | `roles/cloudbuild.builds.editor` and `roles/serviceusage.serviceUsageConsumer` | Selected project; Cloud Build cannot be scoped to a repository |
| Deployer | `roles/run.developer` | Exact existing viewer/coordinator services |
| Deployer | `roles/artifactregistry.reader` | Exact image repository |
| Deployer | `roles/iam.serviceAccountUser` | Exact viewer and coordinator runtime service accounts |
| Deployer | `roles/iam.serviceAccountTokenCreator` | Exact coordinator and executor accounts used for local impersonation |
| Cloud Build execution account | `roles/artifactregistry.writer` | Exact image repository |

An IAM administrator must create the Cloud Run services or temporarily grant
project-level create authority and remove it immediately; an exact-service
`roles/run.developer` binding cannot create a service that does not exist. The
same administrator, not the deployer, sets service IAM because
`roles/run.developer` does not include `setIamPolicy`.

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$VIEWER_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role='roles/datastore.viewer' \
  --condition="expression=resource.name==\"projects/$PROJECT_ID/databases/$DATABASE_ID\",title=graphene_database_only,description=Read_only_selected_Graphene_database"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$COORDINATOR_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role='roles/datastore.user' \
  --condition="expression=resource.name==\"projects/$PROJECT_ID/databases/$DATABASE_ID\",title=graphene_database_only,description=Read_write_selected_Graphene_database"

# The documented example selects Vertex AI. Omit this grant for API-key mode.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$EXECUTOR_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role='roles/aiplatform.user'
```

Database-scoped IAM conditions are documented in [Firestore database access](https://cloud.google.com/firestore/docs/manage-databases#configure_per-database_access_permissions). The role contents and deployment split are documented in [Firestore IAM](https://docs.cloud.google.com/iam/docs/roles-permissions/firestore), [Cloud Run IAM](https://docs.cloud.google.com/run/docs/reference/iam/roles), [Artifact Registry IAM](https://docs.cloud.google.com/artifact-registry/docs/access-control), and [Cloud Build IAM](https://docs.cloud.google.com/build/docs/securing-builds/configure-access-to-resources).

Before deployment, have an IAM administrator apply the table to the exact
resources and inspect each resulting policy. Do not substitute Editor, Owner,
`roles/run.admin`, or a project-wide Firestore role.

## 6. Create and scope the read token

Create the secret without a value, then add a random URL-safe version without printing it or embedding it in shell history:

```bash
gcloud secrets create "$READ_TOKEN_SECRET" \
  --project="$PROJECT_ID" \
  --replication-policy=automatic

openssl rand -hex 32 | gcloud secrets versions add "$READ_TOKEN_SECRET" \
  --project="$PROJECT_ID" \
  --data-file=-

gcloud secrets add-iam-policy-binding "$READ_TOKEN_SECRET" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$VIEWER_SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role='roles/secretmanager.secretAccessor'
```

Only the viewer service receives access to this secret. Pin the deployed service to a numeric secret version, not `latest`. References: [create a secret](https://cloud.google.com/secret-manager/docs/creating-and-accessing-secrets) and [grant secret access](https://cloud.google.com/secret-manager/docs/manage-access-to-secrets).

## 7. Set local Graphene names and run read-only preflight

Set values in an owner-private shell or secret-aware launcher, never in a committed `.env`:

```bash
export GOOGLE_CLOUD_PROJECT="$PROJECT_ID"
export GOOGLE_CLOUD_LOCATION="$REGION"
export GOOGLE_GENAI_USE_VERTEXAI=true
export GRAPHENE_FIRESTORE_DATABASE="$DATABASE_ID"
export GRAPHENE_FIRESTORE_NAMESPACE='graphene'
export GRAPHENE_MISSION_ID='YOUR_CAPTURED_MISSION_ID'
export GRAPHENE_COORDINATOR_URL='https://YOUR_PRIVATE_COORDINATOR_URL'
export GRAPHENE_COORDINATOR_AUDIENCE="$GRAPHENE_COORDINATOR_URL"
export PLAN_SHA256='YOUR_REVIEWED_PLAN_SHA256'
export SEED_RECEIPT="$PWD/graphene-cloud-seed.json"
```

This example chooses Vertex AI, so the executor needs the conditional
`roles/aiplatform.user` grant above. If the separately approved mode is a
Gemini API key, omit that grant, leave `GOOGLE_GENAI_USE_VERTEXAI` unset, and
set exactly one of `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the private shell.
Never configure both modes.

The reviewed CLI has no `graphene doctor --cloud`; use these read-only checks:

```bash
gcloud firestore databases describe --project="$PROJECT_ID" --database="$DATABASE_ID"
gcloud artifacts repositories describe "$AR_REPOSITORY" --project="$PROJECT_ID" --location="$REGION"
gcloud iam service-accounts describe "$VIEWER_SA@$PROJECT_ID.iam.gserviceaccount.com" --project="$PROJECT_ID"
gcloud secrets describe "$READ_TOKEN_SECRET" --project="$PROJECT_ID"
gcloud secrets versions describe 1 --secret="$READ_TOKEN_SECRET" --project="$PROJECT_ID"
```

Do not continue if any resource resolves outside the selected project/location/database.

## 8. Add a small budget and deployment cap

Budget alerts do not hard-cap spend. Create a small project-filtered alert and keep Cloud Run at one instance for proof:

```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud billing budgets create \
  --billing-account="$BILLING_ACCOUNT" \
  --display-name='Graphene sandbox' \
  --budget-amount='10USD' \
  --filter-projects="projects/$PROJECT_NUMBER" \
  --threshold-rule=percent=0.50 \
  --threshold-rule=percent=0.90 \
  --threshold-rule=percent=1.00
```

See [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets) and [Cloud Run maximum instances](https://cloud.google.com/run/docs/configuring/max-instances). The package deploy command must include `--max-instances=1` and `--no-allow-unauthenticated`.

## 9. Build and deploy only an explicitly selected private service

Follow [`deploy/cloudrun/README.md`](../deploy/cloudrun/README.md) after every preflight matches. Its default package is the read-only viewer and must use exactly `$VIEWER_SA@$PROJECT_ID.iam.gserviceaccount.com`; its separate coordinator package must use a separately reviewed coordinator identity. Neither package proves an executor or a live cloud path. Keep both private. Google’s current references cover [private Cloud Run deployment](https://cloud.google.com/run/docs/deploying) and [service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service).

## 10. Explicit live proof

Opt in only after project validation. Capture sanitized evidence:

```bash
GRAPHENE_RUN_LIVE_GEMINI=1 uv run --frozen pytest -q tests/process/test_gemini_live.py

GRAPHENE_RUN_LIVE_FIRESTORE=1 GRAPHENE_RUN_CLOUD_SMOKE=1 \
  uv run --frozen pytest -q tests/integration/test_firestore_live.py

export COORDINATOR_SA_EMAIL="$COORDINATOR_SA@$PROJECT_ID.iam.gserviceaccount.com"
export EXECUTOR_SA_EMAIL="$EXECUTOR_SA@$PROJECT_ID.iam.gserviceaccount.com"

# Seed with the only identity that may write the selected Firestore database.
gcloud auth application-default login \
  --impersonate-service-account="$COORDINATOR_SA_EMAIL"
uv run --frozen graphene mission executor seed \
  --repo PATH --mission "$GRAPHENE_MISSION_ID" \
  --plan-sha256 "$PLAN_SHA256" \
  --audience "$GRAPHENE_COORDINATOR_AUDIENCE" \
  --output "$SEED_RECEIPT" --confirm-human

# Then switch to the invocation-only identity; it has no Firestore access.
gcloud auth application-default login \
  --impersonate-service-account="$EXECUTOR_SA_EMAIL"
uv run --frozen graphene mission executor connect \
  --repo PATH --mission "$GRAPHENE_MISSION_ID" \
  --seed-receipt "$SEED_RECEIPT" \
  --coordinator-url "$GRAPHENE_COORDINATOR_URL" \
  --audience "$GRAPHENE_COORDINATOR_AUDIENCE" --workers 1
```

The local mission must be an operator-created, review-required schema-2 plan at
revision 1 with no dispatch history. Read `PLAN_SHA256` from `graphene --json
plan show "$GRAPHENE_MISSION_ID" --detail`; do not approve or run that local
mission. `executor seed` records a separate approved schema-1 Firestore
execution mission and writes a private create-new receipt. Local SQLite remains
the North Star authority, and the two event heads are deliberately distinct.

- Cloud Run service URL and revision, without access tokens.
- Firestore database/namespace and mission head digest, without private artifacts.
- Returned Gemini model/session/invocation receipt, without prompt or source.
- Mission Control truth banner and exact proof mode.

Configuration, health checks, packaging, or an emulator do not establish deployment. Record live proof in [the implementation report](IMPLEMENTATION_REPORT.md).

## 11. Scoped cleanup

Resolve each target with `describe` before deletion. Never delete the project/default database or use broad wildcard cleanup.

```bash
gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION"
gcloud run services delete "$SERVICE" --project="$PROJECT_ID" --region="$REGION"

gcloud artifacts repositories describe "$AR_REPOSITORY" --project="$PROJECT_ID" --location="$REGION"
gcloud artifacts repositories delete "$AR_REPOSITORY" --project="$PROJECT_ID" --location="$REGION"

gcloud secrets describe "$READ_TOKEN_SECRET" --project="$PROJECT_ID"
gcloud secrets delete "$READ_TOKEN_SECRET" --project="$PROJECT_ID"
```

Delete the named Firestore database only after verifying it contains no needed evidence and explicitly disabling its deletion protection. Service-account and IAM cleanup must name the three exact identities. References: [Cloud Run service deletion](https://cloud.google.com/sdk/gcloud/reference/run/services/delete), [Artifact Registry deletion](https://cloud.google.com/artifact-registry/docs/repositories/delete-repos), and [Firestore database deletion](https://cloud.google.com/firestore/docs/manage-databases#delete_a_database).
