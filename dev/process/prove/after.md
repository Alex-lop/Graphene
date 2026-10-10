# Before and after: 907a7d0 against the branch

Every pair below was taken with the same script under `dev/process/prove/`, the same budgets and the same isolation
flags, on `$A` (907a7d0's wheel) and on `$B` (the branch's wheel at the frozen SHA named at the end). The rules that
decide what a pair may claim were written before any number (`rules.md`). No human is measured anywhere here: every
planner, executor, walker, stranger and reader was a Sonnet session, except the stranger transcript's own `init`,
which picked the account's default model as a stranger's would.

## X1: the first ask (40 asks a build; Wilson 95%)

| measure | 907a7d0 | branch | shown |
|---|---|---|---|
| proposals by ask | 40 of 40 [0.91, 1.00] | 40 of 40 [0.91, 1.00] | no difference |
| proposals by first answer | 40 of 40 [0.91, 1.00] | 35 of 40 [0.74, 0.95] | the intervals overlap: no difference shown |
| asks lost | 0 of 40 | 0 of 40 | no difference |
| first refusals, by class | none | 5: `then:` effects 3 (an id not in the plan; a quoted goal effect ×2), indentation 2 | the text grammar's classes, every one accepted on the second try |
| checks by runner (unittest / pytest / other) | 79 / 24 / 8 | 98 / 9 / 4 | the clean-tree sentence (A5) moved the planner toward the repo's own runner on these stdlib repos |
| median seconds; median planner dollars | 26.5 s; $0.077 | 29.0 s; $0.086 | about the same |
| the ask's last line names the planner, its calls and its dollars | never | 40 of 40 (`the planner (claude sonnet-5-5): 5 calls, $0.11 at list price`) | A2 |

