# The statements task: why it is the size it is

## Why it changed

The task is meant to keep three parallel executors busy for one to three hours: long, unattended,
multi-agent work. On the night of 6 October a practice run of the tree arm (Claude Code on Sonnet,
`graphene run --parallel 3`, a 9-leaf tree) took 9.5 minutes of run time. Each leaf took 1 to 2
minutes. The critical path was migration, ledger, balances, statement, verify. The task was about
8 times too small for its purpose.

The ask was to grow it about 3 times, let a practice run measure the result, and extrapolate from
there. It grew 2 times. That was the largest size finished and green in the night's time box: the
base, the reference, the trip-all patch and the rehearsal. The two practice runs after it
say no size gets there: its biggest leaf edited 16 files in 2 minutes
(`dev/process/meter/statements-practice.md`).

## Old and new

| | files | lines |
|---|---|---|
| before (`make_task.py statements`, until 7 October) | 36 | 1,328 |
| now | 53 | 2,658 |
| `reference.patch` | 677 lines | 1,702 lines |

The base suite went from 32 tests to 86, and to 101 with the reference applied.

## What was added

The subsystems a small finance team grows around a ledger. Each one holds amounts, so the change
has to reach it. Each has its own tests and a command in `api/cli.py`.

| subsystem | files | command | rounds | sums |
|---|---|---|---|---|
| overdraft and late fees | `core/fees.py` | `fees YYYY-MM [--dry-run]` | yes, to the cent | daily balances |
| receivables aging (money in pays the oldest charge) | `core/aging.py` | `aging YYYY-MM` | in print | buckets, totals |
| dunning letters, three levels | `api/dunning.py` | `dunning YYYY-MM [--out DIR]` | in print | what is overdue |
| reconciliation against a settlement file | `core/reconcile.py`, `samples/settlement-2026-09.csv` | `reconcile FILE YYYY-MM` | in print | file and ledger totals |
| the statement as CSV | `api/csvexport.py` | `statement NUMBER YYYY-MM --csv` | yes | running balance |
| month-end figures | `core/summary.py` | `summary YYYY-MM` | in print | across accounts |
| the tax year's interest | `core/summary.py` | `tax-year YYYY` | in print | TOTAL |
| the audit before a close | `core/audit.py` | `audit YYYY-MM` | | |
| the reports' printers | `api/reports.py` | | `round_cents`, half up | |

`scripts/close_month.sh` now audits the month first and writes the CSV statements, the month-end
figures, the aging and the dunning letters. It still has to pass on a postings file in three
currencies, so every one of them has to work per currency.

## What the change has to do to them, and where the paragraph says so

- "Balances are per currency, never add two currencies together": a euro never pays a dollar
  charge in the aging, fees are charged on each currency's own balance and in it, the dunning
  letter has a section a currency, the reconciliation matches a line only in its currency, and the
  reports total each currency on its own.
- "half-even rounding everywhere": the fees, the CSV statement and every report round half up
  today, some through `round_cents`, the monthly file's own function, and some through the
  statement's printer. Flipping `round_cents` at the source is still the legacy trap.
- "Please add tests": each subsystem has tests that pin today's output, and the change breaks them.

Nothing in the new code needs a fact the paragraph does not give.

## What did not change

- The paragraph, the card, `accept.py`, `quality.py` and `traps.py`: not a byte.
- The five traps. The base has the same four migrations, so the card's "0001 to 0004" is still true
  and the reference's migration is still 0005. `tripall.patch` applies to the new reference as it
  did to the old, with one line of context different.
- What the hidden checks measure. They test the paragraph's rules through `balance`, `statement`,
  `export`, `legacy.monthly` and the close script, as before.

`prove.py`'s scripted tree has one more leaf, `reports`, so the rehearsal's tree applies the whole
reference. The rehearsal still reads 5, 5, 0, 0.

## The registered runs

`PREREG-statements.md` says any change to `make_task.py` after its commit shows in `git log`, and a
run on a changed repo is void. This is such a change. The registered runs need a new commit named
for them, and that is Alex's to make before run 1.
