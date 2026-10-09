# morning.md — 2026-10-09 — the loop

Rollback: `main` is untouched at `af6ff38`. To drop the night: close PR #44, `git push origin --delete loop
loop-before-fold`, and `git push origin --delete statements-prereg-2` (the tag is on the branch).

## Your 30 minutes

A fresh terminal, with nothing but `uv` and `git`. Nothing here needs a key. Each step says what it prints. Run as
written from the pushed branch at 03:18 (`4eb0bed`): the install, the clone and the two replays took 45 seconds;
the scratch repo 1 to 3 minutes; the reading is the rest (`dev/process/loop/thirty.md`).

1. **Install the branch as a tool, in a directory of its own** (2 min). Your own `graphene` stays as it is.

   ```sh
   mkdir ~/graphene-loop && cd ~/graphene-loop
   UV_TOOL_DIR=$PWD/tools UV_TOOL_BIN_DIR=$PWD/bin uv tool install 'git+https://github.com/Alex-lop/Graphene@loop'
   export PATH=$PWD/bin:$PATH                            # uv warned that bin is not on PATH; now it is
   graphene --version                                    # graphene 0.5.0
   git clone -q --depth 1 -b loop https://github.com/Alex-lop/Graphene src
   ```

2. **The numbers, before and after** (5 min). `less src/dev/process/loop/before.md src/dev/process/loop/after.md`.
   Four numbers in each: the planner's rate, trees stopped on another leaf's file, width, loops closed.

3. **A closed loop** (5 min). `graphene demo src/tests/recordings/loop-claude-3.jsonl`. Two leaves land; then
   `e2e-xml` comes back (↩ on its row). `j` onto it: its pane shows why, and three rows of one shape, `w`, `b` and
   `r`: `r  reopen xml-source with this reason, which it waits on`, with the command under it. The replay presses
   it: `xml-source` opens again, runs on top of what landed, lands a new commit (◆), and `e2e-xml` runs after it
   and lands. Tab three times to `time`: `xml-source`'s second attempt, and `e2e-xml`'s after it; the note ends
   `width 1 of 3`. `q` quits. The natural one, on Nemotron: `graphene demo src/tests/recordings/loop-nemotron-2.jsonl`
   (16 minutes of run, replayed faster). The pane as the replay shows it: `src/dev/process/loop/screens/replay-came-back-80.txt`.

4. **Red first on a scratch repo** (8 min; it uses your Claude Code login, about $0.80 on its default model).

   ```sh
   uv run -q --no-project --python 3.13 python src/dev/test/make_task.py report ~/graphene-loop/report > /dev/null
   cd ~/graphene-loop/report
   graphene init --planner claude --executor claude       # plan first: on. Every ask in a session is proposed…
   graphene ask 'Finance wants the sales report as JSON: make render(rows, "json") in app/report.py give a list with one object per data row (region, units, revenue), no TOTAL row, and leave the text report as it is.'
   graphene watch
   ```

   The proposal waits for you: `y` on the goal accepts it, `R` runs it. The run's first lines, in the pane:
   `red first: 2 checks at <base> in 0 s`, and above it one line for any check that passes at the base (`it proves
   nothing`) or names a file outside its scope; a leaf so marked shows `∅` after its title. Then `q`, and
   `graphene node show <leaf>`. If `ask` says `no proposal after 2 tries`, ask again: it is the planner's text, not
   the repo. Tonight 3 of 4 asks on this paragraph proposed a tree at once (the first did not, twice over a
   `then:` line).

5. **Decide** (5 min): the three questions in the brief below, each with my default.

6. **Merge** (1 min): `gh pr merge loop -R Alex-lop/Graphene --merge`. Then `git push origin --delete
   loop-before-fold` once nothing in the evidence needs its builds.

## Saturday

The three commands that start `PROVE.md`, from your checkout after it has the branch (read `PROVE.md` there, not
from the tag: the tag's own copy is the one from before it was named):

```sh
cd ~/Desktop/AllThingsAgenticHackathon && git pull -q && git fetch -q --tags origin
less dev/test/PROVE.md                                                    # the whole page, once, before anything
less dev/test/tasks/statements/intent.md                                  # the card: the one page you read once
```

Then `PROVE.md`'s "Once" block as written: the worktree at `statements-prereg-2` (commit `803f2c2`), the wheel
built from it, the rehearsal reading 5, 5, 0, 0 (`dev/process/loop/prove-run.md` is tonight's run of it from a
fresh install). The arms are P1, T1, T2, P2, on the tag, nothing else. Your predictions block is still blank.

## The brief

1. **The numbers**, before → after (`dev/process/loop/before.md`, `after.md`):
   - Nemotron proposals by ask: 15 of 20 → 35 of 40 (87%) (feeds 17 of 20, report 18 of 20) on the final
     code; 30 of 40 on lane 3's build before its review. By answer: 15 of 30 → 35 of 62 (56%).
   - Trees stopped on another leaf's file: 4 of 13 → 2 of 23 trees came back on a landed leaf's fault, and both
     closed the loop with `r`.
   - Width: not measured → the dogfood 4 of 5, feeds 1 or 2 of 2 or 3, statements 3 of 8 to 12; last night's
     recordings 1 of 2, 1 of 2, 1 of 2 and 2 of 3.
   - Loops closed: 0 → 2 live (Nemotron, natural; Claude Code, planted at 01:13:42) and the scripted one; one
     attempt per owner; $0.02 and $0.24 for the closing round.
2. **Watch first:** `graphene demo tests/recordings/loop-claude-3.jsonl` (the planted loop, `j` onto `e2e-xml`
   when it comes back) and `loop-nemotron-2.jsonl` (the natural one). The best take: `loop-nemotron-take-2.jsonl`
   (Ultra planned three leaves, Nano landed all three in Sandboxes, $0.11).
3. **The bill:** $35.55 on the ledger, about $40 with the 30 minutes put on by hand of $50: `planner` $15.85 · `precheck` $11.92 · `reopen` $4.07 · `dogfood` $2.07 · `takes` $1.63; the four runs of the 30 minutes (a tool from GitHub writes no ledger rows) about $4.4 on Claude Code's default model.
4. **Your practice notes:** `~/graphene-timeline/practice.md` does not exist on this machine: nothing to answer.
5. **Decide:** 1. Take 2 as the Nemotron demo recording instead of last night's take 6? Default: yes, it lands
   one leaf more and ran as clean. 2. Keep `r` offered whenever a wanted path has a done owner, even when the
   reason is a scope too narrow? Default: yes, the person reads the reason, and `w` and `b` sit beside it.
   3. The planner reached 87% by ask on the final code (round 2), so `docs/HACKATHON.md`'s planner line stays: Ultra plans, Nemotron executes. Keep it as the pitch? Default: yes, with the number beside it in the brief; the stretch stays what it was.
6. **Broken or risky:** The Claude Code text planner proposed nothing twice in a row on the morning's scratch
   paragraph once in four asks (a `then:` line the text form cannot read); lane 3's repairs are the Nemotron
   planner's only. 12 of 82 Ultra answers stalled to the token limit in round 1 (3 of 30 last night): longer
   send-backs. Net source lines: +406 (lanes 1 and 2 +297, lane 3 +100, lane 4 +5, lane 5 +4).

---

Tonight's decisions are in `dev/DIRECTION.md`, 181 to 195. The evidence: `dev/process/loop/` (`before.md`,
`after.md`, `lane1-evidence.md`, `lane5-evidence.md`, `review.md`, `takes.md`, `asks-round1.md`, `asks-round2.md`,
`prove-run.md`, `lane0.txt`, `thirty.md`, `screens/`).

## The dogfood bill

Lanes 1 and 2 were built through Graphene itself: one tree of five leaves proposed as text, plan first on, accepted
as the person, four Sonnet executors at once in worktrees, the meter on, `watch` on `time` shot every minute. **0
acts of mine after the accept, 12 agent-minutes, 310 s of wall time, $2.07 at list price, width 4 of 5.** Every
leaf landed on its first attempt; `r` was not used on Graphene itself, since no leaf came back. Two skeptics a leaf
then found 44 things about the executors' code, 13 distinct real ones fixed (`dev/process/loop/review.md`).

## Branches

- `main`: `af6ff38`, untouched, local and on GitHub.
- `loop`: the night, pushed; PR #44 is the only one. 31 commits (the directive's 30 to 50): the history was folded before its first
  push (every lane one commit, the tree byte for byte the unfolded one).
- `loop-before-fold`: the 87 commits before the fold, pushed so every build the evidence names resolves. Delete it
  when you merge.
- `statements-prereg-2`: the tag, at `803f2c2` on `loop`, pushed.
- In this run's clone only: nothing else; the lanes' worktrees are gone.

## What was done, in order

- **00:30** Read the directive. Branch `loop` from origin/main `af6ff38`, in a clone outside your checkout. The
  directive is committed at `dev/process/directives/LOOP_DIRECTIVE.md`. The night's ledger: $50 cap, nothing new
  past $45; the session was not started with `GRAPHENE_AGENT_LIVE_USD`, so the directive's $50 line is the opening,
  as decisions 151 and 166 read the last two nights'.
- **00:40** Lane 0: `dev/process/loop/before.md`. The suite on `main` as it is: 1,698 passed in 19 min.
- **00:42** Lanes 3, 4 and 5 started, one builder each in a worktree of the clone, each reviewed from two sides.
- **00:44** Lanes 1 and 2 proposed as one tree of five leaves through Graphene itself and run with four Sonnet
  executors at once. All five landed on their first attempt by 00:50.
- **00:51** The scripted loop: `r` offered and taken, the owner fixed on top of what landed. It showed one gap:
  after `r` a leaf that already waited on the owner still read as came back, so `R` left it alone. Fixed (`f7a9697`).
- **00:54** Live: feeds on Nemotron and on Claude Code, three runs each, and the statements task three times with
  red first on.
- **01:04** Red first's first rule flagged 8 of 9 statements leaves whose checks name an existing test beside their
  own new one. Refined: a red is outside by the failure's cause (`9e38e71`, `fa0ddc7`).
- **01:11** Nemotron run 2 closed the loop on a natural fault: `xml-test` found `normalize/fields.py` returning
  `price` where the rules expect `price_cents`; `r` reopened `xml-feed`; Nano fixed it on one attempt ($0.0077).
- **01:14** Three Claude Code runs came back on nothing (every leaf owns its own test), so a fault was planted at
  01:13:42 in a landed file; `e2e-xml` came back wanting it; `r` reopened `xml-source`; fixed in 4 turns ($0.11).
- **01:16** The planted whole-suite check: `red first` named `tests/test_zero.py`, the file no word of `python3 -m
  pytest -q` names.
- **01:20** The suite found that red first's checks outlived a closed terminal and a Ctrl-C waited for them: fixed
  (`7ce64e4`), with a test for a stop during red first.
- **01:38** Two skeptics a leaf on the dogfood's code: 44 findings, 13 distinct real ones fixed (`49297e6`).
- **01:45** The suite green on lanes 1 and 2 (1,737 passed); the tag `statements-prereg-2`. Lane 6 started on it;
  lane 3's 40 asks and the first four takes started on lane 3's build.
- **02:06** Lane 6 merged: PREREG names the tag and the four new blobs, PROVE.md builds the wheel from the tag,
  and its Once block ran from a fresh install: the rehearsal reads 5, 5, 0, 0 (`dev/process/loop/prove-run.md`).
- **02:24** Lane 3's round 1: 30 proposals in 40 asks (feeds 12, report 18), $10.23.
- **02:50** Lanes 5, 3 and 4 merged, each after its two reviewers and its fixer. The suite: 1,773 passed in 19 min.
  Round 2 of the asks and takes 5 and 6 started on the merged build.
- **03:17** The history folded to 31 commits with the same tree; `loop`, `loop-before-fold` and the tag pushed;
  PR #44 opened; the wheel installed outside the source tree replays `graphene demo --once`; the cut's lane 0
  still leaves the checkout clean (`dev/process/loop/lane0.txt`).
- **03:18** Your 30 minutes, from the pushed branch: the install, the clone and the replays in 45 s; the scratch
  repo's planner proposed nothing twice; three more asks proposed at once and ran.
- **03:20** A review of the whole branch where the lanes meet started: three readers, two skeptics a finding, a
  fixer on a branch.
- **03:43** Lane 3's round 2 on the final build: 35 proposals in 40 asks (feeds 17, report 18), $8.20. CI: the first
  seven jobs green, the rest running.
