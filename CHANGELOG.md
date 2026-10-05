# Changelog

## 0.5.0 (not published yet: the tag is Alex's)

`plan first` has a third value, `auto`, now the default, and a store's `on` becomes it: one leaf of work is
done at once, more is proposed as a tree. `on` now proposes every ask. Run `graphene plan first`.

Graphene on Nemotron. As practice on 2 October, Nemotron planned a small feature 5 times. 2 plans ran to the
end in Token Factory Sandboxes, landing 5 of 6 leaves, each passed by its own check; neither did all it was
asked. 3 stopped at the planner, whose tree was readable on 2 of 9 asks (`docs/test/first-light.md`). Nothing
registered has run live.

- `graphene run` now isolates every leaf in a worktree. `--here` is the old behaviour.
- A Claude Code executor can write in its run's worktree. The hook had refused every write there as the plan's store.
- The old briefs, notes and spikes left `main` for the orphan branch `process`.
  `git show origin/process:README.md` says what is there.
- The web UI is gone. `git revert` of the deletion commit brings it back.
- Nemotron is an optional extra: `uv tool install 'graphene-map[nemotron] @ git+…'`. Without it, no Token
  Factory code loads.

The live half of first light (2 October, practice).
- The sandbox's list of files takes the exit code through `$(...)`, and a command's output is appended, never
  truncated. On ConTree a `cat` into a file opened with `>` leaves it unwritable: no command's list came back,
  every sandbox command read as exit 1, and a command's output was cut at its first `cat`. A leaf's placement
  record counts the commands whose list was lost, and the ladder's rungs 3 and 7 fail on any.
- `graphene plan note` takes JSON's null written as the string `"null"` in a glob list as no glob, as Nano
  wrote it live.
- contree-sdk's "Token expires in 0 hours" no longer reaches the screen (it is a 300-second token, not the
  key).
- Live recordings in `tests/recordings/`: rung 5's leaf and rung 7's first take, replayed in CI with no key.
- Tests that count Token Factory's retry waits patch only its own wait, not the global `time.sleep` (CI's
  flake in test_precheck and test_cover).
- `graphene key check` says Sandboxes' state; a spend cap that is not a number refuses every call; the
  registered runs' $10 cap (carried from 29 September).

First light (29 September).
- `graphene direction`: a small tree of goals above the plans, one line a node, in `.graphene/direction.txt`,
  which git tracks while the rest of `.graphene/` stays ignored. An agent proposes nodes (`direction propose
  -`); only the person accepts or drops them, hangs the plan from one (`direction plan NODE`), attaches a
  session to one (`direction attach SESSION NODE`) or edits the file (`direction edit`). `D` in `graphene
  watch` shows the direction under the tree, read again every tick, and opens no command line. `graphene direction` prints each node with what waits on you, what runs and what is next, read from
  the rows the hooks already write; `graphene plan`, its views and `graphene watch` show the path
  to the plan's node above the plan. A file with a line Graphene cannot read is not used, and the refusal
  names the lines.
- The hook refuses an agent's Edit, Write, MultiEdit and NotebookEdit under `.graphene/`, plan or no plan.
- The board shows only while a question on it is open: `board: auto` (unset) in `graphene config`, by study 4
  (`docs/test/results-2026-09-29-board.md`); `board: on` shows every open item. Accepting the whole plan, an
  `R` that starts something, or `graphene board take` with no id takes every open default and an agent's
  note, in one line that `graphene plan undo` takes back; a default that drops a node waits for its own key,
  and the line names it. `graphene board` prints what answering needs, and `--all` the rest.
- `graphene board lookup` (one Nano call; `GRAPHENE_SHAPE=lookup` runs it after each ask) settles a question
  a file already answers when the line it quotes is in that file, marked `from the repo: FILE:LINE`; `unpark`
  gives it back. It never sends a protected file.
