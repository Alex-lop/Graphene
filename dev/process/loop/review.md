# The review of the dogfood's code

Two skeptics a leaf, read-only, on what the Sonnet executors landed for lanes 1 and 2 (one for correctness, one for fit to
the leaf's contract and the directive's words), started at 00:48 while `wire` still ran. 44 findings, many the same
fault seen from both sides; 13 distinct real ones, each fixed with a test; the rest left, and why. Three the review
did not find were found by the runs first: after `r` a leaf that already waited on the owner still read as came back
(`f7a9697`); the first rule flagged almost every statements leaf (`9e38e71`); and the precheck's checks outlived a closed
terminal (`7ce64e4`, the suite's own finding).

| # | lens | severity | finding | where | fixed or left |
|---|---|---|---|---|---|
| 1 | r-told:directive | medium | A reopen note that starts with '-' breaks every Claude Code attempt | `run.py:343` | fixed: 49297e6 (`--` before the prompt for Claude Code) |
| 2 | r-told:directive | low | run.py adds two sentences where the contract asked for one | `run.py:354` | fixed: 49297e6 (one sentence) |
| 3 | r-told:directive | low | The tests leave several contract sentences unproven | `test_told_first.py:20` | left: the tests cover the contract's sentences by the lines the executors read; not every sentence has a test of its own |
| 4 | r-told:directive | low | `node start` still prints the notes under the contract | `plan_cli.py:1266` | fixed: 49297e6 (`node start` says the note first) |
| 5 | r-told:directive | low | Executor SYSTEM changed but PROMPT_VERSION is still 1 | `executor.py:47` | fixed: 49297e6 (PROMPT_VERSION 2) |
| 6 | rows:directive | high | The leaf's own ruff command fails (E501 at line 34), so CI's ruff step fails too | `test_r_rows.py:34` | fixed: 49297e6 |
| 7 | rows:directive | medium | The precheck mark lands after the state word and moves that row's id and word columns two cells left | `tui.py:646` | fixed: 49297e6 (the mark sits after the title, in its room) |
| 8 | rows:directive | medium | x on a came-back leaf that offers r still says "r runs it again", and the help still says r runs | `tui.py:1880` | fixed: 49297e6 (x says r reopens the owner; the help lists r) |
| 9 | rows:directive | low | A done leaf keeps the mark and the line "e edits the check", but e is refused on a done leaf | `tui.py:2307` | fixed: 49297e6 (an open or proposed leaf only) |
| 10 | rows:directive | low | With several owners, the r row names the leaf by its id inside its own pane | `tui.py:2397` | left: the pane's `_its` reads `; x waits on it`, not `them`: the id shows once with several owners; a word |
| 11 | rows:directive | low | No test shows w, b and r together, and none proves the last precheck row wins | `test_r_rows.py:14` | left: w, b and r together are in the live transcripts (lane1-evidence.md); the last precheck row wins by construction |
| 12 | rows:directive | low | The precheck() docstring is one long it/its sentence, and the comment at line 821 is wrong for outside | `tui.py:2256` | left: house style in a docstring |
| 13 | precheck-core:directive | high | The extra's said() raises KeyError on a kept core 'outside' row, so `graphene plan precheck` crashes | `precheck.py:230` | fixed: 49297e6 (the extra's words gain outside) |
| 14 | precheck-core:directive | medium | 'outside' flags a right red whenever the command also names a tracked file outside the scope | `precheck.py:103` | fixed: 9e38e71 (outside is the failure's cause) |
| 15 | precheck-core:directive | medium | The extra still runs, judges and logs accepted checks itself instead of calling the core | `precheck.py:26` | left: the extra's `plan precheck` (hidden) keeps its own loop for accepted leaves beside the sandbox fork; the core is what `graphene run` calls, as the directive asks |
| 16 | precheck-core:directive | medium | Ctrl-C during the core precheck waits for every running check to finish | `precheck.py:151` | fixed: 7ce64e4 (end_checks under the hangup handling) |
| 17 | precheck-core:directive | medium | The core cuts the output before hiding it, so a key fragment or a partial path is stored | `precheck.py:126` | fixed: 49297e6 (hidden before it is read or cut) |
| 18 | precheck-core:directive | medium | The contract's whole-suite test is missing, and reading paths from the output is untested | `test_precheck_core.py:61` | fixed: fa0ddc7 (the whole-suite test, by the output) |
| 19 | precheck-core:directive | low | The wall-time test passes even when run() never measures the time | `test_precheck_core.py:113` | left: the wall time is read from the run's own clock; a stand-in that runs nothing takes 0 s |
| 20 | precheck-core:directive | low | Unrequested rule: a directory that holds the leaf's own scope counts as its own, and nothing tests it | `precheck.py:112` | left: a directory that holds the leaf's own scope is its own: `pytest tests/` with tests/test_x.py in scope is not outside; untested |
| 21 | precheck-core:directive | low | Docstrings use the house style the cut directive retires; the header says '1 checks' | `precheck.py:3` | left: house style; `1 checks` is fixed |
| 22 | r-offer:correctness | high | r can create a dependency cycle: reopen(for_leaf) adds needs without the acyclic guard the n offer uses | `plan.py:2719` | fixed: 49297e6 (acyclic: no r, and reopen refuses) |
| 23 | r-offer:correctness | medium | done_owners counts a done prompt-made aside (scope **) as the owner: it hides the real owner, and r reopens an open ** leaf for agents | `plan.py:1404` | fixed: 49297e6 (an aside is no owner) |
| 24 | r-offer:correctness | medium | The r row's command is printed unquoted by node show and the plain plan line, so it cannot be pasted | `plan_cli.py:1408` | fixed: 49297e6 (shlex.join) |
| 25 | r-offer:correctness | low | offers() offers r again once the reopened owner is done, so node show tells a ready leaf it came back | `plan.py:1478` | fixed: 49297e6 (offers only while it came back) |
| 26 | r-offer:correctness | low | r reopens a done owner of a path a live leaf now holds, leaving two open writers of one path | `plan.py:1478` | fixed: 49297e6 (a path a live leaf holds is its) |
| 27 | r-offer:correctness | low | A repeated id in reopen's list is reopened twice and its note is logged twice | `plan.py:2700` | fixed: 49297e6 (an id named twice is one) |
| 28 | r-offer:correctness | low | No test checks that r comes before n: moving r after n still passes | `test_reopen_offer.py:36` | left: r's place in the list is pinned by the live transcripts |
| 29 | r-told:correctness | medium | A note that starts with '-' is now the first text of the executor's last argv, which option parsers read as a flag | `run.py:343` | fixed: 49297e6 |
| 30 | r-told:correctness | low | Executor SYSTEM changed but PROMPT_VERSION stays 1, so prompt version 1 now names two system prompts | `executor.py:47` | fixed: 49297e6 |
| 31 | r-told:correctness | low | `graphene node start` still prints the note under the contract as 'sent back with:' | `plan_cli.py:1265` | fixed: 49297e6 |
| 32 | r-told:correctness | low | The run.py prompt gains two sentences where the goal asks for exactly one | `run.py:355` | fixed: 49297e6 |
| 33 | precheck-core:correctness | high | Ctrl-C during the parallel precheck does not stop the checks: the run waits until every running check finishes (up to CHECK_TIMEOUT, 1800 s) | `precheck.py:151` | fixed: 7ce64e4 |
| 34 | precheck-core:correctness | medium | 'outside' fires on every check that names a passing regression test file, though the check fails on the leaf's own missing file (5 of 5 leaves of this plan) | `precheck.py:110` | fixed: 9e38e71 |
| 35 | precheck-core:correctness | medium | Core and extra share one precheck-row cache across two verdict vocabularies: a core 'outside' row crashes the extra with KeyError, and other rows mask each runner's verdicts | `precheck.py:230` | fixed: 49297e6 (the words; one runner's rows a verdict) |
| 36 | precheck-core:correctness | medium | Open sub-goals' integration checks are run at base and flagged 'outside' for naming their own children's files | `precheck.py:134` | fixed: 49297e6 (leaves only: a sub-goal's check runs when its leaves are done) |
| 37 | precheck-core:correctness | medium | The spec's whole-suite case is untested: removing the output-line reading from _outside leaves every core test green | `test_precheck_core.py:61` | fixed: fa0ddc7 |
| 38 | precheck-core:correctness | low | A red's why is cut to 200 characters before it is hidden, so part of a key-shaped word survives (the extra hid the whole text first) | `precheck.py:126` | fixed: 49297e6 |
| 39 | precheck-core:correctness | low | A check that could not be run or timed out is stored as a finished 'red' and is never retried at that commit | `precheck.py:66` | fixed: 49297e6 (not-run: tried again next time) |
| 40 | rows:correctness | medium | ruff check fails on tests/test_r_rows.py:34 (E501), so CI's first step fails | `test_r_rows.py:34` | fixed: 49297e6 |
| 41 | rows:correctness | medium | node show and the plain plan print give the r command unquoted, so it cannot be pasted (plan_cli.py, outside the rows scope) | `plan_cli.py:1408` | fixed: 49297e6 |
| 42 | rows:correctness | low | The ∅ mark shifts a flagged row's id and state columns two cells left and goes after the state word, not after the id or title | `tui.py:646` | fixed: 49297e6 |
| 43 | rows:correctness | low | A sub-goal with a check gets a precheck verdict and the ∅ mark, but its pane never explains it | `tui.py:942` | fixed: 49297e6 |
| 44 | rows:correctness | low | x on a came-back leaf still says 'r runs it again' when r reopens the owner; the help lists only w b n | `tui.py:1880` | fixed: 49297e6 |
