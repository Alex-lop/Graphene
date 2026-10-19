# Stranger's first hour: Graphene from the README (clone 921834de, wheel 0.5.1, against PyPI 0.5.0)

Clone: <scratch>/agents/stranger. Tool install: UV_TOOL_DIR=…/stranger-uvtools, bin …/stranger-uvbin (put first on PATH only for my commands). Scratch project: …/agents/stranger-proj (package `tally`, one pytest test, one commit). Screenshots: …/agents/stranger-shots/. Driver scripts: …/agents/stranger-scripts/{demo_drive.py,watch_drive.py} (Cockpit / CockpitReplay via `App.run_test`, as tests/test_cockpit_app.py and tests/test_cockpit_replay.py do).

Caveat: this session is an agent (Claude Code sets CLAUDECODE), so Graphene refuses it every person-only act. I did not strip those marks. So these were **not checked**: init's interactive prompt as a person sees it (described from cli.py:263-292 and 383-392 instead), and watch after `plan accept` / board answers. I saw the running and finished states only in the demo replay.

## Timeline (wall clock, 18 Oct)

| Step | Time | Result |
|---|---|---|
| clone, `uv sync --all-extras`, `uv build` | 22:59:50 to 23:00:01 (11 s) | built graphene_map-0.5.1 wheel and sdist, no warnings |
| `uv tool install` the wheel into my own dir | 3 s | `graphene 0.5.1`; uv warns the bin is not on PATH (expected) |
| PyPI: `uvx --isolated --from graphene-map graphene --version` | 1 s | `graphene 0.5.0` |
| PyPI: `demo --once`, `demo --cheat` | 1 s | `--once` prints the end state; `--cheat` prints **"no such option: --cheat"** |
| clone: `demo --once`, `demo --cheat` (with and without --once) | under 1 s and about 1-4 s | both fine, text output |
| demo replay driven headless (120x36 and 80x24) | 22 s each | 7 PNGs looked at |
| scratch project + `graphene init` | 1 s | hooks installed; planner/executor "not chosen" (an agent is never asked) |
| `graphene watch` on the empty plan, keys tried | 21 s | 3 PNGs |
| `graphene plan propose -` (goal, one question, 2 leaves) | 1 s | accepted first try |
| watch on the proposal, keys tried; `plan accept`, `board take`, `ask`, `:ask` | 26 s | all refused to an agent, with clear messages |

My whole walk took about 8 minutes of clock. I put a person's first hour at 45 to 60 minutes, most of it reading the README and working out the vocabulary.

## Stumbles, in order

