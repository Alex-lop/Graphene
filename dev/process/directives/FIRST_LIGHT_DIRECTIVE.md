# Graphene: the first-light directive

*For the agent that runs on this repo tonight, from Alex's send until 08:00 his time (America/New_York). Written 2026-09-28 with Alex, after the shaping run (PR #31, merged).*

*"First light" is an astronomer's word for the first night a new telescope sees the real sky. Tonight Graphene meets a real model for the first time.*

*The earlier directives hold wherever this one is silent. The winning directive's rules on integrity, claims and secrets carry over word for word, and so do the claims `docs/process/field.md` forbids. Before you touch anything, read:*
- *`dev/DIRECTION.md` (81 to 100 first)*
- *`dev/process/morning.md`*
- *`docs/process/shaping/walks.md`*
- *`docs/process/ideas.md`*
- *`dev/test/PRACTICE.md`*
- *`dev/process/directives/LIVE_DIRECTIVE_DRAFT.md`*
- *this file*

*Where the draft and this file differ, this file wins tonight.*

## How you work tonight

**You do not doubt yourself.** You are the strongest agent this repo has had, and everything in this file is within your reach. Decide at every fork, write down why in one line, and move.
- Do not hedge.
- Do not ask permission for what this file grants.
- Do not stop at the first version that works.
- Do not leave a TODO where the work could be done.
- Do not call anything out of scope that this file asks for.

**You are never lazy.** Checking your work is not doubt; skipping the check is laziness. Every claim you write has been run. Every fix has a test that failed before it. Every screen was looked at. Every number comes from the ledger.

**Use sub-agents.** Spawn one for every independent piece, as many at once as the work allows, each in its own worktree. You coordinate, integrate and merge. When a lane empties, start the next thing.

**The night ends at 08:00, not when the list looks done.**
- Start nothing new after 07:15.
- Have everything merged and green by 07:45.
- Have the brief final and pushed by 07:55.

## Tonight is practice, and it is capped

Alex's Token Factory key works. Tonight Graphene runs for real for the first time, as practice:
- first contact and the ladder;
- the fixes first contact forces;
- the prototypes, tried live;
- a rough cut of the demo, in real time.

**The actual testing waits for Alex, who wants to be there.** That means the registered arms, rung 6 (their rehearsal), the shaping study with executors, and the final recording. Prepare all of it; run none of it, and do not look at a registered condition's results early.

**The cap is $10 for the whole night, hard.**
- Take the lower of `GRAPHENE_AGENT_LIVE_USD` and 10.
- The ledger estimates at list price, so start nothing live past $8.
- The ladder's per-rung caps reset on a rerun; the night's does not. Keep one ledger for the night, locked. Every live call reserves before it spends, and a call that would cross the cap is refused.
- Count Ultra's calls; it is the expensive one.
- The docs said Sandboxes were free in the beta; the ladder says they are billed apart at a price not read. Find out which before rung 3, and count every Sandbox operation and minute either way.

**Spend in this order, until the cap:**
1. rungs 2 to 5 of the ladder;
2. up to three takes of rung 7, for the rough cut;
3. the prototypes live, a few calls each.

Everything live is labelled practice in the ledger and never enters a registered table.

**The key is in the environment.**
- It is never printed, searched for, copied, written to a file, recorded, or sent anywhere but Token Factory's API.
- Leak checks count matches and never print them.
- If this session refuses a live command, do not work around it. Write the exact command into the brief for Alex, and go on with the rest.

## Before your first change

1. **Leave Alex's checkout alone.** It is on `fix-replay-teardown`, with an uncommitted change to `tests/test_demo.py`: his start on the replay bug. Work in your own worktree, cut from `origin/main`. Read his diff first, and carry it into lane C's fix, credited to him.
2. **Record the rollback SHA.** Work on branch `first-light` with one draft PR. Move `dev/process/morning.md` to `morning-2026-09-28.md` and start a new one.
3. **Let an agent practise only when Alex says so.** Rungs 2 to 7 refuse to run inside Claude Code (they see `CLAUDECODE`), so that spending stays a person's act.
   - Keep that refusal, and add one explicit opening. When the person has set `GRAPHENE_AGENT_LIVE_USD` in the shell that started the session, the ladder and every live path run under the night's cap above. Without it, they refuse exactly as they do now.
   - You never set that variable yourself. Alex set it before sending this.
   - Test both ways.
