# The before numbers, taken on 907a7d0 (`$A`)

Every number here was taken with a script under `dev/process/prove/` on the wheel built from 907a7d0, installed
into its own tool directory, before any change. The same scripts run on the branch in `after.md`. No human is
measured anywhere in this file: every planner, executor, walker and reader is a Sonnet session.

## X4: pytest-bdd issue #476 through the tree (n = 1, a fact)

`x4.sh`, 2026-10-10 16:30Z, repo pinned at 0e04014f, `uv sync` then the venv first on PATH, the planner Sonnet
through `--with`, the executor 907a7d0's DEFAULT_WITH plus `--model sonnet --max-budget-usd 2 --strict-mcp-config
--setting-sources project,local`, `run --parallel 2`.

| measure | 907a7d0 |
|---|---|
| ask: proposal by first answer | yes (23 s, $0.0718, 5 calls) |
| the tree | 1 sub-goal, 2 leaves (`tags-output` needs → `tags-tests`), 2 board items (a question with two options and `then:` lines; a risk with a `then: check` line) |
| checks written | 3 × `python3 -m pytest …`; 0 × `uv run` |
| red first | `tags-output: its check passes at the base commit 0e04014: it proves nothing` (its check is the existing reporter test file); `tags-tests` red (its test file does not exist yet) |
| editable install reaches everywhere | yes: with the venv first on PATH, `python3 -c 'import pytest_bdd'` from `/tmp` imports `repo/src/pytest_bdd/__init__.py`; and pytest-bdd is a pytest plugin loaded from the installed distribution, so a check in a clean worktree runs the checkout's plugin code |
| run | both leaves landed on their first attempt, 53 s, $0.1936 (13 calls); `width 1 of 2`; no hand-back |
| the repo's own suite afterwards | 148 passed in 8.86 s (146 before: the two new tests) |
| the issue's ask, as a judgement | the tags line is printed in both `-v` and `-vv` branches when a scenario has tags, with a README note and a CHANGES entry; not reviewed against #807's reference diff |
| total | 87 s wall, $0.2654 at list price |

What a stranger would meet here on 907a7d0: the run printed the red-first warning and started the leaf anyway (a
warning, by decision); nothing said that the venv's python would test the checkout rather than the leaf's tree;
the bill line read `you 0 acts, 0 min` after the person had accepted the tree; `plan record` gave coverage and the
bill but no landed shas, and `git log` carries two merges with empty bodies.

## X5: the editable-install hole, no model (three combinations, each a fact)

`x5.sh`, 2026-10-10 16:45Z. A src-layout fixture (`pyproject`, `src/pkg`, `tests/`) installed editable by `uv sync`;
leaf `a` owns `src/pkg/__init__.py` with the check `python3 -m pytest -q tests` (it names `tests/`, outside its
scope); leaf `b` owns `src/pkg/b.py` and `tests/test_b.py` with the check `python3 -m pytest -q tests/test_b.py`. A
fake executor breaks the leaf's function in its worktree and calls `done`.

| combination | red first said | `pkg` imported from, in the worktree | `b` (broken) landed | attempts |
|---|---|---|---|---|
| `python3 -m pytest`, no pytest on PATH | `a: its check names tests, outside its scope`; `b`: red, `No module named pytest` (the gist is kept in the log row only) | nothing: no pytest | no: `b came back after 3 attempts`, each refused with the same `No module named pytest` | 3 |
| `python3 -m pytest`, the fixture's `.venv/bin` first on PATH | `a` and `b`: `its check passes at the base commit: it proves nothing` | the checkout, for both leaves | **yes** | 1 |
| `uv run pytest`, the same PATH | the same two lines | its worktree, for both leaves | **yes** | 1 |

Two holes, then, on 907a7d0, and the run said nothing about either:

1. **The editable install.** With the venv first on PATH, `python3 -m pytest` in the clean worktree imports `pkg`
   from the checkout, so the check never saw the leaf's broken function and `b` landed.
2. **The copied index.** Under `uv run pytest` the worktree's own `pkg` was imported, and `b` landed anyway. The
   clean tree is built from a copy of the worktree's index, dated when it is copied; git then trusts every entry's
   stat data, and an edit of the same size made in the second the file was written out reads as the committed
   file. Reproduced outside Graphene in `dev/process/prove/probes/racy.md`: commit, edit the file in the same second
   keeping its size, copy the index with a later date, `git add -A` on the copy writes the committed content; dating
   the copy at epoch+1 makes every entry racily clean and the content is read (a zero date disables git's racy
   check; `git update-index --really-refresh` does not help). The executor's own `done` passed on the committed file
   (b's one check row, `check_passed`; its log: "b is done (check passed, …)"), and the leaf landed broken.

## X1: the first ask (n = 40: feeds 20, report 20)

`x1.sh`, 2026-10-10 16:45Z, the planner `claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format
stream-json --verbose --model sonnet --max-budget-usd 1.5 --setting-sources project,local`, two tries as shipped, four
asks at a time, each in a fresh `make_task.py` repo as the person.

| measure | feeds (20) | report (20) | all (40), Wilson 95% |
|---|---|---|---|
| proposals by ask | 20 of 20 | 20 of 20 | 40 of 40 [0.91, 1.00] |
| proposals by first answer | 20 of 20 | 20 of 20 | 40 of 40 [0.91, 1.00] |
| asks lost | 0 | 0 | 0 of 40 [0.00, 0.09] |
| first refusals, by class | none | none | none |
| `repaired:` lines; leaves sharing a check | 0; 0 | 0; 0 | 0; 0 |
| checks by runner | unittest 61, pytest 3, other 7 | unittest 18, pytest 21, other 1 | unittest 79, pytest 24, other 8 |
| median seconds; median planner dollars | 38.0; $0.108 | 17.5; $0.050 | 26.5; $0.077 |

**The A1 gate, by the rule written before the run: the schema planner is deferred.** Not one of 40 Sonnet asks was
refused on 907a7d0, so there is no first-refusal class for a schema to reach. The loop night's loss (1 of 4 on the
account's default model, before c4bb66d sent every fault back at once) is not what Sonnet does here on these two
tasks. The record's 37 first refusals and 15 lost asks were Nemotron Ultra's, already on the schema. What A2 and A3
still fix is the dead end when a refusal does happen: the kept proposal, the next step, every fault at once.

## X2 (b) and (c): the plain session and `/batch` on feeds, build-independent (n = 3 and n = 2)

`x2_plain.sh` and `x2_batch.sh`, 2026-10-10 16:46Z. Each session: `claude -p --model sonnet --permission-mode
acceptEdits --allowedTools Read Edit Write Glob Grep 'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)'
--output-format json --max-budget-usd 3`, the isolation flags, the feeds paragraph (prefixed `/batch ` for (c), with
`Agent Task EnterWorktree ExitWorktree` allowed and a $5 cap); the harness commits the session's uncommitted change
as one commit, plants `code`→`xcode` in `normalize/fields.py` as the person, and sends the one follow-up sentence
("I broke something after your change: XML records now come out empty. Find it, fix it in the file that owns it, and
say why.") with `--resume`.

| run | accept | held-out | the six untouched | seconds (main; plant) | dollars | denials | turns | the fix changed the owner file | the reply says why |
|---|---|---|---|---|---|---|---|---|---|
| plain 1 | 18 of 20 | 12 of 12 | 6 of 6 | 47; 12 | $0.353 | 2 | 21 | yes | yes |
| plain 2 | 18 of 20 | 12 of 12 | 6 of 6 | 46; 13 | $0.337 | 5 | 17 | yes | yes |
| plain 3 | 18 of 20 | 12 of 12 | 6 of 6 | 52; 12 | $0.383 | 5 | 26 | yes | yes |
| `/batch` 1 | 18 of 20 | 12 of 12 | 6 of 6 | 58; 17 | $0.456 | 6 | 30 | yes | yes |
| `/batch` 2 | 18 of 20 | 12 of 12 | 6 of 6 | 60; 16 | $0.458 | 6 | 30 | yes | yes |

The two misses in `accept` are the same in every run: "`--source` is optional now: xml by extension / csv by
extension", the change of mind the person never sent (as on every prior night). Zero files outside the intent in
every run. "The reply says why" means the follow-up's answer names the cause (every one did: the `sku` key mapped to
`xcode`, so `normalize` returned `None` and every record was dropped); nothing but the session's transcript records
it, and the plain sessions left their fix uncommitted ("that one line is the only edit, and it is not committed").
**`/batch` did not batch:** both runs read the repo, then said "I made the change directly in this checkout rather than
running the batch/worker flow, since it is eight small edits to tightly coupled files"; no subagent, no branch, no
worktree, no PR. On this task the vendor's loop is a plain session with a longer preamble (23 turns, $0.20 against
$0.16 for the plain session's first message). x0.md(f) had set this arm a rule (send the approval; if no worker
starts, report "could not run headless" and score nothing); it was set aside because neither session stopped to ask:
both did the work directly, so their rows are kept and labelled "declined to batch".

## The walks: the README's commands in order, as the person (n = 3, a scripted person on Sonnet)

`walks.sh`, 2026-10-10 16:52Z: `graphene demo --once`, a fresh report repo, `init --planner … --executor …` (Sonnet,
the isolation flags), `graphene ask "<the report paragraph>"`, `graphene plan`, `graphene plan accept`, `graphene run
--parallel 2`, `graphene node show <sub-goal>`, `graphene plan record`, `git log --merges`.

| walk | landed | minutes to the first merge | dead ends by regex (refused, is the person's, hook error, nothing to run, no proposal, could not read, not chosen, nothing is planned, cannot start, came back, exit≠0) |
|---|---|---|---|
| 1 | 2 of 2 | 0.5 | 0 |
| 2 | 2 of 2 | 0.6 | 0 |
| 3 | 2 of 2 | 0.5 | 0 |

The whole walk ran in 48 s for about $0.16 (planner $0.048, executors $0.116). Each ask proposed a sub-goal, two
leaves and one board question with a default; `plan accept` took the default; both leaves landed on their first
attempt. **No dead end on this path on 907a7d0.** What a stranger reads on it, from `walk-1.txt`: `init` prints the
two command lines it chose, `plan first: on. Every ask in a session is proposed, one leaf included, and waits for
you.` with no word of where to accept or how to turn it off, a `.gitignore` sentence that `.git/info/exclude` already
makes moot, and `recorded live into` the store; `plan accept` prints `took the default of json-types`; the run's first
printed line is `red first: 2 checks at fead50f in 0 s` with no word of where it lands; the bill line reads `you 0
acts, 0 min` after the person accepted; `node show` on a sub-goal prints an empty `scope:` and `done:` line; the two
merges carry empty bodies. The dead ends the readers found are not on this scripted path: they are in what `init`
leaves unsaid about the person's own Claude Code sessions, in `watch`'s keys, and in what the record does not print.

## X6: one stranger transcript (n = 1, a fact, not a rate)

`x6_transcript.sh`, 2026-10-10 16:52Z: a Sonnet session given only a README, the branch's (020eb7d's text: the script
read this clone's copy, not 907a7d0's; its install line pointing at the build's wheel), a fresh copy of the pytest-bdd clone with no remote, issue #476, and a `./me` wrapper that runs its
commands without an agent's marks; told to narrate every command and stop at a landed leaf or when stuck. `codex`
hidden from its PATH; `gh` and `git push` denied; GitHub unreachable. Its own `init` picked bare `claude`, so its
planner and executors ran on the account's default model, as a stranger's would.

| measure | 907a7d0 |
|---|---|
| landed | **yes**: merge `6abd049` "Print tags after the scenario status, add a test file and a changelog line (report-tags)", at the second run |
| its own session | 19 turns, 258 s, $0.196 |
| what Graphene's runs cost | $1.05 (the first run, which came back) and $0.95 (the second, which landed), at the default model |
| dead ends it met, in its words | (1) the install: "uv rejects a wheel filename with no version" (the harness had named the wheel `A.whl`; the stranger renamed it and went on: a harness fault, fixed for the after arm); (2) "the leaf came back unlanded because its check was `python3 -m pytest`, and the system python3 has no pytest. I changed only the check to `uv run pytest …` with `graphene node set` … The second run landed it"; (3) one Bash command refused by the hook for naming the store directory ("the plan's own store is not an agent's to read around or write: use `graphene plan`, `graphene node show`, `graphene plan log`") |
| what it did not do | run the test suite itself ("the pass came from Graphene's own check"); answer the two board questions (left on their defaults) |
| what it noticed | "`graphene init` added hooks to `.claude/settings.local.json` and created the store; `./me graphene init --remove` takes the hooks out" (a command that does not exist on 907a7d0: it inferred it from the README it was given, which is the branch's) |

The stranger's second dead end is the one X4 and X1 also show: the planner writes `python3 -m pytest` and the
check runs with the person's PATH; with no pytest there, the leaf costs a run and comes back with `No module named
pytest` buried in the hand-back. Nothing on 907a7d0 names that before the run.

## X2 (a): feeds through Graphene, planted (n = 3)

`x2.sh`, 2026-10-10 16:52Z. Per run: a fresh feeds repo, `init` with X1's planner and 907a7d0's `DEFAULT_WITH` plus
`--model sonnet --max-budget-usd 2 --strict-mcp-config --setting-sources project,local`; as the person: ask, accept,
`run --parallel 3`; then the plant (`code`→`xcode` committed into the landed `normalize/fields.py`), an end-to-end
leaf added and accepted (scope `tests/test_e2e_xml.py`, check `python3 -m unittest tests.test_e2e_xml -q`), a run,
the `r` offer taken by its printed command, a run.

| run | accept | held-out | the six untouched | seconds (main; plant) | dollars (planner and executors) | executor denials; turns | width | came back | the fix landed in the owner's file | why recorded |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 18 of 20 | 12 of 12 | 6 of 6 | 130; 57 | $0.749 | 20; 54 | 2 of 5 | `e2e-xml`, once | yes: `xml-wiring` reopened, landed again | yes: the reopen note |
| 2 | 18 of 20 | 12 of 12 | 6 of 6 | 89; 62 | $0.622 | 18; 51 | 2 of 4 | `e2e-xml`, once | yes | yes |
| 3 | 18 of 20 | 12 of 12 | 6 of 6 | 109; 52 | $0.628 | 14; 43 | 2 of 5 | `e2e-xml`, once | yes | yes |

The same two `accept` misses as every other arm (the change of mind never sent); nothing outside the intent. The
loop closed in all three runs the same way: the end-to-end leaf's executor found the fault, named it ("`normalize/
fields.py` maps the xml sku key to `xcode` but `samples/prices.xml` uses the attribute `code`, so every xml record
normalises to None and load emits nothing") and handed the leaf back wanting `normalize/fields.py`; the run printed
the three offers; `r` reopened `xml-wiring` with the note; the next run landed the owner's fix and then the
end-to-end leaf. Against the plain session (X2 b): the same scores, about twice the dollars ($0.62–0.75 against
$0.34–0.38) and about three times the wall clock (151–187 s against 59–64 s), 14–20 shell commands refused to the
executors (the shipped allow list is `graphene node/plan` only) against 2–5. What differs in kind: here the fault's
diagnosis and the fix's reason are rows in the plan's log and the reopen note, with the leaf that found it and the
leaf that owned it named; in the plain session they are a paragraph in a transcript, and the fix was left
uncommitted. Red first said `xml-wiring: its check passes at the base commit … it proves nothing` in run 1 (its
check was the existing suite) and named checks outside their scope in run 3; the leaves ran anyway, by decision.

## X3: ten questions about a finished run (n = 3 runs × 2 arms, one Sonnet reader each)

`x3.sh`, 2026-10-10 17:02Z, on X2 (a)'s three planted runs. Arm A got `graphene plan record`, `graphene node show`
for every leaf, `graphene plan log` and `git log --graph --oneline` (907a7d0 has no `node diff`). Arm B got `git log
-p base..HEAD` and each attempt's final words from the executors' own run logs. Each reader: `claude -p --tools ''
--json-schema x3_schema.json`, $0.50 cap, the isolation flags; eight factual questions scored by script against
`truth.json` (ids and counts exact, shas by 7-character prefix, dollars within a cent, files as a set); the two
others (why; what waits on you) printed for a person to read.

| run | arm | of 8 | q1 files the fix changed | q3 commands refused to the executors | q4 a check that passed at the base | q5 planner and total dollars | q6 width | q7 came back, reopened | q9 the fix's merge | q10 leaves added after accept |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A record | 7 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 1 | B git + last words | 3 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| 2 | A | 7 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | B | 4 | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ |
| 3 | A | 6 | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ |
| 3 | B | 4 | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ |

Medians: **the record 7 of 8; git plus last words 4 of 8.** Every reader, both arms, missed q3: the record on
907a7d0 says `refused: nothing` under attempts whose own result events hold 14 to 20 `permission_denials`, and git
knows nothing of it (this is what D1 changes). Arm B also lacks what git never held: the at-base verdict, the
dollars, the width, the leaves added after acceptance (D5 puts the first two into the merge message, so on the
branch git itself should answer more; `after.md` reports that as git's own gain). Both arms found the fix's files
and its merge and named the leaf that came back and the one reopened; on 907a7d0 the two landings of `xml-wiring`
share one subject ("Wire xml in as an enabled source with cents prices (xml-wiring)"), and the readers told them
apart by order. Readers cost $0.07–0.14 each. The questions were drawn from the gaps the night's changes fill, so
Arm A's rise on the branch is by construction; the comparison that counts is with Arm B on the same build.
