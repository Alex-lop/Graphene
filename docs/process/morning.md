# morning.md — 2026-09-23 — the terminal directive

(Current at every milestone of this run. Last night's is `docs/process/morning-2026-09-21.md`.)

## 1. What you can run in five minutes

Paragraph in, tree out, prune, run, on real agents, in WezTerm:

```
cd ~/Desktop/AllThingsAgenticHackathon && git checkout terminal && uv tool install --editable . --force
docs/proof/try.sh                        # builds ~/graphene-try (the feeds task) and prints the rest
cd ~/graphene-try
wezterm cli split-pane --right --percent 50 --cwd "$PWD" -- graphene watch
claude                                   # then paste the paragraph try.sh printed, or write your own
```

On the right the tree appears, every line `?` (about 35 seconds). `j` `k` to read it, `Enter` on a
leaf for all of it. Prune one thing: `e` on a leaf opens its contract in your editor. Try taking a
path out of a scope, so that it comes back. `y` on each sub-goal accepts it, or `:plan accept`
accepts all. `R` runs. Leaves go `●`, then `✓`; the node pane says which executor, where, what it did
last and how many seconds ago (`l` is its output). The leaf you starved comes back `↩`, and the node
pane offers `w` (widen to what it wanted) and `b` (a sibling for it). Press `w`, then `R`.
`git log --graph --oneline` reads as the tree. `docs/assets/watch.gif` is that scene, recorded.

## 2. What is waiting on you

- **One PR, `terminal` into `main`:** (link below, under the branches). CI is green on every push.
- **Your working-tree edits** to `docs/DIRECTION.md` and `docs/process/morning.md` were formatting
  only: an editor renumbered decisions 13 to 27 as 1 to 15 and broke some code spans, and no word
  changed. A copy is in `local/alex-editor-2026-09-23/`. I worked from the committed text.
- **The decisions to strike** are 28 to 38 in `docs/DIRECTION.md`, each with its reason. Read these
  four first:
  - **28**: a paragraph (240 characters or more) typed into a session becomes a tree before any code,
    and the session's writes wait until you accept. This is the directive's sentence made binding.
    Taught only at session start, a real session ignored it and wrote the code.
  - **29**: the grammar of the text form, and how an edit applies. Three-way, all or nothing, refused
    by line number.
  - **30**: the two keys I decided, `?` and `n`, where the directive's list collided with itself.
  - **31**: the planner prints its proposal and holds no write tool.
- **This repository's own store** still has the goal "why this repo's plan exists, in your words"
  (you typed the placeholder from an old morning.md on the 21st) and five proposals from the 20th.
  It is yours; I left it. `graphene plan goal '…'` or `graphene plan archive` clears it.

## 3. The map of the code

`src/graphene_debrief/`, 10,300 lines. Read in this order; each line ends with where its tests are.

- `plan.py` (1,730): what the product means. Standard library only, because the hook imports it.
  Node, `caller()` (who is a person), scope globs, the tree (`kids`, `above`, `below`, `validate`,
  `ready`), git reads, the operations (`propose`, `accept`, `edit`, `drop`, `start`, `finish`,
  `release`), `not_here` (a need done elsewhere), `offers`/`wanted`/`widen`/`sibling` (a hand-back's
  fixes), `undoable`/`undo`. Tests: `test_plan.py`, `test_tree.py`, `test_run_live.py`.
- `plan_text.py` (930): the plan as text. `parse` (a line belongs to the node line just above it,
  at one column, or is refused by number), `render`, `apply` (three-way, one transaction),
  `edit_loop` (the editor, refusals written under their line). Tests: `test_plan_text.py`,
  `test_plan_text_cli.py`, and `test_plan_text_findings.py`, where each of the 68 tests guards a
  finding the adversaries made.
- `gate.py` (480): what the Claude Code hooks answer. It includes `paragraph()` and the session-start
  teaching (`TEACH`, `IN_FORCE`). Tests: `test_gate.py`, `test_hooks.py`.
- `run.py` (610): `graphene run`, in place and `--parallel`. `run_node` (Popen, streamed output, the
  `attempt` entry, Ctrl-C), `sweep`, `land`/`park`, `live`/`tail` (what the screen shows of a running
  leaf). Tests: `test_run.py`, `test_parallel.py`, `test_run_live.py` (real SIGINTs).
- `ask.py` (150): the planner: prompt, the proposal read from what it prints, one retry. Tests:
  `test_ask.py`.
- `tui.py` (730): `graphene watch`. `Watch` is the app; `PlanTree` reads the two-key sequences;
  `detail()` is the node pane; `_cli()` runs a key's command in-process. Tests: `test_tui.py`
  (Textual's pilot, at 80 and 120 columns).
- `plan_cli.py` (950): the `plan`, `node`, `watch`, `ask` and `run` commands; `write()` wraps every
  act of yours (undo, and which repository). Tests: `test_plan_cli.py`, `test_plan_text_cli.py`.
- Unchanged tonight: `node_record.py` (a node's record), `store.py` (SQLite; `claim()` now joins an
  outer one), `sources/claude_code.py` (hook entry, transcripts), `graph.py`/`plan_view.py`/`server.py`
  (the page), `attribute.py`, `commits.py`, `record.py`.

To change what a line of the text means, start at `plan_text.parse` and add a case to
`test_plan_text_findings.py`. To change a key, it's `Watch.BINDINGS` and a test in `test_tui.py`.

## 4. What was verified, and how

- **The whole scene on real agents** (23 September, the feeds task, one run):
  - The paragraph typed into a session gave a tree in 35 s, no file touched.
  - Accepted, `run --parallel 4` did the four leaves in 50 s.
  - The result scored 18/20 on the hidden acceptance (the 2 misses want what the paragraph never
    said) and 12/12 held-out. The untouched repo scores 10/20 and 0/12.
  - The run directories are in the session scratchpad (`pane2/`); they are not committed.
- **The same paragraph before the prompt-time rule:** the session wrote the code in 48 s and
  proposed nothing (`pane1/`). That is why decision 28 exists.
- **`graphene ask` on the same paragraph:** 44 s, seven nodes with needs, first try.
- **The screen in a real WezTerm** (an isolated mux, 80×24, read back with `wezterm cli get-text`).
  That run found a killed-after-done executor, the ▶ glyph clash, and a status line that did not
  fit; all three are fixed.
- **The text form:** 54 adversarial agents (49 findings), a re-check of each (33 fixed, 15 partly),
  then a hunt for the rebuild's own regressions (12, all fixed). Each is guarded by a test.
- **Ctrl-C**, in place and in parallel: real SIGINTs in `test_run_live.py`, which checks that no
  executor survives.
- **Tests:** 505. Ruff clean. CI green on Linux and macOS, Python 3.12 and 3.13, on every push.
- **The third test:** see below.

## Not verified

- **You, at the keys.** Nobody has pruned a tree with these keys but me through a mux and the
  stand-ins through the equivalent commands. What you feel at `y` and `d` is what matters and is
  unmeasured.
- **A hand-back taken with `w` on a real run.** The recording's scene is set up to produce one. The
  offer code is covered by tests with real refusals, not by an executor that chose to come back.
- **WezTerm's own window.** I checked its mux, not the GUI: fonts, mouse capture, whether Shift-drag
  selects text over the screen.
- **The paragraph rule's 240 characters** against anyone but you: one person's paragraph, one
  person's one-liners.
- **Codex as planner or executor tonight:** `--with 'codex exec --sandbox read-only'` should work for
  `ask`, and was not run.
- **A stray line**, once, at the top of a 36-column pane of `graphene watch`, gone on the next redraw.
  I could not reproduce it or say where it came from.

## The third test

(Filled in when its report is done: `docs/test/results-2026-09-23.md`.)

## Questions (only what blocks the next step)

1. Is 240 characters the right line between "do it" and "plan it" for you (decision 28)? Nothing
   waits on it, but everyone who tries Graphene meets it in the first minute.

## Rollback

Before the first change `main` on GitHub was `ed010ca` (your merge of PR #26); this run is the
branch `terminal`, cut from it. Nothing here touched `main`. To put your local `main` where GitHub's
is (it was 43 behind, at `6cece1c`):

```
git checkout main && git reset --hard ed010ca
```

## State of every branch

- `terminal`: this run, pushed; one PR into `main`.
- `main` (GitHub): `ed010ca`, untouched. Local `main`: `6cece1c`, 43 behind GitHub, untouched.
- `tree`: `9c21715`, merged into `main` by you (PR #26).
- Everything else (`agent/*`, `codex/*`, `lane/*`, `n*`, `graph`, `plan`, `rebuild`) is as it was.
