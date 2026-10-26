# The landscape, 26 October 2026: what other multi-agent coding tools do

One researcher's reading of the vendors' own pages on the night of 26 October (Fable, cut off before its
fact-check ran: **not checked by a second reader**). Each line quotes or paraphrases the page named; anything the
reader could not open is marked. Read it as a map for the next COMPARE.md, not as claims to publish.

The question for each tool: does anything hold an agent to the files of its task, does a check gate the merge,
does it keep one of several attempts and by what, does it re-check a goal, and is there a spend envelope?

| Tool | Files a task may write | A check gates the merge | Keeps one of several attempts | Re-checks a goal | Spend envelope |
|---|---|---|---|---|---|
| VS Code 1.109 to 1.143 (Agent Sessions, Compare Models) | no; worktree per session, "start separate worktree-isolated sessions when tasks must not modify the same files" | no ("comparison doesn't automatically merge") | yes, 2 to 10 attempts, an optional judge model, then the person | not documented | no |
| GitHub Copilot cloud agent, Agent Merge | no; the repo and its branch | the repo's own required checks and reviews | no | partial: iterates on feedback and failed checks | 59-minute session cap; usage billing |
| Cursor (/best-of-n, worktrees, cloud agents) | no; hooks deny reads and shell before, edits only after (`afterFileEdit`) | no ("does not merge changes back") | yes, a parent agent comments, the person picks | not documented | monthly account limit |
| Claude Code (subagents, agent teams, background, /goal) | static deny rules, checked before the write, per session not per task | not built in (a `TaskCompleted` hook can block) | no best-of-N | **yes**: `/goal`, a model checks the condition each turn | `--max-budget-usd`, print mode only |
| OpenAI Codex (cloud best-of-N, sandbox profiles) | directory-level, OS-enforced, per profile not per task | no | yes, up to 4 attempts, the person picks | not documented | weak |
| Google Jules | no (AGENTS.md, an approved plan) | no | no; a critic flags once | partial | task-count quotas |
| Devin | no ("independent work packages" by convention) | not documented | no | partial (a coordinator) | yes, ACU limit per session |
| Kiro (Web autonomous mode, Crew, Task Runner) | no per task | partial: "if tests pass, git commits the change", then a reviewer reads the diff | no | **yes**, bounded: a conductor checks acceptance criteria | counts and time, not dollars |
| OpenHands (Agent Canvas, critic, run_goal) | no (the Docker mount) | no | yes, by a learned critic (Best@8 73.8% against 57.9% random, its blog) | **yes**: `run_goal`, a judge LLM, capped | `MAX_BUDGET_PER_TASK` (archived config) |
| Conductor, Crystal, Claude Squad, Vibe Kanban, Sculptor, uzi | no | no | the person, by hand | no | no |
| Amp | unverified (its permissions page needs sign-in) | no | no | no | compute billing only |

## What none of them was read to do, which Graphene does

- A write allowlist bound to one task, refused before the write and checked by git at done.
- A landing gate the tool runs itself, in a clean copy, from the task's own declared check.
- Racing several agents on one task and keeping one by a rule fixed before any ran, over test evidence (the
  others' tests on each fork, the check's own files left alone, size, cost, time), with the deciding step said.
- A goal re-check and planned fixes inside a person-set dollar envelope, local and account-free.

## What others do better, honestly

- Isolation: Codex's OS sandbox, and VM sandboxes in Cursor's cloud, Jules, Devin, Kiro Web and GitHub's cloud;
  Graphene's hold is a hook plus git, and says so.
- Judging and synthesis: VS Code's Compare Models (a judge's scorecard, then Synthesize) and Cursor's parent agent
  give the person more than one kept fork; OpenHands' learned critic picks where no test exists.
- Goal loops exist natively now (Claude Code's `/goal`, OpenHands' `run_goal`, Kiro's conductor): what remains
  Graphene's is the loop inside the envelope, with the tests as the judge.
- Landing automation (GitHub Agent Merge), scale and unattended runtime (Claude Code workflows, Codex cloud,
  Jules), and worktree setup contracts (Cursor, Codex, VS Code, Conductor, Sculptor).

Sources, as the reader cited them: code.visualstudio.com/updates/v1_109 and v1_143,
code.visualstudio.com/docs/agents/run/compare-models; docs.github.com/en/copilot (cloud agent);
cursor.com/changelog/3-0, 2-2, cursor.com/docs/configuration/worktrees; code.claude.com/docs/en/sub-agents,
agent-view, agent-teams; learn.chatgpt.com/codex; jules.google/docs; docs.devin.ai; kiro.dev/docs; openhands.dev,
docs.openhands.dev; conductor.build; the GitHub repositories of Crystal, Claude Squad, Vibe Kanban, Sculptor and
uzi; ampcode.com/manual.
