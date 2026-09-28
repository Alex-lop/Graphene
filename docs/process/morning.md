# morning.md — 2026-09-28 — the shaping directive

## The brief

**Do first**
1. The key in `~/.zshenv` (2 min): `export NEBIUS_API_KEY=…  NEBIUS_PROJECT_ID=…`, then open a new shell.
2. The access check, typed by you (1 min): `! uv run python docs/test/access.py` (the classifier refuses it to an agent).
3. The ladder: being built tonight (`docs/test/practice.sh`); this line says when it is ready.

**New tonight** (in flight, nothing merged yet; this list changes at every merge)
- nothing merged yet

**Decide**
- nothing yet

**Broken or risky**
- nothing yet

---

(Everything below the brief: decisions, evidence, screens, the state of every branch. The winning
run's morning is `morning-2026-09-26.md`.)

## Lanes in flight (00:35 start)

| Lane | What | Where |
| --- | --- | --- |
| A | the view seam, a top-down tree, a left-to-right graph with the critical path, the board's model and the planner that asks, the page's views | worktrees, one per piece |
| B | keys, standing conditions, plan size, `graphene config` | run through Graphene itself, in `~/graphene-night` (`docs/process/shaping/as-the-person.md`) |
| C | `practice.sh`, `PRACTICE.md`, the dry run, the sealed paragraphs and the pre-registration | worktrees |
| D | the shaping study's pre-registration and its board arm | worktree |
| E | twenty-plus ideas for Nemotron in the shaping loop, scored | worktree |

## Rollback

Before the first change, `main` on GitHub was `cb2ce54` (your merge of PR #30). This run is the
branch `shaping`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard cb2ce54
```
