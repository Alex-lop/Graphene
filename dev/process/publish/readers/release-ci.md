# release-ci: why CI on main is red, what else is flaky, and what 0.6.0 needs

**The fixes are committed** on branch `release-ci` in `<scratch>/agents/release-ci`, four commits on top of 921834de. Nothing was pushed.
- `8f7f0242` A check gets no terminal. This fixes the macOS run stopping itself, which is the red CI.
- `ce8ae711` Two races that a loaded runner loses: the leaf order in test_land_moved, and the cockpit's timer firing after the app has closed.
- `15a2c3e1` 0.6.0: the version, uv.lock and the CHANGELOG. 0.5.1 is marked as never published.
- `95174fd2` RELEASING.md: what to do when a release run fails before the upload.

Pick them with `git -C <tree> fetch <scratch>/agents/release-ci release-ci && git cherry-pick 8f7f0242^..95174fd2`. The last two commits can be dropped if Alex wants a different version.

## 1. The failing test is a real macOS product bug (severity: high)

**Where it failed.** CI run 39132573456, macos-latest with Python 3.14, `test_nothing_graphene_starts_outlives_its_terminal[it closes saying nothing]`, at tests/test_teardown.py:135. The log I read with `gh run view --log-failed` truncates `said`, so it cannot tell which of the three conditions was missing.

**Reproduced.** I ran 8 copies of the `window=False` case with `-n 12`: **8 of 8 failed**, all at once, and that was without a CPU hog. Running 8 copies one after another, they all passed. The `window=True` copies all passed. I added logging to the run, and every failing run had stopped itself with exit 130 about 0.7 s after it started. The store's log said: `run stopped: nothing was finished`.

**Root cause.** `terminal_closed()` (src/graphene_map/plan.py:719) returned true while the terminal was still open. `os.write(1, b"")` was raising `OSError(5, EIO)`. I traced the run's subprocesses and the run's first EIO, logging every 5 ms:
```
0.177 subprocess.Popen /bin/bash -c 'command -v sleep'   (the run's precheck, via plan._ended)
0.183 subprocess.Popen /bin/bash -c 'sleep 97'
0.187 EIO [Errno 5] Input/output error
```
I then took Graphene out of it with a standalone script, `release-ci-scripts/eio2.py`. Its child is in its own session, on a pty with no controlling terminal, and starts a grandchild with `start_new_session=True` and the terminal inherited as stdin:

| grandchild | the child's write after the grandchild exits |
|---|---|
| bash | **EIO** |
| sh | **EIO** |
| sleep | ok |
| python | ok |
| bash with stdin=DEVNULL | ok |
| bash without a new session | ok |

So on macOS, a bash that leads its own session and is handed a terminal no session holds takes that terminal as its controlling terminal. When it exits, the kernel revokes the terminal, and every process still writing to it gets EIO. `plan._ended` is the only place that starts a session leader and lets it inherit stdin. `_ended` runs every check and every git step of a check. So:
- Whenever `graphene run` or `graphene node done` is on a terminal that is not its own session's, the first check ends the terminal. That covers the test's `window=False` case and any agent harness that hands over a pty without making it the controlling terminal.
- The watcher thread started by `ctrl_c_on_hangup` reads the EIO as "the terminal closed" and stops the run.

**Why the test usually passed.** `up()` tends to see the `sleep 97` check before the watcher's first tick at 0.5 s. The test then closes the terminals, and the run is already gone. So it passed for the wrong reason, and failed on a slow runner when the check showed up after the tick.

**Fix** (commit 8f7f0242): checks get /dev/null as stdin. This is deterministic, not a longer wait.
```diff
--- a/src/graphene_map/plan.py
+++ b/src/graphene_map/plan.py
@@ -755,7 +755,9 @@ def _ended(
-        stdin=None if given is None else subprocess.PIPE,
+        # never the terminal: on macOS a bash in a session of its own takes a terminal no session holds
+        # as its own, and its exit revokes it, so the run's next write failed and it stopped itself
+        stdin=subprocess.DEVNULL if given is None else subprocess.PIPE,
```
- **Teardown test made strict.** After the 1 s settle, the test now asserts that demo, watch and run are all still running, before it closes their terminals.
- **New test:** `test_a_check_leaves_the_terminal_it_was_run_under_open`. It runs `plan.run_check('true', …)` under such a terminal, then calls `terminal_closed()`.
- **Without the fix, both tests fail every time on an idle Mac.** With it, both pass.
- **Under stress:** 8 copies of tests/test_teardown.py with `-n 12` and 12 `yes` hogs gave 32 passed.

## 2. Other tests that depend on timing

### Full suite runs in my clone
All runs used `GITHUB_ACTIONS=true` and `TMPDIR` under my agent directory.

