# What this run did, and why it matters

Two nights of work landed on `main` on 12 and 13 October 2026: **PR #45** (the prove-it night, 10 October, 51
commits) and **PR #48** (the feel night, 11 and 12 October, 26 commits). Both were built on branches by agents,
reviewed at their seams by other agents, and merged by Alex. This file is the account for someone who did not watch:
where Graphene stood, what each night changed, what was measured and what was **not shown**, what only Graphene
does, what Alex still decides, and what is still open. Every number here is copied from the evidence the nights
left in the repository: `dev/process/prove/after.md` and `dev/process/feel/after.md`. None was typed anew.

## Where Graphene stood before (main at 907a7d0, 10 October)

Seven read-only readers and a critic read `main` at 907a7d0. Their verdict, in one line: real and unique, and not yet
easy. **Real and unique:** a write scope per leaf, refused before the write by a Claude Code hook and rechecked by
git when the leaf is declared done; a check that Graphene runs itself, in a clean worktree, not the agent's word for
it; red first, which runs that check before any work so a check that already passes is flagged; a failure sent back
to the leaf that owns the file, with the reason as a row and an offer (`w` widen, `b` sibling, `r` reopen, `n` wait);
and a meter of the person's own acts beside the agents' minutes and dollars. A scan of 37 products found none that
does these; they ship the loop (plan, approve, parallel subagents, PR) without the contract.

**Not yet easy:** the first paid ask could end with nothing when the planner's text form had one fault; `graphene run`
opened with a 297-character line of git flags; every command ended with the repository's full path on stderr; the
record's three coverage sentences read as a contradiction; `node show` printed the agent's orders to the person; the
demo was a scripted stand-in whose meter strip never drew; `?` on a came-back leaf started a paid planner call; and
eleven words (red first, ∅, width, at list price, came back, scope, needs, plan first, hooks, leaf, worktree) reached
the screen before anything defined them.

## The first night: prove it (PR #45)

The night's rule was written before any number: measure on 907a7d0 and on the branch with the same scripts, the same
budgets and the same isolation; claim a difference only where the intervals do not overlap; and judge by two things,
**a stranger's first hour** and **the morning after** (what a person can read of what their agents did). Every
planner, executor, walker and reader was a Sonnet session, so no human was measured; `dev/process/prove/rules.md`
holds the rules, `after.md` every pair with its file and its n.

What it changed, by the hour a stranger meets it:

- **The first ask** says what it cost, after its proposal lines (`the planner (claude sonnet-5-5): 5 calls, $0.11 at list price`), and a refused ask keeps the proposal it paid for and names the next step; `plan propose -` reports
every fault at once instead of one per round.
- **init** says what it did and how to undo it: the hooks it installed, that Claude Code sessions in that repository
are recorded on this machine, that accepting happens in `graphene watch` in another terminal; at a terminal it asks
the plan-first mode; `graphene init --remove` takes the hooks out.
- **The shipped executor** gained a spend cap (`--max-budget-usd 2`, an attempt) and `--strict-mcp-config`, and is
told its shell runs only `graphene node` and `graphene plan`, so it stops guessing.
- **The run** says first where it lands and under what cap; red first asks the environment before it judges (a
missing runner is said as such, never as a red; a Python installed editable from the repository is named, because
a check that imports it tests the checkout, not the leaf); the merge body carries the check, the executor, the
dollars and the reopen note; `graphene node diff` shows what a leaf changed; the record counts the commands an
executor was refused and keeps its last words whole.
- **A correctness fix outside the plan:** `done`'s clean tree was cut from a copy of the index that git trusted, so
an edit of the same size made in the second the file was checked out read as the committed file, and a broken leaf
could land. One line (the copy dated at epoch+1) closes it; `dev/process/prove/probes/racy.md` reproduces it
outside Graphene.

What the numbers said (907a7d0 against the branch):


