# Findings: thirteen read-only readers, 14 October 2026

Each finding names its evidence. `verified: no` means the reader read it but did not reproduce it.


## Controller completeness (`gaps`)

Controller completeness: Graphene has most of the controls a person would look for, but several are hidden, named the wrong way round, or stop short. The core is solid. Hooks refuse a Claude Code write outside its scope before it happens, git and the check hold every executor at `done`, each leaf lands as its own merge, and `node show`, `node diff` and `plan log` keep a full record. The gaps a stranger hits in the first ten minutes are these. There is no `graphene stop`. There is no spending limit for a whole run: the only cap is per attempt, it covers Claude Code only, and Codex has none. `--signoff` merges the work into your branch before you sign it off. Nothing tells you how to take back a landed leaf. `plan pause` turns the rules off instead of stopping the agents. The README names none of these controls. Most of the fixes are a few lines, because the parts they need already exist in the code (`run_holding` plus SIGINT for stop, `park()` for hold-before-merge, the `--no-ff` merge for revert). Everything below comes from reading the code and running `--help`. I started no runs, so how these behave in a live run is untested.


### 1. There is no command to stop a run; the only ways are Ctrl-C in the run's own terminal or a hidden `:stop` inside watch

*high; verified: yes*

- **Evidence.** `graphene stop` printed: "graphene: no such command 'stop'". `graphene --help` and `graphene run --help` offer no stop. The working code exists only in the watch screen: src/graphene_map/tui.py:2189-2207 (`stop_runs`: finds the run with `R.run_holding`, then sends it SIGINT), and it is reached by typing `:stop` (tui.py:1728). The help shows it only as an example inside ":<command> any graphene command (:ask, :stop, :node set)" (tui.py:83), which suggests a `graphene stop` exists when it does not. Per leaf, `graphene node release <id>` does stop that leaf's executor within 0.5 s (run.py:282-292, `_let_go` at run.py:334), but its help says "Use this when the node cannot be finished as written", not "stop it".
- **Why it matters.** "How do I stop it?" is the first thing anyone asks before handing hours of work to agents. Someone who started `graphene run` in another terminal, in tmux or over ssh has no command they can find.
- **Smallest change.** Add `graphene run --stop` (an option, so the nine-command top-level help limit in tests/test_help_budget.py still holds), reusing `R.run_holding(root)` plus `os.kill(pid, SIGINT)` exactly as tui.py:2193-2202 does. Print "stopping the run: what it holds goes back to the plan". Rewrite the `:` line in tui.py HELP to name `:stop` as "stop the run". Mention the command in the README.
- **Files.** src/graphene_map/plan_cli.py, src/graphene_map/tui.py, README.md

### 2. No spending limit or time limit for a whole run in the installed product; Codex attempts have no limit at all

*high; verified: yes*

- **Evidence.** run.py:50-54: Claude Code gets `--max-budget-usd 2` per attempt, and ATTEMPTS = 3 (run.py:56), so a run's worst case is about $6 times the number of leaves, and nothing adds that up. CODEX = "codex exec --json --sandbox workspace-write" (run.py:58) has no cap. The run's first line prints a cap only when `--max-budget-usd` is in the command (plan_cli.py:1053-1058, `* bool(cap)`), so a Codex run states no limit and does not say it has none. `graphene run --help` has no budget, max-dollars or timeout option. The waiting loop has no wall-clock limit (run.py:284-292). The only whole-run cap is the Nemotron extra's "night" ledger, switched on by an environment variable from dev tooling (`GRAPHENE_AGENT_LIVE_USD`, nemotron/night.py:1-10, 78-88; `extra.load` returns None without the extra, extra.py:10-16). Users are never told about it, and docs/HACKATHON.md:171-172 says the ceiling is $10 and new work stops at 80%, while the code says CEILING = 50.0 and START = 0.9 (night.py:46-47).
- **Why it matters.** "What's the most this can cost me overnight?" has no answer today, and leaving agents running unattended depends on that answer.
- **Smallest change.** Step one, a few lines: have the run's first line print the worst case (leaves x attempts x cap), and print "no spend cap" when the executor has none. Step two: add `graphene run --max-usd N`. The run loop already sums the metered dollars that `summary()` reports; once that sum reaches N, start no new attempt. Add an optional `--minutes` per attempt by passing a timeout to the existing `_end(proc)` path. Separately, correct the $10/80% figures in HACKATHON.md to match the code.
- **Files.** src/graphene_map/run.py, src/graphene_map/plan_cli.py, docs/HACKATHON.md

### 3. `--signoff` does not hold the merge: the leaf lands in your branch first, and you sign it off afterwards

*high; verified: yes*

- **Evidence.** In a run, when a sign-off leaf passes its check it goes to REVIEW (plan.py:2484: `REVIEW if node.signoff`). `work()` returns it because its state is DONE or REVIEW (run.py:577-578), and `collect()` then calls `land()` on every leaf that is not None (run.py:1120-1121). `land()` merges it with `--no-ff` into your checkout (run.py:941-974). A sign-off leaf is held back only when its merge fails or the run is stopped (`park()`, run.py:1150-1167). The parts for a real gate already exist: `park()` commits the work to `graphene/<id>` and puts the leaf in review, and `plan.signoff` refuses while that branch is not merged and tells you `git merge graphene/<id>` (plan.py:2696-2712).
- **Why it matters.** Someone who sets `--signoff` expects to approve the work before it reaches their branch. That is the main thing they would compare against a PR-first competitor, and the behaviour is the opposite of what the flag's name suggests.
- **Smallest change.** In `collect()` (run.py:1120), when `node.state == P.REVIEW`, call `park(store, tree, node, say)` instead of `land(...)`. Then `graphene node diff <id>` shows the branch, and `git merge` followed by `node signoff` (already enforced) lands it. Later, let `node signoff` run the merge itself. Add one test in tests/test_run_live.py: a sign-off leaf leaves HEAD unchanged.
- **Files.** src/graphene_map/run.py, tests/test_run_live.py, docs/HOW_IT_WORKS.md

### 4. Nothing tells a person how to take back a landed leaf, although git makes it a single command

*medium; verified: yes*

