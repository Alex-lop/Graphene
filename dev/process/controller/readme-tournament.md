# The README tournament, 14 October 2026

Six persona stand-ins (a designer who builds with an assistant, a product manager, a student, a skeptical senior engineer, an engineering manager, a developer who reads English second) read five pages cold, in rotated order: the old README as a blind control (A) and four independent drafts (B problem-first, C one promise and three holds, D show it first, E the shortest page).

| page | what | mean understood (0-10) | yes | maybe | no | mean rank (1 best) |
|---|---|---|---|---|---|---|
| A | the current README (blind control) | 4.9 | 0 | 4 | 2 | 5 |
| B | problem | 8.7 | 4 | 2 | 0 | 1.7 |
| C | promise | 8.3 | 4 | 2 | 0 | 2 |
| D | show | 7.4 | 3 | 3 | 0 | 2.8 |
| E | minimal | 7.3 | 2 | 4 | 0 | 3.5 |

## Before: five persona stand-ins on the old README, alone

- **vibe-coder**: would try *maybe*, understood 5/10. Stopped at: "a tree of leaves, each with its files and its check"; "With Graphene's hooks in the repo"; "a leaf lands as its own merge when its check passes"; "It's held by git and the check, not by the agent promising to behave.".
- **product-manager**: would try *maybe*, understood 6/10. Stopped at: "a tree of leaves, each with its files and its check"; "a leaf lands as its own merge when its check passes"; "Honestly, in the three comparisons so far a plain paragraph to the same agent di"; "It's held by git and the check, not by the agent promising to behave.".
- **student**: would try *maybe*, understood 6/10. Stopped at: "a tree of leaves, each with its files and its check"; "a leaf lands as its own merge when its check passes"; "Honestly, in the three comparisons so far a plain paragraph to the same agent di"; "It's held by git and the check, not by the agent promising to behave.".
- **skeptic**: would try *maybe*, understood 7/10. Stopped at: "Honestly, in the three comparisons so far a plain paragraph to the same agent di"; "a tree of leaves, each with its files and its check"; "It's held by git and the check, not by the agent promising to behave."; "They record its sessions on your machine (prompts, tool calls and what they retu".
- **eng-manager**: would try *maybe*, understood 6/10. Stopped at: "It's held by git and the check, not by the agent promising to behave."; "They record its sessions on your machine (prompts, tool calls and what they retu"; "Honestly, in the three comparisons so far a plain paragraph to the same agent di"; "Why I built this".

## The drafts' taglines

- **problem** (395 visible words): Your AI coding agent changes only the files you agreed to, and "done" means the tests really passed.
- **promise** (394 visible words): See what your AI coding agent understood, as a plan, before it writes code. Then hold it to that plan.
- **show** (391 visible words): Your AI coding agent shows you its plan before it writes code; each piece names the files it may change and the test it must pass, and Graphene holds it to both.
- **minimal** (176 visible words): Your AI coding agent shows you its plan before it writes code, and Graphene holds it to that plan.

## The fact-check (it blocked the synthesis until two things were fixed)

In one line: the published 0.5.0 is the 7 October tag, 184 commits behind main, so the README described commands a stranger's wheel does not have (checked with `uvx --isolated`, which ignores the tool installed on the person's own PATH).

Don't commit this README yet. Two problems block it.

1. **It describes code that isn't released.** The published 0.5.0 (PyPI, the same code as tag v0.5.0 from 7 Oct) does not have `init --remove`, `node diff`, the $2-per-attempt cap, the `landed: <sha>` line in `node show`, or R asking first. They exist only in the repo source, which still says 0.5.0. Release first, or mark them as unreleased. Plain `uvx --from graphene-map` on Alex's machine resolves to his git-installed tool (commit 3e59d24, also labelled 0.5.0), so local checks hide this. Use `uvx --isolated` to see what a stranger gets.
2. **It breaks a pinned test.** tests/test_tui.py:794 requires relative links to docs/assets/watch.gif and docs/assets/graphene-mark-ink.svg. This README uses absolute raw URLs and drops watch.gif, so the test fails.

Wording fixes:
- **"One commit of its own":** only true for `graphene run`, and it is a `--no-ff` merge. A Claude Code session never commits.
- **Undo:** name the `landed:` line. `revert -m 1` on the leaf's own branch commit, which `node show` also prints, fails.
- **"Takes Graphene out":** `init --remove` takes the hooks out only. The plan folder and the tool stay.
- **"Every ask … ends with its cost":** a Codex ask prints no cost.
- **Privacy:** the sentence needs "With Claude Code or Codex", because Nemotron sends data.
- **$2 cap:** applies to `graphene run`'s Claude executor, not to `ask` or a session you drive.

