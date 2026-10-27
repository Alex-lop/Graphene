# A stranger's first hour, after: the night's extension

A second Fable subagent, 04:45 to 05:08 on 27 October, played the same developer as `../before/stranger.md`, on
the night's `.vsix` (built at `97a708a5`) with the night's listing page. Its CLI was to be the night's wheel
(PyPI was out of its reach; the wheel was named `graphene_map-0.8.0` because the 0.9.0 bump came later, but it
held the night's code). It used the same fresh-start driver: a VS Code of its own with no `graphene.path`, the
stand-in in place of Token Factory, and Claude Code, Codex and Gemini shimmed as not installed. All 59
screenshots are in `/tmp/gv-stranger2/shots/` for the night only; the log below is its own, trimmed.

## The numbers, against the before

| | before (0.8.0) | after (the night) |
|---|---|---|
| Minutes to the first graph | 11 | about 7 |
| Minutes to the first steer | 18 (a Tell); 23 to a link | about 14 (the envelope's forks); 20 to a link |
| Guesses | 9 | 11 |

## What stood in the way, worst first

- **The extension ran a different `graphene` from the one just installed.** It found `~/.local/bin/graphene`
  (this machine's own 0.8.0, which a fresh machine would not have) before uv's tool bin, kept it, and said
  nowhere which binary it ran: Add step… died with `graphene ask: no such option: --step`. This is the
  machine's doing and the extension's: it should say which `graphene` it runs, and look again after an install.
- **Add Step by Hand passes the title bare**, so a title that starts with `--` fails as an option (the review's
  B2, fixed with it).
- **Agents are gone before you can steer them**: the stand-in's forks end in under a second, so Tell opened after
  the race was over. That is the stand-in, not a person's race.
- **Quick-input prompts opened without keyboard focus** while a webview had it; typing went to the page. Maybe the
  driver's clicks; not seen by hand.
- **The walkthrough's Set Up This Folder button did nothing** when clicked, as in the before; the palette worked.
  The set-up notification's Auto… vanished on click.
- **With auto on, Plan and run landed the race at once**: the stranger chose it over Plan first, and a task it
  never asked for landed (the stand-in's canned plan).
- Open Changes from the palette does nothing, silently (the review's S33, fixed with it); the graph's Run ready
  button did nothing on click while the palette's worked; every side bar card repeats the goal as its
  description; the walkthrough ticks a step when its command opens.

## What worked

The walkthrough's path to the graph was short. Set Up This Folder's two picks, Set Envelope's forks, Link… (the
graph redrew the edge), Run Ready (a race on screen, Agents showing 4a and 4c, Needs You counting the hand-back),
Tell (said what it did) and Take Up the Hand-Back (offered Try it again, and ran it) all did what they said.

## Its note to the author

"Show which graphene you run, path and version, in the status bar's hover and in every CLI error, and prefer uv's
tool bin or the newest build over ~/.local/bin. Add Step by Hand must put `--` before the title. Quick-input
prompts should take focus even when a webview had it, and Open Changes from the palette should ask for a task
rather than do nothing. With plan-first on, I expected the plan to wait for me."
