# Scope for the next agent: the canvas run

Read [VISION.md](VISION.md) first, then this file, then the code. If a task isn't in this file, it
waits.

This run makes the VS Code graph the place where a person watches and shapes agent work: it should
look good, draw the plan while it is being written, run in one pipeline, show each step's scope,
and save a graph as a workflow. On the convergence table in VISION.md, it moves row 1 (fix-issue)
to "runs from a file".

## Leaves, in order

Do the leaves in this order. A leaf either lands whole or doesn't start. If time runs out, the
leaves after the last one that landed wait for the next run. Never leave a half leaf: revert its
commits.

Every leaf's scope includes `editors/vscode/test/**` and `editors/vscode/e2e/**` when it touches
the extension. Two commands appear as shorthand below:

- **ext** means `npm --prefix editors/vscode ci && npm --prefix editors/vscode test`
- **readme** means `uv run pytest tests -k "readme or doc_claims" -q -n auto`

### 1. `readme-clean`: no Nemotron, no hackathon, on the first screens

- **Goal:** the README, the extension's README, and Home's and Set Up's pickers no longer mention
  Nemotron, Nebius or the hackathon.
- **Keep:** every claim that is still true stays. `graphene init --executor nemotron` keeps
  working for anyone who has it, because the code is frozen, not deleted.
- **Scope:** `README.md`, `editors/vscode/README.md`, `editors/vscode/src/home/who.ts`,
  `editors/vscode/src/setup.ts`, and the tests that pin those words.
- **Check:** readme, then ext.

### 2. `look`: the graph looks like [ui/canvas.html](ui/canvas.html)

- **Goal:** restyle the graph to the target.
  - a dotted canvas, flowing left to right
  - cards with a tile for who does the step, the title, chips for files and check, and a status
    line under each card
  - curved edges between ports; animated edges where an agent is working
  - a region for "this machine" and one for "leaves your machine"
  - colour only for state, from VS Code theme tokens (light, dark and high contrast)
  - no motion under `prefers-reduced-motion`
- **Keep:** the keyboard paths, labels, Lanes view and zoom all work as they do now. Add no new
  dependency. The graph is our own SVG, and it stays ours.
- **Evidence:** before and after screenshots of Watch the Demo, the same moment at 1920×1050, in
  dark and in light, in `dev/process/canvas/`.
- **Scope:** `editors/vscode/media/graph.css`, `editors/vscode/src/graph/**`,
  `editors/vscode/src/graph.ts`, `editors/vscode/src/layout.ts`, `dev/process/canvas/**`.
- **Check:** ext. The `vscode-e2e` job in CI stays green (`draw.mjs` and `home.mjs`).

### 3. `live-plan`: the plan draws itself

- **Goal:** while the planner writes, each step whose plan-text line is complete appears on the
  graph as a drafted box, with its edges.
  - For Claude Code, read the text as it streams. `--include-partial-messages` adds text deltas to
    `stream-json`; confirm that on the installed version before building on it.
  - For a planner whose stream has no text, the boxes appear when the plan arrives, and the graph
    says so.
- **Scope:** `src/graphene_map/ask.py`, `src/graphene_map/state.py`,
  `src/graphene_map/plan_text.py` (only a reader for the part that is complete),
  `tests/test_ask_live.py` (new), `editors/vscode/src/session.ts`, `editors/vscode/src/stream.ts`,
  `editors/vscode/src/state.ts`, `editors/vscode/src/graph/**`.
- **Check:** `uv run pytest tests/test_ask_live.py tests/test_ask.py -q`, then ext. The test uses a
  fake planner command that prints a stream slowly. No model calls.

### 4. `pipeline`: Plan → Run → Review, with "Stop after the plan"

- **Goal:** Home and the graph's header show the three stages and one switch, **Stop after the
  plan**, which is on by default.
  - **On:** today's Plan it, then Start.
  - **Off:** auto. The plan is still drawn first, then it runs without waiting.
  - A question with no default stops the run either way.
  - Before Run, each step's check runs once. A check that already passes is marked on its card:
    it proves nothing yet.
- **Decision 217 changes here.** Plan it stays `graphene ask` while the switch is on. Add the new
  rule to [DIRECTION.md](DIRECTION.md) as the next decision after 224.
