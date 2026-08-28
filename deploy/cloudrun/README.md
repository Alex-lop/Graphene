# Cloud Run control plane

Canonical cloud architecture and owner setup live in [`docs/FIRESTORE_AND_CLOUD.md`](../../docs/FIRESTORE_AND_CLOUD.md) and [`docs/ALEX_CLOUD_SETUP.md`](../../docs/ALEX_CLOUD_SETUP.md). This file documents only the current package.

Status: **NOT DEPLOYED — NOT PROVEN**. These artifacts are locally testable
packaging, not evidence of a working Google Cloud deployment.

The default image serves one authenticated, read-only Mission Control backed only by an
explicit Firestore database. It does not clone a repository, run commands, invoke
Gemini, dispatch a worker, or fall back to SQLite. Repository work remains the
responsibility of a separately authenticated outbound executor. A distinct
`coordinator.Dockerfile` packages the private multi-mission coordinator factory;
neither image proves a deployment.

The package includes Firestore command/event/sharded-materialization/outbox
transactions plus a private one-worker register/claim/fetch/heartbeat/completion
coordinator, audience-bound OIDC HTTPS client, one-use artifact capabilities,
and outbound local executor. Abandon is disabled and returns 501; interrupted
claims wait for lease TTL expiry. The official emulator production path completed
**4 passed**. The separate coordinator image starts only the private
multi-mission coordinator factory. A live authenticated cloud recovery smoke
remains pending, so deployment remains **NOT PROVEN**.

Build and deploy the coordinator as a separate private service and service
account. The bindings value is configuration, not a client-supplied identity.

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

This command is an operator template only. Use an existing least-privilege
coordinator identity and authorized values; no service or IAM resource was
created or verified by this repository.

After an IAM administrator verifies the private service, grant the executor
identity only service invocation:

```sh
gcloud run services add-iam-policy-binding "$COORDINATOR_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$EXECUTOR_SA_EMAIL" \
  --role='roles/run.servicesInvoker'
```

Cloud Run coordinates Firestore transitions only. Gemini, repository work, and
checks run in the separately authenticated local executor.

## Required existing resources

- an explicitly authorized Google Cloud project and region;
- an existing Artifact Registry Docker repository;
- an existing Firestore Native-mode database;
- a coordinator runtime account with `roles/datastore.user` conditioned to the
  exact Firestore database;
- a viewer runtime account with `roles/datastore.viewer` under the same exact
  database condition;
- an executor account with `roles/run.servicesInvoker` on the exact coordinator
  service and no Firestore role;
