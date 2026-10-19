# The publish night: the plan (18-19 October 2026)

Alex, at 22:50: "create a plan to update the Watch [and] the readme to actually get it finished and ready to be
published, really focus on the overarching ideas that I'm trying to achieve ... what would make this the best repo
for agentic workflow ... don't keep the names like fox... just change it to numbers ... don't expect me to accept any
graphene plans since I will be asleep ... run till 10 AM ... 50 commits ready for tomorrow". This is that plan. It was
written after eight read-only readers (a stranger's first hour, the cockpit's code, a designer's eye on every screen,
a docs and PyPI audit, CI and the release, the field of agent tools, your own words, the hackathon's rules); their
reports are in `dev/process/publish/readers/`. Nothing here waits on your accept: the work is done in a clone and
reaches you as one local branch.

## The idea everything is judged against

In your words: "the limiting factor ... is going to be you, the human, that drives innovation forward" (your video),
and "if you don't say which direction the application should go, the agent has to infer most of it, and you find out
what it inferred in the diff. Graphene tries to bridge that." So the watch is the bridge: one screen where you see
what every agent is doing, tell it what you meant, and know a task is done because its check passed. Every change
below answers one of three questions: does a stranger get the product the README shows; does the screen say the idea
in its first three seconds; does every word and key mean one thing.

## What the readers found that decides the order

1. **PyPI serves 0.5.0 (7 October).** It has no cockpit, `demo --cheat` fails, and every README command describes
   something a stranger cannot install. The v0.5.1 release run failed because one timing test failed on one CI leg
   (`tests/test_teardown.py:135`, macOS, Python 3.14). Until a release with a green suite exists, nothing else in the
   README is true for anyone who follows it.
2. **The hackathon (Nebius x NVIDIA, Devpost) closes Friday 30 October, 10:00 PT.** Its rules ask the README to
   "highlight how you've used NVIDIA Nemotron ... and where Token Factory accelerated your workflow", and stage one
   is pass or fail on that. Today the README never says Nemotron or Token Factory.
3. **The pictures bury the idea.** The GIF opens on "no goal yet", the cockpit still shows a healthy agent in alarm
   red with "no goal yet" on top, the map still shows every folder "nobody", and the GIF shows a false `1 OUTSIDE`
   on the retry that was meant to prove the rule holds.
4. **One thing has three words.** task, leaf and node; flow and graph; territory and map; `w` allow, widen it and
   give it; `x` back, pull back and hand back; `i` all, everything and details.
5. **The field moved.** Claude Code's Agent View and the Codex app now give every agent a row and a worktree; the
   wrappers that only did that are quiet or gone. The field's top complaint is the thing Graphene enforces: "a plan
   finishes, everything shows green, and the implementation is partially or entirely hallucinated" (Superpowers
   #578), and "two teammates editing the same file leads to overwrites" (Claude Code's own Agent Teams docs).

## The words (one word for one thing, on the screens, in the help and in the README)

- The screens: **cockpit** (`c`), **graph** (`g`), **map** (`m`).
- A piece of work is a **task** on the screens and in the README; the commands call it a leaf (`graphene node ...`).
- A task's **check** is the command that proves it; a task whose check passed is **proven**.
- Agents go by numbers: **agent 1** in a sentence, **1** in a column. A task keeps its number through a retry.
- Keys, each with one verb everywhere: `⏎` the row's own move (accept, try again, sign off), `i` **details**, `t`
  **tell**, `w` **widen** (give the task the path the gate stopped), `x` **hand back** (a running task) or
  **reopen** (a finished one), `d` **drop**, `r` **run**, `R` **run ready**, `A` **accept all**, `?` **keys**.

## The work, in lanes (each lane owns its files; each change is a commit with the test that shows it)

**Done first: agents go by numbers** (1082b8b0).

**R: what the cockpit reads** (`cockpit/read.py`, `cockpit/model.py`, `cockpit/replay.py`)
- The false `OUTSIDE` after a widen is gone (git's answer is kept per attempt and scope, not per task).
- A running row shows this attempt only: never the last attempt's hand-back under a new agent.
- An agent's words are never cut silently; the screen cuts them, with an ellipsis.
- A stopped write needs you: it counts in "need you" and sorts with what does.
- The map's lens follows the plan's stage until you choose one (plan before the run, live during it, changed after).
- The replay opens on the plan, not on an empty screen, and its news line narrates (the board's questions, your
  answers, what landed) instead of logging (precheck, usage, attempt).

**S: the cockpit screen** (`cockpit/rows.py`, `app.py`, `help.py`, `look.py`, `lines.py`, `details.py`, `verbs.py`)
- The words above, everywhere on the screen, in the key bar and in the help; marks explained in the help.
- Colour means state: an agent's colour never borrows proven green, running amber, need-you purple or came-back red.
- The headline is your goal; with none, an invitation to give one, not a bold "no goal yet".
- A proposal opens to show what you agree to (its files, its check, what it waits on), and `A` accepts them all.
- Whole titles where they fit; the key bar says what the keys do for the selected row; the summary stays on top
  when the rows scroll; the first run and the empty screens say what to do next and fit 80 columns.
- The keys the screens advertise work (the map's "a: allow", the details' "t ask the planner", Esc back to the
  cockpit, `t` and `i` on any row say something true).
- When something new needs you, the terminal says so (a bell and a notification with the reason; one setting
  turns it off).

**M: the graph and the map** (`cockpit/flow_view.py`, `flowlayout.py`, `territory.py`, `territory_view.py`)
- The graph starts from your goal and draws the sub-goals under it, then the tasks: your direction as a tree, the
  idea you asked for on 16 October. Its legend shows only what is drawn.
- The map's headline tells the truth in each lens; its live marks come before the owners, so 80 columns keeps
  them; owners are agents or titles, never ids; an empty plan is one line.

**D: the demo tells the story** (`tests/test_demo_script.py`, `src/graphene_map/demo.jsonl`, `tests/test_demo.py`)
- The shipped replay (the Nemotron path against its scripted stand-in, $0) gets a plan worth watching: a goal, two
  sub-goals, four tasks, three agents at once, one that comes back with its reason and is widened, one that waits
  on two others. The README's GIF and stills are filmed from it.

**C: the suite is green on every leg** (`tests/`, `.github/workflows/`)
- The timing test that kept 0.5.1 off PyPI is made deterministic, and every other test that waits on a clock is
  checked under load.

**K: review every task before it lands, when you ask** (`plan.py`, `settings.py`, `config_cli.py`)
- One setting puts every task that passes its check in front of you as a sign-off (`c` in its details shows the
  diff) instead of landing it. The default stays "the check decides". The README's "Not yet: a look at every diff
  before it lands" becomes a sentence about how to ask for it.

**P: publish** (README, docs, CHANGELOG, version), after the lanes land
- README in your voice, built on your own 16 October edit (plain markdown, the promise first, the short why with
  your video linked, the Cost line made true): what it is in one line, the GIF, the try line, the three steps, what
  you see, your project, what it enforces and where it ends, a section for Nemotron on Token Factory, privacy, how to
  help. The GIF and both stills filmed again from the new demo.
- docs/HOW_IT_WORKS.md, COMPARE.md (rows for Agent View and Agent Teams), A_RUN.md, the plan text format where
  people look; docs/HACKATHON.md brought to the cockpit and the deadline; a storyboard for the three-minute video
  the rules ask for.
- Version 0.6.0 (it changes the default screen): pyproject, `__init__`, uv.lock; CHANGELOG with 0.5.1 said plainly
  (tagged, never published, its release run failed on one red test).

**Then:** the whole suite and the wheel from a clean home; a review where the lanes meet (one reader a seam, one
skeptic a seam, fixes with a failing test first); a stranger's walk again on the final wheel; the history folded to
about 50 commits; the brief.

## Yours, whatever happens tonight

- `git push`, then `git tag v0.6.0 && git push origin v0.6.0`: the release workflow runs the suite on six legs and
  publishes only if it passes. That is what makes the README true for a stranger.
- The three-minute video (the rules want Token Factory and Nemotron named in it), the Devpost form, the GitHub About
  box (topics nemotron and nvidia, a description that says what it is). All of it before 30 October, 10:00 PT.
- Every decision this plan took for you is listed in the brief, each with the one line that flips it.
