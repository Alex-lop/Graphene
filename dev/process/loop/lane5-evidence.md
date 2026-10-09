# Lane 5 evidence: ids, the ~ mark, re-judge

Items A, C and D of the loop directive's lane 5, as the person sees them. Item B is `node show`
saying "against base". It landed on `loop` in f7e56f4, with its own test, and is not on this branch.

Before is commit 7fe75af, where `loop` stood when the lane began. After is commit add28dc
on `l5`, with the review's fixes. Each case is a fresh git repo in a scratch directory, written `<tmp>`.
Your commands ran through subprocess with no agent's mark in their environment: CLAUDECODE,
CLAUDE_CODE_SESSION_ID, CLAUDE_CODE_ENTRYPOINT, AI_AGENT, GRAPHENE_NODE and GRAPHENE_PLANNER were removed.
With no terminal, the log names you `alex (no terminal)`. The planner's commands ran as a Claude Code
session. `graphene watch` is the headless screen at 80 columns, drawn as `dev/screens/meter_shot.py`
draws it.

## A. Ids are never cut

The time view's label column held 14 cells at most, so a longer id was cut. Now the column fits the
longest id, and 3 cells more. A view 80 columns wide leaves a 32-character id 45 cells of time. An
80-column terminal draws the view in 78 columns (`views.room`), in watch and in
`plan --view time --width 80` alike. There it leaves 43 cells, as below. Both are above the 30 the view
needs. The goal line is still cut to fit. `tests/test_view_time.py` pins 45, 43 and the cut goal.

Two leaves, one with a 32-character id. A Claude Code session starts both, so each has a lane.

```
[you] $ graphene node add 'a long id' --id label-column-fits-the-longest-id --scope a.py --check true
○ a long id  label-column-fits-the-longest-id  ready
```

```
[you] $ graphene node add 'a short id' --id b --scope b.py --check true
○ a short id  b  ready
```

Before (7fe75af):

```
[you] $ graphene plan --view time --width 80 --height 24
no goal yet
 you
 label-colu…  ●
 b            ●
              0s              15s             30s             45s
2 lanes · <1 min · agents 0 min · you 0 acts ~0 min
```

After (add28dc):

```
[you] $ graphene plan --view time --width 80 --height 24
no goal yet
 you
 label-column-fits-the-longest-id  ●
 b                                 ●
                                   0s        15s        30s        45s
2 lanes · <1 min · agents 0 min · you 0 acts ~0 min
```

## C. The ~ mark

Graphene adds a need when a check runs a file another leaf writes. It logged that need under your name.
`graphene plan changes` and the screen's ~ pass over your own acts, so neither showed it. Each command
printed its `waits on` line, before and after. Now Graphene logs the need as its own edit, in a row after
yours. `node set` prints both rows, and its revision counts both, as `plan edit`'s already did.
`tests/test_talk.py` pins the four commands.

### `graphene node set --check`: leaf-a's new check runs leaf-b's file

```
[you] $ graphene node add 'leaf a' --id leaf-a --scope a.py --scope tests/test_a.py --check true
○ leaf a  leaf-a  ready
```

```
[you] $ graphene node add 'leaf b' --id leaf-b --scope b.py --scope tests/test_b.py --check true
○ leaf b  leaf-b  ready
```

```
[you] $ graphene plan seen
0 changes marked as seen; what anyone else changes next is marked
```

Before (7fe75af):

```
[you] $ graphene node set leaf-a --check 'python3 -m pytest tests/test_b.py -q'
leaf-a is now revision 2:
  check: true → python3 -m pytest tests/test_b.py -q
  needs: none → leaf-b
leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-node-set
▼ ○ no goal yet                                                        0/2 done
├   ◌ leaf a                                                   leaf-a  waiting
└   ○ leaf b                                                   leaf-b  ready
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/2 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ◌ leaf a                                                      leaf-a  waiting
 ○ leaf b                                                      leaf-b  ready

 waiting  leaf-a on leaf-b (ready)








 0 on you · agents 0 · you 3 acts ~1m · R: 1 ready · 0/2 done
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

```
[you] $ graphene node show leaf-a
leaf-a (revision 2): leaf a
  goal:   leaf a
  scope:  a.py, tests/test_a.py   (a write anywhere else is refused, and blocks `done`)
  needs:  leaf-b   (it cannot start until they are done)
  done:   `python3 -m pytest tests/test_b.py -q` passes
  finish: graphene node done leaf-a   (runs the check and asks git what changed)
  stuck:  graphene node release leaf-a --why '<what is in the way>' [--wants <paths it needs>]   (hands it back; say why)
