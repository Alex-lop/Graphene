# Running the shaping study (pre-registered in `results-2026-09-28-shaping.md`)

**Once, before any run, from the `shaping` checkout with the board and the graph views merged:**

    G=~/Desktop/AllThingsAgenticHackathon RUNS=~/graphene-shaping-runs V=~/graphene-shaping-venv
    mkdir -p $RUNS && uv build --wheel -o $RUNS/dist $G && uv venv -q $V && uv pip install -q --python $V/bin/python $RUNS/dist/*.whl
    (git -C $G rev-parse HEAD; shasum -a 256 $RUNS/dist/*.whl) > $RUNS/build.txt; export PATH=$V/bin:$PATH

- `graphene board --help` must list take, pick, drop, park, answer and note, and `graphene plan --view auto` must print. If a name differs, change `standin.py`'s board arm and `attention.py`'s `BOARD_CHOSEN` in one commit before any run, and name that commit in the results.
- `ls $G/dev/test/tasks/*/paragraph.md` must list four files; do not open them. Their blobs (`git -C $G ls-tree -r --abbrev=12 HEAD dev/test/tasks`) must match the pre-registration.
- Before the first run, write under "Deviations" in the results whether a tree runs while its board is unanswered, and whether `plan --text` prints the board. Both decide whether the outline arm is as it was on 23 September.

**Each task T, in order feeds, inventory, logs, report. A task's three arms start together:**

    for A in prompt tree board; do R=$RUNS/$T-sealed-$A-1
      bash $G/dev/test/newrun.sh $RUNS $T sealed $A 1
      [ $A = prompt ] && rm $R/repo/.claude/settings.local.json     # the paragraph arm runs free of the gate
      python3 $G/dev/test/standin.py $T sealed $A $R $V/bin > $R/brief.txt
    done

- **Stand-ins.** Spawn three fresh sub-agents at once, on the same model (write it into `build.txt`). Each gets exactly `Read <R>/brief.txt and do what it says. It is your whole brief.`
- Never open `brief.txt` yourself, since it holds the card, and never give a stand-in `PROTOCOL.md`, the directive or the results file. Wait for all three before starting the next task.
- **The judge,** after each outline and board run, is a fresh sub-agent with no part in the run. It gets `$G/dev/test/tasks/$T/intent.md`, the output of `python3 $G/dev/test/attention.py $R`, and `$R/runlog.jsonl`, whose `read` entries show the board and tree as they were shown.
- The judge rules on every dropped or edited node, and every board item answered with pick, answer or drop: *left as proposed, would it have cost a restart, or a wrong or unwanted result by the card?* It writes the verdict to `$R/judge.md`.

**Filling the table:**
1. Run `python3 $G/dev/test/summarize.py $RUNS --out $G/dev/test/runs-2026-09-28-shaping.json`. It runs tally, accept and quality, and prints every run's row.
2. A run whose `opening_is_sealed` is false is void: write the reason into `$R/void.txt` and run summarize again.
3. From each run's attention figures: typing = 0.28 × typed, acts = 1.35 × acts, reading = 0.24 × words read, keys = typed + acts, and candidates = `caught_before_code_n` plus the pick, answer and drop counts in `board_acts`.
4. Fill every cell of the pre-registered table, then the hypothesis rows, then the one sentence. Label anything else "after the fact".
