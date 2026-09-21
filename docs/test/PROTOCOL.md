# The test: a person with a plan against a person with a paragraph

The question, from the collaboration directive: *for the same task, does a person working through
Graphene get fewer files touched outside intent, fewer "no, not that" restarts, and less rework
than the same person with a prompt and a diff?*

The tree directive sharpened it into the thing actually worth knowing: **how much work does a
person hand off per unit of their own attention, and was the result right?** Effort is counted in
person actions and typed characters; rightness is counted twice, once by a hidden acceptance on
the sample the code was given and once by held-out inputs it was never shown.

One task, two arms, the same person, the same private card. Every number at the end is computed by
`tally.py` from git, from `.graphene/graphene.db`, from `.graphene/runs/` and from the run log.
Nobody estimates anything. A run that goes badly is reported as it went.

---

## Ten minutes of your attention

Ten minutes of *yours*. The agent takes longer than that and you are not watching it; that is the
whole point. Do one arm today and the other tomorrow, and do not read the other arm's diff first.

Read `docs/test/tasks/feeds/intent.md` and keep it beside you. It is what you want. You never
paste it into anything, and you never open the repository before your first message.

```sh
G=~/Desktop/AllThingsAgenticHackathon          # this checkout
W=$(mktemp -d)                                 # your own scratch, and your own TMPDIR
export TMPDIR=$W

bash $G/docs/test/newrun.sh $W feeds dense graphene 1    # prints the repo and the base sha
cd $W/feeds-dense-graphene-1/repo
R=$W/feeds-dense-graphene-1/runlog.jsonl
BASE=$(cat $W/feeds-dense-graphene-1/base.sha)
as_me() { env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT -u GRAPHENE_NODE "$@"; }
log() { python3 $G/docs/test/logline.py $R person "$@"; }
```

**Arm B, the tree.** Start a timer on yourself, not on the clock.

```sh
as_me graphene plan goal "northwind send xml now and I want it loading like the other two"
log shape "graphene plan goal …"
```

Ask an agent for the tree — in your own words, however you would say it, and ending with
*"propose a plan with `graphene plan propose -`, reading the JSON on standard input"*. Then shape
it in the terminal, which is the part that is supposed to be worth the tokens:

```sh
as_me graphene plan --all                       # the tree: the goal, the sub-goals, the leaves
as_me graphene node set n3 --scope 'normalize/fields.py' \
      --check 'python3 -m unittest -q tests.test_contract' \
      --goal 'their prices are in cents, not pounds'
as_me graphene node add "drop nought prices, every source" --parent n1 \
      --scope 'validate/rules.py' --check 'python3 -m unittest discover -q tests'
as_me graphene node drop n6
as_me graphene plan accept
log accept "graphene plan accept"
```

Then let it go, and watch it or do not:

```sh
as_me graphene run --parallel 2 --with "claude -p --model sonnet --permission-mode acceptEdits \
  --output-format json --allowedTools Read Edit Write Glob Grep 'Bash(graphene *)' \
  'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)'"
log run "graphene run --parallel 2"

as_me graphene watch --once                     # the tree as it stands, folded to what needs you
as_me graphene plan log                          # every start, check, landing and refusal
git diff $BASE                                   # the only review you get
log review "read the diff"
```

**Arm A, the paragraph.** Fresh repo, same card, nothing else changes.

```sh
bash $G/docs/test/newrun.sh $W feeds dense prompt 1
cd $W/feeds-dense-prompt-1/repo
MSG='…whatever you would actually have typed…'
printf '%s' "$MSG" | python3 $G/docs/test/logline.py $W/feeds-dense-prompt-1/runlog.jsonl person prompt
env -u GRAPHENE_AS claude -p "$MSG" --model sonnet --permission-mode acceptEdits \
  --output-format json --allowedTools Read Edit Write Glob Grep 'Bash(graphene *)' \
  'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)' \
  < /dev/null > $TMPDIR/e1.json
python3 $G/docs/test/logline.py $W/feeds-dense-prompt-1/runlog.jsonl executor result \
  --from-json $TMPDIR/e1.json
```

Carry on with `--resume <session_id>`. Every time you have to say "no, not that" — in any form,
however polite — that is a correction: `log correction "<what you typed>"`. You get three.

**Read them side by side.** This is the one command, and it recomputes everything:

```sh
python3 $G/docs/test/summarize.py $W
```

The first columns are the question as the directive asks it. `outside (final)` is "files touched
outside intent"; `restarts` is "no, not that", printed twice, once as the protocol counts it and
once with the change of mind the card forces on you taken out of both arms; `rework` is lines
written and then written over. `accept` is the hidden acceptance — you never see it during the
run — and `held-out` is the same code against inputs it was never shown, which is the number the
20 September test had no way to produce. `spec/act` is how much specification you got in front of
an executor for each thing you did, which is the closest this harness gets to the measure that
matters.

Two arms of one task is an anecdote, not a result. Two styles, two arms, two repetitions is a
morning.

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
    one template, so anyone can diff them.

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
- `type` — `prompt`, `correction`, `shape`, `accept`, `run`, `review`, `handwork`, `result`.
  `shape` is a person's edit to the plan before it ran; shaping is not a correction, and that is
  the claim being tested.
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
`executor_calls_unpriced` is how many calls nobody can price. What is missing in the product,
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
empty feed is a clean exit, order is the feed's order. Code that passes `accept.py` by
pattern-matching the sample fails here. Both are run by tally, afterwards, and neither arm's
person ever sees either.
