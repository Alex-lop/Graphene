# The rules, written before any number

Written at the start of the night of 10 October 2026, before any experiment ran, on the clone at 907a7d0. Every
number tonight is taken twice, on `$A` (907a7d0's wheel) and on `$B` (the branch's wheel at the frozen SHA that
`after.md` names), with the same scripts under `dev/process/prove/`, the same budgets, the same isolation flags.
A difference is claimed only where a rule below says so.

## Intervals

- x of 40 (X1): a Wilson 95% interval. Two builds differ only when their intervals do not overlap; otherwise
  "no difference shown".
- x of 16 and smaller counts: the same rule.
- n = 3 (X2's Graphene arm, X7, the walks): medians and ranges. Only a full flip (0 of 3 against 3 of 3) is
  reported as a difference; anything else is "no difference shown".
- n = 1 (a stranger transcript, each plain and `/batch` session, X2(d), X4): a fact, never a rate.
- No human is measured tonight. Every "stranger", "walker" and "reader" is a Sonnet session, and every table says
  so in its caption.

## Decision rules: what keeps or reverts a change

- **A1, the schema planner.** Built only if at least 10% of `$A`'s first refusals in X1 fall in the classes the
  schema and its repairs reach: a board item written as a node; `then:`/`about:`; an option under a risk; an
  unusable id. Otherwise A1 is deferred to the morning's list with the histogram. Once built: if proposals by
  first answer on `$B` are lower than on `$A` with non-overlapping intervals, A1 is reverted and the PR says so.
- **C1's cap.** Its value comes from X0(b): "$2 an attempt" if a resumed try is capped on its own, else "$5 a
  leaf". If any attempt in X2's `$B` arm stops at the cap where `$A`'s landed, the number goes to the PR's decision
  list; it is not changed silently.
- **C3's environment probe.** If X5's test-first leaf (`b`, whose check names a test file inside its own scope)
  gets an environment line on `$B` while pytest is present, C3 is wrong and is cut back to printing the gist.
- **C4's editable line.** If X5 on `$B` does not print it for leaf `a` with the editable venv first on PATH, C4 is
  reverted.
- **X7.** The default stays `on` whatever the counts; the counts go in the PR beside decision 176.
- **D5 and X3.** Git's gain from the merge bodies is reported as its own row ("git now answers k of 10"). The
  record arm is compared with git plus the agents' last words on the same build, never across builds alone.
- **Any change** whose guard test (the pinned budgets, caps, recordings) fails at the frozen SHA is cut, not
  loosened, unless the plan names the raise (the HOW_IT_WORKS cap).

## Expected results, written before the runs

- **X2.** Equal `accept.py` and `quality.py` scores across arms within the noise of n = 3; the plain session
  cheaper and faster than Graphene's arm; zero out-of-intent writes in every arm (the plain session has scored
  zero in every prior run); the planted fault's fix lands in the owner's file in Graphene's arm by construction of
  `r`, and in the plain session's arm because it edits the file directly. What may differ is whether anything
  records why the fix was made and what the closing round cost.
- **X5.** The broken leaf `a` lands with `python3 -m pytest` on both builds (the editable install makes the check
  import the checkout); `uv run pytest` refuses it on both; `$B` prints the editable line before the run and `$A`
  prints nothing; with no pytest on PATH, `$A` reads `outside` for `a` and `red` for `b`, and `$B` prints an
  environment line for both.
- **X1.** The semantic classes (one writer; a check that runs a file another leaf writes) do not move between
  builds. The grammar classes fall on `$B` if A1 ships. Proposals by ask on `$A` are expected near the loop night's
  3 of 4, with a wide interval.
- **The walks.** On `$A`: dead ends at init's silence about plan first, at a lost ask, and at `node show` on a
  board item's id; on `$B` fewer, and no rate is claimed.
- **X3.** Arm A (the record) answers more of the eight factual questions on `$B` than on `$A` because the changes
  print what was stored; that rise is by construction and `after.md` says so. The claim is only the comparison
  with Arm B on the same build.

## The ten questions (X3) and where `truth.json` gets each answer

| # | Question | Source of truth | Scored by |
|---|---|---|---|
| 1 | Which files did the fault-fixing leaf change | the landed merge's diff (`git diff m^1 m --name-only`) | script, exact set |
| 2 | Why, in the agent's words | the executor's final result in the run log | a Sonnet reader (synthesis) |
| 3 | How many executor commands were refused, and name one | `permission_denials` in the run logs' result events | script, count and membership |
| 4 | Did any leaf's check already pass at the base; which | precheck rows in the plan log | script, exact id |
| 5 | Planner dollars and total dollars | `graphene plan record` | script, within one cent |
| 6 | Most leaves running at once | start/end times in the plan log | script, exact count |
| 7 | Which leaf came back and why; which was reopened | the plan log's released and reopened rows; the harness | script, exact ids |
| 8 | What waits on the person now | the plan's proposed rows and board | a Sonnet reader (synthesis) |
| 9 | The merge sha that landed the fix | the landed row; `git log --merges` | script, 7-char prefix |
| 10 | How many leaves were added after acceptance | proposed rows after the accept row | script, exact count |

The questions were drawn from the gaps the night's changes fill. `after.md` says so, and Arm B (`git log -p` plus
the agents' last words) is read on the same build as Arm A, so the merge bodies the night adds count for git.

## Safety for every session the night starts

- A clone's `origin` is removed before any agent runs in it; `GH_CONFIG_DIR` is an empty directory and `GH_TOKEN`
  and `GITHUB_TOKEN` are empty; `Bash(gh *)` and `Bash(git push *)` are denied; `codex` is hidden from the PATH of
  any session that runs `graphene init`, or its "chose none" is recorded.
- Every `claude -p` carries `--setting-sources project,local --strict-mcp-config --max-budget-usd`, and its allow
  list on the command line, never in a settings file.
- Each build is installed into its own `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` under the scratchpad, never the default
  tool directory that holds the `graphene` Alex's checkout hooks run.
- A session's whole process group is killed at 30 minutes.
- Nothing runs `--with nemotron`; `GRAPHENE_AGENT_LIVE_USD` stays unset; no Codex spend.
- Alex's checkout is never opened; every command that spells the store directory or the two script variables lives
  in a script under `dev/process/prove/` and is run by path.
- Saturday's tag `statements-prereg-2`, `dev/test/PREREG-statements.md` and `dev/test/PROVE.md` are never
  opened, built or run.

## Spend

Ceiling $60 of Claude Code on Alex's login, Sonnet throughout (the stranger transcript's own `init` picks the
account default, as a stranger's would). Estimates: X0 $1.50; X1 $16; X2 $13; X2(d) $3; X3 $2.50; X4 $4; X5 $0;
X6 $6; X7 $3; seam re-checks $3. `ledger.md` is updated after every experiment from each session's
`total_cost_usd` and each repo's `graphene plan record`. Checkpoints: the end of Phase 1 (about $22) and before the
after arms. Cut order: X2(d); the walks to 2 a build; X2's a-wide row; X4's after arm to one issue.
