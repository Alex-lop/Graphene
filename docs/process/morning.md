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

- **One PR, `terminal` into `main`:** https://github.com/Alex-lop/Graphene/pull/27. CI is green on
  every push but one: `f10387e` failed a timing test on macOS (the hook with a locked store took
  2.05 s against 2.0), because the paragraph rule had made every prompt write. `c3003be` fixed it.
- **The hold (decision 40).** From 09:15Z until you typed "just do it", this session and every
  agent it started could not write. The hook had read a subagent's report as your paragraph. I did
  not route around it. The cause is fixed (`bf82b47`). A report that quoted "just do it" also lifted
  the wait once, in your name. That is closed too, and it is the finding I would read first.
- **The third test says the tree did not save attention** (`docs/test/results-2026-09-23.md`,
  audited). Where a tree existed, the paragraph arm won on every attention measure, and both arms
  got the same outcome. Misunderstandings caught before code: 0 or 1 of 3. The possible one is you
  putting back a line of your own paragraph that the proposal had dropped. These are stand-ins and
  modelled seconds, two runs an arm. Your own ten-minute run (the recipe is in
  `docs/test/PROTOCOL.md`) outranks it. Without a paragraph run of the same card beside it, that run
  shows no saving either way.
- **The decisions to strike** are 28 to 40 in `docs/DIRECTION.md`, each with its reason. Read these
  first:
  - **28**: a paragraph (240 characters or more) becomes a tree before any code, and the session's
    writes wait.
  - **39**: what the closing review and its recheck changed. It holds one question about your goal.
  - **40**: the hold.
  - **31**: the planner prints its proposal and holds no write tool.
- **This repository's own store** still has the goal "why this repo's plan exists, in your words"
  (you typed the placeholder from an old morning.md on the 21st) and five proposals from the 20th.
  It is yours; I left it. `graphene plan goal '<yours>'` replaces the goal, and `graphene node drop
  <id>` removes each proposal (`plan archive` touches only what is done or dropped).

## 3. The map of the code

`src/graphene_debrief/`, 11,000 lines. Read in this order; each line ends with where its tests are.

