# Graphene 0.10.0

<!-- Before tagging: README.md's two install blocks and editors/vscode/README.md's go back to the released commands
     in their comments (uv tool install graphene-map, the .vsix on the latest release), and the sentences saying
     0.10.0 is not released yet go: PyPI's page for 0.10.0 is the README as tagged. The release does not show
     this comment. -->

Install: `uv tool install graphene-map` (over 0.9.0, `uv tool upgrade graphene-map`). The VS Code extension's
`.vsix` is attached below: `cursor --install-extension graphene-0.10.0.vsix` (VS Code: `code --install-extension
graphene-0.10.0.vsix`). Upgrade both: with 0.9.0's CLI every task's pane says Not held and no check's box is
ticked. Or try it with nothing installed: `uvx graphene-map demo --auto`, a scripted replay (no key,
nothing written to your project); `uvx graphene-map demo` is the older one, a run you steer by hand. In the
editor, Graphene: Watch the Demo plays it.

## What you get that 0.9.0 did not have

- **The graph, whole, in a tab of its own.** Click Graphene's icon and the plan opens in an editor tab, fitted
  whatever its size: a plan too big for whole cards is drawn as rows, zoom goes from 20% to 300%, and choosing a
  card moves nothing. It opens by itself when work starts: beside your file in VS Code, in front of it in Cursor.
  Each card's foot is its check, with a box only Graphene ticks; the one act a task needs from you is a button on
  its card, and a chip walks them (`3 tasks need you · show the next`).
- **A plan from your agent's chat.** There is no box to type a goal in: Graphene's hooks have Claude Code or Codex
  propose a plan in its own chat before it writes, and it appears on the graph (Claude Code's task by task, as
  `graphene ask` reads it). Change a task's files, check or attempts on its Edit tab, draw one with Add task, then
  Start; Stop after the plan decides whether a plan waits for you.
- **Scope you can see.** A task's pane opens on Scope: the files it may change, what it may run, how a write
  outside them is held (no more than the tests prove), the writes that were stopped, and its check before and
  after the work (`graphene state --json` says them as `checked` and `held`).
- **Workflows.** Save as workflow writes the graph to `workflows/<name>.md`, and Home runs it again on new inputs
  with no planner call (`graphene workflow fix-issue -i issue=42`). A `run:` step is a command with no agent; one
  that pushes or opens a pull request waits past the leaves your machine line for Approve and run (`graphene node
  done ID`).
- **Codex held before the write.** `graphene init` installs Graphene's hooks for Codex too (`.codex/hooks.json`);
  live, three Codex attempts on one task had every patch outside its files refused before it landed. The gate
  fails closed: a write with no session, no path it can read, or a plan it cannot read is refused.
- **One look, one word a thing.** One set of colours, lines and corners for the graph and Home, made for Cursor's
  themes as for VS Code's; the same words on every screen: task, suggested, working, to review, needs help, done,
  attempt.

## What it does not do

- A write outside a task's files is refused before it happens by Claude Code's hooks and by Nemotron's edit and
  write, and by Codex's hooks once the project and its hooks are trusted in a new Codex session. A hook that is not
  loaded, crashes or times out lets the write through; so does any other CLI agent, or a write a hook cannot read
  (a target in a variable, a glob, a script that opens a file itself): git finds it when the task says it is done.
- No real agent ran the editor's new screens: the graph, Home, workflows and the live plan were walked against the
  scripted stand-in or a fake planner. One live Claude Code call confirmed the stream's shape; nobody has watched
  a real planner draw its plan. No workflow has pushed anything: `git push` and `gh pr` ran against a bare origin
  and a script.
- Auto mode is still not validated live; the envelope decides what is accepted, not whether the work is good,
  which is the checks' job.
- The extension is the `.vsix` on this release, not on the Marketplace or Open VSX. Windows only through WSL.
- The rule keeps one attempt by the check and a few counts; it does not read the code, and `graphene node pick` is
  yours when you disagree.
