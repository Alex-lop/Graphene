# Development

## Prerequisites

- Python 3.13, pinned by [`.python-version`](../.python-version)
- `uv` with the checked-in lock file
- Git
- Node 22 for browser tests
- macOS `/usr/bin/sandbox-exec` only for the verified scripted executor path
- Docker, Gemini credentials, Firestore emulator, and Google Cloud credentials only for explicit opt-in gates

## Setup

```bash
uv lock --check
uv sync --frozen
uv run --frozen graphene --help
```

Do not place credentials in repository files. Copy variable names from [`.env.example`](../.env.example) into an owner-private environment and set only the values needed by an explicitly selected live gate.

## Credential-free verification

```bash
uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py
uv run --frozen pytest -q tests/process/test_mcp_stdio.py
node --test frontend/test/*.test.mjs
node --test tests/frontend/*.mjs
node --check frontend/src/app.mjs frontend/src/graph.mjs frontend/src/workflow.mjs
node --check backend/graphene/viewer/static/reducer.mjs backend/graphene/viewer/static/viewer.mjs
node --check backend/graphene/orchestration/static/mission_reducer.mjs backend/graphene/orchestration/static/mission_control.mjs
uv run --frozen graphene mission replay taskmaster --no-open --exit-after-replay
uv run --frozen python scripts/generate_mission_replay.py --check
uv run --frozen ruff check backend tests scripts benchmarks
git diff --check
```

The aggregate Python command deliberately excludes the separately bounded MCP STDIO process gate.

Official Firestore emulator/client proof (credential-free, Node 22):

```bash
GRAPHENE_RUN_FIRESTORE_EMULATOR=1 \
  npx --yes --package=node@22 --package=firebase-tools@13.31.1 \
  firebase emulators:exec --only firestore --project demo-graphene-emulator \
  "uv run --frozen pytest -q tests/integration/test_firestore_emulator.py"
```

The recorded production-path run completed **3 passed**. It does not prove real Google Cloud behavior.

## Opt-in proof

```bash
uv run --frozen graphene mission demo
GRAPHENE_RUN_LIVE_GEMINI=1 uv run --frozen pytest -q tests/process/test_gemini_live.py
GRAPHENE_RUN_DOCKER_SMOKE=1 uv run --frozen pytest -q tests/unit/orchestration/test_sandbox.py
```

`graphene mission demo` is the credential-gated live Taskmaster planner/worker entrypoint; it has no fake or replay fallback and remains **NOT PROVEN** until a complete two-worker provider run returns receipts. Live Firestore/Cloud commands require the exact project checks in [Alex cloud setup](ALEX_CLOUD_SETUP.md). Docker, live Gemini, real Cloud Run/Firestore, benchmark results, and the submission video remain **NOT PROVEN**. Do not convert required deterministic tests into skips.

Local database inspection is deliberately explicit: `graphene mission db status` reads the schema ledger, `graphene mission db verify` verifies every v2 mission, and `graphene mission db migrate --dry-run` only reports the safe export-and-new-store action for a v1 database. It does not rewrite legacy state.

## Contribution rules

- Preserve the mission/legacy-lineage domain split and strict schemas.
- Add the smallest runnable regression for non-trivial logic.
- Keep operator/external effects explicit and opt-in.
- Update [`contracts/product_proof.json`](../contracts/product_proof.json), [known limitations](KNOWN_LIMITATIONS.md), and the [implementation report](IMPLEMENTATION_REPORT.md) when proof changes.
- Run relative-link and documentation-truth tests after documentation edits.
- Never commit captured credentials, private source, absolute local paths, or unredacted provider output.

CI jobs and supported platform claims are defined in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
