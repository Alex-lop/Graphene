# Scope for the next agent

Read this before the code. A task that is absent from this file waits.

Graphene's ambition is an open workflow tool: easy to shape and run, with a file boundary and a
check deciding what lands. The next build is smaller. It is one modest change in a repository the
person already has, reviewed so they can decide whether it worked. The reasoning is in
[PRODUCT_NEXT.md](PRODUCT_NEXT.md). The prompt that cites this file is
[prompts/workflow.md](prompts/workflow.md).

## In

One slice at a time, in the pieces that already exist.

1. **A result a person can check.** On the Home review path, connect one requested behavior to a
   check Graphene runs, or to an artifact the person can open. Show an expectation the check does
   not cover as uncovered.
2. **A first task with less to operate.** For one project type current users already bring,
   propose the check, show whether it passes before editing, and ask one specific question when
   it cannot be inferred. Keep the proposed command visible, under the permission rules that
   already exist.
3. **A safe return.** On Home, say what finished, what is still off their branch, what needs a
   decision, and what happens next. Say what isolation actually guarantees. Prefer a worktree when
   a person and an agent share the work.

Do slice 1 before slice 2. Do slice 3 when a run can already be left and reopened. Stop when the
slice in the prompt is done.

## Out

Leave these alone until a person asks for them in a new scope:

- A general workflow builder, a no-code app builder, and new providers.
- New commands, new graph controls, and new words (`each:`, `until:`, `kind:`).
- A second plan. One plan a repository stays.
- Releases, tags, pushes to `main`, and new dependencies.
- Rewriting [DIRECTION.md](DIRECTION.md). It is the decision log. Read it when a change would go
  against a decision, and say so. Do not delete history to make the log shorter.
- A subagent pointed at the repository with no file list.
- More autonomous retries, until it is clear why a person rejects a result.

## Files

The prompt for a change names the files it may touch. A change with no file list does not start.
If the slice needs a file the prompt left out, stop and name that file. Do not go and edit it.

## Done

A person can say what changed and what is still uncertain without reading the agent transcript.
A check that was already green is reported as already green. Tests that cover the edited files
pass, `uv run ruff check` is clean, and the pull request says which slice this was.

## How to brief the next agent

Give it this file, [PRODUCT_NEXT.md](PRODUCT_NEXT.md), and the files for the one slice. Say which
slice. Leave "look at the repo and do this" unsent.
