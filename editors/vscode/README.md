# Graphene for VS Code

Your coding agent proposes a plan before it writes, and Graphene draws it as a graph in an editor tab. Read it,
change it, start it, and approve what the agents did. Each task runs in its own copy of your repository, held to the
files it may change, and lands only when its check passes and, if you keep approval on, when you approve it.

![Graphene's graph in an editor tab. Across the top: Plan, Run and Review. On the graph: a plan's task cards flowing left to right into the goal, each with who does it, its files and its check. Beside them, the selected task's Scope pane: the files it may change, what it may run, how a write outside them is held, the writes that were stopped, and its check](media/graph.png)

## Install

1. Graphene itself, once, in a terminal (Python 3.12 or later and [uv](https://docs.astral.sh/uv/)). The extension
   offers to run this when it finds no `graphene` on the PATH, in `~/.local/bin` or in uv's tool directory.

   ```sh
   uv tool install graphene-map
   ```

2. This extension, from the `.vsix` on [the latest release](https://github.com/Alex-lop/Graphene/releases/latest)
   (not on the Marketplace or Open VSX), or built with Node 22+: `npm ci && npm run package` in `editors/vscode`.

   ```sh
   code --install-extension graphene-0.10.0.vsix      # Cursor: cursor --install-extension graphene-0.10.0.vsix
   ```

## The first five minutes

1. **Click Graphene in the activity bar.** The graph opens full size in an editor tab. **Home**, in the side bar,
   sets up a new folder in one click (Claude Code or Codex); leave approval ticked and nothing lands without you.
2. **Ask Claude Code or Codex, in its own chat** (Cursor's own Agent does not plan with Graphene yet). Graphene's hooks have it propose its plan (`graphene plan propose`) before
   it writes. Each task is a card: who does it, the files it may change and, at its foot, the check that proves it.
3. **Read and change the plan.** Click a card: its pane opens on **Scope**, and **Edit** changes its files, check,
   attempts and approval. Answer the plan's questions; **Add task** draws a task; a card's dot links it to another.
4. **Start.** An agent takes each ready task. Home's **Working now** shows what each is editing and what it has
   spent; **Stop all** stops them. A task that needs help says why and offers its fixes as buttons.
5. **Review.** Each finished task shows what it changed and the check that passed. **Open changes** opens the diff;
   **Approve** lands it; **Send back…** returns it with a note. When two attempts pass, you compare and keep one.

**Stop after the plan**, on Home and the graph's header, is on by default: the plan waits for **Start**. Off, a plan
runs as soon as it appears, within your limits; a question with no default still stops it. The tab opens by itself
when work starts, beside your file and without taking the focus; close it and it stays closed until **Open the Graph**.

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
| asks you | a command that would push or open a pull request waits for your approval | yours |
| attempt | one of several agents racing the same task; its check keeps one | fork |
| approve | land it in your repository | sign off |
| send back | open it again, with a note for the next agent | reopen |

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
- It needs Graphene 0.9 or later, and shows one plan per window: the first workspace folder with a store.
- Nobody has used it on a real run yet: it was checked against a fixture and a scripted stand-in.

Source, issues and the CLI: [github.com/Alex-lop/Graphene](https://github.com/Alex-lop/Graphene). Licence Apache-2.0.
