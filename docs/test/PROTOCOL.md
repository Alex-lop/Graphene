# The test: a person with a plan against a person with a paragraph

The question, from the collaboration directive: *for the same task, does a person working through
Graphene get fewer files touched outside intent, fewer "no, not that" restarts, and less rework
than the same person with a prompt and a diff?*

The tree directive sharpened it into the thing actually worth knowing: **how much work does a
person hand off per unit of their own attention, and was the result right?** Effort is counted in
person actions and typed characters. Since 23 September, `attention.py` also counts the words a
person was shown, and turns all three into **modelled** person-seconds with the keystroke-level
model: 0.28 s a character, 1.35 s an act, 250 words a minute. That is a model, never a clock.
Rightness is counted twice, once by a hidden acceptance on the sample the code was given and once
by held-out inputs it was never shown.

One task, two arms, the same person, the same private card. Every number at the end is computed by
`tally.py` from git, from `.graphene/graphene.db`, from `.graphene/runs/` and from the run log.
Nobody estimates anything. A run that goes badly is reported as it went.

---

## Ten minutes of your attention: the tree arm

Ten minutes of *yours*. The agents take longer than that, and you do not have to watch them. This
is the product as the README describes it: paragraph in, tree out, prune, run. The stand-ins' run
of it is in `results-2026-09-23.md`. Read that after you have done this, not before.

**Before the clock, once (not timed).** In WezTerm:

```sh
G=~/Desktop/AllThingsAgenticHackathon
mkdir -p ~/graphene-test
bash $G/docs/test/newrun.sh ~/graphene-test feeds alex tree 1
source ~/graphene-test/feeds-alex-tree-1/env.sh
less $G/docs/test/tasks/feeds/intent.md
```

`newrun.sh` makes `~/graphene-test/feeds-alex-tree-1/`:
- `repo/`, with `graphene init` already done;
- `base.sha`;
- an empty `runlog.jsonl`;
- a `tmp/` of its own;
- `env.sh`, which puts you in the repo and gives you `log` and `as_me`.

It prints the path and version of the `graphene` it found. That is the build you are testing, so
write it down. It will not make the same run twice. A second attempt goes in `feeds-alex-tree-2`,
with the same five lines and a 2 in place of the 1.

The card you just opened is what you want. Keep it beside you, never paste it into anything, and
do not open the repository's files before your first message.

Put the plan on the right and a small shell for the log at the bottom:

```sh
wezterm cli split-pane --right --percent 50 --cwd "$PWD" -- graphene watch
wezterm cli split-pane --bottom --percent 25 --cwd "$PWD"
```

In the new bottom pane:

```sh
G=~/Desktop/AllThingsAgenticHackathon
source ~/graphene-test/feeds-alex-tree-1/env.sh
```

You now have three panes: the top left is for the agent, the right is the plan, and the bottom is
for `log`. Every command below that is not `claude` goes in the bottom pane.

**Start a stopwatch**, on your phone rather than in the terminal.

1. **Write your paragraph**, from the card, the way you would really write it. In the bottom pane:

   ```sh
   nvim ../paragraph.txt
   log prompt < ../paragraph.txt
   pbcopy < ../paragraph.txt
   ```

   In the top-left pane run `claude`, paste with ⌘V, and press Enter. **Note the time.**

   At 240 characters or more, the agent writes no code. It proposes a tree, which appears on the
   right with every line marked `?`. Under 240 characters there is no tree, and the agent does the
   work at once. That is this build's rule, and it is what happened to all four Tuesday stand-ins.
   If it happens to you, carry on without a tree and say so in your notes.

2. **Prune it on the right**, with keys only:
   - `j` and `k` move, and `Enter` shows everything about a node;
   - `d` drops a node you did not mean;
   - `e` edits one node's contract;
   - `E` edits a subtree as text;
   - `y` accepts (`V`, a few `j`, then `y` accepts several);
   - `R` runs everything that is ready.

   As you press `R`, run `log run R` in the bottom pane, and **note the time**.

3. **When the leaves have landed, look.** In the bottom pane:

   ```sh
   git diff $BASE --stat
   git diff $BASE
   python3 -m unittest discover -q tests
   ```

4. **The change of mind on the card**, once the first part works. In the bottom pane:

   ```sh
   nvim ../change.txt
   log correction --mandated < ../change.txt
   pbcopy < ../change.txt
   ```

   Paste it into `claude` in the top left, prune what it proposes, press `R`, and run `log run R`
   again. If a result is wrong and you have to say so ("no, not that"), write it into
   `../no-1.txt`, then run `log correction < ../no-1.txt`, `pbcopy < ../no-1.txt` and paste it in.
   You have three corrections, the change of mind included.

   A leaf that comes back shows why on the right. `w` or `b` takes what it offers, and `x` reopens
   a finished leaf that is wrong.

