# The review of the meter branch, 7 October, 03:00 to 04:15

A workflow read the branch's diff against `main` in four areas: the meter's reading of the streams, `run.py`
with the night's ledger, the screens and the record, and plan first auto with the ledger's rows. Four
readers found 20 defects, 19 distinct; one skeptic each tried to refute the top six, reproducing them on a copy of the
branch. None was refuted. The other thirteen had no second reader; the fixers confirmed each one from the
code, in a test that fails without its fix, before fixing it. Three fixers worked in worktrees of their own,
one per group of files, and their branches were merged into `meter` (`9ca8d71`). The suite then passed:
1,612 in parallel, the 11 width tests that fail only in parallel passing alone.

## Verified by a skeptic, and fixed

| | what was wrong | commit |
|---|---|---|
| C1 | A stopped, unpriced or stream-less Claude Code or Codex attempt settled its $3 hold at $0, so the cap and the 90% rule never saw it. It now settles at the stream's dollars only when the stream gave the whole figure; else at the worst case, as a Token Factory call stopped while out does (decision 129). | `701f962` |
| C2 | A run killed outright left its holds in flight all night, and the next run was refused before its sweep could hand the leaves back. The hold rides on the attempt row; the sweep settles a dead run's hold, then the night is asked. | `f949daf` |
| C3 | A leaf a run brought back and the person then took showed the old attempt as live in the strip and the pane. Every "the attempt going now" reads the current hold (`meter.going`). | `988ea6d` |
| C4 | A leaf dropped mid-attempt, with no `ended` row, counted as a running agent forever. | `210536d` |
| C5 | A Claude attempt on a model the price table lacks stayed "no list price" after its result settled the dollars. | `f8565aa` |
| C6 | A resumed attempt took the earlier attempts' tokens off its own result, so every attempt after the first undercounted its output. Checked live at 03:20: a resumed result's `usage` is the call's own (`rows.md`). | `cb96ffd` |

## Confirmed by a fixer, and fixed

| | what was wrong | commit |
|---|---|---|
| U1 | A Codex edit named by its absolute path was judged outside the scope. From Codex's source, not yet seen live. | `ef38aeb` |
| U3 | The `l` pane showed an earlier hold's rows under this attempt's number. With C3. | `988ea6d` |
| U4 | The status line said the agents spent `$0.00` when what they used has no list price. | `78871a0` |
| U5 | A home directory with a dot or an underscore, as Claude Code spells it in a folder name, was neither hidden in a recording nor counted as a leak. | `399839a` |
| U6 | One leaf whose board item was already open on the board was taken at once. Any board item now makes it wait. | `dc5a4cd` |
| U8 | The run's bill line counted tokens a Claude result had priced as "tokens with no list price". With C5. | `f8565aa` |
| U9 | `--max-budget-usd=N` and `--output-format=stream-json`, the spellings with `=`, were not read. | `49f3fe3` |
| U10 | The same defect as C4. | `210536d` |
| U11 | The tree and DAG views noted `$0.00` on a leaf with no usage yet. | `abc4566` |
| U12 | One leaf whose scope could reach an untracked protected or read-only file was taken at once. It waits. | `b8963e6` |
| U13 | A prose mention of `<tool_call>` before a real call swallowed the call, and the planner took the message for its answer. | `c6a917d` |

## Left as they are

- **U2:** under a $10 opening, `watch`'s `R` runs four leaves; three $3 holds leave no room for the fourth, which
  comes back with the ledger's refusal instead of waiting for room. A scheduling change; not tonight.
- **U7:** the 8-path rule counts tracked files, so a glob over paths that do not exist yet counts as one. Changing
  it changes what lane 1 measured; it needs the evidence run again.
- Two narrow holes in C2: a run that dies between taking its hold and writing its attempt row, or a dead run's
  leaf released by hand before any sweep, keeps that hold in flight until the ledger rolls over at noon.
- C5's `<synthetic>` model: not confirmed that Claude Code writes such a message to the stream.
- U5: the leak count of a path under someone else's home spelled with dashes (`-Users-x-`) is not counted;
  counting `-home-` would flag ordinary words.
