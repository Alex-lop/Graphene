# Field study: what makes the best repo for agentic workflow (October 2026)

*field, 18 Oct 2026, for the night/publish plan. Read-only research: I changed nothing in the repo.*

**How I checked.** I used `gh api` for stars (`stargazers_count`), READMEs, the top issues by 👍 and commits since 18 Jul, run 18 Oct between about 23:00 and 23:50 ET. For Hacker News I used the Algolia search/items API and the Firebase item API, which gives top-level comments in ranked order. Sites and docs came from WebSearch and WebFetch.

**Not checked:**
- Reddit: WebSearch refused reddit.com, and the JSON search returned non-JSON.
- The hackathon's rubric: allthingsagentichackathon.devpost.com returned 403. The Google post gives only the theme ("agents that take on the busy work", Gemini 3.5) and the window, 3 to 31 Aug 2026.
- Conductor's source: it is closed.
- The Vibe Kanban shutdown page itself: it gave a TLS error, so I quote it through search results.

## The short version

1. **The README's try line installs a build that has no cockpit.**
   - The README's `uvx --from graphene-map graphene demo` resolves to PyPI 0.5.0. That is tag v0.5.0 (a96fb48a, 7 Oct), uploaded 13 Oct.
   - `git ls-tree --name-only v0.5.0 src/graphene_map/ | grep -c cockpit` prints `0`.
   - `git rev-list --count v0.5.0..HEAD` printed `332` at 921834de.
   - The GIF and both stills show the cockpit. A judge who copies the line sees the older screen.
2. **"Parallel agents, a worktree each, one dashboard" now comes free with the first-party tools.**
   - The Codex app (2 Feb 2026) gives each agent a worktree and has a review queue.
   - Claude Code's Agent View (`claude agents`, 11 May 2026) is "one screen for all your background sessions: what's running, what needs your input, and what's done".
   - Agent Teams share a task list.
   - The first wave of wrappers has gone quiet:
     - opcode: 1 commit since 18 Jul; its last release is v0.2.0 (31 Aug 2025).
     - Task Master: 0 commits since 18 Jul.
     - Crystal: deprecated in Feb 2026.
     - Bloop, the company behind Vibe Kanban, shut down on 10 Apr 2026.
     - claude-squad: issue #250 is "Project Seems Abandoned".
3. **The field's top open complaint is the thing Graphene enforces.**
   - Superpowers has 301,693 ★. Its PR #578 says: "Phantom completion. The most common complaint: a plan finishes, everything shows green, and the implementation is partially or entirely hallucinated."
   - Claude Code's own Agent Teams docs say "Two teammates editing the same file leads to overwrites. Break the work so each teammate owns a different set of files."
   - The same docs say plan approval happens "without the lead reviewing it" and that "Task status can lag".
   - Graphene answers each one:
     - a scope per leaf, with any write outside it refused before it happens;
     - a check Graphene runs itself in a clean copy;
     - the plan in front of the person before anything runs.
4. **The leaders have moved to a plan graph, with workers named by their task.**
   - jcode's SWARM_TASK_GRAPH.md: "The DAG becomes the primary object; agents become fungible workers."
   - Beads "replaces messy markdown plans with a dependency-aware graph".
   - jcode's own UI labels a worker by its task: "the user-provided spawn label is the useful primary identity".
   - Graphene's plan tree is already this model. Alex's names-to-numbers change landed tonight as 3e38cf24.
5. **Tools lose trust through side effects, not missing features.**
   - Telemetry on by default: Vibe Kanban's top HN comment, with 41 replies.
   - Silent auto-commits: Backlog.md #160.
   - An installer that edits dotfiles and Claude/Codex hooks: jcode #811 and #678.
   - Local installs spending users' credits on upstream issues: Gas Town #3649, 253 HN points.
   - Login walls: Superset #2685.
   - Graphene's "no account, sends nothing, `graphene init --remove`" is a selling point, but it sits in a collapsed `<details>` (README.md:77).

## 1. The tools

Stars are as of 18 Oct. The pitch is the GitHub description.