5. **Stop the stopwatch** when the card is satisfied as far as you can tell, and run `log review done`.
   Write the three times in `~/graphene-test/feeds-alex-tree-1/notes.md`: paragraph sent, first
   `R`, and done. Add anything that surprised you.

**Afterwards (not timed).**

```sh
python3 $G/docs/test/summarize.py ~/graphene-test --out ~/graphene-test/runs.json
python3 $G/docs/test/attention.py ~/graphene-test/feeds-alex-tree-1
as_me graphene plan log
```

Keep the `--out`. Without it, `summarize.py` writes over `docs/test/runs-2026-09-23.json`, which
is the record of the stand-in test. `summarize.py` runs the hidden acceptance and the held-out
checks, which you never see during the run. `attention.py` lists every node you dropped or changed
before the first leaf started, each with its contract as the agent proposed it. For each one, the
question this test asks is: *left as proposed, would it have cost a restart, a wrong or unwanted
result by the card?* Have someone else answer that from the card, not you.

**What the numbers will and will not say about you:**
- The keys you pressed in `graphene watch` are in `graphene plan log`, not in the run log. The
  `acts` and `typed` columns therefore count only your paragraph, your messages and your `R`s.
- `R` runs the product's default executor, which is your usual `claude` model and does not print
  JSON. The cost column will say it is unpriced. The stand-ins' executors were sonnet with JSON
  output.
- The `person-s (model)` column is the keystroke-level model the stand-ins were measured with. It
  is not you. **Your stopwatch is the measure here.**

For scale: the model put a Tuesday run at about 9 minutes and a dense tree run, with a
3,300-to-3,600-character paragraph, at 60 to 70 modelled minutes. Most of that is typing and
reading.

**The paragraph arm, if you do it too.** Do it on another day, in a fresh run, and do not read the
tree arm's diff first:

```sh
bash $G/docs/test/newrun.sh ~/graphene-test feeds alex prompt 1
source ~/graphene-test/feeds-alex-prompt-1/env.sh
rm .claude/settings.local.json
```

The last line takes Graphene's hooks out of this repository. On 23 September they were left in.
At this build, a paragraph in a repository where `graphene init` has been run waits for a tree
whatever the arm, and both dense paragraph-arm stand-ins had to talk their way past it. Without
the hooks, nothing records the session's writes. This arm's `rework`, `churn` and `write events`
will then read zero and mean nothing. Files, the diff, outside-intent, acceptance and held-out
still come from git and the repo. Then follow steps 1, 3, 4 and 5 above, with no tree and no `R`,
and run the same `summarize.py` line over both runs.

Two arms of one task is an anecdote, not a result. It is still worth more than all of the
stand-ins, because you cannot type at machine speed and you will not remember the card perfectly.

---

## The four tasks

| task | shape | the trap |
|---|---|---|
| `report` | one file does the work | the feed's shape is under-specified, and a TOTAL row is the obvious wrong answer |
| `inventory` | three directories, and a node the person owns | a public signature, migrations the person writes, a number no agent may pick |
| `logs` | two parts, and the person changes their mind | the second part is asked for by level and wanted by hour |
| `feeds` | **six directories**, and the person does not know the layout | prices in cents, a summary that is not a product, a stale README that documents half the wiring |

```sh
python3 docs/test/make_task.py <report|inventory|logs|feeds> <dir>
```

Each prints the base commit. Each task's card, its intent globs and its hidden acceptance live in
`docs/test/tasks/<task>/`; `feeds` also has `quality.py`. The repo never contains the card:
neither arm can read the intent off disk, and both have to get it from the person.

`feeds` is the one built after the 20 September test found that a one- to three-file change gives
a paragraph nothing to lose. Doing it right needs a reader in `ingest/`, a field map in
`normalize/`, a rule in `validate/`, a name in `config/`, the usage line in `cli/` and a test —
and the card names none of those, because a person who has not opened the repo in a year does not
know them. Its README says only half of the wiring and has been stale since the config file was
added, which is the reason to wander.

---

## Fairness

These are the rules that make two numbers comparable. Break one and the run is void, not adjusted.

1. **The same card.** Both arms get `intent.md`, whole, before they start. Neither arm pastes it
   into an agent and neither lists the intent globs. The card is what the person knows; the arms
   differ only in how they can express it.
2. **The same budget.** At most **three** corrections per arm. A fourth means the arm is abandoned
   and reported as abandoned, with the three it spent.
