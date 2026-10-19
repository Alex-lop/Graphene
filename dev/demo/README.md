# The demo

## The replay in the terminal: `graphene demo`

`graphene demo` replays a recorded run in the cockpit, `graphene watch`'s screen, change by change, for
someone with no key. It needs no key, no network and no Docker, only git, and nothing in it runs. It opens
on the plan, and its news line narrates: what the board asks and what you answered, what each agent does,
why a task came back, what landed. The top line says it is a replay, what made it, the day, and which change
it is at (`3 of 28`). What made it is read from the run: "as it ran, live" only when every model call it
logged (each `usage` row) says it went to Token Factory, "a scripted stand-in, no model ran" when any did
not or does not say, and "a run with no model calls on record" when it logged none. In a stand-in's replay
the names the run gave the model, the planner and the executor read as the stand-in's (`run:stand-in`,
`stand-in-Nano`), never as Nemotron's. A key that would change the plan or start anything says "a replay:
nothing runs here" and does nothing; moving, `i` (details), `g` (the graph), `m` (the map) and `?` work.
Each change stays on the screen for 2 s at least, and a wait longer than 3 s is played in 3 s; `--speed 2`
plays it twice as fast. Space pauses (`paused at 3 of 28`) and plays on, `.` shows the next change and stays
paused, and `r` plays it again from the start. At the end the screen stays on the last frame and says so
(`ended: last frame`). `graphene demo --once` prints the last frame instead, as `graphene watch --once`
prints a plan, fitted to the terminal's width, its last rows headed "the end of the run's log";
`graphene demo --classic` replays it in the older outline, whose top line also says how much a long wait
was cut (`×10: a wait, cut`). The replay has a temporary repository of its own, removed when the screen
closes, when its terminal closes, or on TERM.

A recording is the plan's store over the run, not the model's calls, which a replay would have to
run: the nodes, their log, the settings the screen reads, each executor's output, and what git
tracked. The repository's path is written `{repo}` and the home directory `~`; the key and the
project in the environment, a sandbox's image, and anything shaped like a key are taken out.

A replay does not have the repository's git history. A leaf's record there counts what git said had
changed when each hold ended, which the log keeps, and says its commits cannot be read; the live
record counts the commits too.

The recording Graphene ships, `src/graphene_map/demo.jsonl`, was made on 19 October 2026 (UTC) with
the scripted stand-in: `dev/proof/nemotron.sh` on a tiny repository, as `tests/test_demo_script.py` runs
it. Its planner puts up a question, an assumption and a leave-out, and a plan of two sub-goals and four
tasks; the script takes each item with the one key a person presses (`BOARD`), and the question's default
adds a sentence to its task's goal. Three agents start at once. Agent 1 is stopped writing `words.py`,
which the person took from greet's scope, and comes back saying so; it is widened and tried again as
agent 1. The fourth task waits on two, greet and farewell, and starts once both have landed. It is made
again from the stand-in with `RECORD_DEMO=src/graphene_map/demo.jsonl uv run pytest
tests/test_demo_script.py`. To record the live demo run in its place, from this repository's root with
`NEBIUS_API_KEY` set:

    RECORD=$PWD/src/graphene_map/demo.jsonl dev/proof/nemotron.sh

or, in the repository of any run, `graphene demo --record <file>` in a second terminal until Ctrl-C,
with the run's `NEBIUS_API_KEY` in that terminal too (its value is what the recorder takes out). What
that terminal is pointed at does not decide what the replay says made the run: the run's own `usage`
rows do, so a run against the stand-in replays as the stand-in's wherever it was recorded from.
Read the file before committing it; `uv run pytest tests/test_demo.py` checks it holds no path and
nothing shaped like a key, and names the leaves of the recording it expects.

## The video's rough cut: `dev/demo/build.sh`

`dev/demo/build.sh` films the demo run of `dev/proof/nemotron.sh` scene by scene with VHS, in real
time, as `dev/demo/STORYBOARD.md` lays it out, and assembles `dev/demo/rough.mp4` with the narration
as a subtitle track and `rough.srt` beside it. Every wait for a model is cut between two scenes and
labelled on screen with its length. It writes `rough.mp4` only when the take's own recording says the
run was live (`graphene demo <run.jsonl> --once`: "as it ran, live"); `--rehearsal` films the scripted
stand-in into `rehearsal.mp4` instead, with "REHEARSAL: scripted stand-in, not live" on every frame.
The storyboard says how to film a take. Takes and videos are git-ignored.
