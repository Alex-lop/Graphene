# Graphene 0.9.0

Install: `uv tool install graphene-map` (over 0.8.0, `uv tool upgrade graphene-map`), or `uv tool install
'graphene-map[nemotron]'` for the Nemotron path. Or try it with nothing installed: `uvx graphene-map demo --auto`,
a scripted replay of auto mode on Nemotron (no key, nothing written to your project); `uvx graphene-map demo` is
the older one, a run you steer by hand. The VS Code extension's `.vsix` is attached below: install it with
`code --install-extension` (Cursor: `cursor --install-extension`), open a folder, and Graphene: Watch the Demo
needs no key.

## What you get that 0.8.0 did not have

- **Auto mode, watched and steered from VS Code, with a click.** Home leads the side bar: set a folder up in
  one pick, type what you want and click Plan it, read each suggested task (what it is for, the files it may
  change, what proves it), and Start. Each finished task shows what it changed, the check that passed and its
  last steps, with Open changes, Approve and Send back; review is on by default, and Approve asks first when the
  changes were never opened. The palette lists seven commands. The graph shows the race and reads at every
  width, in the side bar as lanes and in a tab; the editor streams the plan (`graphene state --json --watch`).
- **Diffs in the diff editor.** A task's or a fork's changes open in VS Code's own diff editor, a race's forks
  side by side; Keep This Attempt and Approve sit in the title (`graphene node diff ID --json` underneath).
- **The plan as text, and a step in a sentence.** Edit Plan as Text opens the plan in a tab; saving applies it,
  and a refusal is a diagnostic on its line (`graphene plan edit --from - --json`). Add Step… takes one sentence
  and the planner proposes the step (`graphene ask "<sentence>" --step --after ID`).
- **The demo in the editor.** Watch the Demo plays the auto replay in a graph of its own, with no key and no
  network (`graphene demo --auto --into DIR`).
- **First run without hunting.** The extension finds `graphene` in `~/.local/bin` and uv's tool directory,
  offers to install it, sets a folder up in one pick, and a refused key offers Set API Key (`graphene key set`).
- **The gate after a review.** Two reviewers who did not build auto mode found nine ways past it; each is closed
  with the test that failed first. A write is judged where it lands (a committed symlink into `.git/`), a `git
  config` that writes is refused, `.CLAUDE/` is `.claude/`, a `#` cannot hide a second command in a check, a
  check runs unread only when it is one plain command, the `tasks` cap counts nested tasks, and the budget is
  read before the planner is asked.
- **Refusals that lead somewhere.** A refusal's advice, followed as printed, now gets past it: `graphene auto`
  names the drop that ends an open goal (it named `graphene plan archive`, which cannot), `--with 'claude
  --max-budget-usd X'` sets Claude Code's cap an attempt when the budget left is under it, undo is advised only
  while it puts back that very act, and init names the install that brings `graphene key set`.
- **A harness for real VS Code and Cursor.** `editors/vscode/e2e` installs the `.vsix` in a profile of its own,
  races a fixture against the scripted stand-in and measures what it sees. The `.vsix` installs and activates in
  Cursor 3.25.6, and the check passes there.
- **Ready for the Marketplace and Open VSX.** An icon, a listing page and a workflow that publishes the `.vsix`
  to both from a release.

## What it does not do

- A write outside a task's files is refused before it happens by Claude Code's hooks and by Nemotron's edit and
  write; with Codex, any other CLI agent, or a write the hook cannot read (a target in a variable it was not
  given, a glob, a script that opens a file itself, an interpreter taking code on its command line), git finds
  it when the task says it is done.
- Auto mode ran end to end against a scripted stand-in of Token Factory, not yet live; the envelope decides what
  is accepted, not whether the work is good, which is the checks' job.
- Home has been clicked through in real VS Code by the harness, against the scripted stand-in; no one has run it
  on a live model yet. A model session played a stranger on 0.8.0's extension, and the harness measured pixels
  and seconds. The Marketplace and Open VSX listings are the publisher's next step.
- Nemotron bills each call after it ends, so auto mode reads the budget between rounds; Codex has no cap of its
  own, and `--max-usd` stops starts, not an attempt that is going.
- The rule keeps one fork by the check and a few counts; it does not read the code, and `graphene node pick` is
  yours when you disagree.
