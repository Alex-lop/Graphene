# The best-of night, 20 October 2026

Alex's ask, before bed: look at the product, not the hackathon, and make it better; take the retry further ("what
if we ran multiple tests to see which one was best"); maybe change the graph's direction; whatever is decided goes
in the README; a PR of 50+ commits to review in the morning.

## What was decided, and why

1. **Forks, with the check as the judge.** Every shipped tool that runs several agents on one task hands the
   person N diffs (Codex cloud's best-of-N, Conductor, Crystal, Sculptor, uzi) or asks a model afterwards
   (Cursor's best-of-n judge); none uses the project's own tests to choose. Graphene has a check per task, the
   one filter every lab recipe starts with (Agentless, Trae Agent, Anthropic's own best-of-N). Among the forks
   that pass, execution evidence first: CodeT's dual execution agreement, at its smallest (each fork's test files
   run on the others' trees); then size, cost, time. Never random, never a model: judges are biased toward
   style, and an LLM selector peaks at 5 or 6 candidates. Reward hacking is the known trap, so once agreement
   has spoken, a fork that changed the check's own files comes after the forks that did not. Sources: `research/best-of-n.md`.
2. **The rule was written before any fork ran** (`src/graphene_map/pick.py`, commit "pick: which fork of a leaf
   to keep, by a rule written before any fork ran"), so no result could bend it. One change since, from the
   engine lane's review: step 1 counts only the other forks' tests (counting a fork's own rewarded writing any
   test at all).
3. **The graph flows into the goal.** A diagram about why puts the goal first (KAOS, GSN, OKR trees); one about
   what must happen before what reads toward its end (logic models; GitLab, Airflow, Dagster since 1.6, n8n).
   A run is the second kind; with every arrow meaning "lands before", the goal is the one place every line
   ends. Sources: `research/graph-direction.md`.
4. **The gate fails closed** where Claude Code can (2.1.295, `onFailure: "block"`), and a call the hook cannot
   judge is refused, not let through. The cost: a repo set up this way refuses every tool call while
   `graphene` cannot run.
5. **The gate's reader** takes the 19 October review's findings 1, 4, 5 and 6 (`dev/process/publish/gate/`);
   findings 2 and 3 stay limits (their fixes made stores in other repos, and two leaves from one prompt).

## How it was built

Lanes, each in its own clone with no remote, then merged here: the engine (forks in `graphene run`, the hold,
the hooks, `done`, the record), the cockpit (fork rows, `f`, digits, the forks table), the graph (waves, lanes,
the goal last), the gate (the reader), and after the merge the docs, the demo and the held bench's forks arm. Each lane had one reviewer
and a fixer; after the merge, the seams were read (forks against the cockpit's rows; nothing changed without
forks) with one skeptic per seam. The commits are as built: a lane's work, then its review's fixes, each with
the test that failed before it.

## The live run

`run.txt`: a toy repo, the branch's build installed in its own venv first on PATH, `graphene run --forks 3 --with
claude:haiku --max-usd 7`. Three Claude Code agents, each judged in its own copy by its own `graphene node done`;
the rule kept a (`10 lines against 12`); one merge, `Executor: claude claude-haiku-5-5 · 3 forks, kept a`; three
refs under `refs/graphene/forks/stats/`; no worktree left; $0.0173 at list price. `run-under-cap.txt`: the
first try, with `--max-usd 1.50`, started nothing and did not say why (now it does).

## Not measured

Whether forks raise the share of tasks that land. The literature: +5 points at N=3 (Trae Agent), +5.8 at N=5
with a trained critic (OpenHands), and coverage climbs fast while selection lags. The held bench (`dev/held/`)
now asks it as a second question, written before any number: G3 (G with three forks a leaf) against G, on
false done and on landed, with its own decision rule and ceiling (`dev/held/rules.md`). Running it is live
spend on Alex's login, his to open.

## The research

`research/` holds three of the night's briefs as they were written, before anything was built: what tools and
papers do with several attempts at one task (`best-of-n.md`, whose "candidates" became the forks), which way a
run's graph should read (`graph-direction.md`), and what other harnesses and task tools do well
(`landscape.md`). Their sources are linked in each; what a brief could not open, it marks unverified.
