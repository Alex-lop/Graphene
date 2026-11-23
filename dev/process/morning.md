# The polish night, 23 November 2026

*Written through the night (00:30 to 10:00) by Claude Opus 5.5, with Opus agents only (no Fable). The lanes, their
reviews and the critics' findings are summed up in the pull request.*

## Your 15 minutes

1. **It is already in your Cursor.** The night's build was installed there at about 03:17 and again at 05:00;
   to load the second I disabled and re-enabled the extension, which leaves Home's side bar blank until the window
   reloads. So reload once (palette: **Developer: Reload Window**), then click Graphene in the activity bar: the
   graph opens in the editor, whole. Your real plan (the fa26 group repo) is
   six whole cards in two sub-goals, the goal readable, a **1 question** chip, and **Start** the one filled button.
2. **Click a card.** Its pane is an inspector: the state and who in its head, May change and Done when first, the
   one act at its foot, the rest under **…**. Nothing was started, accepted or answered on your plan tonight.
3. **Home** (the side bar) has no box to type in: a card for the plan, what needs you, the suggested plan with
   Start, and Settings at the foot. With no plan it tells you to ask Claude Code or Codex in its chat.
4. **Read the PR** (its body has the decisions to veto), and look at `README.md`: half as long, the editor first,
   the new picture.
5. **To release 0.10.0** (everything is numbered; nothing is tagged): merge the PR on GitHub (the two CHANGELOG
   headings say 23 November 2026: change them if you tag another day), then `git switch main && git pull`, then
   `docs/RELEASING.md` as before (`git tag v0.10.0`, push the tag, then the GitHub release with the `.vsix`).
   That release is the first to start `publish-vscode.yml`: with no `VSCE_PAT` or `OVSX_PAT` secret its two
   registry jobs go red, as expected (`gh run cancel` it): the `.vsix` on the release is the install. Both
   READMEs install `graphene-map` from PyPI and `graphene-0.10.0.vsix` from the v0.10.0 release, so they are true
   only once both exist.

## What changed, by what you asked

- **Typing the prompt is gone.** Home's ask box and Plan it, and Graphene: Auto…, are removed. A plan comes from
  your agent's chat (the hooks), a workflow on Home, or Add task on the graph.
- **The expanded graph without hunting.** Graphene's icon opens the graph whole in the active editor group (in
  Cursor a tab that opens by itself does too, since the agent chat already narrows the editor); the side bar's
  cramped Graph view is gone; Home's title bar has Open the Graph.
- **Not loose, not flat in Cursor.** `media/tokens.css`: no colour from what Cursor's themes leave weak (focus
  border 20% white or transparent, near-black button text, a white widget shadow). Then three rounds: a two-row
  header with one main act (Start a suggested plan, Run, Stop), whole cards with two-line titles and their files
  and check inside, state on a card's mark and colour only where it wants you, one bracket per sub-goal into the
  goal, square quiet edges, the question on the canvas, the pane as an inspector, Home with one filled act a card.
- **README** 159 → 97 lines, the extension's 185 → 104, one word a thing on every screen.

## Decisions for your veto

In the PR body, each with what undoes it.

## Not verified

- Nothing ran with a real agent tonight: every walk drove VS Code against the scripted stand-in, and your own
  plan was only read (`graphene state --json`), never run.
- `E2E_APP=cursor node test.mjs` fails its first check (the tab that opens by itself at Cursor's start takes the
  keyboard), exactly as it did before tonight; every other step passes in Cursor.
- Cursor's own Agent cannot plan with Graphene: `graphene init` installs Claude Code's and Codex's hooks only.
  Cursor now has hooks of the same shape (`.cursor/hooks.json`: `preToolUse` can deny a write, `sessionStart` can
  add context), so this is buildable; it was not built, because no Cursor agent CLI is on this Mac to test it.