3. **Neither arm is capped, and the check may state the answer.** *Changed 21 September.* The old
   rule capped the paragraph at 90 words and capped shaping at nothing, then handed the executor
   both — two different amounts of help, called one comparison. Capping shaping instead would
   remove the arm's whole method. So: **neither arm has a limit on what the person may write, in
   words or in nodes, and a node's check may contain the acceptance criteria or the expected
   output.** What the person types is measured rather than rationed, and `person_chars` and
   `spec_chars` are where the difference shows up. The two prohibitions in rule 1 still stand.
4. **The person does not read the repository before their first message.** *New 21 September.*
   They have not opened it in a year; that is what the card says and it is what makes "90 words
   cannot name the files" a fact rather than a rule. No `ls`, no grep, no opening a file, until
   the opening message is sent. Afterwards, anything.
5. **The style is how they write, not what they know.** Every stand-in gets the whole card. Two
   styles, and both arms are run in both:
   - **dense** — careful, long, every constraint they can still remember, in full sentences, and
     they shape every node until it says what they mean.
   - **tuesday** — under a minute of attention. Under thirty words, lower case, no file names, no
     list of constraints; in the plan arm they drop what is obviously wrong, accept, and go.
     This is the style the 20 September report said was missing, and it is the ordinary case.
6. **Both arms run `graphene init`.** The record exists in both, so both are measured the same
   way. The paragraph arm simply has no plan, so nothing there is ever refused.
   *False from 97e473c on (23 September).* At that build, a prompt of 240 characters or more in a
   repository with the hooks waits for a tree, plan or no plan. Both dense paragraph-arm runs were
   held: 3 and 1 refused writes, 3 extra messages each, and in one run two trees accepted unread.
   A paragraph arm free of Graphene needs `rm .claude/settings.local.json` right after
   `newrun.sh`. That also removes the arm's write record (rework, churn, write events), which is a
   trade no run has made yet. The recipe above makes it, and says so.
7. **Review is by reading.** `git diff <base>`, plus `graphene plan --all` and `graphene plan log`
   in the plan arm. **The person never runs `accept.py` or `quality.py` and never sees either.**
   They are run afterwards, once, by tally.
8. **The person's own work is the person's in both arms**, at the same point in the run, logged as
   `handwork` in both.
9. **A different stand-in per run**, and the arms alternate which goes first from cell to cell.
   The report says which went first where.
10. **One run at a time.** *New 21 September.* No two executors anywhere in the harness are ever
    in flight together, so `wall_seconds` means something and two runs cannot contend. Eight of
    the twelve 20 September runs overlapped and their wall times were worth nothing.
11. **Every run gets its own `TMPDIR`**, made by `newrun.sh`, and a proposal is fed to
    `graphene plan propose -` on standard input. Two 20 September executors wrote plan JSON into
    `/tmp` and a later task read a stale one; that is how a `report` node ended up in the `logs`
    plan.
12. **No rerun to get a better number.** A run that went wrong is reported as it went. A rerun is
    allowed only when the harness itself failed — the executor never started, the disk filled, the
    hook crashed — and the report names it as an infrastructure rerun.
13. **Nothing is tuned.** Not a glob, not a check, not a word of the card, once a run has started.
14. **The stand-in is not told what is being measured.** *New 21 September.* It gets its arm's
    method and its style and nothing about the hypothesis. `standin.py` prints both briefs from
    one template, so anyone can diff them. *Broken on 23 September:* the orchestrator told every
    stand-in to read the test's spec first, and the spec names the measures. The brief alone is
    not enough. Whatever starts a stand-in must not hand it the spec either.

---

## The run log

JSON lines, one object per line, one file per run. Write it with `logline.py`, which takes the
character count rather than having anyone type it, and takes an executor's cost out of the
executor's own JSON.

```json
{"t": 1789881061, "who": "person", "type": "prompt", "text": "…", "chars": 125}
{"t": 1789881086, "who": "executor", "type": "result", "text": "…", "cost_usd": 0.122, "turns": 10}
{"t": 1789881090, "who": "person", "type": "correction", "text": "by hour", "mandated": true}
```

- `t` — epoch seconds, or an ISO-8601 stamp. `wall_seconds` spans the first to the last.
- `who` — `person` or `executor`. Only a person's entries count toward `person_actions` and
  `person_chars`.
- `type` — `prompt`, `correction`, `shape`, `accept`, `run`, `review`, `handwork`, `result`,
  and since 23 September `drop`, `edit`, `widen`, `sibling`, `reopen` and `read`. `shape` is a
  person's edit to the plan before it ran; shaping is not a correction, and that is the claim
  being tested. `read` is what the person was shown, and it is not an act. `reopen` counts as a
  restart. `logline.py person edit --edit before after` records a text edit as the characters it
  added.