| Tool | ★ | Pitch | Above the fold |
|---|---|---|---|
| jcode `1jehuang/jcode` | 21,013 | "High performance coding agent harness written in Rust, built for heavy multi-agent dev workflows" | light/dark logo, Trendshift badge; **"High-performance coding agents."** + "Run dozens of agents in parallel without melting your machine"; 4 badges; 4-screenshot table; YC launch video; `curl -fsSL https://jcode.sh/install \| bash`; benchmark tables, each with a Reproduce script |
| claude-squad | 8,620 | "Manage multiple AI terminal agents like Claude Code, Codex, OpenCode, and Amp." | H1 with CI and release badges; one sentence; screenshot; 4 highlights ("Review changes before applying them"); video; `brew install claude-squad` |
| Vibe Kanban | 28,390 | "Get 10X more out of Claude Code, Codex or any coding agent" | logo; tagline; 3 badges; an H1 "**Vibe Kanban is sunsetting.**"; screenshot; "the most impactful way to ship more is to get faster at planning and review"; `npx vibe-kanban` |
| Conductor (closed) | n/a | site: "Run parallel coding agents on your Mac." | download button; supported agents; release 0.91.0; no testimonials or counts |
| Crystal → Nimbalyst | 3,134 | "(Crystal is now Nimbalyst)…" | the whole README is a deprecation page ("Deprecated: February 2026") |
| Sculptor | 240 | "Build product with grounded, parallel coding agents." | plain H1 + one sentence; two NOTE boxes (research preview, no outside contributions); downloads; a getting-started paragraph |
| opcode (was Claudia) | 22,415 | "A powerful GUI app and Toolkit for Claude Code…" | logo; 5 "for-the-badge" nav badges; video; "⭐ Star the repo … for early access"; "not affiliated with Anthropic" note; long TOC |
| ccmanager | 1,265 | "Coding Agent Session Manager for Claude Code / Gemini CLI / Codex CLI / …" | H1; one sentence; video; features; then "Why CCManager over Claude Squad?" |
| Backlog.md | 7,072 | "…managing project collaboration between humans and AI Agents in a git ecosystem" | logo; **"Markdown‑native Task Manager & Kanban visualizer for any Git repository"**; "AI agents write the code. You review the tasks: before, during, and after."; `npm i -g backlog.md`; board GIF |
| Task Master | 28,244 | "An AI-powered task-management system you can drop into Cursor, Lovable, Windsurf, Roo, and others." | Trendshift badge; logo; about 10 badges, including 3 npm-download and 2 Twitter-follow badges; docs links |
| Spec Kit | 141,821 | "Toolkit to help you get started with SDD or any other process!" | logo; "Build with a spec, fix a bug, or assess an idea — with your coding agent."; 4 badges; a "Choose your process" table (need → process → outcome) |
| OpenSpec | 72,339 | "Spec-driven development (SDD) for AI coding assistants." | banner; badges; philosophy block ("→ fluid not rigid → iterative not waterfall"); `<!-- TODO: Add GIF -->`; a "See it in action" You:/AI: transcript |
| BMAD-METHOD | 54,308 | "Breakthrough Method for Agile Ai Driven Development" | banner; **"turn an idea or change request into working software without giving up the thinking."**; loop SVG (Clarify → Plan → Build and verify → Learn and adjust); `npx bmad-method install` |
| Superpowers | 301,693 | "An agentic skills framework & software development methodology that works." | no logo, no badges, no GIF; one sentence, a TOC, then "How it works" told in the second person |
| herdr | 44,662 | "the runtime your coding agents live on" | logo; 6 grey badges; video; bold tagline; 8 "**benefit** — detail" bullets; one install line; "run your agents, split panes, walk away"; an "agent instructions" section |
| Paperclip | 104,188 | "The open-source app everyone uses to manage agents at work" | banner; video; waitlist CTA; "If OpenClaw is an *employee*, Paperclip is the *company*."; 3-step table; agent logo grid; "Paperclip is right for you if" |
| cmux | 28,250 | "…Ghostty-based macOS terminal with vertical tabs and notifications for AI coding agents" | screenshot; demo video; a features table with text on the left and a picture on the right ("Notification rings", "Notification panel") |
| Beads | 27,997 | "Beads - A memory upgrade for your coding agent" | **"Distributed graph issue tracker for AI agents"**; badges; a mermaid loop (create → ready → claim → close); curl + `bd init` + `bd setup claude`; an AGENTS.md snippet |
| Gas Town | 18,415 | "Gas Town - multi-agent workspace manager" | problem/solution table; architecture mermaid; a glossary of coined roles (Mayor 🎩, Rigs, Polecats 🦨, Convoys 🚚, Molecules 🧬, Witness/Deacon/Dogs) |
| Superset | 15,346 | "…an agentic IDE to orchestrate 100+ coding agents in parallel…" | icon; one sentence; hero GIF "with live diffs"; "Documentation for agents" (llms.txt); "Start with one task" in 3 steps |
| Orchestrator.inc | 13,331 | "Run and supervise teams of coding agents from planning to merge…" | logo; three value lines; hero "Kanban showing worker sessions grouped by live status" |
| Happy | 24,201 | "Orchestrate Claude, Codex and Grok in one app…" | "Any Model. Your Subscription."; video; an App Store badge "Rated 4.9 stars from 1,000+ ratings" |
| Worktrunk | 9,294 | "…Git worktree management, designed for parallel AI agent workflows" | the author's dated note ("Please let me know any frictions"); demo GIF; "Context: git worktrees" |
| Agent of Empires | 3,365 | "Manage multiple Claude Code, OpenCode agents from either TUI or Web…" | many badges; office-hours banner; demo GIF + a phone GIF |

### Loop, praise and complaints, tool by tool

