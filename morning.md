# morning.md — 2026-09-25 — the Nemotron directive

(Current at every milestone of this run. Last run's is `docs/process/morning-2026-09-24.md`.)

**Blocker, first: this run has no Token Factory key and no Sandboxes client.** At 01:15 EDT,
`NEBIUS_API_KEY` was not set in the shell this run works in. `GET /v1/models` answered `401 token is
not present`. The ConTree CLI and SDK are not installed. Following the directive's step 3, everything
that does not need inference is built and tested against a recorded fake endpoint. The same goes for
the sandbox placement, against a test double. I check again at every milestone. To give the run
access without stopping it: put `export NEBIUS_API_KEY=…` (and `NEBIUS_AI_PROJECT=…` for Sandboxes)
in `~/.zshenv`. Each new shell this run opens reads that file.

## Rollback

Before the first change, `main` on GitHub was `cd13cbe` (your merge of PR #28). This run is the
branch `nemotron`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard cd13cbe
```
