# How Graphene compares

Read from vendors' own pages, releases and public issues on 14 October 2026 by a model session standing in for a
researcher. Each cell says where it came from; where a page was not read, the cell says so. Graphene is in the same
table, and what it lacks is in the table too. The fuller reading, with every page, is in
[`dev/process/controller/designs.md`](../dev/process/controller/designs.md); Claude Code's Agent View and Agent
Teams were read from their docs on 18 October ([`field.md`](../dev/process/publish/readers/field.md)).

## The problem, in users' words

- "Claude modified files I didn't ask it to modify": the first option on Anthropic's own bug form for model behaviour.
- "reports ALL PASSED when tests are FAILING" ([claude-code issue 46940](https://github.com/anthropics/claude-code/issues/46940)).
- "System-level enforcement that prevents Claude from modifying any files except those explicitly authorized"
  ([claude-code issue 4452](https://github.com/anthropics/claude-code/issues/4452)).

## What each one gives of control

| | A plan before code | The files a piece may change | A check the tool runs itself | A look at the diff before the merge |
|---|---|---|---|---|
| **Graphene**, with Claude Code | a tree you edit and accept | per leaf; a write outside is refused before it happens (Claude Code, and Graphene's own loop for Nemotron and the other hosts; git catches the rest at `done`) | yes, in a clean copy | a leaf marked for sign-off, or every leaf under `review: every`, waits on its branch, and `i` then `c` in the cockpit shows its diff; in VS Code, Open Changes shows it in the diff editor, and Needs You lists what waits for you |
| Claude Code, by itself | plan mode; its docs say it is not enforced in interactive sessions where bypass is available | static allow and deny rules, not per piece | only if you write a hook | see Agent View |
| Claude Code Agent View | each session's own; it is "one screen for all your background sessions: what's running, what needs your input, and what's done" | each session's allow and deny rules | no; a row's pull request label is coloured by its checks | "`Ready for review` and `Needs input` above `Working` and `Completed`", and no diff column |
| Claude Code Agent Teams (experimental) | a shared task list; a teammate's plan can be approved "without the lead reviewing it" | by convention: "Two teammates editing the same file leads to overwrites. Break the work so each teammate owns a different set of files." | a task is done by its status ("Task status can lag"); a `TaskCompleted` hook you write can block it | not read |
| Codex | approvals and a sandbox (read-only, workspace-write) | the sandbox, not a list per piece | not documented | cloud tasks end in a diff or a pull request (third-party guides) |
| Cursor | Plan Mode, editable | hooks can allow or deny a write; no file list tied to a plan item | not documented | background agents open pull requests (third-party) |
| Kiro | specs, then a task graph run in parallel waves | not documented | not documented | not read |
| Cline | Plan and Act modes | auto-approve per category | not read | checkpoints for rollback |
| Spec Kit | spec templates and a CLI | no | no | no |
| GitHub Copilot cloud agent | not read | no per-file limit | required checks run by GitHub | a person merges: the requester cannot approve their own pull request |
| Conductor | no | no | CI checks | a diff viewer, then merge |
| Entire 0.11.5 | trails (intent across branches) | no | gates before merge, evaluated server side | trail review |
| my-pi (Pi agent) | not read | a per-task editable scope; edits outside it are blocked | deterministic validation scripts | stops for review before commit |
| Ralon | no | a kernel-enforced write lock from one static list | no | no |

## Several attempts at one task

| | Attempts at once | Who keeps one |
|---|---|---|
| **Graphene** | `forks: N` on a task, `graphene run --forks N`, or the `forks` setting: N agents, each in a copy of its own | the task's check runs on each; among the forks that pass, a rule written before any ran keeps one (`src/graphene_map/pick.py`: the one that passes the most of the others' tests, then the one that left its check's files alone, the smaller, the cheaper, the sooner) and says which step decided; on a task in review the person can pick another (`graphene node pick`; in VS Code, Compare Forks opens them side by side and Keep This Fork picks one) |
| Codex cloud | "generate multiple responses simultaneously for a single task" (OpenAI's X account, 13 June 2025, as its community forum quotes it; its docs pages read say nothing of it) | the person: "explore possible solutions and pick the best approach" |
| Cursor | "multiple agents in parallel" on one prompt (its changelog for 2.2, 10 December 2025) | Cursor: it evaluates every run once they have all finished and recommends one; "The selected agent will have a comment explaining why it was picked." The entry names no check and does not say what judges |
| VS Code 1.143 (Compare Models, preview) | "Add between two and 10 attempts", each "in its own Git worktree" (code.visualstudio.com/docs/agents/run/compare-models, read 26 October 2026) | an optional judge model "evaluates the attempts and recommends a solution", whose assessment, its page says, "isn't proof that an implementation is correct"; then the person, or Synthesize |

Read on 20 October 2026. Neither vendor's page says what its pick is held to; Graphene's rule keeps nothing whose
check failed, and the check is one you wrote.

## Unattended work: a goal, a loop, a limit

Read on 26 October 2026 by one model session from each vendor's pages (cited in
[`dev/process/revamp/landscape.md`](../dev/process/revamp/landscape.md)). A second reading checked each row
against its vendor's own page (Claude Code's `/goal`, OpenHands' goal guide, Kiro's Task Runner, GitHub's page
on the cloud agent) and corrected Kiro's, which had named a "conductor" its page does not.

| | Re-checks the goal | Plans the fix | A limit on the run |
|---|---|---|---|
| **Graphene**, `graphene auto` | yes: the goal's own check (yours, or every task's together) on the merged result | yes: the planner proposes the fix, accepted only inside your envelope, for `rounds` rounds | the envelope you set: dollars, how many tasks, fix rounds, the files no task may touch |
| Claude Code `/goal` | yes: "a model checks whether the condition holds" after each turn | the same session works on | `--max-budget-usd`, in print mode only |
| OpenHands `run_goal` | yes: "a second judge LLM" audits the transcript for evidence | it re-prompts until complete | `max_iterations` (10 by default) |
| Kiro (Crew's Task Runner) | partly: each task it plans carries acceptance criteria | it retries a step (3 times) and plans again (2 replans) | counts and time (50 tasks, a 90-minute test timeout), not dollars |
| GitHub Copilot cloud agent | on feedback and failed checks, not the goal | Agent Merge (VS Code, preview) fixes what blocks the pull request, failing checks among it | 59 minutes a session |

What Graphene adds here is not the loop, which others have, but what the loop runs inside: the tests are the
judge, every task is held to its files, and nothing outside your envelope is accepted for you.

## What this says, and does not say

For Claude Code, nothing read gives all of this together: a plan where every piece names the files it may change and
the check it must pass, a write outside those files refused as it happens, the check run by the tool in a clean copy,
and a piece landed only when it passes, on your machine with no account. That is the claim, and it is scoped: my-pi
has a per-task file scope with checks for another agent, and Ralon locks writes more strongly than a hook does, from
one static list. Claude Code's Agent View gives every session a row and its Agent Teams a shared task list; both
leave the files to convention. Graphene for VS Code's Home (what needs you, who is working) is those two rows,
held to a plan's files; nobody has used it on a real run yet. Nobody here is "the only one".

What Graphene lacks, in this table: it holds a write before it happens only for Claude Code (for Codex and any other
command, git finds it when the leaf is declared done); its hook fails open if it cannot run on a Claude Code before
2.1.295, or where `graphene init` ran from a script (from 2.1.295, `init` at a terminal makes it fail closed); a run
says its worst case before it starts, a Claude Code attempt stops at $2 and `--max-usd N` starts nothing past N
dollars (an attempt going is not stopped), but Codex has no cap of its own; a leaf allowed to edit the test its own
check runs can weaken it, and `done` flags that and does not refuse it (`review: every` puts each diff in front of
you before it lands); and it is local, so nothing runs off your laptop.

Plan approval, which this project first led with, is in Claude Code, Cursor, Kiro, Cline and Spec Kit. It is no
longer what is different.