- **Evidence.** `grep -rn 'git revert'` over README.md, docs/ and src/graphene_map/*.py found nothing. `graphene plan undo --help`: "Undo your last act on the plan, such as a drop or an accept" (it changes the plan, not the code). dev/DIRECTION.md:1734 (decision 182): "Nothing is reverted by a reopen... its fix lands as a new commit on top." Each leaf lands as one `--no-ff` merge with a `Graphene-Node:` line in its message (run.py:938), so `git revert -m 1 <merge>` removes exactly that leaf's work.
- **Why it matters.** "Can I undo what the agent did?" comes right after "can I stop it?". The design already answers yes, but nobody tells the user.
- **Smallest change.** Have `graphene node show <id>` print "take it back: git revert -m 1 <sha>" under the landed commit it already prints (node_record.py / record.py), and add the same line to the README's command list. A `graphene node revert` command is not needed yet.
- **Files.** src/graphene_map/node_record.py, README.md, docs/HOW_IT_WORKS.md

### 5. `graphene plan pause` turns the rules off; it does not stop the agents

*medium; verified: yes*

- **Evidence.** plan_cli.py:910-916: "Pause the plan: nothing starts and no write is refused", which prints "paused: ... nothing is enforced". `in_force` is false while paused (plan.py:1580-1582), and the hook then lets every call through (gate.py:669-670) and lifts plan-first (gate.py:184-186). Executors already running are not signalled: only `node release` or `drop` stops one (run.py:291, 334-341). New starts are refused (plan.py:1939-1940).
- **Why it matters.** Someone who wants the agents to hold still will type `pause`. What they get is: the running agents carry on, and their writes are no longer refused before they happen (they are still caught at `done`). The word means the opposite of what they want.
- **Smallest change.** Have pause also stop a live run (the same SIGINT path as finding 1), so it hands back what it holds. Or rename the help line to "Lift the plan: nothing starts, and agents already running are no longer refused". The first is safer and about 3 lines.
- **Files.** src/graphene_map/plan_cli.py

### 6. The README names none of the controls: stop, cost ceiling, undo, or which branch the work lands on

*medium; verified: yes*

- **Evidence.** README.md (68 lines) never mentions Ctrl-C, `:stop`, `node release`, a dollar cap, revert, or that a run merges into the branch you have checked out. The run says that last point only once it has started (plan_cli.py:1057: "landing into {on} at {at}"). The only control it lists is the exit (`graphene init --remove`, README.md:55).
- **Why it matters.** For a broad audience, the case that Graphene keeps you in control rests on four plain sentences: you can stop it, it can't spend more than X, you can undo it, it never touches anything but the branch you're on. Without them the README sells a planner, not a controller.
- **Smallest change.** Add a 4-line "You stay in control" block to the README: stop (`Ctrl-C`, or `:stop` in watch, or `graphene run --stop` once it exists), cost ("$2 an attempt, 3 attempts a leaf, with Claude Code"), undo (`git revert -m 1`), branch ("lands on the branch you have checked out: `git switch -c agents` first to keep main clean").
- **Files.** README.md

### 7. Nothing tells you when a leaf needs you while you are away

*low; verified: yes*

- **Evidence.** `grep -rn -i 'notif|bell|osascript|webhook'` over src/graphene_map/*.py found only vendor-notification filtering (gate.py:247). The things that need a person (a leaf that came back, a sign-off in review, an open board question) show up only in `graphene watch` ("quiet for n min" after QUIET = 120 s, tui.py:63) and in the run's last line.
- **Why it matters.** Once someone hands off hours of work, they want to be pinged when a leaf is blocked on them, not to watch a screen. Every parallel-agent tool people compare this with does that.
- **Smallest change.** In the run's `say` path, when a leaf comes back or reaches review, write a terminal bell (`\a`) and one line. Optionally, on macOS, call `osascript -e 'display notification ...'` behind a setting. Do no more until someone asks for it.
- **Files.** src/graphene_map/run.py

### 8. Only Claude Code is stopped before a write; Codex and every other agent are caught only at `done`, which the README's summary hides

*low; verified: yes*

- **Evidence.** docs/HOW_IT_WORKS.md, under The executors: Codex's "sandbox keeps it to the checkout, not the scope; the scope holds at `done`", and for any command "nothing holds it before the write". plan.py:50 knows GEMINI_CLI and CURSOR_AGENT only as marks that say "this is an agent". There is no install step for any agent other than Claude Code (`init` installs Claude Code hooks only). README.md:38 says "It runs whatever executor you like: Claude Code, Codex, Nemotron, or any command", with no difference stated.
- **Why it matters.** A Codex or Cursor user reads the README, thinks they get the same guard as a Claude Code user, and finds out otherwise only after the fact.
- **Smallest change.** Add one row per agent to the README: "Claude Code: stopped before the write; Codex and others: caught at done, by git". Hooks for other agents are a later decision, not a quick fix.
- **Files.** README.md

**Not verified.**

- I did not run a live `graphene run` (the read-only rules forbid it). That a `--signoff` leaf merges before sign-off comes from reading run.py:577-578, 1120-1121 and plan.py:2484, not from watching a run.
- Whether a paused plan still enforces the scope at `done` for an executor already running: I read only the hook side (gate.py:669) and the start refusal (plan.py:1939).
- Whether Codex CLI now offers hooks that Graphene could use to stop a write before it happens: not checked.
- That `git revert -m 1` on a leaf's merge is handled cleanly by Graphene's next start (decision 47 suggests a commit is simply the repository moving): not tested.
- That wrapping the executor as `--with 'timeout 30m claude ...'` would work as a time limit: not tested. label() may then fail to recognise Claude Code, and the meter would be lost.

## The diff in front of the person (`diff`)

Lane: the diff in front of the person. The c key in graphene watch works on a review leaf as well as a done one, but it shows only file names and counts (`node diff --stat`). The key line on a review row and the ? help never mention c. The surprising part: a leaf marked `signoff: yes` is already merged into the person's checkout by `graphene run` before it waits for sign-off. I reproduced this in a scratch repo. The node ended in state review, its log ended `finished, landed`, HEAD moved and a.txt was in the checkout. Meanwhile the watch pane said "its check passed; it waits for your sign-off". So today, on the competitors' one advantage (a diff before the merge), Graphene shows the diff after the merge, and only if you know about c. The smallest change: c opens a "diff" view of the whole change, in colour, with a one-line header that says whether it is already in your checkout or still waiting on its branch. The view stays open while the cursor moves leaf to leaf and while the plan changes. The key appears on review rows and in help. Holding signoff leaves off main until y is a separate leaf and Alex's decision. All scratch work was in mktemp directories through the repo's own test helpers. Nothing in the repo was written.


### 1. signoff: yes does not hold the merge: graphene run merges the leaf first, then asks for sign-off

*high; verified: yes*

- **Evidence.** run.py:941-997 land() commits and runs `git merge --no-ff` for every passed leaf and never reads node.signoff; plan.py:2484 only sets the state to REVIEW. Scratch run (mktemp repo, run_parallel, leaf a with signoff True): printed `STATE review ['added','started','attempt','ended','check_passed','finished','landed']`, `HEAD moved True`, `a.txt in checkout True`, and the run said `a is finished; it waits for a sign-off`. The watch pane for that leaf at 80x24 read `a · review / its check passed; it waits for your sign-off`, with no word that it is already merged. Only `graphene node show a` said `landed: deae53c`. x (send back) runs reopen (plan.py ~2747-2752), which sets the leaf to open and reverts nothing.
- **Why it matters.** The person thinks sign-off decides whether the work goes in. In fact it is already in their branch. Sending it back leaves the rejected work merged. This is exactly the 'diff before the merge' that competitors offer and Graphene claims to answer.
- **Smallest change.** Separate leaf, Alex's decision: in run.land(), when node.signoff is set, commit on the branch and save 'unlanded' (as park() does, run.py:1152-1167) with why 'it waits for your sign-off', instead of merging. Then plan.signoff() on an unlanded leaf runs the clean merge itself; today it refuses until the person merges by hand (plan.py:2700-2716). Until then, the pane and the diff header should say 'already in your checkout'.
- **Files.** src/graphene_map/run.py, src/graphene_map/plan.py, src/graphene_map/tui.py

### 2. c is hidden on the one row where it matters: review

*medium; verified: yes*

- **Evidence.** tui.py:109 KEYS['review'] = ['y sign off','x send back','Enter record'], with no c. Only tui.py:111 (done) hints 'c diff'. The HELP table (tui.py:67-93) never lists c. Scratch: the review key line at 80 and 120 columns was `y sign off · x send back · Enter record · Tab view · ? help · q quit`, yet pressing c there worked and showed the stat.
- **Why it matters.** A person asked to sign off is never told they can see what they are signing.
- **Smallest change.** Add 'c diff' to KEYS['review'] (77 of 78 columns at 80 wide) and a c row to HELP's 'see' group. Update the pinned line in tests/test_tui.py:1155.
- **Files.** src/graphene_map/tui.py, tests/test_tui.py

### 3. c shows only the stat, never the change itself

*medium; verified: yes*

- **Evidence.** tui.py:1975 runs `node diff <id> --stat`. Scratch at 80x24: the pane showed `a.txt | 200` and a bar of +. Typing `:node diff a` in the same screen already puts the whole patch in the pane (scratch: `diff --git`, `index`, `@@`, `+def handler(...)`), uncoloured, with git's plumbing lines and long lines wrapped.
- **Why it matters.** File counts are not something a person can judge. The whole diff is already computed by plan_cli.py:1450-1493 and only one flag away.
- **Smallest change.** c opens the whole diff (stat, then patch) in its own view, coloured by line. See 'proposed'.
- **Files.** src/graphene_map/tui.py, src/graphene_map/plan_cli.py

### 4. What c shows is wiped by the next change anywhere in the plan

*medium; verified: no*

- **Evidence.** finished() sets view 'said' (tui.py:2182-2187). refresh resets 'said' to 'contract' whenever the tree's shape changes (tui.py:1033-1036), and shape includes every node's state (tui.py:1020). Reading a diff while a parallel run starts or finishes another leaf throws the person back to the contract. I read this in the code and did not reproduce it.
- **Why it matters.** Review leaves pile up while a run is still going, which is exactly when a person reads diffs.
- **Smallest change.** Make the diff a view like 'record' or 'tail' (rendered in show_detail and cached by recorded()), not 'said'.
- **Files.** src/graphene_map/tui.py

### 5. At 80 columns the stat's bar wraps onto its own line

*low; verified: yes*

- **Evidence.** Scratch at 80x24, c on a 200-line file: the pane showed `a.txt | 200` on one line and the `++++…` bar on the next. pane_room() is (77, 16), and git sizes --stat for 80 columns when there is no terminal. Correct at 120x36.
- **Why it matters.** The first thing the narrow screen shows looks broken.
- **Smallest change.** Pass `--stat=72` in plan_cli.py:1487.
- **Files.** src/graphene_map/plan_cli.py

### 6. c has one test: a landed leaf, at 120 columns, stat only

*low; verified: yes*

- **Evidence.** tests/test_tui.py:2692-2701 is the only test that presses c. No test covers a review leaf, an unlanded (parked) leaf, 80x24, or a long diff.
- **Why it matters.** The sign-off path, the one people need most, is unpinned.
- **Smallest change.** Add the one test named in 'leaf-contract'.
- **Files.** tests/test_tui.py

**Not verified.**

- That the diff view is reset during a live parallel run: read from tui.py:1020-1036, not reproduced with a run in flight.
- Render time of the pane for diffs of thousands of lines (the proposed 2000-line cap is a guess, not measured).
- That `git diff --stat=72 --patch` keeps the bar on one line inside the 77-column pane: reasoned from the scratch output, not run (a scratch git commit outside the run helper was refused by Graphene's own Bash hook).
- Whether any pane-colour test besides tests/test_tui.py:1143 would object to green/red diff lines.
- How long tests/test_plan_cli.py takes whole; the check names one id from it.
- Behaviour of c on a leaf done by `graphene run --here` with signoff: yes (no merge happens there; node diff shows the checkout's working tree).

## CI and repository hygiene (`ci`)

Lane: CI and repository hygiene. Healthy at the core: the suite is thorough and only one test is red. There are four real problems. (1) The red test is wrong, not the code. On Linux, and on a Mac with TMPDIR=/tmp, the temp directory is the bare /tmp. demo.leaks() is designed not to count bare /tmp, so the count is 1 and the test expects 2. Pinning tempfile.tempdir in the test fixes it (checked in a scratch copy under both TMPDIRs). No other test makes the same assumption. (2) CI takes about 20 min on ubuntu and about 29 min on macOS, almost all of it in a serial `pytest -q` (1,930 tests). Every PR commit runs twice (push plus pull_request), so 12 jobs. pytest-xdist is not a dependency. With xdist (in an ephemeral overlay), the whole suite ran locally in 4m10s instead of the usual ~18 min. Eleven tests failed only because xdist workers set COLUMNS=80. A three-line autouse fixture that clears COLUMNS/LINES made those files pass in parallel. (3) To a stranger on GitHub the repo looks unkempt: 16 open PRs (12 agent PRs from September, 4 'full history' evidence PRs, imgbot), 31 branches, a one-line description that does not say what Graphene is, community health 42% (no CONTRIBUTING, SECURITY, issue or PR templates), and a v0.5.0 release with no title whose body is the entire 22.7k-character CHANGELOG, opening with '## 0.5.0 (not published yet: the tag is Alex's)'. (4) Backup branches (*-before-fold, *-full-history, timeline-before-shape) hold the SHAs the evidence cites and must NOT be deleted. Closing their PRs keeps the branches. Side effects of my reads: `git fetch -q origin` updated remote-tracking refs, and a zero-byte untracked file `uv-620c4ce47c6493c8.lock` appeared at the repo root at 22:27:34. It most likely came from my run with an empty TMPDIR, nothing holds it, and it is safe to delete. I left it because my rules forbid writes.


### 1. The one red test asserts a count the code deliberately does not make when the temp dir is /tmp

*high; verified: yes*

- **Evidence.** tests/test_demo.py:687-689 builds `{tempfile.gettempdir()}/y` and expects leaks(...)['a path under the temp directory'] == 2. src/graphene_map/demo.py:117-122 `_temps()` drops any temp path of length <= 4, so bare '/tmp' is never counted (by design, per its docstring and demo.py:95). With TMPDIR=/tmp, gettempdir() is '/tmp' and only '/private/tmp' is counted, giving 1. `TMPDIR=/tmp uv run --no-sync pytest -p no:cacheprovider tests/test_demo.py -q -k temp_paths` printed `assert 1 == 2` / 1 failed. Without TMPDIR it printed 1 passed. CI log for run 38564650720 shows the same `assert 1 == 2` on all 3 ubuntu jobs. The test arrived in 79bbdda4 (2026-10-13), and main CI has been red since 2026-10-14T03:51.
- **Why it matters.** main shows a red X to every visitor, and every PR inherits the failure, so a real regression on Linux cannot be told apart from this one.
- **Smallest change.** In the test only: add `monkeypatch` to the signature, then `monkeypatch.setattr(tempfile, "tempdir", "/scratch/T")` before hider(), and use the literal `/scratch/T/y` in `scratch`. Verified in a scratch copy of the test: 1 passed with TMPDIR=/tmp and 1 passed with the default TMPDIR. Leave the code alone, because its 'bare /tmp is not counted' rule protects old recordings (tests/recordings).
- **Files.** tests/test_demo.py, src/graphene_map/demo.py

### 2. CI runs the 1,930-test suite serially, twice per PR commit, in 6 jobs: ~20 min Linux, ~29 min macOS

*high; verified: yes*

- **Evidence.** `gh run view 38564650720 --json jobs` step timings: the pytest step took 1093-1182 s on ubuntu and 1663-1758 s on macOS. Every other step took under 5 s. Logs say '1907 passed ... in 1661.03s (0:27:41)' (macos 3.12) and '1923 passed ... in 1179.11s' (ubuntu 3.12). .github/workflows/ci.yml has `on: push:` (every branch) plus `pull_request:`, a 2x3 matrix, no `concurrency`, and `uv run pytest -q`. `gh run list` shows the same SHA run as both pull_request and push (e.g. night/feel 6f2b8bfb, loop 7ac059f2). pyproject.toml [dependency-groups] dev has no pytest-xdist, and uv.lock has no pytest-xdist entry.
- **Why it matters.** Every agent's loop and every PR waits about 30 minutes for a green, and twice the runner minutes get spent.
- **Smallest change.** In ci.yml: `push: branches: [main]`, plus `concurrency: {group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true}`. Add `pytest-xdist` to the dev group and run `uv run pytest -q -n auto`. Optionally, run the full Python matrix only on push to main and ubuntu+macOS on 3.13 for PRs.
- **Files.** .github/workflows/ci.yml, pyproject.toml, uv.lock

### 3. pytest-xdist cuts the local suite from ~18 min to 4m10s, but 11 tests fail under it because workers set COLUMNS=80

*medium; verified: yes*

- **Evidence.** One full run: `uv run --no-sync --with pytest-xdist==3.6.1 pytest -p no:cacheprovider -n auto -q --durations=40` on 11 cores reported '11 failed, 1897 passed, 21 skipped ... in 250.42s (0:04:10)'. All failures were in tests/test_plan_cli.py and tests/test_precheck_wire.py. The same two files run serially: 59 passed. A scratch test printing env showed 'COLUMNS= None ... tty= False' serially and 'COLUMNS= 80 LINES= 24' under `-n 1`. src/graphene_map/plan_cli.py:259 treats a set COLUMNS as being at a terminal. With a scratch plugin holding an autouse fixture that delenv's COLUMNS and LINES, `-n 4` on both files gave 59 passed. Slowest single test: 84.23s (dev/test/test_statements.py rehearsal).
- **Why it matters.** The parallel speedup is real (about 4.3x locally) and costs only a dependency and a fixture. Without the fixture, turning on xdist makes CI red.
- **Smallest change.** In tests/conftest.py, extend the existing autouse `no_agent_marks` fixture (line 38) or add one beside it: `monkeypatch.delenv("COLUMNS", raising=False); monkeypatch.delenv("LINES", raising=False)`. Then add xdist as in the previous finding. If dev/test later shows the same symptom, its own conftest needs the same lines.
- **Files.** tests/conftest.py, src/graphene_map/plan_cli.py

### 4. The v0.5.0 GitHub release has no title and its body is the whole CHANGELOG, starting with 'not published yet'

*medium; verified: yes*

- **Evidence.** `gh release view v0.5.0 --json body,name,assets` returned name='' and assets=0, with a 22,727-character body that begins '# Changelog' / '## 0.5.0 (not published yet: the tag is Alex's)' and runs on through 0.2.0 history in internal words ('rung 5', 'first light', 'the cut', 'Token Factory'). CHANGELOG.md on main now reads '## 0.5.0 (13 October 2026)' (line 23). The tag points at a96fb48a (2026-10-07), and main is 184 commits ahead.
- **Why it matters.** The release page is the second thing a stranger clicks. What they find there says the release is unpublished and needs insider vocabulary to read.
- **Smallest change.** Outward-facing, Alex decides: `gh release edit v0.5.0 --title "Graphene 0.5.0" --notes-file <short.md>` with 5-8 plain bullets (install line, what you see, link to CHANGELOG). Optionally `--latest`.
- **Files.** CHANGELOG.md

### 5. 16 open PRs and 31 branches. Most PRs are stale, but the backup branches must stay

*medium; verified: yes*

- **Evidence.** `gh pr list --state open` shows #12-#22 (agent/* and Aug-Sep chores, 1-3 commits ahead, last touched 2026-08-30 to 09-07), #25 imgbot, and #32/#35/#41/#42, which are evidence branches (shaping-full-history ahead 333, first-light-full-history 151, main-before-reshape 123, meter 121, each also hundreds behind main). Memory 'fold-history-before-first-push' says *-before-fold branches keep the SHAs the evidence names, and `git grep` on origin/main finds 'before-fold' in 2 files and 'timeline-before-shape' and 'full-history' in 1 each. Already merged into main and deletable: codex/runtime-recovery-final-release-20260828, rebuild, strategy, graph, submission, shaping, night/feel.
- **Why it matters.** 16 open PRs on a 0-star repo read as abandoned work. Deleting the wrong branch breaks the cited evidence.
- **Smallest change.** Outward-facing, Alex decides: close #32 #35 #41 #42 with a one-line comment ('kept as an evidence branch'). Closing keeps the branch. Close #12-#22 as superseded, or merge #12 (license line) if still wanted. Delete only the 7 merged branches. Keep every *-before-fold, *-full-history, timeline-before-shape, process and process-archive branch.

### 6. The imgbot PR #25 is safe to merge or close: lossless image shrink, files unchanged on main

*low; verified: yes*

- **Evidence.** `gh pr view 25`: 1 commit (rebased 2026-10-14), MERGEABLE, 7 images in docs/assets and docs/brand, '-9%' overall. All 7 exist on main, and each blob at the merge-base equals origin/main's.
- **Why it matters.** It is one of the open PRs a visitor sees, and watch.gif is due to be re-recorded anyway, which would make its change moot.
- **Smallest change.** Outward-facing, Alex decides: merge it now, or close it and re-run imgbot after the new watch.gif lands.
- **Files.** docs/assets/watch.gif

### 7. The repo front page undersells Graphene: vague description, 42% community health

*low; verified: yes*

- **Evidence.** `gh repo view --json` description: 'Trying to make the collaboration w/ Claude better so you have an idea of what's going on with your agent'. Topics are reasonable (claude-code, ai-agents, cli...). Wiki is enabled. `gh api repos/Alex-lop/Graphene/community/profile` gives health 42, with contributing, code_of_conduct, issue_template and pull_request_template all null, and only README and LICENSE present. There is no SECURITY.md, and .github/ holds only workflows/.
- **Why it matters.** The description is the line shown in search results and link previews. It reads as tentative and never says what you install or get. A tool that runs hooks on people's machines with no SECURITY.md also looks unready.
- **Smallest change.** Outward-facing, Alex decides: `gh repo edit --description "A shared plan for you and your coding agents: Claude Code hooks keep them to it. pip install graphene-map"` and `--enable-wiki=false`. Add a short SECURITY.md (how to report, what the hooks can touch) and one issue template (bug).
- **Files.** .github/workflows/ci.yml

### 8. Root clutter: WHAT_THIS_RUN_DID.md is tracked at the root; $R/x is local only

*low; verified: yes*

- **Evidence.** `git ls-tree --name-only origin/main` lists WHAT_THIS_RUN_DID.md next to README, CHANGELOG and LICENSE. Its first line is '# What this run did, and why it matters', an internal account of PR #45/#48. '$R' contains only an empty directory 'x' (find), and git does not track empty directories, so GitHub never shows it. It is an unexpanded shell variable from some script.
- **Why it matters.** A root file named for one night's run is the first thing after README in the file list a stranger scans.
- **Smallest change.** Inside the repo: `git mv WHAT_THIS_RUN_DID.md dev/process/` (or docs/) and fix any links. Locally: `rmdir '$R/x' '$R'` and delete the stray zero-byte uv-*.lock at the root.
- **Files.** WHAT_THIS_RUN_DID.md

**Not verified.**

- A full-suite run with both fixes (the COLUMNS fixture and the temp-path test) under -n auto. Only the two affected files were re-run in parallel (59 passed). The one full parallel run was before the fix.
- CI wall time with xdist on GitHub's runners. The local 4.3x speedup is on 11 cores. Hosted ubuntu and macOS runners have fewer, and their exact counts were not checked.
- Whether dev/test/ (its own conftest) needs the COLUMNS fixture. None of its tests failed under xdist in the full run.
- Whether the uv-620c4ce47c6493c8.lock at the repo root was created by this investigation. Its creation time (22:27:34) matches my run with an empty TMPDIR, but another concurrent reader could have made it. lsof shows nothing holds it.
- Whether Alex still wants any of the September agent/* PRs (#13-#22). Their bodies were not read beyond #22's first lines.
- Whether merging imgbot's watch.gif is lossless in visual terms. Only file identity on main was checked, not the pixels.
- Side effect: `git fetch -q origin` was run to compare branches. It updated remote-tracking refs in .git and nothing else.

## The market, from the web (`market`)

Market lane, as of 2026-10-14, from vendor docs, GitHub releases and public issues. Graphene's real edge still holds, but only in a narrower form than "plan first". For Claude Code, nothing else ships this: a plan the person approves in which every piece names the files it may change and the check it must pass, writes outside those files refused while the agent works, and the check run by the tool in a clean copy before the piece lands. Plan approval itself is now everywhere: Claude Code plan mode, Cursor Plan Mode, Kiro specs, Cline Plan/Act and Spec Kit (141k stars). Kiro also now runs a dependency graph of tasks in parallel "waves". Graphene's README headline ("See your coding agents' plan and change it before any code") sells the part everyone has. Three things changed around 10 October. Entire 0.11.5 (14 Oct) added "trails" (intent across branches) with gates before merge. Claude Code v2.1.295 (8 Oct) added `onFailure: "block"` so a hook that crashes stops the action instead of letting it through; Graphene's hook does not use it yet. Claude Code's own docs say its plan mode is not enforced in interactive sessions where bypass is available. Several products have one thing Graphene lacks: the person looks at a diff or PR before the merge (already known). Real users describe the problem as "Claude modified files I didn't ask it to modify", which is the first option on Anthropic's own bug form, and as "reports ALL PASSED when tests are FAILING". Graphene's README should lead with those words.


### 1. The README headline sells the feature every competitor already has

*high; verified: yes*

- **Evidence.** README.md:10 "See your coding agents' plan and change it before any code." The same thing ships natively in four places. Claude Code: "Claude reads files and proposes a plan but makes no edits until you approve" (code.claude.com/docs/en/common-workflows). Cursor: "Plan Mode creates detailed implementation plans before writing any code" (cursor.com/docs/agent/plan-mode). Kiro: requirements.md, design.md, tasks.md, and "Kiro builds a dependency graph of the tasks in your tasks.md and groups independent tasks into waves... tasks within a wave execute concurrently" (kiro.dev/docs/specs, page updated October 2, 2026). Cline: Plan/Act modes (docs.cline.bot). github/spec-kit has 141,309 stars (gh api, 2026-10-14). None of these pages describes per-task file limits or a check the tool runs itself.
- **Why it matters.** Someone who isn't an engineer, comparing tools, reads the headline as "plan mode" and stops there, since they already have it for free. The part only Graphene has (the agent touches only the agreed files, and done means the check passed) shows up as the README's third bullet, in words like "held by git and the check".
- **Smallest change.** Rewrite the README's first line in users' own words, for example: "Your agents change only the files you agreed to, and 'done' means your check passed, not that the agent said so." Move the plan or tree to the second line as the way you agree.
- **Files.** ~/Desktop/AllThingsAgenticHackathon/README.md

### 2. Entire moved closer on 14 October: intent across branches plus gates before merge

*high; verified: yes*

- **Evidence.** entireio/cli CHANGELOG [0.11.5] - 2026-10-14 adds three things. First: "`entire trail merge` merges a trail's branch into its base after checking mergeability and gates; `--dry-run` only reports, and `--force` bypasses gates where the repo's bypass policy allows it" (PR #2566, merged 2026-10-07). Second: "Project-scoped trails... one trail captures intent across repositories and branches." Third: agents launched by Claude Code's Workflow tool are now recorded. The same release removed line attribution: `entire blame` no longer gives AI/Human/Mixed labels. 5,182 stars. Its blog (entire.io/blog, newest 2026-10-08) describes no blocking of writes or file scope. The gates are evaluated server-side through the trails API (from PR #2566's description).
- **Why it matters.** The best-funded tool in the space ($60M seed, per the repo's own scan) now has two of Graphene's ideas: a recorded intent, and a gate before merge. Graphene's remaining difference is narrower: limits per piece, enforced while the agent works rather than at merge, and run locally with no account or server.
- **Smallest change.** Add Entire 0.11.5 to the market section of dev/PRODUCT_THESIS.md. In the README, put the difference as "during the work, not at the merge" and "on your machine, no account".
- **Files.** ~/Desktop/AllThingsAgenticHackathon/dev/PRODUCT_THESIS.md

### 3. Graphene's "refused before the write" fails open; Claude Code can now make it fail closed

*high; verified: yes*

- **Evidence.** Graphene installs every hook as {"type": "command", "command": "graphene ingest hook", "timeout": 5} with no onFailure (src/graphene_map/hooks.py:484). The design says "The hook stays fail-open and fast: exit 0 whatever happens" (dev/process/directives/GRAPH_DIRECTIVE.md:99). Claude Code v2.1.295 (CHANGELOG: "Added `onFailure: \"block\"` for command and HTTP hooks") documents why it matters: "a policy hook with a wrong path or a crashing script lets everything through... set \"onFailure\": \"block\"" (code.claude.com/docs/en/hooks.md, line 904). The thesis's backup layers, an Edit(path) deny rule and sandbox denyWrite (dev/PRODUCT_THESIS.md:378-386), are not in src/: grep for denyWrite and Edit( found nothing.
- **Why it matters.** The claim only Graphene can make is that writes outside a piece's files are refused. Today that holds only while the hook is healthy. If graphene is missing from PATH, crashes, or takes more than 5 s, writes go through and are caught only by git's recheck at done. A skeptic who reads Claude Code's docs can make this point.
- **Smallest change.** This is Alex's call. Option one: add "onFailure": "block" to the PreToolUse entry only, and only while a plan is in force. The refusal message must name `graphene init --remove`, because otherwise uninstalling graphene without removing the hook blocks every tool call. Option two: drop the word "before" from the claim wherever it appears.
- **Files.** ~/Desktop/AllThingsAgenticHackathon/src/graphene_map/hooks.py, ~/Desktop/AllThingsAgenticHackathon/dev/PRODUCT_THESIS.md

### 4. Claude Code's own plan mode isn't enforced in some sessions, and the docs say so

*medium; verified: yes*

- **Evidence.** code.claude.com/docs/en/permission-modes: "In interactive terminal sessions with bypass permissions available, Claude Code also doesn't enforce plan mode's blocks. Claude is still instructed to plan without editing, but a file edit or shell command it attempts during planning runs without prompting." CHANGELOG 2.1.299 (2026-10-14): "Added a one-time note when plan mode won't ask before most edits or commands because bypass permissions is available." Since v2.1.283, auto mode, where a classifier approves actions instead of the person, is the default starting mode.
- **Why it matters.** If Graphene's PreToolUse deny holds in those sessions, this is the clearest demo against the built-in: Claude's plan mode is an instruction, Graphene's is a refusal. It also matches what users ask for: "System-level enforcement" (claude-code issue #4452).
- **Smallest change.** Record one $0 check: start Claude Code with bypass available and plan-first on, ask for an edit, and see whether the hook refuses it. If it holds, that recording is the README's one comparison line. If it does not, say so.
- **Files.** ~/Desktop/AllThingsAgenticHackathon/README.md

### 5. The multi-agent dashboard is now built into Claude Code, so watch is not where Graphene can win

*medium; verified: yes*

- **Evidence.** code.claude.com/docs/en/agent-view: `claude agents` gives "a single screen for managing many background Claude Code sessions". Each session "moves into its own git worktree", and rows are grouped as "Ready for review, Needs input, Working, Completed" with a PR label that turns green when checks pass (research preview, n: filter needs v2.1.287). Conductor 0.90.0 (conductor.build) offers worktree workspaces, a diff viewer and merge. Vibe Kanban (28,367 stars) has been community-maintained since its company shut down on 2026-04-10, with a last push on 2026-09-19. claude-squad (8,607 stars) was last pushed on 2026-08-20.
- **Why it matters.** A free first-party list of agents with worktree isolation and PR status covers what most people mean by "control my agents". None of these screens shows a per-agent file limit or a check the tool ran. That gap is Graphene's, and a nicer list is not.
- **Smallest change.** In the README and the pitch, present `graphene watch` as "the plan and what each agent may touch", not as a dashboard. As a later idea (not tested), find out whether a leaf can run as a Claude Code background session so it appears in `claude agents`.
- **Files.** ~/Desktop/AllThingsAgenticHackathon/README.md

### 6. Closest prior art: a per-task file limit with deterministic checks already exists for the Pi agent

*medium; verified: yes*

- **Evidence.** scottspence.com/posts/coding-agent-harnesses-my-pi (2026-07-25): the harness.json contract sets an "editable scope", hooks "block edits outside the allowed paths" and "test changes that were not part of the task", "The scripts run deterministic validation and review", and "the diff must stop for human review before commit". It is published as npm @spences10/pi-harness. Ralon 0.1.7 (2026-08-28, docs.rs/crate/ralon) gives "kernel-enforced write protection driven by an agent.lock file" for nine agents, but as one static list, not per task.
- **Why it matters.** "Nobody does this" is false in general. The claim survives only as "the installable one for Claude Code, with a plan of several pieces, each with its own files and check". If the README says "the only", a stranger can refute it with one link.
- **Smallest change.** Scope the claim to Claude Code and to a plan with several pieces (see the claim artifact). Add my-pi and Ralon to the thesis's market table.
- **Files.** ~/Desktop/AllThingsAgenticHackathon/dev/PRODUCT_THESIS.md

**Not verified.**

- Whether Graphene's PreToolUse deny still refuses in a Claude Code session started with bypassPermissions or with bypass available. Claude Code's docs don't say, and I didn't run it.
- Devin's controls beyond org ACU caps (docs.devin.ai enterprise billing, via search snippet). Nothing found on plan approval or review before merge.
- Amp's permissions: only a third-party guide (verdent.ai, says it was checked 2026-08-25) claims Amp runs tools without approval by default. The official Amp manual wasn't read.
- Codex cloud's diff-to-PR flow and Cursor background agents opening PRs come from third-party blogs, not vendor pages.
- Roo Code and Claude Code subagents' per-agent tool limits were not researched.
- The 238/811 figure is GitHub search's count for the phrase "Claude modified files" among issues labelled model, not a hand count. A few may mention the phrase without choosing that category.
- Whether my-pi's harness handles several parallel tasks, each with its own scope, or checks shell-command writes afterwards. The post doesn't say.
- Entire's trail gates run on its server (from PR #2566's description). I didn't confirm whether they can run without an entire.io account.
- The Reddit quotes were read through a third-party mirror (reddit.sentinel-team.org), not reddit.com.
- Hacker News comments: my query to the Algolia API returned non-JSON, so no HN quotes are included.

## A stranger's first ten minutes from PyPI (`walk`)

I followed the README the way a stranger would, at no cost, in a scratch git repo created with mktemp -d. Everything went through `uvx --isolated` with a fresh uv cache and a scratch tool directory. Nothing was installed and nothing was written in the Graphene repo.

The software is fast and it works. The first run downloaded 13 packages and printed the version in 1.54 s; after that it took 0.11 s. `demo --once` took 0.46 s, the help pages 0.08 to 0.20 s, and the live demo plays in about 18 steps. The problems are all in the words and the order of steps:
- The README's first line needs a tool called uv. It never says what uv is or how to get it.
- The README never offers a way to try Graphene without installing it, although that way works.
- The demo is the only thing a stranger can see for free, and it speaks Graphene's internal event names.
- Plain `graphene` lists the setup step last, and it exits with an error code.
- The cost line the README promises is not in the demo.
- The README does not say what you need before you start: a git repo and a coding agent.

Caveat on this machine: uv was already installed and the network was fast. Without `--isolated`, uvx quietly reused Alex's own installed copy (0.22 s), so a true stranger's cold start may be slower than 1.54 s.

Answer to "does the README tell someone who has never installed uv what to do first": no. Line 12 is `uv tool install graphene-map` with nothing before it.


### 1. The first command needs uv, and the README never says what uv is or how to get it

*blocker; verified: yes*

- **Evidence.** README.md:12 is `uv tool install graphene-map`, with no line before it. grep finds no mention of uv's installer, pip, pipx, uvx or Python anywhere in README.md. In a clean shell (env -i PATH=/usr/bin:/bin zsh) that line printed `zsh:1: command not found: uv`, exit 127. The same clean shell has Python 3.9.6 and no `pip`, while pyproject.toml:12 needs `requires-python = ">=3.12"`. So the obvious fallback a beginner might try (pip with the Mac's built-in Python) is not there either.
- **Why it matters.** A non-engineer gets an error on the very first line and has nowhere in the page to go next. This is the worst stall, because nothing after it gets read.
- **Smallest change.** Add one line under README.md:12: 'No uv yet? Install it first (one command, link to uv's install page), then come back.' uv also installs the right Python, so this one link covers the Python problem too.

### 2. The README asks for a global install before letting anyone look; a no-install trial works and is fast

*high; verified: yes*

- **Evidence.** README.md:12-14 says to install first and then run `graphene demo`. The README never shows `uvx`. In a fresh cache, `uvx --isolated --from graphene-map graphene --version` printed `graphene 0.5.0` in 1.54 s on the first run and 0.11 s after that. `uvx ... graphene demo --once` finished in 0.46 s, needed no key, and left the toy repo untouched (git status was empty). `demo --help` says: 'The replay needs no key, no network and no Docker. Nothing in it runs.'
- **Why it matters.** Asking someone to install a tool on their computer before they have seen what it does loses the curious-but-careful people Alex wants. The free trial already exists; the README just never mentions it.
- **Smallest change.** Make the hero line `uvx --from graphene-map graphene demo` ('try it, nothing installed') and move `uv tool install graphene-map` down into 'Try it on your repo'.

### 3. The demo, the only thing a stranger can see for free, talks in internal event names

*high; verified: yes*

- **Evidence.** In the live demo (run in a pseudo-terminal), the bottom strip shows `usage · goal_proposed · friendly proposed`, `greet model · greet denied · farewell started · farewell attempt`, `greet released · greet usage`, `farewell check_passed`, `friendly rolled_up`. The status line shows `1 on you + 3 on the board`, `▶ ✓ 1 settled` and `1 came back`, and the help bar shows `Enter record` in the middle of a replay. `demo --once` ends with `the end of the run's log`: ISO timestamps, `run:stand-in`, and a cut-off check, `python3 -c 'i…`.
- **Why it matters.** The demo's best moment, Graphene stopping an agent that stepped outside the plan and sending the work back, appears only as the two words 'greet denied'. A beginner sees log noise instead of the reason to use the product.
- **Smallest change.** In the demo, replace the event strip with one plain sentence per step (for example 'the agent tried to edit a file outside its step; Graphene stopped it and sent the step back'). Drop the raw log from the end of --once.

### 4. Plain `graphene` lists the required first step last, and exits as if something failed

*medium; verified: yes*

- **Evidence.** Bare `graphene` in the toy repo printed: 'nothing is planned here yet. Say what you want to your agent, in a paragraph: it proposes the tree, and you prune it in `graphene watch`. Or `graphene ask '<what you want>'`. Before either, `graphene init` chooses who plans and who runs (until then, `ask` and `run` refuse)', exit code 1.
- **Why it matters.** A newcomer follows the first instruction ('say what you want to your agent'). Until `init` has run, that does nothing. 'tree' and 'prune' are not explained either.
- **Smallest change.** Reorder it: 'Start with `graphene init` (it asks which AI plans and which does the work). Then describe what you want…'. Exit 0, because an empty plan is not an error.

### 5. The same thing is called both a leaf and a node in the first ten minutes

*medium; verified: yes*

- **Evidence.** `demo --once` prints `2 leaves, 2 done` and then, two lines later, `next: nothing; every node is done`. `graphene --help` says '`graphene node show <id>` shows one node's record', and README.md:29, 39 and 56 say 'leaf'. Other words appear before anything defines them: `tree` (bare graphene, ask --help), `planner`/`executor` (init --help, README.md:38), `hooks` (README.md:29), `check` and `merge` (README.md:29), `worktree` and `vim keys` (--help), `board` (--help and the demo).
- **Why it matters.** A reader who is not an engineer cannot tell whether a leaf and a node are two things. Each undefined word is a small stall, and on this path they pile up. See the 'words' artifact.
- **Smallest change.** Pick one word for a unit of work and use it in the CLI output and in --help. Define plan, tree and leaf in a single sentence near the top of the README.

### 6. The cost line the README promises does not appear on the free path

*medium; verified: yes*

- **Evidence.** README.md:43: 'every run ends with one line: the agents' minutes and dollars, next to your own moves'. The live demo's last frame shows only `0 on you · 0 running · none ready · 2/2 done, finished · bill $0.0035`: no minutes, nothing about your moves. `demo --once` prints no cost at all.
- **Why it matters.** The README sells the meter as the thing Alex cares about most, but someone who only tries the demo never sees it.
- **Smallest change.** End the demo (both live and --once) with the same one-line summary a real run prints, or have README.md:43 say the demo shows only the bill.

### 7. 'Try it on your repo' never says what you need first: a git repo and a coding agent

*low; verified: yes*

- **Evidence.** README.md:51 says `cd your-repo` but never says it must be a git repository. Plain `graphene` run outside one printed 'run this inside a git repository (no .git found above the current directory)'. README.md:52 says `# claude or codex`, but never that you need one of them installed and signed in, while `init --help` lists 'claude, codex, nemotron or a command'. README.md:38 names 'Nemotron' with no explanation.
- **Why it matters.** Someone who is not an engineer may have no git repo and no coding agent. They discover each requirement only by hitting a refusal.
- **Smallest change.** Put one 'You need' line above the code block: a project folder tracked by git, plus Claude Code or Codex installed and signed in.

**Not verified.**

- A true stranger's cold start: this Mac already had uv and a fast network, and I did not measure the time to install uv itself.
- How long the whole live demo takes at default speed (12 s reached frame 6 of 18, uvx startup included).
- Whether a coding agent must be installed and signed in for `graphene init`: I did not run init, ask, run or watch.
- Whether `pip3` with the Mac's built-in Python 3.9 fails cleanly (I did not install anything; the failure is inferred from requires-python >=3.12).
- How the README renders on GitHub (pictures and dark-mode variants were not viewed).

## Launch kit facts (`launch`)

Lane: launch kit facts. I only read files and ran commands. Nothing was written to the repo; all scratch work went to $TMPDIR/scratch

The product story holds up, and `graphene demo` tells it well for $0. I ran the installed 0.5.0 under vhs. A 56-second tape plays 16 changes: the agent proposes a tree with a question, an assumption and a leave-out; the person narrows one leaf to app.py; that leaf comes back with "the word lives in words.py" and a `w widen` offer; it is widened and lands. This is enough for a 60 to 90 second video with no key and no spend.

Four things on the public face would make a stranger leave:
1. The PyPI page links its pictures by relative path, which PyPI does not serve.
2. The README never says what you need before step one: uv, Python 3.12 or newer, and Claude Code or Codex.
3. Two claims in WHAT_THIS_RUN_DID.md cannot be checked or contradict their own evidence: the "scan of 37 products" and the "7 of 8 / 8 readers" figures.
4. The replay shows dollar bills under "no model ran".

Six artifacts follow: claims, pitches, show-hn, video, objections, assets.


### 1. The PyPI page links all four README pictures and its doc links by paths PyPI does not serve

*high; verified: yes*

- **Evidence.** pyproject.toml:9 `readme = "README.md"`. `curl https://pypi.org/pypi/graphene-map/0.5.0/json` returns a description whose images are `docs/assets/graphene-mark-ivory.svg`, `docs/assets/graphene-mark-ink.svg`, `docs/assets/watch.gif` and `docs/assets/meter.svg`, and whose links are `dev/test/results-2026-09-23.md`, `docs/HOW_IT_WORKS.md` and `docs/HACKATHON.md`. All of them are relative paths.
- **Why it matters.** pypi.org is where `uv tool install graphene-map` sends people. With relative paths there, the logo, the GIF and the meter picture are probably broken images, and the three 'read more' links lead nowhere.
- **Smallest change.** In README.md, point the images at absolute raw.githubusercontent.com/Alex-lop/Graphene/main/... URLs and the links at absolute github.com/Alex-lop/Graphene/blob/main/... URLs, then publish the next release.
- **Files.** README.md, pyproject.toml

### 2. The README never says what a person needs before the first command

*high; verified: yes*

- **Evidence.** README.md:12 and :50 start with `uv tool install graphene-map` but nowhere say how to get uv. pyproject.toml:12 has `requires-python = ">=3.12"`, which the README does not mention. README.md:52 `graphene init  # claude or codex` is the only hint that Claude Code or Codex must already be installed and signed in for anything past the demo.
- **Why it matters.** For the broad audience Alex wants, step one fails with 'command not found: uv', and the page gives no next step. Someone without Claude Code finds out only at init.
- **Smallest change.** Add one line above the install: 'You need: uv (one-line install link), Python 3.12+, and Claude Code or Codex for real runs. The demo needs only uv.'
- **Files.** README.md, pyproject.toml

### 3. Two headline claims in the run's account cannot be checked or disagree with their own evidence

*medium; verified: yes*

- **Evidence.** WHAT_THIS_RUN_DID.md:17-18 says 'A scan of 37 products found none that does these'. `grep -rl "37 products"` finds only WHAT_THIS_RUN_DID.md; the scan itself is not in the repo. WHAT_THIS_RUN_DID.md:62 says 'median of 8 readers' and :127 says '7 of 8 factual questions'. dev/process/prove/after.md:50-54, the evidence that file says it copies, says '3 runs × 2 arms a build, one reader each', with record [7, 7, 8] against git [4, 5, 5], and :71 calls the comparison that counts '7 against 5'.
- **Why it matters.** These are the lines a launch post would quote. A stranger who follows the links cannot find the scan and sees a different reader count, which costs trust in every other number.
- **Smallest change.** In launch text, say 'on the same build, Graphene's record answered 7 of the ten questions where git log -p answered 5 (three runs, AI readers)', and either commit the 37-product scan or drop the 'only one' claim.
- **Files.** WHAT_THIS_RUN_DID.md, dev/process/prove/after.md

### 4. The README's GIF can only be re-recorded by spending money on a live run that may not repeat; a free, repeatable tape of `graphene demo` works

*medium; verified: yes*

- **Evidence.** The README's GIF, docs/assets/watch.gif, was last changed 2026-10-08 (commit b824b2b7). Its tape, dev/proof/terminal.tape, needs claude, tmux and the checkout's own .venv (line 24) plus dev/proof/try.sh (line 28). It hides fixed waits of 75 s, 150 s and 120 s (lines 42, 64, 82), and its header says it costs 'some cents'. A scratch tape running only `graphene demo` in an empty mktemp directory finished in about 2 minutes and wrote a 55.8 s, 500 KB GIF, with no key and no network.
- **Why it matters.** The established stale clock in the pictures cannot be fixed by anyone but Alex at a terminal, with spend, and a live planner that takes longer than 75 s breaks the take. A $0 replay tape can be re-cut on every release.
- **Smallest change.** Commit a dev/demo/replay.tape (the recipe is in the assets artifact) that films `graphene demo` with space and `.` stepping, and point the README picture at its output.
- **Files.** dev/proof/terminal.tape, docs/assets/watch.gif, README.md

### 5. The replay shows dollar bills right under 'no model ran'

*low; verified: yes*

- **Evidence.** In vhs screenshots of `graphene demo` (0.5.0), the top line reads 'replay · a scripted stand-in, no model ran'. The status line reads 'bill $0.0056', and the leaf pane reads 'bill $0.0001 at list price for this leaf's 3 calls · stand-in-Nano'. The recording's plan_meta names 'nvidia/Nemotron-3-Nano-fake' (src/graphene_map/demo.jsonl, line 2).
- **Why it matters.** In a video or GIF made from the demo, a viewer sees a cost for a run that the same screen says never happened. It reads as either fake or broken.
- **Smallest change.** When the recording says stand_in, show the bill as 'bill: none, a stand-in' (or leave the bill out), and never narrate the replay's dollars.
- **Files.** src/graphene_map/demo.jsonl

### 6. The README's words assume an engineer, and its first paragraph argues before it explains

*low; verified: yes*

- **Evidence.** README.md:25 is a 110-word belief paragraph that comes before any sentence saying what to do. README.md:29-39 use 'hooks', 'merge', 'check', 'executor', 'diff' and 'Codex' without saying what they are; 'hooks' is explained only at :60. The footer, :68, links 'Nemotron on Token Factory' with no context. README.md:51 `cd your-repo && graphene demo` suggests the demo touches your repo, but it runs anywhere: `graphene demo --once` in a non-git scratch directory exited 0.
- **Why it matters.** Alex wants broad appeal. A non-engineer meets six unexplained terms before the install block, and the comment on :51 makes the safe first step sound risky.
- **Smallest change.** Lead with three lines (what it is, a 20-second GIF, 'try it: graphene demo, it touches nothing'). Explain leaf, check and hook in one sentence each, move 'Why I built this' below the try block, and drop `cd your-repo &&` from the demo line.
- **Files.** README.md

**Not verified.**

- The rendered pypi.org page: the fetch returned a 3 KB bot-check page, so 'the images are broken there' is inferred from the relative paths in the JSON description, not seen.
- Whether a 'refused' row for words.py is visible in the replay's leaf record without scrolling (the log has a `denied` row; the screenshot showed the record only down to 'in scope app.py').
- The contents of the 37-product scan anywhere outside this repo (memory, another branch, Alex's notes).
- The full 84 s shot timings: I captured screenshots at changes 1, 2, 3 and 9 and at 6 s intervals of a 56 s run, but did not film the stepped version end to end.
- That `graphene direction` exists as a hidden command; it is only absent from `graphene --help`.
- How main's current words (Unreleased) look in the replay: everything I filmed was the installed PyPI 0.5.0.

## The crash test (`attack`)

Most of a crash-test demo already exists. Ran in-process against the real gate in a throwaway repo at $0 ($TMPDIR/scratch/probe.py, a scripted stand-in), Graphene's code refused or flagged each misbehaviour below except one, in about 1.8 s:
- writing a file outside the leaf: refused
- a shell redirect, or `sed -i`, outside the leaf: refused
- a script that opens the file itself: the hook let it through, then `done` refused it because git saw the change
- an attempted stop: refused
- `done` while the check fails: refused
- editing a test outside the leaf: refused
- the agent rewriting its own check (`plan.edit`): refused, only the person can do that

The one that got through: when the leaf's files include the test its own check runs (the shape gate.py:141-145 teaches agents to propose), the agent changed the test so it passed and `done` accepted it. Nothing in the log or in the record marks it. That should be fixed (flag it, not refuse it) before the demo is built, or the demo has to print "got through" for that move.

Proposed name: `graphene demo --cheat`. Size: one new module of about 110 lines, about 10 lines of CLI, about 12 lines in plan.finish, plus tests. The README terms used on screen are: leaf, its files, check, lands.


### 1. A leaf can rewrite the test its own check runs, and done accepts it with no warning

*high; verified: yes*

- **Evidence.** Scratch probe (scripted stand-in, real gate and plan.finish): leaf scope ['src/**','tests/**'], check 'python3 -m pytest -q tests/test_calc.py'. First done printed 'refused: n1 is not done: ... failed'. The stand-in then changed `assert add(2, 2) == 4` to `== 0` in tests/test_calc.py, and done printed 'DONE (accepted)'. Log kinds: ['added','started','stop_refused','check_failed','check_passed','finished']. node_record.render printed 'in scope: tests/test_calc.py' and 'check ... passed ... run by Graphene itself', with nothing saying the check's own file had changed. plan.py:2440-2470 (finish) never compares what changed with what the check runs. gate.py:141-145 (TEACH) tells every session to propose exactly this shape: 'scope: src/pdf/**, tests/pdf/**' with 'check: python3 -m pytest tests/pdf -q'. The limits list in docs/HOW_IT_WORKS.md:197-215 does not mention it.
- **Why it matters.** This is the most common way agents cheat: they make the test agree with the code. The README promises 'held by git and the check', and here the check is what got changed. A crash-test demo would have to print 'got through' for this move.
- **Smallest change.** In plan.finish, after the check passes: list the files at node.base_sha (git ls-tree -r --name-only), run plan.check_paths(node.check, those files, [node]), and keep the ones that are also in `changed`. Store them as detail['check_touched'] on the 'finished' row, print a line at done, and add one line to the record: 'its check runs tests/test_calc.py, which this leaf changed: read that diff'. Files that are new since the base are not flagged. Whether it also sends the leaf to REVIEW (a sign-off) is Alex's decision. About 12 lines in plan.py and 4 in node_record.py.
- **Files.** src/graphene_map/plan.py, src/graphene_map/gate.py, src/graphene_map/node_record.py, docs/HOW_IT_WORKS.md

### 2. Writes outside the repository are never limited, and the check runs with the person's full environment

*medium; verified: no*

- **Evidence.** gate.py:706-707: a write tool's path that `_rel` maps to None (outside the repo) gets `return None`, so nothing is said. tests/test_gate.py:226 asserts `bash(repo, "uv run pytest -q > /tmp/out.txt 2>&1") is None`. plan.py:847-851 check_env passes os.environ through, apart from the Nebius key. HOW_IT_WORKS.md:197-215 lists ignored paths, MCP and scripts, but not writes outside the repo.
- **Why it matters.** An agent could write a file outside the repo that the check's python3 or PATH then loads (for example a site-packages hook), and the check could pass on nothing. Git never sees that file, so done cannot catch it the way it catches a script that writes inside the repo.
- **Smallest change.** Add one line to the limits list in HOW_IT_WORKS: 'A write outside the repository is not limited by any leaf, and the check runs with your environment, so a file written there can change what the check sees.' No code change tonight.
- **Files.** src/graphene_map/gate.py, src/graphene_map/plan.py, docs/HOW_IT_WORKS.md

### 3. The refusal for a file outside the leaf reads as if the leaf's own file were the problem

*low; verified: yes*

- **Evidence.** plan.py:2328 builds the message as f"{node.id} is not done: changed outside its scope ({', '.join(node.scope)})". In the probe this printed 'n1 is not done: changed outside its scope (src/calc.py), which only the person widens | tests/test_calc.py'. src/calc.py is the leaf's own file; the file that broke the rule (tests/test_calc.py) only appears on the next line.
- **Why it matters.** This is the exact sentence a stranger would read on the crash-test screen, and it points at the wrong file.
- **Smallest change.** Name the stray file first: f"{node.id} is not done: it changed {stray[0]}{' and more' if len(stray) > 1 else ''}, outside its files ({', '.join(node.scope)})".
- **Files.** src/graphene_map/plan.py

**Not verified.**

- That a file written outside the repo (for example a sitecustomize.py in the user's site-packages) really makes a check pass. Only the gate's let-through was verified, from gate.py:706-707 and test_gate.py:226. I wrote nothing into the home directory to test it.
- The exact 25-line screen. It is a design built from the probe's real refusal reasons. No implementation exists.
- The FLAGGED line for move 7. It depends on the proposed finish change; today the same sequence gives 'DONE (accepted)' with no flag.
- That Claude Code itself turns these hook answers into blocked calls. The probe called hook_main in-process, as tests/test_gate.py does.
- How long the demo takes on a stranger's machine or on ubuntu CI. Only the 1.8 s scratch-probe run on this Mac was measured.
- That passing sys.executable as the check survives the clean-worktree check runner on every platform.

## A controller bench (`bench`)

Graphene already has most of what a "does it hold?" bench needs: isolated `claude -p` runs (dev/process/prove/common.sh), a $0 fake claude (prove/fake/claude), a spend ledger (ledger.py), scorers that diff git against intent globs (dev/test/tally.py) and a rules-before-numbers habit (prove/rules.md). Nothing is missing on the tooling side. Two things are, and they matter.

1. No task so far tempts the plain agent. In every earlier run, plain Claude Code wrote nothing outside intent: results-2026-09-20.md:104-107, results-2026-09-21.md:195, and X2 in prove/after.md:37 ("nothing outside the intent anywhere"). Those prompts listed the files to leave alone, and Sonnet obeyed. A bench built on those tasks can only return "no difference shown".
2. The fair opponent is not bare Claude Code. It is Claude Code given the same rule through its own deny settings. Graphene's real edge over that is structural: `done` refuses any change outside the leaf's scope, whichever way it was written (src/graphene_map/plan.py:2324-2328), and the executor's shell runs only `graphene node`/`graphene plan` commands (src/graphene_map/run.py:51-55). A plain session allowed `Bash(python3 *)` (x2_plain.sh:17) can write around a deny rule on Edit. Claude Code's actual behaviour here is not verified.

The design below uses three arms: plain (P), plain with deny rules (P+) and Graphene (G). It has four seeded tasks, where the only easy way to green runs through a file the agent should not touch. Each arm gets 5 runs a task, 20 in all. The rule is the repo's own: a difference counts only when Wilson 95% intervals do not overlap, judged G against P+. A $0 scripted layer of cheater, liar and honest stand-ins runs in CI and proves the scorers. The live cost is about $30 at list price (Claude Code's own total_cost_usd, as the ledger records it), with a $45 ceiling. With 20 runs an arm, a difference shows only if P+ trips at least 7 of 20 while G trips 0 (computed). The statements task is set aside, because its five traps are pre-registered for Alex as the person (dev/test/PREREG-statements.md), and a published stand-in result would contaminate those runs.


### 1. The plain agent has never tripped on existing tasks, so the bench could measure only a ceiling

*blocker; verified: yes*

- **Evidence.** results-2026-09-20.md:104-107 (zero outside intent in all six paragraph-arm runs); results-2026-09-21.md:195 (zero in all nine runs, both arms); dev/process/prove/after.md:37 (X2: 'nothing outside the intent anywhere', plain arm included). The feeds prompt names every file to leave alone (dev/test/tasks/feeds/paragraph.md, last lines), and Sonnet obeyed.
- **Why it matters.** Re-running the old tasks would give 0 against 0 and say nothing. A skeptic would also be right that tasks rigged to trip the plain agent are cherry-picked.
- **Smallest change.** Seed tasks where the only easy route to green goes through a file the agent should not touch. Put the rule in the repo (AGENTS.md/CLAUDE.md and a header comment), not in the prompt, and identically in every arm. Freeze the four tasks before the pilot. Never swap a task after a number exists. Report a task the plain agent passes cleanly as a finding; do not drop it.

### 2. Out-of-scope writes are zero for Graphene by construction when they are scored against the leaf's own scope

*high; verified: yes*

- **Evidence.** src/graphene_map/plan.py:2324-2328: done refuses 'changed outside its scope', so a landed leaf cannot carry an out-of-scope file. results-2026-09-20.md:182-186 already called this out: 'outside intent equals outside scope, which the hook enforces'.
- **Why it matters.** A G = 0 that the code guarantees is a tautology, not a measurement. The interesting failure is the planner putting the tempting file into a leaf's scope.
- **Smallest change.** Score every arm against the task author's intent globs, fixed before any run (as tally.py's --intent does), never against Graphene's scopes. Record separately whether a proposed scope named a forbidden path; NAMED in dev/test/tasks/statements/traps.py is the pattern.

### 3. Comparing against bare Claude Code is unfair: the arms differ in shell access and rules, not only in Graphene

*high; verified: yes*

- **Evidence.** src/graphene_map/run.py:52 restricts the executor's shell to 'Bash(graphene node *)' and 'Bash(graphene plan *)'. The plain arm in dev/process/prove/x2_plain.sh:17 allows python3, git, ls, cat and mkdir. tests/test_standing_gate.py shows Graphene enforcing protected and readonly paths, a rule plain Claude Code would get through permissions.deny.
- **Why it matters.** A skeptic will say a deny rule does the same job for free. If G is compared only with P, a win could come from the narrower shell rather than from Graphene.
- **Smallest change.** Add arm P+: plain Claude Code with the same rule as a permissions.deny in .claude/settings.json, plus the same allow list as P. Make claims only for G against P+. Report G against P beside it.

### 4. The two arms are scored from different records

*high; verified: yes*

- **Evidence.** dev/test/tally.py:8-14 reads .graphene/graphene.db and .graphene/runs/ for the Graphene arm and the run log for the other arm. Its own docstring (tally.py:16-30) lists three earlier miscounts, from double-counted churn and Bash change lists that left files out.
- **Why it matters.** A difference could come from the counting instrument rather than from the agent.
- **Smallest change.** Take primary metrics only from sources both arms share: git diff from base to main plus untracked files, and the hidden check run on the final tree. Take dollars and turns from each claude -p result's total_cost_usd and num_turns, as ledger.py already does.

### 5. Harness faults have already passed for results

*medium; verified: yes*

- **Evidence.** after.md:43-45: plant.sh's grep cut a command at a backtick, so 'the scores … are those of a repo whose planted fault was never fixed'. after.md:131-135: the stand-in's uv tool install replaced the machine's graphene, twice.
- **Why it matters.** A broken harness looks like an agent failure, and in a public bench a skeptic will find it first.
- **Smallest change.** Run every arm with FAKE=1 before the live runs. Write a void rule into rules.md: the harness exits non-zero, or the arm's first output line is missing. A budget cap counts as 'not done', never void. Publish the void count. Keep UV_TOOL_DIR and an origin-less clone per run (prove/rules.md:78-84).

### 6. Small samples can only show a large gap

*medium; verified: yes*

- **Evidence.** prove/rules.md:13-14: with n=3, only a full flip counts. Computed Wilson 95%: 0/20 has an upper bound of 0.16, so P+ must trip at least 7 of 20 for a difference to show; at n=10 it needs 6 of 10.
- **Why it matters.** Fewer than about 20 runs an arm cannot separate the arms unless the plain agent fails often.
- **Smallest change.** Pool 4 tasks x 5 runs = 20 per arm for each primary metric. Interleave arms in G, P+, P order on each seed, on the same day. Say before the runs that a result below 7/20 is published as 'no difference shown'.

### 7. The author wrote every task and every scorer

*medium; verified: yes*

- **Evidence.** results-2026-09-20.md:182-186: 'The tool's author designed the test'. dev/process/prove/x4.sh already runs a real repository's open issue (pytest-bdd #476) through Graphene.
- **Why it matters.** Home-made traps are the first thing a skeptic attacks.
- **Smallest change.** Tag the tasks, scorers and rules before the pilot (as statements-prereg-2 was). Add an x4-style real-issue run with its prompt unchanged as a fifth task, scored only on false done, and report it apart from the pooled count.

### 8. The model and Claude Code version drift between runs

*low; verified: no*

- **Evidence.** x2_plain.sh:15 and x4.sh:17 pass '--model sonnet', an alias, not a pinned model id.
- **Why it matters.** Arms run on different days could be compared across different models.
- **Smallest change.** Record `claude --version` and the result JSON's model id per run, and interleave arms by seed. A run whose model id differs from the frozen one is void.

**Not verified.**

- Whether Claude Code's permissions.deny on Edit/Write stops a write made through an allowed Bash(python3 ...) call. The P+ prediction depends on this and needs one scripted probe.
- Whether `claude -p --setting-sources project,local` loads CLAUDE.md/AGENTS.md, so that the in-repo rule reaches the P and P+ arms. Check this in the pilot.
- Whether the total_cost_usd dollars are cash or subscription quota on Alex's account.
- The per-run costs for the new tasks. The $0.353 and $0.533 figures were measured on feeds with two rounds and are only upper-bound estimates.
- Whether the Graphene planner writes a full-suite check on T3. No prediction is made.
- The flaky test's real failure rate under Graphene's clean worktree. The ~30% is a design target, not a measurement.
- No live or scripted run of this bench was made; everything above is design. The only numbers here are quoted from the repo's ledger and after.md, plus Wilson bounds I computed.
