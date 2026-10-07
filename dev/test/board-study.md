# Running study 4, the board after lane C (registered in `results-2026-09-29-board.md`)

**Once, before any run, from a clean checkout at the lane's final code commit.** `G` stays in place
until every judge is done, because each run's `env.sh` logs through `$G/dev/test/logline.py`.

    G=<that checkout> RUNS=$HOME/graphene-board4-runs V=$HOME/graphene-board4-venv
    [ -z "$(git -C $G status --porcelain)" ] || echo "not clean: the wheel would not be the commit"
    mkdir -p $RUNS && uv build --wheel -o $RUNS/dist $G && uv venv -q $V && uv pip install -q --python $V/bin/python $RUNS/dist/*.whl
    W=$(ls $RUNS/dist/*.whl); printf 'commit %s\nwheel %s\nsha256 %s\nstand-ins: %s, judges the same\n' \
      "$(git -C $G rev-parse HEAD)" "$(basename $W)" "$(shasum -a 256 $W | cut -d' ' -f1)" claude-opus-5-5 > $RUNS/build.txt
    for T in feeds inventory logs report; do cp -R $HOME/graphene-shaping3-runs/$T-shape-planned $RUNS/; done
    export PATH=$V/bin:$PATH

Write the stand-ins' real model into `build.txt` if it is not claude-opus-5-5. Copy `build.txt` into
the results' "Deviations" before the first run.

**Pre-run checks.** Each must pass, or no run starts:
- `command -v graphene` prints `$V/bin/graphene`, and `graphene --version` prints the wheel's version.
- `for c in take pick drop park unpark answer note lookup; do graphene board --help | grep -qw $c || echo "missing $c"; done` prints nothing.
- `for T in feeds inventory logs report; do diff -r $HOME/graphene-shaping3-runs/$T-shape-planned $RUNS/$T-shape-planned; done` prints nothing.
- The copied stores open on this build. In a throwaway copy, so the planned directories stay study 3's bytes:
  `for T in feeds inventory logs report; do C=$(mktemp -d)/$T; cp -R $RUNS/$T-shape-planned $C; (cd $C/repo && graphene plan > /dev/null && echo "$T tree: $(graphene plan --text | wc -l) lines" && graphene board --all > /dev/null && ! graphene config | grep -q '^board: *auto') || echo "$T FAILS"; rm -rf $C; done`
- `ls $G/dev/test/tasks/*/paragraph.md` lists four files, never opened. `git -C $G ls-tree -r --abbrev=12 HEAD dev/test/tasks | grep -E '/(intent|paragraph)\.md$'` shows the blobs in the registration.
- `echo ${GRAPHENE_SHAPE:-unset}` prints `unset`.

**Each task T, in order feeds, inventory, logs, report. A task's two arms start together:**

    T=feeds     # then inventory, then logs, then report
    cd $G; for A in outline board; do R=$RUNS/$T-shape-$A-1
      SHAPE_RUNS=$RUNS SHAPE_BIN=$V/bin SHAPE_STUDY=4 python3 dev/test/shape_only.py fork $T $A
      SHAPE_RUNS=$RUNS SHAPE_BIN=$V/bin SHAPE_STUDY=4 python3 dev/test/shape_only.py brief $T $A > $R/brief.txt
    done

- **Stand-ins.** Two fresh sub-agents at once, on the model in `build.txt`. Each gets exactly
  `Read <R>/brief.txt and do what it says. It is your whole brief.` Never open `brief.txt`: it holds
  the paragraph and the card. Never give a stand-in this file, the results file or the directive.
- **What a stand-in may use** is only what `brief.txt` gives: `source <R>/env.sh`; `as_me`, `did` and
  `seen`; `command -v graphene`; its arm's graphene commands (outline: `plan --text`, `plan`, `plan
  accept`, `node drop`, `node set`; board: `board`, `board pick|drop|park|answer|note`, `plan --view
  auto`, and the same three prune commands); and reading files in its repo through `seen`. It logs
  every act and every screen to `<R>/runlog.jsonl` through `did` and `seen`, writes `<R>/notes.md`
  where it would press R, and hands back at most ten lines.
- **The judge,** after each run, is a fresh sub-agent with no part in it. Its brief is the text under
  "The judge's brief" in the results file, whole, with `<G>`, `<T>` and `<R>` filled in. It writes
  `<R>/judge.md`. Wait for both judges before the next task.
- Never commit anything under `$RUNS`: `brief.txt` and `judge.md` hold the card.

**Void checks (rule 4), after the eight runs.** Every line must show `env 1`, `runs 0`, `started 0`
and `dirty 0`, and the two runs of a task must show one `base`:

```sh
for R in $RUNS/*-shape-*-1; do echo "$(basename $R) env $(grep -c "$V/bin" $R/env.sh) base $(cut -c1-12 $R/base.sha)" \
  "runs $(python3 -c 'import json,re,sys; print(sum(1 for l in open(sys.argv[1]) if l.strip() for e in [json.loads(l)] if e.get("type") == "run" or e.get("type") != "read" and re.search(r"graphene (run|ask)\b|board lookup|\bclaude\b", str(e.get("text")))))' $R/runlog.jsonl)" \
  "started $(sqlite3 -readonly $R/repo/.graphene/graphene.db "select count(*) from node_log where kind='started'")" \
  "dirty $(git -C $R/repo status --porcelain | wc -l | tr -d ' ')"; done
shasum -a 256 $RUNS/dist/*.whl     # matches build.txt
```

**The table.** As studies 2 and 3 computed it: `attention.py` per run, `--arm tree` for outline and
`--arm board` for board, then each run's parts. The ruling and constraints met are `judge.md`'s first
two lines. Run on study 3's logs, these lines print study 3's table.

```sh
for R in $RUNS/*-shape-outline-1; do python3 $G/dev/test/attention.py $R --arm tree > $R/attention.json; done
for R in $RUNS/*-shape-board-1; do python3 $G/dev/test/attention.py $R --arm board > $R/attention.json; done
python3 - $RUNS/*-shape-*-1/attention.json <<'EOF'
import json, sys
for p in sys.argv[1:]:
    a = json.load(open(p)); t, k, w = a["typed_chars"], a["acts"], a["read_words"]
    print(p.split("/")[-2], f'{a["modelled_seconds"]} = {0.28 * t:.1f} + {1.35 * k:.1f} + {w * 60 / 250:.1f}',
          "typed", t, "acts", k, "keys", t + k, "read", w, a["board_acts"],
          [n for n in a["notes"] if not n.startswith("no `")])  # that nothing started is expected
EOF
for R in $RUNS/*-shape-*-1; do echo "$(basename $R): $(head -2 $R/judge.md | tr '\n' ' ')"; done
```

Fill every cell of the registered table, then the hypothesis rows, then the decision rows by the rule
as written, then the one sentence. Label anything else "after the fact". The decision goes into
`dev/DIRECTION.md`.
