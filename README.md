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

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ivory.svg" />
  <img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ink.svg" alt="The loop: you shape the plan, your agents do the work, Graphene checks it" width="720" />
</picture>

## How it works

1. **A plan you can edit.** Its small pieces are called leaves. Each names the files it may change and a check: a command that passes only when the leaf is done, like your tests. The agent proposes them; you can change any.
2. **Held to those files.** With Claude Code, a write to any other file is refused before it happens. With Codex, git catches it when the leaf finishes, and the leaf comes back to you instead of landing.
3. **Done is checked.** Graphene runs the check itself, in a clean temporary copy, then merges the leaf into your current branch as one merge.

## In your hands

- **Stop:** Ctrl-C, or `:stop` in watch.
- **Cost:** with Claude Code, $2 an attempt, three at most. Codex has no cap, and nothing caps the total yet. A real two-leaf run cost $0.30.
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

With Claude Code, skip `ask`: type what you want as usual and it proposes a plan first. In watch, `y` accepts, `d` drops a leaf, `e` edits one, `R` runs what is ready (it asks first when more than one leaf could start). `graphene plan first off` lets a quick change through at once.

<details>
<summary><b>Does anything leave my computer?</b></summary>

With Claude Code or Codex, Graphene itself sends nothing anywhere. `graphene init` adds small add-ons (hooks) to your project, so Claude Code asks Graphene before it writes. They record its sessions on your machine only: prompts, tool calls, results, edited files.

</details>

<details>
<summary><b>Claude Code already shows plans. What does Graphene enforce?</b></summary>

So do Cursor, Kiro and Cline. Graphene enforces it:

- Refused before the write: Claude Code only, shell redirects included. With Codex, or if the add-on cannot run, git finds it when the leaf finishes.
- A leaf allowed to edit its own test can weaken it: read `graphene node diff <leaf>`.
- Not yet: approving a diff before it lands. [Every limit](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends).
- Honestly, in the three comparisons so far a plain paragraph to the same agent did just as well for less. What I'm betting on is when you find out what it understood: before the work, not after.

</details>

<details>
<summary><b>Why I built this</b></summary>

I believe the limit on building software won't be tokens or cost. It'll be the human direction it takes. If you don't say which direction the application should go, the agent has to infer most of it, and you find out what it inferred in the diff. Graphene tries to bridge that.

</details>

Honestly, it's early, and I'm building it in the open. If you try it on a real repo, what I most want to hear is where the plan misread what you meant: [open an issue](https://github.com/Alex-lop/Graphene/issues).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md) · [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md) · [Alex Lopez](https://alex-lop.github.io/Alex_Lopez_Website/) · Apache-2.0
