# Cloud Run control plane

Status: **NOT DEPLOYED — NOT PROVEN**. These artifacts are locally testable
packaging, not evidence of a working Google Cloud deployment.

This image serves one authenticated, read-only Mission Control backed only by an
explicit Firestore database. It does not clone a repository, run commands, invoke
Gemini, dispatch a worker, or fall back to SQLite. Repository work remains the
responsibility of a separately authenticated outbound executor; that protocol is
not proven by this image.

The Firestore lease-slot primitives provide transactional fencing only. They do
not publish a lease into the event-head-bound `MissionSnapshot`; a future cloud
scheduler must commit the corresponding domain event and materialization. There
is not yet an atomic scheduler API or outbox, so a crash between a slot claim and
that future event would leave an invisible lease until it expires. Contract-level
at-least-once cloud scheduling is therefore also **NOT PROVEN**.

## Required existing resources

- an explicitly authorized Google Cloud project and region;
- an existing Artifact Registry Docker repository;
- an existing Firestore Native-mode database;
- a dedicated Cloud Run service account with read-only Firestore access (for
  example, `roles/datastore.viewer`, narrowed to the selected database when the
  project policy supports that condition);
- an existing enabled Secret Manager secret version containing only a random
  16-256-character URL-safe Mission Control read token (no trailing newline),
  with the service account granted
  `roles/secretmanager.secretAccessor` on that secret only;
- an existing materialized mission snapshot and its event stream.

Set the values deliberately. Do not copy placeholder values into a real deploy.

```sh
export PROJECT_ID='authorized-sandbox-project'
export REGION='us-central1'
export AR_REPOSITORY='graphene'
export SERVICE='graphene-control'
export SERVICE_ACCOUNT='graphene-control@authorized-sandbox-project.iam.gserviceaccount.com'
export DATABASE_ID='(default)'
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
Mission Control and its Firestore-backed mission is still required before making
any live Cloud Run or Firestore claim.

The adapter rejects a materialized snapshot whose canonical JSON exceeds 900,000
bytes before attempting a write. This intentionally leaves room below
Firestore's 1 MiB document limit; larger projections need a future sharded
materialization design and remain **NOT PROVEN**.

Command references: [Cloud Build submit](https://cloud.google.com/sdk/gcloud/reference/builds/submit),
[Cloud Run deploy](https://cloud.google.com/sdk/gcloud/reference/run/deploy), and
[private-service developer proxy](https://cloud.google.com/run/docs/authenticating/developers).
See [Firestore server-client IAM](https://cloud.google.com/firestore/docs/security/iam)
for the runtime role boundary, [Cloud Run secret configuration](https://cloud.google.com/run/docs/configuring/services/secrets)
for the version-pinned secret environment value, and [Firestore quotas](https://cloud.google.com/firestore/quotas)
for the document-size ceiling.
