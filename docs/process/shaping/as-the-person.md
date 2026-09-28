# Tonight's own plan, shaped by the coordinator in the person's seat

The directive puts tonight's own plan in Graphene and has the coordinator be the person on it: write
the paragraph, prune, take or refuse the offers. Lane B (settings a person states once) went through
Graphene this way, in a clone of this repository at `~/graphene-night` (branch `night-b`), with Claude
Code as planner and executors. Every friction felt there is a finding for lane A, logged here as it
happened, in the order it happened.

How the coordinator stood in: its shell carries Claude Code's markers (`CLAUDECODE`,
`CLAUDE_CODE_SESSION_ID`, …), so Graphene takes it for an agent, as it should. For the person's acts it
dropped those markers and set `GRAPHENE_AS=person:alex`, which is the stand-in's mechanism
(`docs/test/newrun.sh`); the plan's log marks each such act "(no terminal)". A clone, not a worktree:
a worktree shares the main checkout's store, and a plan in force there would have held every other
lane's sub-agent to it.

## Findings

1. **00:46, the paragraph.** 196 words, typed once. `graphene ask` with Claude Code as the planner took
   2 minutes and proposed 9 leaves under 4 sub-goals, every scope from files it had read.
2. **The planner's questions were prose, and scrolled away.** After the block it wrote five
   paragraphs (about 250 words) that were really board items: a gap it could not close (a Codex
   planner can still read protected paths), a choice it made for me (never-propose lines are told,
   not enforced), a default it assumed (an aside's `**` leaves protected paths out rather than being
   refused), the files it would collide on, and what it left out (the README and DIRECTION lines).
   None of it is stored: `graphene ask` prints it once, cut at 300 characters a line (item 4 ended
   mid-sentence, "which leaves out"). To answer them I had to hold them in my head while I read the
   tree. This is the board's case, from our own plan: each would have been one key.
3. **Adding one sentence to a leaf's goal meant retyping all of it.** `graphene node set --goal`
   replaces the goal, so the CLI path to "and never put the key in argv" was 130 words pasted back.
   In the screen `e` opens an editor, which is better; from a shell there is no append.
4. **One check was the whole suite.** The planner gave the last leaf `uv run pytest -q && uv run
   ruff check`: 832 tests in a clean worktree on a machine running eleven other agents, where the hook
   time-budget tests fail for the load. I narrowed it to the three test files the leaf touches. The
   planner has no way to know the suite's cost; a note on the board ("the full suite takes about 6
   minutes; narrow it?") is where that would go.
5. **Accepting was one command** and said which leaves an unattended run would reach (all nine).
   Two acts before `R`: two edits and the accept.
6. **01:00, two leaves came back for one cause, with offers pointing at two different files.** `told`
   and `cond-hidden` did their work, but their checks failed on Graphene's own tests: a check runs
   with the executor's `GRAPHENE_NODE` set, and the suite then takes its test person for an agent.
   Each leaf offered a widen and a sibling for the file it had found (`tests/test_plan_cli.py` for
   one, `tests/conftest.py` for the other). Seeing that one fix in `tests/conftest.py` covers both,
   and that `conftest.py` sat inside a leaf still running (`key-find`), was mine to work out from two
   paragraphs of prose. I added one leaf (`hermetic`, after `key-find`) and made both wait on it: three
   commands, one of them 90 words. What would have cut it: "these two came back for the same reason"
   said once on the tree, and a merge of their offers ("talking on the tree": merge these).
7. **01:07, the run ended with a ready leaf left behind.** I added `hermetic` while the run was
   going; it became ready when `key-find` landed, but the run ended ("6 done, 3 came back") without
   starting it. A leaf added during a run waits for the next `R`. Nothing on screen said so.
8. **A leaf landed with lint the next leaf paid for.** `sizing`'s check was its test file alone, so
   four lines over the length limit landed, and `wire` (whose check runs ruff) came back for them.
   The planner put ruff in one check of nine. A standing condition ("every check ends with ruff") is
   the kind of thing a person states once.
9. **The third came-back (`wire`) needed the same fix plus two files.** I widened it to
   `tests/test_cli.py` (a test that pins the command list) and `sizing.py`, and made it wait on
   `hermetic`: one command, but I had to read three reasons in one paragraph to write it.
10. **01:15, done.** The second `R` ran the four left in 7 minutes; the whole lane took 29 minutes of
    wall clock from the paragraph, and 10 leaves landed (1,341 lines, 11 new test files). My part:
    one paragraph, then 9 acts (2 edits and an accept before the first run; an add, three edits and a
    run between the two runs), and about 700 words of the planner's and executors' prose read. Most
    of the reading was the came-back paragraphs; most of the typing was one retyped goal.
11. **What still landed wrong: lint.** `told` landed five lines over the length limit because its
    check was its tests alone, while `wire`'s ruff ran on a checkout without `told`'s change. Each
    leaf's check passed; the merged whole did not. A check is about its leaf, and nothing checks
    the sum. The review of the lane fixes them.
12. **02:05, the same paragraph again, to the planner that asks.** In a fresh clone at the same
    commit, the board-aware planner (prompt version 2) put up five items instead of five paragraphs:
    three questions with a default each (does a broad scope that covers a protected file get
    refused, or have the protected paths cut out of it; does `--finer` drop the earlier proposals;
    are never-propose lines sentences or globs), one assumption (settings live in the store), and one
    risk I had not seen at all: an executor's own shell can run `security find-generic-password` on
    Graphene's keychain item, so the keychain protects the key from files, not from the executors.
    Every one of the five was a decision lane B's executors made silently tonight. Each would have
    been one key.
