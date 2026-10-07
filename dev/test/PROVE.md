# Prove it: the statements experiment, on a Saturday

Four runs of the task a paragraph should lose, with you as the person. `PREREG-statements.md` says
what is measured and what would make the tree lose. Read it first, once. Then do this, in order.

**Time.** About 30 minutes to set up and rehearse. Each run is up to 10 minutes of you at the start,
then the agents alone, then 5 to 20 minutes of you at the end. How long the agents take is not
known yet. The feeds runs of 23 September took 3 to 10 minutes each, and this task is about three
times their size: guess 20 to 60 minutes a run, and up to 3 hours. If the runs are long, do P1 and
T1 on Saturday and T2 and P2 on Sunday.

**Spend.** An estimate, not a measurement. The eight feeds runs of 23 September cost $0.45 to $1.54
each on sonnet (`runs-2026-09-23.json`). Scaled by this task's size, guess $3 to $10 a run and
$12 to $40 for all four. On a Claude subscription it is usage, not dollars. The rehearsal costs
nothing: it calls no model.

## Once

```sh
G=~/Desktop/AllThingsAgenticHackathon && cd $G && uv sync
uv build -q --wheel -o /tmp/prove-dist
UV_TOOL_DIR=~/graphene-prove/tool UV_TOOL_BIN_DIR=~/graphene-prove/bin uv tool install -q --force /tmp/prove-dist/*.whl
export PATH=~/graphene-prove/bin:$PATH && graphene --version        # write it down
$G/.venv/bin/python $G/dev/test/prove.py rehearse ~/graphene-prove/rehearsal
```

The rehearsal takes a minute. Its traps column must read 5, 5, 0, 0. If it does not, stop: the
harness is broken. Then read the card once, and nothing else in that directory:
`less $G/dev/test/tasks/statements/intent.md`.

Every shell of every run gets these three lines first:

```sh
G=~/Desktop/AllThingsAgenticHackathon && export PATH=~/graphene-prove/bin:$PATH
FLAGS="--model sonnet --permission-mode acceptEdits --output-format json --allowedTools Read Edit Write Glob Grep 'Bash(graphene *)' 'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)' 'Bash(sh scripts/*)'"
agent() { eval claude -p '"$1"' '"${@:2}"' $FLAGS; }
```

## Each run, in the order P1, T1, T2, P2

```sh
bash $G/dev/test/newrun.sh ~/graphene-prove statements alex <prompt|tree> <1|2>
source ~/graphene-prove/statements-alex-<arm>-<n>/env.sh
```

**Paragraph arm (`prompt`).**

```sh
rm .claude/settings.local.json                 # Graphene's hooks out of this repo
log clock start; snaps &
cp $G/dev/test/tasks/statements/paragraph.md ../m1.txt && nvim ../m1.txt   # add what you like, under 10 minutes
log prompt < ../m1.txt; log clock away
agent "$(cat ../m1.txt)" > ../e1.json          # then leave until it returns
```

**Tree arm (`tree`).** Put `graphene watch` in a right-hand pane.

```sh
graphene plan first on
log clock start; snaps &
log prompt < $G/dev/test/tasks/statements/paragraph.md
agent "$(cat $G/dev/test/tasks/statements/paragraph.md)" > ../e1.json      # the board and the tree
```

Answer the board and prune in `graphene watch`, at most 10 minutes from the tree on screen. Then:

```sh
log clock away
graphene run --parallel 3 --with "claude -p $FLAGS" > ../run-1.txt 2>&1    # then leave until it ends
```

**The end, both arms.**

```sh
log clock back
python3 $G/dev/test/logline.py "$R" executor result --from-json ../e1.json
git diff $BASE --stat; git diff $BASE; python3 -m unittest discover -q tests
```

One more round is allowed, clocked with `log clock away` before it and `log clock back` after. In
the paragraph arm it is one follow-up: `agent "$(cat ../m2.txt)" --resume <session_id from e1.json> >
../e2.json`, then log `e2.json` the same way. In the tree arm, take a leaf's offer (`w`, `b`) or
reopen it (`x`), then `graphene run --parallel 3 --with "claude -p $FLAGS" > ../run-2.txt 2>&1`.
Then `log review done; log clock done; kill %1`, and write what surprised you, and what you would
have corrected, in `../notes.md`.

## Where the numbers land

```sh
$G/.venv/bin/python $G/dev/test/prove.py count ~/graphene-prove/statements-alex-<arm>-<n>
$G/.venv/bin/python $G/dev/test/prove.py table ~/graphene-prove --out ~/graphene-prove/table.md
```

`count` writes the run's `tally.json`: traps, when the first wrong inference showed, your clocked
minutes, accept, held-out, dollars. `table` puts the four runs in one table. Copy it as printed into
`dev/test/results-statements-<date>.md`, with the hypothesis rows from the pre-registration and one
sentence under them. No number is typed.
