# Graphene graph directive — three nights, starting 2026-09-19

## You, tonight

You are the strongest agent available for this work, and there is no token budget. Use sub-agents
freely: for parallel milestones, for adversarial review, for walkthroughs. Spend tokens on evidence,
verification and the look of the page rather than on scope.

Alex is at school or asleep and will read `morning.md` in five minutes. Do not wait for input at any
point. Decide, record the decision in `morning.md`, continue.

This work takes three nights. A dry run against the real code put the end of night one at the first
map you can open, so that is where night one is planned to end, in a usable state.

- **Night one (N0–N4):** the truthful record, and the first map, static, on real data.
- **Night two (L1–L6):** live, the design bar, walkthroughs, the recording. Ends publishable.
- **Night three (R1–R5, C1):** rules on the map, and Codex beside them. **Starts only if Alex has
  filled in the kill-criterion line in `morning.md`** (see the contract at the end). If that line
  says the map lost, do the fallback in "Night three" instead.

Which night is it? Read `morning.md` and `git log`. Start at the first milestone that is not
committed. **Clock rule:** seven hours after you start, or at 07:00 local, whichever comes first,
stop starting new work and run the closing sequence of the night you are in (about 45 minutes). Do
not stop before that unless the night's plan is exhausted.

The reasoning behind every decision here is in `docs/PRODUCT_THESIS.md`. Read it. Where this file
and the thesis disagree, this file wins and you note the disagreement in `morning.md`.

## Why this exists

Alex lets agents run on his repos for hours: subagents, worktrees, Workflow fan-outs, overnight. He
comes back to tens of commits and the only account of what happened is the agent's own summary.
The current tool was meant to fix that and, used first-hand on 2026-09-18, it is silently wrong in
exactly his case: on Nemisis, `graphene why` said "no recorded prompt changed …" for the three
most-committed source files; here the release card said 11 files where git says 40; nothing on
screen admits the gap. Meanwhile `why` by itself has been shipped by funded teams (Entire's
`entire why <file>:<line>`, git-ai), and live pictures of one session exist (zoetrope, Agent Flow,
Anthropic's own VS Code agent map).

What nobody has built: a picture that joins agents to files and commits after the fact, across
worktrees, says honestly how much it cannot account for, and lets a person set boundaries on that
picture that the next run must obey. That is Graphene:

> The local map of what your coding agents did to your repo — every agent, task, file, commit and
> check drawn from the records, with an honest count of what it cannot account for — and the place
> where you set the boundaries the next run must obey.

The person it is for delegates in bulk and comes back the morning after. The map must answer three
questions for them faster than anything else can:

1. **Who did what?** Which agent, asked to do what, in which worktree, changed which files, landing
   in which commits.
2. **How much of this is accounted for?** Coverage, by evidence grade, and the rest drawn as
   unknown.
3. **What happened that the diff hides?** Abandoned work, failed checks, refused calls, writes
   outside the repo, two agents on one file, rules that fired.

## Laws that survive any decision

1. Graphene never runs or orchestrates agents. Agents run under their vendors' tools. Graphene
   observes, records, bounds and explains.
2. Every node, link and claim on screen comes from a record: a transcript, a hook event, git, or a
   rule a person wrote. Nothing inferred is displayed as fact.
3. Steering happens only through mechanisms that make it true: the vendor's permission rules and
   hooks. An interaction the agent can silently ignore is never offered as control; if offered at
   all it is labelled a note, and the interface shows whether it was delivered.
4. Local first. No cloud, no telemetry, no accounts. A shareable file or a local page, never a
   hosted service.
5. No claim without the command that shows it. Anything unverified is labelled unverified in the
   docs and in `morning.md`.

## Product law for this design

6. **The map is a time-lane map with positions computed in Python.** Time runs left to right; agents
   are lanes; the repo is rows grouped by directory, in order of first appearance. `f(record) →
   (x, y)` is a pure function tested in pytest. The guarantee, exactly: appending a later event
   never changes the x of an existing mark (a gap's compression is fixed when the gap closes), and
   with every group and directory collapsed, which is the default, never changes its y either (new
   lanes and new directory rows are added at the bottom). Expanding a group is the person's act and
   may move rows. There is no force layout, no layout library and no dragging of nodes, anywhere.
7. **Coverage is on every answer, and it is never one number.** Of the files changed by the commits
   in the run's window (every path in `git show --name-only` for every such commit; no exclusions,
   not lock files, not generated files): how many trace to a **recorded write** (`edit` or `shell`),
   how many only to **an agent's commit**, how many to **nothing** (a file whose only evidence is
   grade `window` counts as nothing, and the `window` subtotal is printed beside it). The card, the map header, `why`
   and the export all print it. An empty or partial answer says that it is partial.
8. **Every link has an evidence grade**, drawn as mark shape and spelled out in the inspector:
   `edit` (tool payload), `shell` (the vendor's change list for a Bash call), `commit` (the file is
   in a commit this agent is recorded making; no write recorded), `window` (committed during the
   session by no identifiable agent), `unknown`. The page carries the permanent caption: "Layout and
   timing do not imply causality."
