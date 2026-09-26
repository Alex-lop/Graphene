# Changelog

## Unreleased (after 0.4.0)

- The import package is `graphene_map`, matching the distribution (it was `graphene_debrief`). The command is still `graphene`, and installed hooks keep working. Anything that imported `graphene_debrief` imports `graphene_map`.
- NVIDIA Nemotron on Nebius Token Factory, as planner and executor: `graphene ask --with nemotron` (Ultra, read-only tools) and `graphene run --with nemotron` (Nano, then Super on a refused attempt; `--forks N`; `--placement local|sandbox`). Model ids come from the live model list, and every call's usage is priced at its list price. Needs `NEBIUS_API_KEY`.
- Token Factory Sandboxes: `pip install 'graphene-map[sandbox]'` (contree-sdk 0.3.6). A leaf's commands run as a user who can write only its scope, what a command makes outside it never comes back, and its check runs in a fork of the sandbox.
- `graphene init` asks once which planner and executor a repository uses, Nemotron first; `run`, `ask`, `node split` and the screen use it, and `--with` overrides one command.
- A check runs in a clean worktree of the leaf's state: nothing it writes lands in the executor's tree. No check gets the Token Factory key.
- `graphene watch` folds: done subtrees fold, a folded row counts its leaves by state, a tall tree opens as its outline; `za zo zc zR zM zx`.
- The bill: what the Nemotron planner and executors cost, at list price, in `graphene node show`, `graphene plan record`, the run's last line and the screen's status line.
- `graphene ui --export` draws a `graphene run` from the store alone; `.github/workflows/pages.yml` publishes the demo page when started by hand.
- Python 3.14 in CI; the store binds values to plain `?` only.
- Graphene reads no Claude Code transcript: `graphene ui` draws the plan and the sessions the hooks recorded; `graphene ingest --backfill` is removed (`graphene ingest hook` is unchanged). A session run before `graphene init`, or without the hooks, is not on the map. Internal: `graphene_map.attribute` is `graphene_map.shell`, `graphene_map.sources.claude_code` is `graphene_map.hooks`, `repo_root` lives in `graphene_map.store`. The screen harness is `docs/screens/`.
- Sandboxes: a clean commit's checkpoint is made once and every leaf at it forks it; `--forks` forks one sandbox; `--image` and `--prepare`; the file list is read back whole; what git ignores is nobody's change. An executor that cannot work hands its leaf back with the cause. The planner and executor read only what git shows. A reasoning model's cut-off reply, Nemotron's `<TOOLCALL>` text and common tool names are handled. A `--parallel` leaf's record holds its own commits, and a Nemotron leaf's is graded by the writes it recorded.
- `docs/test/`: `bench.py` and `results.py` (the benchmark), `score_tree.py` (a tree against its task), `access.py` (the access check), and the OpenCode placement spike.

Paragraph in, tree out, prune, run.
- A paragraph typed into a session (240 characters or more) is asked for a tree before any code: the agent proposes it in the plan's text and stops, and its writes wait until a leaf is accepted. A line is still done at once; "just do it" skips the tree, and a short "no plan" lifts a wait. A new session is taught the text whether or not a plan exists yet.
- The plan as text: `graphene plan --text`; `graphene plan edit [id]` and `graphene node edit <id>` open it in `$EDITOR` and apply what you changed, all or nothing, refusing a line it cannot read by its number; `graphene plan propose -` reads it from an agent (JSON still read) and refuses at once on a terminal with nothing piped; `graphene plan undo`.
- `graphene watch` is a full screen (Textual) with vim keys: the tree, the node under the cursor, the executors as they work (which, where, their last tool call, seconds since), `:` for any command, `?` for the keys. `--once` prints.
- `graphene ask "<what you want>"` and `graphene node split <id>`: a planner with read-only tools, whose printed proposal is added for you to prune.
- A leaf that comes back offers its fix: `graphene node widen <id>`, `graphene node sibling <id>`, or waiting on the nodes its reason names.
- `graphene run`: Ctrl-C (or a closed terminal) hands back what it started and stops the executors and their checks; releasing a running leaf stops its executor; a run that died is swept; a leaf whose need is not here yet waits; each attempt's output is kept as it streams; git is asked before the plan's write lock. The default executor may run `graphene` (its `done` and `release`).
- A check that names a path in neither the repo nor a scope that may still write it is warned about when it is written ("check the spelling"); checks run under bash; every write says which repository it went to.
- New dependency: Textual.

## 0.4.0 (unreleased)

The plan becomes a tree, the terminal its first surface, and ready leaves run at once.
- The root is a sentence of yours (`graphene plan goal`). A node with children is a sub-goal and needs only a title; a node without is a leaf with a scope and a check. `--parent` on `node add` and `node set`; nested `"children"` in `plan propose`. A 0.3 plan is a tree whose nodes all sit under the root.
- Done rolls up: a sub-goal is done when its children are and its own check, if it has one, passes where their work is together. `needs` are inherited downward; cycles through needs, the tree or both are refused.
- A proposal is a subtree: accepting a node accepts what is under it and what it sits under. A leaf too big to do is split by proposing children under it.
- Every executor is told the path from the goal to its leaf (`why:` lines in `node start`, `node show` and the prompt `graphene run` hands over).
- `graphene plan` prints the tree, what waits on you first, with finished work and sub-goals where nothing is moving folded (`--all` unfolds). `graphene watch` redraws it live. `graphene plan record` and `node show <sub-goal>` add up the records of the leaves.
- With a plan in force, a request typed into a session is a leaf by itself (the CLI's `--scope` / `--check` flags typed in the prompt bind it; otherwise it is a record of what the turn changed), and a short plain yes accepts what the session proposed. `graphene plan prompts strict` restores the 0.3 rule.
- `graphene run --parallel N`: a worktree and a branch a leaf, committed by Graphene and merged into your checkout when the merge is clean; otherwise the leaf waits for you in review, on its branch. Plain `graphene run` is unchanged and commits nothing.
- Whoever carries no agent's mark is the person, terminal or not; `graphene run` marks its executors, and the check Graphene runs is never the person.
- The store moves to schema 4 with no table change, so that 0.3 refuses it in words.

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