- **Scope:** `editors/vscode/src/home/**`, `editors/vscode/src/home.ts`,
  `editors/vscode/media/home.css`, `editors/vscode/src/graph/**`,
  `editors/vscode/src/commands.ts`, `editors/vscode/src/session.ts`, `dev/DIRECTION.md`.
  Engine files only where a click needs something the CLI lacks: `src/graphene_map/precheck.py`,
  `src/graphene_map/auto.py`, and their tests.
- **Check:** ext, then `uv run pytest tests/test_precheck_core.py tests/test_precheck_wire.py -q`.
  `home.mjs` walks both switch positions on the demo.

### 5. `scope-pane`: what each step may do, in plain view

- **Goal:** the step pane opens on a **Scope** tab with seven parts:
  1. **May change:** the file tree, its files lit, written ones marked, other steps' files named.
  2. **May run:** the commands it may run.
  3. **Outside:** tools and network. Today that is "none".
  4. **Held by:** one of three states, taken from `tests/test_every_agent.py` and
     `dev/process/graph-edit/hooks.md`: refused before the write, caught when it finishes, or not
     held. An unproven agent shows "not held".
  5. **Stopped:** refused writes, with the time.
  6. **Done when:** the check, with its result before and after the work.
  7. **Tokens:** split into reading, writing and the check.
- **Also:** each step has one colour, on its card and in the Explorer's file marks. A glob is
  shown only when the person expands it.
- **Scope:** `editors/vscode/src/graph/**`, `editors/vscode/src/owners.ts`,
  `editors/vscode/src/session.ts`, `editors/vscode/src/state.ts`, `editors/vscode/media/graph.css`,
  `src/graphene_map/state.py`, `tests/test_state_json.py`.
- **Check:** `uv run pytest tests/test_state_json.py -q`, then ext.

### 6. `workflows`: save a graph, run it again

- **The file:** `workflows/<name>.md` is plan text with a `workflow:` line, `input:` lines and
  `{{holes}}`.
- **A command step:** `run:` runs a command with no agent, and its exit code is its check.
- **The machine line:** a step whose command pushes or opens a PR (`git push`, `gh pr`) is drawn
  past the line and waits for approval.
- **In the extension:**
  - Home lists the repo's workflows.
  - **Run** asks for the inputs, fills the holes, and proposes the plan with no planner call.
    The pipeline then goes on as usual.
  - **Save as workflow** in the graph's header writes the file, with the parts that vary as
    inputs.
- **Ships with:** `workflows/fix-issue.md`.
- **At most one new CLI command.** Name it in the PR.
- **Scope:** `src/graphene_map/workflow.py` (new), `src/graphene_map/plan_text.py`,
  `src/graphene_map/run.py`, `src/graphene_map/cli.py`, `tests/test_workflow.py` (new),
  `editors/vscode/src/home/**`, `editors/vscode/src/home.ts`, `editors/vscode/src/graph/**`,
  `editors/vscode/src/commands.ts`, `workflows/**`.
- **Check:** `uv run pytest tests/test_workflow.py -q`, then ext.
  - A test runs one workflow twice with different inputs: two plans, no planner call.
  - An e2e walk runs fix-issue from Home on the scripted stand-in, and stops at the line.

### 7. `readme-canvas`: the README leads with the canvas

- **Goal:** the README's first screen is the new canvas, from the demo, with the two pillars in a
  sentence each. Every sentence describes something that ran.
- **Scope:** `README.md`, `editors/vscode/README.md`, `editors/vscode/media/graph.png`,
  `docs/assets/**`, and the tests that pin the README.
- **Check:** readme.

## Out

- VISION.md's rows 2 to 4: triggers on Actions, outside tools (MCP) per step, `each` and `until`,
  and one workflow calling another.
- The frozen code: the terminal cockpit, `nemotron/`, the demo replay, and the tree, time and DAG
  views. They keep passing their tests.
- New runtime dependencies, in Python or in the extension.
- Releases, tags, PyPI, the vsix release, pushing to `main`, and merging.
- Rewriting [DIRECTION.md](DIRECTION.md). New decisions are added after 224.
- Nebius or Token Factory spend. The scripted stand-in drives every walk. If a live call is truly
  needed, the cap is $2, and the PR says what it was for.

## Files

Each leaf names its files. Touch a file outside that list only when the leaf can't be done
otherwise, and list each one in the PR under "Outside the list", with the reason.

## Done

Leaves 1 to 7, in order, each one landed with its check green. The `ubuntu` test legs and
`vscode-e2e` pass on the PR. A person can open Watch the Demo and, without reading anything,
answer three questions: what each agent is doing, what it may touch, and what decides it's done.
