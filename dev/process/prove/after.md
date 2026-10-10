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

The A1 gate is read on `$A`, which had no first refusal, so the schema planner was not built. On the branch, 3 of
the 5 first refusals (60%) fall in the rule's classes (the `then:` slips; the other two are indentation slips, which
a schema would also make impossible): taken there, the gate would have been met, which goes to decision 3
(`morning.md`). Nothing was lost: the second try took every one. The branch's X1 ran on the build at d6cd8e9; the ask's code did not change after it
(the one later edit to gate.py is the hook's aside path, not the SessionStart text the planner reads).

## X2: the price of the contract on feeds (n = 3 a build; the plain session and `/batch` once)

| arm | accept | held-out | the six untouched | wall seconds (main; plant) | dollars | denials; turns | the fix landed in the owner's file; why recorded |
|---|---|---|---|---|---|---|---|
| Graphene on 907a7d0 (median of 3) | 18 of 20 | 12 of 12 | 6 | 109; 57 | $0.628 | 18; 51 | yes; yes (the reopen note) |
| Graphene on the branch (median of 3) | — | — | — | — | — | — | — |
| the plain session (median of 3) | 18 of 20 | 12 of 12 | 6 | 47; 12 | $0.353 | 5; 21 | yes; in the reply only |
| `/batch` (2, declined to batch) | 18 of 20 | 12 of 12 | 6 | 59; 16 | $0.457 | 6; 30 | yes; in the reply only |

## X3: ten questions about a finished run (3 runs × 2 arms a build, one reader each)

| arm | 907a7d0, median of 8 | branch, median of 8 |
|---|---|---|
| A: Graphene's record | 7 ([6, 7, 7]) | — |
| B: `git log -p` plus the executors' last words | 4 ([3, 4, 4]) | — |

Per question, 907a7d0: the record missed q3 (refused commands) in every run; git missed q3, q5 (dollars), q6
(width), q10 (leaves added after accept) in every run and q4 (the at-base verdict) in one.

## X4: pytest-bdd issue #476 through the tree (n = 1 a build)

| measure | 907a7d0 | branch |
|---|---|---|
| proposal by first answer; the tree | yes; 1 sub-goal, 2 leaves, 2 board items | — |
| checks written (`python3 -m pytest` / `uv run`) | 3 / 0 | — |
| red first | `tags-output`'s check passes at the base | — |
| landed; came back; attempts | 2; 0; 1 each | — |
| the repo's own suite afterwards | 148 passed | — |
| wall; dollars | 87 s; $0.265 | — |

## X5: the editable-install hole, no model

| combination | 907a7d0: `b` (broken) landed | branch: `b` landed | what red first said on the branch |
|---|---|---|---|
| `python3 -m pytest`, no pytest on PATH | no (3 attempts, `No module named pytest` in the hand-back) | no (3 attempts) | before the run: `b: its check cannot run here: No module named 'pytest'. Checks run in a clean worktree with your PATH and nothing git ignores; a runner that makes its own environment (…) brings pytest with it` |
| `python3 -m pytest`, the venv first on PATH | **yes** (the check imported the checkout) | **yes** (named, not closed, as the rules expected) | `python3 on your PATH has pkg installed editable from this repo: a check that imports it tests your checkout, not the leaf's worktree; uv run pytest … builds the worktree's own` |
| `uv run pytest`, the venv first on PATH | **yes** (the copied index's stat data) | **no**: `b came back after 3 attempts`, each refused with `uv run pytest -q tests/test_b.py failed` | the clean tree now reads the edit (the one-line fix) |

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
| branch | — | — | — |

## X6: one stranger transcript a build (a fact)

Both strangers were given the branch's README (020eb7d's text: `x6_transcript.sh` read the clone's copy, whichever
build ran), so the README's own changes were not measured here, and both reported `graphene init --remove` from it.

| build | landed | its session | Graphene's runs cost | dead ends, in its words |
|---|---|---|---|---|
| 907a7d0 | yes, at the second run | 19 turns, 258 s, $0.196 | $1.05 + $0.95 (the default model) | a wheel the harness misnamed; a check whose runner the PATH lacked (it rewrote the check to `uv run pytest`); a read refused for naming the store |
| branch | — | — | — | — |

## X7: plan first auto against on (branch only, for decision 176)

| repo | ask | auto: reached the person as a tree | auto: taken at once | on: reached the person as a tree |
|---|---|---|---|---|
| feeds | the paragraph (3) | — | — | — |
| feeds | a typo (3) | — | — | — |
| pytest-bdd | a typo (1) | — | — | — |

## The suite, the spend, the SHA

| | 907a7d0 | branch |
|---|---|---|
| the full suite | — | — |
| ruff | clean | — |
| the wheel smoke (`graphene --version`, `graphene demo --once`) | ok | — |
| the night's spend (ledger.md) | $8.06 after the before arms | — |
| the SHA the after arms ran on | 907a7d0 | — |
