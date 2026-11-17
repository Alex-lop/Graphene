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
- The folder you start in sits inside a git repository at Alex's home directory. Run git only
  inside your clone, as git -C <your clone>.
- Branch night/canvas from origin/docs/brainstorm: it is main plus the files this prompt names.
  Push after each leaf so CI runs. Open one draft PR into main after leaf 1, and keep it
  current. Never merge it, never push main, no tags, no releases, never pass --admin.

Commits
- As the git identity the clone has (Alex), with no attribution trailers.
- About 50 in all, between 40 and 50: Alex merges the branch in the morning, and every
  commit lands on main. Each is one coherent step that says what it changes and which check
  shows it works. Never a "wip" or "fix typo" commit: fold those into the step they fix
  before pushing. A subagent's work lands as one squashed commit.

Checks
- Each leaf's check before its push.
- uv run ruff check and uv run pytest -q -n auto before the PR opens, and again before the
  last push.
- After any README edit: uv run pytest tests -k readme -q -n auto. Move a pinned test in
  the same commit as the words it pins.
- The ubuntu test legs and vscode-e2e green on the PR at the end. If one is red, fix it or
  say why in the PR.
- When the last push is green on every leg, mark the PR ready for review (gh pr ready) so
  Alex can merge it in the morning. If anything is red, leave it a draft and say why in the
  first line of its description.

Help: ultracode is on, and Alex has usage to spend. Spend it where it buys correctness.
- Use workflows and subagents, Fable included, for work that is truly independent:
  - lanes inside a leaf whose files do not overlap, such as the engine half and the extension
    half of live-plan, scope-pane and workflows;
  - a read-only scout that maps the next leaf's code while you build the current one;
  - after each leaf and before its push, two readers: one on the code, and one comparing the
    leaf's screenshots with dev/ui/canvas.html.
- Leaves stay in order. Two agents never write the same file at the same time.
- Every finding gets two skeptics, each told to disprove it from the code. Fix only what
  survives both, or what you confirm yourself. Put more skeptics on a finding that matters,
  and none on a typo.
- At the end, review the whole branch at its seams, where the leaves meet: one reader per
  seam, two skeptics per finding, and a fixer on a branch of its own. At most 25 findings.
- Keep the night under about 60 agents. A weekly limit stops the run dead, so push after
  every leaf.
- Agents' clones have no origin: only you push, open or edit the PR. Give each agent a file
  list, absolute paths and git -C. Their work lands through you, squashed, as Alex, with no
  trailers. A Fable lane may sign its commits as itself, so rewrite them.
- An agent that follows the README as a stranger would runs uv tool install. Set UV_TOOL_DIR
  and UV_CACHE_DIR to a scratch directory first, or it lands on Alex's PATH.
- If an agent goes quiet for twenty minutes, read its transcript and take its work over.

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
7. How many agents ran, and what the reviews found and fixed.
```
