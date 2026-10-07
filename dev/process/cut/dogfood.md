# Dogfood: lane 2 as a paragraph

The wheel from `4e5a2a9`, installed as a tool in its own directory. A fresh clone of `cut`.
`graphene init --planner claude --executor claude`, then `graphene ask` with lane 2's text
(631 words) as the paragraph. Started 00:04, finished 00:26: 21 min 59 s.

The first answer could not be read ("line 4: option: is a question's; a risk has a default").
Graphene asked again, and the second answer was read.

## The tree it proposed

```
the direction: the plan hangs from none of its nodes yet (`graphene direction plan NODE`)
Cut Graphene down to what a person uses to set up, ask, prune, run, read the record and watch, by…
 ┌─────────────────┬─────────────────────┴─┬─────────────────┬───────────────────┐
 ? ui              ? nemotron              ? surface         ? process           ? docs
 │ The web UI is…  │ Nemotron is an…       │ The visible…    │ dev/process…     │ The README…
 └ ? ui-delete     ├ ? nemo-move ←1        ├ ? hide ←1       ├ ? process-branch  ├ ? changelog ←2
     Delete the…   │   Move the Nemotron…  │   Hide every…   │   Move…           │   Fold the…
                   └ ? hackathon-sends ←1  └ ? the-rest ←1   └ ? counts ←2       └ ? readme ←3
                       HACKATHON.md says…      HOW_IT_WORK…      Record the…         README…
5 sub-goals · 9 leaves · 14 proposed
```

What the planner said before the tree:

```
the planner says:
  Some leaves write the same files, which breaks the rule that two leaves never share a path. I couldn't find a split that avoids it:
  - ui-delete and nemo-move both write `cli.py`, `plan.py` and `tests/test_review_fixes_executor.py`.
  - nemo-move and hide both write `plan_cli.py` and `board_cli.py`.
  Each of these leaves has to change those files, and the directive wants the UI deleted in a commit of its own. So `needs:` runs the three one after another, and they never run at the same time. Folding hide into nemo-move would remove two of the shared files, but it makes one very large leaf.
  Left out of the tree:
  - `dev/process/cut/dogfood.md` and a note of the moment plan-first stopped helping. Only whoever ran this ask can write those.
  - Lane 1's README facts.
```

## The board it put up

```
the board: 3 open
questions
  ◇ Once `graphene ui` and its server go, nothing calls `refresh_commits`. Nothing     commits  open
    then fills the store's commits, and `node show` stops crediting commits to
    agents, while the suite stays green because its tests call `sync_commits`
    themselves. Should `node show` fill them itself?
      default: yes: node_record syncs the commits of the node's own sessions before it grades them,
               with a test in a repo where `ui` never ran
      1: no: leave it, and say in 0.5.0 that `node show` no longer credits commits to an agent
      about ui-delete
  ◇ `graphene key set` is how a key gets into the keychain. If `graphene key`          key-set  open
    registers only once a key is found, NEBIUS_API_KEY is the only way to set a first
    key. Should `graphene key` wait for a key like the other four?
      default: no: `graphene key` registers whenever the subpackage loads. `plan cover`, `plan
               note`, `plan precheck`, `board lookup` and init's Nemotron choice also need a key
      1: yes: all five register only when a key is found, as the lane says
      about nemo-move
  ◇ A `--depth 1` clone may stay over 3 MB, because the source, the tests,             clone    open
    dev/test's run logs and the recordings all stay on main and nobody has measured
    them without dev/process. Is 3 MB a gate or a number to report?
      default: report it: require fewer than 300 tracked files, and report the clone's size with the
               five largest tracked files beside it when it is over 3 MB. Nothing leaves main that
               the lane does not name
      1: a gate: counts comes back above 3 MB, and you name what else leaves main
      about counts
graphene board take|drop|park|unpark ID · pick ID N · answer ID TEXT · note TEXT
left open, an item takes its default when you accept the plan
```

Graphene also printed five warnings. Each says a leaf's check names a path that is not in the repo.
All five are false: the "paths" are pieces of `sed` and `grep` patterns, such as `Privacy/p` and
`A-Za-z0-9_/`.

## The tree I would have written

```
goal: Cut the surface: delete the web UI, hide all but the budget, move the archive, Nemotron as an extra
- the web UI is gone  [ui]            one commit; tag its parent last-with-ui
- the archive is off main  [process]  orphan branch `process`; one line in DIRECTION
- Nemotron is an extra  [nemotron]    eleven modules behind one shim; a boundary test; README Privacy
- the surface fits the budget  [hide] after the three above: hide, a budget test, "The rest"
- the README says what changed  [readme]  needs ui, nemotron, hide
```

## The differences

- It ran the leaves one after another, because they share `cli.py`, `plan_cli.py` and
  `board_cli.py`. I ran ui, process and nemotron at once in three worktrees and took the merge
  conflicts. Its order obeys Graphene's own rule. Mine is faster on a clock.
- It caught something I missed. Once `graphene ui` goes, nothing calls `refresh_commits`. Then
  `node show` stops crediting commits to agents, and the suite stays green. The merge of the UI
  deletion moves that call to where the record is read.
- Its other two questions matched mine. `graphene key` must register without a key, or a first key
  can only come from the environment. The 3 MB clone target is reported, not gated.
- It left out the dogfood note and lane 1's README facts. That was right: only the asker can write
  the first, and the second is another lane.

## The moment plan-first stopped helping

At 00:15, eleven minutes in. The planner had not answered, and the lanes it would plan were already
specified in the directive. I started the five worktrees then, without its tree. Its tree arrived
eleven minutes later and changed one thing: the `refresh_commits` call. That one thing was worth
the wait. The wait itself was not: a tree that takes 22 minutes to arrive is read after the work
has started, not before.

My own session was not held to plan-first tonight. Its hooks come from Alex's checkout, and every
write went to a worktree with no plan in force. So this is evidence about the planner's latency,
not about the gate.