| # | Step | Expected | What happened | Sev |
|---|---|---|---|---|
| 1 | README "Try it": `uvx --from graphene-map graphene demo` | the cockpit in the GIF | PyPI serves 0.5.0, which has **no `graphene_map.cockpit` module** (I listed its modules: ask … views, no cockpit). The stranger sees the older outline screen, not the GIF, `cockpit.png` or `map.png`. `graphene watch --help` on 0.5.0 reads "Show the plan on one screen, live, with vim keys." | high |
| 2 | README: "`graphene demo --cheat` tries seven ways round them" | the cheat demo | 0.5.0: `graphene demo: no such option: --cheat (Possible options: --help, --once)`. The first command the README asks for fails. | high |
| 3 | README "On your project": `uv tool install graphene-map` | the version the README describes | installs 0.5.0 (same cause as 1), so `y`/`R`/`t`/`w`/`g`/`m` and `--classic` do not exist as described | high |
| 4 | README opening | one line saying what it is | the first screen is a "Why I built this" essay; what Graphene *does* first appears in the bold line after two paragraphs. "397% of your tokens" is an in-joke; "idolized" (idealized?) reads as a typo | med |
| 5 | README and CLI vocabulary | one word for one thing | one thing goes by several words: leaf / task / node (`graphene --help`: "`graphene node show <id>` shows one node's record"; the README says leaves and tasks; the help screen mixes leaf and task). Check / proof / "proven" / "0/2 proven". The screen is "m territory" in the top bar but "m map" in the footer and README. "g flow" in the bar, "g graph" in the footer. `w` is "widen it" on the row, "allow" in the footer, "give it the path the gate stopped" in help. `x` is "back" in the footer, "pull back" in cockpit.png, "hand back" in help. Also "b a sibling", "rolled up", "stand-in", "gate", "lens", "paint" | med |
| 6 | `graphene demo --once` (clone) | the story the GIF tells (a leaf comes back, is tried again, lands) | prints only the last frame and the log tail, with lines cut off ("changed: app.…", "run: 1 done ·…"). It does end with a good next step: "try it on your repo: graphene init, then graphene ask what you want" | low |
| 7 | demo replay, t=15 s (`demo-t15.svg.png`) | follow one agent | the agent on "greet says hello" is **tern** while it comes back, then **wren** once it is done (`demo-end`). The name comes from the session (cockpit/look.py:8-43, `name_for` hashes the session key), so a retry looks like a different agent. Animal names (fox, oak, river, crab…) carry no meaning. Alex wants numbers; a number given per session would jump the same way | med |
| 8 | demo, the `i` details pane (`demo-key-enter.svg.png`) | a demo that "no model ran" | shows `model stand-in-Nano` and `bill $0.0003 at list price for this leaf's 7 calls`. A stranger can't tell what was spent | low |
| 9 | demo, `m` at the end (`demo-key-m.svg.png`) | the map in README's map.png | "TERRITORY 0 of 4 files may be touched (0%)", one row "(root) … nobody". Finished tasks drop out, so the screen the README sells is empty in the only demo a stranger has | med |
| 10 | demo `g` (`demo-key-g.svg.png`) / empty-plan `g` (`empty-6-g.svg.png`) | boxes and arrows | two unconnected boxes; the parent "say hello" is not drawn; the legend "amber lane = a retry loop (bounded) · ◀▶ two-way" names things that are not on screen. On an empty plan, `g` is a blank screen with only that legend: no "nothing planned" line | low |
| 11 | in territory, Esc | back to the cockpit | stays in territory (checked: after `m`, `escape`, `t`, `view=territory`); only `c` goes back | low |
| 12 | top line, cockpit | goal, then state | jammed together: "no goal yet your plan", "tally can subtract and multiply your plan", "a friendlier app replay · …" (`empty-0-open.svg.png`) | low |
| 13 | `graphene init` from inside Claude Code (many strangers will ask their agent to "set up graphene") | it is set up | it installs the hooks and leaves planner/executor "not chosen". The `--planner claude --executor claude` it suggests is refused: "choosing the planner and the executor is the person's to do … run it in a terminal outside Claude Code". The message is clear, but the README does not warn that setup must happen in a plain terminal | med |
| 14 | init prompt (person at a terminal, from code: cli.py:263-292, 383-392; not seen live) | "pick Claude Code or Codex" (README) | two questions: "which planner and executor for this repo?" (numbered list including Nemotron, a name a stranger does not know, and "a command of your own"), then "what happens to an ask in a Claude Code session here?" with on / auto / off. The README mentions neither "planner/executor" nor the plan-first question | low |
| 15 | `graphene plan --help` | a list of the plan commands | `propose` is **not listed** (edit, undo, accept, log, archive, pause, first, resume). `graphene plan propose --help` exists but does not describe the text format | med (for anyone scripting an agent) |
| 16 | the plan text format | documented in docs/HOW_IT_WORKS.md, as the task said | HOW_IT_WORKS.md:38 gives only `- title [id]` / `? title [id]`. The `scope:` / `check:` / `needs:` keys and the `question:` / `default:` / `option:` board syntax are only in src/graphene_map/plan_text.py:1-20 and 74-82 (the `plan edit` header). I wrote the plan from the source; it was accepted first try | med |
| 17 | watch opens on a proposal (`proposed-0-open.svg.png`), press `i` | details of the first row | "select a task to see everything about it": nothing is selected at open, though Enter at open does take the question's default. `j` selects the first leaf | low |
| 18 | question row | read both options | "1 integers o…" is cut off at both 80 and 120 columns, with half the line empty (`proposed-14-enter.svg.png`) | low |
| 19 | `t` on a proposed leaf | a tell box, or "nothing to tell yet" | nothing at all; the feed line stays the same (checked after `t`) | med |
| 20 | Enter on a selected proposal / `y` / `:ask add divide` / CLI `plan accept`, `board take`, `ask` | the person's act | refused to an agent: "✗ graphene plan accept subtract: accepting a proposal is the person's to do, and this call comes from claude:8cfd2651". By design, and the wording is good. A person who opens watch from Claude Code's `!` shell would hit this too | low (by design) |
| 21 | `:` box (`proposed2-3-type_ask_add_divide.svg.png`) | a hint at what to type | an empty box with no placeholder; nothing shows that it runs `graphene <what you type>` | low |
| 22 | README "On your project" ends with `graphene run --parallel 2` | to know what it costs | nothing in the README says `run` starts headless agent sessions on your Claude/Codex account (paid usage). Not checked live (no paid calls) | med |
| 23 | 80x24 terminal | everything fits | the feed legend is cut off ("▁▃▅ activ…"); the demo's top line drops "a scripted stand-in, no model ran" | low |

