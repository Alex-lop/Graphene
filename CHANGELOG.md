# Changelog

## Unreleased

The session product becomes a node's record, and that record works for whoever did the work.
- `graphene node show <id>`'s coverage block is computed from the node's own log, from git and from the check Graphene ran, so a node done by Codex, by `graphene run --with <anything>` or by you at the terminal gets a real line instead of "not computed". The commits inside a node's windows are asked of git directly; the store only ever held those a recorded session's window covered. Claude Code's records, where they exist, still say which path traces to a write somebody recorded making; where they do not, the block says what it was read from and grades every path "to git alone".
- The check Graphene ran is printed in the coverage block, with its command, result and time: it is what verifies the change set.
- Removed: `graphene why` and `graphene why PATH:LINE`, the session card (plain `graphene` with no plan, `graphene debrief`, `graphene --session/--since/--json`) and `graphene sessions`, with the prompt→file→hunk reconstruction behind them. All of it could only answer for a Claude Code session, and none of it is what a node's record needs. The map (`graphene ui`) and its page are unchanged. In a repo with no plan, `graphene` now says how to start one; `graphene ui --session ID` still picks a session, and the page's rail lists them.

## 0.3.0 (unreleased)

Graphene becomes the plan a person and their coding agents share; the record now hangs off it.
- `graphene plan` and `graphene node`: nodes with a goal, a scope (globs), a check, what they wait on, an owner (any agent, or a person) and a state. Agents propose; only a person accepts, edits, signs off, reopens, overrules, pauses or archives.
- `graphene node done` is the gate: Graphene runs the check itself and asks git what changed since the node was started. A change outside the scope keeps the node open, however the file was written.
- With `graphene init`, the Claude Code hooks refuse a write outside the scope of the node a session holds (every permission mode, subagents too) and refuse a stop while a node is open. `init` adds one event, `PreToolUse`; run it again in a repo set up earlier.
- `graphene run`: one executor per ready node (`--with 'claude -p …'`, `'codex exec …'`), and Graphene decides what is done.
- `graphene` alone shows the plan when the repo has one; `graphene node show <id>` is a node's record: who held it, what changed, what was refused, how much is verified.
- `graphene ui` opens on the plan, and a person can edit it there.
- Removed: the guess at "not what you asked for" from prompt text. Scope is a fact of the node now.
- The store moves to schema 3 by an additive step; a 0.2 store is upgraded in place.

## 0.2.0 (2026-09-20)

The truthful record and the first map: agents as records (task, parent, worktree, closing message), commits credited by record, the coverage line as three counts, `graphene ui` and `--export`. `--explain`, `--model`, `--full`, `--md` and `--html` were removed; the package became `graphene-map`.

## 0.1.0 (unreleased)

Graphene reads the transcripts Claude Code keeps on your machine and answers which prompt changed a file or a line: `graphene`, `graphene why PATH[:LINE]`, `graphene init`.
