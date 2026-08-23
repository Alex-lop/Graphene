# Night report — 2026-08-23 live North Star run

Unattended session executing `GRAPHENE_NIGHT_RUN_DIRECTIVE` v2. Read in this
order: checkpoints, commits, what flipped, spend, authority use, blockers,
morning checklist.

`AUTHORITY_DIGEST` = `c5b116e77d0b95a87901f3b19ce1d1d86dec077147c9570220e3d44ab48e7a06`
(SHA-256 of the directive as handed over; the file itself is gitignored under
`local/` and never enters a commit). Every delegated approval below cites it.

## 0. Checkpoint timeline (UTC; local is EDT, UTC−4)

| When | Phase | Spend so far | Attempts | State / next intent |
|---|---|---|---|---|
| 12:06 | Preflight start | $0.00 | 0 | Directive digest recorded; `GEMINI_API_KEY` blanked in `.env`; secret scan clean; baseline matrix started |
| 12:12 | Preflight done | $0.00 | 0 | Baseline green (1923 passed, 4 skipped); target materialized; doctor ready (`vertex_ai`); Phase 4 watcher build launched in a worktree (zero-cost). Next: provider-side receipt stamps, then Phase 1 live run |

## 1. Commits (oldest first)

| Commit | Purpose |
|---|---|
| _(preflight)_ | `scripts/secret_scan.py` (location-only scanner), preflight doctor evidence, this report |

## 2. What is proven / what did not flip

Nothing has flipped yet. Labels flip only in the commit that carries the
evidence they cite.

## 3. Spend log

Pricing source: Google "Gemini Developer API pricing" page
(`ai.google.dev/gemini-api/docs/pricing`, last updated 2026-08-13 UTC):
**Gemini 3.5 Flash, paid tier — $1.50 / 1M input tokens, $9.00 / 1M output
tokens, thinking tokens billed as output.** Vertex AI per-token pricing for the
same model is published as identical; the Vertex pricing page itself was not
machine-readable from this session (it rendered as an empty shell), so the
AI-Studio figure is the cited rate and the morning check should confirm the
Cloud Billing report agrees. Cost per attempt is computed from the receipt's
provider-reported `prompt_tokens` / (`candidate_tokens` + `thought_tokens`)
and rounded **up** to the cent. Planner calls are billed too and are logged
the same way.

| # | When | Mission | Role | Model | Input tok | Output tok (incl. thought) | Cost (ceil) | Running total |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | $0.00 |

Caps: $20 session, ~$5 per mission, 12 worker attempts fallback. Remaining: $20.00.

## 4. Authority-use log

| When | Action | Mission | Detail |
|---|---|---|---|
| 12:06 | Blanked `GEMINI_API_KEY` in `.env` | — | The one permitted `.env` edit (§2). Blanking does **not** revoke the key server-side — Alex must rotate it himself. Doctor afterwards: `configuration_ready: true`, `credential_mode: vertex_ai` |

## 5. Blockers and open questions

- **Directive location discrepancy.** The directive says it lives at
  `local/GRAPHENE_NIGHT_RUN_DIRECTIVE.md`; it was handed over as the untracked
  file `docs/GRAPHENE_NIGHT_RUN_DIRECTIVE (1).md`. A byte-identical copy was
  placed at the `local/` path (same digest); the `docs/` copy is left alone and
  is never staged. Recommended default: delete the `docs/` copy after review so
  it cannot be committed by accident.
- **`GRAPHENE_ULTRA_DIRECTIVE.md` is absent** from the repo and `local/`. Its
  Shadow v0 / demo-target specifications are therefore taken from the runbook,
  `docs/SHADOW_ADAPTER_SPEC.md`, and the current code, which the directive
  ranks above it anyway.
- **No `tmux` / `asciinema` on this machine.** `caffeinate -dims` runs as a
  detached background process for the whole session; terminal recordings use
  `script`(1). Installing tmux was not necessary and was not done.
- **`.env` is not auto-loaded by Graphene.** Live commands source a gitignored
  loader (`local/night_env.sh`) that exports only the three Vertex values plus
  the run gates; nothing prints values.

## 6. Morning checklist for Alex

1. Rotate `GEMINI_API_KEY` server-side (Google AI Studio) — blanking the local
   file does not revoke it.
2. `git log --oneline origin/main..main` and review commits in order.
3. `scripts/morning_verify.sh` (lands later tonight) — one command re-runs the
   night's verification.
4. `git remote -v` must equal the preflight snapshot below; `HEAD` is simply
   ahead of `origin/main`.
5. Push when satisfied. Nothing was pushed tonight.

### Preflight integrity snapshot

```
origin  git@github.com:Alex-lop/Graphene.git (fetch)
origin  git@github.com:Alex-lop/Graphene.git (push)
HEAD    11251c932f00c07ed4c6198380976463cb5587d7   (origin/main was e1e580d7, one commit behind)
```

### Preflight facts

- Baseline on `11251c9`: `uv lock --check` ok; `uv sync --frozen` 73 resolved /
  69 checked; `pytest tests/unit tests/integration tests/process
  tests/adversarial --ignore=tests/process/test_mcp_stdio.py` → **1923 passed,
  4 skipped** (the four opt-in gates) in 316 s; `ruff check .` clean;
  `compileall` ok; `git diff --check` clean. No baseline repair was needed.
- Secret scan (`scripts/secret_scan.py --commits 30 --include-untracked`):
  20 findings, all of them deliberately fake secrets inside redaction test
  fixtures under `tests/` (and the same lines in their introducing commits);
  none in source, docs, contracts, or evidence. `.env` and `local/` are
  gitignored (`git check-ignore` confirmed).
- Capture-script review: `scripts/capture_north_star_evidence.py` ingests no
  repository files at all — it builds its own fixture repo and writes only
  identifiers, digests, and counts. It cannot include `.env`, `local/`, or
  credential paths. No change needed.
- Demo target: materialized at `~/north-star-target` from
  `demo/north_star`; policy `policy_0fe143f50ccfeb433952e23c`; target suite
  `52 passed`.
- Doctor (`evidence/north_star/2026-08-23-doctor-preflight.json`):
  `gemini_preflight.configuration_ready: true`, `modes.gemini-adk.credential_mode:
  vertex_ai`, `check_executor.requested: host-sandbox, supported: true`,
  `policy.status: usable`, `platform_isolation.status: usable`. The JSON
  contains no project id, path, or credential.
