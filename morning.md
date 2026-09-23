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
- **Milestone 2, the run and the hand-back: done.** Ctrl-C hands back what `graphene run` started, in
  place and in worktrees, and stops the executors (exit 130); releasing a running leaf stops its
  executor; a run that died is swept at the next one; a leaf whose need is done but not here (never
  landed, or uncommitted) waits and says why; git is asked before the write lock; each attempt's output
  streams to `.graphene/runs/<leaf>-<time>-<n>.txt`; a leaf that comes back offers `graphene node
  widen <id>`, `graphene node sibling <id>`, or waiting on the nodes its reason names. The `ingest/`
  refusal that bit three of your executors is gone. Proved by `tests/test_run_live.py` (13, with real
  SIGINTs) and `tests/test_gate.py`.
- **Milestone 3, the planner: done.** `graphene ask "<what you want>"` starts a planner with read-only
  tools (default `claude -p --tools Read,Grep,Glob`); what it prints is read as the plan's text and
  added as its proposals; `graphene node split <id>` asks it to cut a leaf. Run for real on the feeds
  task with your paragraph: 44 s, seven nodes with needs between them, first try, and a note that the
  zero-price rule would miss the legacy importer you said not to touch. `tests/test_ask.py`.
- **Milestone 4, `graphene watch` is the TUI: done.** Textual, one screen, vim keys (the list in the
  directive, all of it), every key a command it names on the bottom line. Checked in a real WezTerm
  mux at 80×24 (reading the screen back with `wezterm cli get-text`) and headless in
  `tests/test_tui.py`. `graphene watch --once` prints.
- **The text form, attacked:** 54 adversarial agents confirmed 49 findings against milestone 1; the
  parser was rebuilt (a line belongs to the node just above it, at one column, or it is refused with
  what to do), and a second pass is checking each finding against the rebuilt code.
- Next: the README and DIRECTION, the two-pane recipe and its recording, the third test.

## Your afternoon, read from the record

Your `DIRECTION.md` and `morning.md` had unsaved edits in the working tree. They were formatting only
(an editor renumbered decisions 13–27 as 1–15 and broke some code spans); no word changed. I kept a
copy in `local/alex-editor-2026-09-23/` and worked from the committed text.
