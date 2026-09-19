# Graphene: product thesis

Written 2026-09-18 by the strategist session, for Alex. It decides what Graphene is, and
`GRAPH_DIRECTIVE.md` builds it. Earlier directives, reports and the roadmap were treated as input
and argued with; where this document keeps one of their conclusions it says why.

How to read the evidence. A claim about the current tool cites the command that was run (tool
installed from `rebuild` @ `db587bc` into a fresh tool directory with
`UV_TOOL_DIR=… UV_TOOL_BIN_DIR=… uv tool install --force .`). A claim about a vendor capability
cites the official page, fetched on 2026-09-18. A claim about the market names the product and the
number seen that day. "Could not confirm" means exactly that, and nothing is designed on it.

## 0. The decision in one page

**Verdict: build the graph product, in three nights, with the record fixed first.** Not the
narrower text tool, and not the hackathon again. Night three (rules) starts only after Alex has run
the kill criterion in section 11 on the finished map.

Three findings decide it.

1. **`why` on its own has already been built by people with more money.** Entire ships
   `entire why <file>:<line>` ("Explain the commit, checkpoint, prompt, and session behind a file or
   line", `curl -sL https://docs.entire.io/llms.txt`), supports eight agents, has 5,105 stars and a
   $60M seed. git-ai (2,748 stars) does line attribution in git notes. The previous advisor's
   first law, "`why` is the product", describes a feature two funded teams reached first. It stays
   as a command. It cannot be the identity.
2. **The current tool is silently wrong in exactly the case Alex lives in.** On Nemisis, a repo
   built almost entirely by subagents, `graphene why` returned "no recorded prompt changed …" for
   the three most-committed source files (27, 24 and 15 commits). On this repo it credits
   `debrief.py` to one prompt where git shows 13 commits. The card for last night's release says
   11 files; `git diff --stat 3cc4a9f^ db587bc` says 40. Nothing on screen admits the gap. A
   sub-agent playing a first-time user, allowed the README only, concluded: install yes, keep
   conditionally, tell a colleague "not yet … I'd send it the day the coverage number ships."
3. **What is empty in the market is what a graph is good at.** Nobody shows which agent, under
   which task, changed which files, across worktrees, after the fact, with an honest count of what
   cannot be accounted for; nobody lets a person set a boundary on a picture of the repo and have it
   enforced. The live "graph of one session" is already a crowded spectacle (zoetrope 909 stars in a
   month, Agent Flow 1,650, Anthropic's own VS Code agent map since v2.1.269). Graphene does not win
   by being a fourth one. It wins by being the one whose picture includes the files, the commits
   and the unknown, and where rules attach.

So: **Graphene is the local map of what your coding agents did to your repo — every agent, task,
file, commit and check drawn from the records, with an honest count of what it cannot account for —
and the place where you set the boundaries the next run must obey.**

Time-sensitive, before anything else:

- **Do not push the `v0.1.0` tag and do not create the PyPI publisher for `graphene-debrief`.**
  The name describes a command this thesis demotes, PyPI names cannot be renamed, and 0.1.0 is
  silently incomplete for anyone who uses subagents (finding 2), which is the audience. Publish
  after the first night whose gate passes, as `graphene-map` (free on PyPI today:
  `curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/graphene-map/json` → 404).
- **Add `"cleanupPeriodDays": 365` to `~/.claude/settings.json` today.** The default is 30 days
  (https://code.claude.com/docs/en/claude-directory), and a researcher's read-only check found the
  key unset on this machine and the oldest transcript dated 2026-08-21: the sweep is about two days
  from deleting the first of the records Graphene reads. The builder is not allowed to edit that
  file; it is a one-line change.
- morning.md's `git merge --ff-only rebuild` will fail: `git rev-list --left-right --count
  main...rebuild` → `2 1`. The branches diverged by one docs commit. The directive handles it.

## 1. First-hand use

Done before reading any document, as the brief ordered, by me and then by a sub-agent who had never
seen the repo and was allowed the README only. Logs: the strategist's and the sub-agent's notes are
summarized here; every line below was checked against git.

### Where it was useful

- `graphene sessions` lists 27 sessions back to 2026-08-19 with prompt and call counts, with no
  setup. Git cannot tell you a run existed.
- `graphene debrief 155c08d3`: 83 files, zero commits, "29 tool failures", 66 files written to a
  scratch directory. That night is invisible to git entirely.
- The card's "Abandoned" block (four checks that failed and were rerun green; "26 tool failures … 2
  refused before running") and "Written outside the repo" are facts neither the diff nor the
  agent's own summary carries.
- `graphene why PATH:LINE` named the right commit in 6 of 6 checks against `git blame -L` and a
  prompt in 5 of 6. When it answers, it is right. Nothing it printed was fabricated.
- Live recording works: a failed Bash call of my own session appeared in `graphene debrief --json`
  seconds later with `"source": "hook"`.

### Where it was noise

- `graphene debrief 9e5f295d | wc -l` → 52 lines, 25 of them a commit list `git log` already gives.
- 7 of 27 rows in `graphene sessions` are sessions with zero calls.
- Every `why` answer on this repo quotes the same sentence, "Please implement :
  REBUILD_DIRECTIVE.md …". True, and useless: in directive-driven runs the prompt is too coarse to
  be a reason. The finer records exist and are unused: each subagent's task `description` (in
  `<session>/subagents/agent-<id>.meta.json` and in the parent's `Agent` call), the agent's commit
  messages, Workflow phase names and labels.
- Timestamps are UTC and do not say so (01:17 shown at 21:17 local).

### Where it was wrong

| Command | It said | Git says |
| --- | --- | --- |
| `graphene` in Nemisis (215 commits of agent work) | "1 session, 1 prompt, no file changes recorded" | the latest session is an empty one; the default unit is wrong |
| `graphene why src/nemisis/crashcheck.py`, `cli.py`, `report.py` | "no recorded prompt changed …" ×3 | 27, 24, 15 commits, inside recorded sessions |
| `graphene why src/graphene_debrief/debrief.py` | 1 prompt, "created +845" | 13 commits; 845 is today's size, credited to the first prompt |
| `graphene why src/graphene_debrief/cli.py` | 2 prompts, both 09-17 | eleven more commits on 09-18 (`git log --date=short -- src/graphene_debrief/cli.py \| grep -c 2026-09-18`) |
| `graphene debrief 9e5f295d` | 11 files (+1740/−468) | 40 files, +3652/−349 |
| `graphene debrief 0dc016bf` (Nemisis, 27 h, 7,810 calls, 40 commits) | 9 files (+134/−12), five of them scratch deletions | 40 commits; the work ran in worktrees and through the shell |
| `graphene why README.md:10` | the same change (+87/−41) credited to two sessions, and (+83/−97) to two others | double counting across overlapping sessions |
| `graphene debrief 0dc016bf --full`, prompt 3 | `OVERVIEW.md … [unrequested]` | the prompt asked for that file |

Tallies against `git log --follow` and `git blame -L`, kept separate because the two testers
overlapped on some files. The sub-agent: 14 `why PATH` answers → 4 right and complete, 6
incomplete, 4 empty when they should not be; 6 `why PATH:LINE` → 6 right commits. Mine: 7
`why PATH` → 0 complete, 3 incomplete, 3 empty, 1 with a wrong count (`debrief.py`); 3
`why PATH:LINE` → 1 right, 1 doubtful (a bare `break` matched by text), 1 double-counted
(`README.md:10`). Wrong prompt named for a change it did report: 0 for both of us.

### The cause, checked in the store rather than guessed

My first guess (that subagent transcripts are not read) was wrong, and I told Alex so mid-run; my
second (that it is nearly all worktrees) was half wrong, and the fact-checker caught it. What the
stores say:

- Subagents are ingested. In Nemisis's store, `select count(*), sum(agent_id is not null),
  count(distinct agent_id) from tool_events` → 21,396 events, 19,349 from subagents, 925 agents
  (460 in the largest session). Nothing stores which agent spawned which, or what each was asked.
- **Worktrees are hidden, not attributed.** Of 573 `Edit`/`Write` events there, 77 are under
  `.claude/worktrees/agent-*/` and 44 under a scratchpad worktree; `attribute.py`'s nested-checkout
  rule files every one under "outside the repo". Last night's release fix hid worktree work rather
  than attributing it. Mapping those paths recovers about a fifth of the edits. (Another 425 are in
  throwaway sandboxes under `/private/tmp` that are not the repo at all, and rightly stay outside.)
- **Most source changes never passed through `Edit` or `Write`.** `report.py` (15 commits) has no
  `Edit`/`Write` record anywhere; `crashcheck.py` (27 commits) has one. The release session's main
  transcript holds 147 `Bash`, 16 `Agent`, 5 `Read` and **zero** `Edit`/`Write` calls; 68 of those
  Bash calls carry a heredoc. The shell parser recognises a write in 5.9% of stored Bash commands
  (835 of 14,051) and a repo-relative one in 1.7%.
- **Discovery misses sessions.** Transcripts are found by the repo's path prefix, so a session whose
  working directory was a worktree outside the repo lives in a project folder that is never
  scanned; and the store keeps no `cwd` per event, so 490 relative paths cannot be resolved.
- The vendor now records shell changes itself: 33 transcripts on this machine (all since
  2026-09-14) carry `bashEditDiff` objects, 260 of them, 227 already in this repo's store and unread.

Each hole has records that close it, fully or partly (section 9). A dry run against the real data
says what is reachable: last night's session goes from 11 of 40 committed files to 40 of 40 (22 by
recorded edit, 18 by the vendor's shell-change list); Nemisis's big session, which predates that
list, reaches about 70%, of which 12 files only at the level "this agent made the commit". That is
the honest ceiling for old sessions, and the map must show it as such. This is the prerequisite for
any picture.

## 2. Who

The developer who delegates in bulk. They run Claude Code with subagents, worktrees or Workflow
fan-outs, often unattended or in parallel, and come back to tens of commits they did not watch being
made. You can find them in r/ClaudeCode and the Claude Developers Discord, in Hacker News threads
about parallel agents, and among the users of claude-squad (8,497 stars), Vibe Kanban (28,125) and
Conductor. Alex is one: across the 52 top-level transcripts on this machine, 23 sessions call
`Workflow` and 12 call `Agent`; one Nemisis session has 460 agents. He also runs Codex: 628 rollout
files (2.3 GB, July to September) sit under `~/.codex/sessions`. The same person, two vendors, one
repo.

What they do today when they come back: read the agent's closing summary or its `morning.md`, skim
`git log`, spot-check a few diffs, and trust the rest. The closing summary is the real competitor. It
is a self-report by the party being checked.

What they would stop doing if Graphene worked: taking the agent's own account as the only account,
and rebuilding "which agent did this" by hand from `git log --since/--until`.

Who it is not for, in this phase: teams wanting compliance reporting (Anthropic's Compliance API
and Datadog's Agent Console sell that, hosted), and people who run one attended session at a time
(the transcript and `/rewind` serve them).

**Decision:** one person, the bulk delegator on Claude Code. Every screen is judged by whether it
helps that person the morning after.

## 3. The moment

Ranked by how much the person needs help and how little anyone else gives it.

1. **Coming back after a run has stopped, before merging or pushing.** Nothing else serves this:
   vendor views are live-only, the diff has no agents in it, and the summary is a self-report. This
   decides the default screen: the latest run that did something, fully replayed, with coverage.
2. **While it runs**, as a glance: what is each agent doing, have two met on one file, did a rule
   fire. Same screen with the scrubber pinned to now. It is second because the person watching needs
   less help than the person who was away, and because vendors own this moment (the agent map).
   It is still the launch asset, because motion is what gets shared.
3. **Before the next run**: set boundaries because of what the last run showed. Rules are made on
   the same screen, on the thing they are about.
4. **A week later, something breaks**: `graphene why PATH:LINE` in the terminal, where the person
   already is.
5. **A teammate asks**: a static export of the map. Last, and conservative: Amp removed public
   thread sharing because agents read too many files for a shared thread to be safe
   (ampcode.com/news/end-of-public-threads), so the export carries paths, counts and task text,
   never file bodies or tool output.

**Decision:** the default screen is the come-back view of the latest non-empty run. Live is the same
view, not a second one.

## 4. The three questions

Each is something the transcript, the diff and the vendor's interface cannot answer quickly, with an
example from section 1.

**Q1. Who did what?** Which agent, asked to do what, in which worktree, changed which files, and in
which commits did that land. Example: Nemisis session `0dc016bf`, 27 hours, 7,810 calls, 460
subagents (the repo's eight sessions hold 958 subagent transcript files:
`find … -path '*subagents*' -name '*.jsonl' | wc -l`). The diff has no
agents in it. Anthropic's agent map shows agents only while the session is open in VS Code, and no
files. The tester's unanswered question was this one: "which subagent wrote `sqlite_runner.py`'s
checkpoint change, and what was it told?"

**Q2. How much of this is accounted for?** Of the files this run's commits changed, how many trace
to a recorded action, by what kind of evidence, and what is left. Example: the release card's 11
files against git's 40, with no caveat. No tool in the market scan shows unknown provenance as
unknown. This is the question that makes every other answer trustworthy, and the one the tester
made a condition of recommending the tool.

**Q3. What happened that the diff hides?** Work tried and abandoned, checks that failed and whether
they were rerun green, calls refused, writes outside the repo, two agents on one file, rules that
fired. Example: session `155c08d3`, 83 files and zero commits; the release session's four
failed-then-green checks and two refused calls.

`graphene why` remains the terminal door into Q1 for one line. It must be right, and it is no longer
the headline.

## 5. Why a graph

### The case for, weighed

- *Multi-agent work is graph-shaped.* True on this machine (460 agents in one session; spawn depth
  in `meta.json`; Workflow phases). Accepted.
- *Visual tools spread and text tools do not.* Mixed. zoetrope reached 909 stars in a month and
  Agent Flow 1,650, but the plain transcript viewers sit at the same level
  (simonw/claude-code-transcripts 1,692, claude-code-viewer 1,288), and Agent Flow's Show HN got 5
  points, where the praised feature was the file heatmap, not the graph. Unvalidated, not refuted.
  Graphene has zero stars, so distribution matters more than it did to the previous advisor, and a
  moving picture is the only launch asset this product can have. Accepted as a bet, listed as one.
- *Rules drawn on the graph can be enforced through hooks.* Confirmed against the docs (section 7).
  Accepted.
- *The graph is a new surface on the same store and hook.* Half true. It needs new ingestion
  (agents, worktrees, shell changes, commits). That work is owed anyway (section 1).

### The case against, point by point

**(a) An editable node the agent ignores destroys trust in one click.** Defeated by design. Nothing
on the map is editable except rules and notes. A rule is evaluated by Graphene's own hook and its
state on screen is derived from records: *armed* (the hook has seen events from this session),
*fired* (n denials, each a node), *breached* (a protected path changed through a route the hook
could not stop; shown red, never hidden). A note is labelled a note and shows its delivery receipt.
There is no plan editing, no drag-to-assign, no approve button.

**(b) Vendors ship their own loops and dashboards; a graph that re-renders their data competes on
their turf.** Accepted as the largest risk, not defeated. Anthropic's VS Code agent map (added in
v2.1.269 together with the Hooks and Permission rules dialogs,
raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md) already has per-agent cards,
Stop, and transcripts; 2.1.275 improved it and 2.1.277, the current release, put background shells
into it. Five changelog entries between 2.1.269 and 2.1.277: it is moving. What it does not do
today: anything after the session closes, anything outside VS Code, files, commits, coverage,
history across sessions, rules placed on the repo's own structure, or another vendor's agents. That
last one is structural: Anthropic will not draw Codex. Signal that the risk is materializing: a
changelog entry putting files or past sessions into the agent map, or shipping it in the CLI or
desktop app. Response if it does: Graphene narrows to coverage, cross-session history and the
second source, which is why that source moved up to night three (section 9). Check the changelog
on every release, not monthly (`grep -n -i 'agent map' CHANGELOG.md`).

**(c) A web frontend is a second codebase, and the hackathon died of surface area.** The
post-mortem says the hackathon died of surface outrunning proof: 137,331 lines of Python, a 531 s
suite, four graph renderers with no shared model, and the one experiment that would have justified
any of them (`docs/GRAPH_NECESSITY_EVAL.md`, "Status: NOT YET RUN") never run. The defence is
structural: every position, group, overlap and coverage number is computed in Python and tested in
pytest; the page is a renderer with a line cap; there is one renderer, and the HTML timeline is
deleted the day the map replaces it; no server beyond a localhost stdlib process; and the kill
criterion (section 11) is written before the code.

**(d) Many sessions are one prompt, and the graph of one prompt is a star.** Defeated by choosing
the right middle layer. Between the prompt and the files sit the agent's own recorded units of
work: subagent tasks, Workflow phases, task-list items where they exist, and commits, whose
messages the agent wrote. The release session is one prompt, and also 16 subagents and 24 commits.
A session with one prompt, no subagents and forty files draws as one lane of work split at its
commits, over directory blocks: a timeline with structure, not a star. And the layout chosen below
has no centre for a star to form around.

**(e) Attribution is incomplete, and a graph on incomplete records lies more visibly than a line of
text.** Turned around: the text lies *less* visibly, which is worse (the tester: "confident silence
is worse than an error"). The map makes incompleteness a first-class thing on screen. Every link
carries its evidence grade, the header carries the coverage count, and unaccounted files are drawn
as a labelled block. The attribution fixes come first, before the map draws any real data.

### Decision

The graph is the main surface, and it is a **time-lane map with deterministic layout**, not a
force-directed node-link diagram. Alex should hear this plainly: if the picture in mind is a web of
file bubbles, that is the version the tester said would make them "close it in ten seconds", and the
one file-graph in the scan (claude-code-graph) has 4 stars. A lane map is still a graph: typed
nodes, typed links, grouped nodes, selection that traces a chain. It adds two axes that mean
something, and that is why it can be read at 500 nodes and tailed live without anything moving.

## 6. What kind of graph

### Layout

Time runs left to right. Long idle gaps are compressed to a fixed-width break mark so a twelve-hour
night fits a screen (computed in Python; the break shows the real duration).

- **Top: agent lanes.** Lane 0 is the main agent. Subagents sit under their parent, grouped by
  Workflow run and phase when those records exist. A group is collapsed by default into one lane
  showing its count and activity; it expands in place. On a lane: work steps (bursts of edits),
  checks (pass or fail), commits, failures, rule firings. A spawn link drops from the parent's
  `Agent` call to the child's first step, and a return link rises when it stops, like a git graph.
  This is the part that moves in the recording.
- **Middle, when recorded: the agent's own list.** `TaskCreate`/`TaskUpdate` items as a read-only
  strip whose marks show created, started, done. Captioned "the agent's own list". It is rare (2 of
  52 sessions here) and will stay rare: the changelog says the to-do tools are switched off by
  default on current models (`CLAUDE_CODE_ENABLE_TODO_TOOLS=1` restores them), and there are 0
  `TodoWrite` calls across the 52 top-level and 2,046 subagent transcripts on this machine. So it
  is drawn only when present and nothing depends on it.
- **Bottom: the repo.** Rows are directories, collapsed by default with a count, in order of first
  appearance in the run (so a new one is added at the bottom and nothing above it moves); a
  directory expands to file rows. A mark at (time, row) is a change, coloured by agent and shaped
  by evidence grade. Two agents marking one row within overlapping windows light the row: that is a
  collision, from records alone.
- **Links between lanes and rows are drawn on selection only.** Select an agent and its marks light
  across the repo rows; select a file and the agents, commits and rules that touch it light up.
  Drawing every link at once is the hairball.
- **Right: the inspector.** For an agent: what it was asked (the task text), type, worktree, span,
  files, commits, checks, its closing message. For a file: its history across sessions (this is
  `why`), hunks where recorded, evidence per change. For a directory: its rules, and "add a rule".
  For a commit: files, and which of them are accounted for. Every fact names its record. At the
  top of the inspector the selection's **chain** is drawn as a small node-link diagram in fixed
  columns (task → agent → files → commits → checks and rules): the part of the product that looks
  like the word "graph", and it is the supporting chain of one thing, never the whole repo.
- **Header:** the run in one line, the coverage bar ("31 of 40 committed files accounted for"), and
  counters that act as filters: abandoned, failed checks, refused calls, outside the repo,
  collisions, rule firings.
- **Footer:** the scrubber. Replay is a cut on the time axis; live is the scrubber pinned right.
- **Left rail:** runs, newest first, empty sessions hidden, each with duration, agents, files and
  coverage. Sessions that overlapped in time can be selected together and share one axis, which is
  how collisions between separate sessions in one checkout become visible.

### Node and link types, each backed by a record

| Node | Record |
| --- | --- |
| session, prompt | transcript / `SessionStart`, `UserPromptSubmit` events |
| agent | `agent_id` on events; `meta.json` (`description`, `agentType`, `toolUseId`, `spawnDepth`); parent `Agent` call; `SubagentStart`/`SubagentStop` |
| workflow group, phase | `subagents/workflows/wf_<id>/journal.jsonl` (`label`, `phase`) |
| task item | `TaskCreate`/`TaskUpdate` calls |
| step | consecutive tool events of one agent (a display bucket, labelled as such) |
| file, directory | tool event paths, `bashEditDiff.changedFiles`, git |
| commit | git, tied to an agent by the recorded `git commit` call whose output names the SHA |
| check | recognised test and lint commands with their result |
| rule, rule firing, note delivery | the rules file a person wrote; the hook's own log of what it returned |
| unknown | files changed by commits in the run's window with no record at all |

Evidence grades, drawn as mark shape and spelled out in the inspector: **edit** (tool payload),
**shell** (vendor-reported change list for a Bash call), **commit** (the agent's recorded commit
contains the file, no write recorded), **window** (committed during the session by no identifiable
agent), **unknown**. Nothing inferred is drawn as fact, and the permanent caption from the hackathon
survives because it was right: layout and timing do not imply causality.

### The two first screens

- **One prompt, forty files, no subagents.** One lane, split at commits, each segment titled with
  the commit subject; eight to twelve directory rows with counts; coverage in the header. No centre,
  no star.
- **A repo with ten sessions.** The rail lists them; the latest non-empty one is open at full
  replay. Above the fold without a click: what ran, how much is accounted for, what the diff hides.

At 300 to 500 nodes it stays readable because groups start collapsed, links are on demand, and
off-screen marks are not rendered. Past that the projection is bounded the way the hackathon's was
(a cap, with a visible "n more, zoom in or filter" count that must agree with the data).

## 7. What "collaboration" concretely means

Five interactions, each true by mechanism, each with its limit printed in its own panel. All doc references are to
https://code.claude.com/docs/en/hooks unless stated.

**1. Protect.** Select a directory or file → "agents may not change this" (or "ask me first").
*Mechanism, in three layers, and the panel names which are in force:*
(i) Graphene's `PreToolUse` hook returns `permissionDecision: "deny"` (or `"ask"`) with a reason;
for deny the reason is "shown to Claude". Hooks "also run inside subagents" with `agent_id`, run
before permission rules are evaluated (permissions page), and see `tool_input.file_path` already
made absolute (a path matcher cannot be dodged by re-spelling the path with `~` or a relative
form). A protected path covers its copies in the repo's worktrees through the same mapping that
fixes attribution. This layer is the one that leaves a record of every attempt and says why.
(ii) The same rule written as an `Edit(path)` deny rule into `.claude/settings.local.json`, the file
`graphene init` already writes. "Deny rules block in every mode, including bypassPermissions", they
cover the file tools and the file commands Claude Code recognises in Bash (`sed`, `tee`, `>`
redirections), and settings edits apply "to the running session without a restart". This layer
holds when Graphene's hook times out (a timed-out `PreToolUse` hook fails open) or is not running.
(iii) If the person has the sandbox enabled, the path is added to `sandbox.filesystem.denyWrite`,
"enforced at the OS level … including their child processes": the only layer that stops a Python
script from opening the file itself. Graphene never turns the sandbox on; it uses it when it is on.
*Known hole, shown not hidden:* without the sandbox, "arbitrary subprocesses … like a Python or
Node script that opens files itself" are not stopped by (i) or (ii). So after every Bash call the
`PostToolUse` hook reads `tool_response.bashEditDiff` (the vendor's list of files a Bash command
changed; recorded in auto and bypass modes by default, elsewhere only with the user-level setting
`bashEditDiffEnabled`; git-ignored files and anything past 200 files are not listed; "best effort
and in public beta … not to enforce a policy", so it is used to *detect*, never to promise). A
protected path that changed is recorded as a **breach**, and the hook returns `decision: "block"`
with the reason and the restore command. *The interface shows:* which layers are in force; armed /
fired n times / breached at a time by an agent via shell, restored yes or no; and one fixed line,
"cannot stop a script that writes the file directly unless the sandbox is on".

**2. Finish gate.** Select a check → "don't finish while this is failing or stale". *Mechanism:*
the `Stop` hook returns `decision: "block"` with a reason built from Graphene's own record ("the
last recorded run of `uv run pytest -q` failed at 02:10", or "has not run since `src/x.py` changed
at 02:14"). Graphene does not run the check; it reads what the agent ran. It honours
`stop_hook_active` and gives up after two blocks of its own (the vendor caps at 8), recording
"stopped with a failing check". *The interface shows:* gate fired → check rerun → passed → stopped,
as four marks on the lane. The vendor's `/goal` is a model-judged version of this; Graphene's is
deterministic and leaves a record.

**3. Note.** Pin a sentence to a file or directory. *Mechanism:* `additionalContext` returned from
`PreToolUse`/`PostToolUse` when an agent next touches that path ("inserts it into the conversation
at the point where the hook fired … next to the tool result"), or from `SessionStart` and
`SubagentStart` for repo-wide notes. The docs warn that imperative text "can trigger Claude's
prompt-injection defenses", so the form asks for a fact ("this module is being replaced by
`new_api/`"), not an order. *Labelled:* "a note, the agent may ignore it". *The interface shows:*
waiting, or delivered at 02:14 to agent X on `Edit src/x.py`; the injected text is also "saved in
the session transcript", so delivery can be checked twice.

**4. Stop.** A button on a running session. *Mechanism:* at that session's next hook event the hook
returns `{"continue": false, "stopReason": "…"}`: "Claude stops processing entirely … takes
precedence over any event-specific decision fields". The request is scoped to one session id and
expires in ten minutes so it can never kill a later run. *The interface shows* three times from its own records (requested,
delivered on which event, session ended). Stopping a single subagent:
could not confirm what `continue: false` does inside one, so it is not offered until the builder
has tested it. It is the lowest priority of the five: the vendor's VS Code map already has Stop.

**5. One writer at a time** (set on a directory; build last, drop first). While one agent has
written a file through `Edit` or `Write` and has not stopped, another agent's `Edit` or `Write` to
the same file in the same checkout is denied with a reason naming the first agent and its task.
*Mechanism:* the `PreToolUse` deny above plus one atomic insert into the store (the hook blocks the
call until it returns, so there is no race on the tool path); the claim ends on the first agent's
`SubagentStop` or after a quiet period. This is the one interaction that exists only because
Graphene sees every agent at once. *Limits, printed in its panel:* it does not cover shell writes
(those still show as a collision), and agents in separate worktrees are editing separate copies, so
it matters for agents and sessions sharing one checkout. I rejected this in the first draft as
timing-dependent; the ambition red team showed the tool path is not, and it is back, last in line.

A rule takes effect on a running session at once, because Graphene's hook reads the rules file on
every call; this does not depend on Claude Code reloading anything (it does also reload settings
live, settings page: "applies most edits to the running session without a restart, including edits
to `permissions`, `hooks`").

**Rejected, because they cannot be made true:** editing or reordering the agent's task list (no
hook output can; `TaskCreated` can only cancel a task); pausing (`defer` works only under `-p`;
interactive sessions "ignore the hook result"); assigning work or starting agents (law 1); approving
or rejecting a change from the map (that is git's job and was the hackathon's product). Considered
and deferred: posting a message into a live session through the vendor's cross-session messaging
(a truer "say something now" than a hook note, but held for approval in the unattended modes, and
it gives an idle session a new turn, which is starting an agent: law 1).

One honest unknown: the docs never say outright that hooks run under `bypassPermissions`. The
evidence is indirect (`permission_mode` can be `"bypassPermissions"` in hook input; `bashEditDiff`
is delivered to `PostToolUse` in that mode). So "armed" is never assumed from configuration; it is
shown only after the hook has seen an event from that session.

## 8. What to cut

| Today | Decision | Why |
| --- | --- | --- |
| `graphene` (card) | keep; default unit becomes the latest run that did something; prints coverage; commit list capped at 5 in every form | it is the come-back glance in a terminal, and it was blank in both repos |
| `graphene why` | keep | verified: 6 of 6 on lines; it is the in-flow command; gains agent, task and evidence grade |
| `graphene ui` | **new** | the surface; `--export FILE` writes the static page (paths, counts and task text; no file bodies) |
| `graphene sessions` | keep | the tester's most useful moment; hides empty sessions by default |
| `graphene init` | keep, promoted to the install step | durability and rules both need hooks (section 9) |
| `debrief` | hidden alias of the card for one release, then gone | the map is the full view |
| `--full`, `--md` | cut | the map; piping already gives markdown |
| `--json` | keep, on `graphene` and `graphene ui` | the same contract the page consumes |
| `--html`, `export_html.py`, `templates/record.html` (558 lines) | cut, replaced by `graphene ui --export` | one renderer |
| `--explain`, `--model`, `explain.py` (224 lines) | cut; the `explanations` table stays in the schema, because the store never drops a table again | a model's sentence next to facts is an inference shown as fact (law 2), it costs money, and the agent's own task text and commit messages are better and are records |
| `ingest` | hidden | it is the hook's entry point, not a user command |

Visible commands: `graphene`, `graphene ui`, `graphene why`, `graphene sessions`, `graphene init`.
The previous law "no new subcommands" is overruled once, for `ui`.

## 9. Technical decisions

**Frontend: a small build. React, TypeScript, Vite; SVG rendering; d3-zoom for pan and zoom; no
graph library.** Criteria and reasoning: the layout is data (positions come out of Python), so the
two things a graph library sells, layout and dragging, are things this design must not have.
Against the brief's list: custom node rendering (SVG marks and HTML inspector, trivial), grouped
nodes (row ranges and lane groups, drawn by us), stable incremental layout (by construction:
`f(record) → (x, y)`: an existing mark's x never changes, and with groups and directories
collapsed, the default, neither does its y), pan and zoom (d3-zoom with d3-selection, 7.4 KB gzip), selection
and multi-selection (ours, ~80 lines; keyboard movement along a lane is index arithmetic on sorted
coordinates, which answers the researcher's "long tail" argument for a library), 500 nodes (SVG with off-screen culling on a sorted x), regions
(a directory is a contiguous row range, so selecting a region is selecting rows). The build step
earns its place through `tsc --noEmit` as an acceptance gate on 1,500 lines written unattended, and
through real DOM selectors for Playwright. Built assets are committed under
`src/graphene_debrief/ui/static/` (not `dist/`, which `.gitignore` excludes), ship in the wheel with no
config change, need no Node at install or run time, and CI fails if `npm run build` changes them.
*Runner-up:* `@xyflow/react` 12.11 (MIT, 132 KB with React) if the design ever moves to free-form
cards; it never computes layout, which suits us, but its value is dragging and connecting, which we
forbid. *On Cytoscape, on merit:* its strengths are layout algorithms and canvas speed past 2,000
nodes; its nodes are canvas drawings that cannot carry rich text or be selected by a test. Wrong
tool for this picture regardless of history. *Traps found:* `@cosmograph/cosmos` is CC-BY-NC;
elkjs is EPL/GPL. *What would flip it:* a frontend budget under 600 lines → no-build vanilla with
d3-zoom; force layout as the default view or more than 2,000 visible nodes → Cytoscape.

**Live transport: server-sent events from a stdlib `ThreadingHTTPServer` on 127.0.0.1.** The server
loop sleeps 250 ms, reads `PRAGMA data_version` (measured 1.4 µs per call on this repo's 17k-row WAL store,
and it does change when another connection commits), and streams rows past the client's
`Last-Event-ID`; `EventSource` reconnects by itself. The same endpoint answers a plain poll as the
fallback. **The hook never talks to the server**: it writes SQLite and exits, so nothing the page
does can touch the hook's budget. That budget is a documentation claim today (measured by the code
reader at 30 ms warm, 680 ms cold; no test enforces it), so the directive adds a measuring test.
Because the page can now write rules and request a stop, the server binds loopback only, checks
`Host` and `Origin`, and requires a per-launch token on every write.

**Attribution fixes (night one, before the map draws real data).** (1) *Agents as records:* a
table of agent id, parent call, type, task text, working directory, Workflow run and phase, start,
end, closing message. Verified on real data: `meta.json`'s `toolUseId` matches the parent's `Agent`
call 16 of 16 times; Workflow agents carry no `toolUseId` and link through the `wf_<id>` directory
name, which equals the parent `Workflow` call's `runId`. (2) *Worktree mapping:* a path under a
worktree root maps to its repo-relative path. Roots come from `git worktree list --porcelain` while
the worktree exists and from each subagent transcript's recorded `cwd` after it is gone (on every
one of 48,124 records checked; the docs warn `cwd` follows a `cd`, so a root is accepted only when
the mapped path exists in the repo's history). `gitBranch` is never used: concurrent agents
contaminate it (one agent's file shows four branch names). (3) *Discovery by identity:* also scan
project folders whose recorded `cwd` is a worktree of this repo, wherever it sits; store `cwd` per
event. (4) *Shell changes:* `bashEditDiff` from `PostToolUse` and from transcripts, including its
`moreFiles` count of what it left out. (5) *Commits as records:* a commit belongs to the agent whose
recorded Bash call ran `git commit` and whose output first printed the SHA (agents here commit with
`-q` and print `git log --oneline` after, so match a 7 to 40 character prefix anywhere in the
response); a recorded `git cherry-pick` ties the new commit to its origin. Patch-id matching was
tested and **fails on exactly the conflicted picks**, so it is not used. (6) *Coverage as three
counts, never one number:* of the files in the run's commits, how many trace to a recorded write (`edit`
or `shell`), how many only to an agent's commit, how many to nothing. The not-viable red team was
right that a single percentage that counts "the agent committed it" is close to a tautology.
(7) One change is credited to one session.

**Second source: Codex CLI, read-only, on night three as a parallel track.** Audience per line is
excellent: `@openai/codex` had 20.5M npm downloads last week against Claude Code's 12.3M; its
rollout files carry structural diffs (`FileChange` with `unified_diff`) and explicit `turn_id`s;
250 to 300 lines plus about 40 in `attribute.py`. The first draft pushed this to a later directive,
"once the first source is right". The ambition red team's objection stands: the thesis names
Anthropic's map as the largest risk and cross-vendor as the one structural defence, and Alex
himself has 628 Codex rollouts on this machine. One map with Claude's and Codex's agents on the
same repo is a picture neither vendor will ever ship. It still does not go in night one or two,
because the record and the map must be right for one source before a second is drawn on them; it
runs beside the rules on night three, in its own files, and can slip to night four without
touching anything else. The contract carries a `source` field from night one.

**Durability: yes, `graphene init` becomes the install step, and the store stops being
disposable.** Transcripts are swept at 30 days by default; hooks see what transcripts do not
(`bashEditDiff`, `cwd`, exact prompt ids, `SubagentStart`/`Stop`); rules need hooks. Today a schema
change moves the store aside and rebuilds from transcripts, which loses any session whose
transcript is gone. That becomes additive migrations. The store also stops keeping what it never
uses: `Read` events (10.5 MB of the 73 MB here) and Bash output beyond its head and tail (40.6 MB;
the tail must stay, because that is where the commit SHA is printed), which is also a privacy
improvement. `bashEditDiffEnabled` can only be set in user or managed settings (settings
reference), so `graphene init` cannot set it; it is on by default in auto and bypass modes, and
`init` prints the one line for people who run attended.

## 10. The name

- Distribution: **`graphene-map`** (free today). `graphene` on PyPI is the GraphQL library; it
  ships no console script (`unzip -l graphene-3.4.3-py2.py3-none-any.whl | grep entry_points` →
  nothing), so the command does not collide.
- Command: **`graphene`**, unchanged.
- Import package: stays `graphene_debrief`. Renaming it buys nothing a user sees, and it would
  break `why` on every file it moves until rename-following lands. A distribution whose import name
  differs is ordinary (Pillow, PyYAML).
- One line: **"See what your coding agents did to your repo: a local, replayable map of agents,
  files, commits and checks, built from Claude Code's own records."** After night three it gains
  "…and set the rules the next run must obey."

## 11. Viability, honestly

### Why this fails (most likely first)

1. **Anthropic finishes the job.** The agent map gains files and history, or moves into the CLI and
   desktop app. Most of the live half of Graphene becomes redundant within a release cycle.
2. **The record cannot be made complete enough.** Agents keep inventing ways to write files.
   If coverage on real overnight runs sits at 60%, the honest map is mostly a grey block and the
   product is a disclaimer.
3. **Nobody opens a local page.** The person comes back, reads the agent's summary, and merges.
   Graphene's moment lasts ninety seconds and a browser tab may be one step too many; the card has
   to pull them in.
4. **The picture is admired and not used.** Stars from the recording, no retention. zoetrope's
   numbers may be this already.
5. **The format breaks.** The transcript format is "internal and not a stable public contract"
   (claude-directory page). Hooks are the documented path, which is another reason `init` becomes
   the default, but backfill of past sessions will break on some release.

Entire is not on this list as a killer: it competes on `why`, hosted storage and breadth of agents,
and it has no picture of a run and no rules. It is on the list of reasons `why` cannot be the
identity.

### What must be true, and how each gets tested with the first users

| Assumption | Test |
| --- | --- |
| On runs recorded from now on (hooks installed, vendor shell-change lists present), nearly every committed file traces to a recorded write; on old sessions about 70% trace to something | dry run on real data: last night's session 40 of 40 (22 edit, 18 shell); Nemisis `0dc016bf` 60 of 86, 12 of those commit-only. Night one reproduces or explains these; the three counts print on every card, so every user reports them for free |
| The map answers Q1–Q3 faster than the terminal does | **the kill criterion, run before launch:** five real come-back questions (from section 1), three people, map against `graphene` + `why` + `git log`, timed. If the map loses on three of five, it becomes an inspector behind the card, and Alex is told so. The hackathon wrote this experiment and never ran it |
| Bulk delegators exist in number and have this problem | the launch post targets them with the recording and a click-before-install demo (the synthetic run's export, a static file). Goal for the first month: 1,000 installs and 50 people posting their card's coverage line in a pinned Discussion. Minimum signal worth continuing on: 25 |
| People come back to it | second-week use among those 25, asked directly (no telemetry, law 4) |
| Rules placed on the map get set and kept | after night three: how many of those users have one rule armed after a week |

### Verdict

**Build the graph product as designed, in three nights.** Night one: the truthful record and the
first map you can open (static, real data). Night two: live, the design bar, walkthroughs, the
recording; it ends publishable. Then Alex runs the kill criterion, ten minutes, before anything
else is built on top. Night three: the rules, and Codex beside them. The first draft said two
nights; the directive auditor and a builder dry run against the real code both put night one's end
at the first static map, so the plan says so instead of pretending.

Not "narrower first": the narrow product is the one Entire already sells, and the fix the record
needs produces the map's data as a by-product. Not "the bravest version" either: no plan editing,
nothing that wakes or starts an agent, nothing from the hackathon tag.

If the kill criterion fails, the working `why` and the coverage-bearing card remain a good small
tool, and the right move is to publish that, write up the attribution method (worktrees, shell
changes, cherry-picks: no tool in the scan handles them), keep the map as an inspector behind the
card, and stop building surface.

## 12. Market scan (2026-09-18)

| Product | What it does | Graph? | Line → prompt? | Subagents / worktrees | Local | Signal |
| --- | --- | --- | --- | --- | --- | --- |
| Entire CLI | captures sessions into git refs; `why`, `blame`, `recap`; 8 agents | no (its "graph" is a code index) | **yes** | limited, unconfirmed | CLI local, dashboard hosted | 5,105★, $60M seed |
| git-ai | AI line attribution in git notes, survives rebase | no | which model and session, less which request | no | yes | 2,748★ |
| Agent Trace (Cursor RFC) | a format for line-range attribution | — | the spec for it | — | — | repo returned 404 today |
| zoetrope | live flow graph of one session, replay, terminal | **yes**, agents only | no | agents yes, files no | yes | 909★ in a month |
| Agent Flow | VS Code live node graph, file heatmap | **yes** | no | agents yes | yes | 1,650★ |
| disler/…-multi-agent-observability | hooks → swim lanes, live | lanes | no | yes | yes | 1,540★, stale since Feb |
| claude-code-graph | prompts, subagents, files as a graph | **yes**, with files | no | yes | yes | 4★, dead |
| Claude Code agent map (VS Code) | live cards per subagent, Stop, transcripts; Hooks and Permission dialogs | list/map, live only | no | yes | yes | vendor |
| simonw/claude-code-transcripts, claude-code-viewer, claude-code-log | transcript → HTML | no | no | partial | yes | 1.2–1.7k★ each |
| Nimbalyst (was Crystal) | runner with a "Context Graph" of artifacts | yes, of artifacts | no | — | yes | 3,118★ |
| dcg, trailofbits config, karanb192/claude-code-hooks, hookify | text rules over PreToolUse | no | — | — | yes | 6,004★ / 2,115★ / 520★ |
| sandbox-runtime (Anthropic) | OS-level write limits for Bash | no | — | — | yes | 5,271★ |
| Datadog Agent Console, CloudWatch Coding Agent Insights, Compliance API | team-level spend, sessions, transcripts | Sankey at repo level | no | — | hosted | vendors |
| Vibe Kanban, claude-squad, Conductor | run parallel agents, list or board | no | no | worktrees to isolate, not to explain | yes | 28k★ (company shut down 2026-04-10), 8.5k★ |

What exists and is good: Entire for `why` across vendors; zoetrope and the agent map for watching
one session live; dcg for blocking dangerous shell commands. What nobody does: attribution of work
not written through `Edit`/`Write` (zero tools in the scan claim worktree handling); abandoned
work; provenance shown as unknown; a picture that joins agents to files and commits after the fact;
a boundary placed on that picture and enforced; collisions between live agents. Vibe Kanban's
shutdown note ("couldn't find a business model") is the honest ceiling: this is a tool people can
love and nobody may pay for. Alex's stated goal is a real product people use, and the thesis is
sized to that.

## 13. Red teams

Two adversarial sub-agents attacked the first draft of this thesis and the directive, with a fact
checker, a checklist auditor and a builder dry run beside them. What each side said, and what
survived.

### "Not viable; the graph is a vanity feature"

| Point | Answer |
| --- | --- |
| Coverage at grade `commit` is a tautology: every file in a Bash-made commit passes, so "90%" can be hit with `why` still wrong | **Accepted.** Coverage is now always three counts (traced to a recorded write / tied only to an agent's commit / unknown), the denominator is pinned to every path in the window's commits, and the 90% target is gone: the builder reproduces or explains the dry run's measured numbers |
| No user evidence, and the kill criterion is again scheduled after the build, which is the hackathon's cause of death no. 4 | **Partly accepted.** The map cannot be tested before it exists, but nothing should be built on it untested: night three now waits for Alex's ten-minute test, and a sub-agent stand-in runs inside night two. Publishing a 0.1.1 text tool first is rejected: that race is Entire's, with $60M |
| The plan does not fit the nights; budgets were overrun twice | **Accepted.** Three nights, a clock rule, bounded review loops, budgets restated with their arithmetic |
| Protect is bypassed by a heredoc, fails open on timeout, and sandbox-runtime already does it better; the finish gate can burn an unattended run; notes are "unverified context" | **Accepted as design changes.** Protect now writes the vendor's own deny rule and, where enabled, the sandbox's `denyWrite`, and says which layers are in force; every panel prints what the rule cannot do; the gate gives up after two blocks |
| It is not the graph Alex protected: at rest it is swim lanes, and the 909-star graph is a terminal app | **Partly accepted.** Spawn and return links are always drawn, so at rest it is a branching lane graph like a git graph, and selection now also draws the selected thing's chain as a small node-link diagram in the inspector (task → agent → files → commits → check), laid out deterministically. The substitution is stated at the top of the summary Alex reads. A free-form bubble graph stays rejected on the evidence in section 5 |
| Six factual errors | All six fixed (the agent map's version, "first-time user", the truncated `bashEditDiff` quote, an invented latency, an unfetched settings page, the target) |

Accepted as risks that cannot be answered: Anthropic finishing the job; nobody paying (Vibe Kanban,
28k stars, company closed); whether the vendor's shell-change list sees a git-ignored worktree.

### "The caution killed the ambition"

| Point | Answer |
| --- | --- |
| Lanes read as a trace waterfall; adopt a hybrid with a node-link neighbourhood on selection | **Adopted in deterministic form** (the chain diagram above). Force layout stays out: it is the one thing that cannot be tested in pytest or tailed without jitter |
| Codex is the only structural defence against Anthropic and costs 300 lines; deferring it is the old "one layer at a time" caution | **Adopted:** night three, parallel track. Alex's own 628 rollouts settled it |
| "One writer per file" was rejected as timing-dependent, and it is not, on the tool path | **Adopted** as the fifth interaction, last in line, with its limits printed |
| Protect is built on the weaker mechanism; deny rules hold in every mode and the sandbox stops child processes | **Adopted:** three layers |
| Ship as a Claude Code plugin so install is one command | **Rejected for now.** The hook still needs the `graphene` binary, and a user-level plugin would put a store in every repo the person opens. Per-repo `graphene init` stays; revisit after launch |
| Cross-session messaging is a truer "talk to the running agent" | **Deferred:** held for approval in unattended modes, and it wakes idle sessions (law 1) |
| 25 users is a timid target; publish a demo people can click | **Adopted:** 1,000 installs and 50 posted coverage lines; the synthetic run's export is committed as a static demo file |
| Task-completion gates | Rejected: the task tools are off by default on current models (2 of 52 sessions here) |

### What the dry run changed

The builder dry run read the real code and data and found what would have cost the night: the
ingest path flattens subagent records (so the agents table is the first commit, not a parallel
one); commit SHAs live in a response field the hook and the transcript name differently, and behind
`git commit -q`; the store keeps no `cwd`; `bashEditDiff` has a `moreFiles` truncation count the
first draft never mentioned; the "no mark ever moves" property was false as first written and is
now stated in the form that is true; and the first draft's rollback command contained a banned word.