- `plan.py` (2,000): what the product means. Standard library only, because the hook imports it.
  Node, `caller()` (who is a person), scope globs, the tree (`kids`, `above`, `below`, `validate`,
  `ready`), git reads, the operations (`propose`, `accept`, `edit`, `drop`, `start`, `finish`,
  `release`), `not_here` (a need done elsewhere), `offers`/`offerable`/`widen`/`sibling` (a
  hand-back's fixes), `undoable`/`undo`, `run_check`. Tests: `test_plan.py`, `test_tree.py`,
  `test_run_live.py`.
- `plan_text.py` (940): the plan as text. `parse` (a line belongs to the node line just above it,
  at one column, or is refused by number), `render`, `apply` (three-way, one transaction),
  `edit_loop` (the editor, refusals written under their line). Tests: `test_plan_text.py`,
  `test_plan_text_cli.py`, `test_plan_text_findings.py`.
- `gate.py` (590): what the Claude Code hooks answer, including `paragraph()`, `_tree_wait` and the
  session-start teaching. Tests: `test_gate.py`, `test_hooks.py`.
- `run.py` (750): `graphene run`, in place and `--parallel`. `run_node`, `sweep` (by pid and start
  time), `land`/`park`, `live`/`tail`. Tests: `test_run.py`, `test_parallel.py`, `test_run_live.py`
  (real signals).
- `ask.py` (160): the planner. Tests: `test_ask.py`.
- `tui.py` (830): `graphene watch`. `Watch` is the app; `PlanTree` reads the two-key sequences;
  `detail()` is the node pane; `_cli()` runs a key's command in-process, `background()` in a process
  of its own. Tests: `test_tui.py` (Textual's pilot, at 80 and 120 columns).
- `plan_cli.py` (1,040): the `plan`, `node`, `watch`, `ask` and `run` commands; `write()` wraps
  every act of yours (undo, and which repository). Tests: `test_plan_cli.py`, `test_plan_text_cli.py`.
- Barely touched tonight: `node_record.py`, `store.py` (`claim()` now joins an outer one),
  `sources/claude_code.py` (hook entry, transcripts), `graph.py`/`plan_view.py`/`server.py` (the
  page), `attribute.py`, `commits.py`, `record.py`.

To change what a line of the text means, start at `plan_text.parse` and add a case to
`test_plan_text_findings.py`. To change a key, it's `Watch.BINDINGS` and a test in `test_tui.py`.

## 4. What was verified, and how

- **The whole scene on real agents** (23 September, the feeds task, one run):
  - The paragraph typed into a session gave a tree in 35 s, with no file touched.
  - Accepted, `run --parallel 4` did the four leaves in 50 s.
  - The result scored 18/20 on the hidden acceptance (the 2 misses want what the paragraph never
    said) and 12/12 held-out. The untouched repo scores 10/20 and 0/12.
- **The recording** (`docs/assets/watch.gif`, real agents): a prune that went too far, `R`, the leaf
  coming back wanting `cli/main.py`, `w`, `R`, all done.
- **`graphene ask`** on the same paragraph: 44 s, seven nodes with needs, first try.
- **The screen in a real WezTerm** (an isolated mux, 80×24, read back with `wezterm cli get-text`).
- **The text form:** 54 adversarial agents (49 findings), a recheck of each, then a hunt for the
  rebuild's own regressions (12, all fixed). Each is guarded by a test.
- **The closing review:** 78 findings confirmed, all fixed (`a384829`). A recheck of each with a
  regression test, and a hunt for what the fixes broke (11). Everything the recheck left open is
  fixed and merged, except the three named in decision 39. Every fix has a test that fails without it.
- **Ctrl-C, a closed terminal, `kill`**: real signals in `test_run_live.py`, which checks that no
  executor or check survives.
- **Tests:** 638 (611 in `tests/`, 27 in `docs/test/`). One recheck test (a second Ctrl-C during the executor's TERM) is timing-based; watch it in CI. Ruff clean. CI on Linux and macOS, Python 3.12 and 3.13.
- **The third test:** eight stand-in runs, one at a time, and an independent audit that reproduced
  every figure from the raw runs.

## Not verified

- **You, at the keys.** Nobody has pruned a tree with these keys but me through a mux and the
  stand-ins through the equivalent commands.
- **WezTerm's own window.** I checked its mux, not the GUI: fonts, mouse capture, whether Shift-drag
  selects text over the screen.
- **The paragraph rule's 240 characters** against anyone but you.
- **Codex as planner or executor:** `--with 'codex exec --sandbox read-only'` should work for `ask`,
  and was not run.
- **The start-time check on Linux** when the wall clock steps between a run's start and a sweep. A
  live run could then look gone: its leaf would be swept, though its executor is not killed.
- **A stray line**, once, at the top of a 36-column pane of `graphene watch`. I could not reproduce
  it.

## Questions (only what blocks the next step)

1. Is 240 characters the right line between "do it" and "plan it" for you (decision 28)?
2. When an agent proposes a new tree after your goal is finished, should your goal be set aside
   until you accept or decline the new sentence (what it does now), or stay until you replace it
   (decision 39)?
3. The third test says the tree cost attention rather than saving it. Run the ten-minute recipe
   yourself (`docs/test/PROTOCOL.md`), with a paragraph run of the same card beside it, before the
   next directive leans on the tree?

## Rollback

Before the first change `main` on GitHub was `ed010ca` (your merge of PR #26); this run is the
branch `terminal`, cut from it. Nothing here touched `main`. To put your local `main` where GitHub's
is (it was 43 behind, at `6cece1c`):

```
git checkout main && git reset --hard ed010ca
```

## State of every branch

- `terminal`: this run, pushed; one PR into `main` (#27).
- `main` (GitHub): `ed010ca`, untouched. Local `main`: `6cece1c`, 43 behind GitHub, untouched.
- `worktree-agent-a525b0dc…`, `…a6f78b30…`, `…a7755787…`: tonight's three fix branches, merged into
  `terminal`; their worktrees are under `.claude/worktrees/` and can go (`git worktree remove`).
- Everything else (`agent/*`, `codex/*`, `lane/*`, `n*`, `graph`, `plan`, `rebuild`, `tree`) is as it
  was.