- Spending is the person's. Without `GRAPHENE_AGENT_LIVE_USD`, a process that carries an agent's mark is
  refused a Token Factory call to the real host and any ConTree sandbox before anything is sent. With it,
  every live call goes on one night's ledger that every process shares, locked with `flock`
  (`~/.graphene/night/`): a call reserves its worst case first and is refused unsent past the cap, the lower
  of that figure and $10, and nothing new starts past 80% of it. Its rows say `practice`, and
  `docs/test/evidence.py` refuses them.
- Sandboxes: a project ConTree refuses (403) is one refusal saying what the key lacks and where access is
  asked for, wherever a sandbox is used. `graphene init` asks ConTree's whoami before it places Nemotron's
  leaves in Sandboxes, and places them on this machine with one line saying why when it is refused. An
  operation past its time comes back as the command's exit 124, as Docker's does. The live model list's
  mixed-case Nemotron ids resolve to their roles.
- A recording dropped into `tests/recordings/` replays in CI and is counted for the key, the project, a home
  path and key-shaped words.
- A closed terminal ends `graphene watch`, `graphene demo`, and a run with its executors and their checks,
  whether or not it sends the hangup.
- `graphene demo` holds each change on the screen, pauses on space, steps on `.`, plays again on `r`, and
  names a stand-in on every row it made. The shipped recording was made again on the scripted fake with a
  board: a question, an assumption and a leave-out, each taken with one key. Its status line keeps one form
  and its bill, and offers neither `R` nor `P`.
- The hook imports, queries and starts only what its event needs: recording a call takes about half the
  CPU it did (69 to 32 ms on the author's machine with other work running). Its 60 ms budget is held on CPU time, so a loaded machine no
  longer fails it.
- `graphene key set`, `check` and `remove` refuse Claude Code and Codex. No test reaches the real keychain
  (`tests/keyguard.py`, here and in CI).
- `docs/test/practice.sh night` prints the night's bill, and `practice.sh prototypes` practises cover, note
  and precheck under a $0.05 cap. `docs/demo/build.sh` films the demo run scene by scene and assembles
  `rough.mp4` only from a run recorded as live.
- With no planner or executor chosen, `graphene ask`, `node split`, `talk` and `run` refuse in one line and
  start nothing until `graphene init` or `--with` names one; they no longer start `claude` from the PATH.
- A leaf that came back waits on the person: `R` and a plain `graphene run` leave it and say that
  `graphene run --node ID` (`r` on the screen) runs it again. A leaf a run let go is ready again.
- A came-back leaf is never offered a path another live leaf's scope has; it is offered to wait on that
  leaf instead, and the pane says which paths were not offered and why.
- Asking again finer or coarser (`+`, `-`) carries a board answer to the leaf the planner wrote again, and
  says, with the command, any answer it cannot place.
- `graphene plan undo` of a board answer logs `undone`. `graphene config` names a board answer's read-only
  globs `# answered: readonly …`, not a second `board:` key, and `graphene board` wraps to the terminal.
- Bare `graphene` names a proposal and an open board as what waits on the person, and `graphene run` on a tree
  nobody accepted says to accept it.
- No test gets the repository git was pointed at: a suite started from `git bisect run`, a hook or `rebase
  --exec` hands no `GIT_DIR` or its kin to its tests.
- `docs/test/bench.py` counts a leaf its round's timeout stopped as failed and runs it no more, now that a
  leaf a run stopped reads ready.
- Smaller: `:ask` keeps a paragraph's apostrophes; a planner or executor run by an interpreter is named by
  its script; a leaf's record reads its check before its finish.

Shaping (28 September): the board (`graphene board`: the planner's questions and risks, answered only by
the person, with `then:` lines that change the tree), the outline, tree and graph views (`Tab`, `--view`),
talking on a node (`?`: `graphene talk`), what changed since you looked (`graphene plan changes`, `seen`),
the settings you state once (`graphene config edit`: `protected`, `readonly`, `never`, `size`), the key in
the system keychain (`graphene key`), the practice ladder (`docs/test/practice.sh`), and three Nano
prototypes (`graphene plan cover`, `note`, `precheck`), each run only against the stand-ins.

- `graphene demo` replays a recorded run in `graphene watch`, with no key, no Docker and no network, and
  runs nothing: every key that would change the plan or start a process says so. `graphene demo --once`
  prints its last frame. `graphene demo --record FILE` records a run's store (not the model's calls),
  taking out paths, keys and sandbox ids. The wheel ships a recording, and it says on screen that it is a
  scripted stand-in until the live run replaces it. Needs git.