9. **Nothing on the map is editable except rules and notes** (night three). No plan editing, no
   assigning work, no approve or reject, no pausing, nothing that wakes or starts an agent. The
   agent's own task list, where recorded, is shown read-only and captioned "the agent's own list".
10. **One renderer.** The HTML timeline is deleted in the commit that makes `graphene ui` work. The
    static export is the same page with the data inlined.
11. **The hook stays fail-open and fast**: exit 0 whatever happens, stdlib-only import path, 250 ms
    lock give-up, and it never talks to the UI server. It writes to stdout only when it has a
    decision or a note to return (night three). Its cost is measured by a test, not claimed.
12. **The server is a stdlib process on 127.0.0.1.** It checks `Host` and `Origin`, and every
    request that writes (night three) carries a per-launch token. No new Python runtime dependency:
    typer and rich remain the only two.
13. Deterministic attribution only. No model is called by the product, for anything.
14. The seven banned words stay banned in every tracked file, as whole words, in any case. They are
    listed in `RELEASE_DIRECTIVE.md` law 10 and in `STRATEGIST_BRIEF.md` under "How to work" (both
    untracked, in the main checkout's root; sub-agents in worktrees cannot see them, so give them
    the rule, not the file). This file does not spell them. Two traps: the usual word for a
    frontend build output is one of them (say "built assets"), and so is the last word of git's
    safer force-push flag (use plain `--force` in anything tracked).
15. Never commit anything derived from `~/.claude/projects` or `~/.codex`. Do not modify
    `~/.claude/settings.json`. Do not touch the `hackathon-2026` tag. Do not create or push a
    version tag. Do not publish to PyPI. Commits carry no attribution trailers and use the
    configured git identity. Other repos on this machine are read-only to you, except that running
    `graphene` inside one updates its own self-ignored `.graphene/` store.
16. **Nothing in the `hackathon-2026` tag is ported**: no code, no file, no node taxonomy. Two ideas
    from it are restated in this file (bounded projection with honest counts; the causality
    caption); that is all that survives.

## How to work

