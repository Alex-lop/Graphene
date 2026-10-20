# The video: under three minutes, a pitch on the cockpit

A draft for Alex. The Devpost rules want a public YouTube video under three minutes, with footage of Graphene
working, that says how Nebius Token Factory and NVIDIA Nemotron are used; judges need not watch past three
minutes, and the organisers' advice is to treat it as a pitch, not a tutorial. Submissions close Friday 30
October, 10:00 PT. So this is a pitch in your voice, over the cockpit: the idea first, then a real Nemotron run on
Token Factory, the moments where you steer it, and what it cost.

Most of the footage costs nothing. The repository keeps recordings of live Nemotron runs on Token Factory, and
`graphene demo` replays them in today's cockpit, with "as it ran, live" and the day on the top line. Only the
scenes marked *live* spend your key.

**Kinds.** *voice*: your narration over a frame from the scene after it. *replay*: a recording replayed with
`graphene demo <file>` from the root of a clone (the recordings are in `tests/recordings/`, not in the wheel);
keep its top line in the frame. *live*: your own run on your key, in a terminal of yours. *script*: `graphene demo
--cheat`, a script and not a model, as its own screen says.

| # | Scene | Length | Kind | On screen | Narration |
| --- | --- | --- | --- | --- | --- |
| 01 | the idea | 12 s | voice | The cockpit paused on a plan: `graphene demo tests/recordings/loop-nemotron-2.jsonl`, space at change 4 (two tasks under the goal). | "The limiting factor for software won't be the next model or harness. It's going to be you, and the direction you give it." |
| 02 | the gap | 10 s | voice | The same replay playing on: agent 1's row comes alive. | "Tell an agent what you want and it fills in the blanks itself. You find out what it guessed in the diff." |
| 03 | Nemotron on Token Factory | 14 s | live | `graphene key check` (it says Token Factory was reached), then `graphene init --planner nemotron --executor nemotron`: the planner and executor lines name the Nemotron models from Token Factory's list. | "Graphene is the plan you and your agents share. Here the agents are NVIDIA Nemotron on Nebius Token Factory: Ultra plans, Nano does the tasks, Super takes a retry." |
| 04 | the ask | 14 s | live | `graphene ask "…"` with the paragraph below; `asking the planner (nemotron)…`; cut the wait; the proposed tasks and the planner's bill at list price. | "I say what I want in one paragraph. Nemotron 3 Ultra reads the repository through Token Factory and proposes tasks, each with the files it may change and a check." |
| 05 | what needs you | 14 s | live | `graphene watch`: questions and proposed tasks on top under "need you"; `⏎` on each. | "What the code can't tell it, it asks me first, with a default. Everything that needs me is on top, and Enter takes it." |
| 06 | a row an agent | 14 s | live | `R` (and `y`, Enter, when it asks): the ready tasks' rows turn amber, each with its agent's number, files touched of allowed, checks passed and seconds quiet. | "R runs every ready task, each a Nemotron Nano agent in its own worktree. One row an agent: what it touched, what it proved, how long it's been quiet." |
| 07 | the task that came back | 16 s | replay | `tests/recordings/loop-nemotron-2.jsonl` at change 91: agent 1's row red, its reason in its own words, `⏎ try again`, `w widen it`; `.` to change 92. | "This is a real run from October. On its second try, on Nemotron Super, agent 1 needed a file outside its task, so it came back saying why. w widens it to that file." |
| 08 | tell | 12 s | live | Only if a task came back in your take: `t`, one line, Enter; the line under its row; then `⏎`. Else leave the scene out and give 07 the time. | "t tells an agent one line. Claude Code hears it with its next write, and a Nemotron agent the next time its task starts." |
| 09 | the fault's owner | 12 s | replay | The same recording at change 297: agent 2 came back, naming `normalize/fields.py`, agent 1's file; `r reopen`; `.` to change 298, agent 1 reopened with that reason. | "Agent 2 says the fault is in agent 1's file. r reopens the task that owns it, and tells it why." |
| 10 | proven, with a bill | 14 s | replay | `tests/recordings/loop-nemotron-take-2.jsonl` at its end, 3/3 proven; `i` on the first task: its model, NVIDIA-Nemotron-3-Nano-30B-A3B, its Sandbox, its bill. | "Done means proven: Graphene ran each task's check itself. Token Factory reports every call's tokens, so every task has a bill. This one cost less than a tenth of a cent." |
| 11 | the graph and the map | 14 s | replay | `g` on the same replay: the plan as boxes and arrows. Then the first recording at change 150, `m`: the folders agent 1 may write. | "g draws the plan as boxes and arrows, what waits on what. m shows the folders each agent may write, and nobody else's." |
| 12 | the locks | 12 s | script | `graphene demo --cheat`: the seven moves and the closing line. | "A script plays an agent that tries seven ways round the locks. Six are refused, one is flagged, and none gets through." |
| 13 | the end | 8 s | voice | `github.com/Alex-lop/Graphene` and `uvx --from graphene-map graphene demo`. | "You stay the one who decides where it goes. Graphene is open source; try it in one line." |

