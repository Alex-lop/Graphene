# Graphene for VS Code

**One plan for your coding agents. Clear boundaries. Tested commits.**

Your coding agent proposes a plan before it writes, and Graphene draws it as a graph in an editor tab. Read it,
change it, start it, and approve what the agents did. Each task runs in its own copy of your repository, held to the
files it may change, and lands only when its check passes and, if you keep approval on, when you approve it.

![Graphene's graph in an editor tab. Across the top: the goal, then Plan, Run and Review. On the graph: four task cards under one sub-goal, three done and one working with its three attempts, each card with its files and, at its foot, its check, all leading into the goal. Beside them, the selected task's Scope pane: the files it may change, its check failing before the work and passing after it, what it may run, how a write outside its files is held, and the write it was stopped from making](media/graph.png)

*The graph, replaying the bundled demo: a scripted stand-in, no model ran.*

## Install

The extension and the CLI go together, 0.10.0 each: with 0.9.0's CLI every task's pane says **Not held** and no
check's box is ticked. Until PyPI and [the latest release](https://github.com/Alex-lop/Graphene/releases/latest)
have 0.10.0, build both from the repository (Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node 22+; the
extension is not on the Marketplace or Open VSX):

```sh
git clone https://github.com/Alex-lop/Graphene && cd Graphene
uv tool install .                                  # released: uv tool install graphene-map
cd editors/vscode && npm ci && npm run package     # released: the .vsix on the latest release
code --install-extension graphene-0.10.0.vsix      # Cursor: cursor --install-extension graphene-0.10.0.vsix
```

## The first five minutes

1. **Click Graphene in the activity bar.** The graph opens full size in an editor tab. **Home**, in the side bar,
   sets up a new folder in one click (Claude Code or Codex); leave approval ticked and nothing lands without you.
2. **Ask Claude Code or Codex, in its own chat** (Cursor's own Agent does not plan with Graphene yet). Graphene's
   hooks have it propose its plan (`graphene plan propose`) before it writes. Each task is a card: the files it may
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

## The words on screen

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

Seven commands in the palette, under `Graphene:`: **Home**, **Open the Graph**, **Watch the Demo**, **Stop All Agents**,
**Set Up This Folder**, **Install Graphene…** and **Set API Key…**. Everything else is a button on Home, on the
graph, or in a diff's title (**Keep This Attempt**, **Approve**).

| Setting | Default | What it does |
| --- | --- | --- |
| `graphene.path` | `graphene` | the command: a name on PATH or an absolute path, from your own settings only |
| `graphene.pollMs` | `1500` | how often the plan is read again when the CLI has no `--watch` stream |
| `graphene.advanced` | off | every command in the palette, and the Needs You, Agents, Plan and Rounds views |
| `graphene.graph.openOnStart` | on | the graph opens as a tab by itself when work starts; off, only **Open the Graph** opens it |

## Trust and privacy

- **A thin client.** Everything it shows is `graphene state --json`, streamed with `--watch`, and everything it
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

- VS Code 1.95 or later, or Cursor 3.25.6 (its agent layout hides the side bar: Home needs the classic layout).
- It needs Graphene 0.10.0's CLI (with 0.9.0's every task's pane says **Not held** and no check's box is ticked),
  and shows one plan per window: the first workspace folder with a store.
- Nobody has used it on a real run yet: it was checked against a fixture and a scripted stand-in.

Source, issues and the CLI: [github.com/Alex-lop/Graphene](https://github.com/Alex-lop/Graphene). Licence Apache-2.0.
