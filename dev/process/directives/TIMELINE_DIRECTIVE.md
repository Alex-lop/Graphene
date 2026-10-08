# Graphene: the timeline directive

*For the Opus 5.5 agent that runs on this repo next. Written 8 October 2026 from a review of `main` after the meter night (PR #40). Commit this file at `dev/process/directives/TIMELINE_DIRECTIVE.md` before you start. The working rules of the earlier directives hold: a branch, small green commits, one PR, `dev/process/morning.md` current at every milestone, the voice rules of the cut directive for everything you write.*

---

## A note from Alex (edit in your own words, then keep it)

Last night's run told me the truth about what broke, and that's why tonight exists. You have up to $40 of live testing and I want you to use it on the fixes, not on new things. Be relentless about running the real thing until each fix is proven by a number, and write down every run. If something blocks you, route around it; if you can't, write the exact command for me and keep going. Don't give up on a lane because the first run broke. I believe in this project and in you.

---

## Alex decides before sending this (edit, then delete this block)

- Spend cap: **$40** hard, nothing new started past $35, one ledger, a purpose on every row.
- The README: **untouched** (default). Not a word, not a number.
- The registered arms of the statements experiment: **still Alex's** (default).
- Lane order if the night runs short: **1, 2, 3, 4, 5, 6** (default). Lane 6 is written at every milestone regardless.

---

## What kind of run this is

The meter night found three things and fixed none of them. Tonight fixes them, builds one view, and leaves Alex a morning he can run in thirty minutes.

1. **Most stopped runs died on one cause.** Statements run 2 stopped at 3 of 7 leaves; run 3 came back on `statement-sections`; Nemotron takes 4, 6, 8, 9, 12 and 17 came back. Every time: a leaf's check ran a test file another leaf owned, or two leaves needed to write the same test file. The planner rules already say "two leaves never share a path" and "a check can pass with what its scope and its needs write." Planners don't follow it, and nothing checks it. Lane 1.
2. **The Nemotron planner fails on format.** 11 of 19 takes produced no proposal: markdown headings, JSON instead of text, `<tool_call>` as text, a `needs:` naming no node, a cycle. Ultra is asked to write Graphene's indented text grammar. `plan propose` already reads `{"nodes": [...]}`, and `cover`, `lookup` and `note` already call Token Factory with a strict JSON schema. The planner should too. Lane 2.
3. **`auto` doesn't work.** Two nights of evidence: the feeds paragraph became one leaf 2 of 3 times under `auto`, and the 8-path threshold is fitted to one repo. No rule separates a small ask from a big one, because the planner sets the granularity. The default goes back to `on`. Lane 3.

Then the one thing built tonight: **the timeline**, a fourth view that shows how the agents worked, over time. Lane 4. The README is Alex's and stays as it is.

Net source lines may go up for the timeline and the propose-time check, and for nothing else.

## The budget

One ledger at `~/.graphene/night/`, as the last two nights. Purposes: `scopes`, `planner`, `first`, `timeline`, `takes`, `dogfood`. Hard cap $40, nothing new past $35. Spend in this order: lane 1's measurement (~$10), lane 2's measurement and takes (~$12), lane 3's evidence (~$3), lane 5's recordings (~$5), the rest in reserve. The key is never printed, copied, written to a file or sent anywhere but Token Factory.

## Lane 0: the numbers to beat

Before any change, write down the baselines, from last night's records, in `dev/process/timeline/before.md`:

- **Hand-backs over test files.** From `dev/process/meter/statements-practice.md` and `takes.md`: how many leaves came back because their check ran, or they needed to write, a file in another leaf's scope. Count them, name them.
- **Nemotron proposal rate.** From `takes.md`: proposals produced over asks made (a "no proposal, twice" is 0 of 2).
- **`auto` on the paragraph.** 1 tree in 3, from `dev/process/meter/auto-evidence.md`.

The brief leads with these three numbers before and after.

## Lane 1: a check never runs another leaf's file

Two parts, the mechanical one first.

**At propose time, Graphene checks the tree.** For every leaf, the paths its check names (tokens that resolve to a tracked file, a path a glob in some scope covers, or a directory of such) are compared with every other leaf's scope. A check that names a path inside another leaf's scope, where that leaf is not in `needs:`, gets `needs:` added and the proposal says so in one line per leaf. Two leaves whose scopes cover one path are refused by their lines, as the text form refuses a line it cannot read. The same check runs on `plan edit` and `node set --check`, so a person is told too. Keep it conservative: a token that resolves to nothing is ignored. Decide and write down what a check that names a directory means (`tests/` covering another leaf's `tests/test_x.py` waits on it).

**The planner rules say it plainly.** In `ask.py`'s `RULES` and in the Nemotron planner's system prompt, one rule in the cut directive's voice: a leaf's check may run only files in its own scope or files that exist at the base commit; a leaf that needs a test another leaf writes waits on it with `needs:`; when several leaves share one test file, give each leaf its own test file, or make one `tests` leaf that waits on all of them. Nothing else in `RULES` changes.

**Measure it.** The statements task at its current size, with stand-ins as the 23 September harness runs them, `--parallel 3`, three runs, as practice. Count hand-backs over test files and leaves that never ran, against lane 0. Then the feeds task twice. If hand-backs don't fall, say so and say what the planner did instead.

## Lane 2: the Nemotron planner proposes in JSON

- Write the JSON schema for a proposal: `{"goal": …, "board": [{kind, id, text, default, options, then, about}], "nodes": [{id, title, goal, scope, check, needs, parent, mark}]}`, matching what `plan propose` already reads and what the text form carries, including `then:` lines. Strict, every field typed, `additionalProperties: false`.
- The Nemotron planner asks Token Factory with `response_format: json_schema, strict: true`, as `cover.py` does, and hands the answer to the same code path the text form takes (convert to the text form, or feed `propose` the JSON; whichever keeps one validator). A refused proposal is sent back once with the validator's exact words, and the second answer is the answer.
- A `<tool_call>` written as text is already read as a call (`b2a26b9`); keep that.
- The Claude Code and Codex planners stay on the text form. They produce it.
- **Measure it.** Ten `graphene ask` runs on feeds with Ultra, ten on report. Proposal rate against lane 0. Then up to six full takes with `dev/proof/nemotron.sh`, Nano and Super on the leaves, in Sandboxes when ConTree accepts the project. A clean take is one where every leaf landed or came back for a reason the person would accept. Record every take; keep the best in `tests/recordings/` with the leak check; say which model did what.

## Lane 3: plan first is `on`

- The default for new repos is `on`. An existing store on `auto` stays `auto` until the person changes it; say so in the CHANGELOG.
- `auto` stays as the opt-in it is, with its rule as it stands. `P` cycles `on`, `auto`, `off`.
- Under `on`, a one-leaf proposal in `watch` is one row and `y` takes it: nothing more to read. Check that the status line says what waits and that `y` on a one-leaf proposal starts it when an executor is chosen (ask Alex nothing; `R` is still the key that runs).
- Small fix in the same lane: the Claude Code planner reports its cost too (`--output-format stream-json` on the planner's command), so the ledger stops holding $1.50 of worst case per ask. Last night $15 of $41 was planners held, not spent.
- Evidence: the feeds paragraph under `on`, three asks on Sonnet: every one a proposal the person sees in `watch`, with its board item when the planner puts one up. One Tuesday ask: one row, `y`, done.

## Lane 4: the timeline

A fourth view, on Tab after `dag`, named `time`, in `src/graphene_map/view_time.py`, registered in `VIEWS`. It also prints with `graphene plan --view time`.

### What it shows

One lane per leaf that has ever been held, in the outline's order, under one lane for the person. Time runs left to right from the plan's first `asked` or first `started`, whichever is earlier, to now (or to the last event when nothing runs). A label column of at most 14 cells; the rest is time.

A leaf's lane is a bar per attempt, one cell per slice of time, each cell a block whose character says what the executor was mostly doing in that slice: reading, editing, running a command, talking. A slice with no event for more than a minute is drawn dim, as idle. Between attempts the lane is empty. On the bar, marks for the moments that matter: a write refused, a check passed or failed, the leaf came back, the leaf landed, the leaf is running now. The person's lane has a tick per act (a key in `watch`, a command typed). The bottom line is the view's note: `3 lanes · 12 min · 1 came back · agents 31 min $2.41 · you 4 acts ~3 min`. An axis line under the lanes says the minutes.

A target, in spirit; the glyphs and the palette are yours, but each block must read on a dark and a light terminal and in the GIF:

```
 you        |   |            |                        |
 zero-rule  ▓▓▒▒▒▒░░✓◆
 xml-feed   ░░░░░░░▓▓▓▓▒▒▒▒▒▒×  ↩ ▓▓▓▓▒▒▒✓◆
 report     ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓▓▓▓▓▓▓▓▓▒▒▒▒▒░░░░░░░ ●
            0m        3m        6m        9m        12m
 3 lanes · 12 min · 1 came back · agents 31 min $2.41 · you 4 acts ~3 min
```

The cursor on a lane is on that leaf, so Enter, `l`, `e` and the rest work as in every view. In the detail pane under the view, a running or finished leaf shows its activity: the `did` and `said` rows in order, repeats collapsed (`editing cli/main.py ×4`), each with how long after the attempt began. That is the record `node show` already prints, live.

### How it fits the views' contract

Views never read the store. Extend the contract the way `METER = True` did: a view that says `EVENTS = True` is given `events`, the rows it needs (`attempt`, `did`, `said`, `usage`, `refused`, `check_passed`, `check_failed`, `released`, `finished`, `landed`, and the person's acts), by node, with timestamps. `suits` scores above the outline only when some leaf has an attempt; `draw` returns None when the time column is under 30 cells. Scrolls when there are more lanes than rows. Redraws on `watch`'s tick, so a running bar grows.

### Replay

`graphene demo` replays store frames, so the view replays for free. Verify on `tests/recordings/meter-claude.jsonl`: Tab to `time` during the replay and the bars grow as the run did. Then record the feeds run again on Claude Code with the view open and keep it as the shipped demo recording if it is at least as good as the one there.

### Evidence

The view at 80 and 120 columns, live, mid-run, on Claude Code and on Nemotron; the same after the run; `graphene plan --view time` printed; the replay. All in `dev/process/timeline/screens/`.

## Lane 5: the recordings and the GIF

After lanes 1 to 4: one clean feeds run on Claude Code with `watch` on `time`, recorded for `graphene demo`; the best Nemotron take from lane 2. Rebuild `docs/assets/watch.gif` only if the new recording is better than the one there; the README's image path does not change.

## Lane 6: the morning, for Alex

This lane is written at every milestone, not at the end. `dev/process/morning.md` has, above everything else, a section called **Your 30 minutes**: the exact commands, in order, with what each should print and what to look at. It assumes a fresh terminal and nothing but `uv` and `git`. It covers: installing the branch as a tool in its own directory; the before-and-after numbers; `graphene demo` with Tab to `time`; the five-minute check on a scratch repo; the three decisions; and the one command that merges the PR. Nothing in it needs a key.

Below it, **Your practice run**: the steps for Alex to use Graphene for one hour on one of his own repos, with `plan first on`, a paragraph of his own, Claude Code as the executor, `watch` on `time`. What to note while he does it (where the tree misread him, what he pruned, what came back, what the timeline showed that the live row didn't), in a file he can paste into Issues.

## What not to do

- Do not touch the README.
- No new visible command. The timeline lives on Tab and `--view`.
- No web page, no server, no export.
- Do not run the registered arms. Do not change what `PREREG-statements.md` measures.
- Do not tune a planner's wording until a paragraph becomes a tree. Measure, report.
- Do not touch `~/.claude/settings.json`. Do not push `main`. Do not force-push. Do not tag or publish.
- Do not stop at the first broken run.

## Verification before the PR

1. Full suite on the CI matrix, `ruff check` clean, `uv build`, the wheel smoke test, `graphene demo --once` from the wheel.
2. Lane 0's three numbers, before and after, in the brief.
3. The propose-time check under tests: a check naming another leaf's file gets `needs:`; two scopes on one path are refused by line; a token that resolves to nothing is ignored.
4. Lane 2's proposal rate over 20 asks and the takes, each with its ledger rows.
5. Lane 3's transcripts.
6. Lane 4's screens, the printed view, and the replay.
7. The cut's lane 0 scenario (`dev/process/cut/lane0.sh`) still leaves the checkout clean.
8. The ledger under $40, by purpose.
9. `Your 30 minutes` run as written from a fresh tool install at the branch, at the end, and the time it took.

## The decisions that are yours

- The timeline's glyphs, palette, slice length and idle threshold.
- What a check naming a directory means.
- The JSON schema's exact shape.
- Which recording ships as the demo.

## The decisions that are Alex's, with your defaults

In the brief, each with the default you took: whether `auto` should stay at all; whether the Nemotron take is good enough for the video; whether the registered arms should now run; anything the propose-time check refused that a person would have wanted.

## The morning

`dev/process/morning.md`: **Your 30 minutes** and **Your practice run** first (lane 6), then the brief, at most twenty lines, no paragraphs:

1. **The three numbers**, before and after.
2. **Watch first:** the replay with the timeline, and the best take.
3. **The bill**, by purpose against $40.
4. **Decide:** at most three questions, each with your default.
5. **Broken or risky:** three lines at most.

Below the brief: DIRECTION.md gets "Decisions taken on the night of the timeline directive", at most fifteen, each at most three lines. The state of every branch and the rollback SHA.

## When to stop

- At 07:15, start nothing new and nothing live.
- By 07:45, everything is merged into the `timeline` branch and green.
- By 07:55, it is pushed, with the PR description current and `Your 30 minutes` run once from the pushed branch.

A lane not reached stops where it stands, with its state written down.

Now go. Fix what the runs broke on, draw the time, and leave Alex a morning he can finish before class.