- deployer and Cloud Build grants scoped exactly as listed in
  [`docs/ALEX_CLOUD_SETUP.md`](../../docs/ALEX_CLOUD_SETUP.md#5-create-three-service-identities);
- an existing enabled Secret Manager secret version containing only a random
  16-256-character URL-safe Mission Control read token (no trailing newline),
  with the service account granted
  `roles/secretmanager.secretAccessor` on that secret only;
- a private create-new seed receipt from `graphene mission executor seed` for
  the separately materialized Firestore execution mission.

Set the values deliberately. Do not copy placeholder values into a real deploy.

```sh
export PROJECT_ID='authorized-sandbox-project'
export REGION='us-central1'
export AR_REPOSITORY='graphene'
export SERVICE='graphene-control'
export SERVICE_ACCOUNT='graphene-viewer@authorized-sandbox-project.iam.gserviceaccount.com'
export DATABASE_ID='graphene-taskmaster'
export FIRESTORE_NAMESPACE='graphene'
export MISSION_ID='mission_example'
export READ_TOKEN_SECRET='graphene-control-read-token'
export READ_TOKEN_SECRET_VERSION='1'
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPOSITORY/graphene-control:taskmaster-v1"
```

Fail closed if the active project, identity, database, repository, or service
account is not exactly the authorized target. The following reads are safe
preflight checks; they create nothing:

```sh
gcloud auth list --filter=status:ACTIVE
gcloud config get-value project
gcloud firestore databases describe --project="$PROJECT_ID" --database="$DATABASE_ID"
gcloud artifacts repositories describe "$AR_REPOSITORY" --project="$PROJECT_ID" --location="$REGION"
gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project="$PROJECT_ID"
gcloud secrets describe "$READ_TOKEN_SECRET" --project="$PROJECT_ID"
gcloud secrets versions describe "$READ_TOKEN_SECRET_VERSION" --secret="$READ_TOKEN_SECRET" --project="$PROJECT_ID"
gcloud secrets get-iam-policy "$READ_TOKEN_SECRET" --project="$PROJECT_ID" \
  --flatten='bindings[].members' \
  --filter="bindings.role=roles/secretmanager.secretAccessor AND bindings.members=serviceAccount:$SERVICE_ACCOUNT"
```

Build and deploy only after those checks match the authorized sandbox:

```sh
gcloud builds submit . \
  --project="$PROJECT_ID" \
  --config=deploy/cloudrun/cloudbuild.yaml \
  --substitutions="_IMAGE=$IMAGE"

gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$SERVICE_ACCOUNT" \
  --no-allow-unauthenticated \
  --max-instances=1 \
  --port=8080 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GRAPHENE_FIRESTORE_DATABASE=$DATABASE_ID,GRAPHENE_FIRESTORE_NAMESPACE=$FIRESTORE_NAMESPACE,GRAPHENE_MISSION_ID=$MISSION_ID" \
  --set-secrets="GRAPHENE_MISSION_CONTROL_READ_TOKEN=$READ_TOKEN_SECRET:$READ_TOKEN_SECRET_VERSION"
```

Secret Manager is used here only to keep the long-lived application bearer out
of shell history and plaintext Cloud Run environment configuration. It is access
secret handling, not an additional service claimed to pad the hackathon stack.

For an IAM-authenticated local view, use the Cloud Run proxy and open the shown
Mission Control URL:

```sh
gcloud run services proxy "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --port=8080
```

```text
http://127.0.0.1:8080/mission-control/<MISSION_ID>#token=<READ_TOKEN>
```

An operator separately authorized to read the secret can retrieve its value
without placing the value itself in shell history:

```sh
gcloud secrets versions access "$READ_TOKEN_SECRET_VERSION" \
  --secret="$READ_TOKEN_SECRET" \
  --project="$PROJECT_ID"
```

Supply that value out of band in the URL fragment only after the authenticated
proxy is running. The command prints secret material, so run it only in a private
terminal and do not capture its output. The service never returns its token from
an anonymous app route, header, or HTML response. The browser keeps the fragment
client-side; do not paste it into logs, issues, or shared links. This second-hop
token does not replace Cloud Run IAM, and the service must remain private.

`GET /healthz` proves only that required configuration was accepted; its response
continues to say `NOT PROVEN`. A captured authenticated read of the deployed
Mission Control plus a coordinator-to-local-executor round trip is required
before making any live Cloud Run or real-Firestore claim.

Materialized state is split into five content-addressed shards, each capped at
450,000 canonical bytes, plus a root capped at 65,536. The committed pointer contains
only the head/root binding. No mission depends on one monolithic document near
Firestore's 1 MiB limit.

Command references: [Cloud Build submit](https://cloud.google.com/sdk/gcloud/reference/builds/submit),
[Cloud Run deploy](https://cloud.google.com/sdk/gcloud/reference/run/deploy), and
[private-service developer proxy](https://cloud.google.com/run/docs/authenticating/developers).
See [Firestore server-client IAM](https://cloud.google.com/firestore/docs/security/iam)
for the runtime role boundary, [Cloud Run secret configuration](https://cloud.google.com/run/docs/configuring/services/secrets)
for the version-pinned secret environment value, and [Firestore quotas](https://cloud.google.com/firestore/quotas)
for the document-size ceiling.
