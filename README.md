<p align="center"><img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark.svg" alt="The Graphene mark"></p>

# Graphene

**A team of coding agents on one repo. Each one owns its files. Your tests decide what lands.**

Give Graphene a goal. NVIDIA Nemotron plans it as small tasks that can run at once; several agents race each task,
each in its own copy and held to that task's files; the task's check keeps one; then Graphene runs your goal's own
check and, when it is red, plans the fix. You set the limits once. In your terminal or in VS Code, with Nemotron,
Claude Code, Codex or any model. On your computer, no account.

<p align="center">
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/v/graphene-map?color=5e5d59" alt="PyPI"></a>
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/pyversions/graphene-map?color=5e5d59" alt="Python"></a>
  <a href="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml"><img src="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Alex-lop/Graphene/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-5e5d59" alt="License"></a>
</p>

<p align="center"><img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/auto.gif" alt="graphene demo --auto: one goal; Nemotron plans three tasks that run at once; three agents race each task, one is stopped at a file outside its task, the rule keeps one fork a task; all three land; the whole test suite is red because two of them broke an old test together; Nemotron plans the fix, it races and lands, and the suite is green"></p>

## Try it

A scripted replay of auto mode on Nemotron: no AI, no key, nothing written to your project.

```
uvx graphene-map demo --auto
```

One goal, three tasks, nine agents at once, one of them stopped writing a file that is not its task's, and your
whole test suite catching what two tasks broke together. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/),
a free installer for Python tools. Then watch the locks hold: `uvx graphene-map demo --cheat` plays an agent
trying seven ways round them.

```
6 refused, 1 flagged, 0 got through
```

## One goal in, tested commits out

```
uv tool install 'graphene-map[nemotron]'
graphene key set                                   # your Token Factory key, or NEBIUS_API_KEY
graphene init --planner nemotron --executor nemotron
graphene auto "add a --top N option to the CLI, with tests" --budget 2 --forks 3 --check "python3 -m pytest -q"
```

1. **You set the envelope, once.** `--budget` in dollars, `--tasks`, fix `--rounds`, `--forks`, and in `graphene
   config` the files no task may touch and the test commands it may run as checks. Inside it Graphene accepts the
   plan for you; anything outside it waits for you, with the one reason why. Only you can set it: Graphene refuses it from an agent, and it never takes a task
   that could reach the agents' own settings and hooks.
2. **Nemotron 3 Ultra plans** small tasks, each naming the files it may change and a check, a command that passes
   only when the task is done. It is told to plan wide: tasks that run at once share no file, each its own test file.
3. **Agents race each task, all at once.** Three Nemotron 3 Nano agents a task, each in its own git worktree,
   refused before any write outside its task's files. Two tasks never write the same file, and each gets its own
   port, so their dev servers don't collide either.
4. **The check decides, not a model.** Graphene runs each fork's check itself, in a clean copy, and a rule written
   before any fork ran keeps one: the fork that passes the most of the other forks' tests, then the one that left
   the check's own files alone, the smaller, the cheaper, the first. It lands as one merge commit you can revert.
