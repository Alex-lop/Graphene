# Verification commands and evidence

The verification started at PR #60's recorded head, `2a2c6fbb`, restored as `night/graph-edit` with Alex's explicit direction. It had already merged into main at `1588482c`; comparing main...night/graph-edit would now hide its changes. The test inventory came from `git diff e15d66a1..2a2c6fbb --stat`. The about-30-commit series is based on the restored night/graph-edit tip. A prior delivery opened PR #61 against main and Alex merged it; this verification run leaves that PR untouched and prepares a separate draft against night/graph-edit.

Run checks in the fresh clone, never Alex's Desktop checkout:

```sh
export ZDOTDIR="$(mktemp -d)"
export NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off
export GRAPHENE_TOKENFACTORY_URL=http://127.0.0.1:9
uv run ruff check
uv run pytest -q -n auto
cd editors/vscode
npm test
npm run package
cd e2e
E2E_APP=cursor npm test
E2E_APP=cursor npm run home
E2E_APP=cursor npm run draw
# Also verified in local VS Code (the default application):
npm run home
npm run draw
```

The same verified working files were kept while the commits were arranged by probe, regression/fix, documentation and report. There was no source rewrite between that verification and the commit series. Checks remained green before each commit; documentation was also checked against the existing reference word cap (5,298 words, cap 5,300).

| Check | Result |
|---|---|
| Ruff / diff whitespace | passed |
| Python, final complete run | 2,945 passed; 21 skipped; five subtests passed; one existing multiprocessing warning |
| Extension typecheck + node tests | 137 passed |
| Extension build + local VS Code smoke + VSIX package | passed |
| Cursor graph walk | 6 harness unit tests; three tasks drawn in sidebar and panel |
| Cursor Home | setup, plan, Start, review, send back, Exact all passed |
| Cursor Draw | shared drafts, panel close, window reload, attempts, ownership, one inline refusal, held-task edit all passed |
| VS Code Home / Draw | both passed, including the expanded persistence and refusal walk |
| Original #60 tests under source mutation | 27 controls passed; 26 caught initially; strengthened no-task test catches all 27 |
| Original real-editor walks under mutation | both controls passed; wrong attempt count and disabled Exact hold each made its walk fail |

`probes/red-tests.txt` keeps the red results before fixes. Every live claim below has a rerunnable probe and output; the live probes use disposable repositories and the fake/dead Nebius environment.

| Probe | Command from clone root | Kept output |
|---|---|---|
| Shell paths, payload field, manual edits, empty work | `uv run python dev/process/verify/probes/boundaries.py` | `probes/boundaries-before.txt` |
| Legacy recording-only hooks | `uv run python dev/process/verify/probes/legacy_hooks.py` (file replay, no live vendor) | `probes/legacy-hooks.txt` |
| Exact defaults | `bash dev/process/graph-edit/probes/exact.sh` | `probes/exact.txt` |
| Edits by task state | `bash dev/process/graph-edit/probes/edits.sh` | `probes/edits.txt` |
| Codex patch/shell before and after | `uv run python dev/process/verify/probes/live_codex.py --forks 1` | `probes/codex-before.txt`, `probes/codex-after.txt` |
| Three real attempts | same script with `--forks 3` | `probes/codex-three-attempts.txt` |
| Hook crash and timeout, marker proves execution | `uv run python dev/process/verify/probes/codex_failures.py` | `probes/codex-hook-failures.txt` |
| Session before init | `uv run python dev/process/verify/probes/codex_mid_session.py` | `probes/codex-mid-session.txt` |
| Source mutations of #60 | `uv run python dev/process/verify/probes/mutations.py`, then `--strengthened` | `probes/mutations-before.txt`, `probes/mutations-after.txt` |
| Real editor mutations of #60 | `uv run python dev/process/verify/probes/e2e_mutations.py` | `probes/e2e-mutations.txt` |

Live Codex was 0.167.2 on gpt-6.1-sol with xhigh. Its probes require an isolated, authenticated `CODEX_HOME`, never `~/.codex`: only scratch config/trust was changed. Hook automation explicitly trusted the fixture with Codex's invocation flag; that does not prove a normal installation has trusted its hooks. The native PreToolUse events are preserved without credentials in `tests/fixtures/codex-hooks-0.167.2.json` and replayed in CI.

The pre-fix Codex run used a source archive of `2a2c6fbb` on PYTHONPATH and `--without-hooks`; after-fix runs used this branch. All three real attempts denied outside.txt, passed the inside check, and c won by finish order before the allowed change merged. Model token totals are in the output; no list price was available, so the $0 meter line does not claim the Codex service is free.

The failing inherited-environment run had 400 failures; clearing the actual marks gave the original 2,927 passes. Moving mark isolation to the root conftest then fixed the four dev harness failures left outside tests/. The final suite includes the captured-payload, malformed-input, stale-store, installer, worktree and concurrent-human-edit regressions.

Cursor and Copilot's own agents were not invoked. Claude's three rows were exercised by payload and mutation, not new live Claude calls. No Nemotron endpoint, release, marketplace publication or housekeeping action was performed.
