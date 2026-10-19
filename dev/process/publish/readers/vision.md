# vision: what Alex is building, and where the repo says something else

Line numbers are for the tree at `921834de` (`<scratch>/work`).

**What I read:** the video transcript, website.md, his uncommitted README (the diff and the whole file), README.md, dev/DIRECTION.md (the head, "Your answer, 22 September", decisions 137-195), dev/ui/IDEAS.md, the last three briefs in dev/process/morning.md, PRODUCT_THESIS §0, §2-4, §12 and §14, HACKATHON.md (skimmed), dev/launch/*, CHANGELOG Unreleased, `src/graphene_map/cockpit/`, and the memory notes from 1 and 10-18 Oct.

**What I ran:**
- I stepped the shipped demo frame by frame, headless, in my own clone (`agents/vision`, no remote).
- I cut the README's GIF into frames (ffmpeg, one frame every 6 s, 50.88 s long).
- I read PyPI's JSON.
- I ran the README's two try-it commands from PyPI with `uvx --isolated` in an empty scratch directory.

## (a) The idea, in his words

1. **The limit now is the person, not the model or the harness.**
   - "The limiting factor for innovation in software development won't be the next model or harness ... It's going to be you, the human, that drives innovation forward." (video, 17 Oct)
   - "At a high level, you are still the only thing that matters when building." (the video's description)
2. **What's scarce is direction. Without it the agent guesses, and you find out late.**
   - "I believe the limit on building software won't be tokens or cost. It'll be the human direction it takes. If you don't say which direction the application should go, the agent has to infer most of it, and you find out what it inferred in the diff. Graphene tries to bridge that." (his own README text: commit 939e98af, and his uncommitted edit)
3. **The skill is steering the work from above, whatever agent tool you use.**
   - "the limiting factor wasn't necessarily the model I was using. It was more so my ability to orchestrate and actually implement the plan at a high level."
   - "whether your model is Astra, Opus, Fable, Quen, or even Argon ... it doesn't really matter" (both from the video)
   - On 16 Oct he said to learn from jcode's swarm screen "but as a controller, not a harness" (a controller steers the agent; a harness is the agent's own loop).
4. **Graphene is the bridge: you see what your agents are doing, and you steer them toward what you meant.**
   - "Trying to make the collaboration w/ Claude better so you have an idea of what's going on with your agent" (his GitHub description)
   - "help guide you and the agent toward that perfect idolized application you actually had in mind from the start" (c70302b7, 15 Oct)
   - "a visual tool for seeing what to build next with an AI agent" (website)
5. **AI drives ambition rather than replacing people, and there are no magic numbers.**
   - "if you shift your perspective of seeing AI as something that will replace us to something that will drive human ambition, it kind of changes the narrative" (video)
   - "not claiming it magically saves 397% of your tokens" (c70302b7); the website says it is not a guaranteed token saver; the README says "Honestly, it's early".
   - His Terence Tao line: "The helicopter gets you there faster, but the hiker learns the terrain, which paths are dead ends." My reading, not his: Graphene keeps you knowing the terrain (the plan, who touched what, each dead end with its reason) while the agents do the climbing.

**Already in the repo, and it matches:**
- dev/DIRECTION.md:13-14 says: "the shared plan between a person and their coding agents: a graph of the work, which both can see, which the person shapes, and which the agents are held to."
- His own answer of 22 Sep (DIRECTION.md:187-196): the paragraph stays the input, the agent proposes the tree, and the person reads and prunes.

## (b) What it must feel like in the hand

- **The cockpit is home.** One screen beside your agent's terminal. A session should never need the CLI: `y`, `R`, `:ask`, `t`, `w` and `x` are all there.
- **Your words on top, the agent's guesses under them, before any code.** The top line is your sentence. What the agent inferred comes back as questions with a default.
  - The demo already has the frame that *is* the idea: `? a --name flag; nobody asked for one  ⏎ agree`. That is scope creep caught before the work.
- **Numbers, glyphs and verbs; you read only when you ask (`i`).** IDEAS.md:1 is titled "talking to your agents with almost no text".
  - He cut the five-row digits ("the big is kind of unnecessary, maybe just make it scrollable?"). So: calm, scrollable, fits 80x24.
- **One word for one thing.** task, proven, need you, came back, tell, heard. Agents get a number, and the same number appears on the row, on the graph box, on the map bar, and in `tell 2:`.
- **The rhythm of a session (his loop):**
  1. You say where it should go: a paragraph in Claude Code, or `:ask`.
  2. You see what it understood (tasks, plus questions with defaults) and shape it with single keys (`⏎`/`y`, `d`, `1-9`, `a`, `e`).
  3. You watch them work. Every row shows it is alive: pace, `✎` files touched of allowed, `✓` proofs, `⏸` seconds quiet.
  4. You talk to them mid-run. After `t` the row says "heard", not "done".
  5. A task that hits an edge comes back with its reason, in its own words, and one-key answers: `w` give it the file, `b` a sibling, `r` reopen the owner, `x` hand back.
  6. Done means proven. Graphene ran the check, the bar fills, and it lands as one merge you can revert.
  7. `g` shows the plan's shape from your goal down, with the agents on the boxes; `m` shows who may write where.
- **Never surprised, never oversold.** The line under the rows names the command each key ran. A replay says "no model ran".

## (c) Where the product and the README contradict or bury the idea

Ordered by severity.

**High**

1. **What a stranger installs is not what the README shows.**
   - PyPI's latest is `0.5.0`, uploaded 2026-10-13 (`curl https://pypi.org/pypi/graphene-map/json`).
   - README.md:27 is `uvx --from graphene-map graphene demo`. In an empty directory, `graphene --version` prints `graphene 0.5.0`, and `demo --once` prints the old outline (`replay · a scripted stand-in, not Nemotron · 2026-09-29`).
   - README.md:32 is `graphene demo --cheat`, which prints `graphene demo: no such option: --cheat (Possible options: --help, --once)`.
   - README.md:66 `uv tool install graphene-map` gets the same 0.5.0. So the GIF, the stills and "What you see" (README.md:34-47) describe a screen no PyPI user gets.
   - pyproject.toml:7 says 0.5.1, which is still the old screen (18 Oct brief). This build changes the default screen, so the next tag is 0.6.0.
2. **The README contradicts his own latest hand edit.**
   - His `README.md` was last saved 2026-10-16 17:31:23 -0400 (`stat`). That is 91 s after the run's last commit, 3bb075a6 (17:29:52), and after 7e5bad17 (01:08), which had put his long why at the top.
   - Text-wise, his edit is his own 15 Oct "revert readme" (939e98af), with three changes:
     - every HTML wrapper turned into plain markdown;
     - the short "Why I built this" moved to the bottom, in bold;
     - a stray quote typed into "direct"ion".
   - The `diff` of the two, tags stripped, shows only those changes. Both versions have 703 visible words.
   - Today's README does the opposite:
     - HTML header at :1-10;
     - the 180-word long why at the top (:12-16), above the headline;
     - no Cost bullet at :55-59;
     - 899 visible words (tags, link targets and markdown marks stripped, then `wc -w`).
3. **The pictures bury the idea: the person's direction never appears.**
   - `docs/assets/cockpit.png` (README.md:45) opens with `no goal yet`, plus the recording id `plant-claude-3`, a raw `run graphene node release e2e-xml --wants normalize/fields.py --why '…` in the tail, and `e2e-xml attempt` in the status line.
   - `docs/assets/map.png` (README.md:47) shows `TERRITORY 0 of 30 files may be touched (0%)`, with every folder `nobody`. The map exists to show who may write where, and this picture shows no one.
   - The GIF (README.md:34) opens on `no goal yet / Nothing is planned yet`. The moment the idea lives in (the questions with defaults, step 2 of 16) gets a single `Sleep 2s` (docs/assets/watch.tape:29). The person's accept is never shown as the person's act; the news line just says `friendly accepted · greet accepted · farewell accepted`.

**Medium**

4. **Agent names don't stay with their task.** In the shipped demo the same task, `greet says hello`, is `tern` in steps 7-10 and `wren` in steps 13-16 after its retry. It shows in the GIF too.
   - That contradicts IDEAS.md:73 ("a task keeps its name") and read.py:297-299 ("a leaf has the same name running, back, in review and done").
   - Cause: `agent_key` (read.py:296) is the session, and a retry is a new session. This is the reason to number tasks, not sessions.
5. **The GIF shows a false `1 OUTSIDE` right after the person widened the task.**
   - At steps 13-14 the row reads `✎2/2 ✓0/1 1 OUTSIDE`, while the scope is `['app.py', 'words.py']`.
   - Cause: `m.seen` (read.py:279-293) is keyed by task id only. It keeps the first attempt's `outside=['words.py']` for up to `GIT_EVERY` (5 s, read.py:35).
   - Checked: clearing `app.model.seen` before step 13 gives `outside []`. On screen, the headline promise ("stays inside") appears to break, in the hero GIF.
6. **The graph Alex loves is at its thinnest.**
   - The cockpit and `g` take leaves only (read.py:84; flow_view.py:19-22). The goal and the sub-goals (the "why", your direction as a tree) are never drawn.
   - The demo's graph is two boxes with no arrows. The 0.5.0 outline showed `a friendlier app → say hello → greet / bye`.
   - app.py:201 always prints `amber lane = a retry loop (bounded) · ◀▶ two-way`. Yet `extra_edges` is never written anywhere in `src/` (grep), so a real plan never draws either one.
   - IDEAS.md:78 lists "sub-goal boxes in the flow view" as not done.
7. **The pitch lines disagree, and none carries the idea or the cockpit.**

   | Where | Says |
   | --- | --- |
   | pyproject.toml:8 | "Keep Claude Code and Codex inside the files you agreed to…" |
   | PyPI 0.5.0 summary | "A plan you and your coding agents share…" |
   | GitHub description (his words) | collaboration: "have an idea of what's going on with your agent" |
   | Website | "seeing what to build next" |
   | dev/launch/pitches.md, show-hn.md | containment only; written before the cockpit existed |

8. **"What you see" (README.md:43) is a 98-word key manual.** That goes against "docs short, product low-text". The `?` help already lists the keys.
9. **"On your project" (README.md:65-74) teaches a six-command CLI routine**: install, init, ask, watch in a second terminal, `plan accept`, `run`. All of that is now one or two keys in the cockpit (`:ask`, `y`, `R`). The README doesn't say the cockpit is where you work.

**Low**

10. **Engine plumbing in the person's view:**
    - tail lines `run graphene node done farewell`;
    - replay news `settings recorded`, `greet usage`, `friendly rolled up` (replay.py:53 falls back to `D.what`);
    - details `model stand-in-Nano`, `bill $0.0003 at list price…`.
11. **The cockpit mixes "task" and "leaf"**, against IDEAS.md:72 ("plain words on the new screens"):
    - help.py:24, :26, :27;
    - app.py:313 (`select a task to run … R every ready leaf`);
    - verbs.py:126, :238, :240.

    The README does the same: "task" at :43, "leaf" at :51, :74, :89.
12. **README.md:74 says "`d` drops a leaf"**, but the cockpit's `d` drops a proposal or a question only (help.py:19).
13. **His Cost bullet, if it comes back, has one stale clause**: "nothing caps the total yet". `graphene run --help` now has `--max-usd: Start no attempt past these dollars; one going is not stopped` (run.py:439). The "$2 an attempt" is still true (run.py:50).
14. **docs/HACKATHON.md is the largest file in docs/** (6,394 words). It is a Nebius × NVIDIA Devpost draft, while decision 163 (DIRECTION.md:1686) says `docs/` is for using Graphene. HOW_IT_WORKS.md:256 and :287 link to it, and tests/test_doc_claims.py:17, :35 and :39 read it.
    - The repo never names the hackathon he is entering now; only the checkout folder does (`AllThingsAgenticHackathon`).
15. **Small picture issues:**
    - In a Quick Look render, the four arrow labels of `loop-ink.svg` (`ui-monospace`) overlap the boxes. Not checked in a browser.
    - Without the `<picture>` wrapper (his plain-markdown edit), part of `graphene-mark-ink.svg` is `#141413`, dark on GitHub's dark theme. `loop-ink.svg` draws its own `#F0EEE6` background, so it is fine. Not checked in a browser.

## (d) Decisions that bind tonight, and the ones now overridden

**These stand.** Newest first.

1. **18 Oct (tonight):**
   - The watch and the README "finished and ready to be published".
   - The overarching idea first; "the best repo for agentic workflow".
   - Names become numbers.
   - He is asleep, so nothing can wait on his accept.
   - About 50 commits for him to read; relentless.
2. **17 Oct:**
   - The cockpit replaces the watch ("may be just ok").
   - "Focus on making the UI look good and not getting blocked."
   - "Fix the readme to reflect this", so re-shooting its pictures is in scope.
3. **16 Oct direction** (memory ui-direction):
   - Close the gap between what you mean and what the agents do, through the watch's screen.
   - A controller, not a harness.
   - Docs short, product low-text.
   - No USD, cost-cap or demo *features* ("maybe later").
   - The graph idea: give an agent a graph, no LangGraph (IDEAS.md:49-55). Execution graph first, intent graph after (IDEAS.md:74).
4. **16 Oct morning:** "not try and do too much". Calm and small; no big numbers.
5. **His own hand, 16 Oct 17:31:**
   - plain markdown;
   - a short "Why I built this" at the bottom;
   - the Cost bullet back;
   - the headline ("stays inside … Done means your tests passed") kept;
   - the honest line kept ("a plain paragraph to the same agent did just as well for less", README.md:91).
6. **IDEAS.md decisions 1, 2, 3 and 5 stand** (IDEAS.md:69-74):
   - an unanswered question takes its default, and says so;
   - one window, many agents;
   - plain words on the screens;
   - execution graph first.

   Tell only arrives with the agent's next write, never as a command ends (IDEAS.md:59-63; measured 12 runs of 14 against 1 of 12).
7. **The 18 Oct brief's one-line decisions**, which he has not flipped (morning.md:36-38):
   - the cockpit is the default;
   - `d` drops only proposals and questions;
   - `y`/Enter accepts one proposal;
   - proposals count as "need you";
   - Enter in a replay says nothing runs.
8. **Standing rules:**
   - Agents propose; only a person accepts (DIRECTION.md:56).
   - The demo stays scripted, with no network (DIRECTION.md:1725).
   - Never claim "the only" tool; no token-savings claims.
   - 30-50 commits authored as Alex with the trailer; nothing pushed.
   - $0 on Nebius; no paid model calls tonight.

**Now overridden:**

- **IDEAS.md:73 decision 4, "Keep the agent names".** Agents become numbers. That touches:
  - code: look.py:8-11 (NAMES), rows.py:97 (comment), lines.py:19;
  - docs: CHANGELOG.md:7 ("its agent's name"), IDEAS.md:15, 36-37, 73;
  - pictures: both stills and the GIF;
  - tests: test_cockpit_look.py:4, 25-28; test_cockpit_read.py:12, 179, 384; test_cockpit_rows.py:35, 48, 71, 107; test_cockpit_territory_view.py:30, 45; test_cockpit_flow_view.py:14; cockpit_scene.py:11, 17; test_cockpit_app.py:174, 180.
  - **One sub-decision to flag:** number the *task* (assigned in plan order and kept through retries), not the *session*. Then "2 is stuck" stays true, and the number is the same on the row, the graph box, the map bar and `tell 2:`. Numbering sessions, the literal reading, would renumber `greet` from 1 to 3 on its retry, exactly as tern became wren.
- **16 Oct: "the README opens with his why" (7e5bad17, his long text).** His own later edit overrides it: short, at the bottom. Proposal: follow the edit, and carry the idea at the top in one pitch line under the title.
- **16 Oct: "no cost talk" in the README** (7e5bad17 removed the Cost bullet). He put it back by hand. Keep it, with the `--max-usd` clause made true.
- **1 Oct: a wBlock-style layout** (centred header, FAQ in `<details>`). His 16 Oct edit drops the HTML; the later act wins.

**Leave alone tonight**, so it doesn't creep in:
- unhiding `graphene direction` (DIRECTION.md:1640, decision 145; reachable as `D`);
- the intent graph (loops);
- any cost feature;
- a live or paid recording.

## (e) Pitch, in his voice

**One sentence:** Graphene is the plan you and your coding agents share: you set the direction, they work inside it, and you can see every one of them while they do.

**Why, in three lines:**
> I think the limit on building software won't be the model or the harness. It'll be you, and the direction you give it.
> If you don't say where the app should go, the agent guesses, and you find out what it guessed in the diff.
> Graphene puts the plan in between, so you and your agents can see it, shape it, and stick to it.

**Alternative 1** (built on the cockpit and his GitHub description): One screen to see what every coding agent is doing, tell it what you meant, and know when it's actually done.
> Models are good enough now. What I kept missing was any idea of what my agents were actually doing.
> So Graphene gives you one screen: a row a task, what needs you on top, one key to tell an agent something.
> And "done" isn't the agent's word for it: Graphene runs your check before anything lands.

**Alternative 2** (from his video, Tao's analogy): Let the agents take the helicopter. Graphene makes sure you still know the terrain.
> Terence Tao said using AI is like taking a helicopter up the mountain instead of hiking: faster, but the hiker learns which paths are dead ends.
> With agents doing the climbing, Graphene keeps the map with you: the plan they follow, the files each one may touch, every time one comes back and why.
> You stay the one deciding where it goes.

Whichever line wins should be the same in README.md under the title, pyproject.toml:8, dev/launch/pitches.md and show-hn.md. The GitHub "About" box is his to change.

## (f) The three things that would most make it feel finished to him

1. **What `uvx --from graphene-map graphene demo` installs matches the README.**
   - Prepare 0.6.0: pyproject, `__init__`, uv.lock, and CHANGELOG Unreleased renamed to 0.6.0.
   - Run the whole suite, `ruff`, `uv build`, and the wheel's demo from a clean HOME.
   - Write the release notes, and leave him the two commands (push, tag).
   - Until he tags, the try-it line can't promise the cockpit from PyPI. Either point it at `git+https://github.com/Alex-lop/Graphene` (main has had the cockpit since PR #49) or live with the mismatch for a few hours. That's his decision.
2. **One README in his voice that leads with the idea and shows it.**
   - Apply his uncommitted edit: plain markdown, the short why at the bottom, the Cost bullet made true. Fix his typo `direct"ion`.
   - Put one pitch line from (e) under the title.
   - Cut "What you see" to about 40 words.
   - Re-shoot both stills with a goal on top, tasks that own folders, numbers instead of animals, and no recording ids.
   - Re-film the GIF so it holds on the "before" frame (the questions with defaults, and "nobody asked for one") instead of the empty opening.
3. **The cockpit says the idea on its first screen.**
   - Numbers per task.
   - Your goal sentence always on top, and as the root box in `g` with the sub-goals under it: the graph idea, and the riskiest piece of tonight.
   - Remove the loop legend (app.py:201).
   - Fix the stale `OUTSIDE` after a widen (read.py:279-293).
   - One word, "task", on every screen.
   - Plumbing out of the rows and the news line.

## Not checked

- Whether real Claude Code sessions usually leave the goal empty (only the 9 Oct recording behind cockpit.png did).
- How either SVG renders on GitHub, light or dark.
- Whether PyPI's renderer keeps `<picture>` and `<details>`.
- Which hackathon he is entering now, and its rules.
- The cockpit's numbers with live agents. I only read the code and the scripted demo.
