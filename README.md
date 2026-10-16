<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark-ivory.svg" />
  <img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark-ink.svg" alt="The Graphene mark" width="72" />
</picture>

# Graphene

**Your AI coding agent stays inside the files you agreed to. "Done" means your tests passed, not that the agent said so.**

</div>

You ask your assistant for one small change. It edits files you didn't ask it to touch and says all tests pass. They don't. You find out in the diff, after the money is spent.

Graphene sits between you and Claude Code or Codex, on your computer, no account. You see the agent's plan and fix it before any code is written.

**Try it.** A scripted replay: no AI, no API key, nothing written to your project.

```
uvx --from graphene-map graphene demo
```

<sub>Needs [uv](https://docs.astral.sh/uv/getting-started/installation/), a free installer for Python tools.</sub>

Watch the locks hold: `graphene demo --cheat` tries seven ways round them.

<img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/watch.gif" alt="graphene demo: a plan is proposed, a leaf comes back with its reason, it lands" width="720" />

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ivory.svg" />
  <img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ink.svg" alt="The loop: you shape the plan, your agents do the work, Graphene checks it" width="720" />
</picture>

## How it works

1. **A plan you can edit.** Its small pieces are called leaves. Each names the files it may change and a check: a command that passes only when the leaf is done, like your tests. The agent proposes them; you can change any.
2. **Held to those files.** With Claude Code, a write to any other file is refused before it happens. With Codex, git catches it when the leaf finishes, and the leaf comes back to you instead of landing.
3. **Done is checked.** Graphene runs the check itself, in a clean temporary copy, then merges the leaf into your current branch as one merge.

## In your hands

- **Stop:** Ctrl-C, `graphene run --stop`, or `:stop` in watch.
- **Cost:** with Claude Code, $2 an attempt, three at most, and a run says its worst case first. Codex has no cap, and nothing caps the total yet. A real two-leaf run cost $0.30.
- **Undo:** `git revert -m 1 <id>`, with the `landed:` id from `graphene node show <leaf>`.
- **Leave:** `graphene init --remove`.

## On your project

You need a git folder, and Claude Code or Codex signed in.

```
uv tool install graphene-map
graphene init                              # pick Claude Code or Codex
graphene ask "what you want, in a paragraph"
graphene watch                             # in a second terminal
graphene plan accept
graphene run --parallel 2                  # two leaves at a time
```

With Claude Code, skip `ask`: type what you want and it proposes a plan first. In watch, `y` accepts, `d` drops a leaf, `R` runs what is ready (it asks first when more than one leaf could start). `graphene plan first off` lets a quick change through at once.

<details>
<summary><b>Does anything leave my computer?</b></summary>

With Claude Code or Codex, Graphene itself sends nothing anywhere. `graphene init` adds small add-ons (hooks) to your project, so Claude Code asks Graphene before it writes. They record its sessions on your machine only: prompts, tool calls, results, edited files.

</details>

<details>
<summary><b>Claude Code already shows plans. What does Graphene enforce?</b></summary>

So do Cursor, Kiro and Cline ([compared, gaps included](https://github.com/Alex-lop/Graphene/blob/main/docs/COMPARE.md)). Graphene enforces it:

- Refused before the write: Claude Code only, shell redirects included. With Codex, or if the add-on cannot run, git finds it when the leaf finishes.
- A leaf allowed to edit its own test can weaken it: `done` flags it, and a sign-off lets you read the diff first.
- Not yet: a look at every diff before it lands. A leaf marked for sign-off waits for you, and `c` in watch shows its diff; the rest land when their check passes. [Every limit](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends).
- Honestly, in the three comparisons so far a plain paragraph to the same agent did just as well for less. What I'm betting on is when you find out what it understood: before the work, not after.

</details>

<details>
<summary><b>Why I built this</b></summary>

I believe that in the near future, whether through new models, better harnesses, or a shift off the LLM frame entirely, the limit on building software won't be tokens or cost. The limiting factor will be the human intervention and drive it takes to actually get the software out. I know this sounds a little wild. The conversation is still mostly "who has the better model?" and "what's the best harness?" For most applications, though, I think the current models are already completely capable of debugging and fixing the work.

Ok, but not to ramble on too long, that idea is what drove me to build Graphene. No matter how many tokens you have, if you don't say which direction the application should go, the agent has to infer most of it. Graphene tries to bridge that connection between you and the agent. So, not claiming it magically saves 397% of your tokens but (ideally) it should help guide you and the agent toward that perfect idolized application you actually had in mind from the start.

</details>

Honestly, it's early, and I'm building it in the open. If you try it on a real repo, what I most want to hear is where the plan misread what you meant: [tell me in two minutes](https://github.com/Alex-lop/Graphene/issues/new?template=first-hour.yml), or [open an issue](https://github.com/Alex-lop/Graphene/issues).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md) · [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md) · [Alex Lopez](https://alex-lop.github.io/Alex_Lopez_Website/) · Apache-2.0
