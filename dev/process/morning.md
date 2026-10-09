# morning.md — 2026-10-09 — the loop

Rollback: `main` is untouched at `af6ff38`. To drop the night: close the PR, `git push origin --delete loop`.

## Your 30 minutes

(written at the end, from the pushed branch)

## Saturday

(written at the end)

## The brief

(current at 02:08; lanes 3, 4 and 5 are landing)

1. **The numbers**, before → after (`dev/process/loop/before.md`, `after.md`):
   - Loops closed: 0 → 2 live (Nemotron, on a fault nobody planted; Claude Code, on a planted one), 1 attempt per
     owner, $0.02 and $0.24 for the closing round.
   - Red first: the whole-suite check caught by behaviour (`planted-1`: the flag names the file); the first rule
     flagged 22 of 28 statements leaves, the refined one 12 of 19, every one a check that passes at the base.
   - Nemotron proposals: 15 of 20 → 18 of 20 on report and 9 of 13 so far on feeds, on lane 3's build. Width: not
     measured → measured on every run tonight (the dogfood 4 of 5, feeds 1 or 2 of 2 or 3, statements 3 of 8 to 12).
2. **Watch first:** `graphene demo tests/recordings/loop-nemotron-2.jsonl` (the natural loop) and
   `loop-claude-3.jsonl` (the planted one); the time view mid-run with four lanes: `dev/process/loop/screens/`.
3. **The bill:** $26 of $50 at 02:08 (`bill` in the ledger): `precheck` $14 · `planner` $5 · `reopen` $4 · `dogfood` $2 · `takes` $1.
4. **Your practice notes:** `~/graphene-timeline/practice.md` does not exist on this machine: nothing to answer.
5. **Decide:** (at the end)
6. **Broken or risky:** Docker Desktop is not running (Sandboxes are; Nemotron ran there). The dogfood's executors
   wrote code two skeptics a leaf then found 44 things about; the real ones are fixed (`49297e6`), the rest listed.

## What was done, in order

- **00:30** Read the directive. Branch `loop` from origin/main `af6ff38`, in a clone outside your checkout. The
  directive is committed at `dev/process/directives/LOOP_DIRECTIVE.md`. The night's ledger: $50 cap, nothing new
  past $45; the session was not started with `GRAPHENE_AGENT_LIVE_USD`, so the directive's $50 line is the opening,
  as decisions 151 and 166 read the last two nights'.
- **00:40** Lane 0: `dev/process/loop/before.md`. The suite on `main` as it is: 1,698 passed in 19 min.
- **00:42** Lanes 3, 4 and 5 started, one builder each in a worktree of the clone, each reviewed from two sides.
- **00:44** Lanes 1 and 2 proposed as one tree of five leaves through Graphene itself (`graphene plan propose -`,
  plan first on, accepted as the person), and run with four Sonnet executors at once, the meter on, the time view
  shot every minute. All five landed on their first attempt by 00:50: 12 agent-minutes, $2.07, width 4 of 5.
- **00:51** The scripted loop (a reader with a wrong field name, a tests leaf that finds it): `r` offered and
  taken, the owner fixed on top of what landed. It showed one gap: after `r` the tests leaf still read as "came
  back" when it already waited on the owner, so `R` left it alone. Fixed (`f7a9697`).
- **00:54** Live: feeds on Nemotron and on Claude Code, three runs each, and the statements task three times with
  red first on.
- **01:04** Red first's first rule flagged 8 of 9 statements leaves whose checks name an existing test beside their
  own new one. Refined: a red is outside by the failure's cause (`9e38e71`, `fa0ddc7`).
- **01:11** Nemotron run 2 closed the loop on a natural fault: `xml-test` found `normalize/fields.py` returning
  `price` where the rules expect `price_cents`; `r` reopened `xml-feed`; Nano fixed it on one attempt ($0.0077).
- **01:14** Three Claude Code runs came back on nothing (every leaf owns its own test), so a fault was planted at
  01:13:42 in a landed file; `e2e-xml` came back wanting it; `r` reopened `xml-source`; fixed in 4 turns ($0.11).
- **01:16** The planted whole-suite check: `red first` named `tests/test_zero.py`, the file no word of `python3 -m
  pytest -q` names.
- **01:20** The suite found that red first's checks outlived a closed terminal and a Ctrl-C waited for them: fixed
  (`7ce64e4`), with a test for a stop during red first.
- **01:38** Two skeptics a leaf on the dogfood's code: 44 findings, 13 distinct real ones fixed (`49297e6`); the
  rest are nits listed in `dev/process/loop/review.md`.
- **01:45** The suite green on lanes 1 and 2 (1,737 passed); the tag `statements-prereg-2` at `803f2c2`. Lane 6
  started on it; lane 3's 40 asks and the first four takes started on lane 3's build.
- **02:06** Lane 6 merged: PREREG names the tag and the four new blobs, PROVE.md builds the wheel from the tag,
  and its Once block ran from a fresh install: the rehearsal reads 5, 5, 0, 0 (`dev/process/loop/prove-run.md`).