leaf-a  leaf a
  state: open · owner agent
  nobody has held this node yet, so no window and nothing changed under it
  coverage: not computed — nobody has held this node, so there is no window for git to answer for
  refused: nothing
  what people did to it:
    2026-10-09T06:10:23.872Z  edited  alex (no terminal)  check: 'true' -> 'python3 -m pytest tests/test_b.py -q'; needs: [] -> ['leaf-b'] (revision 2)
  every entry, check runs included: `graphene plan log` (2 for leaf-a)
```

After (add28dc):

```
[you] $ graphene node set leaf-a --check 'python3 -m pytest tests/test_b.py -q'
leaf-a is now revision 3:
  check: true → python3 -m pytest tests/test_b.py -q
  needs: none → leaf-b
leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-a: edited needs by graphene
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-node-set
▼ ○ no goal yet                                                        0/2 done
├   ◌ leaf a                                                  ~leaf-a  waiting
└   ○ leaf b                                                   leaf-b  ready
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/2 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ◌ leaf a                                                      leaf-a  waiting
 ○ leaf b                                                      leaf-b  ready

 waiting  leaf-a on leaf-b (ready)








 1 changed since you last looked · graphene plan changes · m seen · 0 on you
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

```
[you] $ graphene node show leaf-a
leaf-a (revision 3): leaf a
  goal:   leaf a
  scope:  a.py, tests/test_a.py   (a write anywhere else is refused, and blocks `done`)
  needs:  leaf-b   (it cannot start until they are done)
  done:   `python3 -m pytest tests/test_b.py -q` passes
  finish: graphene node done leaf-a   (runs the check and asks git what changed)
  stuck:  graphene node release leaf-a --why '<what is in the way>' [--wants <paths it needs>]   (hands it back; say why)
leaf-a  leaf a
  state: open · owner agent
  nobody has held this node yet, so no window and nothing changed under it
  coverage: not computed — nobody has held this node, so there is no window for git to answer for
  refused: nothing
  what people did to it:
    2026-10-09T06:27:46.243Z  edited  alex (no terminal)  check: 'true' -> 'python3 -m pytest tests/test_b.py -q' (revision 2)
    2026-10-09T06:27:46.243Z  edited  graphene            needs: [] -> ['leaf-b'] (revision 3)
  every entry, check runs included: `graphene plan log` (3 for leaf-a)
```

### `graphene plan edit`: the same change, saved in the editor

The same two leaves and `graphene plan seen`. $EDITOR is a script that turns leaf-a's `check: true` into
the new check.

Before (7fe75af):

```
[you] $ graphene plan edit
leaf-a: check changed; leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-plan-edit
▼ ○ no goal yet                                                        0/2 done
├   ◌ leaf a                                                   leaf-a  waiting
└   ○ leaf b                                                   leaf-b  ready
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/2 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ◌ leaf a                                                      leaf-a  waiting
 ○ leaf b                                                      leaf-b  ready

 waiting  leaf-a on leaf-b (ready)








 0 on you · agents 0 · you 3 acts ~1m · R: 1 ready · 0/2 done
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

After (add28dc):

```
[you] $ graphene plan edit
leaf-a: check changed; leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-a: edited needs by graphene
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-plan-edit
▼ ○ no goal yet                                                        0/2 done
├   ◌ leaf a                                                  ~leaf-a  waiting
└   ○ leaf b                                                   leaf-b  ready
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/2 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ◌ leaf a                                                      leaf-a  waiting
 ○ leaf b                                                      leaf-b  ready

 waiting  leaf-a on leaf-b (ready)








 1 changed since you last looked · graphene plan changes · m seen · 0 on you
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

### `graphene node set --add-scope`: leaf-b takes in the file leaf-a's check runs

The need lands on leaf-a, a leaf the command did not name.

```
[you] $ graphene node add 'leaf a' --id leaf-a --scope a.py --scope tests/test_a.py --check 'python3 -m pytest tests/test_shared.py -q'
○ leaf a  leaf-a  ready
```

```
[you] $ graphene node add 'leaf b' --id leaf-b --scope b.py --scope tests/test_b.py --check true
○ leaf b  leaf-b  ready
```

```
[you] $ graphene plan seen
0 changes marked as seen; what anyone else changes next is marked
```

Before (7fe75af):

