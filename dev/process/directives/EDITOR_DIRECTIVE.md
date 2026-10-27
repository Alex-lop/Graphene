# Graphene: the editor directive

*For the Opus 5.5 agent that runs on this repo tonight, 26 to 27 October 2026. Written by the reviewer Alex works
with, from a reading of `main` at `2da29a5` (0.8.0 on PyPI). The reading covered:*
- *the revamp night's record and morning file;*
- *the extension in `editors/vscode/`, built, tested and rendered in its preview page at several widths;*
- *the README, `docs/HACKATHON.md` and `dev/launch/video-auto.md`;*
- *Claude Code's docs on hooks and on Chrome.*

*Alex hands it over as it is. Two lines in it are marked for him: whatever they say when you read this is the
rule. Commit it at `dev/process/directives/EDITOR_DIRECTIVE.md` before you start.*

*The working rules of the earlier directives still hold:*
- *Work in a fresh clone of GitHub's `main` in your scratchpad, never Alex's checkout, on a branch named
  `night/editor`.*
- *Make small green commits, each fix with the test that failed before it.*
- *Keep `dev/process/morning.md` current at every milestone.*
- *Follow the cut directive's voice rules in everything you write.*

---

## Why tonight

Alex used Graphene for VS Code himself today, in VS Code and in Cursor. His verdict: "it's not that good if I'm
being honest." The CLI, the race and auto mode are strong. The editor is where judges and every future user will
actually meet Graphene, and right now it is a graph in a webview plus a lot of terminals.

Tonight you make Graphene for VS Code the best way to watch and steer coding agents in any editor. That means it
is:
- readable at any width;
- live;
- native to the editor: its diff editor, its text documents, its Explorer;
- ready for the places people install extensions.

Then you set up the rest of the week:
- a release Alex can tag Tuesday;
- the live take in one command;
- b-roll for the video;
- a review of auto mode by reviewers who weren't there when it was written.

Submissions close Friday 30 October at 10:00 PT (13:00 for Alex). Nothing tonight may break what a judge runs:
`uvx graphene-map demo --auto`, `demo --cheat` and `demo --live`.

## How to work tonight

Be relentless. Decide, act, and write down why.
- Never leave a lane at "it should work": open it in the real app and look.
- Back every claim about the editor in the morning with a screenshot or a number from real VS Code or Cursor, not
  the preview page.
- A run that breaks is a finding, not the end of a lane.

Use subagents hard: parallel lanes, each in its own clone. A skeptic who didn't write a lane reviews it, then it
gets fixed. Split the lanes the way Graphene splits a plan, one writer a path. A lane that needs another lane's
file asks for it in the shared log instead of editing it.

