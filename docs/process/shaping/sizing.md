# How big the plan is: measured

Directive B asks for the proposed tree's size against the repo's size on the four tasks, Graphene itself and two public repos. This file measures the planner's output only. Whether the stand-ins pruned less is measured by the shaping study (lane D), not here.

## Reading

Under `auto` the Claude Code planner proposed 1 to 3 leaves on every repo, from 118 lines to over 20,000. The ask set the count, not the repo: a one-flag change got one leaf in the 118-line `report` repo and in Graphene's 461 files, and no run came near the auto band's upper bound of 6 or 10. The size setting moved the tree the way it was asked. `finer` gave more leaves than `auto` in 5 of 7 repos and never fewer, with smaller scopes per leaf. `coarser` gave fewer or the same in all 7. The only band broken was `requests` under `finer`: 3 leaves against a floor of 4.

## Table

| repo | files | lines | size | band the sentence gave | leaves | sub-goals | dirs touched | median scope (entries) | median scope (existing files) | planner s |
|---|---|---|---|---|---|---|---|---|---|---|
| report | 13 | 118 | coarser | 1 leaf | 1 | 0 | 3 | 3 | 2 | 148 |
| report | 13 | 118 | auto | 1 to 3 leaves | 1 | 1 | 3 | 3 | 2 | 26* |
| report | 13 | 118 | finer | 2 to 6 leaves | 2 | 1 | 3 | 1.5 | 1 | 42 |
| logs | 13 | 136 | coarser | 1 leaf | 1 | 1 | 3 | 5 | 4 | 80 |
| logs | 13 | 136 | auto | 1 to 3 leaves | 3 | 1 | 3 | 2 | 1 | 26 |
| logs | 13 | 136 | finer | 2 to 6 leaves | 3 | 2 | 3 | 2 | 1 | 41 |
| inventory | 15 | 154 | coarser | 1 leaf | 1 | 0 | 2 | 2 | 1 | 80 |
| inventory | 15 | 154 | auto | 1 to 3 leaves | 2 | 1 | 3 | 2 | 1 | 29 |
| inventory | 15 | 154 | finer | 2 to 6 leaves | 2 | 1 | 4 | 2.5 | 1.5 | 80 |
| feeds | 27 | 298 | coarser | 1 leaf | 1 | 0 | 3 | 3 | 2 | 85 |
| feeds | 27 | 298 | auto | 1 to 3 leaves | 1 | 1 | 2 | 2 | 1 | 33 |
| feeds | 27 | 298 | finer | 2 to 6 leaves | 2 | 1 | 3 | 1.5 | 1 | 88 |
| itsdangerous | 50 | 3,199 | coarser | 1 to 3 leaves | 1 | 0 | 3 | 3 | 2 | 61 |
| itsdangerous | 50 | 3,199 | auto | 1 to 6 leaves | 1 | 0 | 3 | 3 | 3 | 20 |
| itsdangerous | 50 | 3,199 | finer | 2 to 12 leaves | 2 | 1 | 3 | 1.5 | 1 | 37 |
| requests | 130 | over 20,000 | coarser | 1 to 5 leaves | 2 | 1 | 3 | 1.5 | 1 | 87 |
| requests | 130 | over 20,000 | auto | 2 to 10 leaves | 2 | 1 | 4 | 2 | 1.5 | 20 |
| requests | 130 | over 20,000 | finer | 4 to 20 leaves | 3 | 1 | 4 | 1 | 1 | 46 |
| graphene | 461 | over 20,000 | coarser | 1 to 5 leaves | 1 | 0 | 2 | 2 | 1 | 87 |
| graphene | 461 | over 20,000 | auto | 1 to 10 leaves | 1 | 0 | 3 | 3 | 2 | 25 |
| graphene | 461 | over 20,000 | finer | 2 to 20 leaves | 3 | 1 | 3 | 2 | 1 | 43 |

\* `report`/`auto` ran alone, as the trial run. The other 20 ran five at a time.

## How it was run

- **Code.** Branch `lane-b-fix` at b19c6fa, from its own venv. Every run was `graphene init --planner claude --executor claude`, then `graphene ask "<ask>"` with `--finer`, `--coarser` or nothing.
- **Environment.** `GRAPHENE_AS=person:alex` and `GRAPHENE_KEYCHAIN=off`. Every `CLAUDE*`, `AI_AGENT`, `CODEX*`, `NEBIUS*` and other `GRAPHENE_*` variable was unset. A fake `security` was first on PATH for `init`.
- **Fresh copy each run.** Each run used its own fresh copy of the repo, so no run saw another's tree.
- **Repos.**
  - The four task repos came from `docs/test/make_task.py`.
  - Graphene was a depth-1 clone of `lane-b-fix`.
  - `pallets/itsdangerous` and `psf/requests` were depth-1 clones of their default branches on 2026-09-28.
- **No 'off' size.** The code offers no size that leaves the sizing sentence out. `sizing.SIZES` is auto, finer and coarser, and `ask.prompt_for` always adds `sizing.measure`'s sentence for a whole-tree ask. So `auto` is compared with `finer` and `coarser` instead of with no sentence.
- **Files and lines** are what `sizing.measure` puts in its sentence. It stops counting at 20,000 lines. The full counts are 28,182 lines for `requests` and 90,062 for Graphene.
- **What was counted.**
  - Leaves are proposed nodes with no children. Sub-goals are proposed nodes with children.
  - Dirs touched is the distinct directories of all leaves' scope entries: the path up to the first wildcard, or a file's directory, with `.` for the repo root.
  - Median scope is given two ways. Entries are the globs or paths in a leaf's scope. Existing files are the tracked files `P.in_scope` matches, which leaves out files a leaf would create.
- **Planner seconds** are the wall clock of `graphene ask`.

The asks were written before any run and were the same for all three sizes:

- feeds: Add a --dry-run flag to the load command that reads and normalizes the feed as it does now but prints the records it would write instead of writing them, and exits 0.
- inventory: Add a --dry-run flag to the adjust command that prints the stock level the adjustment would leave, without writing anything to the ledger.
- logs: Add a --since option to the command line that skips log lines older than the given timestamp, and have the summary say how many lines were skipped.
- report: Add a --limit N option to the report command so it prints only the first N rows, and have the output say how many rows were left out.
- itsdangerous: Let a TimedSerializer be created with a default max_age that loads and loads_unsafe use when the caller passes none, with tests and a line in the changelog.
- requests: Add a per-session default timeout: a Session gets a timeout attribute that request() uses when the caller passes no timeout, with tests and a note in the docs.
- graphene: Add a --json flag to graphene config that prints every setting as one JSON object, so a script can read the settings without parsing the text form.

## What this does not show

- **Seconds depend on run order.** All `coarser` runs went first, then `finer`, then `auto`, five at a time on a heavily loaded machine. The drop from 61–148 s to 20–33 s follows that order, so it cannot be put down to the size.
- **One run per cell.** There is no measure of the planner's run-to-run variance.
- **"tests" and "docs" count as named directories.** `sizing.named_dirs` counts the words "tests" and "docs" in an ask as named directories. That raised the `auto` floor to 2 for `requests`, and it named `tests` for `itsdangerous`, though that did not change its floor. The asks said "with tests" and "a note in the docs", not a path.
- **Nothing ran.** Whether these trees are the right size for the work, and whether the stand-ins pruned less, is measured by lane D.
