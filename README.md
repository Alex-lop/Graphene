<p align="center"><img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark.svg" alt="The Graphene mark"></p>

<h1 align="center">Graphene</h1>

**One plan for your coding agents. Clear boundaries. Tested commits.**

Your coding agent proposes a plan before it writes. You read and shape it on a graph in VS Code or Cursor, start
it, and approve what lands. Works with Claude Code and Codex.

<p align="center">
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/v/graphene-map?color=5e5d59" alt="PyPI"></a>
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/pyversions/graphene-map?color=5e5d59" alt="Python"></a>
  <a href="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml"><img src="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Alex-lop/Graphene/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-5e5d59" alt="License"></a>
</p>

![Graphene's graph in an editor tab. Across the top: Plan, Run and Review. On the graph: a plan's task cards flowing left to right into the goal, each with its files and its check. Beside them, the selected task's Scope pane: the files it may change, what it may run, the writes that were stopped, and its check](https://raw.githubusercontent.com/Alex-lop/Graphene/main/editors/vscode/media/graph.png)

*The graph, replaying the bundled demo: a scripted stand-in, no model ran.*

- **A graph you watch and shape.** One pipeline, Plan → Run → Review. You edit a task before it starts, and one
  switch, **Stop after the plan**, decides whether the run waits for you.
- **Scope you can see.** Select a task and its pane says which files it may change, what it may run, how a write
  outside them is held, which writes were stopped, and what its check said before and after the work.

## What it solves

More agents means overlapping edits, hidden dependencies, and changes that look finished until you run the tests.

- **Parallel work stays separate.** Each task owns its files and its own Git worktree; one that needs another waits.
- **“Done” is defined before work starts.** Graphene runs each task's check itself, in a clean copy, and merges
  only what passes; when attempts race one task, a fixed rule keeps one.
- **You stay in control.** Edit the plan or stop a run; each task lands as a merge commit you can revert.

## In VS Code or Cursor

Install the CLI, then the extension from the `.vsix` on the
[latest release](https://github.com/Alex-lop/Graphene/releases/latest) (it is not on the Marketplace or Open VSX):

```sh
uv tool install graphene-map
cursor --install-extension graphene-0.10.0.vsix   # VS Code: code --install-extension graphene-0.10.0.vsix
```

1. Click Graphene in the activity bar: the graph opens in an editor tab; **Home**, in the side bar, sets up the folder.
2. Ask your agent for something, in its own chat. Graphene's hooks have it propose a plan first, on the graph.
3. Read it: click a task to change its files, check or attempts; answer its questions; **Add task** draws one.
4. Click **Start**, then review each finished task: **Open changes**, then **Approve** or **Send back** with a note.

With **Stop after the plan** off, a plan runs as soon as it appears, within your limits. **Save as workflow** writes
the graph to `workflows/<name>.md` for Home to run again on new inputs, with no planner call; a `run:` command that
pushes or opens a pull request (`git push`, `gh pr`) waits past the **leaves your machine** line for your approval
([an example](https://github.com/Alex-lop/Graphene/blob/main/workflows/fix-issue.md)). The
[extension guide](https://github.com/Alex-lop/Graphene/blob/main/editors/vscode/README.md) has the rest.

## In the terminal

Try the scripted replay first: `uvx graphene-map demo --auto` needs no API key and writes nothing to your project.
Graphene needs Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, on macOS or
Linux (Windows via WSL). On your repository, with Claude Code or Codex installed and signed in:

```sh
uv tool install graphene-map
cd your-repo
graphene init    # choose the planner and executor; installs the Claude Code and Codex hooks
graphene watch   # the cockpit: the plan the editor shows
```

From then on, your agent proposes a plan before it writes (restart an open Codex session and trust the project).
In the cockpit, `A` accepts the plan and `R` runs ready tasks; it asks first when more than one task could start.
`graphene ask "…"` asks the planner yourself: the graph draws each task as Claude Code writes it, and a Codex plan
appears whole. `graphene auto "…" --budget 10` plans, runs and fixes a whole goal; the budget is not a hard cap.
`graphene plan first off` lets quick changes through, `graphene init --remove` removes the hooks, and
`uv tool uninstall graphene-map` uninstalls.

## Know the limits

Graphene is early. Trusted, loaded hooks and the built-in executor block supported writes outside a task's files; a
hook that is not loaded or fails lets writes through, and Git checks tracked changes again before merging. This is
file coordination, not a security sandbox, and a check is only as strong as your tests. Live auto mode is not yet
validated, and nobody has used the graph or workflows on a real run: they were checked against a scripted stand-in.
[Enforcement limits](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends)
· [Privacy](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#privacy).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md)
· [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md)
· [Comparisons](https://github.com/Alex-lop/Graphene/blob/main/docs/COMPARE.md)
· [Changelog](https://github.com/Alex-lop/Graphene/blob/main/CHANGELOG.md)
· [Contributing](https://github.com/Alex-lop/Graphene/blob/main/CONTRIBUTING.md)
· [Feedback](https://github.com/Alex-lop/Graphene/issues/new?template=first-hour.yml)
