# morning.md — 2026-09-23 — the terminal directive

(In progress: rewritten at every milestone. Last night's is `docs/process/morning-2026-09-21.md`.)

## Rollback, first

Before the first change: `main` on GitHub was `ed010ca` (your merge of PR #26). This run works on the
branch `terminal`, cut from it. To go back to where you were:

```
git checkout main && git reset --hard ed010ca   # local main was 6cece1c, 43 behind; this brings it level
```

## Where the run is

- **Milestone 1, the plan as text: done.** `graphene plan --text` prints the tree one line a node;
  `graphene plan edit [id]` and `graphene node edit <id>` open it in your `$EDITOR`, and what you save
  is applied, all of it or none; `graphene plan propose -` reads the same text from an agent (JSON is
  still read); `propose -` at a terminal with nothing piped says so and exits; `graphene plan undo` puts
  back your last act. A new Claude Code session is taught the text whether or not a plan exists yet.
  Proved by `tests/test_plan_text.py` and `tests/test_plan_text_cli.py` (26 tests; `propose -` on a
  real pseudo-terminal).
- Next: the run (Ctrl-C, the tail, needs in flight, the lock), hand-backs with offers, the planner
  (`graphene ask`), the TUI, the README, the third test.

## Your afternoon, read from the record

Your `DIRECTION.md` and `morning.md` had unsaved edits in the working tree. They were formatting only
(an editor renumbered decisions 13–27 as 1–15 and broke some code spans); no word changed. I kept a
copy in `local/alex-editor-2026-09-23/` and worked from the committed text.