The A1 gate held on `$A` (no refusal), so the schema planner was not built. The branch's five first refusals are
the classes a schema would reach (three `then:` slips) or not (two indentation slips, which the schema also makes
impossible); over both builds that is 5 of 80 first answers, 6%, under the 10% the rule set. Nothing was lost: the
second try took every one. The branch's X1 ran on the build at d6cd8e9; the ask's code did not change after it
(the one later edit to gate.py is the hook's aside path, not the SessionStart text the planner reads).

## X2: the price of the contract on feeds (n = 3 a build; the plain session and `/batch` once)

| arm | accept | held-out | the six untouched | wall seconds (main; plant) | dollars | denials; turns | the fix landed in the owner's file; why recorded |
|---|---|---|---|---|---|---|---|
| Graphene on 907a7d0 (median of 3) | 18 of 20 | 12 of 12 | 6 | 109; 57 | $0.628 | 18; 51 | yes; yes (the reopen note) |
| Graphene on the branch (median of 3) | 18 of 20 | 12 of 12 | 6 | 88; 47 | $0.533 | 4; 31 | yes; yes (the reopen note, now in the merge's body too) |
| the plain session (median of 3) | 18 of 20 | 12 of 12 | 6 | 47; 12 | $0.353 | 5; 21 | yes; in the reply only |
| `/batch` (2, declined to batch) | 18 of 20 | 12 of 12 | 6 | 59; 16 | $0.457 | 6; 30 | yes; in the reply only |

Three runs a build, the same scores on every arm (the two misses are the change of mind the person never sent;
nothing outside the intent anywhere). Graphene's arm on the branch against 907a7d0: the executors were refused 3–4
commands a run instead of 14–20 (the executor is now told its shell runs only `graphene node` and `graphene plan`),
took 30–34 turns instead of 43–54, cost $0.52–0.55 instead of $0.62–0.75, and the main round took 84–88 s instead of
89–130 s (n = 3: medians, no interval). The plain session stays cheaper and faster ($0.34–0.38; 46–52 s), as the rules
expected. The wide-shell sensitivity row (one run on the branch with `Bash(python3 *)` allowed, as the recordings
had): the main round landed four leaves for $0.26 with 2 refused commands, the end-to-end leaf came back with the
same diagnosis, and then the harness failed, not Graphene: the executor's note held a backtick, `plant.sh`'s grep
cut the printed `graphene node reopen …` command at it, nothing was reopened, and the scores (16 of 20, 1 of 12)
are those of a repo whose planted fault was never fixed. The row says nothing about the shell and is not counted. What the contract adds is unchanged in kind and now also in git: each merge's body reads `Check: … passed`,
`Executor: claude claude-sonnet-5-5 · 1 attempt · $0.0445 at list price`, and the reopened landing carries
`Reopened: came back from e2e-xml: … sku key must be 'code'` under a subject ending `(xmlwire, reopened)`. The run's
first line on the branch: `landing into main at b6ba009: claude (sonnet), up to 3 at once, $2 an attempt at most; …`.

## X3: ten questions about a finished run (3 runs × 2 arms a build, one reader each)

| arm | 907a7d0, median of 8 | branch, median of 8 |
|---|---|---|
| A: Graphene's record | 7 ([6, 7, 7]) | 7 ([7, 7, 8]) |
| B: `git log -p` plus the executors' last words | 4 ([3, 4, 4]) | 5 ([4, 5, 5]) |

Per question. 907a7d0: the record missed q3 (refused commands) in every run; git missed q3, q5 (dollars), q6
(width), q10 (leaves added after accept) in every run and q4 (the at-base verdict) in one. The branch: the record
answers q3 in every run (`refused: 1 command refused to the executor` and the command itself), and misses q5 in two
of three: both readers took the record's `bill: $0.4455` for the whole plan's dollars, where the record means the
leaves' bill and prints `the planner's bill: $0.1067` on its own line; each figure they gave was right, the sum was
not asked for by name (the third reader summed). That is a labelling finding for the morning (`morning.md`), not a
regression. Git on the branch answers q4 in every run from the merge body's "and it passed at the base too" (the
night's own addition, reported as git's gain, as the rules say), and still cannot say the width, the dollars as a
whole, or the leaves added after acceptance. The record arm's rise is by construction; the comparison that counts,
record against git on the same build, is 7 against 5.

## X4: pytest-bdd issue #476 through the tree (n = 1 a build)

| measure | 907a7d0 | branch |
|---|---|---|
| proposal by first answer; the tree | yes; 1 sub-goal, 2 leaves, 2 board items | no (a `then: goal …` effect was quoted and refused; the second answer was taken); 1 sub-goal, 1 leaf, 2 board items |
| checks written (`python3 -m pytest` / `uv run`) | 3 / 0 | 2 / 0 (the clean-tree sentence did not move the planner on this repo) |
| red first | `tags-output`'s check passes at the base | `tags-report`'s check passes at the base, **and** `python3 on your PATH has pytest-bdd installed editable from this repo: a check that imports it tests your checkout, not the leaf's worktree; uv run pytest … builds the worktree's own` |
| landed; came back; attempts | 2; 0; 1 each | **0; 1; 1**: the leaf came back with the executor's own diagnosis: "the check cannot pass: python3 -m pytest imports pytest_bdd from the editable install at repo/.venv → repo/src/pytest_bdd (main checkout), not from the worktree copy, so the check run … executes the unmodified reporter and the new tag test sees no (tags: …) line" |
| the repo's own suite afterwards | 148 passed | 146 passed (nothing landed) |
| wall; dollars | 87 s; $0.265 | 125 s; $0.357 |

What the pair shows: the editable hole is real on a real repository and the branch names it before the run. On
907a7d0 it was masked by luck: the planner cut the work in two, the implementation landed into the checkout
first, and the tests leaf's check then imported the new code from the checkout. On the branch the planner put
implementation and tests in one leaf, so the check imported the checkout's old reporter and `done` refused it; the
executor read the same hole the warning named and handed the leaf back. The fix is the person's (`e` edits the
check to `uv run pytest …`, as the stranger in X6 did on 907a7d0 by itself), and the night's rule keeps red first a
warning. n = 1 on each build; the two trees differ, so the pair is two facts, not a difference.

## X5: the editable-install hole, no model

| combination | 907a7d0: `b` (broken) landed | branch: `b` landed | what red first said on the branch |
|---|---|---|---|
| `python3 -m pytest`, no pytest on PATH | no (3 attempts, `No module named pytest` in the hand-back) | no (3 attempts) | before the run: `b: its check cannot run here: No module named 'pytest'. Checks run in a clean worktree with your PATH and nothing git ignores; a runner that makes its own environment (…) brings pytest with it` |
| `python3 -m pytest`, the venv first on PATH | **yes** (the check imported the checkout) | **yes** (named, not closed, as the rules expected) | `python3 on your PATH has pkg installed editable from this repo: a check that imports it tests your checkout, not the leaf's worktree; uv run pytest … builds the worktree's own` |
| `uv run pytest`, the venv first on PATH | **yes** (the copied index's stat data) | **no**: `b came back after 3 attempts`, each refused with `uv run pytest -q tests/test_b.py failed` | the clean tree now reads the edit (the one-line fix); the same on the frozen SHA |

Also on the branch, in every combination: the run's first line (`landing into main at <sha>: x5_exec.py, up to 2 at
once; each leaf is committed with --no-verify … and merged --no-ff; checks run in a clean worktree with your PATH;
graphene watch in another terminal follows it live`), the dirty-checkout warning, and the came-back line ending
"`graphene node show b` says why". Red first judged only `b`: `a` waits on `b` (Graphene added the need), so it is
not judged at a commit it never starts from. The rules' two reverts (C3 wrong if a test-first leaf gets an
environment line; C4 wrong if the editable line is missing) did not fire.

## The walks: the README's commands in order (n = 3 a build)

| build | landed | median minutes to the first merge | dead ends by regex |
|---|---|---|---|
| 907a7d0 | 2 of 2, 2 of 2, 2 of 2 | 0.5 | 0, 0, 0 |
| branch | 2 of 2, 2 of 2, 2 of 2 | 0.5 | 0, 0, 0 |

On the branch the walks read, in order: `plan first: on. … You accept in graphene watch, in another terminal; graphene
plan first off, typed outside Claude Code, stops it.`; `the next Claude Code session here is recorded into the store
(its prompts, its tool calls and what they returned, the files it edits; on this machine only); graphene init --remove
takes the hooks out`; the ask's last line `the planner (claude sonnet-5-5): 3 calls, $0.05 at list price`; the
run's first line `landing into main at 5d0a6af: claude (sonnet), up to 2 at once, $2 an attempt at most; …`; and the
bill line `you 2 acts, 2 min` (the accept and the ask) where 907a7d0 read `you 0 acts, 0 min`. `node show` on a
sub-goal still prints an empty `scope:` line (listed in `morning.md`).

## X6: one stranger transcript a build (a fact)

| build | landed | its session | Graphene's runs cost | dead ends, in its words |
|---|---|---|---|---|
| 907a7d0 | yes, at the second run | 19 turns, 258 s, $0.196 | $1.05 + $0.95 (the default model) | a wheel the harness misnamed; a check whose runner the PATH lacked (it rewrote the check to `uv run pytest`); a read refused for naming the store |
| branch | yes, at the first run: two leaves (`impl`, `test`), both landed | 10 turns, 171 s, $0.100 | $1.32 + $0.52 planner (the default model) | none met: "The graphene binary isn't on your PATH, so I called it by full path"; it noted "Graphene flagged that itself" of the `impl` leaf's check passing at the base, and that "`graphene init --remove` takes them out" |

A fact a build, not a rate: on 907a7d0 the stranger's first run came back for want of pytest on the PATH and it
rewrote the check; on the branch its `uv sync` put pytest on the PATH first and both leaves landed at once. The
branch's stranger read the ∅ warning and repeated it in its report. **A harness fault, both builds:** the stranger's
`uv tool install <wheel>` ran with no tool directory of its own and replaced the `graphene` on this machine's default
PATH (the tool `graphene-map`), twice; the receipt showed the branch's wheel. It was put back from
`git+https://github.com/Alex-lop/Graphene@af3da2c5`, the build it had held, at 19:2xZ, and the script now gives
the stranger `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` under its own directory. `morning.md` says so.

## X7: plan first auto against on (branch only, for decision 176)

`x7.sh` on the branch, each cell a fresh repo with the hooks installed, the session `claude -p` with `auto_live.py`'s
argv (Sonnet, `acceptEdits`, its allow list, `--max-turns 25`, the isolation flags, $1.50). The typo ask is "fix the
typo in the README's first heading", with a letter dropped from that heading first (the fixtures had no typo; the
first attempt measured nothing and was rerun).

| repo | ask | auto: reached the person as a tree | auto: taken at once and done in the session | on: reached the person as a tree | dollars (median) auto / on |
|---|---|---|---|---|---|
| feeds | the paragraph (3) | 0 of 3 | 3 of 3, as one leaf of exactly 8 paths (WIDE), 15–22 turns | 3 of 3 (4–5 leaves, 1 board item) | $0.23 / $0.10 |
| feeds | a typo (3) | 0 of 3 | 3 of 3, one leaf of 1 path, about 10 s | 3 of 3: the one-path leaf waits for the person | $0.06 / $0.04 |
| pytest-bdd | a typo (1) | 0 of 1 | 1 of 1 | 1 of 1: waits | $0.05 / $0.04 |

Both sides of decision 176, measured: under `on`, a one-line typo waits for the person in another terminal (the
first-hour cost every reader named); under `auto`, the typo is done at once and the whole feeds paragraph is also
done at once as one 8-path leaf, never reaching the person as a tree (the 7 October count was 1 of 3; tonight 0 of
3; WIDE = 8 was tuned on feeds, and on pytest-bdd only the typo was asked). The default stays `on`; `init` now asks
at a terminal. The one `auto` typo run also shows the gate at work: the session's first edit, before it had started
its leaf, was refused, and it then started the leaf and landed it.

## The suite, the spend, the SHA

| | 907a7d0 | branch |
|---|---|---|
| the full suite | — | — |
| ruff | clean | — |
| the wheel smoke (`graphene --version`, `graphene demo --once`) | ok | — |
| the night's spend (ledger.md) | $8.06 after the before arms | — |
| the SHA the after arms ran on | 907a7d0 | — |
