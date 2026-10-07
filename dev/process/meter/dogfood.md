# Dogfood: Graphene writes its own HOW_IT_WORKS, with plan first on and the meter on itself

Run on 7 October between 01:04 and 01:16. A clone of `meter` at `94f128d`, Graphene from a wheel of the
branch installed as a tool. The person was the agent that ran the night, acting from a shell with no
agent's mark (`dogfood.py`, beside this file). Every live call is on the night's ledger, purpose `dogfood`.

## What ran

1. `graphene init`: Claude Code as the planner, read-only, on Sonnet; Claude Code on Opus as the
   executor, its stream on. `graphene plan first on`.
2. `graphene ask` with `ask.md`: lane 3's HOW_IT_WORKS cut, as a paragraph. The first answer could not
   be read ("line 4: option: is a question's"); Graphene asked again.
3. The proposal: ten leaves. Nine wrote one section each into `dev/process/meter/how/`, each with a test
   file of its own (`tests/test_how_plan.py` and eight more), so that no two leaves shared a file; a tenth
   assembled them. One board question: should the final check run the README's doc tests whole?
4. The person's prune. Nine fragments and nine test files for one document was more than the job, and
   the planner had said so itself ("If you would rather one leaf write the whole file, drop the nine
   fragments"). The person dropped them and wrote the brief into the tenth leaf's goal: `node set` with a
   new goal, scope and `--needs none`. The first `node drop` was refused, because the tenth leaf still
   waited on the nine; the order mattered. Then the board's default, then `plan accept`.
5. `graphene run`: the leaf came back after 6 minutes and $2.72. Its record in `node show` said why: the
   check called bare `python3`, and a run's worktree has no `.venv`, so the doc tests could not import
   `graphene_map`. The doc itself was written, at 2,903 words.
6. The person changed the check to `uv run --frozen pytest …` (`node set --check`) and ran the leaf again
   (`graphene run --node assemble`). It landed after 3 more minutes and $1.55: 2,849 words, a test that
   pins the size and the sections, and the privacy test pointed at the new file.

## The bill

`graphene watch` at the end: `agents 0 · 8m · $4.27 · you 7 acts ~4m · 1/1 done, finished`.
`graphene run`'s two lines: `run: 1 came back (assemble) · agents 6 min, $2.7174 at list price · you 0
acts, 0 min`, then `run: 1 done · agents 3 min, $1.5479 at list price · you 0 acts, 0 min`.
The planner's answer is text and reports no cost; the ledger holds its $1.50 worst case.

## What it caught, and what it cost

- **The tree paid once, before anything ran.** The waste in the proposal, nine files and nine tests for
  one document, was visible in the tree and cost two commands to remove.
- **The meter paid once, when the leaf came back.** "exit 0" would have said nothing; the attempt's
  record said what it wrote, what it ran and why the check could not run.
- **What it found in Graphene:** a check that needs the project's environment cannot pass in a run's
  worktree, which has none. The planner wrote the check the way the repo's own docs would.
- **Plan first cost:** 7 acts over about 4 minutes, against 9 agent-minutes.