| measure                                                                                                                     | 907a7d0                                                                  | the branch                                                                                                       |
| --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| X1, the first ask, 40 Sonnet asks a build: proposals by first answer                                                        | 40 of 40 [0.91, 1.00]                                                    | 35 of 40 [0.74, 0.95]: the intervals overlap, no difference shown; 40 of 40 by ask on both                       |
| X2, the feeds task with a planted fault, median of 3 runs: hidden checks; dollars; commands refused to the executors; turns | 18 of 20; $0.628; 18; 51                                                 | 18 of 20; $0.533; 4; 31                                                                                          |
| X2, the plain Claude Code session on the same task (median of 3)                                                            | 18 of 20; $0.353; 5 refusals; 21 turns; the fix said in the reply only   | the same arm on both builds                                                                                      |
| X3, ten morning-after questions, median of 8 readers: Graphene's record; `git log -p` plus the agents' last words           | 7; 4                                                                     | 7; 5 (the merge body made git answer one more)                                                                   |
| X4, pytest-bdd issue #476 on a real repository                                                                              | 2 landed by luck of import order; 148 of its tests pass                  | 0 landed: the leaf came back with the executor's own diagnosis of the editable install; nothing broken           |
| X5, the editable-install hole, $0                                                                                           | the broken leaf landed with `python3 -m pytest` and with `uv run pytest` | named before the run; `uv run pytest` refuses it; `python3 -m pytest` still lands it, as the rules expected      |
| X7, plan first on new repositories                                                                                          |                                                                          | `auto` took the feeds paragraph at once as one 8-path leaf 3 of 3 times; `on` made it wait for the person 3 of 3 |
| the suite at the tip                                                                                                        |                                                                          | 1,876 passed, 21 skipped                                                                                         |
| spend, every experiment on both builds                                                                                      |                                                                          | $20.61 by the sessions' own reports                                                                              |


**What was not shown.** The bet that a tree beats a paragraph was not tested and is not settled: the plain session
did the feeds task as well for less, as the rules expected. What the contract buys on that task is in kind, not in
score: the planted fault's fix landed in the owning leaf's file with the reason recorded as a row and a merge body,
where the plain session said it in its reply only. The schema planner was not built, because on 907a7d0 the first
ask already ended in a tree 40 of 40 times. No human was timed; `dev/process/prove/morning.md` has the protocol
for Alex's own hour on a repository he did not build.

## The second night: feel (PR #48)

Measured correctness was last night's work and holds. This night asked how Graphene feels in the hand. Three Fable
readers walked the installed wheel with a stand-in model, at no cost, each with one lens: **the words** every command
prints in the first hour, **the screen** of `graphene watch` at 80x24 and 120x36, and **the rhythm** of an hour under
a clock (what prints when, and where the person waits in silence). They brought back 36 things that feel wrong,
each pinned to a line of source with the smallest change (`dev/process/feel/findings.md`). A designer chose twelve
by felt difference per line of diff; a judge argued each, kept eleven whole and amended the rest
(`decisions.md`); four lanes built them, one commit per change with a test that fails on main; seven readers read
the merged branch at its seams and a fixer landed 26 fixes; an after-walk repeated the three walks on the result.

What a stranger reads now, before and after:

- **After init:** `plan first: on. Every ask in a session is proposed, one leaf included, and waits for you…`
(206 characters, six undefined words) became `plan first: on. Claude proposes a plan here before it writes; you accept it in` graphene watch`, in another terminal.` graphene plan first off `turns it off.` Eight Claude Code
event names became `(8 Claude Code hooks)`.
- **While the planner works:** nothing for half a minute became one line per tool call as it happens (  `reading normalize/fields.py`,   `searching def load`), and `graphene watch` counts the seconds since the planner was asked.
- **After ask and after accept:** `prune it: …` and `left alone, agents can reach: fields, readme` became `next:` graphene plan accept`, or prune in` graphene watch `(y accepts, d drops)` and `next:` graphene run `reaches fields, readme  (R in graphene watch)`.
- **The run:** the 297-character line became `landing into main at cc9b19a: claude, up to 2 at once; an attempt stops once it passes $2` and one line on how to follow it; the git flags live in `run --help`; every 30 seconds the
terminal says what each metered leaf is doing (`fields · 30 s · 4 turns · $0.08 · editing normalize/fields.py`);
red first names the check it flags: `their check (`true`) passes before any work: it would pass with nothing done`.
- **Every command's last line:**   `(the plan of /Users/you/…/repo)` became nothing, in the repository you stand in.
- **node show, for a person:** the agent's `finish:` and `stuck:` orders are gone, and `landed:` sits right under
the contract.
- **The watch screen at 80 columns:** the status clock is one phrase (`agents 1 <1m`), so `1/9 done` is back on the
line; `? help · q quit` end every key line (they were the first to fall off); the empty plan opens on `plan first: on` and three keys instead of six zeros; the legend names every glyph once, and the time view has a key of its own.
- **The demo:** `a scripted stand-in, not Nemotron` became `a scripted stand-in, no model ran`; the shipped recording
was made again with the meter on, so the strip shows while a leaf runs; a live run on Fable is recorded beside it
at `tests/recordings/feel-fable.jsonl`.

