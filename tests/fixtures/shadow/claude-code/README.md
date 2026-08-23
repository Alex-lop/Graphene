# Shadow claude-code fixture

`session_v1.jsonl` is **synthetic**. No agent produced it, no path, session
id, tool-call id, or message in it is real, and the repository it names
(`/home/dev/proj`) does not exist. It was written by hand to mirror the record
shapes of a real Claude Code 2.1.x session file (the same top-level keys,
`message.content` blocks, `tool_use`/`tool_result` pairing, and bookkeeping
record types) so the `claude-code` adapter can be tested without any private
transcript. It proves nothing about any real session; the real-session smoke
is reported as counts only in `contracts/product_proof.json`.

## What the 35 records contain

| lines | what | why it is there |
|---|---|---|
| 1–3, 6–7, 12, 35 | `mode`, `permission-mode`, `atis-latch`, `ai-title`, `last-prompt`, `file-history-snapshot`, `queue-operation` | bookkeeping records: skipped and counted by type, never events |
| 4 | user prompt (string content) | opens the session |
| 5 | `attachment` | harness-injected context: skipped and counted |
| 8 | assistant `thinking` block | hidden reasoning: never ingested, counted as skipped |
| 9 | assistant `text` | an agent message with no claim in it |
| 10–11 | `Read` call and result | `file_read` of `app/greet.py` |
| 13–14 | `Edit` call and result | `file_edit` with the digest of `new_string`, never the text |
| 15 | assistant `text` "I fixed the bug …" | a `fixed` claim with no check since the edit: `claimed-without-evidence` fires |
| 16–17 | `Bash` `pytest -q`, result `is_error: false` | `check_run` / `check_result` exit 0, family `pytest` |
| 18 | `system` `turn_duration` | bookkeeping: skipped and counted |
| 19 | second user prompt | a `user_message` segment boundary |
| 20–21 | `Bash` `gh pr list` with a fake `GITHUB_TOKEN=ghp_…` in the environment, result `is_error: true` with `Exit code 1` | `network_op`; the token is `<redacted>` in the excerpt; exit code parsed from the result |
| 22–23 | `Bash` `rm … && sed -i … && echo > /home/dev/scratch/log.txt` | inferred `file_delete`, `file_edit`, and an outside-repository `file_create` (`scope-drift`) |
| 24–25 | `Write` call and result | `file_create` of `tests/test_greet.py` |
| 26–27 | `TodoWrite` call and result | `tool_call`; a `plan_marker` segment boundary |
| 28–29 | `Read` of the file written at line 24 | a read-after-write edge between segments |
| 30–31 | `Bash` `uv run pytest -q …`, result exit 0 | the passing check that backs the final claim |
| 32 | assistant `text` "Done. All tests pass. … /home/dev/scratch/log.txt" | a backed `checks_pass` claim; the home path collapses to `~` when the adapter's home is `/home/dev` |
| 33 | user record with `isMeta: true` | a `system` actor message |
| 34 | `type: "future-record"` | a record type the adapter has never seen: an explicit `unknown` event |

Ingest yields 30 events (25 observed, 5 inferred, 2 claims, 1 unknown), three
segments, two edges, and the findings `claimed-without-evidence`,
`scope-drift`, `write-overlap`, and `network-or-install`.
`tests/unit/shadow/test_claude_code_adapter.py` pins all of it.