4. **Alex ran rung 1 himself before sending this.** Climb from rung 2.

## The lanes

### A. First light (the main line)

**Why.** No surface can claim anything live until this happens, and first contact with a beta service breaks things. Better tonight than on camera.

**What.**
- Run rungs 2 to 5 live:
  - a leaf run locally;
  - a leaf in a Sandbox (if Sandboxes access is missing, note it and go on);
  - the escape test in ConTree;
  - a recorded leaf.
- Every fix first contact forces is its own commit with a test. Sanitised recordings replay in CI.
- Verify live what was verified only against the fake:
  - errors never echo the key;
  - a recording holds no secret;
  - model ids resolve from the live list;
  - a killed or timed-out Sandbox operation comes back cleanly.
- Once rung 2 passes, one line becomes true: Graphene has made a runtime call to Token Factory. Say exactly that where the README says what Graphene is not yet, and nothing more.

**Done when** rungs 2 to 5 have passed live or their blocker is written down, with recordings, the bill, and a test for every fix.

### B. The rough cut, in real time

**Why.** Alex wants to see the video running live on Nebius. A rough cut shows what the real one needs.

**What.**
- Update `dev/demo/STORYBOARD.md` for the board, the views and the direction.
- Record up to three live takes of rung 7, scene by scene with VHS, in real time. Label any cut wait on screen.
- Assemble `dev/demo/rough.mp4` with `dev/demo/build.sh`, with the narration as subtitles. Make the script if it is missing; commit the script, never the video.
- List what looked wrong on camera. Fix what you can tonight, and put the rest in the brief.

**Done when** `rough.mp4` exists from live footage only, and the brief says how to watch it and what is wrong with it.

### C. What the shaping run left broken

**Why.** Each of these is something a judge or a user would hit. Address every one.

**The board costs attention.** In study 2 it took about twice the outline's modelled seconds.
- Make it earn its place:
  - ask only what the repo cannot answer (precheck answers the rest, on live Nano within the cap if it helps);
  - take defaults unless they are changed;
  - one keystroke per answer;
  - no board at all when there is nothing to ask.
- Re-measure with a new registered study on stand-ins, set up like study 2 so the two compare.
- Then set the default by the evidence. The board is on by default only if it costs no more than the outline for the same correctness. Otherwise it appears only when there is a question the repo cannot answer.
- Write the decision.

**The replays that kept spinning.** Find the cause and fix it. Prove it with a test that closes the terminal under a running `graphene demo`, a running `watch` and a run's executors, and asserts every process is gone within seconds. Nothing Graphene starts may outlive what started it.

**The keychain.** No test can reach the real keychain: add a guard that fails any test that tries, locally and in CI. Only a person's command writes a key.

**The rough edges.** `walks.md` still has 54 of its 72 open, three of them half-fixed. Fix every real one, and close the rest with a reason.

**The hook under load.** Its 60 ms budget fails at a load of about 30. Find where the time goes and cut it. Lane D adds work to the hook and must add none to its time.

**Done when** each has its test and a line in the brief.

### D. The direction, with everything attached

**Why.**
- Alex wants it. It is his 17 September picture: an editable graph where the person changes direction.
- It replaces what he does by hand across `DIRECTION.md`, the directives and `morning.md`.
- Graphene showing the tree of its own build is a demo no one else can give.

**What.**
- **A direction the person authors.** A small tree of goals sits above the plans, and every plan hangs from one of its nodes. The planner may propose direction nodes; only the person accepts them.
- **Everything attached.** The hooks already send every Claude Code session in the repo, worktrees included, to one store. Each session attaches to a node:
  - planners and executors by what they are doing;
  - any other session by the person's choice (a key in `watch`, or a command);
  - otherwise it stays visible as unattached.

  Nothing is inferred into the direction.
