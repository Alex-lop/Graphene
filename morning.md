# morning.md — 2026-09-24 — the polish directive

(Current at every milestone of this run. Last run's is `docs/process/morning-2026-09-23.md`.)

**State right now: the "before" is recorded, and four parts are being built in worktrees** (the
screen, the logic, the messages, plan first as a mode), from one shared vocabulary already on the
branch (`plan.reads`: one word, glyph and colour per state) and the `graphene plan first on|off`
setting. Branch `polish`, cut from `origin/main` at `2c86399` (your merge of PR #27).

## 1. Before and after

The "before" of every screen this run will change is recorded: the feeds task built by
`docs/proof/try.sh` at `~/graphene-polish`, a real Claude Code session typed the paragraph (a tree
in 29 s), real executors ran it (`R`, a sign-off, a leaf that came back wanting `cli/main.py`, `w`,
`R`, done), and `graphene watch` was driven in an isolated WezTerm mux at 80×24 and 120×36. The
"after" goes here as each fix lands.

## Rollback

Before the first change `main` on GitHub was `2c86399`. This run is the branch `polish`; nothing
touches `main`.

```
git checkout main && git reset --hard 2c86399
```