What went right: a clean build; the cheat demo is clear and honest ("6 refused, 1 flagged, 0 got through … It does not show what a real model will try"). Init leaves `git status` clean: its files go in .git/info/exclude. The proposal format took a three-level tree plus a question on the first try. The empty state says what to do. Every refusal names the reason and the way forward. The help screen (`demo-help.svg.png`) is complete.

## Screenshots (PNG, looked at)

- <scratch>/agents/stranger-shots/demo-t15.svg.png (a leaf came back, the reason, ⏎ try again)
- …/stranger-shots/demo-end.svg.png, demo-help.svg.png, demo-key-enter.svg.png (details), demo-key-g.svg.png (flow), demo-key-m.svg.png (empty map)
- …/stranger-shots/empty-0-open.svg.png, empty-6-g.svg.png, empty-8-m.svg.png
- …/stranger-shots/proposed-0-open.svg.png, proposed-4-i.svg.png, proposed-6-g.svg.png, proposed-8-m.svg.png, proposed-14-enter.svg.png (refusal), proposed2-3-type_ask_add_divide.svg.png
- All the SVGs for every key press are in the same directory (empty-*, proposed-*, proposed2-*, narrow-*, demo-*).

## Top 10 changes for a stranger's first hour, ranked

1. **Release 0.5.1 to PyPI (or point the README at the git install until then).** Every README command a stranger runs today hits 0.5.0: no cockpit, no `--cheat`, a screen that matches none of the pictures. Nothing else on this list matters until this is fixed (stumbles 1-3).
2. **Put one sentence of what it is, and the try-it command, above "Why I built this".** For example: "Graphene keeps your coding agent inside the files you agreed to, and calls a task done only when your check passes." Move the essay below the demo. Fix "idolized" and drop "397%" (4).
3. **One word for one thing on screen, in the help and in the README.** Pick task *or* leaf (and keep node out of user-facing help), check *or* proof, map *or* territory, graph *or* flow, and one verb each for `w` and `x` (5).
4. **Numbers for agents, kept for the task's life.** Agent 1, 2, 3 in the order they started, and a retry stays the same number (or reads "1, try 2"), so the demo does not turn tern into wren (7).
5. **Make the demo show the map and the graph with content.** Keep finished tasks' folders on the map (dimmed) and draw the parent and the edges in flow, so `m` and `g` in the only demo look like the README pictures. Drop the legend items that are not on screen (9, 10).
6. **Say in the README where setup must happen.** "Run `graphene init` and accept in your own terminal, not through your agent: only you can choose and accept." Name init's two questions (planner/executor, plan first) (13, 14).
7. **Every key answers.** `t` on a proposal should say "it has no agent yet: accept it first". `i` at open should open the first row. Esc should go back from map/graph. Select the first row at open (11, 17, 19).
8. **Document the plan text format where people look.** List `propose` in `graphene plan --help`. Put a five-line example (goal, question/default/option, a leaf with scope/check/needs) in `plan propose --help` and in HOW_IT_WORKS.md (15, 16).
9. **Say what `graphene run` spends and on whose account,** in one line in "On your project". In the demo's details, show "no model ran, $0" in place of "stand-in-Nano … $0.0003" (8, 22).
10. **Polish the cockpit's first lines.** Separate the goal from the source ("tally can subtract and multiply · your plan"), never cut an option short while the line has room, and give the `:` box a placeholder ("a graphene command, e.g. ask …, stop") (12, 18, 21, 23).
