# The prompt for the next run

Copy the block and send it as the whole ask. The direction is in [VISION.md](../VISION.md) and the
leaves are in [SCOPE.md](../SCOPE.md), so the message stays short. For a later run, change the run
name, the branch and the leaves; keep the rules. Once the docs are on `main`, branch from
`origin/main` again.

```
You are running the canvas run on Graphene, unattended.

Read, in this order, before any code: dev/VISION.md, dev/SCOPE.md, AGENTS.md. Open
dev/ui/canvas.html in a browser (add ?still for the end state): it is the look to reach.
Then do SCOPE.md's leaves 1 to 7, in order. A leaf lands whole, with its check green, or it
does not start. Do not look for other work in the repository.

Where
- Clone https://github.com/Alex-lop/Graphene into a directory of your own. Never work in
  ~/Desktop/AllThingsAgenticHackathon: it is Alex's checkout, with his uncommitted edits.
- Branch night/canvas from origin/docs/brainstorm: it is main plus the files this prompt names.
  Push after each leaf so CI runs. Open one draft PR into main after leaf 1, and keep it
  current. Never merge it, never push main, no tags, no releases, never pass --admin.

Commits
- As the git identity the clone has (Alex), with no attribution trailers.
- About 30, at most 50. Each says what it changes and which check shows it works. A
  subagent's work lands as one squashed commit.

Checks
- Each leaf's check before its push.
- uv run ruff check and uv run pytest -q -n auto before the PR opens, and again before the
  last push.
- After any README edit: uv run pytest tests -k readme -q -n auto. Move a pinned test in
  the same commit as the words it pins.
- The ubuntu test legs and vscode-e2e green on the PR at the end. If one is red, fix it or
  say why in the PR.

Help
- At most two subagents at a time, on Sonnet or Haiku, never Fable. Give each a file list,
  absolute paths and git -C, and remove origin from their clones.
- One review at the end, of the whole branch, capped at ten findings. Verify each finding
  yourself before fixing it.

Money
- No Nebius or Token Factory spend. The scripted stand-in drives every walk.
- A live model call only if a leaf cannot be checked without one: $2 at most, and the PR
  says what it was for.

Clock
- After about seven hours, start no new leaf. Finish the one in hand or revert it, then write
  the debrief.

Debrief: the PR description, written for Alex to read in five minutes
1. Per leaf: landed or not, and how to see it (one command or a click path).
2. Before and after screenshots of the canvas (from dev/process/canvas/).
3. What was not verified.
4. Files touched outside a leaf's list, and why.
5. At most five decisions you made that Alex may want to flip, each with your default.
6. Which row of VISION.md's convergence table moved, and what the next run should take.
```