5. **Then your goal.** Your `--check` (or every task's check, together) runs on the merged result. Red: Ultra plans
   the fix and the race goes again, at most `--rounds` times, inside the budget. Every round, acceptance and fork
   is in `graphene plan log`, so the plan's history is there the morning after.

Add `--plan` the first time: the plan your envelope accepts is shown, and nothing runs until `graphene auto`
alone runs it.

![The loop: you shape the plan, your agents do the work, Graphene checks it](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ink.svg)

## Many agents, one repo

Agents in parallel go wrong first in one way: two of them edit the same file. Graphene's rule is one writer a
path: two running tasks never share a file, and a task that needs another's work waits on it. Each gets its own
worktree and its own `PORT`. The rule holds for agents you start yourself: open three Claude Code sessions with
three asks, and with `graphene config set auto on` every plan that fits your envelope is accepted at once, so
nobody waits on you to click through three plans; a plan that would write another's files waits, and says whose.

## Watch it, steer it

![graphene watch during the race: three tasks running at once, each as three forks on Nano; fork 1c stopped writing wordkit/count.py, which is not its task's; 1b passed with 7 lines; the auto line: round 1 of 3, $0.01 of $2.00](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/race.png)

`graphene watch` is the cockpit: a row a task, its agent's number and model, its forks as they race, what each one
costs, and what needs you on top. Enter does the row's move (accept, try again, sign off), `t` tells an agent one
line, `w` widens a task to the file it was stopped at, `f` forks a task, `?` shows every key.

`g` draws the plan as a graph flowing into your goal, with how many tasks can run at once. On it, `+` adds a step
after the task you're on and `L` links two tasks; `m` maps the folders each task may write; `:auto <goal>` starts
auto mode from the cockpit.

![the graph: four tasks flowing into the goal, each with its agent and model; auto, round 2 of 3, done, $0.02 of $2.00](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/auto-graph.png)

### In VS Code

![Graphene for VS Code: the plan as a graph in an editor tab, a task's three forks with their models and the kept one, the details of the selected task, and the buttons that add a step after it, link it, edit it or tell its agent](https://raw.githubusercontent.com/Alex-lop/Graphene/main/editors/vscode/media/graph.png)

The extension in [`editors/vscode`](https://github.com/Alex-lop/Graphene/blob/main/editors/vscode/README.md) shows
the same plan in an editor tab and a sidebar: the graph, the forks racing, the status bar (`◆ 2 running · 1 needs
you · $0.42`). Every click is a `graphene` command run as you: add a step, link two, edit, drop, accept, tell an
agent, and **Graphene: Auto…** for a goal. It reads `graphene state --json`, so the cockpit and the editor never
disagree. It is built for VS Code 1.95 and later, so its forks such as Cursor should load it (not tried there yet).

## Any agent, any model

| Who does the task | How a write outside its files is held |
|---|---|
| Nemotron on Token Factory (`--with nemotron`), or the same loop on NVIDIA NIM, Ollama or any OpenAI-compatible host (`--with 'nemotron --endpoint nim'`) | refused before the write, by Graphene's own tool loop |
| Claude Code (`--with claude`, `claude:MODEL`) | refused before the write, by its hooks |
| Codex (`--with codex`) | git finds it when the task finishes; the task comes back instead of landing |
| Any CLI agent (`--with 'aider --yes --message-file {prompt_file}'`) | git finds it when the task finishes |

`--with` again mixes them in one race: `--with nemotron --with claude:haiku --with codex` puts three different
agents on every task, and the same rule keeps one.

## In your hands

- **Stop:** Ctrl-C where `graphene auto` or `graphene run` runs, `graphene run --stop` from another terminal, or
  `:stop` in the cockpit. What was running goes back to the plan; `graphene auto` goes on from there.
- **Review:** `review: every` in `graphene config edit` holds every task that passes for your sign-off, auto mode
  too: `i` then `c` shows its diff, Enter lands it.
- **Cost:** the envelope's budget, or `graphene run --max-usd N`. With Claude Code, $2 an attempt, three at most,
  and a run says its worst case first; Nemotron bills each call after it ends, so auto mode reads the budget
  between rounds. Codex has no cap. A real two-task Claude Code run cost $0.30.
- **Undo:** `git revert -m 1 <id>` with the `landed:` id from `graphene node show <task>`; `graphene plan undo`
  takes back what your envelope accepted.
- **Leave:** `graphene init --remove`, then `uv tool uninstall graphene-map`. The plan and what the hooks recorded
  stay in `.graphene/` until you delete it.

Without auto mode, nothing runs until you accept: tell Claude Code what you want, and the plan shows in the cockpit
before it writes (with Codex: `graphene ask "what you want"`). Enter accepts a task, `A` all of them, `R` runs
what is ready, and it asks first when more than one task could start. `graphene plan first off` lets a quick
change through at once.

## What it enforces, and where it ends

- Refused before the write: Claude Code, and Graphene's own loop (Nemotron and the other hosts), shell redirects
  included where the hook can read them (a `#` comment line above one, or a target in a variable, hides it). With
  Codex or any other agent, git finds it when the task finishes; nothing outside a task's files ever lands.
- Scopes cover files. A task can still use the network, or a database two tasks share; its own port is as far as
  Graphene goes there.
- A task allowed to edit its own test can weaken it: `done` flags it, and `review: every` lets you read the diff
  first. The replay's fix round is one, and Graphene says so.
- The envelope decides what is accepted, not whether the work is good: that is the checks' job, and they are only
  as good as your tests. Auto mode has run end to end against a scripted stand-in of Token Factory; a live auto run
  is next.
- Honestly, in the three comparisons so far (September) a plain paragraph to the same agent did just as well for
  less. What I'm betting on is when you find out what it understood: before the work, not after.
  [Compared with Claude Code, Cursor, Kiro and Cline, gaps included](https://github.com/Alex-lop/Graphene/blob/main/docs/COMPARE.md) · [every limit](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends).

## Nemotron on Token Factory

For the Nebius × NVIDIA Global AI Hackathon, Graphene runs on NVIDIA Nemotron through Nebius Token Factory, from one
goal to tested commits. **How Nemotron is used:** Nemotron 3 Ultra plans, reading your repository with read-only
tools and answering in a strict JSON schema, so what it proposes is tasks Graphene can hold, planned so the tasks
that run at once share no file. Nemotron 3 Nano does the tasks in Graphene's own tool loop, whose write tools refuse
a file outside the task; in auto mode three Nanos race each task; a refused attempt steps up to Nemotron 3 Super;
and when the goal's own check is still red, Ultra plans the fix. **Where Token Factory sped it up:** one key and one
OpenAI-style endpoint from Python's standard library, one family in three sizes so each role gets the size it
needs, and a price on every model, so every task has its own bill (408 calls in a night came to $1.80). It ran live
in practice and in 31 demo takes on two small repositories on 7 to 9 October, and `uvx graphene-map demo --live`
replays one of them as it ran; auto mode has run against the scripted stand-in.
[Details, and every number's source.](https://github.com/Alex-lop/Graphene/blob/main/docs/HACKATHON.md)

## Does anything leave my computer?

With Claude Code or Codex, Graphene itself sends nothing anywhere. `graphene init` adds small add-ons (hooks) to
this project only, so Claude Code asks Graphene before it writes; they record its sessions on your machine:
prompts, tool calls, results, edited files. On the Nemotron path, the planner and the executors read your files
through Token Factory (or the host `--endpoint` names), as any hosted model does; with Ollama or another host on
your machine, nothing leaves it.

## Why I built this

I believe the limit on building software won't be tokens or cost. It'll be the human direction it takes. If you don't say which direction the application should go, the agent has to infer most of it, and you find out what it inferred in the diff. Graphene tries to bridge that. ([The longer version, in under three minutes.](https://www.youtube.com/watch?v=S3mucmwD-kQ))

Honestly, it's early, and I'm building it in the open. If you try it on a real repo, what I most want to hear is where the plan misread what you meant: [tell me in two minutes](https://github.com/Alex-lop/Graphene/issues/new?template=first-hour.yml), or [open an issue](https://github.com/Alex-lop/Graphene/issues).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md) · [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md) · [Changelog](https://github.com/Alex-lop/Graphene/blob/main/CHANGELOG.md) · [Contributing](https://github.com/Alex-lop/Graphene/blob/main/CONTRIBUTING.md) · [Alex Lopez](https://alex-lop.github.io/Alex_Lopez_Website/) · Apache-2.0