| run | flags | result | failures |
|---|---|---|---|
| 1 | -n 10, fix 1 applied | 2199 passed, 1 failed, 328 s | test_cli |
| 2 | -n 10 | 2198 passed, 2 failed, 357 s | test_cli, **test_land_moved.py:252** |
| 3 | -n 14 | 2198 passed, 2 failed, 285 s | test_cli, **test_land_moved.py:252** |
| 4 | -n 14 with 16 CPU hogs, land_moved fix applied | 2198 passed, 2 failed, 358 s | test_cli, **test_cockpit_replay NoMatches** |
| 5 | -n 10, all 4 commits | 2199 passed, 2 failed, 295 s | test_cli, test_plan stale-worktree (both environment-only) |

**Environment-only failures** (not CI problems): `~` is a git repo (`~/.git` exists), and my TMPDIR is under home.
- `test_cli.py:166 test_commands_refuse_to_run_outside_a_git_repo` gets "refusing to treat your home directory as a repo". It failed in every run.
- `test_plan.py:497 test_a_stale_worktree_git_can_no_longer_read_stops_nothing` sees the stale directory as dirty files of the home repo (`.CFUserTextEncoding`, …). It failed in run 5 and in all 3 stress copies.

On CI, TMPDIR is under /var/folders. A minor product edge case remains: a person whose home is a dotfiles git repo, with a stale worktree directory under home, would hit the second one. Not checked further.

### Ranked by risk

1. **Fixed: tests/test_land_moved.py:252, `test_a_check_already_red_on_the_target_is_not_held_against_the_next_leaf`** (high). It failed in 2 of 3 full runs. It also failed in 3 of 6 copies under a hog, while the fixed file passed 3 times, 66 of 66 each time.
   - **Cause:** the "slow" leaf's executor slept for 1 s or 2 s so that it would land second. The first leaf's landing took longer than that, and `b attempt 1: the executor ended` came before `c started`.
   - **Fix** (ce8ae711): the slow leaf waits until `git rev-list --merges --count HEAD` in the checkout reaches `GRAPHENE_AFTER` (default 1, and 2 for this test), with a 60 s limit. This covers every `slow=` test in the file: lines 96, 114, 146, 245, 262, 283 and 294.
2. **Fixed: tests/test_cockpit_replay.py `test_i_opens_everything_about_the_leaf_that_came_back_in_a_replay_too`** (medium, and the same bug exists in the product). It failed once under the hog with `NoMatches: No nodes match '#bar'` at cockpit/app.py:166, raised from the `look` interval.
   - **Cause:** Textual's `_shutdown` sets `_running = False` before it removes widgets. `Cockpit.look` had no `is_running` guard. The classic watch's `refresh_plan` (tui.py:935) and the replay's `play` already have one.
   - **Fix:** the same guard in `look` and in `Details.refresh_pane`.
   - **New test:** it calls `app.look()` after `run_test` has exited. Without the fix it raises the exact NoMatches; with the fix it passes.
3. **Historical failure, not reproduced: tests/test_parallel.py:175 `test_more_leaves_than_workers_every_one_lands`.** It failed once on CI (run 38319558772, macOS 3.14, 12 Oct) with a "refused" or "did not land" line. I ran 6 copies with -n 14 and 16 hogs, twice: no failures.
4. **Historical failure, not reproduced: tests/test_precheck_core.py:72.** It got `not-run` instead of `outside` once on CI (run 37912644386, macOS 3.12, 9 Oct). The log does not say why: it was either the check timing out or not being runnable. Not checked further.
5. **Fixed sleeps or tight limits that passed under stress** (low to medium; I ran 3 to 6 copies of each under the hog):

   | location | what it relies on |
   |---|---|
   | tests/test_board.py:420 | `sleep(1.5)` for the recorder to pick up `board take` |
   | tests/test_run_cap.py:204 | `sleep(1.5)`, "its worker waits in take()" |
   | tests/test_run_meter.py:161, 187, 221 | a 0.6 s heartbeat against an executor that lasts 1.5 to 2.5 s |
   | tests/test_gate.py:394 | `< 1.0` s for a 400 KB command |
   | tests/test_hooks.py:329 | `< 2.0` s against a 0.25 s lock budget |
   | tests/test_tui.py:594 | `< 10` s, with a subprocess timeout of 12 s |
   | tests/test_init.py:319 | `< 10` s |
   | tests/test_plan_text_cli.py:156 | `< 20` s |
   | tests/test_cockpit_read.py:109 | clock within 5 s |
   | tests/test_plan.py:955, 975 | `sleep(2)` before asserting a negative; this can only pass wrongly, never fail wrongly |

   The files run_live, demo, tui, all cockpit_*, talk, hooks, gate, init, plan, demo_replay and views: 1680 tests passed under the hog. The 9 failures in that run were copy artifacts: test_demo and test_demo_replay read files relative to `__file__`, and the test_plan one is the home-repo issue above.

## 3. What 0.6.0 needs

