# morning.md — 2026-09-21 — the tree directive

(Kept current through the run. Yesterday's is `docs/process/morning-2026-09-20.md`. Sections marked
PENDING are filled when the last sub-agent reports; everything else is final.)

## 1. What you can run in five minutes

```
cd ~/Desktop/AllThingsAgenticHackathon && git checkout tree
docs/proof/parallel.sh     # two real agents at once, a worktree each, on a tree. ~30 s, some cents. ok/FALSE lines
docs/proof/tuesday.sh      # a plan in force; an ordinary typed request; no refusal, no command; then "yes" accepts
graphene watch             # in the repo either script prints at the end (`cd` there): the tree, live. Ctrl-C leaves
WITH='codex exec --sandbox workspace-write --skip-git-repo-check' docs/proof/parallel.sh   # the same, two Codex agents
```

In a repo of your own: `graphene plan goal "…"`, ask your agent to propose a tree with
`graphene plan propose -`, prune it (`graphene`, `node set`, `node drop`, `plan accept <subtree>`), then
`graphene run --parallel 3` and `graphene watch` beside it. The README's "first ten minutes" is that.

## 2. What is waiting on you

Nothing blocks the next step. One PR, `tree` into `main`, is yours to merge (link at the end).
Decisions 13 to 27 in `docs/DIRECTION.md` are tonight's, each with its reason and the question I would
have asked. The four I would read first:

- **18** A request typed into a session is a leaf that may touch anything unless you type `--scope`.
  This is what makes a plan in force free on a Tuesday, and it loosens decision 4.
- **20** Whoever carries no agent's mark is you, terminal or not. An agent of a vendor that sets no
  mark is now taken for you. (The check Graphene runs never is.)
- **21** `graphene run --parallel` commits and merges, on `graphene/<leaf>` branches of its own.
- **25** `graphene why`, the session card and `graphene sessions` are gone.

## 3. A map of the code, for working in it every day

`src/graphene_debrief/` is 7,500 lines. Read in this order; each line ends with where its tests are.

**The plan (start here).**
- `plan.py` (1,360): everything the product means. Standard library only, because the hook imports
  it. Top to bottom: `Node`, `caller()` (who is a person), scope globs, **the tree** (`kids`, `above`,
  `below`, `leaves`, `validate`, `ready`, `forecast`), git reads, `contract`/`trail` (what an executor
  is told), then one function an operation: `propose`, `accept`, `edit`, `drop`, `start`, `finish`
  (the boundary), `roll_up`, `close_aside`, `release`, `signoff`, `reopen`, `archive`. Every
  operation is "change a row, write a log line". → `tests/test_plan.py` (the boundary),
  `tests/test_tree.py` (the tree, and every tree finding of the closing review).
- `plan_cli.py` (750): `graphene plan …`, `graphene node …`, `graphene run`, `graphene watch`. No
  logic of its own except `plan_lines`, the tree print that `plan` and `watch` share.
  → `tests/test_plan_cli.py`.
- `gate.py` (390): what the Claude Code hooks answer: a write refused, a stop refused, a prompt
  read as a leaf or as a yes (`_on_prompt`, `_aside`). → `tests/test_gate.py`, `tests/test_tuesday.py`.
- `run.py` (370): `run_node` (one leaf to its boundary), `run_plan` (one at a time, in place),
  `run_parallel` + `worktree_for` + `land` (worktrees, commit, merge). → `tests/test_run.py`,
  `tests/test_parallel.py`.

**The record.**
- `node_record.py` (590): a leaf's record and `rolled_up` for a subtree or the plan.
  → `tests/test_node_record.py`. `record.py` (220) and `commits.py` (190) grade commits for it.
- `store.py` (680): SQLite. Nodes are JSON documents in one table, so a new node field needs no
  migration. → `tests/test_store.py`.
- `sources/claude_code.py` (1,000): the hook entry point `hook_main`, `graphene init`, transcript
  backfill. The biggest file and the least related to the plan. → `tests/test_hooks.py`,
  `test_backfill.py`, `test_ingest_run.py`.
- `attribute.py` (250): what is left is the shell-command parser the gate uses
  (`bash_written_paths`). → `tests/test_attribute.py`.

**The page.** `plan_view.py` (375) and `graph.py` (715) build JSON; `server.py` (225) serves it;
`ui/` is the React source, and its build is committed under `src/graphene_debrief/ui/static` (CI
fails if they differ: `npm --prefix ui run build`). → `tests/test_plan_view.py`, `test_graph.py`,
`test_server.py`, `ui/src/*.test.ts(x)`.

**To make a change and know where its test goes:** a rule of the plan → `plan.py` +
`tests/test_tree.py` or `test_plan.py`, using the `store`/`repo` fixtures and the `do()` helper (a
real git repo every time; git is the mechanism, never mocked). Words a person or agent reads →
`plan_cli.py` or `gate.py`, asserted through the CLI runner or `hook_main`. The gate before a commit:
`uv run ruff check && uv run ruff format --check && uv run pytest -q` (90 s).

