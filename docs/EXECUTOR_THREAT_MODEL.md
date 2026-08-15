# Fixed-test executor threat model

Status: local macOS component and CI boundary, 2026-08-13.

The supported input is Graphene's frozen, sanitized Auth fixture and its fixed `python -m pytest -q -p no:cacheprovider` command. Arbitrary repositories, arbitrary commands, package installation, and network access are not supported.

The candidate checkout may contain untrusted runtime-written Python in a frozen mutable path. Before pytest starts, Graphene creates a new temporary test view containing only the current bytes of contract-listed tracked paths and existing mutable paths. Files are opened directory-relative with `O_NOFOLLOW`; ambient checkout files, symlinks, binary files, and oversized files do not enter that view. The scoped runtime can therefore test its authorized candidate bytes but cannot use pytest to read other checkout content.

On macOS, `sandbox-exec` additionally denies network, fork, broad process information, sysctl (including raw `SYS_sysctl`), and writes outside a separate temporary scratch directory. Standard input is `/dev/null` and the environment is allowlisted. Pytest output is capped and transient; public events store only status, counts, and digests.

Host assumptions and limits:

- Graphene and SQLite run under an honest, dedicated host account. This is not malicious-admin resistance.
- Every contract-listed tracked file is intentionally readable to tests and must be sanitized public fixture data.
- The sandbox protects host paths outside the temporary view, but macOS `sandbox-exec` is deprecated platform machinery, not a general multi-tenant isolation guarantee.
- Linux and the shipped Docker image currently fail closed because no equivalent executor is implemented. The full v2 workflow is therefore unsupported there even though the legacy HTTP service can start.
- A crash may leave an operating-system temporary directory until normal OS cleanup; no durable evidence points to its private bytes.

The regression for the repo-internal read channel is `test_fixed_tests_cannot_read_ambient_checkout_files`. Host filesystem, stdin, parent environment/argv, network, fork, symlink, timeout, and output behavior remain covered in `tests/unit/execution/test_adapter.py`.

## CI and platform contract

The CI workflow keeps platform claims visible rather than treating operating
systems as interchangeable:

| Runner | Executed gate | Supported claim |
| --- | --- | --- |
| Python 3.13 on `macos-15` | Complete `tests/unit`, `tests/integration`, `tests/process`, and `tests/adversarial` suites; MCP STDIO process tests; installed CLI help and canonical NDJSON smoke | The frozen fixture's fixed tests use the checked macOS `sandbox-exec` profile |
| Python 3.13 on `ubuntu-24.04` | The two fixed-test boundary regressions plus the verified-replay process test and CLI smoke | Linux reaches the explicit `fixed tests require an available OS sandbox` failure and does not execute hostile fixture tests; the checked-in replay remains read-only and portable |
| Node 22 on `ubuntu-24.04` | Dependency-free frontend tests and JavaScript syntax checks | Browser-side deterministic logic only; no Python executor claim |

The macOS job is the only job that runs the full v2 human workflow because that
workflow invokes the fixed test. The Linux job is a negative portability gate,
not an executor certification. The Dockerfile is Linux-based, so its legacy HTTP
server can start but the v2 fixed-test workflow remains unsupported and fails
closed. No CI job uses cloud credentials, invokes a real model, deploys a service,
or validates Firestore residency.

Stable local equivalents are:

```bash
uv lock --check
uv sync --frozen
uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py
uv run --frozen pytest -q tests/process/test_mcp_stdio.py
uv run --frozen graphene --help
node --test frontend/test/*.test.mjs
node --test tests/frontend/*.mjs
node --check frontend/src/app.mjs frontend/src/graph.mjs frontend/src/workflow.mjs
node --check backend/graphene/viewer/static/reducer.mjs backend/graphene/viewer/static/viewer.mjs
```

The separate MCP command is a named CI gate and is excluded from the preceding
aggregate command. CLI NDJSON behavior is covered both by the CI process smoke and
`tests/process/test_v2_process.py`.
