<p align="center"><img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark.svg" alt="The Graphene mark"></p>

<h1 align="center">Graphene</h1>

**One plan for your coding agents. Clear boundaries. Tested commits.**

Graphene turns a goal into tasks with explicit files, dependencies, and checks. Agents work in separate Git
worktrees; Graphene checks their changes and merges what passes. You can see the plan and steer it from your
terminal or VS Code. Works with Claude Code and Codex.

<p align="center">
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/v/graphene-map?color=5e5d59" alt="PyPI"></a>
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/pyversions/graphene-map?color=5e5d59" alt="Python"></a>
  <a href="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml"><img src="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Alex-lop/Graphene/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-5e5d59" alt="License"></a>
</p>

![Graphene's canvas in VS Code, replaying the bundled demo. Across the top: Plan, Run and Review. On the canvas: three steps as cards with their files and checks, one landed and two working, each racing three attempts, and a region for what leaves your machine. Beside it, the selected step's Scope pane: the two files it may change, what it may run, how a write outside them is held, the one write that was refused, and its check](https://raw.githubusercontent.com/Alex-lop/Graphene/main/editors/vscode/media/graph.png)

*The canvas in VS Code, replaying the bundled demo: a scripted stand-in, no model ran.*

- **A canvas you watch and shape.** One pipeline, Plan → Run → Review: each step is drawn as the planner
  writes it (Claude Code's stream; a Codex plan appears whole when it arrives), you edit a step before it
  starts, and one switch, **Stop after the plan**, decides whether the run waits for you.
- **Scope you can see.** Select a step and its pane says which files it may change, what it may run, how a
  write outside them is held, which writes were stopped, and what its check said before and after the work.

## What it solves

Running more agents creates more coordination work: overlapping edits, hidden dependencies, and changes that
look finished until you run the tests. Graphene makes that work visible and gives it rules.

- **Keep parallel work separate.** Each task owns its files and worktree. Tasks with dependencies wait.
- **Define “done” before work starts.** Each task has a check that Graphene runs itself in a clean copy.
  Optional forks race the same task; a fixed rule chooses among passing results.
- **Stay in control.** Review the plan, adjust scope, link tasks, send an agent a note, or stop a run.
  Each landed task is a merge commit you can revert.

## Get started with the CLI

![Graphene's CLI cockpit: three tasks running in parallel, their racing attempts, a stopped write, and cost](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/race.png)

*The CLI cockpit tracks tasks, attempts, stopped writes, and cost. Scripted demo.*

Try the scripted replay first. It needs no API key and writes nothing to your project:

```sh
uvx graphene-map demo --auto
```

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git on macOS or Linux
(Windows via WSL). Graphene requires Python 3.12+.

To use it on your own repository, have Claude Code or Codex installed and signed in, then run these commands
in your terminal:

```sh
uv tool install graphene-map
cd your-repo
graphene init
graphene ask "add a --top N option to the CLI, with tests"
graphene watch
```

`init` asks which planner and executor to use. In the cockpit, press `A` to accept the plan, then `R` to run
ready tasks; it asks first when more than one task could start. Press `g` for the graph, `i` for task details,
and `?` for all keys. Stop a run with `graphene run --stop` from another terminal.

![Graphene's CLI graph: completed tasks flowing into their goal, with the auto round and budget above](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/auto-graph.png)

*Press `g` to switch to the task graph. The same scripted demo, after completion.*

With Claude Code, `init` also installs project hooks: your next request proposes a plan before writing.
`graphene plan first off` lets quick changes through. Remove the hooks with `graphene init --remove`;
uninstall with `uv tool uninstall graphene-map`.

<details>
<summary><strong>Let Graphene plan and run the whole goal</strong></summary>

```sh
graphene auto "add a --top N option to the CLI, with tests" \
  --budget 10 --check "python3 -m pytest -q"
```

Your planner plans, an agent takes each task, and Graphene checks the merged result. If the goal's check
fails, it plans a fix within your task, round, and budget settings. `--forks 3` races three agents on each
task. Each attempt holds its worst case from the budget before it starts ($2 with Claude Code, $3 with
Codex), so leave room for the ones that run at once. Add `--plan` to inspect the plan without running it.
The dollar limit is not a hard spending cap.

</details>

## Use the graph in VS Code or Cursor

![Graphene in Cursor: completed tasks, the kept attempts, and auto mode's round and budget](https://raw.githubusercontent.com/Alex-lop/Graphene/main/dev/process/editor/after/cursor-panel-1920x1050-dark.png)

*Cursor showing a completed auto run against the scripted stand-in.*

The screenshots and Home workflow show current `main`, ahead of the
[0.8.0 packaged release](https://github.com/Alex-lop/Graphene/releases/latest). To use the current CLI and
editor, build from source with Node 22+:

```sh
git clone https://github.com/Alex-lop/Graphene.git
cd Graphene
uv tool install --force .
npm --prefix editors/vscode ci
npm --prefix editors/vscode run package
code --install-extension editors/vscode/graphene-0.9.0.vsix
# Cursor:
cursor --install-extension editors/vscode/graphene-0.9.0.vsix
```

Click Graphene in the activity bar to open **Home**. Pick your planner and executor, type a goal, click
**Plan it**, review the suggested tasks, then **Start**. Keep approval enabled to review each finished task
with **Open changes**, then **Approve** or **Send back** with a note. Home and the graph show the three
stages and the **Stop after the plan** switch: turn it off and **Plan it** runs what fits your limits without
waiting for **Start**.

**Graphene: Show Graph** opens the plan in a tab. Click a step and its pane opens on **Scope**; its **Edit**
tab changes its files, check, attempts, or approval; drag its dot onto another step to add a dependency.
**Graphene: Watch the Demo** needs no key. Each step has one colour, on its card and, from the time it is
accepted until it lands, on its files in the Explorer; `graphene.advanced` enables the extra task and round
views.

A graph can be saved and run again. **Save as workflow** writes it to `workflows/<name>.md` with the values
you name as inputs; Home lists the repository's workflows, and **Run** fills the inputs and proposes the plan
with no planner call. A `run:` step runs a command with no agent. One that pushes or opens a pull request
(`git push`, `gh pr`) is drawn past the **leaves your machine** line and waits for your approval. This
repository ships [`workflows/fix-issue.md`](https://github.com/Alex-lop/Graphene/blob/main/workflows/fix-issue.md).

Current `main` also installs Codex hooks: run `graphene init` in your project, start a new Codex session,
trust the project, and review its hooks with `/hooks`.

The editor and `graphene watch` read the same local plan, including when Codex executes the tasks.
See the [extension guide](https://github.com/Alex-lop/Graphene/blob/main/editors/vscode/README.md) for Cursor
installation, commands, and settings.

## Know the limits

Graphene is early. Trusted, loaded hooks and the built-in executor block supported writes outside scope;
Codex's hooks require current `main`. Unloaded or failed hooks can let writes through; Git checks tracked
changes again before merging. This is file coordination, not a security sandbox. Checks are only as strong
as your tests;
set `review: every` in `graphene config edit` to require your sign-off before changes land.

Plans and session records stay in `.graphene/`. Your chosen agent or model provider still receives the
context it needs. The bundled auto demo uses a scripted stand-in; live auto mode has not yet been validated.
The canvas, the Scope pane and workflows were built and checked against that stand-in too: nobody has used
them on a real run yet.
[Enforcement limits](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends)
· [Privacy](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#privacy).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md)
· [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md)
· [Comparisons](https://github.com/Alex-lop/Graphene/blob/main/docs/COMPARE.md)
· [Changelog](https://github.com/Alex-lop/Graphene/blob/main/CHANGELOG.md)
· [Contributing](https://github.com/Alex-lop/Graphene/blob/main/CONTRIBUTING.md)
· [Feedback](https://github.com/Alex-lop/Graphene/issues/new?template=first-hour.yml)
