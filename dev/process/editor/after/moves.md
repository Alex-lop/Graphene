| group | cockpit key | what it does | the editor offers | covered |
|---|---|---|---|---|
| answer | `⏎ y` | the row's own move: the default, accept, sign off, try again | Needs You: each item's own move (a question's default, Accept, Sign Off, a hand-back's offers) | yes |
| answer | `1-9 a` | pick that option, or a fork; answer in your own words | graphene.answer (its options, its default, your own words); graphene.pickFork from a fork's diff | yes |
| answer | `d A` | drop a proposal or a question; accept every proposal | graphene.dropStep (a came-back task too), graphene.acceptAll | yes |
| agents | `t` | tell its agent a line, heard with its next write or command | graphene.tell | yes |
| agents | `w` | widen: give the task the path the gate stopped | Needs You's widen, for a running task the gate stopped and for one that came back | yes |
| agents | `x` | hand back a running task; reopen a finished one (say why) | — | no |
| agents | `b n r` | came back: a new task, wait on another, reopen the one named | graphene.handBack (the task's own offers: a sibling, wait on, reopen) | yes |
| agents | `r R s` | run this task, or every ready one; s: the planner splits one | graphene.runReady (every ready one); a hand-back's try again; no split | part |
| agents | `f` | fork: N agents at once, the check keeps one | Set Envelope's forks, for every task; not one task | part |
| plan | `e E` | edit the task, or the whole plan, in your $EDITOR | graphene.editStep, graphene.editPlan (the plan as a text tab, refusals on their lines) | yes |
| plan | `P u D` | plan first: on, auto, off; undo; D: the plan's direction | — | no |
| plan | `+ L` | graph: + adds a step after; L on A, then on B: B waits on A | graphene.addStep (a sentence), graphene.link (the graph's dot, dragged) | yes |
| screens | `j k` | move; ← → the task on the map, the box on the graph | the Plan tree, Needs You, Agents, the graph's boxes (keys and clicks) | yes |
| screens | `i` | details: the task's contract, output, changes and record | the graph's pane (contract), graphene.openDiff (its changes); no output, no record | part |
| screens | `c g m` | the cockpit, the graph, the map; Tab goes on, Esc comes back | graphene.openCockpit (a terminal), graphene.showGraph; no map | part |
| screens | `v p` | on the map: v changes the lens, p paints a folder to a task | — | no |
| anything | ``:` q` | any graphene command (:stop stops runs, :ask asks); q quits | graphene.auto, envelope, stop, init, addStep and the rest, each its own command | part |

cockpit moves: 17. The night's editor covers 9 whole and 5 in part; 3 not at all (0.8.0's: 4, 6 and 7).

The table is the orchestrator's reading of the night's commands against the cockpit's `?` help, key by key, as
`measure/moves.py`'s table is for 0.8.0; it is a judgment, not a count a script makes.
