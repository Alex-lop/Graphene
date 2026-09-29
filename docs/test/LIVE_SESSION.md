# The live session: what waits for you, in order

Costs are list price by rung 1's live list (per million in/out: Nano $0.06/$0.24, Super $0.30/$0.90,
Ultra $1.00/$3.00), as ranges: a Nano call from $0.0001 (rung 2's three: 1,334-1,465 in, 98-191 out)
to $0.0015 (20,000 in, 1,000 out, late in a session); an Ultra ask $0.01-0.05 (5,000-20,000 in,
2,000-8,000 out). Sandboxes are $0 in the beta. Times are guesses. You type each command from the
repo root in your own terminal. Tonight each harness here ran only as far as its `--help` or usage
line; `newrun.sh` and `summarize.py` have none and did not run.

**Once.** (1) Sandboxes: `uv run --frozen --extra sandbox python -c "from graphene_map import
sandbox; print(sandbox.refused() or 'Sandboxes do not refuse this project')"`. A 403 prints the
refusal (ask at tokenfactory.nebius.com/sandboxes/about); rungs 3, 4, 6, 7 and every Sandbox leaf
wait on it. Offline it prints the second line too: rung 3 passing is the proof. (2) The key:
`NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID` in `~/.zshenv`, where rungs 1-2 read them. Every zsh reads
it, a stand-in's too. (3) The opening: `docs/test/practice.sh night` says whether
`GRAPHENE_AGENT_LIVE_USD` is set, and nothing else from the environment. Set for practice; `unset
GRAPHENE_AGENT_LIVE_USD` before registered runs (`evidence.py` refuses practice rows), and export
instead, where stand-ins inherit it, `GRAPHENE_LEDGER=~/graphene-bench/ledger.jsonl
GRAPHENE_SPEND_CAP_USD=50`.

**Rungs 3 to 7, rung 6 among them.** `docs/test/practice.sh` climbs the next rung not passed. Caps and
minutes (practice.py): 3 $0.50 3-8, 4 $0.05 2-5, 5 $0.50 2-5, 6 $3 15-40, 7 $3 10-30. Rung 6
(`practice.sh 6`, arm A as one leaf, then B′, on feeds) guessed at $0.02-1. Done: `practice.sh
status` says rung 6 PASS.

**Registered runs** (`results-2026-09-28-live-prereg.md`): feeds 5 each of A, B, B′ and C;
inventory, logs and report 3 each of A, B and B′, C at most once; one run at a time, arms rotating.
Three things come first and are not built: the fixed trees `docs/test/trees/{feeds,inventory}.plan`
(each passes `bench.py TASK --config NAME --executor 'nemotron …' --checks-only`), the frozen
configuration as a DIRECTION decision (it gives arm A's `--steps` and `--seconds`), and arm B's
brief on Nemotron (`standin.py`'s tree and board arms still run Claude Code). RUN is the directory
`newrun.sh` prints.
- **A**: `docs/test/newrun.sh RUNS feeds sealed nano 1`; a stand-in gets `docs/test/standin.py feeds
  sealed nano RUN VENV_BIN --steps N --seconds S`, which drives `arm_a.py`. $0.002-0.15 a run for N
  of 20-100 calls; at most S seconds.
- **B′**: `uv run --frozen --extra sandbox python docs/test/arm_bprime.py feeds --paragraph-file
  docs/test/tasks/feeds/paragraph.md --change-file docs/test/tasks/feeds/change.md --executor
  'nemotron …' --planner nemotron --ledger "$GRAPHENE_LEDGER" --run 1` (no change file for inventory
  or report). One or two asks, 4-10 leaves of 10-40 calls: $0.02-1 a run, B the same; up to an hour.
- **C**: `newrun.sh RUNS feeds sealed prompt 1`, `rm RUN/repo/.claude/settings.local.json`, the
  `standin.py … prompt` brief. Claude Code's bill: $0.45-1.54 a feeds run on 23 September
  (`runs-2026-09-23.json`), 4-10 min.
- After each: `uv run --frozen python docs/test/evidence.py add RUN --task feeds --arm A|B|B′|C`.
  Done: `evidence.py report --ledger "$GRAPHENE_LEDGER" --out docs/test/results-DATE-live.md` fills
  the table and draws `docs/assets/evidence.svg`. 14 A and 28 B or B′ runs: $0.60-30 in all.

**The shaping study with executors** (study 1 of `results-2026-09-28-shaping.md`): 4 tasks, arms
prompt, tree and board, n = 1. `newrun.sh ~/graphene-shaping-runs TASK sealed ARM 1`, then a
stand-in told to read and do `standin.py TASK sealed ARM RUN VENV_BIN`. Claude Code plans and
executes: 12 runs at $0.45-1.54, $5-19, 3-10 min each. Last time Claude Code's auto-mode classifier
refused each stand-in's `claude -p`: start them where it may run. Done: `docs/test/summarize.py
~/graphene-shaping-runs` prints 12 rows, none void.

**The final recording.** `docs/demo/build.sh --rehearsal` ($0, stand-ins), then
`docs/demo/build.sh`: rung 7's run filmed in real time, 10-30 min, a guessed $0.02-0.50. Done:
`docs/demo/rough.mp4`, which is written only when the run's recording says "as it ran, live".
