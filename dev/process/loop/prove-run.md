# PROVE.md's "Once", run from the tag

`dev/test/PROVE.md`'s "Once" section, run as written on 9 October 2026 at 05:57 UTC: one zsh, the lines in
order, a fresh tool install in an empty directory. Nothing in it calls a model. Two paths are written as
PROVE.md writes them: the scratch directory as `~/graphene-prove`, and the clone the tag was cut in as
`~/Desktop/AllThingsAgenticHackathon`. `$G` is a worktree of that clone at `statements-prereg-2`, commit
`eb9696f`. Each command is followed by what it printed. A command with no lines under it printed nothing.

```
$ cd ~/Desktop/AllThingsAgenticHackathon && git fetch -q --tags origin

$ git worktree add -q --detach ~/graphene-prove/tag statements-prereg-2

$ G=~/graphene-prove/tag && cd $G && uv sync
Using CPython 3.13.9 interpreter at: /opt/anaconda3/bin/python3
Creating virtual environment at: .venv
Resolved 30 packages in 2ms
   Building graphene-map @ file://~/graphene-prove/tag
      Built graphene-map @ file://~/graphene-prove/tag
Prepared 1 package in 299ms
Installed 29 packages in 75ms
 + aiofiles==25.1.0
 + annotated-doc==0.0.5
 + anyio==4.15.1
 + attrs==26.1.0
 + cattrs==26.2.0
 + certifi==2026.7.22
 + contree-sdk==0.3.6
 + graphene-map==0.5.0 (from file://~/graphene-prove/tag)
 + h11==0.16.0
 + httpcore==1.0.9
 + httpx==0.28.1
 + idna==3.20
 + iniconfig==2.3.0
 + linkify-it-py==2.2.0
 + markdown-it-py==4.2.0
 + mdit-py-plugins==0.6.1
 + mdurl==0.1.2
 + packaging==26.3
 + platformdirs==4.11.12
 + pluggy==1.6.0
 + pygments==2.21.0
 + pytest==9.1.1
 + rich==15.0.0
 + ruff==0.16.8
 + shellingham==1.5.4
 + strenum==0.4.15
 + textual==8.2.8
 + typer==0.27.2
 + typing-extensions==4.16.0

$ uv build -q --wheel -o ~/graphene-prove/dist

$ UV_TOOL_DIR=~/graphene-prove/tool UV_TOOL_BIN_DIR=~/graphene-prove/bin uv tool install -q --force ~/graphene-prove/dist/graphene_map-0.5.0-py3-none-any.whl

$ export PATH=~/graphene-prove/bin:$PATH && graphene --version        # write it down
graphene 0.5.0

$ $G/.venv/bin/python $G/dev/test/prove.py rehearse ~/graphene-prove/rehearsal
run       ~/graphene-prove/rehearsal/statements-tripall-tree-1
repo      ~/graphene-prove/rehearsal/statements-tripall-tree-1/repo
base      ced34710e33c9b0928beb1269ed3b8a07fe6dc56
runlog    ~/graphene-prove/rehearsal/statements-tripall-tree-1/runlog.jsonl
TMPDIR    ~/graphene-prove/rehearsal/statements-tripall-tree-1/tmp
env       ~/graphene-prove/rehearsal/statements-tripall-tree-1/env.sh
graphene  ~/graphene-prove/bin/graphene
version   graphene 0.5.0
run       ~/graphene-prove/rehearsal/statements-tripnone-tree-1
repo      ~/graphene-prove/rehearsal/statements-tripnone-tree-1/repo
base      a026103f5a0112715dc3cb95862cec03c5efe63f
runlog    ~/graphene-prove/rehearsal/statements-tripnone-tree-1/runlog.jsonl
TMPDIR    ~/graphene-prove/rehearsal/statements-tripnone-tree-1/tmp
env       ~/graphene-prove/rehearsal/statements-tripnone-tree-1/env.sh
graphene  ~/graphene-prove/bin/graphene
version   graphene 0.5.0
run       ~/graphene-prove/rehearsal/statements-tripall-prompt-1
repo      ~/graphene-prove/rehearsal/statements-tripall-prompt-1/repo
base      2103c90f221c37e8ccdf961f5c9fd89ada18c577
runlog    ~/graphene-prove/rehearsal/statements-tripall-prompt-1/runlog.jsonl
TMPDIR    ~/graphene-prove/rehearsal/statements-tripall-prompt-1/tmp
env       ~/graphene-prove/rehearsal/statements-tripall-prompt-1/env.sh
graphene  ~/graphene-prove/bin/graphene
version   graphene 0.5.0
run       ~/graphene-prove/rehearsal/statements-tripnone-prompt-1
repo      ~/graphene-prove/rehearsal/statements-tripnone-prompt-1/repo
base      21c25ea85669eb0b57972686816b531ac15d14fc
runlog    ~/graphene-prove/rehearsal/statements-tripnone-prompt-1/runlog.jsonl
TMPDIR    ~/graphene-prove/rehearsal/statements-tripnone-prompt-1/tmp
env       ~/graphene-prove/rehearsal/statements-tripnone-prompt-1/env.sh
graphene  ~/graphene-prove/bin/graphene
version   graphene 0.5.0
# Rehearsal: the statements task, scripted, no model

`dev/test/prove.py rehearse` on 2026-10-09, at eb9696f, with graphene 0.5.0 first on PATH. No model ran. A script
played the person, the planner and three executors, and applied the task's own patches: trip-all
is reference.patch then tripall.patch, trip-none is reference.patch alone. The minutes are near zero
because a script waits seconds, not hours. Each run's whole count is its tally.json.

| run | traps | tripped | first wrong (min) | at (UTC) | how it showed | person min (start, end) | tree read min | board (naming a conflict) | accept | held-out | cost $ | wall min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| statements-tripall-prompt-1 | 5 | legacy output changed, vendor touched, v1 shape changed, migrations out of order or not contiguous, protected test edited | 0.02 | 2026-10-09T05:58:27Z | snapshot 27940fe808 trips legacy output changed, v1 shape changed, migrations out of order or not contiguous | 0.0, 0.0 | — | 0 (0) | 17/24 | 11/12 | unknown | 0.1 |
| statements-tripall-tree-1 | 5 | legacy output changed, vendor touched, v1 shape changed, migrations out of order or not contiguous, protected test edited | 0.0 | 2026-10-09T05:57:43Z | decimalfmt was proposed with scope vendor/decimalfmt/** | 0.0, 0.0 | 0.0 | 1 (1) | 17/24 | 11/12 | unknown | 0.2 |
| statements-tripnone-prompt-1 | 0 | — | — | — | — | 0.0, 0.0 | — | 0 (0) | 24/24 | 12/12 | unknown | 0.1 |
| statements-tripnone-tree-1 | 0 | — | 0.0 | 2026-10-09T05:58:05Z | board item rounding: the person overrode its default | 0.0, 0.0 | 0.0 | 1 (1) | 24/24 | 12/12 | unknown | 0.2 |
```

Then the card: `less $G/dev/test/tasks/statements/intent.md` printed 58 lines, byte for byte the blob
`f755d3cf168e` that `PREREG-statements.md` names. The card is not copied here: it is the person's.

What it shows:

- The wheel is `~/graphene-prove/dist/graphene_map-0.5.0-py3-none-any.whl`, built in the tag's worktree.
  It prints `graphene 0.5.0`.
- `newrun.sh` found `~/graphene-prove/bin/graphene` in all four runs.
- The rehearsal's heading says `at eb9696f`. Its traps column reads 5, 5, 0, 0. It took 74 seconds.