- **PyPI.** `curl pypi.org/pypi/graphene-map/json` says version 0.5.0, releases ['0.2.0', '0.5.0'].
- **Why the v0.5.1 Release run failed** (38970158201): the test legs failed on Typer's forced colour (test_help_budget.py:75, test_plan_cli.py:349, test_views.py:537). The tag is on 3bb075a6. That colour problem is fixed on main by the conftest autouse fixture.
- **Decision: skip 0.5.1 and release 0.6.0.** Leave the v0.5.1 tag where it is. Moving a public tag is worse than skipping a number.
- **Commit 15a2c3e1** sets `version = "0.6.0"` in pyproject.toml:7 and `__version__ = "0.6.0"` in src/graphene_map/__init__.py:3, and `uv lock` updated uv.lock from 0.5.1 to 0.6.0. No test pins the version. The CHANGELOG changes:
```diff
-## Unreleased
+## 0.6.0
+
+The first release on PyPI since 0.5.0: it holds everything under 0.5.1 below (never published) as well as this.
 ...
+- On macOS, `graphene run` on a terminal that is not its session's own (an agent's pty) no longer stops itself
+  half a second in: its check's bash took that terminal and revoked it as it exited. A check gets no terminal.
+- The cockpit no longer fails on a tick that lands while it closes (`NoMatches: #bar`).
 ...
-## 0.5.1 (14 October 2026)
+## 0.5.1 (tagged 16 October 2026, never published)
+
+The v0.5.1 tag's release run failed its tests (help text on GitHub's runners, which force colour), so nothing
+was uploaded, and PyPI went from 0.5.0 to 0.6.0. What follows is in 0.6.0.
```
  0.6.0 has no date. Alex adds it when he tags.

### Wheel and smoke checks
**Wheel contents** (`unzip -l`): 61 `.py` files, including all 14 cockpit modules, plus `graphene_map/demo.jsonl` (44,330 bytes). The cockpit has no `.tcss` or other data files: `find src -type f ! -name '*.py'` finds only demo.jsonl.

**Smoke tests**, each in a clean `uv venv` outside the source tree:

| Python | what I ran | result |
|---|---|---|
| 3.12 and 3.14 | `graphene --version`, `graphene demo --once` | rc 0 |
| 3.14 | `graphene demo --cheat` (what the publish job runs after the upload) | "6 refused, 1 flagged, 0 got through", rc 0 |
| 3.14 | the cockpit `graphene demo` on a pty for 6 s, then `q` | exits 0, no traceback |
| 3.12 | `graphene watch` in an empty repo | exits 0 on `q` |
| 3.14, after the bump | 0.6.0 wheel: `graphene 0.6.0`, `graphene-map --version`, `demo --once` | ok |

**twine** (`uvx twine check dist/*`): PASSED for both the 0.5.1 and the 0.6.0 wheel and sdist.

## 4. Anything else that could break the release or a fresh install

- **The dependency floors work.** pyproject asks for `typer>=0.15`, `rich>=13`, `textual>=8.2`.
  - With typer 0.15.0, textual 8.2.0 and rich 14.2.0 on 3.14 (rich 14.2 is the lowest textual 8.2.0 accepts), `--version`, `demo --once` and the cockpit all ran.
  - So `rich>=13` is never the bound that actually applies, which does no harm.
  - With every transitive dependency at its lowest (`--resolution lowest`), typing_extensions breaks on 3.14 ("type 'typing.TypeVar' is not an acceptable base type"). No real resolver picks those versions.
- **Flaky tests block publishing.** `publish` needs all six test legs (release.yml calls ci.yml), so one flaky leg blocks the upload. That is why the three fixes above matter for the release itself.
- **Node 20 warning, not a failure.** actions/checkout@v4, astral-sh/setup-uv@v6 and upload/download-artifact@v4 are being forced onto Node 24. Bumping their major versions would remove the warning. I did not change it because I could not verify the newest tags offline.
- **Python 3.14:** the only warning is in a test. test_sizing.py:101 uses `multiprocessing.get_context("fork")` in a threaded process. Nothing in `src/` forks.
- **The sdist is 3.9 MB** and contains all of `dev/` (437 files), `tests/` and the docs images. It harms nothing, since the repo is public. To slim it, add `[tool.hatch.build.targets.sdist] exclude = ["dev"]`. I did not make that change.
- **The Release build job** smokes only `graphene --version`. That is acceptable: the CI legs it calls also run `demo --once` from the wheel.

## Scripts and logs
- **Scripts** in `<scratch>/agents/release-ci-scripts/`:
  - `runpty.py`: N runs on ptys without a controlling terminal.
  - `eio2.py`: the bash/EIO isolation.
  - `ptyshot.py`: drives a TUI on a pty.
  - `suite.sh`
- **Logs** in `<scratch>/agents/release-ci-tmp/`:
  - full suite runs: `suite1.log` to `suite3.log`, `suite4-hog.log`, `suite5.log`
  - stress runs: `zz1.log` to `zz3.log`
  - CI logs: `ci.log`, `rel.log`, `hist/*.log`
