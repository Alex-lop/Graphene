# Redacted v2 terminal transcript

Captured on 2026-08-13 on macOS with Python 3.13.9, `google-adk==2.5.0`, and `mcp==2.0.0`. IDs, digests, timestamps, and absolute temporary paths below are redacted; the executable assertion is [`tests/process/test_mcp_stdio.py`](../tests/process/test_mcp_stdio.py).

Terminal A bootstraps the private run:

```text
$ graphene --json run baseline_max_attempts --profile platform-maintainer@1
{"database":"<private-runtime>/lineage.sqlite3","projection_sha256":"<sha256>","run_id":"<run-id>","verified_head":{"event_count":1,"event_sha256":"<sha256>","run_id":"<run-id>","seq":1}}
```

Terminal B starts before the agent call and follows canonical committed NDJSON:

```text
$ graphene --json watch <run-id>
{"event_type":"run.started","run_id":"<run-id>","seq":1,...}
{"event_type":"invocation.started","run_id":"<run-id>","seq":2,...}
{"event_type":"tool.started","payload":{"operation":"read_file","status":"started"},"run_id":"<run-id>","seq":3,...}
{"event_type":"tool.completed","payload":{"operation":"read_file","path":"app/auth/limiter.py","status":"completed",...},"run_id":"<run-id>","seq":4,...}
```

Terminal C is an official MCP `ClientSession` connected to the installed `graphene-mcp` STDIO executable:

```text
stderr: GRAPHENE_MCP_STDIO_READY
client calls: read_file({"path":"app/auth/limiter.py"})
client receives, only after Terminal B flushes seq 4:
{"path":"app/auth/limiter.py","state":"PRESENT","content":"<authorized bounded bytes>",...}
```

The full test also proves exact six-tool schemas, protocol-only stdout, denial privacy, zero-argument completion, terminal rejection, restart verification, and interruption on uncertain EOF. The full human-loop process proof continues from exact feedback and approved memory into a fresh consumer, a fixed retest, checkpointed promotion, `why`, `inspect`, and restart-stable projection in [`tests/process/test_human_loop.py`](../tests/process/test_human_loop.py).

The abbreviated event lines above are explanatory excerpts, not stored-event exports. Use `watch --json` or `replay --json` for full canonical envelopes.
