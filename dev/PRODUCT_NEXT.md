# Where I would take Graphene next

Alex — these are product hypotheses from working on this repository and testing its behavior.
They are not findings from watching customers use it.

The missing value is confidence at the end. Graphene can already divide work, isolate agents,
hold file boundaries, run checks, and present changes for approval. A person can still reach a
green task and wonder: did it do what I asked, what do I need to inspect, and can I carry on?
Someone who rarely codes feels that uncertainty more strongly.

## The ambition those slices serve

Graphene should be the open-source way to automate a workflow. A person should be able to shape
it and run it with about as little ceremony as a tool like n8n, and the result should mean
something: a file boundary and a check decide what lands.

Easy means they state a goal, correct the few choices that change the result, and start. They
get one small change finished without inventing a test command, a task id, or a file list.
Meaningful means the review shows what was checked, what happened, and what still needs a person.
Open source means it runs on the computer they already have, with the agents they already use.
Adding a provider is later work.

That is the product to aim at: workflow automation that is easy to run, checked rather than
asserted, and usable without an account. The three slices below are how the first workflow earns
that. A slice is worth building when it makes a workflow easier to run, or the result easier to
trust.

## 1. Make the result something a person can verify

Start with one complete experience in the existing Home review flow.

Suppose someone asks, “Add CSV export to this table.” Before running, Graphene should propose a
few concrete expectations: export the visible rows, keep the column names, and handle an empty
table. The person can correct those expectations without choosing file paths or writing a test
command. Only unresolved choices that affect the result should interrupt them.

At review, return to those same expectations. Show what was checked, what happened, and what still
needs a person. For this example, that could mean an actual exported file to inspect, the relevant
automated test result, and a way to try the export in the app. A developer can expand the diff and
logs. An occasional coder can start with the behavior.

Graphene already has checks, whole-goal validation, diffs, and approval. The work is connecting
that evidence to the original request. Another model saying “looks good” is insufficient evidence.
A screenshot supports an appearance claim. It does not establish that an export contains the right
data. A check that was already green before the work deserves less confidence than one that
catches the missing behavior.

**First slice:** one supported project type, one requested behavior, and a review card that
connects the request to an executable check or an artifact. Display unsupported or unverified
expectations honestly. Leave a general proof system for later.

**Success:** a person can explain what changed and what remains uncertain without reading the
agent transcript. Also hand them an incomplete result on purpose, and see whether the review
helps them catch it.

## 2. Make the first real task require less orchestration knowledge

Home already provides setup, planning, Start, and review. Improve that path before adding another
entry point.

For an existing repository, propose the likely way to run its checks, show whether those checks
pass before editing, and suggest a small first change. Keep the proposed commands visible and
subject to the existing permission rules. When setup cannot be inferred, ask one specific question
with useful choices. Leave the person out of inventing a test command or diagnosing a toolchain
from a terminal traceback.

Keep the graph available for shaping complicated work. For a small request, let someone stay with
the goal, the few decisions that need them, and the result. They should be able to get value
without managing task ids, file ownership, or several attempts.

Initially target developers and occasional coders who already have a working repository. A promise
to take anyone from an empty folder to a deployed app would mix in too many unrelated failures to
learn what Graphene itself contributes.

**First slice:** support the setup and first-change path for the project type the first users
actually bring. If their baseline is broken, say so before spending on implementation.

**Success:** a new user completes a useful change in their own project without a walkthrough of
how to operate Graphene. Record every point where they ask for help.

## 3. Make leaving and coming back feel safe

The value of orchestration includes being able to look away. On returning, a person needs a short
account of what finished, what remains separate from their branch, what needs a decision, and what
happens next.

Build this into the existing Home screen. Use the stored run state and evidence, with links to
details. When work stops, explain the immediate reason and offer the existing relevant action.
Preserve useful completed work so the user can continue from the run, rather than reconstructing
it from logs.

Verification on this repository found why this matters: hooks can be unloaded or fail, and edits
in a shared checkout cannot reliably be attributed to a human or an agent. Present protection and
isolation accurately. Prefer isolated worktrees when people and agents work together. A green
status means the checks that ran passed. It does not promise anything those checks did not cover.

**First slice:** test returning after a window reload, an interrupted run, and a conflicting human
edit. Ask users what they believe has landed and whether their own work is safe. Compare their
answers with the actual repository state.

## What I would do before expanding the product

Watch five people complete a small task in their own repositories: a mix of regular developers and
people who code occasionally. Give them the current extension and let them encounter the awkward
parts. Compare equivalent tasks with their usual coding agent, and balance the order so familiarity
with the task does not decide the result.

Measure human attention, help requests, review mistakes, successful changes, and model spend. Task
completion time alone misses the point if Graphene makes someone supervise more. Five sessions
will expose problems. They will not establish a reliable performance claim.

Then build priority 1 for the most common task, and repeat. The working preference is one attempt
for straightforward work, and more attempts when the user wants alternatives or when there is
evidence they improve outcomes. Multiple agents should earn their added cost and review burden.

## What I would defer

More commands, more graph controls, more provider integrations, and a general no-code app builder.
Also more autonomous retries, until it is clear why real users reject results. Each may become
worthwhile. The trustworthy first finished change answers the central product question more
directly.

If I had to choose one next deliverable, it would be this: a person asks for a modest change in
their own project, Graphene does it, and the review makes it easy to decide whether it actually
worked. Build that experience with the pieces already here, then let observed use decide what
comes next.
