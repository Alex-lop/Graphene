# The test: a person with a plan against a person with a paragraph

The question, from the collaboration directive: *for the same task, does a person working through
Graphene get fewer files touched outside intent, fewer "no, not that" restarts, and less rework
than the same person with a prompt and a diff?*

One task, two arms, the same person, the same private intent card, the same budget. Every number
at the end is computed by `tally.py` from git, from `.graphene/graphene.db` and from the run log.
Nobody estimates anything. A run that goes badly is reported as it went.

---

## Run it yourself in ten minutes

You are the person. Pick one task — `report` is the shortest — and do it twice, once in each arm,
with a timer. Read `docs/test/tasks/report/intent.md` first and keep it beside you; it is what you
want, and you never paste it into either arm.

```sh
T=~/Desktop/AllThingsAgenticHackathon/docs/test
W=/tmp/graphene-test && mkdir -p $W

# one line that appends to a run log; you will call it after each thing you do
log() { python3 -c 'import json,sys,time; t=sys.argv[3]
print(json.dumps({"t":time.time(),"who":sys.argv[1],"type":sys.argv[2],"text":t,"chars":len(t)}))' "$@"; }
```

**Arm A, the paragraph.** Start the timer.

```sh
python3 $T/make_task.py report $W/a          # note the base sha it prints
cd $W/a && graphene init
log person shape "graphene init" >> $W/a.jsonl

# Now type your paragraph the way you would on a Tuesday: one paragraph, 90 words or fewer,
# your own words, any constraint you think of. Do not paste the card. Do not list globs.
claude --model sonnet --permission-mode acceptEdits
log person prompt "<paste what you actually typed>" >> $W/a.jsonl
```

Work as you normally do. Every time you have to say "no, not that" — in any form, however polite —
that is a correction: `log person correction "<what you typed>" >> $W/a.jsonl`. You get three, and
no more. When you are finished, read `git diff <base>` against the card, and stop the timer.

**Arm B, the plan.** Fresh repo, same card.

```sh
python3 $T/make_task.py report $W/b          # a new base sha
cd $W/b && graphene init
claude --model sonnet --permission-mode acceptEdits
```

Ask the agent for a plan in one sentence of 30 words or fewer, plus *"propose a plan with
`graphene plan propose`"*. Then shape it yourself, in another terminal, as the person:

```sh
as_me() { env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u AI_AGENT GRAPHENE_AS=person:$(id -un) "$@"; }
as_me graphene plan                                   # what it proposed
as_me graphene node set n1 --scope 'app/report.py' --check 'python3 -m unittest -q tests.test_report'
as_me graphene plan accept
as_me graphene run --with 'claude -p --model sonnet --permission-mode acceptEdits'
as_me graphene plan ; as_me graphene plan log ; git diff <base>
```

Log every one of those as a person action (`shape`, `accept`, `run`, `review`). Same three
corrections; here a correction is a `graphene node reopen --note …`, or a `--scope`/`--check`/
`--goal` edit to a node that had already started. Stop the timer.

**Read them side by side.**

```sh
for arm in a b; do
  python3 $T/tally.py $W/$arm --base <that arm's base sha> \
    --intent $T/tasks/report/intent_globs.txt --accept $T/tasks/report/accept.py \
    --arm $( [ $arm = a ] && echo prompt || echo graphene ) --runlog $W/$arm.jsonl > $W/$arm.json
done

python3 - <<'PY'
import json
a, b = (json.load(open(f"/tmp/graphene-test/{x}.json")) for x in "ab")
rows = ("files_outside_intent_final_n", "files_written_outside_intent_ever_n", "restarts",
        "rework_lines", "refused_writes", "person_actions", "person_chars",
        "executor_cost_usd", "executor_turns", "wall_seconds")
print(f"{'':38}{'paragraph':>12}{'plan':>12}")
for k in rows:
    print(f"{k:38}{a[k]!s:>12}{b[k]!s:>12}")
for name, d in (("paragraph", a), ("plan", b)):
    acc = d["acceptance"]
    print(f"{name}: {acc['passed']} of {acc['passed'] + acc['failed']} hidden checks passed")
    for x in acc["details"]:
        if not x["ok"]:
            print("   failed:", x["check"])
PY
```

