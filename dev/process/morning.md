# morning.md — 2026-10-08 — the timeline

Rollback: `main` is untouched at `a96fb48`. To drop the night: close the PR, `git push origin --delete timeline`.

## Your 30 minutes

A fresh terminal, with nothing but `uv` and `git`. Nothing here needs a key. Each step says what it prints.

1. **Install the branch as a tool, in a directory of its own** (2 min). Your own `graphene` stays as it is.

   ```sh
   mkdir ~/graphene-timeline && cd ~/graphene-timeline
   UV_TOOL_DIR=$PWD/tools UV_TOOL_BIN_DIR=$PWD/bin uv tool install 'git+https://github.com/Alex-lop/Graphene@timeline'
   export PATH=$PWD/bin:$PATH
   graphene --version                                    # graphene 0.5.0
   git clone -q --depth 1 -b timeline https://github.com/Alex-lop/Graphene src
   ```

2. **The numbers, before and after** (5 min). `less src/dev/process/timeline/before.md src/dev/process/timeline/after.md`.
   Each file leads with the same three numbers.

3. **The timeline** (5 min). `graphene demo src/tests/recordings/timeline-claude.jsonl`. When the tree shows, press
   Tab three times: tree, dag, then `time`. Each lane grows as its leaf ran. ✓ is a passed check, ◆ a landing.
   `j` onto a lane, and the pane under it lists what that leaf did, with the seconds. `q` quits.

4. **Five minutes on a scratch repo** (8 min; it uses your Claude Code login, about $0.30).

   ```sh
   uv run -q --no-project --python 3.13 python src/dev/test/make_task.py report ~/graphene-timeline/report > /dev/null
   cd ~/graphene-timeline/report
   graphene init --planner claude --executor claude       # plan first: on. Every ask in a session is proposed…
   graphene ask 'Finance wants the sales report as JSON: make render(rows, "json") in app/report.py give a list with one object per data row (region, units, revenue), no TOTAL row, and leave the text report as it is.'
   graphene watch
   ```

   The proposal waits for you. One leaf is one row: `y` accepts it and runs it. A tree: `y` on the goal accepts it
   all, then `R` runs it. Tab to `time` while it runs. Then `q`, and `graphene node show <leaf>`.

5. **Decide** (5 min): the questions in the brief below, each with my default.

6. **Merge** (1 min): `gh pr merge PRNUM -R Alex-lop/Graphene --merge`.

## Your practice run

One hour, on a repo of yours, the way you would use Graphene.

1. In the terminal from step 1: `cd ~/<your repo> && graphene init --planner claude --executor claude`. Plan first
   is `on`.
2. Two panes: `claude` on the left, `graphene watch` on the right.
3. On the left, say a paragraph of your own: something you want done that is bigger than one change.
4. On the right, prune the tree (`d` drops, `e` edits, `y` accepts), then `R`. Tab to `time` while it runs. Enter
   on a lane gives its record.
5. As you go, write in `~/graphene-timeline/practice.md`, under these headings, to paste into Issues:
   - **Where the tree misread me:** the leaf, and what I meant.
   - **What I pruned or edited, and why.**
   - **What came back**, and whether its reason was fair.
   - **What the timeline showed** that the live row did not.
   - **What I looked for and could not find.**
6. At the end: `graphene plan record > ~/graphene-timeline/record.txt`, then `graphene plan archive`.

## The brief

1. **The three numbers**, before → after (`dev/process/timeline/before.md`, `after.md`):
   - Hand-backs over another leaf's file: 8 in last night's 10 trees, 6 over a test file → 4 in tonight's 13 trees,
     1 over a test file. The statements task: 20 of 22 leaves landed in three runs, none left unrun.
   - Nemotron proposals: 7 in 34 answers (21%) → 15 in 30 (50%) on the final schema; by ask with its one
     send-back, 7 in 19 → 15 in 20. Takes: 3 of 6 ran clean, take 6 landing every leaf; last night none of 19.
   - The feeds paragraph: a tree 1 time in 3 under `auto` → a tree, waiting for you, 3 times in 3 under `on`.
2. **Watch first:** `graphene demo tests/recordings/timeline-claude.jsonl`, Tab three times to `time`. Nemotron's
   first clean take: `graphene demo tests/recordings/timeline-nemotron-take-6.jsonl`. The GIF ends on the timeline.
3. **The bill:** $26.43 of $40 so far: `planner` $12.78 · `scopes` $8.45 · `takes` $2.10 · `first` $1.83 ·
   `timeline` $1.27.
4. **Decide:** 1. Keep `auto` at all? Default: yes, as the opt-in it is: under `on` Tuesday asks became trees 4
   times in 6, and `auto` is the one way a one-change ask runs with nothing to press. 2. Take 6 for the video?
   Default: yes, the first clean take. 3. Run the registered arms? Default: not yet: the doubled task still needs a
   commit named for them. Nothing the new check refused tonight looked like something you would have wanted.
