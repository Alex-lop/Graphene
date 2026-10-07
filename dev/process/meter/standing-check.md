# Do the paragraph's conditions reach every executor?

Run on 7 October at 00:03, as practice, never registered. One tree-arm planning session on a fresh
`statements` repo: Claude Code on Sonnet, plan first on, PROVE.md's tool list, the paragraph byte for
byte. Then the person accepted with the board's defaults, and each leaf's contract was printed exactly
as `graphene run` sends it (`run.prompt_for`). The session took 6 turns and $0.23 (the night's ledger,
purpose `statements-practice`). Script: `dev/test/standing_check.py`.

| leaf | half-even | vendor/ | legacy byte for byte | v1 shape |
|---|---|---|---|---|
| mig | yes | yes | yes | yes |
| money | yes | yes | yes | yes |
| ledger | yes | yes | yes | yes |
| statement-render | yes | yes | yes | yes |
| cli | yes | yes | yes | yes |
| export-v1 | yes | yes | yes | yes |
| legacy-monthly | yes | yes | yes | yes |
| final | yes | yes | yes | yes |

How they got there:

- The planner wrote them into the plan's goal: "Postings carry a currency (backfilled USD),
  balances/statements/interest are per currency, rounding is half-even, and legacy monthly, v1 export,
  close_month.sh and vendor/ stay as they are." Every executor reads the goal as the first line of `why:`.
- It put three conflicts on the board as items about the whole plan: half-even against the legacy file,
  which rounds half-up (`q-legacy`); the frozen v1 shape against per-currency balances (`q-v1`); and the
  vendored formatter, whose half-even goes through a float (`r-vendor`). Accepted with their defaults,
  each one is a `decided:` line in every leaf's contract.

So on this sample the agent's prediction in PREREG-statements.md does not hold: "The tree splits the
paragraph's constraints across leaf contracts, and each executor sees only its own." Nothing was changed
to make the conditions reach. One session is one sample: the practice runs check it again. The board
also named the rounding conflict, the frozen v1 shape and the vendored bug before any code ran.