166 seconds planned, fourteen under the limit for a slow line. The narration is at most 2.5 words a second of its
scene, so it can be said in the time. Name Token Factory and Nemotron aloud as written (scenes 03, 04, 06 and
10); the graph flows into your goal at the right, so scene 11 may say "into my goal".

## Recording it in one sitting

About an hour. Screen-record a terminal of your own at 120x36 (QuickTime, File, New Screen Recording, the
terminal's window), record the narration after, and cut each scene to its length.

Every command uses the `graphene` on your PATH: `graphene watch --help` should list `--classic`, which only the
cockpit's version has.

**1. The replays, at no cost** (from the root of a clone of the repository):

    graphene demo tests/recordings/loop-nemotron-2.jsonl --speed 10       # scenes 01, 02, 07, 09, 11
    graphene demo tests/recordings/loop-nemotron-take-2.jsonl             # scenes 10, 11
    graphene demo --cheat                                                 # scene 12

The first is a live run of 9 October (Ultra planned, Nano worked, Super on a retry): agent 1 comes back at change
91 and is widened, agent 2 comes back at change 297 saying the fault is in agent 1's file, and agent 1 is
reopened. Space pauses, `.` steps one change, and the top line counts them (`91 of 322`). The second is the run
of 9 October in which Nano landed all three tasks on their first attempts in Sandboxes; `i` on a task shows its
model and bill, and Esc comes back. Keys that would change the plan say "a replay: nothing runs here", so nothing
you press can spend.

**2. The live take, on your key** (scenes 03 to 06, and 08), after `graphene key set` once:

    python3 dev/test/make_task.py feeds ~/graphene-film/take-1 && cd ~/graphene-film/take-1 &&
    graphene key check &&
    graphene init --planner nemotron --executor nemotron &&
    graphene ask "Look at this repo. I want the new Northwind XML feed to load the same way csv and json already do: same load command, same JSONL out. Prices in that feed are already in cents. The summary line at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch vendored or legacy files that aren't ours this week." &&
    graphene watch

Then `⏎` on each question and each proposed task, `R` (and `y`, Enter, when it asks), and let it run. Run it in
your own terminal, not in a Claude Code session: an agent's process is refused a live call unless you opened it.
Give each take a directory of its own (`take-2`, `take-3`): `make_task.py` refuses one that is not empty, and
the `&&`s then stop the take there, before an init and a paid ask in whatever directory the shell is in.

**3. What a take cost before** (list price, from the records):
- 2 October: $0.38 for each of the two takes that ran to the end, the planner $0.30 to $0.37 of it
  (`dev/test/first-light.md`).
- 8 October: about $0.10 for the take that landed both its tasks, and $0.46 and $0.70 for the two others that
  ran clean (`dev/process/timeline/takes.md`).
- 9 October: $0.11 with the planner for the take that landed all three tasks (`dev/process/loop/takes.md`).
- Ultra does not always answer with a plan: 35 of 40 asks did on 9 October, and an ask without one still cost
  $0.06 to $0.43 (`dev/process/loop/asks-round2.md`). Budget three takes, about $2.

If your take puts up no question, scene 05 shows the proposed tasks alone, or take the question rows from
`graphene demo`, the replay Graphene ships, with its top line ("a scripted stand-in, no model ran") in the frame.
If no task comes back, leave out scene 08: the replay's scene 07 carries the moment.

## Filming it with build.sh

`dev/demo/build.sh` films each scene from its tape in `dev/demo/scenes/`, one tape a scene, and lays the
narration column of this table under the footage as subtitles. The tapes were written for the September screen
and still press its keys (`Tab`, `gg`, `E`, `/running`), so they do not film this table yet: until they are
written again, record by hand as above. `build.sh` refuses an agent's shell, since a live take spends your key.

## Before you upload

- Under 3:00, public on YouTube, its link in the Devpost form.
- Token Factory and Nemotron said aloud and seen on screen (the init line in 03, the model in 10).
- Every replay keeps its top line in the frame. Say "a real run" only over a recording whose top line says "as it
  ran, live"; the replay `graphene demo` ships says "a scripted stand-in, no model ran".
- The cheat is a script, not a model, and the narration says so.
- Nothing `dev/launch/claims.md` rules out: never "broadly tested live", never "the only".
- The key never on screen: `graphene key set` reads it from a hidden prompt.
- Captions: YouTube makes them, or paste the narration column as a subtitle file.
