# Workflows

Alex, 12 November 2026. This is the direction for workflows. The job an agent may take is
[SCOPE.md](SCOPE.md). The prompt is [prompts/workflow.md](prompts/workflow.md). The product note
is [PRODUCT_NEXT.md](PRODUCT_NEXT.md).

## What you want

Graphene should feel as direct as drawing a workflow and running it: you see the graph, you change
it, you start it. The result stays meaningful because each task has files and a check, and
Graphene runs the check. It stays open source, on the machine you already use, with the agents you
already have.

The graph is that workflow. VS Code is where people meet it. The CLI follows with whatever proved
itself in the editor.

## Decisions that still hold

1. **VS Code first.** The extension is the workflow surface. The engine grows when a click needs a
   command it does not have yet.
2. **No new words.** `each:`, `until:`, and `kind:` stay parked. If one earns a place, it arrives
   as a control on a task, with the screen saying attempt, task, files, and check.
3. **You build the graph, and you can leave the building to Graphene.** For a small request the
   person stays on the goal, the few choices that change the result, and the review. The graph
   remains there for work that needs shaping.
4. **Holes are a switch.** On: the plan leaves blanks the person fills. Off: Graphene fills them
   and the person starts. Off is the default until someone asks to be in the plan.
5. **One plan a repository.** Switching which goal the graph shows is in reach. A second plan
   store is engine work, and it is outside the current scope.
6. **The hooks are a fact to prove, per agent.** Refused before the write, caught when the task
   finishes, or not held. Say which, from a test. The editor's own agent is the row that matters
   most if VS Code is home, and it is unproven.

## What an edit to the graph is for

An edit belongs in the current scope when it makes one workflow easier to run or the review
easier to trust. Attempts on a task, editing a task in place, drawing a task without calling the
planner, and one line that says what an edit does to a running task are that kind of edit, and
only when the prompt names their files.

Saved workflows, "repeat until green", and "one task a file" wait until the first slice in
[SCOPE.md](SCOPE.md) is in use.

## Left behind on purpose

The earlier brief for a graph-editing night carried a spend cap, a subagent limit, a file map, a
debrief template, and a rule to open a draft pull request and not merge. That night is over. Those
operating rules are not the direction. Use [prompts/workflow.md](prompts/workflow.md) instead of
pointing an agent at this repository and asking it to continue the night.
