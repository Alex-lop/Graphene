# The revamp night, 26 October 2026

Alex's ask, going to bed at 00:30 after skimming the honest take on Graphene's chances: "work all throughout the
night ... wake up with a morning md file and a completely revamped product and readme.md ... be as aggressive as
possible, if I don't submit on time who cares I only care about making this the best product possible ... keep
spawning more sub agents". The direction he agreed with: many agents in parallel, each owning its files; an auto
mode where the agent draws the plan and Graphene runs it, the plan and its iterations tracked; Nemotron racing;
VS Code plus the CLI; any harness, any model.

## What was built

The product in one sentence: **you give Graphene a goal and an envelope once; it plans with Nemotron, races agents
on every task in parallel, each held to its own files, lands only what its check passes, checks the goal itself and
plans the fix when that is red, and you watch and steer from the terminal or VS Code.**

- **Auto mode** (`src/graphene_map/auto.py`, `auto_cli.py`; lane auto). The envelope is the person's settings:
  `auto`, `budget`, `tasks`, `rounds` beside `protected`, `readonly`, `never`, `forks`, `review`; `graphene config
  set KEY VALUE` changes one without an editor. While auto is on, a proposal that fits is accepted as the person's
  stand-in (`by: auto`, undoable), from `graphene ask` and from any agent's `graphene plan propose -`.
  `graphene auto "<goal>"` sets the goal, asks the planner for a tree under a root sub-goal that carries the goal's
  check, takes what fits, runs it with forks, and when the root's check is red asks the planner for the fix, for
  `rounds` rounds; each stage is an `auto` row on `*` (the contract in `auto.state`). Planners are told to split
  wide (each task its own test file); after an accept Graphene says how many tasks can run at once.
- **The race on screen** (`cockpit/`, `meter.short`; lane race). Every agent's row names its model, each fork its
  own with its dollars; the auto line in the cockpit's and the graph's head; `+` adds a step after a task and `L`
  links two on the graph (`graphene node set B --add-needs A`); the head says the width.
- **State for editors** (`src/graphene_map/state.py`; lane state). `graphene state --json`, one snapshot of what the
  cockpit shows, read-only; `graphene plan log --json --since ID`; `tests/fixtures/state-sample.json`.
- **Graphene for VS Code** (`editors/vscode/`; lane vscode). TypeScript, no runtime dependencies: a Plan tree, the
  graph in an editor tab and the sidebar, a details pane with Add step after/under, Link to…, Edit, Drop, Accept,
  Tell; the status bar; Open Cockpit, Auto…, Run Ready Tasks, Stop. Every change is a `graphene` command with the
  agents' marks taken out of its environment. 20 unit tests, a smoke test that activates it in a real VS Code
  1.143.1, `npm run package` makes a 29.5 KB `.vsix`; a CI job of its own.
- **Any model, any agent, a port a task** (lane anymodel). `--endpoint tokenfactory|nim|ollama|openai` for
  Graphene's own planner and tool loop; `{prompt}` and `{prompt_file}` for any CLI agent; `PORT` and `GRAPHENE_PORT`
  per running task and fork, given to its check; `graphene init` offers Nemotron at a terminal.
- **Later in the night, alone:** `checks:` in the envelope; `graphene config set`; Graphene: Set Envelope… in VS
  Code; `:auto <goal>` in the cockpit, as a process of its own; a fix round's planner told never to loosen a test;
  the extension tested against a real snapshot; `graphene state --json` without Textual.
- **`graphene demo --auto`** (`dev/proof/auto.sh`, `dev/proof/make_wordkit.py`, `tests/test_demo_auto.py`): auto mode
  on Nemotron against the recorded fake, shipped in the wheel: three tasks, nine forks at once, one write refused
  outside its task, the whole suite red after all three land, Ultra's fix, green. `docs/assets/auto.gif` (vhs,
  `docs/assets/auto.tape`), `race.png`, `auto-graph.png`.
- **The docs.** README rewritten around the new product (Alex's why kept word for word); HACKATHON's Devpost fields,
  the kit (`dev/launch/hackathon.md`), claims, CHANGELOG, release notes for 0.8.0, CONTRIBUTING, a new video script
  (`dev/launch/video-auto.md`). Version 0.8.0 (0.7.0 was tagged but never published).

## How it was built, and what went wrong

00:31 a clone of GitHub's `main` (499d0a3d, the forks merge that Alex's local `main` lacks) in the session's
scratchpad, on `night/revamp`; his checkout was never written (its plan-first hook refuses agents, and its
untracked `dry-run/` blocks any leaf). Baseline: ruff clean, 2,576 passed, 21 skipped. Six read-only readers mapped
the code (plan, run, nemotron, cockpit, cli, docs: their maps fed every lane). A small contract commit (522e0313)
gave the lanes shared names. At 00:57 five Fable lanes started, each in its own clone with no remote, each to be
built, reviewed by a skeptic and fixed.

**At 01:50 the Fable limit hit** ("You've reached your Fable limit"). Every lane's work was committed by then (the
vscode builder had finished at 01:33; auto had one finished test uncommitted, which I ran and committed), but no
review and no fixer ran. Alex's standing rule is Fable for every subagent ("a run that needs another model waits
for him"), so from 01:50 the night is the main session alone. A probe at 02:35 found Fable still limited.