The after-walk's verdict on the 36 (`dev/process/feel/after.md`): 16 mended, 14 partly, 6 unchanged, none worse. The
six unchanged were left out on purpose, each with its reason in `decisions.md`: the record's `in short` and
coverage sentences, the closing line's `width` and `acts`, the seven spellings of a duration, the ask's flat
`proposed id:` rows, and two of the screen's smaller words, most of them Alex's vocabulary to settle first. In the
same captures, printed lines over 80 columns went from 88 to 73, and over 190 columns from 11 to 4. The suite at the
tip: 1,901 passed, 21 skipped (the one number here not copied from an after.md file: it is from a local run on
the merge's commit, and CI on that commit is green).

**What was not shown here, either.** One reader walked the after column, with the same stand-in and the same steps
as the three before it, and quoted every line so a person can read it themselves; that is a reading, not a
measurement, and no stranger has yet been timed on the new words.

## Why this makes Graphene the best it could be right now

The claim this repository can stand behind is narrow and true. Every other tool in the scan hands the agent the
loop and trusts it to stay in its lane; Graphene is the only one where the lane is enforced by the hook before the
write and by git at `done`, where the check is Graphene's and runs in a clean tree, where a failure goes back to the
leaf that owns the file with its reason kept, and where the person's own time and acts sit on the same line as the
agents' minutes and dollars. The two nights did not add to that list. They made it reachable: a stranger now gets
from `uv tool install` to a landed leaf on the README's words alone, with a cost line after every ask, a next step
after every act, a terminal that speaks while agents work, and a morning-after record that answered 7 of 8 factual
questions where `git log -p` answered 4 to 5. And two holes in `done` that could land a broken leaf are closed or
named before the run. What it does not claim is that a tree beats a paragraph on a small task; the plain session
still does the feeds task as well for less, and that is written down rather than argued away.

## Decisions that are Alex's (each one commit to drop)

From the prove night: plan first `on` for new repositories (init asks at a terminal); the shipped executor's
`--strict-mcp-config` and `--max-budget-usd 2`; `?` as help on every row, `t` to talk, a run that could start more than one leaf asking first; the Stop hook blocking an interactive session once; the bill line's `you` counting since
the last run; the HOW_IT_WORKS word cap at 3,300; the demo staying a scripted replay.

From the feel night: the `(the plan of …)` trailer printing only from outside the repository (decision 43); the
time view's `═` for a hold and `■` for a landing (decision 179); red first's gloss `it would pass with nothing done`
(decision 186); the empty plan's one-line status (decision 44); the re-recorded demo and the live Fable recording
(decision 8); and every rewritten sentence, which is a draft in his voice.

## Still open

The record's `in short` and `coverage:` sentences; `width` and `acts` on the closing line; one spelling for a
duration; the ask's flat proposal rows; the per-row `graphene plan accept <id>` under a proposed parent; the README's
two pictures, which still draw the old dotted clock; the schema planner's case if a planner other than Sonnet refuses
more often; `docs/HACKATHON.md`'s stale lines; and the one human number worth having, a stranger's timed first hour.

## To see it yourself

```
uv tool install graphene-map              # 0.5.0 on PyPI
cd a-small-repo && graphene demo          # the replay first; no key needed
graphene init                             # at a terminal: Claude Code, plan first on
graphene ask "what you want, in a paragraph"
graphene watch                            # another terminal: y accepts, d drops, R runs
graphene plan accept && graphene run --parallel 2
graphene node show <a landed leaf> && graphene plan record
graphene init --remove                    # the way out
```

