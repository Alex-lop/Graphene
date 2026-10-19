![The Graphene mark](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark.svg)

# Graphene

**Your AI coding agent stays inside the files you agreed to. "Done" means your tests passed, not that the agent said so.**

One screen beside Claude Code or Codex: see what every agent is doing, tell it what you meant, and land a task only when its check passes. On your computer, no account.

[![PyPI](https://img.shields.io/pypi/v/graphene-map?color=5e5d59)](https://pypi.org/project/graphene-map/) [![Python](https://img.shields.io/pypi/pyversions/graphene-map?color=5e5d59)](https://pypi.org/project/graphene-map/) [![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg)](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/license-Apache--2.0-5e5d59)](https://github.com/Alex-lop/Graphene/blob/main/LICENSE)

![graphene demo: four tasks proposed with a question, an assumption and a leave-out, three agents at once, agent 1 stopped at a file outside its task and handing it back with its reason, the retry, everything proven, then the plan as a graph](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/watch.gif)

## Try it

A scripted replay of a run: no AI, no key, nothing written to your project.

```
uvx graphene-map demo
```

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/), a free installer for Python tools. Then watch the locks hold: `uvx graphene-map demo --cheat` plays an agent trying seven ways round them.

```
6 refused, 1 flagged, 0 got through
```

## How it works

1. **You say where it should go.** Your agent proposes a plan before it writes: small tasks, each naming the files it may change and a check, a command that passes only when the task is done, like your tests. What it would have guessed comes back as a question with a default. You change any of it first.
2. **Each task is held to its files.** With Claude Code, a write to any other file is refused before it happens. With Codex, git catches it when the task finishes, and the task comes back to you instead of landing.
3. **Done is checked.** Each task runs in its own worktree. Graphene runs the check itself, in a clean copy, then merges the task into your branch as one commit you can revert.

![The loop: you shape the plan, your agents do the work, Graphene checks it](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ink.svg)

## What you see

`graphene watch` is the cockpit: a row a task, numbered in the order the tasks were taken, and what needs you on top. Enter does the row's move (accept, try again, sign off), `t` tells an agent one line, `w` widens a task to the file it was stopped at, `?` shows every key.

![graphene watch: agent 1 has handed its task back with its reason, the word lives in words.py, and Enter tries again; agents 2 and 3 are running, and a fourth task waits on agents 1 and 2](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/cockpit.png)

`g` draws the plan as a graph from your goal down; `m` maps the folders each task may write.

![the graph: the goal, its two sub-goals, the four tasks under them, and the task that waits on two others](https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graph.png)

## On your project

You need a git repository, Claude Code or Codex signed in, and macOS or Linux.

```
uv tool install graphene-map
graphene init        # in your own terminal: pick Claude Code or Codex
graphene watch       # the cockpit, beside your agent
```

Then tell Claude Code what you want, and the plan shows in the cockpit before it writes (with Codex: `graphene ask "what you want"`). Enter accepts a task, `A` all of them, and `R` runs what is ready on your Claude Code or Codex account; it asks first when more than one task could start. `graphene plan first off` lets a quick change through at once. Accepting is yours: Graphene refuses it from an agent, so run `init` and accept in your own terminal.

## In your hands

- **Stop:** Ctrl-C where `graphene run` runs, `graphene run --stop` from another terminal in the repo, or `:stop` in the cockpit.
- **Review:** `review: every` in `graphene config edit` holds every task that passes for you: `i` then `c` shows its diff, Enter on its row lands it.
- **Cost:** with Claude Code, $2 an attempt, three at most, and a run says its worst case first; `graphene run --max-usd N` caps a run. Codex has no cap. A real two-task run cost $0.30.
- **Undo:** `git revert -m 1 <id>`, with the `landed:` id from `graphene node show <task>`.
- **Leave:** `graphene init --remove`, then `uv tool uninstall graphene-map`. The plan and what the hooks recorded stay in `.graphene/` until you delete it.

## What it enforces, and where it ends

- Refused before the write: Claude Code only, shell redirects included. With Codex, or if the hook cannot run, git finds it when the task finishes.
- A task allowed to edit its own test can weaken it: `done` flags it, and `review: every` lets you read the diff first.
- Honestly, in the three comparisons so far (September) a plain paragraph to the same agent did just as well for less. What I'm betting on is when you find out what it understood: before the work, not after. [Compared with Claude Code, Cursor, Kiro and Cline, gaps included](https://github.com/Alex-lop/Graphene/blob/main/docs/COMPARE.md) · [every limit](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends).

## Nemotron on Token Factory

For the Nebius × NVIDIA Global AI Hackathon I built a third way to run it, on NVIDIA Nemotron through Nebius Token Factory:

```
uv tool install --python 3.12 'graphene-map[nemotron]'
graphene key set                                     # or NEBIUS_API_KEY
graphene init --planner nemotron --executor nemotron
```

Nemotron 3 Ultra reads your repository and plans, in a strict JSON schema, tasks Graphene can hold. Nemotron 3 Nano does them in Graphene's own tool loop, whose writes refuse a file outside the task, and a refused attempt steps up to Super. Token Factory made the split cheap: one endpoint, one family in three sizes, a price on every call, so each task has its own bill (408 calls in a night came to $1.80). It ran live in practice and in 31 demo takes on 7 to 9 October, and `uvx graphene-map demo --live` replays one of them as it ran; the rest is tested against a scripted stand-in, which `graphene demo` replays. [Details, and every number's source.](https://github.com/Alex-lop/Graphene/blob/main/docs/HACKATHON.md)

## Does anything leave my computer?

With Claude Code or Codex, Graphene itself sends nothing anywhere. `graphene init` adds small add-ons (hooks) to this project only, so Claude Code asks Graphene before it writes; they record its sessions on your machine: prompts, tool calls, results, edited files. On the Nemotron path, the planner and the executors read your files through Token Factory, as any hosted model does, and with that extra and a key set, `graphene init` asks Token Factory for its list of models.

## Why I built this

I believe the limit on building software won't be tokens or cost. It'll be the human direction it takes. If you don't say which direction the application should go, the agent has to infer most of it, and you find out what it inferred in the diff. Graphene tries to bridge that. ([The longer version, in under three minutes.](https://www.youtube.com/watch?v=S3mucmwD-kQ))

Honestly, it's early, and I'm building it in the open. If you try it on a real repo, what I most want to hear is where the plan misread what you meant: [tell me in two minutes](https://github.com/Alex-lop/Graphene/issues/new?template=first-hour.yml), or [open an issue](https://github.com/Alex-lop/Graphene/issues).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md) · [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md) · [Changelog](https://github.com/Alex-lop/Graphene/blob/main/CHANGELOG.md) · [Contributing](https://github.com/Alex-lop/Graphene/blob/main/CONTRIBUTING.md) · [Alex Lopez](https://alex-lop.github.io/Alex_Lopez_Website/) · Apache-2.0