**What I think a person should own from here:** `plan.py`'s words (every `Refused` message and
`contract` is the product's voice), `docs/DIRECTION.md`, the README, and `gate._YES`/`_NOT_YES` (what
counts as your yes is a judgement about how you talk, not a mechanism). What agents can keep:
`sources/claude_code.py`, `graph.py`, the page.

## 4. What was verified, and how

- **The tree, on real agents.** `docs/proof/parallel.sh`: two Claude agents at once, a worktree each,
  each told the why path, each landed as a merge, the sub-goal done by its own check after both
  landed, the dependent leaf only then, hooks running inside the worktrees: 9/9, 26 s
  (`docs/proof/2026-09-21-parallel.txt`). The same with two Codex agents: 8/8, 60 s
  (`-parallel-codex.txt`). The first real run found a bug tests had not (the sub-goal's check ran
  before the sibling had landed); fixed, tested.
- **Free on a Tuesday, on a real agent.** `docs/proof/tuesday.sh`: a plan in force, an ordinary typed
  request, zero graphene commands by the person, no refusal, a done leaf whose record names the
  file; then a proposal accepted by typing "yes" in the session and done by the same session: 6/6.
  **What that proof does not show:** its "yes" is fed by `claude -p`, not typed by a person; the
  mechanism cannot tell those apart, which is the printed hole in decisions 18/19.
- **The three 0.3 proofs** re-run on this code: `proof.sh` 5/5 (the typo the person asked for is now
  fixed under a leaf made from the prompt, not refused), `stop.sh` 2/2, `run.sh` 4/4.
- **The closing review.** Two adversaries told to assume I had cut corners: 47 findings, each
  reproduced twice, all collected before any was fixed (`local/reviews/`, untracked). The worst:
  prose after "check:" in a prompt was run as a shell command; an agent could pipe a forged prompt
  into `graphene ingest hook` and be you; with "no terminal is the person", a pytest file an executor
  wrote was the person; 3 of 8 parallel leaves were refused over a sibling's landed file; `land`
  aborted a merge of the person's own and said "nothing of yours was touched"; `archive` could
  orphan a node and brick the plan. Every promise-breaking one is fixed with a test, except the forged
  hook event, which is refused by its ordinary spelling only and printed as a hole.
- **The gate:** PENDING (clean clone, 3.12 and 3.13, ruff, wheel smoke, page build identical, CI).
- **The rollback recipe** below was run against 0.3's code in a scratch repo.

## Not verified

- PENDING: all five proof scripts re-run on the code as it stands after the review's fixes.
- `graphene watch` on a real terminal by a person: tested through `--once`, and the full-screen loop
  was never looked at by eyes. The cut-to-fit logic is untested on a real 80x24.
- The page in a browser beyond the sub-agent's two webkit screenshots; 50 nodes on screen.
- The hook's cost with thousands of prompt leaves: the review measured the median crossing the 60 ms
  budget near 5,000; nothing prunes them yet (`graphene plan archive` relabels).
- A parallel run on a large repo: `start` holds the store's write lock while it looks at every other
  worktree; the review saw "database is locked" with 20 worktrees of 4,000 untracked files each.
- Codex hooks and the vendor sandbox (the two things after the list): not started.
- Review findings left as they are, all visible rather than promise-breaking: two attended sessions
  in one checkout (the second gets no leaf, and is not told why well); a leaf with a proposed child
  draws as a sub-goal on the page; non-English yes; `accept` works while paused.

## The test a paragraph can lose

PENDING: the sub-agent running the second test has not reported. Its results will be
`docs/test/results-2026-09-21.md`, with the refreshed ten-minute recipe at the top of
`docs/test/PROTOCOL.md`.

## Questions (only what blocks the next step)

None blocks. The one I would most like answered: decision 18's default (a typed request may touch
anything) against the stricter "anything no other open leaf claims".

## Rollback

`main` before tonight: `6cece1c`. Nothing has touched `main`; all work is on `tree`.

```
git checkout main && git reset --hard 6cece1c          # only if tree is merged and you want it out
sqlite3 .graphene/graphene.db "UPDATE nodes SET data = json_remove(data, '$.parent', '$.aside'); PRAGMA user_version = 3"
```

The second line is for a repo whose store 0.4 has opened (schema 4, no table changed): without it
0.3 says "written by a newer graphene"; with it 0.3 prints the plan (run tonight, scratch repo).

## State of every branch

- `main`: untouched, `6cece1c`, as you left it. `origin/main` likewise.
- `tree`: tonight's work, pushed to `origin/tree`. PENDING: final SHA, CI run, PR link.
- Left on the machine: five sub-agent worktrees under `.claude/worktrees/agent-*` with their
  branches (`worktree-agent-*`), merged or read-only; `git worktree remove` and `git branch -D` are
  yours, as before.
