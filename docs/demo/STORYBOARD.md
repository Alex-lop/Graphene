# The video: under three minutes, the moment before anything runs

A draft for Alex. The rules (`docs/process/field.md`) ask for a public video under three minutes, with
footage of Graphene functioning, and audio on how Token Factory and Nemotron are used. So the narration
says what runs where, and nothing about why software should be written this way.

Every scene is one VHS tape under `docs/demo/scenes/`, filmed in real time by `docs/demo/build.sh`
against one take of the demo run: rung 7's `docs/proof/nemotron.sh` on feeds, played by a person's keys
in `graphene watch` at 120x36. Nothing is sped up. A wait for the model is waited for, not shortened, and
cut between two scenes; the top line of the next scene says how long was cut and what it was
(`cut: 1 min 32 s of the planner reading the repository and planning`). `build.sh` reads this table: the
narration column becomes the subtitles, spread over each scene's own footage, and the length column is
what each scene is measured against.

**Kinds.** *live*: filmed as it happened, keys and screen in real time. *live, after a cut*: the same,
following a wait that was cut and is labelled on screen. *only if*: filmed only when the screen shows
what the scene is about (a board, a leaf that came back); otherwise the take goes on without it and
`build.sh` says so. No scene is a replay: `graphene demo` of the take's recording is how anyone without a
key watches the same run afterwards.

| # | Scene | Length | Kind | On screen | Narration |
| --- | --- | --- | --- | --- | --- |
| 01 | the opening | 9 s | live | `graphene config` in feeds: the settings, the planner and the executor (Nemotron) and where the key was found, never the key. | "This is Graphene on a small Python repository. The planner and the executors are NVIDIA Nemotron models on Nebius Token Factory." |
| 02 | the ask | 14 s | live | `graphene ask "…"`, the paragraph pasted in the shell, wrapping over three lines and held there to be read; Enter; `asking the planner (nemotron)…`. | "I ask for a feature in one paragraph. Nemotron 3 Ultra plans it through Token Factory's OpenAI-compatible API, reading the repository with read-only tools: list, grep and read." |
| 03 | the plan | 10 s | live, after a cut | What the ask proposed and put up, one line each; then `graphene watch`: the tree, every row `?` proposed, and the board's rows above it. | "It answers with a tree: sub-goals, and leaves that each name the files they may change and the command that proves them done." |
| 04 | the board | 16 s | live; only if the planner asked | The cursor on the first board row, its default and options in the pane; `y` takes the default, and what it changed is said under it. | "What the code cannot tell it, it asks before anything runs: at most three questions or risks, each a row under the goal with a default. One key answers, and the answer goes to that leaf's executor." |
| 05 | the views | 18 s | live | `Tab`: the tree, top-down. `Tab`: the graph, the critical path heavy, and named on the bottom line. `Tab`: the outline again. | "Tab draws the same plan as a tree, and again as a graph of what waits on what. The heavy line is the critical path, and the bottom line names it." |
| 06 | the prune | 14 s | live | `gg`, `E`: the plan as text in vim; one substitution takes `cli/main.py` out of every scope; `:wq`; `y` on the goal accepts the rest. | "Then I prune. In the plan's text I take one file out of every scope, and accept the rest." |
| 07 | the run | 16 s | live | `R`: leaves turn yellow; `/running` puts the cursor on one, and its pane shows the executor, where it runs, its last step and the seconds since. | "R runs every ready leaf, each with a Nemotron Nano executor on Token Factory, in a git worktree of its own. Its tools refuse a write outside the scope, and a leaf is done only when its check passes." |
| 08 | the leaf that came back | 16 s | live, after a cut; only if a leaf came back | `/came back`: the leaf, magenta, its reason and `w  widen …`. `w`, then `R`. | "This leaf needed the file I took away. It comes back with the reason and the fix already written. One key widens its scope, and it runs again." |
| 09 | every leaf green | 8 s | live, after a cut | `gg`: every row green. | "Every leaf has landed, each passed by its own check." |
| 10 | the history | 12 s | live | `q`, then `git log --graph --oneline`: one merge per leaf. | "Each leaf landed as a merge on my branch, with its reason in the message, so git's history reads as the tree." |
| 11 | the bill | 12 s | live | `graphene plan record`: the checks Graphene ran, and the bill of the executors and of the planner at Token Factory's list price. | "Token Factory returns each call's token usage. Priced at the list price, this is what the leaves cost, and the plan." |
| 12 | the direction | 15 s | live; only if `graphene direction` runs | In Graphene's own checkout, `graphene direction`: the goals above the plans, each plan and session hanging from one, with its status. | "Above the plans sits the direction, the goals I write. This is Graphene's own, with tonight's sessions attached to what they are doing, and their status." |
| 13 | the end | 5 s | live | The repository's address. | "Graphene, on GitHub." |

165 seconds planned, fifteen seconds under the limit for the cut labels and the scenes that run long. The
narration is at most 2.5 words a second of its scene, so it can be said aloud in the time; `build.sh`
says which filmed scene is too short for its line.

## What changes with tonight's work

