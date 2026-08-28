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

### Parity checks — the two topologies this host is not

Everything above is a result from *this* machine. Two CI jobs run somewhere it
cannot see, and each has shipped a defect that no local run could reproduce:

```bash
scripts/linux_parity_check.sh          # the pinned python:3.13-slim image (SQLite 3.46)
scripts/macos_parity_check.sh          # python.org's framework interpreter, the runner's
scripts/macos_parity_check.sh --quick  # two files, under a minute, same topology
```

`linux_parity_check.sh` exists because a SQL `LIKE` against a BLOB matches on
macOS SQLite 3.51 and matches nothing on the 3.46 in the deployment image.
`macos_parity_check.sh` exists because python.org's `bin/python3.x` is a
launcher that execs `Resources/Python.app/Contents/MacOS/Python` in place —
which `actions/setup-python` installs on `macos-15` and Anaconda, Homebrew and
uv interpreters do not do, so the owned-process registry refused its own child
only in Actions. Both spend nothing, contact no provider, write nothing into
the working tree, and print a SKIP naming what is then unchecked when the
topology they need (Docker; a framework interpreter) is absent. `--quick`
prints `MACOS PARITY (quick):`, which a grep for `MACOS PARITY: ALL PASS`
deliberately does not match.

Official Firestore emulator/client proof (credential-free, Node 22):

```bash
GRAPHENE_RUN_FIRESTORE_EMULATOR=1 \
  npx --yes --package=node@22 --package=firebase-tools@13.31.1 \
  firebase emulators:exec --only firestore --project demo-graphene-emulator \
  "uv run --frozen pytest -q tests/integration/test_firestore_emulator.py"
```

The recorded production-path run completed **4 passed**. It does not prove real Google Cloud behavior.

## Opt-in proof

```bash
uv run --frozen graphene mission demo
GRAPHENE_RUN_LIVE_GEMINI=1 uv run --frozen pytest -q tests/process/test_gemini_live.py
GRAPHENE_RUN_DOCKER_SMOKE=1 uv run --frozen pytest -q tests/unit/orchestration/test_sandbox.py
GRAPHENE_CHECK_EXECUTOR=host-sandbox uv run --frozen graphene mission demo
```

`GRAPHENE_CHECK_EXECUTOR` selects how `fixture-tests` checks run on the `gemini-adk` path: `docker` (default) or `host-sandbox` (macOS `sandbox-exec`, check subprocess registered in the owned-process registry). Any other value fails closed with `GRAPHENE_CHECK_EXECUTOR must be docker or host-sandbox`. The darwin-gated tests in `tests/unit/orchestration/test_host_check_runner.py` drive the host runner through a fake two-worker mission; every worker attempt also binds a `worker-provider-receipt` evidence artifact that `store.verify` resolves by digest.

`graphene mission demo` is the credential-gated live Taskmaster planner/worker entrypoint; it has no fake or replay fallback. Its 2026-08-23 two-worker provider receipts are historical earlier-runtime evidence; the current recovery runtime is **NOT PROVEN** live (see [Proof](PROOF.md)). Live Firestore/Cloud commands require the exact project checks in [Alex cloud setup](ALEX_CLOUD_SETUP.md). Docker, real Cloud Run/Firestore, benchmark results, and the submission video remain **NOT PROVEN**. Do not convert required deterministic tests into skips.

Local database inspection is deliberately explicit: `graphene mission db status` reads the schema ledger, `graphene mission db verify` verifies every v2 mission, and `graphene mission db migrate --dry-run` only reports the safe export-and-new-store action for a v1 database. It does not rewrite legacy state.

## Contribution rules

- Preserve the mission/legacy-lineage domain split and strict schemas.
- Add the smallest runnable regression for non-trivial logic.
- Keep operator/external effects explicit and opt-in.
- Update [`contracts/product_proof.json`](../contracts/product_proof.json), [known limitations](KNOWN_LIMITATIONS.md), and the [implementation report](IMPLEMENTATION_REPORT.md) when proof changes.
- Run relative-link and documentation-truth tests after documentation edits.
- Never commit captured credentials, private source, absolute local paths, or unredacted provider output.

CI jobs and supported platform claims are defined in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