- `mandated` — on a `correction`, this one is the card's own change of mind, which the protocol
  forces on both arms. `restarts` counts it; `restarts_unmandated` does not. Report both.
- **Never log a `result` for an executor `graphene run` started.** Its cost is read out of
  `.graphene/runs/`; logging it as well counts it twice.

Write the log as you go, not afterwards from memory.

---

## What tally counts, and what it cannot

`tally.py` prints one JSON object per run. Every field comes from git, from the store, from
`.graphene/runs/` or from the run log, and the object says which. Four things are worth knowing:

**Most writes do not come through `Edit` or `Write`.** Executors do a lot of their editing with a
`python3 - <<EOF` heredoc. Claude Code attaches what a command changed to the `Bash` call, so
those writes are in the record after all, and tally counts them — keeping the two records apart
(`rework_from_edit_events` against `rework_from_shell`) so anyone can see which a number rests on.

**Churn is counted once per file, not once per record.** *Changed 21 September.* The two records
are two views of one filesystem. Adding them counted `.plan-logs.json` twice on 20 September and
printed 26 lines of rework for a scratch file, in the plan arm's disfavour. Per file, the larger
of the two is taken. That makes `rework_lines` a lower bound where it used to be an inflated upper
bound, and `churn_double_counted_lines` says exactly how much the old arithmetic would have added.

**A file created and removed inside the run is not rework.** Not in the base commit, not on disk
at the end: a scratch file came and went and no code was rewritten. `transient_files` and
`transient_churn_lines` name them, and they are out of `rework_lines`.

**A write inside `.graphene/worktrees/<node>/` is a write to the file it names.** `graphene run
--parallel` gives each leaf a worktree, and the hook records what happens in there against the
main repo's root — so every parallel write arrives looking like a write to `.graphene/`, which is
the one directory every count throws away. Tally maps it back. Without that, a parallel run
measures nothing.

**Executor cost is recoverable through `graphene run`, but only by reading its logs.** `graphene
run` writes each executor's stdout and stderr to `.graphene/runs/<node>-<attempt>.txt` and parses
none of it. Run the executor with `--output-format json` and that file *is* the vendor's JSON
object, cost and turns and session id included, so tally reads it out.
`executor_cost_from_graphene_runs_usd` is what came from there and
`executor_calls_unpriced` is how many calls nobody can price. *Changed 23 September:* a resumed
`claude -p` session reports its running total as `total_cost_usd`, so tally counts each session
once, at its largest total. `executor_cost_from_runlog_summed_usd` keeps the old sum, which
over-counted every resumed session on 20 and 21 September. What is missing in the product,
precisely: nothing in Graphene ever parses `done.stdout`, so no cost, turn count or executor
session id is stored in the plan, the log or anywhere a person can see it. The smallest change
would be to `json.loads(done.stdout)` when the executor's basename is `claude` and put
`total_cost_usd`, `num_turns` and `session_id` into the `finished` entry's detail dict — the same
place `changed:` already goes.

**What tally still cannot see.** A write outside the repository is invisible to it in both arms.
A change list with no hunks is reported in `notes` rather than counted as zero. Read `notes`
before comparing two arms.

`.graphene/` and `.claude/` are left out of every file count and every churn count in both arms.
`graphene init` runs in both, so both grow a store and a hooks file, and neither is anybody's
change.

Tally's own arithmetic is checked against a repo, a store, a `.graphene/runs/` and a run log built
by hand, where every expected number is worked out in a comment:

```sh
uv run pytest -q docs/test          # or: python3 docs/test/test_tally.py
```

---

## The two measures of rightness

`accept.py` runs the sample that was in the repo the whole time: does it do what the card asked,
and were the things the card said not to touch left alone. It is the same shape for every task.

`quality.py` is the half the 20 September test had no way to produce. For `feeds` it is twelve
feeds the code was never shown, each one an instance of something the card states as a *rule*
rather than as an example — only product elements are products, prices are in cents, nought means
"ask us", a product missing a field is skipped and not a crash, entities and accents survive, an
empty feed is a clean exit, order is the feed's order.

It used to say here that code passing `accept.py` by pattern-matching the sample fails this. It
does not. The 21 September auditor built three readers and measured: a correct one scores 12 of 12,
a lazy `el.tag != "summary"` scores 11, and a regex fitted to the literal shape of the sample's
product line scores 11. Eleven of the twelve properties come free from any `ElementTree` call plus
the repository's own `normalize()`, `to_cents(…, "minor")` and negative-price rule. **This suite
separates a lazy reader from a careful one by one check in twelve.** Treat a 12 of 12 as weak
evidence, and if you write a held-out suite for a new task, check what a deliberately lazy
implementation scores on it before you trust it. Both are run by tally, afterwards, and neither arm's
person ever sees either.
