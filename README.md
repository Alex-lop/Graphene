<p align="center"><img src="https://raw.githubusercontent.com/Alex-lop/Graphene/main/docs/assets/graphene-mark.svg" alt="The Graphene mark"></p>

<h1 align="center">Graphene</h1>

**See what your coding agents are doing, and what they did. Nothing to set up.**

Install the extension and start Claude Code or Codex as you always do. A page opens beside your file and draws
that session as a graph. Click a card to see that agent's terminal. When it finishes, each card carries a receipt:
the files it changed and whether its tests passed. Nothing refuses, delays or holds your agent.

<p align="center">
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/v/graphene-map?color=5e5d59" alt="PyPI"></a>
  <a href="https://pypi.org/project/graphene-map/"><img src="https://img.shields.io/pypi/pyversions/graphene-map?color=5e5d59" alt="Python"></a>
  <a href="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml"><img src="https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Alex-lop/Graphene/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-5e5d59" alt="License"></a>
</p>

![Graphene in VS Code. In the side bar, Home lists the folder's session. In the editor, the session's page: four cards joined by curved lines, left to right. The request, done, with the files it changed and a ticked "unittest passed" at its foot; the two subagents it started, each "ran no tests"; and a follow-up request, done, with its own ticked test. Under each card, one line of what it said last](https://raw.githubusercontent.com/Alex-lop/Graphene/main/editors/vscode/media/session.png)

*A real Claude Code session in a scratch repository, as its page drew it.*

Every mark on the page answers one of four questions:

- **What is it doing?** A card for each request you made, each task on the agent's own list and each subagent it
  started. The one at work says so, with its last move under it.
- **Does it need me?** A card says **needs you** only when the session's file shows it waiting for your answer.
- **What did it change?** The files each card wrote. Click one for its diff.
- **Did it work?** The tests it ran and what they said: passed, failed, or ran none. A tick only for a pass that
  was seen, and a short list of what is worth a second look (a push, a delete, a test edited after it failed).
  **Ran no tests** means the agent ran none, or was not allowed to: it is what the session shows, not a fault.

## Try it

The extension, 0.11.0, from the [release](https://github.com/Alex-lop/Graphene/releases/latest) (it is not on the
Marketplace or Open VSX yet):

```sh
curl -LO https://github.com/Alex-lop/Graphene/releases/download/v0.11.0/graphene-0.11.0.vsix
code --install-extension graphene-0.11.0.vsix
```

In Cursor: `cursor --install-extension graphene-0.11.0.vsix`. No `code` or `cursor` on your PATH? In the editor,
Extensions → ⋯ → **Install from VSIX…**. From a clone instead: `npm ci && npm run package` in `editors/vscode`
(Node 22+). Then:

1. Open any folder (git or not) and start Claude Code or Codex in it, in a terminal or in its own panel: `claude`,
   or `claude -p "…"` for one ask. A few seconds after the session's first line a page opens in the editor area,
   beside your file if one is open, and the file keeps the keyboard. Until then the ◆ in the status bar says how
   many sessions Graphene sees here. (`graphene.graph.openOnStart` turns the page off.)
2. Click a card: the terminal it runs in, or a view of what it writes when it runs outside the editor.
3. When it finishes, read each card's receipt, and click a file for its diff.
4. A second session gets a page of its own; **Add to page…** puts it on this one, as a band. **Home**, in the side
   bar, lists the folder's sessions, live ones first, and **Resume in terminal** picks an idle one up again.

No session yet? The empty page replays a recorded one. In a folder the editor has not been told to trust
(Restricted Mode), the extension is off.

## Strict mode

Graphene as it was through 0.10, now opt-in, a folder at a time: your agent proposes a plan before it writes, each
task owns its files and a Git worktree, and Graphene runs each task's check itself and merges only what passes. It
needs the CLI (Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git; macOS or Linux):

```sh
uv tool install graphene-map     # installed already: uv tool upgrade graphene-map
cd your-repo
graphene init    # choose the planner and executor; installs the Claude Code and Codex hooks
graphene watch   # the cockpit: the plan the editor shows
```

In the editor, **Home → Strict mode…** sets the folder up. In the cockpit, `A` accepts the plan and `R` runs ready
tasks; it asks first when more than one task could start. `graphene plan first off` lets quick changes through,
`graphene init --remove` removes the hooks, and `uvx graphene-map demo --auto` is a scripted replay of a run: no
key, nothing written to your project. The [extension guide](https://github.com/Alex-lop/Graphene/blob/main/editors/vscode/README.md#strict-mode) and
[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md) have the rest.

## Know the limits

Graphene is early, and nobody outside has used it yet.

- **What ran on real sessions.** Claude Code sessions started in a terminal (`claude` and `claude -p`), on macOS,
  in VS Code and in Cursor: the page, the terminal on click, resume and receipts. **What did not:** Codex sessions
  are read from their files and were not walked in an editor; Cursor's own agent is not read; Windows and Linux
  are untested.
- **What a receipt cannot see.** It reads the session's file and git, nothing else. A file a shell command changed
  is listed only as changed with no tool call, and only for a session Graphene saw begin; git does not say who
  changed it. A test whose output never reached the session (sent to a file, run in the background) is **ran,
  result not seen**. A flag says what was run (`git push`), not what it did. A session waiting on a permission
  prompt does not say **needs you**: the prompt is not in its file. A check is only as strong as your tests.
- **Private by construction.** The extension reads the session files Claude Code and Codex write on your machine
  (`~/.claude/projects`, `~/.codex/sessions`) and runs read-only `git` in your folder. It sends nothing anywhere:
  no request, no telemetry.
- **Strict mode** is file coordination, not a security sandbox. Its live auto mode is not yet validated, and its
  graph and workflows were checked against a scripted stand-in, not a real run.
  [Enforcement limits](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#where-each-mechanism-ends)
  · [privacy](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md#privacy).

[How it works](https://github.com/Alex-lop/Graphene/blob/main/docs/HOW_IT_WORKS.md)
· [A real run](https://github.com/Alex-lop/Graphene/blob/main/docs/A_RUN.md)
· [Comparisons](https://github.com/Alex-lop/Graphene/blob/main/docs/COMPARE.md)
· [Changelog](https://github.com/Alex-lop/Graphene/blob/main/CHANGELOG.md)
· [Contributing](https://github.com/Alex-lop/Graphene/blob/main/CONTRIBUTING.md)
· [Feedback](https://github.com/Alex-lop/Graphene/issues/new?template=first-hour.yml)