```
[you] $ graphene node set leaf-b --add-scope tests/test_shared.py
leaf-b is now revision 2:
  scope: b.py, tests/test_b.py → b.py, tests/test_b.py, tests/test_shared.py
leaf-a waits on leaf-b: its check runs tests/test_shared.py, which leaf-b writes
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-add-scope
▼ ○ no goal yet                                                        0/2 done
├   ◌ leaf a                                                   leaf-a  waiting
└   ○ leaf b                                                   leaf-b  ready
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/2 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ◌ leaf a                                                      leaf-a  waiting
 ○ leaf b                                                      leaf-b  ready

 waiting  leaf-a on leaf-b (ready)








 0 on you · agents 0 · you 3 acts ~1m · R: 1 ready · 0/2 done
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

After (add28dc):

```
[you] $ graphene node set leaf-b --add-scope tests/test_shared.py
leaf-b is now revision 2:
  scope: b.py, tests/test_b.py → b.py, tests/test_b.py, tests/test_shared.py
leaf-a waits on leaf-b: its check runs tests/test_shared.py, which leaf-b writes
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-a: edited needs by graphene
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-add-scope
▼ ○ no goal yet                                                        0/2 done
├   ◌ leaf a                                                  ~leaf-a  waiting
└   ○ leaf b                                                   leaf-b  ready
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/2 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ◌ leaf a                                                      leaf-a  waiting
 ○ leaf b                                                      leaf-b  ready

 waiting  leaf-a on leaf-b (ready)








 1 changed since you last looked · graphene plan changes · m seen · 0 on you
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

### `graphene node add`: a new leaf whose check runs leaf-b's file

The same two leaves and `graphene plan seen`. The review found this one: the need went into your `added`
row. A new line in `plan edit` was already judged after it, as Graphene's edit. Now `node add` is too, so
the new leaf is revision 2.

Before (7fe75af):

```
[you] $ graphene node add 'leaf c' --id leaf-c --scope c.py --check 'python3 -m pytest tests/test_b.py -q'
◌ leaf c  leaf-c  waiting
leaf-c waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-node-add
▼ ○ no goal yet                                                        0/3 done
├   ○ leaf a                                                   leaf-a  ready
├   ○ leaf b                                                   leaf-b  ready
└   ◌ leaf c                                                   leaf-c  waiting
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/3 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ○ leaf a                                                      leaf-a  ready
 ○ leaf b                                                      leaf-b  ready
 ◌ leaf c                                                      leaf-c  waiting

 waiting  leaf-c on leaf-b (ready)






 0 on you · agents 0 · you 3 acts ~1m · R: 2 ready · 0/3 done
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

After (add28dc):

```
[you] $ graphene node add 'leaf c' --id leaf-c --scope c.py --check 'python3 -m pytest tests/test_b.py -q'
◌ leaf c  leaf-c  waiting
leaf-c waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-c: edited needs by graphene
```

```
[you] $ graphene watch   (80 columns, headless)
 the plan of <tmp>/c-node-add
▼ ○ no goal yet                                                        0/3 done
├   ○ leaf a                                                   leaf-a  ready
├   ○ leaf b                                                   leaf-b  ready
└   ◌ leaf c                                                  ~leaf-c  waiting
────────────────────────────────────────────────────────────────────────────────
 no goal yet
 the goal · 0/3 done
 the root of the tree, in your words: :plan goal '…' says why any of this is
 done

 ○ leaf a                                                      leaf-a  ready
 ○ leaf b                                                      leaf-b  ready
 ◌ leaf c                                                      leaf-c  waiting

 waiting  leaf-c on leaf-b (ready)






 1 changed since you last looked · graphene plan changes · m seen · 0 on you
 R run all ready · E edit the plan as text · za fold all · Tab view · ? help
```

## D. Re-judge after a board answer

A board answer's `then:` line was applied unjudged (decision 171). Now a new check or scope is judged as
`node set` judges it. A check waits on the leaf that writes its file, and a second writer of a path is
refused. The command says the `waits on` line on a line of its own, after the answer's `changed:` line.
The need is Graphene's edit, so `plan changes` lists it (item C). `tests/test_board.py` pins the three
answers, and the defaults taken all at once.

In each of four fresh repos: the same two leaves, the planner's three questions, and `graphene plan seen`.

```
[you] $ graphene node add 'leaf a' --id leaf-a --scope a.py --scope tests/test_a.py --check true
○ leaf a  leaf-a  ready
```

```
[you] $ graphene node add 'leaf b' --id leaf-b --scope b.py --scope tests/test_b.py --check 'python3 -m pytest tests/test_shared.py -q'
○ leaf b  leaf-b  ready
```

```
[the planner, a Claude Code session] $ graphene plan propose - < the text below
question: what does leaf-a's check run?  [a-runs]
    default: leaf-b's test
    then: check leaf-a: python3 -m pytest tests/test_b.py -q
question: who writes tests/test_shared.py?  [a-writes]
    default: leaf-a
    then: scope leaf-a + tests/test_shared.py
question: may leaf-a write tests/test_b.py too?  [a-takes]
    default: yes
    then: scope leaf-a + tests/test_b.py