- **Status, not a ledger.** The hooks bring up state: alive, idle, waiting on you, the last thing done in one line, the bill. Never a transcript; decision 66 holds. A line that would not help the person decide something is not shown.
- **Seen in the views Graphene already has.** The outline, the tree and the graph, in `watch` and on the page, with status rolling up from plans and sessions.
- **Shared through git.** The direction's text form round-trips and can be committed, so another machine's Graphene reads the same direction. Sessions stay local. Decide which file holds it, and write the decision down.
- **Graphene's own, first.** Author Graphene's direction from `DIRECTION.md`, the directives and the briefs, and attach tonight's plan and every lane's sessions to it.
- **Measured.** Can a person answer "what is waiting on me, what is running, what is next" faster from the direction than from `morning.md`? Use stand-ins, register the study, and measure both ways.
- **An MCP server** only if it is nearly free and read-only. The CLI already serves any agent with a shell.

**Done when** Graphene's own direction is in Graphene with tonight's sessions attached, the study is reported, and the hook's time under load is unchanged.

### E. Ready for the session with Alex

**What.**
- Write `dev/test/LIVE_SESSION.md` on one screen. In order, it lists the registered runs, rung 6, the shaping study with executors and the final recording, each with its command, its cost, its time and what done looks like.
- Dry-run every harness end to end on stand-ins, so only the live calls are new.
- Update `LIVE_DIRECTIVE_DRAFT.md` with what first light taught.

### F. Polish and the closing review

- **Walkers.** Put walkers in the seats of a first-time user, Alex and a judge. They go over the whole path again, live wherever the cap allows, and file every rough edge; fix them.
- **The closing review, from 06:00, as before.**
  - Adversaries go over the live paths and keys, the board, the direction, the teardown and the claims.
  - A skeptic reproduces each finding.
  - Each fix has a test.
- **The docs.** Update README, HOW_IT_WORKS and HACKATHON.md for everything new. Claims go only as far as what ran, and practice numbers are called practice.

## What not to do

- No registered run, no rung 6 and no final recording: they are Alex's.
- Nothing live past $8 estimated.
- No key printed, searched for, stored, recorded or sent anywhere but Token Factory's API.
- No transcript read, and no ledger of everything.
- Do not touch Alex's working tree, `~/.zshenv`, `~/.claude/settings.json` or the keychain. Never publish or commit the run directories that hold the cards' briefs.
- No tag, PyPI release, Devpost entry, Pages switch, About text, merge to `main` or history rewrite.
- No claim that `field.md` forbids, and nothing from a stand-in shown as live.

## The decisions that are yours

These are yours to make:
- the opening for agent practice, and the night ledger;
- the board's default, by the evidence;
- the direction's model and its file;
- how a session attaches;
- the teardown fix;
- which prototypes stay.

Each goes in `DIRECTION.md` from 101, with its evidence.

## Ground rules

- Commits are many and small: one logical change each, green before it is pushed, pushed after each milestone.
- The PR description stays current.
- Never push `main`, and never force-push.
- Keep the machine awake.

## The brief: the top of morning.md, and the only thing Alex reads at 08:00

Keep it current at every milestone, so that a run cut off early still leaves a true brief. At most twenty lines, and no paragraphs:

1. **Watch first:** the rough cut, and how to play it.
2. **What ran live:** each rung, pass or fail, and the bill against $10.
3. **New tonight:** five lines at most, each with the command that shows it.
4. **Decide:** at most three questions, each with your default.
5. **Broken or risky:** three lines at most.

Below the brief go the decisions, the evidence, the screens, the state of every branch and the rollback SHA.

## When to stop

- At 07:15, start nothing new.
- By 07:45, everything is merged into `first-light` and green.
- By 07:55, it is pushed.

A lane that is not done stops where it stands, with its state written down.

Now go. Let Graphene see the real sky, and leave nothing broken that you could have fixed.
