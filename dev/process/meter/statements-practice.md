# The statements task as practice, and its size

Two practice runs of the tree arm on 7 October, never registered (`dev/test/statements_practice.py`, style
`practice`). The person is a scripted stand-in: it takes every board default, prunes nothing, and in the
protocol's one more round takes what Graphene offers. Claude Code on Sonnet planned (a session in the repo
with plan first on, PROVE.md's tools) and did the leaves (`graphene run --parallel 3`, its stream on).

## Run 1, at the registered size (1,328 lines), 00:31

- **The plan:** 9 leaves under 3 sub-goals, in 22 turns and $0.31. Three board items about the whole
  plan: a statement's USD heading, what v1 and the monthly file do with euros, and the rounding conflict
  with the vendored float bug. Their defaults kept legacy half-up and v1 dollars-only.
- **Round 1:** the migration landed. `ledger` came back: "Posting.currency must be a dataclass field, but
  api/export.py writes v1 postings with dataclasses.asdict(p), so the field would leak into the frozen v1
  export shape". That is trap 2, seen by an executor before anything broke. Nothing could be offered,
  because `api/export.py` belongs to `export-usd`.
- **Round 2:** the stand-in's note told `ledger` to add the field and leave the export to `export-usd`.
  Then 6 leaves landed in 4 minutes, three at a time, and `verify` came back: `tests/test_cli.py` expects
  half-up `7,116.43`, the decided half-even prints `7,116.42`, and that test is outside its scope.
- **The count:** 0 of 5 traps, 19 of 24 acceptance, 8 of 12 held-out. Run time 9.5 minutes; the
  stand-in's clock 1.3 minutes. The executors cost $1.61 and the plan $0.31. This run used the wheel from
  before the meter merged, so its rows were not written, and its spend went on the ledger after the run,
  from what Claude Code reported.

## The size, doubled, 01:15

At 1 to 2 minutes a leaf, the run was about 8 times too short for one to three hours. An agent grew the
task to 2,658 lines: eight subsystems that sum money or round it (fees, aging, dunning, reconciliation, a
CSV statement, month-end figures, tax-year interest, an audit), each with tests and a command, all run by
`scripts/close_month.sh`. The paragraph, the card and the three checks are unchanged (their blobs are
pinned). `reference.patch` makes all eight per currency and still passes 24 of 24 and 12 of 12 with 0
traps; the rehearsal still reads 5, 5, 0, 0. `dev/test/tasks/statements/SIZE.md` says what changed.

## Run 2, at twice the size, 01:17

- **The plan:** 51 seconds. The same two questions, and a new risk: "The aging, dunning, fees, interest,
  reconcile, summary and audit code all add up amounts without a currency, so with a EUR posting they
  would silently add EUR to USD." Its default: those stay USD-only, "per-currency reports are a separate
  job". The stand-in took it, so the new code left the tree.
- **Round 1:** 3 leaves landed in 2 minutes; `half-even` came back: four test files outside its scope pin
  half-up figures. Graphene offered to widen it or to add a sibling.
- **Round 2:** the stand-in took the widen offer. `half-even` finished its code and came back again:
  `tests/test_statement.py` belongs to another leaf.
- **The count:** 0 traps. The run stopped at 3 of 7 leaves after about 3 minutes of agent time.

## What it says

- **Size does not set the length here; the plan does.** Doubling the code changed nothing on the
  critical path, because the planner put the new subsystems on the board and its default kept them out.
  A person who answers that risk with "make them per currency" gets the long run; one who takes the
  default does not. The paragraph is pre-registered, so the task cannot ask for them itself.
- **What stops a run is a test file two leaves need.** Both runs came back over tests outside a leaf's
  scope, and twice nothing could be offered because another leaf owned the file.
- **The conditions reached every leaf.** As in `standing-check.md`, the goal and the plan-wide board
  items carried half-even, vendor/, the monthly file and v1 to every contract.
- **The size stays doubled on this branch**, with `SIZE.md`. PREREG-statements.md says a run on a changed
  repo is void: the registered runs need a new commit named for them, Alex's to make before run 1, or
  `git revert` of the merge that doubled it.
