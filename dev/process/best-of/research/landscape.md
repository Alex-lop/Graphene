# Landscape brief: harnesses and task tools for coding agents, 20 October 2026

Pages fetched 20 Oct unless marked; stars and dates from the GitHub API that day. **Unverified**: pages this environment could not open (cursor.com, developers.openai.com and agentskills.io refused connections; Amp's manual sub-pages need sign-in).

## 1. The idea that matters, per tool

**Skills and method**

- [mattpocock/skills](https://github.com/mattpocock/skills) (297.7k stars, v1.3.1): 27 skills, "small, easy to adapt, and composable", against "heavier process frameworks that take control away from the developer".
  - [tdd](https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/tdd/SKILL.md): "Write the failing test first, then only enough code to pass it"; "Test only at pre-agreed seams"; vertical slices.
  - [grilling](https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md): rounds asking every "frontier" question (prerequisites settled), each with a recommended answer so "yes" accepts it; facts to a sub-agent, decisions to the user.
  - prototype: a throwaway build for one design question; research: cited Markdown from primary sources; domain-modeling: GLOSSARY.md and ADRs; codebase-design: "large behavior behind small interfaces"; wizard: a bash script for human-only steps; writing-for-agents: SKILL.md and AGENTS.md ([README](https://github.com/mattpocock/skills)).
  - [code-review](https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/code-review/SKILL.md): two axes, standards and spec, in parallel sub-agents, never merged: it "stops one axis from masking the other".
  - [pr](https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/pr/SKILL.md): Summary, Evidence (the test that fails then passes), Merge Danger ("one-way or two-way door", a one-word blast radius).
  - [diagnosing-bugs](https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/diagnosing-bugs/SKILL.md): "one command that goes red on this specific bug" before any hypothesis; 3-5 falsifiable hypotheses; the regression test before the fix.
  - Also [to-tickets](https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/to-tickets/SKILL.md) (tracer-bullet tickets "sized to fit in a single fresh context window") and [implement-spec](https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/implement-spec/SKILL.md) (tickets are "a task graph"; an implementer subagent per ticket in its own worktree; one merger merges "one at a time").
- [obra/superpowers](https://github.com/obra/superpowers) (302k, v7.0.0): brainstorm, worktree, a plan for "an enthusiastic junior engineer with poor taste", a fresh subagent per task reviewed after each; "Evidence over claims"; skills are "Mandatory workflows, not suggestions".
- [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) (54k, v6.12.4; v7 alpha ships as skills): "Small changes go straight to build. Complex work gets the depth it needs"; decisions carried forward instead of re-explained.
- [Spec Kit](https://github.com/github/spec-kit) (142k, v1.2.2): constitution, specify, plan, tasks, then "repeat implement and converge until convergence reports `Converged`"; `uv tool install specify-cli`.
- [Kiro specs](https://kiro.dev/docs/specs/) (updated 15 Oct): tasks.md becomes a dependency graph run in waves ("Wave 1 contains tasks with no dependencies"); Quick Spec has no approval gates.
- Factory Droid ([docs](https://docs.factory.com/); search snippets, unverified): Spec Mode is read-only planning; an Autonomy Level is "the highest-risk work Droid can run without pausing for approval", each command rated low, medium or high.

**Trackers for agents**

- [beads](https://github.com/gastownhall/beads) (28k, v1.3.1): "persistent, structured memory for coding agents" on Dolt; `bd ready` lists unblocked work; `bd update --claim` is atomic; hash IDs avoid merge collisions.
- [Backlog.md](https://github.com/MrLesk/Backlog.md) (7.1k, v1.54.0): a Markdown file per task in git; a project-wide Definition of Done on every task; "one task = one context window = one PR".
- [Task Master](https://github.com/eyaltoledano/claude-task-master) (28k; last push April 2026): PRD to tasks to subtasks, `next`. Dormant.
- [Gas Town](https://github.com/gastownhall/gastown) (18k, v1.2.1): a "Bors-style merge queue — polecats never push directly to main", with verification gates and a bisecting queue; a Witness "detects stuck agents".

**Parallel-session managers**

- [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) (28k; README: "Vibe Kanban is sunsetting"; [shutdown post](https://vibekanban.com/blog/shutdown) unverified): inline diff comments "go straight to the agent".
- [Conductor](https://conductor.build/) (0.91.0): Mac app, parallel agents, "review and merge" from one dashboard. [Claude Squad](https://github.com/smtg-ai/claude-squad) (8.6k, idle since August): tmux, a worktree per agent. [Crystal](https://github.com/stravu/crystal): deprecated February 2026.
- [ccmanager](https://github.com/kbwo/ccmanager) (1.3k, v4.4.9): Waiting, Busy, Idle per session; "custom commands when Claude Code session status changes".
- [container-use](https://github.com/dagger/container-use) (4.1k; last release Aug 2025): a container and branch per agent, reviewed with `git checkout`.
- [Sculptor](https://imbue.com/sculptor/): containers because worktrees "need dependencies reinstalled"; it plans to flag "tests passed" claims "without real tests".

**Harnesses**

- [jcode](https://github.com/1jehuang/jcode) (21k) since mid-October ([v0.99.0](https://github.com/1jehuang/jcode/releases/tag/v0.99.0), 19 Oct; [releases](https://github.com/1jehuang/jcode/releases)): retry on the next pooled account at a usage limit, idle hibernation, a "stalled-worker watchdog for swarms" (v0.95), and "Swarm mode simplified: the task graph was removed".
- [Amp](https://ampcode.com/manual) ([news](https://ampcode.com/news)): Orbs, a machine per thread ("close your laptop, and the agent keeps working"); "proof, not a diff"; diffs ordered with "the files that explain a change first".
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) (91k): now "Agent Canvas", a self-hosted control center that also runs Claude Code and Codex.
- [Goose](https://github.com/block/goose) (55k): a Linux Foundation agent, desktop, CLI and API, 70+ MCP extensions.

**Claude Code** ([CHANGELOG](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md): 2.1.304 newest)

- [Plugins](https://code.claude.com/docs/en/plugins): skills, agents, hooks, MCP servers and mods installed as one unit, `name@marketplace`; project scope through the committed `.claude/settings.json`; skill names sit in context "on every turn".
- [Marketplaces](https://code.claude.com/docs/en/plugins/create-marketplace): a `.claude-plugin/marketplace.json`. [Publishing](https://code.claude.com/docs/en/plugins/publish): your own marketplace needs no form; the directory needs a paid plan. A CLI in the official marketplace can [emit `<claude-code-hint>`](https://code.claude.com/docs/en/plugins/cli-hints).
- [Skills](https://code.claude.com/docs/en/skills): a SKILL.md "loads only when it's used"; `disable-model-invocation`, `context: fork`, `hooks`, `paths`.
- [Subagents](https://code.claude.com/docs/en/sub-agents): `isolation: worktree`, `background: true`, per-agent hooks.
- [Hooks](https://code.claude.com/docs/en/hooks): about thirty events, among them `PreToolUse` (deny or `updatedInput`), `TaskCompleted` (exit 2 blocks) and `WorktreeCreate`; `onFailure: "block"` (v2.1.295) closes the fail-open gap.
- [Agent View](https://code.claude.com/docs/en/agent-view): rows grouped Ready for review, Needs input, Working, Completed; a PR label coloured by its checks; sessions move into `.claude/worktrees/` before editing.
- [Agent Teams](https://code.claude.com/docs/en/agent-teams) (experimental): a shared task list with dependencies; "Two teammates editing the same file leads to overwrites"; "Task status can lag"; no worktree isolation.
- [Checkpoints](https://code.claude.com/docs/en/checkpointing): `/rewind` restores code and/or conversation; it "does not track files modified by Bash commands".
- Background: [`Ctrl+B`](https://code.claude.com/docs/en/interactive-mode) and `/tasks`; [`/batch`](https://code.claude.com/docs/en/commands) splits a change into "5 to 30 independent units", a subagent per unit in a worktree, each "implements its unit, runs tests, and publishes its change"; [Projects](https://code.claude.com/docs/en/claude-projects) run cloud threads with shared memory ([comparison](https://code.claude.com/docs/en/agents)).

**Codex** ([changelog](https://learn.chatgpt.com/codex/changelog), newest 14 Oct; CLI rust-v0.163.0)

- [exec](https://learn.chatgpt.com/codex/noninteractive): read-only sandbox by default, `--sandbox workspace-write`, "`--full-auto` is no longer supported".
- [Hooks](https://learn.chatgpt.com/codex/hooks): "Treat tool hooks as a useful guardrail, not a complete enforcement boundary." [Subagents](https://learn.chatgpt.com/codex/subagents) inherit the sandbox; "Write-heavy parallel work can cause conflicts."
- [Cloud](https://learn.chatgpt.com/codex/cloud): a workspace per task, ending in a PR. Best-of-N: OpenAI's June 2025 post, "generate multiple responses simultaneously for a single task" ([forum copy](https://community.openai.com/t/codex-generates-multiple-responses-simultaneously/1287639)); `codex cloud exec --attempts 1-4` per a [third-party guide](https://codex.danielvaughan.com/2026/04/01/codex-cloud-exec-best-of-n-attempts/), unverified.
- [Plugins](https://learn.chatgpt.com/codex/plugins) bundle skills, MCP and hooks; "Plugins aren't available in the IDE extension". [Skills](https://learn.chatgpt.com/codex/skills) follow the agentskills.io standard in `.agents/skills`.

**Cursor** (unreachable; quotes are search snippets of [plan mode](https://cursor.com/blog/plan-mode), [hooks](https://cursor.com/docs/hooks) and [cloud agents](https://cursor.com/help/ai-features/background-agents))

- Plan Mode "asks clarifying questions, and generates a reviewable plan you can edit before building"; plans live in the home directory unless "Save to workspace".
- Hooks: `.cursor/hooks.json`; exit 2 blocks; "Other exit codes - Hook failed, action proceeds (fail-open by default)". Cloud agents: a VM each, a branch and a PR (August, secondary).

## 2. The map, and the top ten by impact on one developer running several agents on one repository

Plan, DAG, worktree per unit, tests, publish is now built into Claude Code (`/batch`, Agent Teams), Kiro (waves), mattpocock's implement-spec and Gas Town. None has the contract: a scope refused as the write happens, a check the tool runs in a clean copy, a person who accepts. Take what strengthens it.

1. **Race attempts; the check picks.** Codex best-of-N; [SWE-Gym](https://arxiv.org/abs/2412.21139) separates pass@k from best@k, its verifier lifting 20.6% to 32.0% at k=16; [SWE-HERO](https://arxiv.org/abs/2604.01496) keeps the best of 32 rollouts. Today `run` retries one after another (`ATTEMPTS = 3`, [run.py](https://github.com/Alex-lop/Graphene/blob/main/src/graphene_map/run.py)). `graphene run --attempts 3` cuts three worktrees for one leaf, runs them at once, and the leaf's check is the verifier: the first green lands, the rest are dropped; all green, the person picks in the diff pane. The worst case is N× and `--max-usd` holds it. Cost: a week; the chooser and the row are new.
2. **A leaf is a tracer bullet sized to one context window** (to-tickets, Backlog.md): vertical slices "demoable on its own" in the planner prompt and SessionStart text. Cost: a day.
3. **Evidence on the landed record** (pr skill, Amp, Sculptor): `node show` keeps attempt 1's red line and the green line that landed, plus the door: two-way (`git revert -m 1`) or one-way (migrations, CI, secrets). Cost: two days.
4. **Risk-rated sign-off** (Factory, Backlog's DoD): a scope on a configured risk list sets `signoff: yes` itself; a default check is appended to every leaf. Cost: a day.
5. **A stall watchdog that hands back with a reason** (jcode v0.95, Gas Town's Witness, ccmanager): the meter counts seconds quiet; `stall: 10m` hands the leaf back naming its last tool call, and a `notify` command runs per state change. Cost: two days.
6. **Land through a queue that bisects** (Refinery, implement-spec's merger): under `--parallel`, land serially and re-check on the merged tree; a red bisects to the leaf that broke it. Cost: three days.
7. **Review on two axes, never merged** (code-review skill): `graphene review ID`, a read-only executor call against the contract and the repo's standards, two short reports, no verdict. Cost: three days.
8. **Hooks that cannot fail open, and Teams under the contract:** `init` writes `onFailure: "block"` on the gate; a `TaskCompleted` hook completes a teammate's task only when its leaf's check passed. Cost: an hour, then a week.
9. **A worktree setup contract** (Sculptor's complaint, `.worktreeinclude`): a `setup:` command and `.worktreeinclude` so each worktree and the clean check copy have dependencies and `.env`. Cost: two days.
10. **The graph as waves** (Kiro): `g` is goal-down; [view_dag.py](https://github.com/Alex-lop/Graphene/blob/main/src/graphene_map/view_dag.py) already draws needs left to right, critical path bold; make it the view while a run is on: ready now, next wave, blocked. Cost: two days.

Below the line: question rounds (grilling); diffs ordered test first (Amp); a decisions file across plans (beads, BMAD); a JSONL plan export for teammates (beads); `--pr` landing for teams.

## 3. Do not copy

- Agent-written verify gates (jcode's `validation` string) or rubric-only passes: [Agentic Rubrics](https://aclanthology.org/2026.acl-long.697/) scores patches without tests and [R2E-Gym](https://arxiv.org/abs/2504.07164) finds hybrid verifiers scale best. Rank with them, never land on them.
- Agent-to-agent chat as the coordination primitive: jcode removed its swarm task graph in v0.99.0; Anthropic says "Task status can lag". Graphene coordinates through a store and hooks.
- A hosted service: Vibe Kanban's company "couldn't find a business model" (search snippets). "No account" is the position.
- Session-manager features (panes, previews, autoyes): Agent View does the job.
- Role-play methodologies (BMAD's roles, Spec Kit's commands): the planner already asks only what the code cannot settle.
- Hooks sold as enforcement: Codex and Cursor say theirs fail open; `onFailure: block` plus git at `done` is honest.
- Dolt as a dependency (beads); silent auto-update and default telemetry (jcode).

## 4. Distribution

How these tools reach users: Claude Code marketplaces (mattpocock, superpowers and BMAD v7 through `claude-plugins-official`); the cross-agent [`npx skills add owner/repo`](https://github.com/vercel-labs/skills) (35.7k), one SKILL.md into 75+ agents (agentskills.io standard, unverified); Codex `/plugins`; Homebrew (codex, claude-squad, beads, backlog-md, gastown, droid); uv (Spec Kit, Graphene).

Graphene should ship both, thin, with the binary still from PyPI:

- **A plugin in the Graphene repo**: a `.claude-plugin/marketplace.json` with `source: "./"`, so `claude plugin install graphene --marketplace Alex-lop/Graphene` at project scope gives collaborators the hooks through the committed settings. `hooks/hooks.json` carries the six events `init` writes today, command hooks calling `graphene hook` on PATH, the gate with `onFailure: "block"`. SessionStart injects `additionalContext` as `init` does, cut short because it costs context every turn; the plan format moves into a `graphene:plan` skill that "loads only when it's used".
- **`init` stays** for Codex (`.codex/hooks.json`), trust, plan-first mode and the install hint ("Ship a plugin with your own tool"). The `<claude-code-hint>` needs the official marketplace, which "doesn't take submissions through the directory portal".
- **A SKILL.md alone** reaches Codex, Cursor and the rest through `npx skills`; it teaches the format but cannot install hooks.
- **Traps:** plugin hooks fire in every session where enabled, so project scope only; they are skipped where an organization manages Claude Code (2.1.299); `${CLAUDE_PROJECT_DIR}` stays at the main checkout while `cwd` follows the worktree; a hook cannot install the binary, so SessionStart detects a missing `graphene`. One source (hooks.py's event list) generates both hooks.json and `init`'s settings; `claude plugin validate --strict` in CI. One to two days.