**jcode.**
- **Loop:** `jcode`, then spawn a swarm (`/swarm`, Alt+N focuses the inline swarm panel).
- **Swarm UI**, read from the clone of 15 Oct at `tmp/jcode/repo`:
  - A server manages every agent in a repo. "When agent A edits a file that agent B has read … the server notifies agent B."
  - Agents send DMs or broadcasts. The coordinator spawns workers.
  - A compact strip shows an emoji and an animated status glyph per agent. The selected row expands as an accordion.
  - A dedicated page shows "a nested, ownership-aware tree of every managed agent with animated status glyphs", with "the selected agent's detailed live card" below it.
  - The swarm plan is drawn as an inline Mermaid graph with assignees.
  - Lifecycle states: spawned, ready, running, blocked, completed, failed, stopped, crashed.
  - A completion report must give the outcome, the changes, the validation done and the blockers, "not just `done`" (`docs/SWARM_ARCHITECTURE.md`).
  - In the DAG redesign, deep mode needs a critique/verify gate before a node closes, and the handoff includes `what_i_did_not_check` (`docs/SWARM_TASK_GRAPH.md`).
- **Praise:** HN barely noticed it (Show HN, 5 pts: https://news.ycombinator.com/item?id=49249151). It grew through X and its YC video. It ships fast: v0.99.0 came out 19 Oct, with 100+ commits since 18 Jul.
- **Complaints:**
  - #811 "STOP shilling jcode via Claude Code/Codex configs and silently editing dotfiles on first run". The installer "injects a `SessionStart` hook into `~/.claude/settings.json` and `~/.codex/hooks.json` that shows ad-style desktop notifications … no consent prompt and no working opt-out."
  - #678: "Installer silently adds a global shortcut and persistent LaunchAgent".

**claude-squad.**
- **Loop:** `cs`; `n` opens a session in tmux plus a worktree; `↵` attaches; `tab` switches between preview and diff; `c` commits and pauses; `s` commits and pushes. A menu at the bottom lists the keys.
- **Complaints:**
  - #250 "Project Seems Abandoned" (11 👍) and #214 "No more updates?" (16 👍).
  - tmux capture-pane errors (#216, #189).
  - ccmanager's README says claude-squad shows no session state, and that its AutoYes "bypasses Claude Code's built-in security confirmations".
- **Activity:** 3 commits since 18 Jul.

**Vibe Kanban.**
- **Loop:** an issue on the board becomes a workspace (branch, terminal, dev server). You review the diff and leave inline comments that go to the agent, then open a PR and merge. The columns are To do → In progress (attempt started) → In review (attempt finished, passed or failed) → Done (merged) (https://vibekanban.com/docs/core-features/creating-tasks.md).
- **Praise:** Show HN, 195 pts and 132 comments (https://news.ycombinator.com/item?id=44533004): "feels like the same increase in productivity … from when I first used Cursor".
- **Complaints:**
  - The top comment (41 replies): "analytics appear to default to enabled … It is harvesting email addresses and github usernames".
  - "The permissions this asks for feel kinda insane".
  - Parallel agents "clash while editing files simultaneously, i lose mental context of what's going on, they rewrite tests".
  - #2687 "Bring back old UI" (33 👍, 39 comments): "after upgrade ALL old tasks and PROJECTS are gone". #2509: "please keep the Kanban board".
  - Bloop shut down on 10 Apr 2026. Search quotes the CEO: "the vast majority are free users and we couldn't find a business model".

**Conductor (Melty Labs).**
- **Loop, from its docs:** each task gets a workspace with its own "branch, files, terminal, diff, and review path". In the diff viewer, line comments go to the agent. The Checks tab is "the last review pass before merge": git status, PR, CI and todos, and it "may block or discourage merge actions". Then you open a PR, merge and archive.
- **Agents:** Claude Code, Codex and Cursor. It ships a tutorial repo (`meltylabs/conductor-tutorial`).
- **Praise:** "They get the git worktree setup and teardown and managing dev servers part of it right" (https://news.ycombinator.com/item?id=46588905).
- **Complaints:** "I really didn't like the extra stuff conductor added to the UX (the text rendering always drove me nuts)" (https://news.ycombinator.com/item?id=48236770). It is Mac only.

**Crystal.**
- Ran Claude Code and Codex sessions in parallel worktrees. Deprecated in Feb 2026; the final release, v0.3.5, came out 26 Feb.
- Its HN posts got 4 pts or fewer. The lesson: a rebrand strands users.

**Sculptor.**
- **Loop:** "Connect a repo, create a workspace (an isolated copy of your code), and prompt an agent. Review the changes when it's done and merge back to main."
- **Praise:** HN, 176 pts and 85 comments (https://news.ycombinator.com/item?id=45427697): "I was cooking dinner and blasting out features".
- **Complaints:**
  - "are we all just working on various ways of using Claude Code in docker with git worktrees?"
  - "It's not clear to me what a 'container' and 'pairing' is"
  - "free while we're in beta. Ok, and then what?"
- **Activity:** very active (v0.49.0rc1 on 19 Oct).

**opcode / Claudia.**
- **Praise:** HN, 501 pts and 226 comments (https://news.ycombinator.com/item?id=44933255).
- **Complaints:**
  - "we're in the 'Twitter client' phase of LLM IDEs".
  - The name: "'Claudia' closely resembles 'Claude'". It was renamed.
  - "Does this sandbox the agents? … enforced using operating system primitives rather than a pinky promise with an LLM".
  - "the fact that Claude Code is a standalone terminal app is a strength".
  - On the homepage video: "please … slow it down and make it less frantic".
- **Activity:** 1 commit since 18 Jul; last release 31 Aug 2025.

**ccmanager.**
- **Loop:** one menu of sessions per worktree, each shown as Waiting, Busy or Idle. "Status change hooks for automation and notifications"; `.worktreeinclude` carries gitignored files into new worktrees.
- Its README has a fair comparison: "If you love tmux-based workflows, stick with Claude Squad!"
- **Reception:** its HN post got 1 pt. The top issues are small (a multi-repo view, copying gitignored files).

**Backlog.md.**
- **Loop:** `backlog task create`; the agent writes its plan into the task; you approve; it builds. `backlog board` and `backlog browser` show the board.
- **README:** "The bottleneck is no longer writing code. It's your attention." It offers three review checkpoints (spec, plan, code) and "one task = one context window = one PR". It is dogfooded: "nearly all of Backlog.md's own code is written by AI agents working through Backlog.md itself".
- **Praise:** HN, 254 pts (https://news.ycombinator.com/item?id=44483530). The author: "The fix turned out to be process, not model horsepower" (task success went 50% → 75% → 95%+).
- **Complaints:**
  - #160: "uses git commits and automatically creates them without my knowledge".
  - tptacek: how are planned tasks dispatched, and how does the agent avoid "blowing out their context budget"?

**Task Master.**
- **Loop:** `task-master parse-prd`, `task-master next`, expand, set status.
- **Complaints:** "Better AI Model Management" (#79, 36 👍) and "Pure MCP for 0$ cost" (#366, 35 👍): users don't want a second bill. The license is "MIT with Commons Clause".
- **Activity:** 0 commits since 18 Jul; the last was 23 Apr.

**Spec Kit.**
- **Loop:** `/speckit-constitution` → `-specify` → `-plan` → `-tasks` → `-implement` → `-converge`.
- **Complaints:**
  - #1191 "Can't Easily Update or Refine Existing Specs" (105 👍).
  - #467: users asked for a workflow diagram (50 👍).
  - Fowler (HN 128 pts, https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html): "I'd rather review code than all these markdown files", "felt like overkill for the size of the problem", "the agent ignored the notes".

**OpenSpec.**
- **Loop:** `/opsx:explore` → `propose` → `apply` → `archive`.
- **Praise:** "definitely less heavy than SpecKit" (HN 204 pts, https://news.ycombinator.com/item?id=49734264).
- **Complaints:**
  - "huge divergence from spec to code" after 6 to 9 months of use.
  - "The documentation is entirely about how to use it … What I'd like to see is what it is, how and why it works, ideally backed by some benchmarks".
  - "Haven't we moved on from these things?"

**BMAD.**
- **Loop:** role skills (analyst, PM, architect, dev) carry briefs and specs forward. Its loop diagram says "Start anywhere".
- **Praise and complaints:** not checked. Its HN posts got 4 pts or fewer, and Reddit was blocked. The top issues are integration requests (OpenCode #285 with 41 comments; "Incorporate agent teams for Claude code" #1613).

**Superpowers.**
- **Loop:** brainstorming → using-git-worktrees → writing-plans (2 to 5 minute tasks) → subagent-driven development with a review after each task → TDD → finishing-a-development-branch. It installs in one line: `/plugin install superpowers@claude-plugins-official`.
- **Praise:** Simon Willison: "I can't recommend this post strongly enough" (HN 435 pts, https://news.ycombinator.com/item?id=45547344). "Superpowers 6" got 196 pts.
- **Complaints:**
  - "This isnt science, or engineering. This is voodoo".
  - "not very valuable without benchmarks".
  - #743: slowness since installing (32 reactions).
  - #895: plans "over-specify implementation, leaving no room for executor judgment" (38 reactions).
  - PR #578: phantom completion.

**herdr.**
- **Loop:** run `herdr` where the work lives; run agents in panes, each marked working, blocked or idle; `ctrl+b q` detaches; `herdr` reattaches.
- **Site:** a clickable mock layout. States are a glyph plus a word: ● working, ○ idle, ◉ blocked.
- **Praise:** HN, 404 pts (https://news.ycombinator.com/item?id=48756578):
  - "a UI for agents running in panes, with a cool status (idle/working) display".
  - "it doesn't punish you for not remembering the bindings, everything is clickable".
  - "a great landing page where you can see and interact".
- **Complaints:**
  - "what's the value over tmux?"
  - Users asked for worktree support and file diffs.
  - #1134: a 60Hz limit (32 👍). #1307: the terminal theme is unreadable on Ghostty's light theme.

**Paperclip.** Its README checklist: "You have 20 simultaneous Claude Code terminals open and lose track of what everyone is doing", and "monitor costs and enforce budgets". Reception not checked: I found no sizable HN thread.

**cmux.**
- **Origin:** the Show HN post (198 pts, https://news.ycombinator.com/item?id=47079718) says "Claude Code's notification body is always just 'Claude is waiting for your input' with no context".
- **Features:** blue notification rings, and a panel that can "jump to the most recent unread".
- **Complaints:** "a buggy mess. Can't switch top tabs".

**Beads.**
- **Praise:** HN, 111 pts (https://news.ycombinator.com/item?id=46075616): simonw on the JSONL + SQLite data design, and "turning the corner … to inventing new tools … designed specifically for AI use".
- **Complaints:**
  - "kept wondering what problem the system aims to address".
  - "Agents report that they enjoy working with Beads" was questioned.
  - #376 "I want to love Beads but the AI generated docs make it impossible" ("bold, overhyped claims").
  - #2573 "Moving to dolt pretty much made beads unusable for me" (37 👍).

**Gas Town.**
- **Reception:**
  - "Welcome to Gas Town": 354 pts.
  - Maggie Appleton's review: 403 pts and 433 comments (https://news.ycombinator.com/item?id=46734302). She found its AI-made diagrams "unhelpful".
  - "Gas Town Decoded": 219 pts and 234 comments. A whole post was needed to decode the vocabulary.
- **Complaints:** #3649, also on HN at 253 pts: its formulas "burning through usage on subscribed LLMs … without the user's explicit direction".

**Superset.**
- **Praise:** Launch HN, 108 pts and 135 comments (https://news.ycombinator.com/item?id=48236770): "running probably 40-50 agent sessions over several repos simultaneously without losing track".
- **Complaints:**
  - Login: "it's behind a login wall", and #2685 "Make login non-required".
  - It "tries to download its own OpenCode instead of using the one installed".
  - Freezing; Mac only.

**Orchestrator.inc.** Its README states the problem first: "One coding agent can handle a task. Running several across a project creates a different job…". Its Show HN title: "Built using the agents it orchestrates".

**Agent of Empires.**
- Show HN: 118 pts (https://news.ycombinator.com/item?id=46588905).
- A user asked: "Does it have a . Hotkey for automatically switching to the next idle worker, like the namesake did?"
- A complaint: it corrupted a user's tmux server.

### What a judge already has from first-party tools

**Claude Code Agent View** (https://code.claude.com/docs/en/agent-view.md):
- Rows are grouped by state, with "`Ready for review` and `Needs input` above `Working` and `Completed`".
- A row shows "the session's name, current activity, and its age", plus a PR label coloured by its checks.
- Keys: ↑/↓, Enter or → attaches, Space opens a peek panel, Ctrl+S, Ctrl+T pins, Ctrl+R renames, Ctrl+X stops, `?` lists keys.
- You reply in the peek panel, and digits pick a choice.
- It sends notifications through the terminal channel and fires the `Notification` hook (`agent_needs_input`, `agent_completed`).
- It has **no cost, token or diff column**.

**Claude Code Agent Teams** (experimental, off by default; https://code.claude.com/docs/en/agent-teams.md):
- A shared task list: pending, in progress, completed, with dependencies, and self-claim under file locking.
- The `TaskCompleted` hook can block completion by exiting with code 2.
- Limits, in its own words: the file-overwrite warning, plan approval "without the lead reviewing it", "Task status can lag", and "The lead can stop early too".

**Codex app** (HN 805 pts and 638 comments, https://news.ycombinator.com/item?id=46859054):
- A worktree per agent, a review queue, and automations.
- An HN reply: "workspace agent runner apps (like Conductor) get more and more obsolete".

## 2. What the best READMEs share

1. **They say what it is in one line, and what changes for you in the next.**
   - herdr: "the runtime your coding agents live on."
   - Backlog.md: "AI agents write the code. You review the tasks: before, during, and after."
   - BMAD: "…without giving up the thinking."
   - Graphene today: README.md:12 opens with "Why I built this". Its first sentence is a forecast. What Graphene is comes about 150 words later.
2. **The loop is visible in the first screen.**
   - A GIF or video: claude-squad, Backlog.md, Superset, herdr, Agent of Empires.
   - A diagram: Beads' mermaid loop, BMAD's loop SVG.
   - A transcript: OpenSpec.
   - Graphene has a GIF (546 KB, 1000×480) and a loop SVG. Its stills, though, show an empty moment and the old names:
     - cockpit.png reads "no goal yet", "0 need you", and agents "ant", "otter", "quail";
     - map.png reads "0 of 30 files may be touched (0%)", with every folder "nobody".
3. **One command to try sits near the top.** `npx vibe-kanban`; herdr's curl line, then `herdr`; `npm i -g backlog.md`.
4. **A first task comes in three steps.** Superset's "Start with one task"; Paperclip's 01/02/03; herdr's "run your agents, split panes, walk away."
5. **The problem comes before the features, in the reader's words.**
   - Backlog.md: "AI agents can now produce more plausible code in an hour than you can carefully read in a day."
   - Worktrunk: "requires typing the branch name three times".
   - The counterexample is Beads, whose top HN comment is "kept wondering what problem the system aims to address".
6. **Evidence beats adjectives.**
   - jcode puts a Reproduce link under each benchmark table.
   - Backlog.md has its dogfood ledger in the repo, and talks.
   - Beads tracks its own issues in Beads.
   - Orchestrator.inc was "Built using the agents it orchestrates".
   - The counterexamples are OpenSpec and Superpowers, both asked on HN for benchmarks.
7. **Restraint.** Superpowers (301.7K ★) has no logo and no badges, just a story. herdr's badges are grey. The counterexamples are Task Master's badge wall and opcode's "Star the repo … for early access".
8. **They are honest about limits and fair to rivals.** ccmanager tells tmux users to stay with Claude Squad. Graphene already does this well: COMPARE.md says "gaps included", and the README has the "a plain paragraph … did just as well" line.
9. **They write docs for agents.** herdr's "agent instructions" section; Superset's llms.txt; Beads' AGENTS.md snippet and `bd setup claude`.
10. **One picture per feature.** cmux's table puts text on the left and a screenshot on the right.

## 3. Twelve things Graphene could take, ranked

Each item gives what to take, the evidence, Graphene today, and the change.

1. **Make the try line run what the README shows (onboarding).**
   - **Evidence:** every top repo's one-liner installs the current build.
   - **Today:** PyPI has 0.5.0 (13 Oct) and no `cockpit/`. pyproject says 0.5.1, and tag v0.5.1 is local only. website.md says the v0.5.1 release workflow failed on a red suite.
   - **Change:** publish the build that has the cockpit before the README goes out. That is a tag push, so it is **Alex's call**. If the README must be right sooner, a possible interim line is `uvx --from git+https://github.com/Alex-lop/Graphene graphene demo`. Not checked: a lane should try it with UV_TOOL_DIR and UV_TOOL_BIN_DIR under its own folder.
2. **First screen: what it is, the promise, the loop, the try line (README).**
   - **Evidence:** patterns 1 to 4.
   - **Change:**
     - Order: mark → H1 → one line in Graphene's own nouns (a plan tree whose leaves each name the files they may change and the check that proves them done) → the existing bold promise → the GIF → `uvx` → three steps (say it → fix the plan → each leaf lands only when its check passes).
     - Re-render the GIF and stills after 3e38cf24 at a busy moment: two leaves running, one come back with its reason, one landed, numbers instead of animals, and a real goal.
     - Make "Why I built this" the second section, in Alex's voice, 3 to 4 sentences, linking his video (https://www.youtube.com/watch?v=S3mucmwD-kQ). Backlog.md puts its "Why … in the AI era" right under the GIF, and its "It's your attention" is the same thesis as his "it's going to be you, the human".
     - His uncommitted diff (16 Oct) already moves Why down. Its Cost bullet says "nothing caps the total yet", but `--max-usd` exists (plan_cli.py:1022, run.py:439). Fix that line before using it.
3. **Lead the difference with the field's own top complaint, and say what Graphene already does that others headline (positioning).**
   - **Evidence:** Superpowers PR #578; the Agent Teams doc quotes above; claude-code #46940; every orchestrator headlines "each task gets its own git worktree".
   - **Today:** run.py:11 already gives each leaf its own worktree and branch, but the README never says "worktree" (only "merges the leaf into your current branch", README.md:53). COMPARE.md's Claude Code row was written before Agent View and Agent Teams were in it.
   - **Change:**
     - Add one sentence to "How it works": each leaf runs in its own worktree on its own branch, and merges only after Graphene's own run of its check in a clean copy.
     - Add COMPARE.md rows for Agent View and Agent Teams, quoting their docs:

       | | Agent View / Agent Teams | Graphene |
       |---|---|---|
       | Files | scope by convention | write refused before it happens |
       | Plan | approved by the lead | approved by you |
       | Done | by task status | by a command Graphene runs |
4. **A review before landing, for every leaf, on request (diff review).**
   - **Evidence:** Conductor's diff viewer and its "last review pass before merge"; Vibe Kanban's In review column with inline comments; the Codex app's review queue; claude-squad's diff tab. Agent View has no diff.
   - **Today:** README.md:90 says "Not yet: a look at every diff before it lands". Only sign-off leaves wait, and `i` then `c` shows their diff.
   - **Change:** a run or plan setting that puts a green leaf in the existing review state (◆) instead of landing it. Enter lands it, `x` hands it back with a line, `c` shows the diff. The default stays "the check decides". Effort: medium. Not checked: how sign-off is stored.
5. **Say when something needs you, and why (notifications).**
   - **Evidence:** cmux exists because Claude Code's notification has "no context"; herdr: "when an agent stops and needs an answer, herdr says so"; Agent View's notifications and its `Notification` hook; ccmanager's status hooks; HN users wiring "a hook+Pushover".
   - **Today:** there is no notification code. Grepping cockpit/ and run.py for bell, notify and OSC finds only a threading `notify_all` (run.py:477).
   - **Change:** when "need you" goes up, ring the bell and send an OSC 9 notification carrying the reason, for example "agent 2 · parser fix came back: check red (tests/test_parse.py)". Add one setting to turn it off. Small change in app.py.
6. **Put the state on each row in words (per-agent status line).**
   - **Evidence:** herdr's glyph-plus-word states; Agent View's six states, with Needs input and Ready for review first; ccmanager's Waiting/Busy/Idle; jcode's eight states.
   - **Today:** the cockpit already puts what needs you first. It shows numbers no rival has: pace, files touched of allowed, proofs, writes stopped, seconds quiet (rows.py:1-7). State, though, is only a glyph and a colour (look.py STATE_GLYPH).
   - **Change:** add the word after the glyph: running, needs you, came back, checking, review, landed. Keep Graphene's numbers on the right. They are what Agent View cannot show; it shows only name, activity and age.
7. **Agents by number, rows by task.** This is Alex's ask, and jcode's code backs it.
   - **Evidence:** jcode, info_widget_swarm_gallery.rs:132: "the user-provided spawn label is the useful primary identity". comm_session.rs:787: "so the swarm strip and member lists can show the task, not just the animal name". Gas Town's coined roles needed a decoder post.
   - **Done:** landed tonight as 3e38cf24 ("● 1  users return ids").
   - **Open:** digits still mean "pick that option" (help.py:18, app.py:489). On a task row they answer "pick needs a question and one of its numbers" (verbs.py:131-136), while the row now shows a digit.
   - **Proposal, for Alex's veto:** on a task row, digit N selects agent N; on a question row, it picks option N. Agent of Empires users asked for a key that jumps to the next idle worker.
8. **Time and money on screen (meters).**
   - **Evidence:**
     - Paperclip: "track work and costs from one dashboard", plus budgets.
     - jcode's widgets include UsageLimits quota bars.
     - ccusage has 19,057 ★ for usage alone.
     - Agent View shows no cost.
   - **Today:** a $2 cap per attempt (Claude Code), `--max-usd`, and a worst case stated before a run. None of it is in the cockpit: no cost field in rows.py, model.py or read.py.
   - **Change:** a header like "$0.84 of $5 · 3 attempts", and rows like "4m · $0.12", from the existing ledger. Show "—" for Codex, which has no cost data.
9. **Proof anyone can rerun, plus the record of Graphene building itself (evidence).**
   - **Evidence:** pattern 6.
   - **Today:**
     - `graphene demo --cheat` "tries seven ways round them".
     - Alex's diff says "A real two-leaf run cost $0.30".
     - Graphene's own commits landed through its leaves. This is from memory, not re-verified: the 13 Oct direction run landed 23 commits that way.
   - **Change:**
     - A 7-row table of the cheats, each with what stopped it, generated from `--cheat` output, with the command to rerun it.
     - One line: "built with Graphene: N leaves landed through their checks", with a link.
     - Keep the honest "plain paragraph" line.
10. **A trust line above the fold.**
    - **Evidence:** section 4. Backlog.md puts "Local-first -- no server, no account, no telemetry" in its feature list.
    - **Today:** Graphene's version of this is true, but it sits in a collapsed `<details>` (README.md:77).
    - **Change:** one line under the try command: local, no account, sends nothing, `graphene init` adds hooks to this project only, `graphene init --remove` takes them out. Check each claim against hooks.py before writing it.
11. **Keys you don't have to remember (keyboard).**
    - **Evidence:** herdr: "doesn't punish you for not remembering the bindings"; claude-squad's bottom menu; Agent View's keys are what Claude Code users' fingers know (Space peek, `?`, Enter); cmux jumps "to the most recent unread".
    - **Today:** about 30 keys in help.py. Row words are clickable. The replay footer is already a key line ("space pause · . next · r again · i everything · g graph · m map · ? keys · q").
    - **Change:**
      - In live watch, a footer of the 4 to 6 keys for the selected row's state. For a came-back row: Enter retry · w widen · t tell · x drop · i details.
      - Space as an alias of `i` where it is free. Replay uses Space for pause, so keep it there.
      - A "next that needs you" key, if Enter doesn't already cycle.
12. **A kanban folded into one column.**
    - **Evidence:** Vibe Kanban's columns, and its users' "please keep the Kanban board"; `backlog board`; Orchestrator.inc's "grouped by live status"; Agent View groups rows by state.
    - **Change:** thin group headers with counts in the existing list: needs you 2 · running 3 · ready 1 · waiting 2 · landed 5. No four-column board in 80 columns.

**Smaller ideas, not ranked:**
- An "agent instructions" section and an llms.txt (herdr, Superset).
- Packaging as a Claude Code plugin for distribution. Superpowers installs with one `/plugin install` and has 301.7K ★.
- A `TaskCompleted` hook so Agent Teams tasks get a Graphene check ("Exit with code 2 to prevent completion").
- jcode's `what_i_did_not_check` in a leaf's done record.
- A "right for you if" list (Paperclip).
- A GitHub description that says what Graphene is. Today it reads "Trying to make the collaboration w/ Claude better so you have an idea of what's going on with your agent"; the repo has 0 ★ and 3 views in 14 days.
- A listing in hesreallyhim/awesome-claude-code (55,974 ★).

## 4. What not to copy

- **Telemetry on by default.** Vibe Kanban's top HN comment.
- **Silent side effects:**
  - auto-commits (Backlog.md #160);
  - an installer that edits dotfiles, adds LaunchAgents and injects hooks into `~/.claude` (jcode #811, #678);
  - spending users' credits on upstream issues (Gas Town #3649);
  - changing a setting after an update without asking ("Codex macOS app switches to Fast speed after update without asking", HN 47886763).
- **Accounts and login walls.** Superset #2685.
- **Coined vocabulary.** Gas Town needed "Gas Town Decoded". Animal names are gone as of 3e38cf24; don't bring them back as glyph mascots.
- **AI-written hype docs and claims about how agents feel.** Beads #376 and its "Agents report that they enjoy working with Beads"; Gas Town's AI-drawn diagrams.
- **Frantic demo videos.** Claudia on HN.
- **Redesigns that take away the familiar view.** Vibe Kanban #2687. Graphene keeps `--classic`; good.
- **Badge walls and star-begging.** Task Master; opcode.
- **Competing only on parallel sessions, worktrees and a dashboard.** First-party tools ship it. opcode, Task Master, Crystal and Vibe Kanban are gone or quiet.
- **Spec ceremony and plans that write the code for the agent.**
  - Spec Kit: "I'd rather review code than all these markdown files".
  - Kiro: "a sledgehammer to crack a nut".
  - Superpowers #895: plans that over-specify implementation.
  - Keep a leaf as scope plus check.
- **Persuasion-style prompting and claims without benchmarks.** Superpowers on HN.
- **Agent chat swarms run on "I've never seen the code".** Gas Town. Also jcode's agent-written verify string (from the 15 Oct study).
- **Remote, mobile, cloud and multiplayer for now.** Happy, Agent of Empires' web view, herdr's remote, Paperclip Cloud. It is a real trend, but out of scope tonight.
- **Names close to someone's trademark.** Claudia became opcode; Mux became Xum.

## 5. Facts from Graphene's repo the lanes need

- **PyPI:** `curl https://pypi.org/pypi/graphene-map/json` → latest `0.5.0`; releases `0.2.0` (20 Sep) and `0.5.0` (13 Oct).
- **The published tag:**
  - `git ls-tree --name-only v0.5.0 src/graphene_map/` has no `cockpit/`.
  - `git log -1 v0.5.0` → `a96fb48a Wed Oct 7`.
  - pyproject `version = "0.5.1"`; tags v0.5.1 and v0.5.0 are local.
- **night/publish moved while I worked:** `3e38cf24 cockpit: agents go by numbers…` sits on 921834de. Digit keys are unchanged (help.py:18, app.py:489).
- **The stills predate 3e38cf24.** Both images show animal names, I viewed both:
  - cockpit.png shows "no goal yet" and "x pull back", where the keys help says "x … hand a running agent back";
  - map.png shows every folder as "nobody".
- **Worktrees:** run.py:11, each leaf gets its own worktree on its own branch. The README never says so.
- **Cost:** `--max-usd` is at plan_cli.py:1022 and run.py:439. Alex's uncommitted Cost bullet ("nothing caps the total yet", diff line 59) is out of date.
- **No notifications:** there is no bell, OSC or notification code in cockpit/ or run.py.
- **GitHub:** `gh api repos/Alex-lop/Graphene` → 0 ★, 0 forks, topics set (agent-orchestration, claude-code, …). Latest GitHub release v0.5.0. Traffic: 3 views from 3 uniques in 14 days.
- **Activity elsewhere, as commits since 18 Jul (first 100), last commit, latest release:**

  | Tool | Commits | Last commit | Latest release |
  |---|---|---|---|
  | opcode | 1 | 2026-09-18 | v0.2.0, 2025-08-31 |
  | claude-squad | 3 | 2026-08-20 | v1.0.20 |
  | vibe-kanban | 10 | 2026-09-19 | 2026-04-24 |
  | task-master | 0 | 2026-04-23 | |
  | sculptor | 100 | | v0.49.0rc1, 2026-10-19 |
  | jcode | 100 | | v0.99.0, 2026-10-19 |
  | herdr | 100 | | v0.9.5, 2026-10-14 |