- First night only: `git fetch origin && git checkout -b graph origin/strategy && git merge
  --no-edit origin/main` (the merge is clean: `git diff c6ac90e origin/main` is empty; it makes
  `main` an ancestor so the gate's merge is trivial). Later nights: `git checkout graph`, or the
  branch named under that night. `main` is touched only by a gate.
- Read before acting, in this order: `docs/PRODUCT_THESIS.md`; `docs/HOW_IT_WORKS.md`; `README.md`;
  the reports in `docs/reports/`; then run `uv run pytest -q` and `uv run ruff check` and write down
  the baseline (2026-09-18: 158 passed in 8.6 s; lint clean). The transcript format and hook
  protocol are encoded in `src/graphene_debrief/sources/claude_code.py`; do not re-derive them.
  Vendor facts you need are in the thesis with their sources; if you need one that is not there,
  fetch the official page (`curl -sL https://code.claude.com/docs/en/hooks.md`; also `permissions`,
  `settings`, `settings-reference`, `sandboxing`, `sub-agents`) and cite it. If you cannot confirm a
  capability, do not build on it.
- Parallelize where files do not overlap (the plan says where). **A sub-agent gets a done-test, not
  a topic.** One integrator merges sub-agent work and runs the whole check suite before every
  commit. Worktree-isolated sub-agents are created from the repository's default branch, not from
  your HEAD: the first command in every such brief is `git switch -c <name> graph`, and the
  sub-agent confirms `git log -1 --format=%h` matches yours before it writes anything.
- Commit after every milestone. The message states what works and which test proves it. Before
  every commit: `uv run ruff check`, `uv run pytest -q`, and once `ui/` exists
  `npm --prefix ui run check` (typecheck, unit tests, build) followed, from the repo root, by
  `git diff --exit-code -- src/graphene_debrief/ui/static` (the built assets match the source).
- Time-box: any single problem that resists about two hours of attempts gets its state written into
  `morning.md` and you move on. Review loops are bounded where the plan says so.
- Every claim in `morning.md` is backed by a command you ran. If you did not run it, it goes under
  "Not verified".
- Known friction, so you do not rediscover it: the browser tool refuses `file://` (use the page's
  own localhost server) and saves screenshots only under the repo (`.playwright-mcp/` is
  git-ignored); the environment's classifier refuses commits that contain real transcript content;
  Typer forces colour under GitHub Actions; `npm --prefix ui run …` runs with `ui/` as its working
  directory, so repo-root paths inside npm scripts need `../`.

## Night one — the truthful record and the first map

Order: N0, N1, then N2 and N3 in parallel, then N4. N1 exists so the page can be built against a
fixed fixture while the record is being fixed.

### N0 — Ground (short)

- Rename the **distribution** to `graphene-map`, version `0.2.0`; the command stays `graphene` and
  the import package stays `graphene_debrief` (renaming it buys a user nothing and breaks `why` on
  every moved file). Update `pyproject.toml` (description: "See what your coding agents did to your
  repo: a local, replayable map of agents, files, commits and checks, built from Claude Code's own
  records."), the README install lines and `docs/RELEASING.md`. Add `node_modules/` to `.gitignore`.
- Cut: `--explain`, `--model`, `explain.py` and its tests; `--md`; `--full`. Hide `debrief` (an alias
  of the card for this release) and `ingest` from help. Leave the explanations table in place:
  **never drop a table or set a store aside again** (see N2.0). `--html` and its template go in N3.
- Add `tests/test_words.py`: fails if any tracked text file contains a banned word as a whole word,
  case-insensitive, LICENSE excepted. Word boundaries are Python's `\b`, so an identifier such as
  the old UI file names quoted in `docs/reports/2026-09-17-rebuild.md` (word, underscore, word)
  does not trip it. The list lives inside the test, each word reversed, so the
  test file passes itself. The integrator writes it (sub-agents cannot see the list).
- Acceptance: suite and lint green; `graphene --help` shows the card, `why`, `sessions`, `init`;
  wheel smoke from a clean `UV_TOOL_DIR` prints `graphene 0.2.0`.

### N1 — The contract and the fixture (integrator, before any parallel work)

- `src/graphene_debrief/graph.py`: dataclasses and one function `build_graph(store, session_ids) →
  Graph`, serialised by `graphene ui --json`. It carries: `run` (sessions, span, prompts); `axis`
  (compressed time: an idle gap over two minutes becomes a fixed-width break that records its real
  duration); `lanes` (agents with parent, depth, group, type, task text, working directory, span,
  closing message; groups collapsed by default); `rows` (directories and files by first appearance,
  directories collapsed by default); `marks` (id, kind, lane or row, x, y, agent, grade, record
  reference; marks on one row at one x merge into one mark with a count); `links` (spawned,
  returned, touched, committed-in, ran, blocked; each with grade and record reference); `tasks` (the
  agent's own list, when recorded); `coverage` (law 7's three counts plus the `window` count);
  `counters`; `omitted` (what the projection and the vendor's lists left out); `source` on every
  session and agent (`"claude-code"` today). x and y are numbers in the JSON.
- Bounded projection: beyond a cap (start at 1,500 marks) the builder collapses further and reports
  `omitted` counts that a test forces to agree with the data. Never silently drop.
- Extend `tests/fixtures/make_transcript_fixture.py` with one synthetic run that exercises
  everything: a main agent; a Workflow group of six subagents (`workflowPhase` in their `meta.json`,
  no `toolUseId`, linked by the `wf_<id>` directory that equals the parent `Workflow` call's
  `runId`); two plain `Agent` subagents whose `meta.json` `toolUseId` matches the parent call; two
  of the agents in worktrees, one under `.claude/worktrees/` and one elsewhere (the test creates it
  with a real `git worktree add` in the temp repo, and its transcript sits in its own project
  folder); heredoc writes whose Bash response carries `bashEditDiff` (`files`, `changedFiles`,
  `moreFiles` above zero once, `shared` once); commits made with `git commit -q … && git log
  --oneline -1` in both response shapes (`stdout` in transcripts, `content` in hook events); one
  recorded `git cherry-pick`; one commit with no record at all; a check that fails then passes; a
  refused call; a write outside the repo; two agents on one file in overlapping windows; a
  `TaskCreate` list. No real paths, byte-identical on rerun.
- Acceptance: a golden `graph.json` for the fixture, pinned by a test; a schema test (every mark
  and link has a grade and a record reference); and **the no-jitter property** over event prefixes:
  for every prefix of the run's events in time order, every mark present keeps the same x in every
  longer prefix, and with all groups and directories collapsed keeps the same y.

### N2 — The truthful record (Python; parallel with N3)

**N2.0 Schema (integrator, first, short).** Replace rebuild-on-mismatch with additive migrations:
`user_version` 2 adds `agents`, `commits`, `commit_files`, and `cwd` on `tool_events`. A
hook-recorded session is never dropped again, because its transcript may be gone (Claude Code
deletes transcripts after 30 days by default).

**N2-A Agents, worktrees, discovery (one sub-agent, first: B and C wait for its first commit).**
`sources/claude_code.py` around line 453 flattens subagent records into the session and throws away
which file they came from; that identity carries the agent id, the `meta.json` sibling, the `wf_`
group and the working directory. Rewrite that first. Then fill `agents`: id, session, parent
tool-use id, type, task text, cwd, Workflow run, phase, label, started, ended, closing message.
Sources: the parent's `Agent` call and its result (`toolUseResult.agentId`); `agent-<id>.meta.json`
(`toolUseId`, `description`, `agentType`, `spawnDepth`, `workflowPhase`); the `wf_<id>` directory
name; `journal.jsonl` when it exists (it is not always written, and holds labels only); the
`SubagentHandback` call's `message` for the closing message; and the `SubagentStart` and
`SubagentStop` hook events, which `graphene init` now registers (keep init idempotent: a repo with
the old five events is upgraded in place, in whichever settings file already holds them; this repo's
are in `.claude/settings.json`). Worktree mapping: a path under a worktree root maps to its
repo-relative path, longest prefix first (`.claude/worktrees/` is inside the repo root), with
provenance "worktree copy". Roots come from `git worktree list --porcelain` while the worktree
exists, and from the subagent transcript's recorded `cwd` after it is gone, accepted only when the
mapped path exists somewhere in the repo's git history. Never use `gitBranch` from a transcript:
concurrent agents contaminate it. Store `cwd` per event and resolve relative `file_path` values
against it. Discovery: besides the path-prefix rule, scan project folders whose first recorded
`cwd` is a worktree of this repo (`git -C <cwd> rev-parse --git-common-dir` while it exists). The
nested-checkout rule stays for vendored clones and submodules.

**N2-B Shell changes, commits, coverage (one sub-agent).** Read `bashEditDiff` from `PostToolUse`
Bash events and from transcripts (227 such events already sit unread in this repo's store): its
`changedFiles` and `files` give grade `shell`; its `moreFiles` count goes to `omitted`; when
`unavailable` is set the call contributes nothing; when `shared` is set keep the grade and carry
the flag to the inspector ("may belong to a concurrent command"), preferring another agent's `edit`
record for the same file and window if there is one. `bashEditDiffEnabled` can be set only in user
or managed settings, so `graphene init` does not set it; it prints the one line for people who run
attended (it is already on in auto and bypass modes). Fill `commits` and `commit_files` from git for
each session's window, including the agents' worktree branches. A commit belongs to the agent whose
recorded Bash call ran `git commit` and is the earliest, across the session's agents, whose
response contains a 7-to-40-character prefix of the SHA, in any response field (`stdout` and
`content` both occur; agents here commit with `-q` and print `git log --oneline` after). A recorded
`git cherry-pick <sha>` ties the new commit to its origin's agent. Do not use patch-id or subject
matching (tested: patch-id fails on conflicted picks). One change is credited to one session: fix
the double count visible in `graphene why README.md` on this repo.

**N2-C The store and the hook (one sub-agent).** Stop storing `Read` responses; keep Bash output to
its first and last 4 KB (the tail is where the SHA is printed); cap `input`. Add
`tests/test_hook_budget.py`: twenty runs of the hook entry against a temp store; assert the median
under 60 ms locally and 150 ms under CI, print the p95, and put both numbers in `morning.md`.

**Then, on the integrator:** the card's default unit becomes the latest session that did something
(plain `graphene` was blank in both repos it was tried on); the card, `why` and `sessions` print
law 7's coverage; the card's commit list is capped at five in every form, piped included;
`sessions` hides sessions with no calls unless `--all`; `why`'s empty answer becomes "changed in N
commits during session X; no recorded write" when that is the case; `why` rows gain the agent, its
task text and the grade; times print in local time with the offset; the false `[unrequested]` on a
file the prompt asked for is fixed, or the flag leaves every default view if it cannot be made
right (say which in `morning.md`).

- Acceptance, run by you on real data and reported as numbers only: on this repo,
  `graphene why src/graphene_debrief/cli.py` names work from session `9e5f295d`. A dry run on
  2026-09-18 measured what the rules above should reach: session `9e5f295d` **40 of 40** committed
  files (22 `edit`, 18 `shell`); Nemisis session `0dc016bf`
  (`cd /Users/alexlopez/Desktop/repos/Nemisis && graphene`) **60 of 86** (48 `edit`, 12 `commit`
  only, 26 with nothing; it predates the vendor's shell lists and has no hooks).
  Reproduce those or explain the difference with counts. **Do not tune a number**: not by changing
  the denominator, not by matching basenames across copies, not by loosening the commit rule beyond
  what is written here. Fixture tests cover every case in N1's list.

### N3 — The map, static first (one frontend sub-agent against N1's golden; then the integrator wires real data)

- `ui/` at the repo root: Vite, React, TypeScript, plain CSS with custom properties. Dependencies:
  `react`, `react-dom`, `d3-zoom`, `d3-selection`, and dev tooling (Vite, TypeScript, Vitest,
  types). Commit `package-lock.json`. Nothing else without an entry under "Decisions to check". No
  graph library, no component kit, no CSS framework. Rendering is SVG for lanes, rows, marks and
  links, HTML for the inspector, header, rail and scrubber.
- The page draws what the JSON says, at the coordinates the JSON gives. It computes no layout. It
  may compute only: the viewport transform, which marks are on screen, selection state, and the
  scrubber's cut.
- Built assets go to `src/graphene_debrief/ui/static/` and are committed (the repo ignores `dist/`,
  so do not use that name). CI gains one Node job on ubuntu: `npm ci --prefix ui`,
  `npm --prefix ui run check`, then the `git diff --exit-code` above. The wheel must contain the
  assets; `pip install` must need no Node; the page must make no network request (assert it in the
  Playwright run by listing requests; do not grep the built files, React's own strings contain
  URLs).
- `graphene ui` starts the server on a free loopback port, prints the URL, opens the browser unless
  `--no-open`, serves the assets and `GET /api/graph?sessions=…`. `graphene ui --export FILE` writes
  one self-contained HTML file with the JSON inlined; the export carries paths, counts, task text
  and prompts, and no hunks or tool output unless `--with-diffs`.
- Delete `export_html.py`, `templates/record.html`, `--html` and their tests in the same commit
  that makes the export work.
- Build in this order and stop wherever the clock rule lands: lanes with marks and spawn links;
  repo rows with marks and the collision highlight; selection lighting the chain (links between
  lanes and rows are drawn on selection only); the inspector; the header with the coverage counts
  and filter counters; the left rail of runs. The scrubber is night two.
- Acceptance: a Playwright run against the fixture opens the page, selects the agent that worked in
  the worktree outside the repo, and asserts by DOM selectors that its task text, its files
  (repo-relative) and its commit appear in the inspector, that the unknown block shows the
  unrecorded commit's file, and that the collision row is marked. You look at screenshots at
  1440×900, light and dark. Then the same on this repo's real session `9e5f295d`: sixteen agents,
  their tasks, and that night's commits are on screen. **Commit here even if everything after this
  slips.**

### N4 — Closing sequence, night one

- README: only what changed tonight, truthfully (the name, `graphene init` as step two and why,
  `graphene ui`, the coverage line, what was cut). The rewrite for a stranger is night two.
- Dogfood: `graphene`, `graphene why src/graphene_debrief/graph.py`, `graphene ui --export` on
  tonight's own session. Paste the card verbatim into `morning.md` with its coverage line. If
  tonight's own coverage is poor, that is the most important finding of the night: say why.
- Adversarial review, one sub-agent, truth lens only: find a mark or link with no record, or a
  number the terminal disagrees with. Collect every finding before fixing any.
- One new-user walkthrough pair in a fresh `HOME` from the built wheel (with synthetic transcripts;
  with none), following the README literally. Fix what is fixable tonight; list the rest.
- `docs/reports/<date>-record-and-map.md` and `morning.md`.
- **Gate, all required, in order:** (1) lint, tests, `ui` check and the assets diff green;
  (2) the walkthrough pair has no blocker; (3) `git push origin graph` and wait for every CI job on
  that push to finish green (`gh run watch`; do not skip the wait); (4) report and `morning.md`
  committed. If N3 is not at "inspector works on real data", the gate has not passed: push `graph`,
  leave `main` alone, and say so in the first line of `morning.md`.
- **Merge, only if the gate passes:** `git checkout main && git pull --ff-only origin main &&
  git merge --no-ff graph -m "Graphene 0.2.0: the truthful record and the first map" &&
  git push origin main`, and confirm CI on `main` is green. `GRAPH_DIRECTIVE.md` and
  `strategy-summary.md` stay tracked until the last night, because the later nights read them.
- **Rollback, written into `morning.md` verbatim either way:**
  `git checkout main && git reset --hard 165343b && git push --force origin main`

## Night two — live, the bar, the recording

Work on `graph`. If night one's gate did not pass, finish night one first.

### L1 — Live

- `GET /api/events` streams server-sent events: the server thread sleeps 250 ms, reads
  `PRAGMA data_version` on a read-only connection, and when it changed sends the graph delta past
  the client's `Last-Event-ID`. The same URL answers a plain poll (`?since=`) as the fallback.
  `ThreadingHTTPServer` with daemon threads; if you serve assets over HTTP/1.1, the stream sends
  `Connection: close`. At most four streams. The hook is not touched by any of this.
- Live is the same view with the scrubber pinned right and a "now" line. New marks fade in; nothing
  already drawn moves (law 6). An event that arrives with a timestamp older than the right edge is
  not squeezed in silently: the page shows "history updated" and redraws on click.
- Acceptance: a dev script replays the fixture's events into a scratch store at 10× speed while
  Playwright watches; marks appear without a reload; the positions of earlier marks, read from the
  DOM before and after fifty appended events, are unchanged; killing and restarting the server
  resumes the stream.

### L2 — Replay, runs, the chain

- The scrubber: replay is a cut on the time axis; a URL parameter `?t=<ms>` renders the map at that
  moment (the recording in L5 uses it).
- The rail: sessions that overlapped in time can be selected together and share one axis, which is
  how a collision between two separate sessions in one checkout becomes visible.
- The chain: at the top of the inspector, the selection's supporting chain as a small node-link
  diagram in fixed columns (task → agent → files → commits → checks), positions from Python or from
  plain column arithmetic, at most about forty nodes with an honest "n more". This is the part that
  looks like the word "graph"; it is the chain of one thing, never the whole repo.
- Acceptance: `?t=` at three moments renders three different cuts, asserted by DOM node counts;
  two overlapping sessions selected in the rail share one axis and their common file's row is
  marked as a collision; selecting the worktree agent draws a chain whose nodes match the JSON.

### L3 — The design bar (bounded: two review rounds)

"Looks like a real product" means all of the following, each checked:

- **Typography:** system UI stack for prose, `ui-monospace` for paths, SHAs and commands; sizes 12,
  13, 15 and 20 px only; tabular numerals for counts and times; nothing under 11 px; line height
  1.45.
- **Palette:** neutral greys and one accent hue for selection and focus. Agent colours from a fixed
  set of eight colour-blind-safe hues by lane order, reused with a dash pattern past eight. Red only
  for failure and breach, amber only for ask and stale, green only for pass. Evidence grade is
  carried by **shape**, never by colour alone: filled circle `edit`, square `shell`, diamond
  `commit`, hollow circle `window`, hatched block `unknown`. Light and dark through
  `prefers-color-scheme`; text contrast at least 4.5:1, checked by a script over the CSS variables.
- **Density:** lane 28 px collapsed and 40 px expanded; row 22 px; inspector 360 px. At 1440×900 the
  fixture run shows all nine of its lanes, with the Workflow group expanded, and fourteen rows
  without scrolling. A 4 px spacing grid.
- **Motion:** new marks fade in over 150 ms; the "now" line moves; nothing else animates, and
  nothing ever re-flows. `prefers-reduced-motion` removes the fade.
- **Empty states**, one sentence and one action each: not a git repo; no transcripts (say where it
  looked); sessions but none that changed anything; hooks not installed (the command to run); live
  and waiting for the first event.
- **First screens.** One prompt, forty files, no subagents: one lane split at its commits, each
  segment titled with the commit subject, eight to twelve directory rows with counts, coverage in
  the header. A repo with ten sessions: the rail lists them, the latest that did something is open
  at full replay, and without a click the screen says what ran, how much is accounted for, and what
  the diff hides.
- **Finish:** no default browser widgets visible; visible focus rings; every number has a label or
  unit; every truncated string carries its full text in a tooltip; Tab order is sane, arrow keys
  move along a lane and between lanes, Esc clears selection, `/` focuses the filter; zero console
  errors or warnings; no clipped or overlapping text at 1280×800 and 1920×1080; first paint of a
  500-mark run under one second and scrubber drag at 30 frames per second or better, both measured
  in a Playwright run and reported.
- Acceptance: a checklist file in the report with each line above marked pass or fail with its
  evidence (script output, screenshot path, measured number). Then a fresh sub-agent who has seen
  nothing else is shown the screenshots and asked what is ugly, confusing or amateur. Fix; ask a
  second fresh sub-agent once more; fix; stop. Anything left goes in `morning.md`.

### L4 — Walkthroughs, the come-back test, review, docs

- New-user walkthroughs as in N4, at most three rounds, until both are clean or the remainder is
  listed. Install to first map under 30 seconds.
- Come-back test (a stand-in for the kill criterion, which needs a person): one sub-agent gets only
  the map of the fixture run, another only the terminal commands and `git`. Both answer the same
  five questions (which agent changed `<file>` and what was it asked; how many committed files are
  unaccounted for, and which; which check failed and was it rerun green; which file did two agents
  touch; what was written outside the repo). Record right answers and tool calls for each. Report
  the result whichever way it goes; do not rerun it to improve it.
- Adversarial review with three lenses: truth (find a mark or link with no record, or a number the
  terminal disagrees with), security (the server: `Host`, `Origin`, path traversal, what the export
  leaks), product (the design bar). **Collect every finding from every reviewer before fixing any**,
  so reviewers can reproduce each other; last time fixes landed mid-review and the skeptics could
  confirm only the first.
- README rewritten for a stranger: the one sentence; the hero; install (`uv tool install
  graphene-map`, marked "after publication", and the `git+https` line that works today); `graphene
  init` as step two with the reason (Claude Code deletes transcripts after 30 days by default; the
  hooks record more than the transcripts hold); `graphene ui`, `graphene`, `graphene why`; how it
  works in one paragraph with the evidence grades; what it does not do; privacy (what the store
  keeps and no longer keeps, what the export contains); requirements. `docs/HOW_IT_WORKS.md` gains
  the contract, the grades, the worktree mapping and the coverage definition. `docs/ROADMAP.md`
  becomes: the map (now), rules on the map and a second source, Codex CLI (next). `CHANGELOG.md`
  gets `0.2.0`.
- Acceptance: a sub-agent that reads only the README says correctly what the tool does, how to
  install it, and what it will never do.

### L5 — The launch asset

- `docs/assets/replay_fixture.py` (a dev script, outside the package) prepares a scratch store from
  the synthetic run. With `graphene ui` open on it at 1440×900, capture frames by stepping `?t=`
  through the run (one `browser_run_code_unsafe` call that loops `page.goto` or sets the parameter
  and calls `page.screenshot` is much faster than one tool call per frame), and assemble them with
  `ffmpeg` (present at `/opt/homebrew/bin/ffmpeg`) into `docs/assets/map-live.mp4` and a GIF under
  8 MB, 12 to 20 seconds: agents spawning, marks landing on repo rows, a collision lighting, a
  check failing then passing, the coverage counts filling, then one selection drawing its chain.
  Because live and replay are one view, this is what live looks like; if L1 is done, record the
  live stream instead.
- A still of the come-back view (`docs/assets/map.png`, light) is the README hero, with the GIF
  under it. `docs/demo/index.html` is the synthetic run's export, committed, so people can click
  before they install (turning on GitHub Pages is Alex's step). Synthetic data only: no real
  paths, no real prompts.
- Acceptance: you looked at the frames; every beat listed is there; the README renders with both
  on GitHub's markdown (relative paths, sizes under GitHub's limits).

### L6 — Closing sequence, night two

As N4 (dogfood, report `docs/reports/<date>-live-and-launch.md`, `morning.md`, the same gate with
both walkthroughs clean, merge with the message "Graphene 0.2.0: the map"). The rollback SHA is
`main`'s head when you start tonight; write it down first. `morning.md` must carry the
kill-criterion block for Alex (see the contract).

## Night three — rules on the map, and Codex beside them

Precondition: `morning.md` has Alex's kill-criterion line. If it says **the map lost**: do not build
rules on it. Instead make the card and `why` carry everything the map does (agents, tasks, the three
coverage counts, the hidden-from-the-diff counters), demote `graphene ui` to "open the inspector",
write up the attribution method in `docs/`, run the closing sequence, and stop.

Otherwise work on `graph-rules`, branched from `main`. Two independent tracks; either can ship
without the other.

### R1 — Rules as records
`.graphene/rules.json`, written atomically, versioned, each rule with an id, kind, target, author,
created time. A pure evaluator `decide(event, rules, recent) → decision | None`, tested as a table:
protect (deny or ask) on a path or directory, including worktree copies through N2-A's mapping;
finish gate on a recognised check command; note on a path or on session start.
Acceptance: the decision table runs as a pytest table over recorded event fixtures, including a
worktree copy of a protected path; `decide` does no I/O.

### R2 — Enforcement
`graphene init` adds `PreToolUse`. The hook returns, and logs to a `firings` table, what it returned.
- **Protect, in up to three layers, and the rule's panel names which are in force.** (i) The hook:
  `hookSpecificOutput.permissionDecision` `"deny"` or `"ask"` with a reason that names the rule and
  who set it. (ii) The same path as an `Edit(<path>)` deny rule in `.claude/settings.local.json`
  (deny rules hold in every permission mode and cover `sed`, `tee` and redirections; Claude Code
  applies settings edits to a running session). Use `Edit(...)`, never `Write(...)`: path rules on
  other tool names are accepted and never consulted. Check by experiment which path form also
  matches a worktree copy, and say what you found. (iii) If, and only if, the person's settings
  already enable the sandbox, add the path to `sandbox.filesystem.denyWrite`. Never enable the
  sandbox yourself. Removing a rule removes exactly what Graphene added, nothing else. After every
  Bash call, `PostToolUse` compares `bashEditDiff`'s lists with protected paths; a hit is a
  **breach**: recorded, and answered with `decision: "block"`, the reason, and the restore command.
  The panel always prints: "cannot stop a script that writes the file directly unless the sandbox
  is on".
- **Finish gate** → on `Stop`, `decision: "block"` with a reason built from the store ("the last
  recorded run of `<command>` failed at 02:10" or "has not run since `<path>` changed at 02:14").
  Graphene never runs the check. Honour `stop_hook_active`; give up after two blocks of your own and
  record "stopped with a failing check". The panel prints: "asks at most twice, then lets go".
- **Note** → `additionalContext` on `PreToolUse`/`PostToolUse` when the path is touched, or on
  `SessionStart`/`SubagentStart`; phrased as a fact (the docs warn that imperative text can trip
  injection defences; the form says so); each delivery logged with agent and event. The panel
  prints: "a note; the agent may ignore it".
- A rule's state is derived from records only: **armed** once the hook has seen an event from that
  session (never assumed from configuration: whether hooks run in every permission mode is not
  stated in the docs), **fired n**, **breached**.
- Acceptance: protocol tests from recorded event fixtures for every decision; the budget test still
  passes with rules present; and one real check in a scratch repo with `claude -p` on the cheapest
  model, at most ten calls and fifty cents: a protected file is refused and the refusal appears as a
  firing; a finish gate makes the agent rerun a failing check; a note's text appears in the
  transcript. If the environment refuses the real calls, write the commands into `morning.md` as a
  runbook for Alex and list the behaviour under "Not verified".

### R3 — Rules on the map
Select a directory or file → protect (deny / ask). Select a check → require before finishing. Select
a path → pin a note. Each is a small form in the inspector that posts to the server with the launch
token; the server checks `Host` and `Origin` and rejects the rest. Rules draw as a band on their
rows; firings, breaches and deliveries draw as marks on the lane they happened in, and the rule's
panel lists them with times and its fixed "cannot do" line. Design bar as L3. A second short GIF: a
rule placed, an agent refused, the firing appearing. README's sentence gains "…and set the rules the
next run must obey." Acceptance: a Playwright run places a protect rule from the inspector and
asserts that the band draws on the row and the rule is in `.graphene/rules.json`; a POST with a
wrong `Origin` and one with no token are both rejected.

### R4 — Last in line, drop first
- **One writer at a time** (set on a directory): while one agent has written a file through `Edit`
  or `Write` and has not stopped, another agent's `Edit` or `Write` to the same file in the same
  checkout is denied with a reason naming the first agent and its task. One atomic insert into the
  store decides it; the claim ends on that agent's `SubagentStop` or after ten quiet minutes. The
  panel prints: "does not cover shell writes or separate worktrees".
- **Stop** a running session: at its next hook event return `{"continue": false, "stopReason": …}`.
  The request names one session id and expires in ten minutes. Log requested, delivered, ended. Test
  what `continue: false` does inside a subagent and report it; offer per-agent stop only if it
  stops only that agent.
- Acceptance: two recorded agents editing one file in one checkout produce exactly one deny, which
  names the first agent's task; a stop request expires after ten minutes, shown by a test that
  injects the clock.

### C1 — Codex CLI as a second source (one sub-agent, its own files)
`src/graphene_debrief/sources/codex.py`, read-only backfill of `~/.codex/sessions/**/rollout-*.jsonl`
for sessions whose `session_meta.cwd` is inside the repo or one of its worktrees: prompts from
`UserMessage` items by `turn_id`; edits from `FileChange` items (`unified_diff`), from
`patch_apply_end`, and from the legacy `apply_patch` text; commands from `CommandExecution`;
subagents from `SubAgentActivity` (`agent_thread_id`, `agent_path`). Inter-agent message bodies are
encrypted in the file: show the agent, not the text, and say so. `source: "codex"` throughout; its
lanes carry a small source label. No hooks for Codex in this directive. Synthetic fixtures only in
the repo; check it on the real rollouts on this machine and report numbers only. Acceptance: a
fixture with one Claude Code session and one Codex session overlapping in time on one repo draws
both on one axis, and `why` names the Codex turn for a line it wrote.

### R5 — Closing sequence, night three
As before; report `docs/reports/<date>-rules.md`. On `graph-rules`, before the gate:
`git rm GRAPH_DIRECTIVE.md strategy-summary.md` (they stay on the `strategy` branch; the thesis
stays in `docs/`). The rollback SHA is `main`'s head when you start tonight.

## Scope rules

- Visible commands at the end: `graphene`, `graphene ui`, `graphene why`, `graphene sessions`,
  `graphene init`. No others.
- Soft line budgets, non-test Python (today 3,642): **4,700 after night one** (cuts remove about
  340; the graph builder, agents, commits, migrations and the server add about 1,350), **4,900
  after night two, 5,900 after night three**. Frontend: **1,500 lines of TypeScript after night
  two, 1,900 after night three; 450 of CSS.** The reason is the hackathon: 137,331 lines, a 531 s
  suite, four graph renderers and a headline claim that was never proven. Each line here has to be
  covered by a test or a walkthrough. If you pass a budget, say so in the first section of
  `morning.md` with what you would cut; last time an overrun went unstated.
- No new infrastructure of any kind: no database server, no cloud, no containers, no socket
  library, no background daemon, no accounts, no telemetry, no model calls.
- Not in these three nights: a Claude Code plugin; hooks for Codex; plan editing; cross-session
  messaging; anything per-team; Windows.

## morning.md — the contract

Alex reads this in five minutes. The first two sections together are at most 30 lines.

```
# morning.md — <date> — night <n> of 3

## 30-second version
- main: merged and green / untouched (reason)
- What you can open right now: <one command>
- Coverage on last night's own session: <n> committed files · <n> traced to a recorded write ·
  <n> only to an agent's commit · <n> to nothing
- Publishable today: yes / no — blocked on: <the human steps only>
- Biggest risk: <one line>
- Budgets: Python <n>/<budget>, TypeScript <n>/<budget> — over? what to cut
- Next night starts at: <milestone>

## Do these today (in order, minutes in brackets)
1. [1] ~/.claude/settings.json: add "cleanupPeriodDays": 365 (transcripts are deleted after 30 days
   by default; yours start 2026-08-21) — skip if done
2. [10] (after night two) THE KILL CRITERION. Run `graphene ui` on a real run of yours. Answer the
   five come-back questions below once with the map and once with `graphene`, `graphene why` and
   `git log`, and time each. Then fill in this line, which night three reads:
   KILL CRITERION: map won / map lost — <n> of 5 faster with the map — <one sentence>
3. [5] PyPI: add a pending trusted publisher: project graphene-map, owner Alex-lop, repo Graphene,
   workflow release.yml, environment pypi
4. [1] git tag v0.2.0 && git push origin v0.2.0 — then watch Actions → release
5. [10] (after night two) Post the recording: <paths>, with the two-line description from the
   README; turn on GitHub Pages for docs/demo if you want the click-before-install link
6. <anything else, with the exact command>

## What changed
One line per change, each ending with the test or command that proves it.

## Not verified / not done
## Decisions to check
## Rollback
<the verbatim command>

## Last night's session, as Graphene sees it
<the card, verbatim, with its coverage line; the path of the exported map>

## Questions (at most 3, only ones that block the next step)
```

Plain language. No claim without the command that shows it. If something failed, say so in the first
section, not on page three.
