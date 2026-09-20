# Changelog

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

## 0.2.0 (unreleased)

The truthful record and the first map: agents as records (task, parent, worktree, closing message), commits credited by record, the coverage line as three counts, `graphene ui` and `--export`. `--explain`, `--model`, `--full`, `--md` and `--html` were removed; the package became `graphene-map`.

## 0.1.0 (unreleased)

Graphene reads the transcripts Claude Code keeps on your machine and answers which prompt changed a file or a line: `graphene`, `graphene why PATH[:LINE]`, `graphene init`.
