# Tonight (1→2 Oct): first light, the live half

## Context
First light (28–29 Sep) was meant to be Graphene's first night on a real model: the ladder, the fixes
first contact forces, the prototypes and a rough cut. Only rungs 1–2 ran live ($0.0029 of $10). The
opening, `GRAPHENE_AGENT_LIVE_USD`, was not in that session's environment, and Sandboxes answered 403.
The Nemotron planner has never run live. The README still says Nemotron on Token Factory is "Built, but
not run live yet".

Alex now grants about $10 of Token Factory for overnight practice.

**The goal:** Graphene plans and runs on Nemotron for real, as practice, several times, so that:
- every break first contact finds is fixed with a test;
- Alex's own filmed take is predicted from repeated runs, not guessed;
- the docs say exactly what ran.

**Not tonight:**
- rung 6, the registered arms, and the sealed cards (`docs/test/tasks/*/{intent,paragraph,change}.md`,
  `accept.py`, `quality.py`, `intent_globs.txt`): their files are never opened or run;
- the filmed take, because `docs/demo/build.py` refuses any agent mark;
- from my shell: `ask`, `talk`, `plan cover|note|precheck`, `key`, `init` with a model, `plan accept`
  and `graphene run --with nemotron` (DIRECTION 101). The ladder plays the person on throwaway repos;
  I don't;
- the fixed trees, the frozen configuration, and Lean.

## Read live at 23:22 ($0: ConTree's whoami, which writes nothing)
- **Sandboxes now work** for the old key and the project: import, list and spawn are granted. The 403 of
  29 Sep is gone. M0 reads the new key again.
