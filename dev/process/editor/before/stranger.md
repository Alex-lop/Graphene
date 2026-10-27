# A stranger's first hour, before: 0.8.0's extension

One Fable subagent, 00:49 to 01:18 on 27 October, played a developer who had never heard of Graphene. It had
0.8.0's extension page (`editors/vscode/README.md` at `2da29a52`), the released `graphene-0.8.0.vsix` installed in
a VS Code 1.143.1 of its own (no `graphene.path`, Alex's `~/.local/bin` off PATH), the wordkit repository open,
and a Token Factory stand-in in place of a real account. Claude Code, Codex and Gemini were shimmed as not
installed, so nothing could spend. Its hands were the harness's driver (screenshots, palette, clicks, keys) and a
terminal of its own. The goal it was given: "add a --top N option to wordkit's CLI that prints the N most common
words, and count hyphenated words like well-known as one word". All 70 screenshots are in
`~/graphene-film/harness/stranger-before/`; four are here.

## The numbers

- First graph: 11 minutes, step 7 (an empty "no goal yet"). First graph with a plan in it: 18 minutes.
- First steer: 18 minutes (a Tell note). First change to the plan from the graph: a link at 23 minutes, an
  accept at 28.
- Guesses: 9.

## What stood in the way, worst first

- **A missing key is a dead end on screen.** `init` and `auto` say "Token Factory answered 401 ... token is not
  present", and auto "waits for you", but nothing says where the key goes, and the notification has no Set Key
  ([11-init-prompt.png](stranger/11-init-prompt.png), [29-auto-output.png](stranger/29-auto-output.png)).
- **Terminals the extension opens run their command at once**, in a fresh shell, so there is no moment to set
  anything first.
- **The walkthrough's Set Up This Folder button did nothing** when clicked; the palette command worked. The step
  ticks when the command starts, not when `init` is done.
- **The default executor needs Nebius Sandboxes**, and nothing on screen names `--placement local`.
- **With auto on, "Plan and run" is the default**, and the envelope accepted and landed the whole race before
  there was anything to steer.
- **A task that came back cannot be dropped from VS Code**: Drop Step says "No task to choose from", and the pane
  has no Drop.
- **The details pane's buttons sit below a long note** with no scroll ([61-panel-hidden.png](stranger/61-panel-hidden.png)).
- **Link mode stays armed** after the selection changes from the side bar, and Esc works only with focus in the
  graph.
- **Tell gives no acknowledgement**, and the note shows nowhere in the extension.
- The status bar says "Graphene · error" while `init` is still asking; the graph tab is blank for a moment;
  Rounds counted a later ask's accepts into round 1; the walkthrough says `graphene-map[nemotron]` where the page
  says `graphene-map`; the terminal's echo of Auto… shows shell quoting (`wordkit'\''s`); the terminal ran a
  different `graphene` from the one the stranger installed.
- Machine, not product: the stand-in's own key, and a shell profile that put a real key in the stranger's
  shell (see the brief).

## What worked

Once a race ran, the graph was what the page promised: forks fanning out with "✓ kept" and "gave up", red
diamonds on what came back, the "needs you" count, and the pane's contract
([54-run-output.png](stranger/54-run-output.png)). Link… and Accept from the palette and the pane did real
things that `graphene plan log` confirmed.

## Its note to the author

"What stands between a stranger and that moment is the key: every surface tells me Token Factory answered 401
and none tells me where the key goes. After that, the defaults work against steering: Plan and run with auto on
landed a task I did not ask for before I had seen the plan. Make Plan first the path the walkthrough takes, show
the Tell note and the board in the extension, let a came-back task be dropped, keep the pane's buttons reachable,
and make the walkthrough's buttons fire and tick only when init is done."
