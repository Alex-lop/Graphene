# How the best editor agent UIs show work in progress

*Thirty minutes of research for lanes 1 and 2 of the editor night, 27 October 2026, by one Fable subagent, from
the vendors' own pages. Each claim names its source.*

Five surfaces, checked against vendor docs current to October 2026. Each: what it shows, how you steer, the one
thing to learn (and the screen or API), one thing to avoid.

## VS Code Agent Sessions view

**Shows.** One list of local, background (worktree) and cloud sessions. Each row: name, last-active time, and a
count of file changes you have not reviewed, which "clears once you accept or undo them"
([learn page, 10/21/2026](https://code.visualstudio.com/learn/foundations/agent-sessions-and-where-agents-run)).
Filters: Active, Archived/Done, External
([manage sessions](https://code.visualstudio.com/docs/agents/run/sessions/manage-sessions)).
**Steer.** Pin, Archive, Delete (removes the worktree), Resume in Terminal; a Session Target dropdown (Local/Cloud)
and `/delegate` ([cloud agents](https://code.visualstudio.com/docs/agents/agent-types/cloud-agents)).
**Learn.** The row encodes "needs you": `ChatSessionStatus` is exactly `InProgress | NeedsInput | Completed |
Failed`, and `ChatSessionItem` carries `badge`, `timing`, and `changes: ChatSessionChangedFile[]` (uri,
insertions, deletions)
([vscode.proposed.chatSessionsProvider.d.ts](https://github.com/microsoft/vscode/blob/main/src/vscode-dts/vscode.proposed.chatSessionsProvider.d.ts)).
Four states, one count.
**Avoid.** Building on it. It is a proposed API; Marketplace extensions cannot ship it
([using proposed API](https://code.visualstudio.com/api/advanced-topics/using-proposed-api)). Use a TreeView with
`ViewBadge` instead.

## Claude Code's VS Code panel

**Shows.** In Manual mode a side-by-side diff with the permission prompt; **Accept this change / Reject this
change** per hunk; editing the proposed text before accepting tells Claude you changed it. Plan mode opens the
plan "as a full Markdown document where you can add inline comments". An **agent map** draws subagents as a tree
with status, elapsed time, token count, and a Stop. Sessions list filters: Needs input, Working, Completed
([docs](https://code.claude.com/docs/en/vs-code)).
**Steer.** Mode switch (Auto/Manual/Plan), `/plan`, Esc ends the turn while background agents keep running,
rewind via checkpoints (same page).
**Learn.** The plan is a real text document in the editor, commented with the Comments API; the diff is the real
diff editor. Both surfaces the person already knows.
**Avoid.** A hidden tab's only signal is "a small colored dot on the spark icon: blue means a permission request
is pending" (same page). Needs-you must be a list, not a dot.

## GitHub Copilot coding agent

**Shows.** In VS Code, the GitHub sidebar lists sessions with a running/finished icon; a session opens its PR;
**View Session** opens the log
([GitHub docs](https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/use-copilot-agents/use-cloud-agent-in-your-ide),
[changelog](https://github.blog/changelog/2025-07-14-start-and-track-github-copilot-coding-agent-sessions-from-visual-studio-code/)).
On github.com/copilot/agents the log shows reasoning and tools; the overview tracks progress, tokens, session
length ([manage agents](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/manage-agents)).
**Steer.** Type below the session log; applied "after its current tool call finishes". **Stop session** ends the
run but keeps pushed commits (same page).
**Learn.** The unit of work is a PR, and every commit message links to its session log. Steering lands at a
tool-call boundary; stopping never loses pushed work.
**Avoid.** No cancel from VS Code (only JetBrains/Eclipse have Cancel Job), and no diff until the PR exists; while
running you get prose, not code.

## Cline

**Shows.** A **Checkpoint** marker after each tool use with **Compare** (opens the editor's diff viewer) and
**Restore** ([checkpoints](https://docs.cline.bot/core-workflows/checkpoints)). Plan mode reads only; Act edits and
runs ([plan and act](https://docs.cline.bot/core-workflows/plan-and-act)).
**Steer.** Restore Files / Restore Task Only / Restore Files & Task. Auto-approve per action class; OS notification
"when approval is required" and when an approved command runs over 30 s
([auto-approve](https://docs.cline.bot/features/auto-approve)).
**Learn.** Rollback is split in two: code and conversation, each restorable alone.
**Avoid.** A separate progress layer. Cline deprecated Focus Chain because it "was no longer providing enough
additional benefit on top of the current harness" ([deprecations](https://docs.cline.bot/resources/deprecations)).
Derive progress from the tree; do not keep a todo list beside it.

## GitLens commit graph

**Shows.** A **Working Changes** row per worktree with changed-file count, branch pill, worktree marker, and
conflict count; an overview bar with a pill per dirty worktree; live agent state (working, idle, needs input) on
the branch via hooks ([parallel workflow, Sept 2026](https://help.gitkraken.com/gitlens/gl-parallel-dev-workflow/)).
An **Agent Kanban** groups sessions by Working, Idle, Inactive, Needs Input, with permission approval on the card
([CHANGELOG](https://github.com/gitkraken/vscode-gitlens/blob/main/CHANGELOG.md)).
**Steer.** Double-click a row to **Scope to Worktree**; **Resume Agent Session** on a WIP row; Archive (same
sources).
**Learn.** Width rule: "when space is tight the label compacts to WIP before the branch name truncates"
(CHANGELOG 19.1.0). Scoping keeps scroll, selection and filters.
**Avoid.** State that depends on an install step; without hooks the Agents panel is empty (CHANGELOG 19.2.0).

## Five moves

1. Lane 1: one row per fork, GitLens-style: branch pill, file count, state; compact the label before truncating
   the name.
2. Lane 1: draw the race as Claude's agent map does: forks under their task, each with state, elapsed time, a
   Stop, and the winner marked.
3. Lane 2: Needs You is a TreeView with exactly four states (InProgress, NeedsInput, Completed, Failed) and a
   `ViewBadge` count that clears when the person acts.
4. Lane 2: open a fork's worktree against its base with `vscode.changes` and a file with `vscode.diff`
   ([commands](https://code.visualstudio.com/api/references/commands)); editing there before accepting feeds back
   to the agent.
5. Lane 2: the plan is a Markdown document in the editor; inline comments via `comments.createCommentController`
   go to `graphene plan propose -`.
