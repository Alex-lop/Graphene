| group | cockpit key | what it does | the editor offers | covered |
|---|---|---|---|---|
| answer | `⏎ y` | the row's own move: the default, accept, sign off, try again | graphene.accept (a proposal; no sign-off, no try again) | part |
| answer | `1-9 a` | pick that option, or a fork; answer in your own words | — | no |
| answer | `d A` | drop a proposal or a question; accept every proposal | graphene.dropStep, graphene.acceptAll | yes |
| agents | `t` | tell its agent a line, heard with its next write or command | graphene.tell | yes |
| agents | `w` | widen: give the task the path the gate stopped | — | no |
| agents | `x` | hand back a running task; reopen a finished one (say why) | — | no |
| agents | `b n r` | came back: a new task, wait on another, reopen the one named | — | no |
| agents | `r R s` | run this task, or every ready one; s: the planner splits one | graphene.runReady (every ready one; not this one, no split) | part |
| agents | `f` | fork: N agents at once, the check keeps one | — | no |
| plan | `e E` | edit the task, or the whole plan, in your $EDITOR | graphene.editStep (four boxes; not the whole plan) | part |
| plan | `P u D` | plan first: on, auto, off; undo; D: the plan's direction | — | no |
| plan | `+ L` | graph: + adds a step after; L on A, then on B: B waits on A | graphene.addStep, graphene.link (the graph's dot, dragged) | yes |
| screens | `j k` | move; ← → the task on the map, the box on the graph | the Plan tree, the graph's boxes (click) | yes |
| screens | `i` | details: the task's contract, output, changes and record | the graph's details pane (contract; no output, no diff) | part |
| screens | `c g m` | the cockpit, the graph, the map; Tab goes on, Esc comes back | graphene.openCockpit (a terminal), graphene.showGraph; no map | part |
| screens | `v p` | on the map: v changes the lens, p paints a folder to a task | — | no |
| anything | ``:` q` | any graphene command (:stop stops runs, :ask asks); q quits | graphene.auto, graphene.envelope, graphene.stop, graphene.init, each its own command | part |

cockpit moves: 17. The editor covers 4 whole and 6 in part; 7 not at all.
extension commands (15): accept, acceptAll, addStep, auto, dropStep, editStep, envelope, init, link, openCockpit, refresh, runReady, showGraph, stop, tell