---
put up a-runs: what does leaf-a's check run?
put up a-writes: who writes tests/test_shared.py?
put up a-takes: may leaf-a write tests/test_b.py too?
```

### `graphene board take a-runs`: leaf-a's check runs leaf-b's file

Before (7fe75af):

```
[you] $ graphene board take a-runs
taken a-runs
  changed: leaf-a: check is now python3 -m pytest tests/test_b.py -q
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

The plan then:

```
leaf-a: needs none; scope a.py, tests/test_a.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

After (add28dc):

```
[you] $ graphene board take a-runs
taken a-runs
  changed: leaf-a: check is now python3 -m pytest tests/test_b.py -q
leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-a: edited needs by graphene
```

The plan then:

```
leaf-a: needs leaf-b; scope a.py, tests/test_a.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

### `graphene board take a-writes`: leaf-a takes in the file leaf-b's check runs

Before (7fe75af):

```
[you] $ graphene board take a-writes
taken a-writes
  changed: leaf-a: scope + tests/test_shared.py
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

The plan then:

```
leaf-a: needs none; scope a.py, tests/test_a.py, tests/test_shared.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

After (add28dc):

```
[you] $ graphene board take a-writes
taken a-writes
  changed: leaf-a: scope + tests/test_shared.py
leaf-b waits on leaf-a: its check runs tests/test_shared.py, which leaf-a writes
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-b: edited needs by graphene
```

The plan then:

```
leaf-a: needs none; scope a.py, tests/test_a.py, tests/test_shared.py
leaf-b: needs leaf-a; scope b.py, tests/test_b.py
```

### `graphene board take a-takes`: leaf-a takes in a path leaf-b writes

Before (7fe75af):

```
[you] $ graphene board take a-takes
taken a-takes
  changed: leaf-a: scope + tests/test_b.py
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

The plan then:

```
leaf-a: needs none; scope a.py, tests/test_a.py, tests/test_b.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

After (add28dc):

```
[you] $ graphene board take a-takes
leaf-a and leaf-b both write tests/test_b.py. A path has one leaf that writes it: give it to one, and let the other wait on it
[exit 1]
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

The plan then:

```
leaf-a: needs none; scope a.py, tests/test_a.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

### `graphene board take`: every default at once

`graphene plan accept` and `graphene run` take the defaults the same way, and say the same lines.
Before, all three were taken unjudged, and leaf-a and leaf-b both wrote tests/test_b.py. After,
a-writes is taken and leaf-b does not wait on leaf-a. leaf-a waits on leaf-b already, so leaf-b's
check runs tests/test_shared.py as the base commit has it. That is item B's case.

Before (7fe75af):

```
[you] $ graphene board take
took the defaults of a-runs, a-writes, a-takes, left open on the board (`graphene plan undo` takes them back)
```

```
[you] $ graphene plan changes
nothing changed since you last looked
```

The plan then:

```
leaf-a: needs none; scope a.py, tests/test_a.py, tests/test_shared.py, tests/test_b.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

After (add28dc):

```
[you] $ graphene board take
took the defaults of a-runs, a-writes, left open on the board (`graphene plan undo` takes them back)
leaf-a waits on leaf-b: its check runs tests/test_b.py, which leaf-b writes
left for you: a-takes (its default is refused: leaf-a and leaf-b both write tests/test_b.py. A path has one leaf that writes it: give it to one, and let the other wait on it)
```

```
[you] $ graphene plan changes
1 changed since you last looked (graphene plan seen marks them seen):
  06:27  leaf-a: edited needs by graphene
```

The plan then:

```
leaf-a: needs leaf-b; scope a.py, tests/test_a.py, tests/test_shared.py
leaf-b: needs none; scope b.py, tests/test_b.py
```

## What the review found

Two reviewers read the branch at 5ed2739. Each fix to the code has a test that fails without it.

- The waits line was kept in the answer's `changed:` line. A re-ask read that line as the check, and told
  you and the planner a check that cannot pass. Now the line is the effect alone. `tests/test_reask.py`.
- A need Graphene added to a leaf that came back cleared it. The leaf read waiting and lost its offers, and
  the next run would start it on the fault it handed back. Now Graphene's rows are passed over.
  `tests/test_plan.py`.
- Taking every default said neither a default's need nor a refused default. Now both are said (D, above).
  `tests/test_board.py`.
- `node add` put Graphene's need in your row (C, above). `tests/test_talk.py`.
- The board rows' fixture widened ids onto schema.py, which the schema leaf writes. That pick is refused
  now, and four tests failed. Its option adds uuid.py instead. `tests/test_board_rows.py`.
- The time column at an 80-column terminal is 43 cells, not 45 (A, above).