Verified:
- The demo is a scripted replay that writes nothing, in PyPI 0.5.0 and the local tool, in a git repo and a plain directory.
- Ctrl-C and `:stop` stop a run (tests/test_run_live.py:101 and :640, tests/test_tui.py:539).
- ATTEMPTS=3, and Codex has no cap.
- `git revert -m 1` is correct for the merge sha.
- Hooks fail open, and git catches the write at done while a leaf is held (gate.py:9, hooks.py:429, HOW_IT_WORKS).
- Shell redirects are refused (shell.py).
- The hooks' recording sentence matches.
- The anchor and all URLs resolve (200).
- The four test_doc_claims pins are present.

Word counts: 384 visible (outside details and code), 606 without code blocks, 653 with code (markup stripped), 722 raw `wc -w`. None of the repo's old banned words (from the deleted tests/test_words.py) appear. "just" appears once ("just as well"). Scratch copy of the README and the counter: $TMPDIR/scratch/README.md and count.py. PyPI 0.5.0 source inspected at ~/.cache/uv/archive-v0/qNGgkOJjngN_l1RF/lib/python3.13/site-packages/graphene_map.

| verdict | claim | fix |
|---|---|---|
| wrong | Published 0.5.0 matches the README ("Version 0.5.0"; `uv tool install graphene-map`; `uvx --from graphene-map` | Release a new version (docs/RELEASING.md) before this README goes on main, and change "Version 0.5.0" to match. If that can't happen first, mark the newer features as unreleased or install from git+ht |
| wrong | README passes the repo's pinned README tests | Either use relative src/srcset paths (docs/assets/graphene-mark-ink.svg etc.) and embed docs/assets/watch.gif again, or update the test in the same commit to accept absolute raw URLs on main and drop  |
| wrong | Commands named exist with the flags shown: init, ask "…", watch, plan accept, run --parallel 2, node show <lea | Ship a release that includes them, or say they need the unreleased version. |
| wrong | Only then is the leaf added to your project, as one commit of its own | "With `graphene run`, only then is the leaf merged into your branch, as one merge of its own; in a Claude Code session the changes stay in your working tree for you to commit." |
| wrong | With Claude Code, an attempt stops at $2, three per leaf | Ship the cap in a release, then: "with `graphene run` and Claude Code, an attempt stops at $2, three attempts a run". |
| wrong | Every ask and run ends with its cost | "Every run, and every ask with Claude Code, ends with its cost." |
| wrong | `graphene node show <leaf>` gives the leaf's commit id; `git revert -m 1 <sha>` takes it back alone | "Undo: the `landed:` line of `graphene node show <leaf>` names the merge; `git revert -m 1 <that sha>` takes it back alone (leaves landed by `graphene run`)." |
| wrong | `graphene init --remove` takes Graphene out | "`graphene init --remove` takes the hooks out; the plan folder is yours to delete, and `uv tool uninstall graphene-map` removes the tool." |
| wrong | Graphene itself sends nothing anywhere | "With Claude Code or Codex, Graphene itself sends nothing anywhere." |
| unverifiable | Cursor, Kiro and Cline show plans | none |

## After: six cold re-reads of the synthesized README (before the fixes above)

Mean understood 7.2/10; would try: vibe-coder maybe, product-manager maybe, student maybe, skeptic maybe, eng-manager maybe, esl-developer yes.

- **vibe-coder** (6/10): "Its small pieces are called leaves."; "its check: a command that succeeds only when the leaf is done, like yo"; "With Codex, git finds it when the leaf finishes, and the leaf is held "
- **product-manager** (7/10): "Its small pieces are called leaves."; "With Codex, git finds it when the leaf finishes, and the leaf is held "; "git revert -m 1 <sha>"
- **student** (7/10): "git revert -m 1 <sha>"; "Its small pieces are called leaves."; "With Codex, git finds it when the leaf finishes, and the leaf is held "
- **skeptic** (7/10): "Honestly, in the three comparisons so far a plain paragraph to the sam"; ""done" means the tests really passed"; "Before any code, you see the agent's plan and fix it."
- **eng-manager** (8/10): "Codex has no cap, and nothing caps the total yet."; "With Codex, git finds it when the leaf finishes, and the leaf is held "; "Otherwise, or if the add-on cannot run, git finds them when the leaf f"
- **esl-developer** (8/10): "Its small pieces are called leaves."; "`git revert -m 1 <sha>`"; "Honestly, in the three comparisons so far a plain paragraph to the sam"

## What was changed after the re-read

The headline says the agent stays inside the files (not that it changes only them); 'really' is gone; the check is said to be proposed by the agent and changeable by the person; 'held back' became 'comes back to you instead of landing'; the Undo line names the `landed:` id; cost says three attempts at most and what a real run cost; where it lands is said; `plan first off` left the privacy fold; the Claude Code path (no `ask`) is one sentence; the unreleased version number is gone from the page.


## The synthesized README before those edits

```markdown
<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark-ivory.svg" />
  <img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark-ink.svg" alt="The Graphene mark" width="72" />
</picture>

# Graphene

**Your AI coding agent changes only the files you agreed to, and "done" means the tests really passed.**

</div>

You ask your assistant for one small change. It edits files you didn't ask it to touch and reports that all tests pass. They don't. You find out in the diff, after the time and money are spent.

Graphene sits between you and Claude Code or Codex, on your computer, no account. Before any code, you see the agent's plan and fix it. Then the work starts.

**Try it.** A scripted replay: no AI runs, no API key, nothing written to your project.

```
uvx --from graphene-map graphene demo
```

<sub>Needs [uv](https://docs.astral.sh/uv/getting-started/installation/), a free installer for Python tools that also fetches Python.</sub>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ivory.svg" />
  <img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/loop-ink.svg" alt="The loop: you shape the plan, your agents do the work, Graphene checks it" width="720" />
</picture>

## How it works

1. **You see the plan first.** Its small pieces are called leaves. Each names the files it may change and its check: a command that succeeds only when the leaf is done, like your tests.
2. **The agent stays inside those files.** With Claude Code, a write to any other file is refused before it happens. With Codex, git finds it when the leaf finishes, and the leaf is held back.
3. **Done is checked, not claimed.** Graphene runs the check itself, in a clean copy of your files, rather than take the agent's word. Only then is the leaf added to your project, as one commit of its own.

## You stay in control

- **Stop:** Ctrl-C, or `:stop` in watch, the live view of the plan.
- **Cost:** with Claude Code, an attempt stops at $2, three per leaf. Codex has no cap, and nothing caps the total yet. Every ask and run ends with its cost.
- **Undo:** `graphene node show <leaf>` gives the leaf's commit id (its sha); `git revert -m 1 <sha>` takes it back alone.
- **Leave:** `graphene init --remove` takes Graphene out.

## On your project

You need a folder tracked by git, and Claude Code or Codex signed in.

```
uv tool install graphene-map
graphene init                             # pick Claude Code or Codex
graphene ask "what you want, in a paragraph"
graphene watch                            # in a second terminal
graphene plan accept
graphene run --parallel 2
graphene node show <leaf>                 # what changed, what it cost
```

In watch, `y` accepts, `R` runs what is ready (it asks first when more than one leaf could start), `?` shows the rest.

<details>
<summary><b>Does anything leave my computer?</b></summary>

Graphene itself sends nothing anywhere. For Claude Code, `graphene init` adds small add-ons (hooks) to that one project so Claude Code asks Graphene before it writes. They record its sessions on your machine only: prompts, tool calls and results, edited files. `graphene plan first off` lets quick changes through.

</details>

<details>
<summary><b>Claude Code already shows plans. What does Graphene enforce?</b></summary>

So do Cursor, Kiro and Cline. Graphene then enforces it:

- Other files are refused before the write: Claude Code only, shell redirects included. Otherwise, or if the add-on cannot run, git finds them when the leaf finishes.
- A leaf allowed to edit its own test can weaken it: read `graphene node diff <leaf>`.
- Not yet: approving a diff before it lands. [Every limit](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends).
- Honestly, in the three comparisons so far a plain paragraph to the same agent did just as well for less. What I'm betting on is when you find out what it understood: before the work, not after. Version 0.5.0.

</details>

<details>
<summary><b>Why I built this</b></summary>

I believe the limit on building software won't be tokens or cost. It'll be the human direction it takes. If you don't say which direction the application should go, the agent has to infer most of it, and you find out what it inferred in the diff. Graphene tries to bridge that.

</details>

Honestly, it's early, and I'm building it in the open. If you try it on a real repo, what I most want to hear is where the plan misread what you meant: [open an issue](https://github.com/Alex-lop/Graphene/issues).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md) · [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md) · [Alex Lopez](https://alex-lop.github.io/Alex_Lopez_Website/) · Apache-2.0
```

