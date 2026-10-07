# The demo

## The replay in the terminal: `graphene demo`

`graphene demo` replays a recorded run in `graphene watch`, change by change, for someone with no
key. It needs no key, no network and no Docker, only git, and nothing in it runs. The top line says it
is a replay, what made it, the day, and which change it is at (`3 of 12`). What made it is read from
the run: "as it ran, live" only when every model call it logged (each `usage` row) says it went to
Token Factory, "a scripted stand-in, not Nemotron" when any did not or does not say, and "a run with
no model calls on record" when it logged none. In a stand-in's replay the names the run gave the model,
the planner and the executor read as the stand-in's (`run:stand-in`, `stand-in-Nano`), never as
Nemotron's. Before the first proposal the pane says what the planner was asked. A key that would
change the plan or start anything (`y d e E a A s R P w b n : x u V`) says "a replay: nothing runs
here" and does nothing; moving, folding, `/`, Enter (the record), `l` (the output) and `?` work.
Each change stays on the screen for 2 s at least, and a wait longer than 3 s is played in 3 s, the top
line saying by how much (`×10: a wait, cut`); `--speed 2` plays it twice as fast. Space pauses (`paused
at 3 of 12`) and plays on, `.` shows the next change and stays paused, and `r` plays it again from the
start. At the end every fold opens (as `zR` opens them), so every leaf is a row, and the screen stays
on that last frame and says so. `graphene demo --once` prints the last frame instead, as `graphene
watch --once` prints a plan, fitted to the terminal's width, its last rows headed "the end of the
run's log". The replay has a temporary repository of its own, removed when
the screen closes, when its terminal closes, or on TERM.

A recording is the plan's store over the run, not the model's calls, which a replay would have to
run: the nodes, their log, the settings the screen reads, each executor's output, and what git
tracked. The repository's path is written `{repo}` and the home directory `~`; the key and the
project in the environment, a sandbox's image, and anything shaped like a key are taken out.

A replay does not have the repository's git history. A leaf's record there counts what git said had
changed when each hold ended, which the log keeps, and says its commits cannot be read; the live
record counts the commits too.

The recording Graphene ships, `src/graphene_map/demo.jsonl`, was made on 29 September 2026 with the
scripted stand-in: `dev/proof/nemotron.sh` on a tiny repository, as `tests/test_demo_script.py` runs
it. Its planner puts up a question, an assumption and a leave-out; the script takes each with the one
key a person presses (`BOARD`), and the question's default adds a sentence to its leaf's goal. To record the live demo run in its place, from this
repository's root with `NEBIUS_API_KEY` set:

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