- `graphene init` lists what it finds here (`claude` or `codex` on the PATH, a Token Factory key), each
  with what it needs, and none comes first: Enter takes a choice only when exactly one is found. Without a
  terminal, an unset choice gets the one thing found, or stays unset and says why.
- Forks and the model ladder are visible. Each fork is a row under its leaf in `graphene watch` (its
  model, which fork, its state), a step up to a larger model is named on the bottom line and in the leaf's
  pane, the pane shows the leaf's sandbox (its checkpoint, operations and seconds) and its bill, the record
  says which fork won and why each other one did not.
- The Nemotron path survives what the judging period can throw at it: a model id the live list no longer
  has falls back within the Nemotron family and says which instead of which; a 429 storm, 5xx errors, a
  timeout, a reply cut off, a malformed or text-only tool call, a sandbox killed or gone mid-leaf and a
  check that hangs each bring the leaf back with its cause and what to do, the run goes on, and nothing is
  left running; no more than fifty sandbox operations run at once from one machine.
- The first fork whose check passes is the one that lands, decided under a lock.
- Forks read what git shows in the leaf's checkout (they were blind: a fork's copy has no `.git`), and a
  winning fork never deletes or copies what git ignores (it used to delete a `.env` under a `**` scope).
  A stopped run stops its forks and the model's commands, writes each fork's row as stopped, and bills
  what they spent. A usage row says whether Token Factory or a stand-in answered, and the bill credits
  Token Factory only when every row says so.
- A record read where git has not got a hold's starting commit says its commits cannot be read.
- The README says what Graphene on Nemotron claims, directly under the opening, offers two paths (the agent
  you have, or Nemotron through Token Factory), and gives judges ten lines to test it.

- The import package is `graphene_map`, matching the distribution (it was `graphene_debrief`). The command is still `graphene`, and installed hooks keep working. Anything that imported `graphene_debrief` imports `graphene_map`.
- NVIDIA Nemotron on Nebius Token Factory, as planner and executor: `graphene ask --with nemotron` (Ultra, read-only tools) and `graphene run --with nemotron` (Nano, then Super on a refused attempt; `--forks N`; `--placement local|sandbox`). Model ids come from the live model list, and every call's usage is priced at its list price. Needs `NEBIUS_API_KEY`.
- Token Factory Sandboxes: `pip install 'graphene-map[sandbox]'` (contree-sdk 0.3.6). A leaf's commands run as a user who can write only its scope, what a command makes outside it never comes back, and its check runs in a fork of the sandbox.
- `graphene init` asks once which planner and executor a repository uses (as above: what it finds, none first); `run`, `ask`, `node split` and the screen use it, and `--with` overrides one command.
- A check runs in a clean worktree of the leaf's state: nothing it writes lands in the executor's tree. No check gets the Token Factory key.
- `graphene watch` folds: done subtrees fold, a folded row counts its leaves by state, a tall tree opens as its outline; `za zo zc zR zM zx`.
- The bill: what the Nemotron planner and executors cost, at list price, in `graphene node show`, `graphene plan record`, the run's last line and the screen's status line.
- Python 3.14 in CI; the store binds values to plain `?` only.
- Graphene reads no Claude Code transcript; `graphene ingest --backfill` is removed (`graphene ingest hook` is unchanged). Internal: `graphene_map.attribute` is `graphene_map.shell`, `graphene_map.sources.claude_code` is `graphene_map.hooks`, `repo_root` lives in `graphene_map.store`. The screen harness is `docs/screens/`.
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