The first four rows are the test. `files_outside_intent_*` is the directive's "files touched
outside intent"; `restarts` is its "no, not that"; `rework_lines` is its rework — lines that were
written and then written over, which the final diff no longer shows. `refused_writes` is what the
hooks stopped before it happened, and it is zero in the paragraph arm by construction: there is no
plan there to be outside of. The acceptance block is the thing you never see during the run: it
says whether what came out is what the card asked for, and whether the four things you said not to
touch were touched.

Two arms of one task is an anecdote, not a result. Three tasks, both arms, is the test.

---

## The three tasks

| task | shape | the trap |
|---|---|---|
| `report` | one file does the work | the feed's shape is under-specified, and a TOTAL row is the obvious wrong answer |
| `inventory` | three directories, and a node the person owns | a public signature, migrations the person writes, a number no agent may pick |
| `logs` | two parts, and the person changes their mind | the second part is asked for by level and wanted by hour |

```sh
python3 docs/test/make_task.py report    <dir>
python3 docs/test/make_task.py inventory <dir>
python3 docs/test/make_task.py logs      <dir>
```

Each prints the base commit. Each task's card, its intent globs and its hidden acceptance live in
`docs/test/tasks/<task>/`. The repo never contains the card: neither arm can read the intent off
disk, and both arms have to get it from the person.

---

## The run log

JSON lines, one object per line, one file per arm.

```json
{"t": 1789881061, "who": "person", "type": "prompt", "text": "…", "chars": 125}
{"t": 1789881086, "who": "executor", "type": "result", "text": "…", "cost_usd": 0.122129, "turns": 10, "session_id": "f60caf4a-…"}
```

- `t` — epoch seconds, or an ISO-8601 stamp. `wall_seconds` is the span from the first to the last.
- `who` — `person` or `executor`. Only a person's entries count toward `person_actions` and
  `person_chars`.
- `type` — one of:
  - `prompt` — the person's opening paragraph (paragraph arm) or plan request (plan arm)
  - `correction` — the person had to say "no, not that". This is `restarts`. See the budget below.
  - `shape` — a person's edit to the plan before it ran: `node add`, `node set`, `drop`, `owner`,
    `check`, `accept`. Shaping is not a correction; that is the whole claim being tested.
  - `accept`, `run`, `review` — the person accepted the plan, started a run, read the diff
  - `handwork` — the person did a node themselves, by hand
  - `result` — an executor finished. Carries `cost_usd`, `turns` and `session_id` when the
    executor was run with `--output-format json`; leave them out of an interactive session and
    `executor_cost_usd` will be 0, which tally reports as 0 rather than guessing.
- `text` — what was typed. `chars` is its length; when it is missing, tally counts `text` itself.

Write the log as you go, not afterwards from memory.

---

## Fairness

These are the rules that make the two numbers comparable. Break one and the run is void, not
adjusted.

1. **The same card.** Both arms get `intent.md`, whole, before they start. Neither arm pastes it
   into an agent, and neither arm lists the intent globs to an agent. The card is what the person
   knows; the arms differ only in how they can express it.
2. **The same budget.** At most **three** corrections per arm. A fourth means the arm is abandoned
   and reported as abandoned, with the three it spent.
3. **The paragraph arm's first prompt** is one paragraph, **90 words or fewer**, written the way a
   busy developer types it. Any constraint they think of, in their own words. No pasted card, no
   glob list, no bullet points.
4. **The plan arm's first prompt** is one sentence of task description, **30 words or fewer**, plus
   *"propose a plan with `graphene plan propose`"*. Everything else the person wants goes into the
   plan, by shaping it — that is the arm's whole method, and shaping is not spending a correction.
5. **Both arms run `graphene init`.** The record exists in both, so both are measured the same way.
   The paragraph arm simply has no plan, so nothing there is ever refused.
6. **Review is by reading.** In both arms the person reviews with the diff and the card —
   `git diff <base>`, plus `graphene plan` and `graphene plan log` in the plan arm. **The person
   never runs `accept.py` and never sees it.** It is run once, afterwards, by tally.
7. **The person's own work is the person's in both arms.** `inventory` has a number only the person
   sets. In the plan arm that is a node owned by them; in the paragraph arm they open the file and
   type it. Same work, same point in the run, logged as `handwork` in both.
