# Graphene for VS Code

**See what your coding agents are doing, and what they did. Nothing to set up.**

Start Claude Code or Codex as you always do. A page opens beside your file and draws that session as a graph: a
card for each request, each task on the agent's own list and each subagent. Click a card to see that agent's
terminal. When it finishes, each card carries a receipt: the files it changed and whether its tests passed. Nothing
refuses, delays or holds your agent.

![Graphene in VS Code. In the side bar, Home lists the folder's session. In the editor, the session's page: four cards joined by curved lines, left to right. The request, done, with the files it changed and a ticked "unittest passed" at its foot; the two subagents it started, each "ran no tests"; and a follow-up request, done, with its own ticked test. Under each card, one line of what it said last](media/session.png)

*A real Claude Code session in a scratch repository, as its page drew it.*

## Install

From [the release](https://github.com/Alex-lop/Graphene/releases/latest), 0.11.0 (it is not on the Marketplace or
Open VSX yet):

```sh
curl -LO https://github.com/Alex-lop/Graphene/releases/download/v0.11.0/graphene-0.11.0.vsix
code --install-extension graphene-0.11.0.vsix
```

In Cursor: `cursor --install-extension graphene-0.11.0.vsix`. No `code` or `cursor` on your PATH? Extensions → ⋯ →
**Install from VSIX…**. From a clone instead: `npm ci && npm run package` in `editors/vscode` (Node 22+). Nothing
else to install.

## The first minute

1. **Start Claude Code or Codex in the folder**, in a terminal or in its own panel (`claude`, or `claude -p "…"`
   for one ask; any folder, git or not). A few seconds after the session's first line a page opens in the editor
   area, beside your file if one is open, once for each session in a window, and the file keeps the keyboard. Until
   then the ◆ in the status bar says how many sessions it sees. A session that was there before the window opened
   gets no page until it writes again; **Home**, in the side bar, lists them all, live ones first.
2. **Read the cards.** One for each request you made; under a request, the tasks on the agent's own list or the
   subagents it started. A card at work says **working** and its last move; **needs you** only when the session's
   file shows it waiting for your answer; otherwise **idle**, **done**, **interrupted** or **failed**.
3. **Click a card.** The terminal it runs in comes forward. A session running outside the editor, and a subagent,
   open as a view of what they write. **Resume in terminal** picks up one that is idle or finished, with the
   agent's own command (`claude --resume`, `codex resume`), and never one that is still writing.
4. **Read the receipt.** At a card's foot, the tests it ran: **passed** (ticked, only for a pass that was seen),
   **failed**, **ran no tests**, or **ran, result not seen**. In its pane: each file it changed, opening its diff;
   each test and check with what decided it; what is worth a second look (a push or pull request, a delete, a
   forced git command, a hard reset, a test edited after it failed, a file two sessions wrote, a write outside the
   folder), each with the line that shows it; and what git says changed with no tool call of the session's.
5. **Put sessions together.** **Add to page…** puts another session on this page as a band; the × on a band takes
   it off again. Pages come back when the window reloads.

No session yet? The empty page replays a recorded one. `graphene.graph.openOnStart`, off, keeps pages from opening
by themselves.

## Strict mode

Graphene as it was through 0.10, now opt-in, a folder at a time: your agent proposes a plan before it writes (Cursor's
own Agent does not plan with Graphene yet), and Graphene draws it as a graph. Read it, change it, start it, and
approve what the agents did. Each task runs in its own copy of your repository, held to the files it may change, and
lands only when its check passes and, if you keep approval on, when you approve it.

![Graphene's graph in an editor tab. Across the top: the goal, then Plan, Run and Review. On the graph: four task cards under one sub-goal, three done and one working with its three attempts, each card with its files and, at its foot, its check, all leading into the goal. Beside them, the selected task's Scope pane: the files it may change, its check failing before the work and passing after it, what it may run, how a write outside its files is held, and the write it was stopped from making](media/graph.png)

*The graph, replaying the bundled demo: a scripted stand-in, no model ran.*

