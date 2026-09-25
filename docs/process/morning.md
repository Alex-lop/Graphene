# morning.md — 2026-09-25 — the Nemotron directive

(Current at every milestone of this run. Last run's is `docs/process/morning-2026-09-24.md`.)

**The blocker, first: this run has had no Token Factory key and no Sandboxes access.**
- At 01:15 EDT `NEBIUS_API_KEY` was not set in the shell this run works in, and `GET /v1/models`
  answered `401 token is not present`. Neither ConTree's CLI nor its credentials are on the machine.
- I checked again at every milestone. It was still unset at 05:56, when the run ended.
- So everything is built against two stand-ins, and the first real run needs only the key:
  - for Token Factory, a scripted fake endpoint (`tests/fake_tokenfactory.py`; it can replay a
    recording, and none exists yet);
  - for Sandboxes, a real Linux box, Docker, with the same users and permissions (`sandbox.Docker`).

To give a run access: put `export NEBIUS_API_KEY=…` and `export NEBIUS_PROJECT_ID=…` in `~/.zshenv`,
then run `uv run python docs/test/access.py`.

## 1. The number

**There is none.** No leaf has been done by a real Nemotron model, so there is no landed share,
accept, quality or cost per landed leaf. I will not print one from the fake.

What stands between you and the number, in order:
1. `uv run python docs/test/access.py`. It prints the NVIDIA ids Token Factory lists, and makes one
   tool call per Nemotron model to say which misfire. It also times the Sandboxes steps: make, run,
   fork, two forks at once.
2. A fixed tree per task: `docs/test/trees/README.md` gives the commands. Ultra plans from a stand-in's
   paragraph, a stand-in prunes it, and `bench.py --checks-only` refuses a tree with a check that
   already passes at base.
3. `docs/test/bench.py <task> --config … --executor … --run n`, three times on feeds and three on
   inventory, then `docs/test/results.py`. It writes one row a leaf and one a run, and the table
   puts accept beside landed.

How the number moved over the night: nothing to move.

## 1b. Three judges who had never seen the run (backlog 5)

They were given the rules, the criteria and the branch, and could run anything that needs no key.

- **Stage One:** pass, 3 of 3.
- **Median scores:** Technological Implementation 3, Design 3, Potential Impact 3, Quality of the
  Idea 4.
- **Their caveat:** a strict screener could fail it on "runs on Token Factory", because nothing has
  run live yet.

They found real bugs, each reproduced. What I fixed, each with a test that fails without the fix:

- **A sandbox leaf's `done` could not reach ConTree.** The executor stripped the key from its own
  `graphene node done`, where the check is forked, so the SDK sent the variable's *name* as the
  token. The first live run would have failed on every leaf.
- **An executor that cannot work at all** (no key, a refused key, no sandbox, the spend cap) now
  hands the leaf back itself, with the cause. Before, a wrong key came back as "3 attempts, the last
  one refused: AssertionError".
- **The planner's `read` sent a git-ignored `.env` to Token Factory.** The planner and the executor
  now read only what git shows.
- **The sandbox's file list was read from capped output.** In a big tree, in-scope files were
  unlinked from the checkout (224 of 3,000). The list is now read back whole, or nothing changes.
- **Guards for real reasoning models:** a reply cut off at the token limit, Nemotron's own
  `<TOOLCALL>` text, and a POST retried after a 300 s timeout.
- **Leaves at one commit now fork one checkpoint**, and `--forks` forks one sandbox. The thesis said
  so, and the code did not: each fork uploaded again, and from a copy with no `.git` it packed
  nothing. There are also `--image` and `--prepare`, so a repository whose check needs pytest can
  pass in a sandbox.
- **The draft submission's overclaims are gone.** It had said every tool call runs in the sandbox,
  the stand-in was "recorded", and the pricing feedback was observed; the counts were stale.
- **The README's 18/20 now sits beside the fair comparison:** the 23 September test, where a plain
  paragraph also passed.

Still open from their list:
- **Yours:**
  - the install line gets Nemotron only once PR #29 is merged;
  - the GitHub About text and homepage still describe the old Taskmaster product;
  - the demo URL and the video.
- **Needs the key:** the live run, and a real repository.
- **Not reproduced:** a "3 leaves" count.
- **After the cut merges:** the Nemotron leaf's record, the parallel record's attribution, and init's
  Claude-heavy output.

## 2. What you can run in five minutes

**Without a key** (what I ran; about four minutes):

```
cd ~/Desktop/AllThingsAgenticHackathon && git checkout nemotron && uv sync --all-extras
open -a Docker                              # the sandbox stand-in
uv run pytest -q tests/test_escape.py tests/test_executor.py tests/test_planner.py tests/test_init.py
SHOW_DEMO=1 uv run pytest -q -s tests/test_demo_script.py     # the whole demo script, against the fake
uv run python docs/test/access.py --sandbox docker
open docs/process/nemotron/demo-draft-standin.gif           # the tape, rendered against the stand-in
```

`test_escape.py` is the one to read. A scripted Nemotron executor, in a sandbox, tries every way out
of its leaf's scope, and every way fails; every write inside the scope succeeds. Section 4 quotes its
log. The gif is the storyboard's shape with a scripted model on a tiny repository. It is not Token
Factory, and it is kept in the diary for that reason.

**With a key**, the Nemotron path end to end on feeds, where the key spends real money (about the
price of a coffee, going by the fake's token counts; unmeasured):

```
export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=…
uv tool install --editable '.[sandbox]' --force
docs/proof/nemotron.sh ~/graphene-nemotron      # the path in one script
vhs docs/proof/nemotron.tape                     # the same, on screen, for the video
```

## 3. What waits on you

- **Access.**
  - A Token Factory key.
  - For Sandboxes, a project with the beta (by request).
  - The rules' credits: `NEBIUS-DEVPOST-GLOBAL26` on the resources page gives $25 of Token Factory
    credit.
- **PR #29** (draft), `nemotron` into `main`. CI was not green at every push, and two runs show
  why:
  - `2926419`, macOS 3.13: the hook time-budget test, 163 ms against 150 on the runner. That is the
    directive's named environment test, left as it is.
  - `3b7da28`, macOS 3.12: a real race. The executor read its attempt number back from the log
    before `run` had written it, so it could stay on Nano for attempt 2. Fixed at `07c73ab`
    (`GRAPHENE_TRY`), with a test that fails without the fix.
- **The README changes, for you to put in your own words.** The opening and the hand-back copy are
  untouched. What changed:
  1. **The setup:** install with the `sandbox` extra, the key, `graphene init`, and what runs where.
     Claude Code's two panes follow as the alternative.
  2. **What it is not yet:** a paragraph saying the Nemotron path has run only against the
     stand-ins.
  3. **What does not bind:** it opens with the table of who is held before a write and how, then
     layer 2's directory grain.
  4. **Install:** a sentence about `[sandbox]`.
  5. **Privacy:** two bullets replace "nothing leaves your machine". One says what Nemotron sends, and
     where the key never goes; the other says where the bill is.
  6. **Requirements:** a sentence on the key, the extra and Docker.
  7. **What works today:** the 18/20 result now sits beside the 23 September comparison, where a
     plain paragraph also passed 20 and 12 with less of the person's time.
  8. **The table:** in the local placement a command can read, as well as write, what your user can.
- **The GitHub repository's About text and homepage** still describe the pre-period "Taskmaster"
  product. A judge meets them first. A line for it: "The shared plan between a person and their coding
  agents: NVIDIA Nemotron plans and does the work on Nebius Token Factory, each leaf held to its files
  in a Sandbox." Yours to set.
- **`docs/HACKATHON.md`**, a draft: what Graphene is, how it uses the sponsor's tools, what changed
  during the Submission Period (from git: all of `src/` was written after it opened), and the feedback.
- **Pages, PyPI, the video, Devpost:** yours, untouched. `pages.yml` runs only when you start it.
- **The diary.** After this PR merges, the one command that removes `docs/process/` from `main` is
  at the end of this file (item 9). I do not run it.
- **Decisions to strike: 53 to 65** in `DIRECTION.md`. Read these first:
  - 54 (Graphene now calls a model, when you name Nemotron);
  - 57 (layer 2's directory grain);
  - 62 (the check's clean tree has no `.venv` in it).

## 4. Tonight's decisions, with their evidence

- **53. The import package is `graphene_map`.** One mechanical commit (`af03827`): 695 tests, the page
  rebuilt identical, the wheel smoke passed.
- **54. Graphene calls a model when you name its Nemotron planner or executor.** This changes decision
  9. The key is read at each call and written nowhere. A command the model runs, and every check, get
  an environment without it. Checking that, I found the check `graphene run` runs after an executor
  ends had inherited the key. Now fixed, and a test fails without the fix.
- **55. The placement is "the loop here, the tools there."** A spike ran OpenCode 1.18.31 inside the
  same Docker sandbox, against the same fake, three runs each
  (`docs/test/spikes/harness_there/RESULTS.md`):

  | | the loop here | OpenCode in the sandbox |
  | --- | --- | --- |
  | a write outside the scope reaches Graphene's log before it happens | 3 of 3 | 0 of 3 |
  | the key readable by a command the model writes | 0 of 3 | 3 of 3 |
  | characters sent to the model for a landing leaf | 32,265 | 168,111 |
  | wall time, landing leaf (median of 3) | 9.6 s | 8.9 s |
  | wall time, a hand-back | 2.8 s | 7.3 s |
  | one tool call | 2.3 s for a command in the sandbox, 0.00 s for an edit | 0.02 s, plus about 5 s to start |

  What would change the call: ConTree's round trip, which is the first number `access.py` takes.
- **56. No model id is written in the code; the live list names them.** Not verified against the real
  list tonight.
- **57. Layer 2 is directory-grained, and what it cannot stop never comes back.** From the escape
  test's log (the Docker stand-in):

  ```
    1 write other.py → other.py is outside the scope of the node you hold (greet: app.py, tests/test_new.py). …
    3 run echo gone > other.py → exit 1
    4 run sed -i s/1/2/ other.py → exit 4
    5 run python3 -c "open('other.py', 'w').write('x = 4')" → exit 1
    6 run mv other.py moved.py → exit 1
    7 run rm -f other.py tests/test_app.py → exit 1
    8 run git checkout -- other.py; git reset --hard; git config user.name x → exit 128
    9 run ln -sf /etc/hostname other.py → exit 1
   10 run chmod 666 other.py || chmod 777 . tests → exit 1
   11 run echo 'import os' > tests/conftest.py → exit 0   (made in the sandbox; refused, never brought back)
   12 run ln -s /etc/passwd leak → exit 0                   (the same)
   13 edit app.py → edited app.py
   14 run sed -i s/hullo/hello/ app.py → exit 0
   15 run printf 'def test_new():…' > tests/test_new.py → exit 0
   18 done → greet is done (check passed, nothing outside its scope)
  ```

  Graphene's own check of that leaf then ran in a fork of the sandbox, as the sandbox's user: its
  output is `leaf`. The spike found that a check's own `__pycache__` was logged as a breach and became
  a hand-back offer. It is fixed: what git ignores is nobody's change, in the sandbox as at `done`.
- **58. The bill is Token Factory's own usage at its list price.** It shows in `node show`,
  `plan record`, the run's last line, and the screen's status line and node pane.
- **59. ConTree's SDK is pinned at 0.3.6.** Its docs describe an API no release has. Details are in
  the feedback in `docs/HACKATHON.md`.
- **60. A leaf can fork:** N conversations from one checkpoint, and the check picks.
- **61. `graphene init` asks once**, and Nemotron is offered first.
- **62. The check runs in a clean worktree** of the leaf's state. This replaces decision 48's
  move-aside. An adversarial review found three real faults in the first version, and each is fixed
  with a test:
  - a `uv run` check broke the checkout's `.venv`;
  - a large repository hit a 30 s cap;
  - a killed worktree was left locked.
- **63. Folding.** Thirty leaves at 80×24 open as a seven-row outline that says where your move is.
  Before and after, at 80×24 and 120×36: `docs/process/nemotron/folding/`.
- **64. The demo URL is one file, exported from the store**, and a Pages workflow that runs only when
  you start it. Its review found `graphene ui --export` crashed on any leaf whose merge had not
  landed. That is fixed.
- **65. The benchmark's person** takes a widen only when every path it adds is inside the task's
  intent, and never a sibling.
- **Backlog 7:** Python 3.14 is in CI. One finding goes against the directive: no 3.13 or 3.14 build
  warns about `?N` placeholders. Python 3.12.0 to 3.12.3 do, and those are fixed.
- **66. Graphene reads no Claude Code transcript** (item 9). The transcript world is deleted, and the
  modules are named for what they do:
  - `hooks.py`, the live hooks;
  - `shell.py`, the shell parser the gate uses;
  - `repo_root` is in `store.py`.

  `src/graphene_map` lost 731 lines. A review found the map had lost a subagent's task and worktree;
  both are now read from what the hooks recorded. The full map of what was kept, moved and deleted is
  `docs/process/nemotron/cut.md`.
- **67. A leaf in a sandbox forks its commit's checkpoint**, and **68. an executor that cannot work
  hands its leaf back with the cause**, and **69. only what git shows is read and sent.** All three
  came from the judges (section 1b).

## 5. From tomorrow to 30 October

Each step, with its risk.

| When | What | Risk |
| --- | --- | --- |
| The day the key comes | `access.py`: ids, one tool call per model, and the Sandboxes timings | Nemotron's native tool calls misfire at Nano size. `--protocol text` is ready. |
| +1 day | The four fixed trees (Ultra plans, a stand-in prunes), and `score_tree.py` on each | Ultra writes checks that already pass at base. The bench refuses those, so a tree may need a second pass. |
| +2 to +4 days | Item 2d: tune on feeds and inventory until 80% land over three runs with accept passing, one lever at a time, rows for each | Nano may land far less than 80%. Report it low and climb the ladder (Super, forks). The directive forbids tuning the number, not the executor. |
| +5 days | Freeze; report and logs held out; backlog 1 and 2 (five runs each, and the cost curves) | Spend: the ledger caps each night at $30. |
| +6 days | Backlog 3 (a fifth task from a real repository) and 4 (`--parallel 8`, thirty leaves, in sandboxes) | ConTree's beta cap of 50 operations at once, and rate limits. |
| by 20 October | The demo run, live; `vhs docs/proof/nemotron.tape` (two panes, the storyboard's scenes); record the video to `docs/demo/STORYBOARD.md` | A flaky live run on camera. The tape cuts only the waits. |
| by 25 October | Finish `docs/HACKATHON.md` in your words: numbers, the account of changes, feedback. Export the demo page and enable Pages. | The judges test until 15 December, so the page and the README must keep working. |
| 30 October, 10:00 PT | Submit on Devpost | Yours. |

## 6. The map of the code, where it moved

`src/graphene_map/` has 13,540 lines in 23 modules at `a03bf4c`.

New tonight:
- `tokenfactory.py` (213): the client, `roles` from the live list, the ledger and the cap.
- `executor.py` (623): the Nemotron executor.
  - `Leaf` holds its tools; `converse` is the loop, `fork_and_pick` the forks, `Local` the local
    placement.
  - `stop` hands the leaf back when the executor cannot work.
  - `ALIASES` and `text_calls` cover the call spellings small models use.
- `planner.py` (205): the Nemotron planner; it reads what git shows.
- `sandbox.py` (439):
  - `Contree`, the ConTree box, and `Docker`, its stand-in;
  - `base` (the commit's checkpoint) and `layer2` (a leaf's permissions);
  - `Sandbox`, with `.fork` and the whole-list `_state`;
  - `check_in_fork`.

Moved by the cut (item 9, `docs/process/nemotron/cut.md`):
- `sources/claude_code.py` is `hooks.py` (415): the live hooks. The transcript backfill is deleted.
- `attribute.py` is `shell.py` (251).
- `repo_root` is in `store.py`.

Where old code moved:
- **`gate.scope_refused`:** the one scope refusal, which the hook and the executor both say.
- **`plan.run_check`:** the one place a check runs (a clean worktree). `plan.sandboxed` routes a
  sandbox leaf's check to a fork, and `plan.in_tree` lists what git shows.
- **`node_record`:** `bill`; `_own`, a `--parallel` leaf's own commits; `_graded_by_executor`.
- **`run.named` and `ask.named`:** turn `nemotron`, `claude` and `codex` into commands.
- **`cli.init`:** the choice first (61).
- **`tui.py`:** folding and the bill.

The harness is in `docs/test/`:
- `access.py`: the access check.
- `bench.py` and `results.py`: the benchmark.
- `score_tree.py` and `trees/README.md`: the fixed trees.
- `spikes/harness_there/`: the OpenCode placement spike.

The screen harness is `docs/screens/`.

The tests:
- `tests/fake_tokenfactory.py`, the scripted fake (it can replay a recording);
- `test_tokenfactory`, `test_executor`, `test_planner`, `test_init`, `test_demo_script` and
  `test_demo_export`;
- and, with Docker, `test_escape`, `test_sandbox_state` and `test_sandbox_contract`.

## 7. Questions (only what blocks the next step)

1. **Can this machine have the key tonight or tomorrow?** Everything in section 1 waits on it, and
   nothing else does.

## Verified, and not

- **Verified.**
  - The suite: 758 tests at `a03bf4c`, green, nothing skipped with Docker running. Ruff is clean over
    the whole repository.
  - The wheel installs outside the tree and runs `graphene --version`, and the Nemotron modules
    import from it.
  - The escape test runs against a real Linux user in Docker.
  - The OpenCode spike ran, with numbers.
  - `docs/proof/nemotron.sh` runs end to end against the scripted fake (`tests/test_demo_script.py`).
  - The tape renders.
  - The access check says "no key" truthfully.
- **CI.** Two failures in tonight's pushes were environment tests (the hook budget on a macOS
  runner). Two were real:
  - a race in the attempt number (fixed at `07c73ab`);
  - a race in a test's trigger (made deterministic at `a03bf4c`).

  I cancelled the queued runs of superseded commits, so the tip gets CI's verdict. Check it on
  PR #29.
- **Not verified.** Anything against Token Factory or ConTree (no key): the real ids and prices,
  Nemotron's tool calls, ConTree's users, output cap and timings, the live demo, and every number in
  section 1.

## The diary (item 9)

`docs/process/` is on its own branch, `process-archive`, made with `git subtree split` so its history
comes too, and pushed. After you merge PR #29, the one command that takes the diary out of `main` is:

```
git rm -r -q docs/process && git commit -m "the process diary lives on the branch process-archive"
```

Nothing in the product, the tests or CI reads `docs/process/`. I checked that with `git grep`. Two
documents name files in it, and those names will point at `process-archive`:
- `docs/DIRECTION.md` names the directives and past morning files;
- `docs/screens/README.md` names the polish run's saved screens.

The screen harness moved out to `docs/screens/` first.

## Rollback

Before the first change, `main` on GitHub was `cd13cbe` (your merge of PR #28). This run is the
branch `nemotron`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard cd13cbe
```

## State of every branch

- **`nemotron`:** this run, 73 commits on `origin/main`, pushed. Draft PR #29, description current.
- **`process-archive`:** `docs/process/` with its history (`git subtree split`), pushed.
- **`main` (GitHub):** `cd13cbe`, untouched. Local `main`: `6cece1c`, behind, untouched.
- **Tonight's build branches:** `worktree-wf_cc0667ef-4ad-1` … `-4`, `worktree-wf_649e59d0-fc8-1`
  and `-2`, `worktree-wf_75600a22-a0a-1` and `-2`, and `worktree-agent-a8f2179f59c043d5a`. All are
  merged into `nemotron`. Their worktrees are removed and the branches kept (`git branch -d` drops
  them).
- **Everything else** (`polish`, `terminal`, `agent/*`, `n*`, …) is as it was.
- **Docker:** tonight's 195 test checkpoints are pruned. `python:3.12` and the spike's image
  `graphene-harness-there:opencode-1.18.31` stay.