- **The old key expired at 23:27:06 tonight** (whoami's `token_expiration`). Alex is making a new one.
- **Sandboxes have no published price.** docs.tokenfactory.nebius.com/sandboxes/overview, read
  2026-10-01, states only beta limits (50 concurrent operations). The night ledger counts Sandbox
  operations and minutes at $0, "price: unknown".

## Found while planning (fixed tonight, $0)
- **Six commits never reached `main`.** They are on `origin/first-light` (fee8b6b..5166edb) and hold
  Alex's 29 Sep answers:
  - a spend cap that is not a number refuses every call;
  - `key check`'s Sandboxes line, and `init` placing leaves locally on a 401 or no answer;
  - prereg rule 6's $10 cap;
  - DIRECTION 132.

  PR #34 merged one push before them.
- **CI flake on `main`.** The two "failing endpoint, no backoff" tests failed 4 of the last ~8 CI runs,
  on branches that changed only docs (`test_precheck.py:288`, `test_cover.py:275`).
  - Cause, read in CPython: 11 tests patch the global `time.sleep` through `tf.time`.
  - `Popen.wait(timeout=…)` polls with sleeps of 0.001, 0.002, 0.004 … 0.05, exactly the recorded list.
  - On a loaded runner, a git child that outlives its pipes lands in the test's list.
  - *Correction (00:15, 2 Oct): it was 4 failed runs since 30 Sep, 3 of the last 17 completed, not 4 of ~8; and the branches changed no product code (readme also touched a test's README pins), not only docs.*

## Before the night (Alex, about 10 minutes)
1. Make a Token Factory key that outlives tomorrow. Replace `NEBIUS_API_KEY` in `~/.zshenv`, then open a
   new shell.
2. `cd ~/Desktop/AllThingsAgenticHackathon && GRAPHENE_AGENT_LIVE_USD=10 claude --continue`, in your
   overnight permission mode, then say "go". A fresh session works too: tell it to run
   `~/.claude/plans/ok-so-i-belive-stateless-swan.md`.
   - If that mode is auto, add
     `--allowedTools "Bash(/Users/alexlopez/graphene-practice-night/docs/test/practice.sh:*)"`, so the
     classifier cannot stall the ladder at 2 a.m.
   - I never set the opening myself (101). Never put it in `~/.zshenv`: every shell would become
     practice.
3. Stay until rung 2 starts, about 10 minutes, in case a permission prompt appears.

The $10 is Token Factory's only; Claude Code's own usage is separate. If the opening is unset when the
night starts, M0 and M1 run at $0, and the first line of the brief says so.

## How the night runs
**Spending**
- **The only live commands:** `/Users/alexlopez/graphene-practice-night/docs/test/practice.sh
  2|3|4|5|7|prototypes|night`, plus M0's one whoami read.
  - Never a bare `practice.sh`: it climbs to the next rung not passed, rung 6 included.
  - Never `access.py`, `nemotron.sh`, `bench.py`, `arm_*.py`, `build.sh`, `vhs` or `tmux`.
  - Nothing is called to provoke an error. The rungs assert their own leak, id and timeout checks; read
    each off its PASS line.
- **Only this session runs live, one step at a time.** Each step runs in the background (the Bash tool
  kills a foreground call at 10 minutes, and the rung's children would keep spending). It is called by
  absolute path with its output to a git-ignored file, waited on with Monitor, and stopped only with
  `kill -INT`.
- **After each step, look for leftovers.** `ps -axo pid,command | grep -E
  'practice\.py|nemotron\.sh|graphene_map\.executor|graphene (run|demo --record)'` must show nothing
  left; anything left gets `kill -INT` and a line in the brief.
- **The bill.** One night ledger (`~/.graphene/night/2026-10-01.jsonl`), capped at min($10, opening);
  nothing new past $8.
  - `practice.sh night` runs before and after each live step. If the bill moved between steps, all live
    work stops.
  - Sandboxes are capped by me at 150 minutes, as the ledger counts them, checked before each take.
    Past that, no new Sandbox take starts.
- **Never PATH's `graphene`.** It is Alex's stale editable install (041b93f): no night ledger, no cap. Use
  `~/graphene-practice-night/.venv/bin/graphene` or `uv run --frozen` there. In my shell it only reads
  (`plan`, `board`, `node show`, `demo --once`). A fix is tried by rerunning its rung. A take's repo is
  read only from a subshell, `(cd <repo> && …)`. Never set `GRAPHENE_TOKENFACTORY_URL`.

**Keys and leaks**
- **The key** is never printed, searched for, copied, written, or sent anywhere but Token Factory's API.
  Leak checks print counts only.
- **Before every push**, with the key and project present and the opening unset:
  - run `demo.leaks` on `tests/recordings/*.jsonl`;
  - count the key's and the project id's values in `git diff origin/main...practice`, in
    `git log --format=%B origin/main..practice`, and in the PR body.

  Anything but zero means no push.
- **A nonzero count anywhere stops all live work.** That rung's files are not quoted, committed or
  pushed, and the brief names them.

**Sub-agents and git**
- **Every sub-agent Bash call, and every test or gate call of mine,** starts with
  `unset GRAPHENE_AGENT_LIVE_USD NEBIUS_API_KEY NEBIUS_PROJECT_ID; export GRAPHENE_KEYCHAIN=off; cd <its worktree> &&`.
  Sub-agents inherit the opening, so this is what keeps them from spending.
- **Worktrees.** `git worktree add -b night-<lane> ~/graphene-night-<lane> practice`, never the harness's
  isolation (that cuts from origin/main inside Alex's checkout). Each is removed with
  `git worktree remove` once merged.
- **Guarded files.** A sub-agent's diff to `night.py`, `tokenfactory.py`, `sandbox.py`, `keys.py`,
  `demo.leaks`, or practice.py's `counted`/`Rung` lands only after I read it. test_night, test_tokenfactory,
  test_keys, test_practice and test_recordings must pass with no assertion removed or loosened.
- **Forbidden:** `git stash`, `git bisect`, `rebase --exec`, Playwright, browsers, and tags (a `v*` tag
  publishes to PyPI). Alex's checkout gets no file or git command of ours.
  - His hooks still record every tool event into his git-ignored `.graphene/graphene.db`; the brief says
    so.
  - My cwd stays in `~/graphene-practice-night`.
- **Pushing.** Only `git push origin practice`, after each milestone. Never `main`, never force, never
  merge.
- **Commits.** About 10–20, each green before it is pushed.

**Clock**
- `caffeinate -i -t <seconds to 08:00>` from the first action.
- No rung-7 take starts after 06:00. Nothing new after 07:15.
- CI green by 07:45; the brief pushed by 07:55.

## Milestones (each has a done-test)
**M0. Setup ($0, about 30 min; rung 2 starts about 10 minutes in, and the rest of M0 runs beside it).**
1. Read the opening by count: `printenv GRAPHENE_AGENT_LIVE_USD`.
2. `git fetch`, then `git worktree add -b practice ~/graphene-practice-night origin/main`. These write only
   the shared `.git`.
3. **Cherry-pick `fee8b6b..5166edb` first.** It stops once, at d45abf6 on README.md. Run
   `git checkout --ours README.md`; that commit's message says its README hunk was dropped, since
   HOW_IT_WORKS carries it.
4. `uv sync --all-extras --frozen`.
5. One whoami read from the night's venv: the new key's expiry and Sandboxes' state, metadata only. A key
   that ends before 09:00 goes in line one of the brief, and live work stays within its time.
6. Start rung 2 (M2).
7. Beside it:
   - archive `docs/process/morning.md` (now 5166edb's) as `morning-2026-09-29.md`;
   - start the new brief with the rollback SHA (origin/main 4e1660c);
   - commit this plan as `docs/process/directives/PRACTICE_PLAN.md`;
   - push, and open one draft PR.
- *Done:* test_key_cli, test_sandbox_contract, test_tokenfactory, test_init, docs/test/test_bench,
  test_arm_a and test_arm_bprime pass.

**M1. CI flake ($0, one background sub-agent, at most 45 min; M2 never waits on it).**
- `tokenfactory` sleeps through a name of its own, at lines 130 and 143 only. The 11 tests patch that
  name.
- *Done:* a new test pins that tokenfactory's backoff never touches the global `time.sleep` (it fails on
  `main`). Both flaky tests pass 30 times in a row under a self-ending CPU hog, never during a live step.

**M2. First contact: the ladder** (caps add to about $1.55; expected under $0.10).
- Run `practice.sh 2`, then `3` (a leaf in a Sandbox), `4` (the escape test), `5` (a recorded leaf),
  then `prototypes` (cover, note, precheck: 4–5 Nano calls, their first live JSON answers).
- Rung 5's recording goes to `tests/recordings/first-light-rung-5.jsonl` once `demo.leaks` counts zero.
  CI replays it.
- Each break goes to a sub-agent. It writes a test that fails first, then the fix; I integrate it and
  rerun the rung.
- Blockers are written from the log's last lines, not from the "most likely" line, whose first match can
  blame Sandboxes.
- *Done:* rungs 2–5 and the prototypes pass live, or each blocker is written down with its log line.

**M3. Rung 7, repeated: Nemotron plans and runs feeds** (at most 5 takes, $3 cap each; expected
$0.02–0.50 each).
- `practice.sh 7` runs `docs/proof/nemotron.sh` with its own public paragraph. Ultra plans and Nano
  executes, with Super if a leaf steps up. `init` places the leaves: in Sandboxes when whoami says they
  work, otherwise on this machine. Every take uses the same placement.
- After each take, before anything else:
  `cp .graphene/practice/demo.jsonl .graphene/practice/take-N.jsonl` and the same for `rung-7.log`.
  Rung 7 overwrites both.
- **Code may change only until a take passes.** After that, takes repeat on unchanged code until three
  have passed. Alex's take is then predicted from three runs.
- **Fixes are first-contact plumbing only:** a misparsed reply, a wrong-worded refusal, placement, the
  recorder, a client timeout. No prompt, `PROMPT_VERSION`, model by role, forks, escalation,
  `--parallel` or `--rounds` change, because those belong to the frozen configuration. A case for one
  goes to Decide.
- **Per take, record:**
  - wall minutes, and Ultra's planning minutes (scene 03's cut label);
  - the bill, planner apart from executors;
  - Ultra's board items, and whether it raised the legacy-feed question Claude Code put up as
    `zero-legacy`;
  - which leaves landed and which came back, with which model;
  - placement and Sandbox minutes;
  - anything a camera would catch.
- The best take goes to `tests/recordings/first-light-rung-7.jsonl` once `demo.leaks` counts zero.
  Swapping it into `src/graphene_map/demo.jsonl` is a Decide item.
- *Done:* three passing takes on one code state, or each take's blocker written down.

**M4. Say exactly what ran ($0), in this order.**
1. `docs/test/first-light.md`: a row for every rung and every take, leak-counted.
2. `docs/process/field.md`: its "one live line" sentence becomes tonight's.
3. README's "Where it's at" line, CHANGELOG.md:5 and the pin at `tests/test_doc_claims.py:153` change in
   one commit. The README stays short.
4. HACKATHON.md: the gap lines, the stale comment at lines 14–18, and new items in "Feedback on Token
   Factory".
5. LIVE_SESSION.md: measured minutes and dollars.
6. DIRECTION 133 onward.

Every surface reports every take (k of n, with ranges), never the best one alone.

**M5. Closing (from 06:30).**
- Three adversary sub-agents: leaks (counts only), claims against the ledger, and the diff's
  correctness.
- A skeptic reproduces each finding, and each fix gets a test.
- Run the gate with the opening and the key unset: `uv sync --all-extras`, `ruff check`, `pytest -q` in
  the background. The ui check is CI's.
- Push, then wait for all 7 CI jobs.

## Budget
- The night cap is $10, and nothing new starts past $8. Expected: $0.10–2.50 of Token Factory, plus at
  most 150 Sandbox minutes at an unpublished price.
- What the rest of the $10 could buy is off-limits or Alex's: rung 6, the arms, the fixed trees, the
  shaping study. So no take or rerun runs just to spend.

## The brief (top of the new morning.md, at most 20 lines, true at every milestone)
- **Watch first.** Tonight's best live take, replayed with no key and no spend:
  `cd ~/graphene-practice-night && uv run --frozen graphene demo tests/recordings/first-light-rung-7.jsonl`.
  Then his own filmed take: `cd ~/graphene-practice-night && caffeinate -i uv run --frozen --extra sandbox docs/demo/build.sh`,
  with its minutes and dollars measured over n takes.
- **What ran live.** Each rung and take, pass or fail, and the bill against $10, with Sandbox minutes.
- **New tonight.** At most 5 lines, each with its command.
- **Decide.** At most 3 items, each with a default (for example, ship the live replay).
- **Broken or risky.** At most 3 lines.

## Verification
- `practice.sh status` shows rungs 2–5 and 7 PASS. `practice.sh night` shows the bill and Sandbox minutes.
- `pytest -q tests/test_recordings.py` replays both recordings offline, saying "as it ran, live".
- Leak counts are 0 before every push. CI is green on all 7 jobs at the last code commit.

## Critical files
- `docs/test/practice.py`, `practice.sh`, `PRACTICE.md`, `first-light.md`, `LIVE_SESSION.md`
- `docs/proof/nemotron.sh`
- `src/graphene_map/{night,tokenfactory,sandbox,keys,demo}.py`
- `tests/test_recordings.py`, `tests/test_doc_claims.py`, `tests/test_precheck.py`, `tests/test_cover.py`
- `README.md`, `CHANGELOG.md`, `docs/HACKATHON.md`, `docs/process/field.md`, `docs/DIRECTION.md`
