# morning.md — 2026-09-26 — the winning directive

**The blocker: this session had no Token Factory key, so access failed and nothing ran live.**
`NEBIUS_API_KEY`, `NEBIUS_PROJECT_ID` and `NEBIUS_AI_PROJECT` were unset in the shell this run works
in, and there is no `contree` CLI on the path. When I tried to run `uv run python docs/test/access.py`,
Claude Code's auto-mode classifier refused it as "credential exploration", and it refused my look at
where the key might be kept for the same reason. I did not try any way around that. So the
directive's "if access fails" branch was in force: only the work that needs no key (items 3, 7, 8, 9,
11 and 12), then stop.

To give the next run access (two minutes):

```
# in ~/.zshenv, which every shell Claude Code starts reads:
export NEBIUS_API_KEY=…   NEBIUS_PROJECT_ID=…
# then, in the session, so the classifier sees you run it:
! uv run python docs/test/access.py
```

(Current at every milestone of this run. The Nemotron run's morning is `morning-2026-09-25.md`.)

## 1. The chart and the pre-registered table

**There is neither.** Both need live runs, and the directive's access-failed list leaves out item 2,
the pre-registration included (a stand-in writes each task's paragraph, which is stand-in work). No
number in any surface comes from a live run, and none was made up.

## 2. First contact

**Not made.** No leaf ran on Token Factory or in a Sandbox, the escape test did not run in ConTree, and
there is no live recording to replay in CI. What is ready for the moment a key exists:

- **The failure paths a beta service will throw** (item 8, decisions 71 to 74), each with a test
  against the fake: a retired model id, a 429 storm, 5xx errors, a timeout, a reply cut off, a
  malformed or text-only tool call, a sandbox killed or gone mid-leaf, a hung check, and the cap of
  fifty operations at once. The leaf comes back with its cause and what to do, the run goes on, and
  nothing is left running. `uv run pytest -q tests/test_faults.py` (21 tests, about 3 minutes).
- **`graphene demo --record FILE`**, and `RECORD=<file> docs/proof/nemotron.sh`, which records the live
  run as it happens, for `graphene demo` and for a CI replay.

## 3. What a judge sees

- **The README** (`README.md`). Directly under the unchanged opening sits "Graphene on Nemotron": the
  claim, where the chart goes (it says the chart does not exist yet), what runs where, and that the
  path has run only against the stand-ins. Next is "For judges", ten lines with the no-key path first.
  "The first ten minutes" has two paths: with the agent you have (no key), and on Nemotron through
  Token Factory (a key).
- **`graphene demo`**: a recorded run replayed in the real screen. It needs no key, no Docker and no
  network, and runs nothing. The top line reads `replay · a scripted stand-in, not Nemotron · …`,
  because tonight's recording is the fake's. Try `uv run graphene demo`.
- **The screen, before and after** (item 3). `docs/process/winning/screens/{before,after}/`, at 80×24
  and 120×36, made against the scripted stand-in (the README there says so first). Each fork is a
  row under its leaf: its model, `fork k`, its state. A step up is named on the bottom line
  (`farewell stepped up to Nemotron-3-Super-fake: attempt 1 refused: …`) and in the leaf's pane.
  The pane shows the sandbox and the bill, and the record (Enter) says which fork won and why the
  others did not.
- **The Devpost draft** (`docs/HACKATHON.md`): every field. Each number names its source, and none is
  live. The account of the Submission Period comes from `git blame` (all 13,540 lines of `src/` at
  `94ce837` were written after 26 August 16:00 UTC). The feedback is concrete, with an eighth point:
  model retirement needs a machine-readable signal.
- **The field** (`docs/process/field.md`, item 11). The Coding track's public entries, read from their
  READMEs. **Read this one:** forking N candidates from one checkpoint and letting the tests pick is
  the track's most common pattern (Arborist, Coppice, ARCHON, PortVerdict and at least six more,
  several live with SWE-bench numbers). So the directive's "nobody else maps a person's pruned tree
  onto a tree of sandboxes" must not go out. What the field leaves Graphene is narrower: we found no
  other entry where a person prunes the plan an agent proposed before anything runs, and none that
  measures the tree against the paragraph in the person's attention. No surface in the repository
  makes a claim the field falsifies (decision 79).
- **The closing review** (decision 80). Five adversaries covered the executor, the replay, the
  screen, the claims and a stranger's first ten minutes, and a skeptic reproduced each finding. That
  gave 36 findings, all collected before any was fixed: 27 confirmed and all fixed, plus two refuted
  ones fixed because they went against the directive's intent. Each fix has a test that fails
  before it. The two that mattered most were on the fork path, which predates tonight and which
  item 3 now puts on screen:
  - a winning fork deleted git-ignored files in its scope from the checkout (a `.env` under `**`);
  - every fork was blind: `view` said each file "is not there".
  Also fixed:
  - a stopped run left forks calling Token Factory, unbilled, and containers behind;
  - a stand-in recorded from a second terminal replayed as "live";
  - a key split across two looks survived in a recording;
  - `graphene init`'s first line, on the no-key path, was a signup pointer.
- **Not built tonight, because each needs the key:** the video (item 4), the demo page export of a
  live run (item 7), the real repository (item 5), the feature built on Nemotron (item 6), and the
  judges' seats on the real video and text (item 10).

## 4. What only you can do, in order

1. **The key, two minutes** (the commands at the top). Everything live waits on it.
2. **PR #30 → main** (draft), when CI is green: ten minutes for the merges and decisions 70-80.
   Merge it before anything from `docs/HACKATHON.md` goes into Devpost: the judges' install line
   installs `main`, which has no `graphene demo` until then.
3. **The GitHub About text and homepage**, two minutes. They still describe the old Taskmaster
   product, and a judge meets them first. A line for it: "A plan you and your coding agents share, as
   a tree: NVIDIA Nemotron plans and does the leaves on Nebius Token Factory, each held to its files
   in a Sandbox, and the check decides what lands."
4. Later, after the live run: the voice-over (about 30 minutes), Pages (one click on
   `pages.yml`), the tag `v0.5.0` for PyPI (`docs/RELEASING.md`; two minutes once CI is green), the
   Devpost form (an hour, from `docs/HACKATHON.md` in your words), and the diary command at the end of
   `morning-2026-09-25.md`.

## 5. Decisions from 70, each with its evidence

All are in `docs/DIRECTION.md`, and each names its tests (80 is the review):

- **70.** `init` offers what it finds, none first (revises 61).
- **71.** A retired model falls back within the family.
- **72.** Refusals and give-ups come back with the cause and what to do (extends 68).
- **73.** A sandbox killed or gone mid-leaf, and a hung check.
- **74.** Fifty sandbox operations at once, machine-wide.
- **75.** Forks and the model on the leaf's log.
- **76.** Forks and a step up on the screen and the page.
- **77.** The replay.
- **78.** A record without git's history says so.
- **79.** The front door, and what the field changed.
- **80.** What the closing review changed.

Read 70, 74, 77 and 80 first.

## 6. The plan to 30 October

| When | What | Risk |
| --- | --- | --- |
| The day the key is here | `access.py`; first contact (item 1): one leaf local, one in a Sandbox, the escape test in ConTree, a recording replayed in CI | ConTree's real behaviour on a killed or timed-out operation is untested (decision 73) |
| +1 day | Pre-register (item 2), then tuning on feeds and inventory with fixed trees, then freeze | Nano may land little; report it |
| +2 to +4 days | The arms A, B, B′ (and C on your agent), the chart from the ledger | Spend: the cap is `GRAPHENE_SPEND_CAP_USD`, 50 if unset |
| +5 days | The live demo run, recorded (`RECORD=src/graphene_map/demo.jsonl`), the page exported, the draft video | A flaky live run on camera: record scene by scene |
| +6 days | The real repository (item 5), the feature built on Nemotron (item 6), the judges' seats (item 10) | |
| by 25 October | HACKATHON.md in your words, Pages, `v0.5.0` on PyPI | Judges test until 15 December |
| 30 October, 10:00 PT | Submit | Yours |

Frozen: nothing yet, since the configuration is frozen only after tuning.

## 7. Questions

1. Can the next session have the key in `~/.zshenv`, and will you type `! uv run python
   docs/test/access.py` in it yourself, so the classifier sees you run it?

## Verified, and not

- **Verified here:**
  - The suite: 832 passed, nothing skipped, at the merge of the review fixes (`56cfc02`); ruff clean;
    the page's 23 UI tests pass, and the committed page equals its build.
  - The wheel, built at 0.5.0, installed offline in clean `python:3.12`, `3.13` and `3.14`
    containers with `--network none` and no key. On each, `graphene --version` says 0.5.0,
    `graphene demo --once` prints the replay, and the demo script passes end to end against the
    scripted stand-in with the wheel's `graphene` (`docs/test/wheel_smoke.sh`).
  - `graphene demo` in a pseudo-terminal (the replay lane, by hand).
- **Not verified:** anything on Token Factory or in ConTree. That covers the real model ids and
  prices, Nemotron's tool calls, ConTree's users, output cap and timings, the thirty-leaf run at
  `--parallel 8` (only against a counting fake box), and every number the directive calls live.

## Rollback

Before the first change, `main` on GitHub was `ebf7a95` (your merge of PR #29). This run is the
branch `submission`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard ebf7a95
```

## State of every branch

- **`submission`:** this run, pushed; draft PR.
- **The four lane branches**, `worktree-wf_54a10577-161-1` to `-4` (faults, forks, demo, front),
  and the three review-fix branches, `worktree-wf_187a44e6-dfa-1` to `-3` (executor, replay,
  screen), are merged into `submission`. Their worktrees are under `.claude/worktrees/`, and the
  branches are kept (`git branch -d` drops them).
- **`main` (GitHub):** `ebf7a95`, untouched. Local `main`: `6cece1c`, behind, untouched.
- **Everything else** is as it was.
- **Left running, not mine:** a fake Token Factory server from the Nemotron run's judges,
  `/tmp/judge/fakeserve.py` (pid 37353, up for a day). I left it alone.
