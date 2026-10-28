# Graphene for VS Code

Say what you want, read the plan, start the agents, and approve what they did. Graphene runs each agent on one
task, in its own copy of your repository, held to the files that task may change. A task lands only when its
check passes and, if you keep the box ticked at setup, when you approve it.

![Graphene for VS Code during a race against the scripted stand-in, in real VS Code: Home, in the side bar, shows three agents working, each with its model, what it is doing now, its cost and its attempts, and a Stop all button; the editor tab draws the same race, two tasks each fanned out into three Nano attempts, all running, flowing into the goal; the auto line says round 1 of 3, running, $0.007 of $2.00](media/graph.png)

It is a thin client over the `graphene` command. Everything it shows is `graphene state --json`, streamed with
`--watch`, and everything it changes is one `graphene` command, the same ones the terminal cockpit runs.

## Home: everything with a click

Click Graphene in the activity bar. Home is the first view, and it shows the one thing to do next.

1. **Set up the folder.** Pick who plans and does the work: Claude Code, Codex or Nemotron. One click. Leave
   *Ask me to approve each finished task* ticked, and nothing lands without you.
2. **Say what you want.** Type it, in a sentence or a paragraph, and click **Plan it**. The planner reads the
   repository and suggests small tasks. Each card says what the task is for, the files it may change, and the
   check that proves it is done. Remove what you do not want.
3. **Start.** The tasks are accepted and an agent starts on each. **Working now** shows each agent, what it is
   editing and what it has spent; **Stop all** stops them.
4. **Review.** Each finished task shows the files it changed, the check that passed, and the agent's last
   steps. **Open changes** opens VS Code's diff editor; **Approve** lands it; **Send back…** returns it to an
   agent with what is wrong. Approve before you have opened the changes, and Home asks first. When two attempts
   both pass, you compare them and keep one.

A task that needs help says why and offers its fixes as buttons: try again, allow it a file, add a task for what
it needs. A question from the planner shows its options as buttons, the default first.

The **graph** under Home is the whole plan: which tasks wait on which, the attempts racing, the one kept and
why. **Show graph** opens it as a tab. The Explorer marks each file a task owns, a working agent's with its
number.

## Try it with no key

**Graphene: Watch the Demo** plays a recorded run in a graph of its own, with no model and no network, and says
so at the top.

## Install

1. Graphene itself, once, in a terminal (it needs Python 3.12 or later and [uv](https://docs.astral.sh/uv/)):

   ```sh
   uv tool install graphene-map
   ```

   The extension offers to run this for you when it cannot find `graphene`. It looks on the PATH, in
   `~/.local/bin` and in uv's tool directory first.

2. This extension, from the `.vsix` on [the latest release](https://github.com/Alex-lop/Graphene/releases/latest),
   or from the Marketplace (VS Code) and Open VSX (Cursor) once it is published there:

   ```sh
   code --install-extension graphene-0.9.0.vsix      # Cursor: cursor --install-extension graphene-0.9.0.vsix
   ```

3. Open a folder and click Graphene in the activity bar. Home sets it up.

The Welcome page's **Get started with Graphene** walks through these, each step a button.

## The words on screen

| On screen | What it means | The CLI's word |
| --- | --- | --- |
| suggested | the planner proposed it; nothing runs until you start it | proposed |
| working | an agent is on it now | running |
| to review | its check passed; it waits for your approval | review |
| needs help | it stopped before its check passed, and says why | came back |
| attempt | one of several agents racing the same task; its check keeps one | fork |
| approve | land it in your repository | sign off |
| send back | open it again, with a note for the next agent | reopen |

## Commands

Seven in the command palette, all under `Graphene:`: **Home**, **Show Graph**, **Watch the Demo**, **Stop All
Agents**, **Set Up This Folder**, **Install Graphene…** and **Set API Key…**. Everything else is a button on Home,
in the graph's details pane, or in a diff's title (**Keep This Attempt**, **Approve**).

Set `graphene.advanced` to see every command in the palette (auto mode, limits, edit the plan as text, add a task
by hand, the cockpit in a terminal) and the Needs You, Agents, Plan and Rounds views.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `graphene.path` | `graphene` | the command: a name on PATH or an absolute path. Read from your own settings only, never a folder's |
| `graphene.pollMs` | `1500` | how often the plan is read again while a view is open, when the CLI has no `--watch` stream |
| `graphene.advanced` | off | every command in the palette, and the Needs You, Agents, Plan and Rounds views |

## Editors

VS Code 1.95 or later. In Cursor 3.25.6 (VS Code 1.128) the `.vsix` installs and activates, and the harness's
end-to-end check passes there (`editors/vscode/e2e`). Cursor's agent layout hides the primary side bar; in its
classic layout the views look as they do in VS Code.

## Trust and privacy

- **A thin client.** The extension reads the plan with `graphene state --json` and changes it with `graphene`
  commands, run as you in the folder. It never opens the plan's store itself.
- **Nothing from a page reaches a shell.** Home and the graph send the extension a message; it checks each one
  against the plan (a known act, a task the plan has, an option the question has) and passes words only as one
  argument of a `graphene` command. A title or a planner's words are shown as text, never as markup or a link.
- **No network of its own.** The extension makes no request and sends no telemetry. The models you configured
  (Token Factory, Claude Code, Codex) are the CLI's business, with a key it reads from a hidden prompt.
- **Off in Restricted Mode.** In a folder you have not trusted it does nothing: it would run commands, and the
  plan's checks, there.
- **Your settings only.** `graphene.path` comes from your user settings, never from a folder's
  `.vscode/settings.json`, so a cloned repository cannot choose what the extension runs.
- **A click in VS Code is the person's.** An editor started from an agent's shell inherits the agent's marks
  (`CLAUDECODE`, `CODEX_SESSION_ID`, …); the extension takes them out of everything it runs, so your approval
  is a person's.
- **The demo stays out of your folder.** Watch the Demo plays into a directory under the OS temp dir, and
  closing its graph removes it.

## Limits

- It needs Graphene 0.9 or later; with an older CLI each view says what the CLI said, and the plan is polled
  instead of streamed.
- One plan per window: the first workspace folder with a store.
- Nobody has used it on a real run yet. It was built and checked against a fixture and a scripted stand-in.

Source, issues and the CLI: [github.com/Alex-lop/Graphene](https://github.com/Alex-lop/Graphene). Licence
Apache-2.0.
