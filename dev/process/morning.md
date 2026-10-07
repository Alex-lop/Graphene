# morning.md — 2026-10-07 — the meter

Rollback: `main` is untouched at `af3da2c`. To drop the night: close the PR, `git push origin --delete meter`.

## The brief

**1. Watch first:** not yet: the meter is being built.

**2. The bill:** $4.24 of $50. `auto` $3.94, `statements-practice` $0.23, `meter` $0.08.

**3. `auto`:** Tuesday asks: 8 of 12 yours at once and done; the 4 others waited on a board item they put up.
  The feeds paragraph: a tree once in three; twice one leaf of 8 paths with no board item, taken at once
  and done (18/20, 12/12). No threshold separates it. `dev/process/meter/auto-evidence.md`.

**4. Run in five minutes:** not yet.

**5. The README:** not yet.

**6. Decide:** 1. Codex: your ChatGPT login is revoked (`refresh_token_invalidated`). Run `codex logout && codex login`.
  Until then the Codex lane runs `codex exec --json` against Nemotron Super on Token Factory.

**7. Broken or risky:** your checkout's hook (plan first auto) now covers its worktrees, so this run works
  in a clone of its own outside your checkout. Your checkout and its plan were not touched.

---

## What was done, in order


- **23:26** Read the directive. Branch `meter` from origin/main `af3da2c`, in a clone outside your checkout.
  The directive is committed at `dev/process/directives/METER_DIRECTIVE.md`.
- **23:40** The night's ledger: $50 cap, nothing new past $45, a purpose on every row. The session was not
  started with `GRAPHENE_AGENT_LIVE_USD`; the directive's $50 line is the opening, so this run sets it to 50
  for its own live commands.
- **23:45** Real stream shapes, live: Claude Code 2.1.292 `stream-json` (Sonnet 5.5, 4 turns, $0.0623) and
  `codex exec --json` 0.151.0 (Nemotron Super on Token Factory, $0.0150).
- **00:03** The statements check: one tree-arm planning session put "half-even" and "vendor/" in the plan's
  goal and three conflicts on the board as plan-wide items, so all four conditions reached every leaf's
  contract. Nothing was changed. `dev/process/meter/standing-check.md`.
- **00:18** Lane 1 merged: under `auto` every ask is proposed; one leaf with no board item and at most 8
  paths is yours at once.
- **00:20** Live, the old node count made a leaf in a sub-goal of its own wait. Fixed: the rule counts
  leaves (`c0d8379`). Three more rounds ran on the fix.
- **00:25** The move: `docs/` keeps what you need to use Graphene, `dev/` holds how it gets built.
- **00:30** `meter` pushed for CI.
