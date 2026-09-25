# The screen, before and after

Each screen of `graphene watch` this run changed, in an isolated WezTerm mux at 80×24 and at 120×36,
on the same saved repository of the real feeds run: before (`2c86399`) and after (this branch).
The SVGs keep the colours; the `.txt` beside each is the same screen as text. How they were taken:
[harness/README.md](harness/README.md).

## The tree as proposed, cursor on a sub-goal

One row grammar (glyph, title cut at a word, id, state word, in fixed columns); the goal is the first row instead of a cut-off top bar; the sub-goal's pane lists its children and what waits, where it was a title, two blank lines and `0/1 done`; the status line says what waits on you instead of `planner: claude:59409a10`.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p01-proposed-subgoal-80x24.svg) | ![](after/p01-proposed-subgoal-80x24.svg) |

before, 120×36

![](before/p01-proposed-subgoal-120x36.svg)

after, 120×36

![](after/p01-proposed-subgoal-120x36.svg)

## A proposed leaf

Aligned keys, wrapped at words; who proposed it is said once, in words (it was said twice, as `claude:59409a10`); no `revision 1`.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p02-proposed-leaf-80x24.svg) | ![](after/p02-proposed-leaf-80x24.svg) |

before, 120×36

![](before/p02-proposed-leaf-120x36.svg)

after, 120×36

![](after/p02-proposed-leaf-120x36.svg)

## Enter on a proposed leaf: the record

A laid-out pane, where `node show`'s text was pasted and wrapped mid-word; a node nothing has happened to says so in a line.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p03-record-leaf-80x24.svg) | ![](after/p03-record-leaf-80x24.svg) |

before, 120×36

![](before/p03-record-leaf-120x36.svg)

after, 120×36

![](after/p03-record-leaf-120x36.svg)

## The help

Grouped as the README groups the keys, two columns at 120 and one at 80, instead of a wall wrapped mid-phrase.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p04-help-80x24.svg) | ![](after/p04-help-80x24.svg) |

before, 120×36

![](before/p04-help-120x36.svg)

after, 120×36

![](after/p04-help-120x36.svg)

## A sub-goal, open, with a leaf of yours under it

Its children as rows with their states, and one line of what waits (`n6 is yours`), where it said `1/3 done`.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p05-subgoal-open-80x24.svg) | ![](after/p05-subgoal-open-80x24.svg) |

before, 120×36

![](before/p05-subgoal-open-120x36.svg)

after, 120×36

![](after/p05-subgoal-open-120x36.svg)

## A ready leaf

Why (the path from the goal, short), goal, scope, check, needs with each need's state.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p06-ready-leaf-80x24.svg) | ![](after/p06-ready-leaf-80x24.svg) |

before, 120×36

![](before/p06-ready-leaf-120x36.svg)

after, 120×36

![](after/p06-ready-leaf-120x36.svg)

## A leaf that is yours (added with `a`, `owner: me`)

It reads `yours` (magenta, it waits on you) and `y` marks it done; it read as a sub-goal with `(none: a sub-goal whose leaves are still to come; s asks the planner)`, and could never be finished.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p07-yours-80x24.svg) | ![](after/p07-yours-80x24.svg) |

before, 120×36

![](before/p07-yours-120x36.svg)

after, 120×36

![](after/p07-yours-120x36.svg)

## A running leaf

Executor in words (`claude, started by graphene run`), worktree, the last thing it did and how long ago, said once; it said `running` twice and `run:claude`.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p08-running-80x24.svg) | ![](after/p08-running-80x24.svg) |

before, 120×36

![](before/p08-running-120x36.svg)

after, 120×36

![](after/p08-running-120x36.svg)

## `l` on a running leaf

While `claude -p` has printed nothing, the tool calls its hooks recorded, newest last; it said `(nothing yet)`.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p09-tail-80x24.svg) | ![](after/p09-tail-80x24.svg) |

before, 120×36

![](before/p09-tail-120x36.svg)

after, 120×36

![](after/p09-tail-120x36.svg)

## A leaf that came back

Why, then the offers as rows of one shape, each with its command (under it where the pane is narrow); `↩` is magenta, not the only red thing on the screen.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p10-came-back-80x24.svg) | ![](after/p10-came-back-80x24.svg) |

before, 120×36

![](before/p10-came-back-120x36.svg)

after, 120×36

![](after/p10-came-back-120x36.svg)

## Enter on the leaf that came back

The record laid out: contract, why it came back and its offers, each hold, the check, what was refused.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p11-came-back-record-80x24.svg) | ![](after/p11-came-back-record-80x24.svg) |

before, 120×36

![](before/p11-came-back-record-120x36.svg)

after, 120×36

![](after/p11-came-back-record-120x36.svg)

## A leaf waiting for your sign-off

`y sign off` on the bottom line; the pane says it once.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p12-review-80x24.svg) | ![](after/p12-review-80x24.svg) |

before, 120×36

![](before/p12-review-120x36.svg)

after, 120×36

![](after/p12-review-120x36.svg)

## A done leaf

When it was done and what changed.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p13-done-leaf-80x24.svg) | ![](after/p13-done-leaf-80x24.svg) |

before, 120×36

![](before/p13-done-leaf-120x36.svg)

after, 120×36

![](after/p13-done-leaf-120x36.svg)

## Enter on a done leaf

Its hold (who, when, where, what changed in scope), the check Graphene ran, coverage.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p14-done-record-80x24.svg) | ![](after/p14-done-record-80x24.svg) |

before, 120×36

![](before/p14-done-record-120x36.svg)

after, 120×36

![](after/p14-done-record-120x36.svg)

## `:plan log`

The output wrapped with a hanging indent, values in words (`scope: a, b → a`), and the bottom line says where it is; it was Python reprs wrapped mid-word.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p15-command-said-80x24.svg) | ![](after/p15-command-said-80x24.svg) |

before, 120×36

![](before/p15-command-said-120x36.svg)

after, 120×36

![](after/p15-command-said-120x36.svg)

## `V` and two `j`

The bottom line says VISUAL and what y and d do (the selection is reversed on screen; see the SVG).

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p16-visual-80x24.svg) | ![](after/p16-visual-80x24.svg) |

before, 120×36

![](before/p16-visual-120x36.svg)

after, 120×36

![](after/p16-visual-120x36.svg)

## No plan yet

Two lines across the screen; it was the whole help wrapped into the pane.

| before, 80×24 | after, 80×24 |
| --- | --- |
| ![](before/p00-empty-80x24.svg) | ![](after/p00-empty-80x24.svg) |

before, 120×36

![](before/p00-empty-120x36.svg)

after, 120×36

![](after/p00-empty-120x36.svg)