**Models.** You are Opus 5.5. Subagents run on Fable 5.1 while it is available, and carry on as Opus 5.5 when its
limit hits. Last night it hit at 01:50 and no review ran after that. A model running out never stops a review.
*(Alex: delete the second sentence of this paragraph to keep last night's Fable-only rule.)*

**Spend.**
- **The scripted stand-in** costs nothing. It is `tests/fake_tokenfactory.py` served on this machine, with
  `GRAPHENE_TOKENFACTORY_URL` pointed at it. Use it for every run whose point is the editor.
- **Claude Code executors** (Haiku, Sonnet) in scratch repos are for runs whose point is a real agent. Spend at
  most $15 on them tonight, with every run under `--max-usd`. They draw on the same plan as you and your
  subagents. *(Alex: change the number if you like.)*
- **Token Factory** only if Alex started this session with `GRAPHENE_AGENT_LIVE_USD` set. Then spend up to that
  cap, on lane 7's live takes, through the night ledger (`~/.graphene/night/`, purposes `takes` and `verify`).
  - Never set `GRAPHENE_AGENT_LIVE_USD` yourself.
  - Never print, copy or write the key anywhere.

**Alex's notes.** If `~/graphene-notes.md` exists, read it before anything else. Every line in it is a finding:
either fix it tonight, or answer it in the brief with why not.

**Keep the Mac awake** for the night: run long jobs under `caffeinate -i`. Screenshots come from the app, so a
locked screen is fine, but sleep is not.

**If the night runs short, work in this order:**
1. The editor (lanes 0 to 3) first. The review (lane 5) runs in parallel from the start.
2. The listing (lane 4) and the live take (lane 7) next.
3. The docs (lane 6) always, at the end.

The browser spike (lane 8) runs whenever a subagent is free.

## What we already know

This was read on 26 October. Verify each point rather than trusting it.
- **The sidebar graph is a thumbnail.** At about 320 px, fit-to-view shrinks every box past reading, and the goal
  box falls off the right edge. To see it, open `media/preview.html?fixture=running` at 320×700.
- **It has never watched a live run.** According to the revamp record, it has only run in the preview page in
  Chromium and in a smoke test that activates it in VS Code 1.143.1.
- **It installs only by hand.**
  - The `.vsix` on the GitHub release is the only way to get it.
  - Open VSX, where Cursor installs from, answered 404 for `alex-lop.graphene-vscode`.
  - There is no Marketplace listing.
  - `package.json` has no PNG icon, which both listings need.
- **It re-reads on every agent's save.**
  - Its watcher covers `.graphene/**`, and every task's worktree lives under `.graphene/worktrees/`. All it needs
    is `.graphene/graphene.db` and its `-wal`.
  - Each read is a fresh `graphene state --json` process (about 0.10 s), on top of a poll every 1.5 s while a
    view is open.
- **Adding a step takes four input boxes:** title, where, scope and check. That breaks what Alex settled on 23
  September: the person never types the tree.
- **The editor can't do what the cockpit does.**
  - There's no diff of a task or a fork (the cockpit has `i` then `c`).
  - Board questions say "answer it in the cockpit".
  - `watch`, `run`, `auto` and `init` each open a terminal.
- **A judge with no key sees nothing in VS Code.** The extension needs a real store, and the replays only play in
  the terminal.
- **Auto mode has never run live.** The README says so twice.
- **The README still says a plain paragraph did as well for less.** Those September runs compared one agent with
  a plan against one with a paragraph. They never involved lanes or races.
- **Some things are already right. Keep them:**
  - It is a thin client: every read and every change is a `graphene` command.
  - Agent marks are stripped from what a click runs.
  - `graphene.path` comes from the user's own settings only.
  - The extension is off in Restricted Mode.
  - The webview has a CSP with a nonce and no `innerHTML`, and hovers are escaped.
  - The Explorer owners, the status bar, the Rounds view and the notifications all work.

## Lane 0: the before, in the real app (the first hour)

Build the harness the whole night leans on, and use it to see what Alex saw.

**Drive real VS Code** with Playwright's Electron support, the way VS Code's own smoke tests drive it.
- Use a build that `@vscode/test-electron` downloads, or the installed app. Also drive the installed Cursor if
  `/Applications/Cursor.app` exists.
- Always launch with a `--user-data-dir` and `--extensions-dir` of your own, never Alex's.
- Trust the fixture folder in that profile, because the extension is off in Restricted Mode.

**Drive a real store.** Install the `.vsix` built from the branch and open a fixture repo
(`dev/proof/make_wordkit.py`). Run `graphene auto` against the stand-in so the store changes the way it would
live.

**Look at it.** Reach into the webview's frames and assert on what's there. Take screenshots of:
- the sidebar at 280, 320 and 400 px;
- the editor tab at 1280×800 and 1920×1080;
- each of those in Dark Modern, Light Modern and a high-contrast theme.

Record video while you do this.

**A stranger's first hour.** Give a fresh subagent only the extension's README and the installed app, and have it
try to get from nothing to a race it can steer. Its confusion, step by step, is a list of findings.

**Thirty minutes of research, one subagent.** Find out how the best editor agent UIs show work in progress:
- VS Code's Agent Sessions view;
- Claude Code's VS Code panel;
- Copilot's coding agent;
- Cline;
- GitLens's graph.

Write what each does best on one page, for lanes 1 and 2.

**Write `dev/process/editor/before/`.** It holds the screenshots, the stranger's log, the friction list, and five
numbers:
- seconds from install to the first graph;
- the editor's moves against the cockpit's;
- the smallest text drawn at each width;
- latency from a store write to the screen;
- idle CPU.

## Lane 1: the graph, readable and alive

The graph tab is where people watch the race. Make it the clearest, best-looking thing in the editor.

**Readable at every width.**
- No text under 11 px and no clipped boxes. The goal is always on screen, or one key away.
- When narrow (the sidebar), either lay the graph out top to bottom with waves as rows, or show a compact lanes
  view instead. Decide by looking at screenshots of both.
- Pan and scroll rather than shrinking past reading. Remember the zoom for each view.

**The race, visible.**
- Each fork shows its progress as it works: attempts, lines, dollars and seconds quiet.
- The kept fork is marked as soon as it's chosen and says why, in the cockpit's words (`kept b: 4 lines against
  12`).
- A task that came back is red, with its reason on the box.
- Changes animate, quietly. Nothing moves when nothing changed.

**Live.** A state change reaches the screen within a second of the store's write. Measure it.

**Editing by touch.** Keep drag to link, × to unlink, and adding a step after a task. Make all three findable: a
hint the first time, hovers, and every key listed on `?`.

**Look.**
- Use codicons and the theme's own colours, real type and spacing, and focus rings.
- Support keyboard navigation through every box, screen-reader labels and the high-contrast themes.
- Hold it to the bar of the best extensions in the Marketplace, judged from the screenshots, not the code.

## Lane 2: native to the editor

The editor can do much more than a canvas. Use what VS Code already does better than any webview.

**Needs you, first.** The sidebar leads with whatever needs the person, the way the cockpit's top rows do:
questions, proposals, hand-backs, sign-offs, and auto mode waiting. Each item has its move inline:
- answer a question from a quick pick of its options and its default, or in your own words;
- accept or drop a proposal;
- widen a hand-back, reopen its owner, or try it again;
- sign off from the diff.

Nothing that needs the person sends them to the cockpit.

**Agents, live.** Add a view of every running agent, showing for each:
- its number, task, model and fork;
- what it's doing now (`editing app.py`);
- seconds quiet and dollars.

A click opens its changes so far.

**Diffs in the diff editor.** Any task or fork opens its changes in VS Code's own diff editor, against its base or
its ref, multi-file where the engine allows. A race's forks open side by side, and you can land or pick from
there.

**The plan as a text document.** Edit Plan opens the plan's text form (`graphene plan --text`) in a real editor
tab. Saving applies it through the same path `plan edit` uses, and Graphene's refusals show up as diagnostics on
their lines. This is how Alex asked to edit "what the plan says".

**Add a step in a sentence.** The person types one line. The planner proposes the step with its scope, check and
needs, and it appears as a proposal to accept. Typing a scope by hand stays available under Edit for people who
want it.

**Files you open.** A file a running task owns says which agent has it and offers "Diff with agent 3's copy". The
person's own editing is never blocked.

**The demo in the editor.** "Graphene: Watch the Demo" plays `demo --auto` in the VS Code graph with no key and no
network. Its header says it's the scripted stand-in, the way the terminal replay's top line does. A judge sees
the race in VS Code in one click.

**First run without hunting.**
- Find `graphene` on PATH, in `~/.local/bin`, or in `uv tool dir --bin`. If it's missing, offer to install it, in
  a terminal the person can see, after they say yes.
- Set Up This Folder is a pair of quick picks for planner and executor. It runs `graphene init` in a terminal,
  because an init that sees no terminal leaves the gate open.
- Then Auto…. The key stays in its terminal, read from a hidden prompt on purpose.

**Cursor.** Everything works in the installed Cursor, or says plainly what it can't do. Never raise
`engines.vscode` above the version Cursor's build reports.

## Lane 3: what the CLI owes the editor

The extension never opens the store itself. Everything it shows comes from a `graphene` read, and everything it
changes goes through a `graphene` command. Give it what it needs.

**A stream instead of a poll.**
- A long-lived `graphene state --json --watch` (or your name for it) prints a snapshot line each time the store
  changes. It watches the store's own version, not the clock, and costs next to nothing when idle.
- The extension uses the stream when the CLI has it, and falls back to polling on an older CLI.
- Narrow the extension's file watcher to the store's own files.
- Keep `.graphene/worktrees/**` out of the editor's watcher and search, if an extension is allowed to set that
  default on the engine you target. Check `configurationDefaults`.

**One sentence to one proposed step, for lane 2.**
- The step can go after or under a task.
- It uses the configured planner, or Nano when the planner is Nemotron.
- Only a person, or the envelope, accepts it.

**The plan's text read from stdin, with faults by line**, in a form the extension can turn into diagnostics.

**A replay the editor can watch**, for Watch the Demo, somewhere it can't touch a real project's store.

**Words.**
- Every new flag goes in `--help` in plain words, and in `docs/HOW_IT_WORKS.md`.
- Add no new top-level command unless lane 2 can't do without it. If you add one, say why.

## Lane 4: where people install

The extension goes to the Marketplace and Open VSX once Alex makes the accounts on Tuesday. Have everything else
ready.

**The listing.**
- A 256×256 PNG icon made from `docs/brand/avatar/`.
- Categories including AI, `preview: true`, a gallery banner and keywords.
- A README written for the listing page. `vsce` refuses SVG images there, apart from badges.
- The extension's CHANGELOG, with its version kept in step with the CLI's.

**A publish workflow.** It runs by hand or on a release and publishes the same `.vsix` to both listings, using
`VSCE_PAT` and `OVSX_PAT` from repository secrets. It never runs tonight.

**`docs/RELEASING.md`** gets the exact first-time steps for both listings:
- the Marketplace publisher, and the Azure DevOps token with its scope;
- the Eclipse account, the publisher agreement and the namespace for Open VSX;
- the two secrets.

Check whether the name `alex-lop` is free on both, and say what to use if it isn't.

**Package it and prove it.** Make `vsce package` run clean and check its file list. Install that exact `.vsix`
in the harness's VS Code and in Cursor, and run lane 0's checks on it.

**CI.** The extension's end-to-end tests run on Linux under xvfb, alongside its unit tests.

## Lane 5: auto mode, reviewed by someone who wasn't there

Last night's agent found and fixed real holes in the envelope, with no reviewer after 01:50:
- a task that writes the hooks' settings;
- a git hook planted in `.git/hooks/`;
- an unread `curl … | sh` check.

Tonight, two fresh reviewers who didn't write any of it read:
- `auto.py`, `auto_cli.py` and the envelope's checks;
- `state.py`, and last night's changes to `gate.py`;
- the extension's `commands.ts`, `extension.ts` and `graph.ts`.

They assume hostile input:
- a repository whose files tell the planner what to propose;
- an agent's own `graphene plan propose -` while auto is on;
- paths that dodge a guard: links, `..`, absolute paths, case, Unicode normalization on a Mac's disk, and globs
  that expand into protected paths;
- a check that smuggles in a second command;
- every way to spend that the budget doesn't see: forks, retries, fix rounds, the planner's own calls, and an
  agent's own `graphene run`;
- the webview:
  - a message the host takes that it shouldn't;
  - an id or title that reaches argv as an option;
  - a goal or title that reaches a terminal unquoted;
  - plan text rendered as markup anywhere.

Each finding gets this sequence: a failing test, the fix, the test passing, and the other reviewer confirming
it. `dev/process/editor/review.md` lists every finding, including the ones that stay as limits.

## Lane 6: the docs, true at the end

**The README.**
- The headline stays, and so does Alex's "Why I built this", word for word.
- The VS Code section shows screenshots from real VS Code, taken by the harness, not the preview page. Once Cursor
  has been tried, it says so.
- The install lines must be true on the day the branch merges.

**The paragraph line.** Narrow it to what was tested (one agent, a plan against a paragraph, in September), or move
it below the fold.

**The stand-in lines.** Change the two "auto mode has run against the scripted stand-in" lines only if lane 7 ran
it live, and give its numbers and source.

**Everything else matches what was built:** `editors/vscode/README.md`, the walkthrough, `docs/HACKATHON.md`,
`docs/COMPARE.md` and `dev/launch/claims.md`. The CHANGELOG and release notes are for the next version: 0.9.0,
unless tonight turns out small.

## Lane 7: the live take and the b-roll

**The live take in one command.** `dev/proof/auto.sh` already makes the repo, records with `RECORD`, and ends with
the bill. Add what filming needs:
- the one line that installs the night's `.vsix` in Alex's own VS Code;
- a pause after `graphene init`, so he can open the folder in VS Code and start recording before the race;
- `ENDPOINT=standin`: the same take, free, against the stand-in, so he can rehearse with no key.

Rehearse that exact sequence in the harness, and save a reference screenshot of each beat.

**If Alex opened Token Factory:**
- Run the live takes yourself, up to his cap. Ultra plans, three Nanos race each task, and the goal's check runs.
- Keep the harness's VS Code open on the folder and recording. That way the best take is both the proof and the
  footage for the video's beats 4 and 6.
- Commit the cleanest recording, replayable with no key.
- A take that breaks is a finding: fix it and take it again.

**The b-roll.** Record 1080p clips from the harness, each named for its beat in `dev/launch/video-auto.md`:
- the race fanning out in the graph;
- a fork being kept;
- the Explorer's owners;
- a drag that links two tasks;
- a diff opened from a task;
- the needs-you queue being answered.

Add `vhs` takes of `demo --auto` and `demo --cheat` at 1080p. Everything goes in `~/graphene-film/broll/`, not
the repo, with a list in the morning file. Any clip filmed against the stand-in shows that it is one.

**Dogfood, if the night allows.** Run one of tonight's own lanes through Graphene, using Claude Code executors on
Sonnet within the $15, with the harness's VS Code watching. Say how it went, and keep the clip.

## Lane 8: the browser question, answered with evidence (one subagent, 45 minutes)

Alex asked whether Graphene could show what agents do in the browser, with screenshots. Before anything is built,
answer the two questions the idea depends on, using this machine's Claude Code. Set up:
- a scratch repo with Graphene's hooks;
- Playwright MCP (`--isolated --headless`) on a page served from localhost;
- `claude -p` on Haiku.

The questions:
1. Do PostToolUse and PreToolUse hooks fire for MCP tool calls? An issue (#73586, on 2.1.198) says PostToolUse
   didn't, but the hooks docs say MCP tools appear in tool events.
2. Where does a screenshot end up: in the hook's `tool_response`, only in the transcript, or both? How much space
   does it take in Graphene's store?

Write `dev/process/editor/browser-spike.md` with the versions, the commands, what happened, and what a per-task
trail would take.
- Write no product code, and put nothing in the README or the pitch.
- Never use Claude in Chrome, never use Alex's browser, and never visit a site that isn't localhost.

## What not to do

- Don't change what Graphene is. The headline stays, and the browser stays a spike.
- Don't break the judge's paths. `demo --auto`, `demo --cheat` and `demo --live` must work from the built wheel at
  every merge.
- Don't touch Alex's VS Code or Cursor profiles, settings or extensions, or `~/.claude/settings.json`. Don't use
  Claude in Chrome or his browser.
- Don't publish anything:
  - nothing to PyPI, the Marketplace or Open VSX;
  - no tags and no GitHub release;
  - no push to `main` and no force-push;
  - no deleted branch or tag.
- Don't set `GRAPHENE_AGENT_LIVE_USD`.
- Don't loosen a guard to make a demo pass.
- Don't add a runtime dependency to the extension unless the screenshots show it pays for itself. If you do,
  bundle it, keep the license permissive, and say which license it has.
- Don't claim anything that didn't run.

## Verification before the PR

1. **CI on GitHub, green.**
   - Open a draft PR from `night/editor` as soon as the first lane merges, because CI runs on pull requests, not
     on branch pushes. Push often after that.
   - Ruff clean, `uv build`, the wheel's smoke test, and the three demo paths run from the wheel.
2. **The extension.** Types check, unit tests pass, and the end-to-end tests pass in the harness's VS Code
   (locally and in CI) and in Cursor. `vsce package` runs clean.
3. **Lane 0's five numbers again**, before and after, from the same harness.
4. **Screenshots after**, at every width and theme from lane 0, beside the before. Look at each one yourself.
5. **The stranger again**: a fresh one, on the new build, with its log.
6. **Every review finding with its test**, and the ledger by purpose if Token Factory was opened.
7. **"Your 15 minutes"** (below), run as written from the pushed branch, and timed.

## The decisions that are yours

- The narrow layout: vertical, lanes, or both.
- The stream's name, and how it notices a change.
- The shape of the needs-you queue and the agents view.
- The CLI side of "add a step in a sentence".
- Whether the next version is 0.9.0 or 0.8.1.

## The decisions already taken

- The extension stays a thin client over the CLI, so the cockpit and the editor never disagree.
- Publishing to the Marketplace and Open VSX is Alex's job, on Tuesday.
- The browser is a spike tonight, nothing more.
- Subagents: Fable first, then Opus 5.5.

## The morning

Write `dev/process/morning.md` in this order.

**Your 15 minutes**, first. A fresh terminal, the commands exactly as written, each with what it shows:
- install the night's `.vsix` in VS Code and in Cursor;
- Watch the Demo;
- open the fixture, watch a stand-in race, then answer something in the needs-you queue and open a diff;
- if a live take ran, replay it.

**Tuesday**, second:
- the first-time steps for the two listings (about 20 minutes);
- the release commands for the next version;
- the live take command, if he still needs to film it;
- where the b-roll is.

**The brief**, at most twenty lines:
1. Before and after: seconds to the first graph, the smallest text at each width, latency, idle CPU, and the
   editor's moves against the cockpit's.
2. Look at these first: three screenshots and one clip.
3. The review's findings, fixed or open.
4. Alex's notes, each one fixed or answered.
5. The browser spike's answer, in two lines.
6. Decide: at most three questions, each with your default.
7. Broken or risky: three lines at most.

Below the brief:
- DIRECTION.md gets "Decisions taken on the editor night", at most fifteen of them.
- Then the state of every branch, and the rollback SHA (`main`'s HEAD when you start).

## When to stop

- At 07:15, start nothing new and nothing live.
- By 07:45, everything is merged into `night/editor` and green on GitHub.
- By 07:55, it's pushed, the draft PR's body is the night's record, and "Your 15 minutes" has been run once from
  the pushed branch.

A lane you didn't reach stops where it stands, with its state written down.

Now go. Make the editor the place people want to watch their agents work, prove it in the real app, and leave
Alex a Tuesday where all he has to do is publish, film and ship.