8. **A different stand-in person per arm**, so the second arm is not the first one done twice with
   hindsight. Alternate which arm goes first from task to task, and say in the report which went
   first where.
9. **No rerun to get a better number.** A run that went wrong is reported as it went. A rerun is
   allowed only when the harness itself failed — the executor never started, the disk filled, the
   hook crashed — and the report names it as an infrastructure rerun.
10. **Nothing is tuned.** Not a glob, not a check, not a word of the card, once a run has started.

---

## The stand-in person

A sub-agent playing the person gets: the task name, the repo path, the base sha, the whole of
`intent.md`, the arm, and these rules. It does not get `accept.py`, `intent_globs.txt`, or the
other arm's transcript.

**Paragraph arm**

1. `graphene init`; log it as `shape`.
2. Write the paragraph (rule 3) and send it to the executor. Log as `prompt`.
3. Read what came back and the diff. If it is not what the card wants, one `correction` — a
   follow-up message in the same session. Up to three.
4. `inventory`: do your own part by hand when the executor's first reply lands. Log as `handwork`.
5. `logs`: the change of mind is a follow-up message once the parsing is done, and it costs one of
   your three corrections. That is what the paragraph arm has instead of a boundary.
6. Stop when the card is satisfied as far as you can tell, or the budget is gone. Log a `review`.

**Plan arm**

1. `graphene init`; log as `shape`.
2. Ask for a plan (rule 4). Log as `prompt`.
3. Shape what it proposed: `node set` a scope, add a check, split a node, `node add` one it missed,
   `--owner me` for what is yours. Log each as `shape`. This is free, and it is the point.
4. `graphene plan accept`. Log as `accept`.
5. `graphene run --with '<executor>'`. Log as `run`, and log each executor result.
6. When the run stops on a node that is yours, do it by hand through the same gate
   (`graphene node start <id>` … `graphene node done <id>`). Log as `handwork`.
7. `logs`: the change of mind is applied **at the boundary** — `graphene node set` on the node that
   has not started yet — and a `node set` on a node that has not started is a `shape`, not a
   correction. Editing a node that has already started is a `correction`. So is
   `graphene node reopen`, and so is a release that needs you.
8. Review with `graphene plan`, `graphene plan log` and `git diff <base>`. Log as `review`.

The executor, in both arms:

```sh
claude -p --model sonnet --permission-mode acceptEdits --output-format json \
  --allowedTools Read Edit Write Glob Grep "Bash(graphene *)" "Bash(python3 *)" \
  "Bash(git *)" "Bash(ls *)" "Bash(cat *)" "Bash(mkdir *)" < /dev/null
```

`--resume <session_id>` continues it. `--output-format json` is what gives the run log its
`cost_usd`, `turns` and `session_id`.

---

## What tally counts, and what it cannot

`tally.py` prints one JSON object per arm. Every field comes from git, from the store, or from the
run log, and the object says which. Two things are worth knowing before you read one:

**Most writes do not come through `Edit` or `Write`.** In the dry run that built this harness, the
executor did all of its editing with a `python3 - <<EOF` heredoc: the store held six `Read`s, one
`Bash` and not a single file-tool event. Claude Code attaches what a command changed to the `Bash`
call, so those writes are in the record after all, and tally counts them — but it keeps them apart
(`rework_from_edit_events` against `rework_from_shell`, and
`files_written_outside_intent_by_source`) so you can always see which record a number rests on.
When `recorded_write_events` is 0 and `rework_from_shell` is not, that is what happened.

**`rework_lines` is recorded churn minus the final diff, floored at zero.** It answers "how much
was written and then written over". It is only as good as the record: if a change list comes back
with no hunks, or a payload was too large to keep, tally says so in `notes` rather than quietly
counting zero. Read `notes` before you compare two arms.

`.graphene/` and `.claude/` are left out of every file count in both arms. `graphene init` runs in
both, so both grow a store and a hooks file, and neither is anybody's change.

Tally's own arithmetic is checked against a repo, a store and a run log built by hand, where every
expected number is worked out in a comment:

```sh
python3 docs/test/test_tally.py
```

