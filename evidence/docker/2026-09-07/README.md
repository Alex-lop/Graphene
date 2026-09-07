# Docker check executor smoke — GitHub Actions

| Field | Value |
|---|---|
| Date (UTC) | 2026-09-07 |
| Run id | 34159157244 |
| Run URL | https://github.com/Alex-lop/Graphene/actions/runs/34159157244 |
| Job | `Python 3.13 / Linux Docker executor smoke` (id 101857158715) |
| Job conclusion | success |
| Job started / completed (UTC) | 2026-09-07T20:22:33Z / 2026-09-07T20:22:55Z |
| Head commit | 2e6370fd6df5e6735440a8ebb8d70b2eaeaa96d9 |
| Runner | ubuntu-24.04 |
| Image digest | sha256:9d2bf8e8515fc699f59227eb3bd76c092cc7a0f74582bc8ed3cf0207681ea2bf |
| pytest summary | 19 passed in 2.08s |

## Commands the job ran

```
docker build -f docker/executor.Dockerfile -t graphene-executor:py313-pytest .
docker image inspect --format '{{.Id}}' graphene-executor:py313-pytest
GRAPHENE_RUN_DOCKER_SMOKE=1 uv run --frozen pytest -q tests/unit/orchestration/test_sandbox.py
```

The digest above is the second command's output line. The third command ran with
`GRAPHENE_RUN_DOCKER_SMOKE: "1"` in the step environment, which is the only way
`test_real_docker_executes_only_the_scoped_fixture` stops skipping: 19 passed is
18 offline boundary checks plus that one container run.

## What this proves

On the runner's rootful Docker daemon, `DockerExecutor` built the immutable
executor image from `docker/executor.Dockerfile`, created a container from that
exact freshly built image (`--pull never` means the daemon could not fetch a
different one, and the runner started with no image under that tag), ran one
scoped fixture pytest check inside it against a read-only scoped repository
view, and returned exit code 0 with `timed_out`, `oom_killed` and
`output_truncated` all false and `cleanup_complete` true. The container boundary
flags are the ones pinned verbatim by `tests/unit/orchestration/test_sandbox.py`
(`--network none`, `--user 65532:65532`, `--cap-drop ALL`, `--read-only`,
`--pull never`, `--pids-limit 64`, and the 512 MiB memory/memory-swap pair). This
is the first Linux evidence that the real check executor runs, not only that
unsupported platforms fail closed.

## What it does not prove

No live mission ran: no model, no planner, no scheduler, no approval. No policy
template other than the fixture pytest argv was executed. There is no Linux
scripted-local loop — the scripted fixture path still requires macOS
`/usr/bin/sandbox-exec`. Cancellation and reconciliation under Docker were not
exercised. Local macOS runs of the same smoke are developer convenience, not
this evidence; this file records only the CI job named above.
