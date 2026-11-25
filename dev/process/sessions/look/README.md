# The look, before and after (24 November 2026)

Piece 5 of the sessions run (../../../prompts/sessions.md): PR #67's canvas with PR #68 and #69's readability.
Every picture is the graph's own preview page in headless Chrome (`../shoot.sh`), 900 px tall, at 680 px (a
Cursor editor area with its chat open) and at 1440 px, resampled to one pixel a point.

- `before-*`: the page as it was at `0a6852ea`, before the look changed.
- `after-*`: the page as it is.
- `running`: the fixture `editors/vscode/test/fixtures/running.json`, a plan in strict mode.
- `real`: one real Claude Code session (`claude -p`, haiku, in a scratch repository): a request that launched
  two subagents, fixed what they found and ran the tests, then a follow-up. Its snapshot was written to a file
  by the reader and drawn with `&state=`.
- `cursor`, `plus`, `light`, `hc`: Cursor Dark, Default Dark+, a light theme, high contrast (the preview's
  stand-ins for the editors' theme variables, `editors/vscode/media/preview-themes.css`).

What changed: the flow is the layout's default (a block only for a plan that would not fit), every line is one
curve from a card's port to the next one's, each card has a tile for who is working on it and its state's
colour on its border, its one line of status is under it, and only a working card's ring and its line move.
What stayed: the whole plan fitted on open, the zoom and its percentage, the type sizes, the card's cell, the
check at the card's foot with a tick only when it was earned, and every colour through `media/tokens.css`.