- **The board (decision 84, and lane BOARD tonight).** The board is rows of the outline under the goal:
  `asks`, `risk`, `assumes`, `leaves out`, each with its default; `y` takes the default, `1`-`9` picks an
  option, `p` parks, `d` drops, `Enter` answers in your words. Tonight's changes: a default holds unless
  it is changed, one key answers, and there is no board when there is nothing to ask. Scene 04 presses
  one `y` only, because the number of items is the planner's: when there is no board, the scene is not
  filmed and the take goes from the plan to the views.
- **The views (decisions 85 to 87).** `Tab` goes outline, tree, graph, and past a view that does not fit,
  saying so once. The graph's note names the critical path first, so 80 columns never cut it. On the
  scratch plan the shaping run drew (the four feeds leaves, and the board's new zero-price-product leaf,
  which has no scope or check yet), `graphene plan --view dag --width 80` ends its note
  `critical ━ xml-reader > xml-wire > xml-e2e (3) · none ready · 2 once accepted · 3 wait` here, and
  `… · 2 wait` before the board's new leaf. In the rehearsal the heavy `━` of the path is only a pixel
  heavier than a light line at this size, so the narration points at the bottom line, which names it.
- **The direction (lane D tonight).** A small tree of goals above the plans that only the person
  accepts, with every Claude Code session attached to a node and its state: alive, idle, waiting on
  you, the last thing done, the bill. Scene 12 films Graphene's own, in its own checkout, read-only. Its
  tape types `graphene direction`; when the direction has its own keys in `graphene watch`, the scene
  moves there.
- **Sandboxes.** Rung 1 was refused Sandboxes for Alex's project (ForbiddenError), so the leaves run in
  git worktrees and scene 07 says so. If the project has Sandboxes by the recording night, rung 3 has
  passed, and the node pane says `sandbox`, scene 07's narration becomes: "Each gets a Nemotron Nano
  executor on Token Factory, and every tool call it makes runs in a Token Factory Sandbox forked from one
  checkpoint of the repository."

## Filming a take

From a fresh terminal of your own (not Claude Code: a live take spends your key, and `build.sh` refuses
an agent's shell), in a checkout of `first-light` (or `main` once it is merged), with the key in
`NEBIUS_API_KEY` or the keychain:

    caffeinate -i env EXECUTOR='nemotron --placement local' docs/demo/build.sh

`EXECUTOR` is read as `docs/proof/nemotron.sh` reads it: while Sandboxes refuse the project, the leaves
run in local worktrees; once rung 3 has passed, leave it out and `graphene init` puts them in Sandboxes.
The `graphene` on PATH is the one filmed (yours is the checkout's own, installed editable).

A take builds feeds at `~/graphene-film/feeds` (`FILM_DIR` moves it), records the run with
`graphene demo --record`, and films each scene into `docs/demo/takes/<time>/`. The seconds spent waiting
for the planner and the executors go by un-filmed, so a take lasts as long as rung 7 does (10 to 30
minutes) plus about a minute of VHS starting. Then it writes `docs/demo/rough.mp4` and `rough.srt` and
prints each scene's length against this table, the cuts, and the total. The spend goes to the practice
ladder's ledger, `.graphene/practice/ledger.jsonl`, under rung 7's $3 cap, unless the shell names
`GRAPHENE_LEDGER` and `GRAPHENE_SPEND_CAP_USD`. Each take replaces `rough.mp4`; its clips stay in its
own directory, and `docs/demo/build.sh --take docs/demo/takes/<time>` makes that take the cut again.

Watch it with `open docs/demo/rough.mp4`. QuickTime shows the narration as subtitles (View, then
Subtitles, then English, if they are not on).

`rough.mp4` is written only when the take's run was live: `graphene demo <the take's run.jsonl> --once`
must say "as it ran, live", which it does only when every model call the run logged went to Token
Factory. A take that was not live stops there, with the recording's own words. The take's `run.jsonl` is
also the live recording `graphene demo` can ship in place of the stand-in's (`src/graphene_map/demo.jsonl`,
after `uv run pytest tests/test_demo.py`).

- `docs/demo/build.sh --rehearsal` films the same take against the stand-ins (the scripted Nemotron in
  `docs/demo/standin.py`, and Docker for the sandbox when it is up) into `docs/demo/rehearsal.mp4`, with
  "REHEARSAL: scripted stand-in, not live" on the top line of every frame. It never writes `rough.mp4`.
  About eight minutes.
- `--size 80x24` films at 80x24, to see what fits there.
- Each clip is played at the length it took: every tape marks its start and end (`Ctrl+B M`), since VHS
  catches fewer frames than it plays when the machine is busy (a 15-second clock filmed at 30 frames a
  second played in 11 seconds).

Takes, clips and videos are git-ignored: the script is committed, never the video.

## What must be true before the final recording

- The demo run is live, with the frozen configuration, and every number on screen comes from that run.
  The numbers in the narration are read off the screen, never written in advance, and the model named
  for the executors is the one the frozen configuration uses (Nano, Super, or Nano then Super).
- The board and the questions on it are Nemotron's, from that run.
- Nemotron's shaping prototypes (`graphene plan cover`, `note`, `precheck`) and `?` talk appear only if
  they ran live in that recording. Until then they are not on camera.
- Nothing recorded in the Docker stand-in is shown or described as a Token Factory Sandbox.
- The final video has the narration as audio; the subtitles are the rough cut's stand-in for it, and
  `rough.srt` is the captions file YouTube takes.