What I did in place of the reviews, each with a failing test first:
- **The merge's seams**: six failures on the merged branch (a script's fork named `repo-forks.p`, the keychain
  and check stubs not taking the arguments the any-model lane added), fixed (38f950a1).
- **A spend-guard bypass** (partly older than tonight): Token Factory's URL variable pointed at its own host
  spelled another way (`:443`, a capital letter) or at a proxy counted as a stand-in, so an agent's call went out
  with the person's key and no opening. Now only a host on this machine stands in (c3d9d6f3).
- **An escalation through the envelope**: a held task whose scope names `.claude/settings.local.json` may write
  the hooks (that is how the person edits them), so an agent's proposal naming it, taken at once by the envelope,
  could have turned the gate off. The envelope now never takes a task that reaches `.claude/`, `.codex/`,
  `.cursor/`, `.gemini/` or `.github/workflows/` (00882613).
- **`.git/` was anybody's** (older than tonight, made worse by auto mode): a leaf scoped to `.git/hooks/pre-commit`
  was proposed, fit the envelope, and could have planted a hook that runs on the person's next commit, unseen by
  `done` (git status never shows `.git/`). No scope reaches `.git/` now, and no write there is let through.
- **The budget only held `graphene auto`**: an agent whose plan was taken could start `graphene run` itself, or
  the person's `R`, unbudgeted. While auto is on, every run counts against the budget now (5788b7da).
- **A planner's check ran unread**: with auto on, nobody reads a check before Graphene runs it (red first, then
  at every landing), and a read-only planner fed a hostile repository could write `check: curl … | sh`. The
  envelope now takes only one plain command as a check (no `;`, `&&`, `|`, redirect or `$(…)` outside quotes) and,
  once `checks:` names commands, one of them; anything else waits for the person.
- **A stranger's walk** on a fresh repo with the built wheel: before `graphene init`, `graphene auto` named
  `--with` (the executor's flag) and turned auto on for a command that started nothing; with no key the reason
  came wrapped in three others. All three fixed (d96ea25f).
- Screens I looked at while filming: a fix round did not say why it was fixing (now `fixing: FAIL: test_x`); the
  replay's news said "you accepted" for the envelope's acceptances; VS Code's graph hid the goal box under the
  details pane, and counted rounds differently from the cockpit. All fixed.

## The live proof that did not happen

- **Token Factory:** an agent's live call is refused without the person's opening (`GRAPHENE_AGENT_LIVE_USD`), by
  design, and the standing rule is that an agent never sets it. Not run; `dev/proof/auto.sh` is the one command
  for Alex (see the brief).
- **Claude Code as the executor** (as the best-of night's Haiku forks were run in a scratch repo): needs a model
  other than Fable tonight, which his rule says waits for him.
- **Ollama, free and local:** its server on this Mac (running since July from an Ollama.app no longer in
  /Applications) cannot start any model ("llama-server binary not found"), and the two models it has (Gemma 3) do
  not call tools. I pulled NVIDIA's `nemotron-mini` (4B, tools) to try, found the server broken, and deleted the
  model again; reinstalling Ollama is Alex's call.

- **Codex**, signed in with ChatGPT (no API key, so no dollars): one bounded live `graphene auto` on wordkit at
  03:12, Codex planning and doing the tasks. Codex refused before any work: `ERROR: workspace routing discovery
  unauthorized (401)`, twice; its sign-in has expired (`codex login` is Alex's). Graphene stopped as it should:
  `waits for you: the planner proposed nothing … exit 3`, nothing accepted, nothing run.
- **Gemini CLI** is set up for Vertex AI, which bills a Google Cloud account: not tried.

So auto mode has run end to end only against the scripted stand-in (`tests/test_auto_nemotron.py`,
`tests/test_demo_auto.py`). The README, HACKATHON and claims say so.

## Verified

- The whole suite on the merged branch: 2,730 passed, 21 skipped, ruff clean (Python 3.13, macOS; after the
  seam fixes). The suite at the night's end is in the brief.
- `graphene demo --auto --once` from the built 0.8.0 wheel in an empty directory, no key, no network.
- The extension: `npm test` (types, 20 unit tests, the smoke test in VS Code 1.143.1) and `npm run package`, from
  `night/revamp`; its parser read a real `graphene state --json` snapshot.
- The GIF and the stills, looked at frame by frame.

Also measured: `graphene state --json` answered in 0.16 to 0.22 s on the replayed demo's plan (`plan --json`:
0.07 s), most of it importing Textual for one pure function and the replay's narrator; with both moved out of the
screens' modules it answers in 0.10 s, which is what the extension's poll every 1.5 s pays. A test of the auto set failed three times under load (the suite beside a film or a lane) and never alone:
`test_auto_stop.py` sent its Ctrl-C between the attempt's row and the executor's pid file, then read the pid.
It waits for the pid now (fixed, 2af8c0b7).

## Not verified

- A live auto run on any model. A person on the new screens. The extension in Cursor. Codex as an auto executor.
  Whether a race of three Nanos lands more tasks than one (`dev/held/rules.md` has the question).
- GitHub CI on this branch (nothing is pushed).

## The files

`dev/process/revamp/` holds this record. The night's maps, brief and log were in the session's scratchpad; the
landscape research (`landscape.json`, one researcher, its fact-check cut off by the limit) is summarized in
`landscape.md` here.