5. **Broken or risky:** NETLINES The validator says one fault at a time, so a Nemotron
   answer with two ends the ask after its one send-back: most of tonight's misses. A glob is now read as written:
   `run --parallel` lets a carve-out run beside the leaf of the directory it leaves out.

---

Tonight's decisions are in `dev/DIRECTION.md`, 166 to 180. The evidence: `dev/process/timeline/` (`before.md`,
`after.md`, `takes.md`, `lane0.txt`, `screens/`).

## Branches

- `main`: `a96fb48`, untouched, local and on GitHub.
- `timeline`: the night, pushed; the PR is the only one.
- `timeline-before-shape`: the night's commits before 02:49, pushed so the builds the evidence names resolve.
  Delete it when you merge: `git push origin --delete timeline-before-shape`.
- In this run's clone only: `l1`, `l2`, `l3`, `l4` (the lanes, squashed into `timeline`), `off` (the offset).

## What was done, in order

- **00:13** Read the directive. Branch `timeline` from origin/main `a96fb48`, in a clone outside your checkout.
  The directive is committed at `dev/process/directives/TIMELINE_DIRECTIVE.md`.
- **00:20** The night's ledger: $40 cap. Nothing new starts past $35 (Graphene's own stop is 90%, $36: the
  run checks the bill before it starts anything). The session was not started with `GRAPHENE_AGENT_LIVE_USD`;
  the directive's $40 line is the opening, as decision 151 read last night's, so this run sets it to 40 for its
  own live commands.
- **00:30** Lane 0, from last night's records: `dev/process/timeline/before.md`.
- **00:34** The suite on `main` as it is: 1,631 passed, 21 skipped, in 17.6 minutes.
- **00:38** Ultra with a strict JSON schema, live: it answers JSON in the schema. With tools in the same request it
  calls no tool, so the schema goes on the final answer only. $0.0016.
- **00:42** Lanes 1 to 4 started, one builder each in a worktree of their own, each reviewed from two sides before
  it merges.
- **00:45** Token Factory reached, 4 NVIDIA models; Sandboxes work (`graphene key check`).
- **01:55** Lane 2 merged: the Nemotron planner answers in a strict JSON schema, tried by Graphene's own validator
  before it prints, sent back once with Graphene's words. Its review found one real fault (a node's goal of two
  lines was written as one), fixed with a test.
- **02:06** Lane 4 merged: the `time` view. Its review found one high and two medium faults (the pane hid its
  newest row; a pane of bare headings for an executor with no meter; a replay never drew the recording's person),
  all fixed with tests. Two more fixed after: an attempt the meter cannot read is a held bar, not an idle one, and
  a leaf that waits on you keeps its usual pane.
- **02:10** Lane 3 merged: plan first `on` for new repos, one row for a one-leaf proposal, the Claude Code
  planner's stream on the ledger. Its review found five medium faults (among them: `y` would start a paid run on
  the last leaf of a pruned tree), all fixed with tests.
- **02:14** Lane 1 merged before its review ended, to start the live work; its review's fixes follow.
- **02:16** The live measurements started on build `b4fbf60`.
- **02:18** The first Ultra ask proposed take 9's shape again: the tests leaf waited on the code, and the code's check
  ran the tests leaf's new file. The rule let it through. Stopped everything, refused that case (`4490656`), and
  started again. The stopped session's hold settled at its own turns' list price, $0.18.
- **02:22-02:46** Lane 1 measured: three statements runs (20 of 22 leaves landed, 1 hand-back over another leaf's
  test file), two feeds runs (6 of 6). Lane 3: the paragraph under `on` was a tree three times in three; one Tuesday
  ask was one row, `y`, done in 40 seconds.
- **02:24** Ultra with `anyOf` in a strict schema wrote spaces to the token limit; with `pattern` it broke a
  string. Types and enums hold. The schema stays plain.
- **02:40** Lane 2's first round: 10 proposals in 20 asks. 12 of 41 answers had stuck after the nodes, because the
  schema asked for `says` last. Fixed (`674754d`): `says` first, and a board item's unreadable id made readable.
  The second round started.
- **02:49** The history folded into 11 commits with the same tree, and `timeline` pushed; CI started. The commits
  before the fold are on `timeline-before-shape`, so every build named in the evidence resolves.
- **02:22-03:03** Six Nemotron takes: Ultra planned four; takes 1, 3 and 6 ran clean, take 6 landing every leaf (the
  first that has). `dev/process/timeline/takes.md`.
- **02:55** Lane 2's second round: 12 proposals in 20. The most common refusal on feeds was a board line naming a node
  the answer had not given an id yet: the schema asked for the board before the nodes. Fixed (`674b32c`): nodes first.
  The third round started.
- **03:00** The GIF again, on real agents, ending on the time view. Its planning session ($0.47, priced from its own
  turns) went on the ledger by hand: a `claude -p` session writes nothing to it.
- **03:13** Lane 1's review fixes ported (`32c6d4f`): a glob is read as written, a re-ask may write the paths of old
  leaves that stay, changed checks are judged last in one save, and the Nemotron planner's dry run is given what a
  merge replaces.
