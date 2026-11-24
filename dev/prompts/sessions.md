# The sessions run

The prompt of 24 November 2026, as it was sent. The direction it carries out is [../VISION.md](../VISION.md).

```text
You are running the sessions run on Graphene, unattended, for Alex Lopez.

WHY THIS RUN

Graphene (github.com/Alex-lop/Graphene, 0.10.0 on main) gives coding agents a plan, scopes and
checks, and draws the plan as a graph in VS Code and Cursor. After three and a half months
nobody outside uses it. Alex has decided why: the graph is the useful part, and everything in
front of it gets in the way. Today a person needs Python, uv, a CLI, a downloaded .vsix and
`graphene init` in each repository. The extension wakes by itself only in a folder that already
has Graphene's store. Then its hooks stop the agent until a plan is filed, refuse writes outside
a task's files, refuse to start on a checkout with uncommitted changes, and hold the session's
end. Each of those has stopped real work, Alex's and his agents'.

The new default: install the extension, start Claude Code or Codex the way you always do, and a
Graphene page shows that session's work as a graph. Click a card to see that agent's terminal.
When it finishes, each card carries a receipt: what it changed and whether its tests passed.
Nothing in the default path refuses, delays or holds an agent, and nothing needs setting up.

Other tools already draw agent graphs (Agent Flow, github.com/patoles/agent-flow, Apache-2.0,
is the closest; read its README before you design). They draw every tool call, which looks
alive and tells a person little. Graphene draws a handful of cards at the level a person thinks
at, and every mark on the page answers one of four questions: what is it doing, does it need
me, what did it change, did it work. A mark that answers none of them comes off.

Alex judges by real runs, by honest labels, and by how it feels in the hand. Every earlier run
proved its work on a scripted stand-in, and its README had to say so. This run is proven on
real agent sessions, starting with your own.

WORDS

- session: one agent conversation, as Claude Code or Codex records it on disk
- page: one Graphene graph tab in the editor
- card: one piece of work on a page
- receipt: what a card says about the work after it happened
- strict mode: Graphene as it is on main (plan first, scopes, checks, hooks), now opt-in

WHAT TO BUILD, IN THIS ORDER

A piece lands whole, with its check green, or it does not start. All of it is in
editors/vscode unless a piece says otherwise.

1. A source that needs nothing installed.
   - The extension works in any folder, with no `graphene` on PATH and no store. Today
     package.json activates on `workspaceContains:.graphene/graphene.db`, and Home asks for an
     install.
   - It finds the open folder's sessions by itself and follows them as they grow: Claude Code
     first, Codex second, behind one interface.
   - It turns a session into the snapshot the graph already draws (`State` in src/state.ts,
     posted to the webview as {type: "state"}). One graph, two sources: the CLI's
     `graphene state --json` as today, and this. Add optional fields; do not write a second
     renderer.
   - Cards come from what the agent already wrote, with nothing forced. Use the first that the
     session has: its own task list or plan (TodoWrite, TaskCreate and TaskUpdate, ExitPlanMode);
     then the subagents and workflows it launched, one card each, fanning out from the request
     that launched them; otherwise one card per request the person made, titled from their words.
     Tool calls are never cards. They are the activity inside a card.
   - It reads only what is new in a file, skips lines it does not understand, and never takes a
     page down. A file it cannot read says so in one line.
   Done when: unit tests pass on hand-made fixtures (unknown line types, a truncated last line,
   a session with subagents, a Codex rollout), and a real session in a scratch repository draws.

2. Sessions and pages.
   - A session that starts or writes while the editor is open in its folder gets a page: beside
     the file in front, without taking the keyboard, once. Never a page per old session at
     startup. The existing setting `graphene.graph.openOnStart` turns it off.
   - Home lists the folder's sessions, live ones first: title, which agent, what it is doing,
     how long ago. Click one to open or focus its page.
   - "Add to page…" puts a second session on a page that is already open, drawn as its own band
     (layout.ts already has bands). A session can be taken off again. Several pages can be open
     at once, and a page remembers its sessions across a reload.
   - "Needs you" shows only when the file proves it; otherwise "idle".
   - In a folder with no Graphene plan, the side bar shows only what this mode uses. Five views
     and 28 commands is clutter for a person who installed a graph.
   - The empty page says what to do in one line and can replay a bundled recorded session, so a
     person sees a graph before they have one.
   Done when: two real sessions in one scratch folder give two pages, then one page with two
   bands, with a file being typed in beside them that keeps the keyboard throughout.

3. The terminal on click.
   - If the session runs in one of the editor's own terminals, clicking its card reveals that
     terminal (Terminal.processId and the process tree can tell you).
   - Otherwise the card opens a live view of the transcript's tail that reads like a terminal:
     what the agent said, each command, the end of its output. A VS Code pseudoterminal is one
     cheap way. A subagent's card opens the subagent's own transcript.
   - An idle or finished session offers "Resume in terminal": a new editor terminal in the
     session's folder running `claude --resume <session id>` (Codex: `codex resume`). Never
     offer it for a session that is still writing; two writers on one session corrupt it.
   Done when: all three paths are walked on real sessions, with screenshots.

4. Receipts.
   - On each card and for the page as a whole, from the transcript and from git, after the fact:
     the files it changed, each opening its diff; the tests and checks it ran (pytest, unittest,
     npm, pnpm or yarn test, vitest, jest, go test, cargo test, make test, ruff, eslint, tsc,
     mypy), the last run of each deciding; and anything worth a second look: a push or a pull
     request, a delete, a force flag, a hard reset, a test file edited after its test failed, a
     file two sessions wrote, a write outside the folder.
   - Three honest states for tests: passed, failed, ran none. A tick only for a pass that was
     seen. A flag is a fact with the line that shows it, never a verdict, and a guess is
     labelled as a guess.
   - Git knows what tool calls do not. Note HEAD and the dirty files when a session is first
     seen, compare at the end, and say which changes no tool call explains.
   - This is the Scope pane, drawn from what happened. In this mode "May change" becomes what
     changed and "Done when" becomes the tests it ran; "Held by" and "Stopped" belong to strict
     mode only.
   Done when: a real session that edits two files and runs a test shows both files and the pass;
   one that runs no test says so; one that pushes shows the flag. Unit tests cover each flag.

5. The look: PR #67's canvas with PR #68 and #69's readability.
   - Keep from main: the whole plan fitted on open, the zoom with its percentage
     (src/graph/zoom.ts), the type sizes and card proportions, the check at the card's foot with
     a tick when earned (src/graph/marks.ts), the theme tokens (media/tokens.css).
   - Bring back from #67 (merge commit 83302d1a; see editors/vscode/media/graph.png and
     src/graph/main.ts at that commit, and dev/ui/canvas.html, the target): the flow left to
     right with a curved edge from each card's port, a tile on each card for who is working,
     colour on the card for its state, one line of status under the card, motion only where
     work is happening.
   - What went wrong since: cards were packed into a grid with one straight line per group, so
     the graph reads as a board. layout.ts still lays out left to right; find where the grid
     was chosen and make the flow the default, wrapping only when a plan would not fit.
   Done when: before and after pictures of the same fixture and of one real session, at 680 px
   wide (Alex's editor in Cursor, with its chat open) and at full width, in Cursor Dark, Default
   Dark+, a light theme and high contrast.

6. Strict mode, the words, the version.
   - Everything under src/ (the Python engine) and its tests stay as they are. Do not delete or
     refactor them. A folder with a Graphene plan works as it does on main.
   - First commit: this prompt as dev/prompts/sessions.md; dev/VISION.md rewritten to this
     direction in under 80 lines; AGENTS.md pointing at both; dev/SCOPE.md and
     dev/prompts/workflow.md removed (their seven leaves landed in PR #67).
   - README: lead with the no-setup path and a picture of a real session. Strict mode moves to
     one short section. "Know the limits" says what ran on real sessions and what did not, what
     a receipt cannot see, and that the extension reads local session files and sends nothing
     anywhere.
   - Bump the version, so a new build can be told from the 0.10.0 Alex has installed.

DONE MEANS

This walk, on real sessions, with a screenshot at each step in the PR. Use VS Code in a
throwaway profile with only the extension installed, `graphene` not on its PATH, and a new git
repository with no Graphene files:
  1. Start Claude Code in the folder with a small ask that changes two files and runs a test.
     A page opens by itself. The file in front keeps the keyboard.
  2. While it works, the card shows it working. Click the card: its terminal view.
  3. It finishes: the card shows the two files, the test and its result.
  4. Start a second session: a second page. Add it to the first page: two bands.
  5. Reload the window: the pages come back.
  6. Resume the first session from its card.
Then steps 1 to 3 again in Cursor, at 680 px.

WHERE

- Clone https://github.com/Alex-lop/Graphene into a directory of your own. Never work in
  ~/Desktop/AllThingsAgenticHackathon: it is Alex's checkout, with his uncommitted edits and
  Graphene's hooks.
- The folder you start in sits inside a git repository at Alex's home directory. Run git only
  inside your clone, as git -C <your clone>.
- Branch ui/sessions from origin/main. Push after each piece so CI runs. Open one draft PR into
  main after piece 1 and keep it current. Never merge it, never push main, no tags, no
  releases, never pass --admin. Publishing is Alex's (docs/RELEASING.md).
- At the end, build the .vsix (npm run package in editors/vscode), copy it to ~/Downloads, and
  put the one command that installs it in the PR's first lines. Do not install it into Alex's
  own Cursor or VS Code, and do not touch the `graphene` on his PATH (0.9.0).

COMMITS

- As the git identity the clone has (Alex), with no attribution trailers. This is the
  repository's rule, and it overrides your default.
- Between 40 and 50 in all. Alex merges the branch, and every commit lands on main. Each is one
  coherent step that says what it changes and which check shows it works. No "wip" or "fix
  typo" commits: fold those into the step they fix before pushing. Never force-push a pushed
  branch. A subagent's work lands as one squashed commit.

CHECKS

- In editors/vscode: npm run check; node --experimental-strip-types --test "test/*.test.ts";
  npm run build. Do not run npm test: it ends in test/smoke.cjs, which opens a real VS Code
  window on Alex's Mac.
- uv run ruff check and uv run pytest -q -n auto before the PR opens and before the last push.
- After any README edit: uv run pytest tests -k readme -q -n auto. The README is pinned by
  tests; move a pinned test in the same commit as the words it pins.
- Before pushing, in editors/vscode/e2e: PYTHON=<venv python> node --test unit.test.mjs. CI's
  vscode-e2e runs it first, and it pins a per-version table (e2e/measure/moves.py) that moves
  with the version.
- CI runs on pull requests only. The three ubuntu test legs and vscode-e2e are green at the
  end, then gh pr ready. If one is red, leave the PR a draft and say why in its first line.

WHAT I CHECKED ON ALEX'S MAC ON 24 NOVEMBER (check again; these formats are undocumented and
change between versions)

- Claude Code writes ~/.claude/projects/<folder path with its separators as dashes>/<session
  id>.jsonl, one JSON object a line. Match a session to a folder by the `cwd` inside its lines,
  not by the directory's name.
- Each line has a `type`. `user` and `assistant` lines carry `sessionId`, `cwd`, `gitBranch`,
  `timestamp`, `isSidechain`, `version` and `message.content[]`. An `ai-title` line holds a
  title for the session. About fifteen other types exist; skip them.
- A `tool_use` block has `id`, `name`, `input`. Its `tool_result` block comes in a later `user`
  line with `tool_use_id` and `is_error`; that line's `toolUseResult` has `stdout`, `stderr`
  and `interrupted` for a command.
- Subagents are in <session id>/subagents/agent-<id>.jsonl beside the session file, and their
  lines carry `agentId`.
- Codex writes ~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl. The first line is
  `session_meta`, whose payload has `cwd`, `id` and `git`.
- `claude --resume <session id>` and `codex resume` exist.
- Agents do not always write a plan: of the 15 newest sessions in Alex's checkout, 1 used the
  built-in task list (there, Graphene's hooks took the plan instead). The last rung of piece
  1's ladder will be the common case, so make it good.
- The extension is a thin client: src/session.ts and src/stream.ts run the CLI, src/graph.ts
  posts the snapshot, src/graph/main.ts draws it. media/preview.html?fixture=<name>&theme=<name>
  draws a fixture in a plain browser, which is the fast loop for pictures.
- e2e/lib.mjs runs a real VS Code or Cursor in a throwaway profile (findApp, makeProfile,
  installVsix). Neither `code` nor `cursor` is on PATH; Cursor's is
  /Applications/Cursor.app/Contents/Resources/app/bin/cursor.

REAL SESSIONS, AND ALEX'S PRIVACY

- Alex's Mac has hundreds of real sessions under ~/.claude/projects and ~/.codex/sessions. Read
  them to learn the format and to test your reader against, your own session included. They
  hold his prompts and his code. Never copy one into the repository, the PR, a screenshot or a
  subagent's prompt. Committed fixtures are written by hand or recorded from your own scratch
  sessions, with paths and names made generic.
- Start real sessions freely in scratch repositories (`claude -p`, small asks, a small model).
  They run on Alex's subscription. No API-key spend and no Nebius.

TRAPS THAT HAVE COST EARLIER RUNS HOURS

- In Cursor, a tab that opens over a file being typed in takes the keyboard (measured on
  23 November). Test that yours does not.
- lib.mjs's close() deletes ~/.cursor/projects/<folder>. Point the harness only at scratch
  folders. Its windows open on Alex's screen: never click on his desktop, and never kill a
  process you did not start.
- Cursor Dark's focus border is almost invisible and its widget shadow is a white haze, so
  every colour goes through media/tokens.css.
- A new element that reuses a CSS class has broken e2e selectors. Search e2e/ before renaming.
- A note that says a file is dead can be wrong. Run the packaging tests before deleting.
- Anything that follows the README as a stranger runs `uv tool install`. Set UV_TOOL_DIR,
  UV_TOOL_BIN_DIR and UV_CACHE_DIR to a scratch directory first, or it lands on Alex's PATH.
- macOS has no `timeout`, and zsh hides a failed command behind a pipe: set -o pipefail.

HELP

Build it yourself. Use subagents only where a second pair of eyes buys correctness: a reader
on each piece's diff before its push; two stand-ins at the end who get only the README and an
empty folder and try to reach a page; one skeptic per group of findings, told to disprove them
from the code. About fifteen agents in all. Their clones have no origin: only you push or touch
the PR. Their work lands through you, squashed, as Alex, with no trailers (a subagent may sign
its commits as itself, so rewrite them). If one goes quiet for twenty minutes, read its
transcript and take its work over.

NOT IN THIS RUN

Publishing to the Marketplace or Open VSX. Cursor's own agent (look at what it leaves under
~/.cursor/projects, and say in the debrief whether it is readable). Deleting or changing the
engine. Any new guardrail, hook or setting a person must touch before the graph appears. Do not
look for other work in the repository.

CLOCK

After about eight hours, start no new piece. Finish the one in hand or revert it, then write
the debrief.

DEBRIEF: THE PR DESCRIPTION, FOR ALEX TO READ IN FIVE MINUTES

1. Try it in a minute: the install command, then what to do.
2. Per piece: landed or not, with a screenshot from a real session.
3. The look, before and after, at 680 px.
4. What a receipt cannot see, and what was not verified.
5. At most seven decisions you made that Alex may want to flip, each with your default.
6. What is left before the extension can go on the Marketplace, and what the next run should
   take.
7. How many agents ran, and what the reviews found and fixed.
```
