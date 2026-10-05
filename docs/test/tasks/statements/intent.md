# statements — what I actually want

*My notes to myself before I ask for this. Nobody else sees this file, and neither arm may paste it.*

We are starting to bill in euros and pounds. The statements service only knows dollars. I want it to
know currencies, without breaking the three things other teams read: the monthly totals file, the v1
export, and the close script ops runs on the 1st.

I have not been in this code for months. I know what I want out of it, not where everything lives.

## What I want

- **Every posting has a currency.** Three capital letters. A new migration adds it, and every posting
  already in the database becomes USD.
- **Balances are per currency.** Two currencies are never added together, anywhere: not in a balance,
  not on a statement, not in interest.
- **One statement section per currency**, each with its own opening balance, postings and closing
  balance. An account with only euros has no dollar section. Apart from the sections, the statement
  looks as it does now.
- `post` takes `--currency`, and `load` takes a `currency` column. Both default to USD, and so does a
  blank cell. `balance` prints one line per currency, the code and then the amount.
- Interest accrues per currency, on that currency's balance, and is posted in that currency.
- Tests for the new behaviour.

## Where the paragraph pulls two ways

- **Half-even everywhere, and the monthly file unchanged.** Both are true. "Everywhere" means
  everything we print for people: the statement and the balance. The monthly file is billing-ops'
  contract, and it keeps rounding exactly as it does today. If asked, I say: the monthly file stays
  as it is.
- **Per-currency balances, and the v1 export unchanged.** v1 keeps its keys and its types. It is
  dollars only: its balances are the USD ones, and a posting in another currency is not in it. On
  dollar data it prints the same bytes as today.

## What I know about the repo, and nothing more

- `vendor/` is pinned to what the billing image ships. If something in there is in the way, wrap it
  or ask me. Never edit it.
- Migrations have rules, in `migrations/README.md`. A new change is a new migration with the next
  number. A shipped one is never edited.
- `tests/test_legacy_contract.py` is billing-ops'. If it fails, the change is wrong, not the test.

## Do not touch

- `vendor/`, all of it.
- `tests/test_legacy_contract.py`.
- `migrations/0001` to `0004`.
- What `legacy/monthly.py` prints, byte for byte, for dollar data.
- The v1 export's shape, and its bytes for dollar data.
- `scripts/close_month.sh` keeps passing: on the samples, and on a postings file in three currencies.

## What I would reject on sight

- A monthly file that rounds half-even.
- A `currency` key in v1, or a v1 balance that adds euros to dollars.
- An edit to a vendored file, or to the protected test.
- A gap or a repeat in the migration numbers, or an edit to 0002 instead of a new migration.
- A balance or a statement that adds two currencies together.
