# The demo page

`docs/demo/index.html` is a run's record as one read-only web page: the goal, the plan's tree,
each leaf's state, and each leaf's record. It is what `graphene ui` shows on the machine where the
run happened, with its data inlined, no token and no way to write. It is drawn from the
repository's `.graphene/` store alone, so a run whose executors keep no records of their own
(whatever `graphene run --with` starts, other than Claude Code) is drawn in full. Until the demo
run has been made, there is no `index.html` here, and the workflow below refuses to publish.

## Making it

In the repository the run happened in, once `graphene run --parallel N` has finished:

    graphene ui --export <this repository>/docs/demo/index.html

That is all. The page is one file (about 330 KB, most of it the page's own script): its script,
its style and the run's data are inlined, and it fetches nothing, so any static host serves it.
`tests/test_demo_export.py` makes one from a real `graphene run --parallel 2` with a scripted
executor and reads it back.

What a leaf's record on the page holds, from its log: who started it, each attempt, each refused
`done` with the paths it was refused over, each check Graphene ran by its command and result, what
had changed when it finished, that it landed and which paths it brought, why it was handed back, and
what git said when it passed and its merge was refused. A leaf that came back reads `came back` and
is listed as waiting on you, as in the terminal.

What stays on the machine: what a check printed (a check is named by its command and its result),
and anything after the first line of a reason (the reason `graphene run` hands a leaf back with
quotes the refusal, and a failed check's output is under it); the page's token; the log's absolute
paths (the leaf's worktree, the executor's output file, the checkout it was merged into); and the
checkout's path wherever a sentence names it (git's refusal of a merge, a file refused in a leaf's
worktree): the page says the repository's name there instead.

Read the page before you publish it. It does carry the person's name as the actor of their own
acts (`GRAPHENE_PERSON`, else `USER`), the first word of `--with` as the executor's name in every
act of its own and of the run's (its command name, never its path), and every check command as it
was written: a check that names an absolute path outside the repository (the Python it runs, say)
or a secret publishes it.

The page's second screen, the record of a run, is drawn from Claude Code's sessions only. When the
repository has none, that screen is shut and its button says why.

## Hosting it

`.github/workflows/pages.yml` publishes this directory to GitHub Pages. It runs only when someone
starts it (Actions, then Pages, then Run workflow), and stops before publishing unless
`docs/demo/index.html` is there and is a read-only export. Pages is not enabled for this
repository: enabling it (Settings, then Pages, then Source: GitHub Actions) and running the
workflow are the owner's. The page would then be at `https://alex-lop.github.io/Graphene/`.

## The replay in the terminal: `graphene demo`

`graphene demo` replays a recorded run in `graphene watch`, as it happened, for someone with no key.
It needs no key, no network and no Docker, only git, and nothing in it runs. The top line says it is
a replay, what made it, and the day. What made it is read from the run: "as it ran, live" only when
every model call it logged (each `usage` row) says it went to Token Factory, "a scripted stand-in, not
Nemotron" when any did not or does not say, and "a run with no model calls on record" when it logged
none. A key that would change the plan or start anything (`y d e E a A s R r P w b n : x u V`) says
"a replay: nothing runs here" and does nothing; moving, folding, `/`, Enter (the record), `l` (the
output) and `?` work. A wait longer than 3 s is played in 3 s, and the top line says by how much (`×10:
a wait, cut`). At the end every fold opens (as `zR` opens them), so every leaf is a row, and the
screen stays on that last frame and says so. `graphene demo --once` prints the last frame instead, as
`graphene watch --once` prints a plan. The replay has a temporary repository of its own, removed when
the screen closes, when its terminal closes, or on TERM.

A recording is the plan's store over the run, not the model's calls, which a replay would have to
run: the nodes, their log, the settings the screen reads, each executor's output, and what git
tracked. The repository's path is written `{repo}` and the home directory `~`; the key and the
project in the environment, a sandbox's image, and anything shaped like a key are taken out.

A replay does not have the repository's git history. A leaf's record there counts what git said had
changed when each hold ended, which the log keeps, and says its commits cannot be read; the live
record counts the commits too.

The recording Graphene ships, `src/graphene_map/demo.jsonl`, was made on 25 September 2026 with the
scripted stand-in, because no key existed that night: `docs/proof/nemotron.sh` on a tiny repository,
as `tests/test_demo_script.py` runs it. To record the live demo run in its place, from this
repository's root with `NEBIUS_API_KEY` set:

    RECORD=$PWD/src/graphene_map/demo.jsonl docs/proof/nemotron.sh

or, in the repository of any run, `graphene demo --record <file>` in a second terminal until Ctrl-C,
with the run's `NEBIUS_API_KEY` in that terminal too (its value is what the recorder takes out). What
that terminal is pointed at does not decide what the replay says made the run: the run's own `usage`
rows do, so a run against the stand-in replays as the stand-in's wherever it was recorded from.
Read the file before committing it; `uv run pytest tests/test_demo.py` checks it holds no path and
nothing shaped like a key, and names the leaves of the recording it expects.
