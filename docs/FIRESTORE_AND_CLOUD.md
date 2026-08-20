# Firestore and Cloud

## Current truth

The official Firestore Emulator production-path command completed **3 passed**. The real Google client exercised namespace schema initialization, mission creation, exact plan approval, readiness, executor session registration, atomic claim/outbox delivery, heartbeat, failed completion, five-shard materialization, reconciliation, and incompatible-schema rejection. Two additional tests prove cleanup is exact and bounded.

This is credential-free local proof, not a Google Cloud deployment. No project was authorized, no service was deployed, and no authenticated cloud-to-local run was captured. Cloud Run and real Firestore remain **NOT DEPLOYED — NOT PROVEN**.

## Implemented narrow vertical

Firestore stores an immutable content-addressed state root plus five bounded shards: mission summary, tasks, attempts/leases, publications/gates, and result. Each shard is capped at 450,000 canonical bytes and the root at 65,536. The committed pointer binds the exact head/root and stays small; it is not a monolithic snapshot document. Production `append`/`save_snapshot` bootstrap is disabled unless a test explicitly opts in.

The authoritative transition path supports:

- mission creation, exact plan approval, and readiness materialization;
- executor session/capability registration;
- atomic ready-task claim with attempt, lease/fence, event, head-bound state, and durable outbox;
- exact-owner heartbeat, V2 publication completion, failure completion, and abandon;
- executor-local artifact ownership, one-use fetch capabilities, reconnect/idempotent completion, and materialization repair;
- a private multi-mission coordinator API plus an outbound local executor. Cloud Run never clones or mounts the repository.

The adapter is not yet a drop-in implementation of the local `SchedulerStore`. These exact mutations remain unsupported through that protocol: `register_worker`, `revoke_worker`, `expire_leases`, `enter_awaiting_result`, generic `claim_task`, generic `heartbeat`, generic `complete_attempt`, `pause`, `resume`, and `cancel`. The cloud-specific session/dispatch methods cover only the vertical above. Final gate/input/retry/replan parity and the full shared SQLite state-machine corpus are also pending.

## Identity and protocol boundary

| Identity | Minimum purpose |
|---|---|
| Mission Control viewer | Read the selected Firestore database/namespace only |
| Coordinator | Commit the allowed domain/materialization/outbox transitions only |
| Outbound local executor | Invoke the private coordinator and claim only its bound workers |

The coordinator binds the authenticated Google principal to executor identity server-side. The HTTPS client requests a fresh audience-bound OIDC token, sends bounded no-store requests, and reconnects through idempotent command IDs. The executor has no Firestore viewer/admin role; the viewer has no command or lease authority.

Artifact bytes stay in the executor's private durable spool. Firestore records only bounded V2 references and locality. A downstream task is pinned to the artifact-owning executor; an unavailable spool produces `artifact_locality_unavailable`, never a dispatch to a machine that cannot verify the bytes.

## Proof commands

Official emulator/client:

```bash
GRAPHENE_RUN_FIRESTORE_EMULATOR=1 \
  npx --yes --package=node@22 --package=firebase-tools@13.31.1 \
  firebase emulators:exec --only firestore --project demo-graphene-emulator \
  "uv run --frozen pytest -q tests/integration/test_firestore_emulator.py"
```

The separately gated real-project smoke requires both `GRAPHENE_RUN_LIVE_FIRESTORE=1` and `GRAPHENE_RUN_CLOUD_SMOKE=1`, plus the exact project/database/namespace values. It was **NOT RUN**. Deployment instructions remain in [`deploy/cloudrun/README.md`](../deploy/cloudrun/README.md); owner IAM, billing, smoke, and cleanup steps are in [Alex cloud setup](ALEX_CLOUD_SETUP.md).

Cloud Mission Control currently polls Firestore per client every two seconds. There is no shared listener or fan-out, so cloud streaming remains **NOT PROVEN**.