It needs the CLI from PyPI (Python 3.12+ and [uv](https://docs.astral.sh/uv/)): `uv tool install graphene-map`
(installed already: `uv tool upgrade graphene-map`), or `uv tool install .` from a clone. Then **Home → Strict
mode…**, or **Graphene: Set Up This Folder** in the palette. A folder that already has a Graphene plan opens in strict
mode as it always did.

### The first five minutes

1. **Click Graphene in the activity bar.** The graph opens full size in an editor tab. **Home**, in the side bar,
   sets the folder up in one click (**Strict mode…**, then Claude Code or Codex); leave approval on and nothing
   lands without you.
2. **Ask Claude Code or Codex, in its own chat.** Graphene's hooks have it propose its plan (`graphene plan
   propose`) before it writes. Each task is a card: the files it may
   change and, at its foot, the check that proves it.
3. **Read and change the plan.** Click a card: its pane opens on **Scope**, and **Edit** changes its files, check,
   attempts and approval. Answer the plan's questions; **Add task** draws a task; a card's dot links it to another.
4. **Start.** An agent takes each ready task. Home's **Working now** shows what each is editing and what it has
   spent; **Stop all** stops them. A task that needs help says why and offers its fixes as buttons.
5. **Review.** Each finished task shows what it changed and the check that passed. **Open changes** opens the diff;
   **Approve** lands it; **Send back…** returns it with a note. When two attempts pass, you compare and keep one.

**Stop after the plan**, under Home's Settings, is on by default: the plan waits for **Start**. Off, a plan runs as
soon as it appears, within your limits; a question with no default still stops it. The tab opens by itself when work
starts, without taking the keyboard: beside your file in VS Code, over it in Cursor, whose agent chat already narrows
the editor. Close it and it stays closed until **Open the Graph**.

**Save as workflow** writes the plan to `workflows/<name>.md`, with the values you name as inputs; Home lists them,
and **Run** proposes the plan again with no planner call. A `run:` line is a command with no agent; one that pushes
or opens a pull request (`git push`, `gh pr`) waits past the **leaves your machine** line for **Approve and run**.

**Graphene: Watch the Demo** plays a recorded run in a graph of its own: no key, no model, no network.

### The words on screen

| On screen | What it means | The CLI's word |
| --- | --- | --- |
| task | one piece of the plan, a card on the graph: the files it may change and the check that proves it | leaf |
| suggested | proposed by your agent or the planner; nothing runs until you start it | proposed |
| working | an agent is on it now | running |
| to review | its check passed; it waits for your approval | review |
| needs help | it stopped before its check passed, and says why | came back |
| asks you | it waits on you: a question to answer, or a command that leaves your machine | yours, or needs_you |
| yours | a task you do yourself (**I will do this one**); **Mark done** finishes it | yours |
| attempt | one of several agents on the same task at once (`3 agents at once` on its card); one that passes is kept | fork |
| approve | land it in your repository | sign off |
| send back | open it again, with a note for the next agent | reopen |
| on its own | **Stop after the plan** is off: it plans, runs and fixes the goal in rounds, within your limits | auto |

## Commands and settings

Three commands in the palette, under `Graphene:`: **Home**, **Open the Graph** and **Set Up This Folder** (the way
into strict mode). In strict mode four more: **Watch the Demo**, **Stop All Agents**, **Install Graphene…** and
**Set API Key…**. Everything else is a button on Home, on the
graph, or in a diff's title (**Keep This Attempt**, **Approve**).

| Setting | Default | What it does |
| --- | --- | --- |
| `graphene.path` | `graphene` | the command: a name on PATH or an absolute path, from your own settings only |
| `graphene.pollMs` | `1500` | how often the plan is read again when the CLI has no `--watch` stream |
| `graphene.advanced` | off | every command in the palette, and the Needs You, Agents, Plan and Rounds views |
| `graphene.graph.openOnStart` | on | a page opens by itself when a session begins (in strict mode, when work starts), beside your file and without the keyboard; off, only **Open the Graph** opens it |

## Trust and privacy

- **It reads, and sends nothing.** With no plan in the folder it reads the session files Claude Code and Codex
  write on your machine (`~/.claude/projects`, `~/.codex/sessions`; `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are
  honoured) and Claude Code's records of its running processes (`~/.claude/sessions`), lists running processes
  (`ps`) to find the terminal a session runs in, and runs read-only `git` for the session's folder, with git's
  optional locks off so an agent's own `git add` is never refused for it. It runs no `graphene` command and no
  `uv`, writes nothing into your folder, and types into a terminal only the resume command you clicked.
- **A thin client in strict mode.** Everything it shows there is `graphene state --json`, streamed with `--watch`, and everything it
  changes is one `graphene` command, run as you in the folder: the same ones the terminal cockpit runs.
- **Off in Restricted Mode.** In a folder you have not trusted it does nothing: it would run commands there.
- **Your settings only.** `graphene.path` is never read from a folder's settings: a cloned repository cannot
  choose what the extension runs.
- **A page's words reach a shell only as one quoted argument**, once the extension has checked the message
  against the plan. **Start**, **Run** and **Approve and run** type a `graphene` line into a terminal you can stop.
- **A click in VS Code is the person's.** An editor started from an agent's shell inherits its marks (`CLAUDECODE`,
  `CODEX_SESSION_ID`, …); the extension takes them out of everything it runs, so your approval is a person's.
- **No network of its own.** No request, no telemetry. The demo plays in a directory under the OS temp dir.

## Limits

- VS Code 1.95 or later, or Cursor 3.25.6 or later (its agent layout hides the side bar: Home needs the classic
  layout).
- Sessions were walked on real Claude Code sessions started in a terminal, on macOS, in VS Code and in Cursor.
  Codex sessions are read from their files and were not walked in an editor; Cursor's own agent is not read;
  Windows and Linux are untested.
- Only the first workspace folder's sessions are drawn. A Codex command that runs for more than two minutes reads
  as idle until it writes again (Codex keeps no record of its process to ask); a Claude Code session whose process
  is killed reads as idle once that is seen.
- A receipt reads the session's file and git, nothing else: a file a shell command changed shows only as changed
  with no tool call, a test whose output never reached the session is **ran, result not seen**, and a session
  waiting on a permission prompt does not say **needs you** (the prompt is not in its file).
- Strict mode needs Graphene 0.10.0's CLI (with 0.9.0's every task's pane says **Not held** and no check's box is
  ticked), and shows one plan per window: the first workspace folder with a store. Nobody has used it on a real
  run yet: it was checked against a fixture and a scripted stand-in.

Source, issues and the CLI: [github.com/Alex-lop/Graphene](https://github.com/Alex-lop/Graphene). Licence Apache-2.0.
