#!/usr/bin/env bash
# X2 arm (c) · Claude Code's /batch on the feeds paragraph, once, independent of the build. Gated on
# X0F=1 (the X0(f) probe found /batch runs headless); otherwise it says so and exits 0.
#
#   X0F=1 dev/process/prove/x2_batch.sh OUT [REPS]      REPS default 2; FAKE=1 spends nothing
#
# Per run, under OUT/runs/feeds-batch-<i>/: session1.json, where.txt (branches, worktrees, commits the
# session made), scratch/ (the repo with every unit branch merged in, which is what is scored),
# session2.json (the follow-up after the plant), seconds.txt, score.json. A stall or nothing is the result.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 1 ] || { sed -n '2,10p' "$0"; exit 2; }
[ "${X0F:-}" = 1 ] || { echo "X2(c) skipped: X0F is not 1 (the /batch probe did not run headless)"; exit 0; }
OUT=$(mkdir -p "$1/runs" && cd "$1" && pwd); REPS=${2:-2}
[ "${FAKE:-}" = 1 ] && export PATH="$PROVE/fake:$PATH"
FOLLOW="I broke something after your change: XML records now come out empty. Find it, fix it in the file that owns it, and say why."
FLAGS=(--model sonnet --permission-mode acceptEdits --output-format json --max-budget-usd 5
       --setting-sources project,local --strict-mcp-config
       --allowedTools Read Edit Write Glob Grep 'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)'
       Agent Task EnterWorktree ExitWorktree)
merge_units() {  # every branch but the one checked out, merged into scratch/; what would not merge is said
  local repo=$1 scratch=$2 head
  rm -rf "$scratch"; git clone -q "$repo" "$scratch"
  head=$(git -C "$repo" symbolic-ref --short -q HEAD || echo HEAD)
  for b in $(git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads/); do
    [ "$b" = "$head" ] && continue
    git -C "$scratch" fetch -q "$repo" "$b:$b" || true
    git -C "$scratch" merge -q --no-edit "$b" > /dev/null 2>&1 || { git -C "$scratch" merge --abort || true; echo "did not merge: $b"; }
  done
}
for i in $(seq 1 "$REPS"); do
  RUN="$OUT/runs/feeds-batch-$i"
  [ -e "$RUN" ] && { echo "$RUN exists; skipped"; continue; }
  stamp "x2 batch $i start"
  mkdir -p "$RUN/tmp"
  python3 "$TEST/make_task.py" feeds "$RUN/repo" | sed -n 's/^base  //p' > "$RUN/base.sha"
  : > "$RUN/runlog.jsonl"
  (
    cd "$RUN/repo"
    export TMPDIR="$RUN/tmp"
    python3 "$TEST/logline.py" "$RUN/runlog.jsonl" person prompt < "$TEST/tasks/feeds/paragraph.md" > /dev/null
    t0=$(date +%s)
    python3 "$PROVE/pgtimeout.py" 1800 env $UNMARK claude -p "/batch $(cat "$TEST/tasks/feeds/paragraph.md")" "${FLAGS[@]}" \
      > "$RUN/session1.json" 2> "$RUN/session1.err" || echo "exit $?" >> "$RUN/session1.err"
    python3 "$TEST/logline.py" "$RUN/runlog.jsonl" executor result --from-json "$RUN/session1.json" > /dev/null 2>&1 || true
    git add -A && git commit -qm "the session's change in place" --allow-empty
    { echo "branches:"; git for-each-ref --format='  %(refname:short) %(objectname:short) %(subject)' refs/heads/
      echo "worktrees:"; git worktree list; echo "commits since the base:"; git log --all --oneline "$(cat "$RUN/base.sha")..HEAD" --
    } > "$RUN/where.txt" 2>&1
    echo "main $(( $(date +%s) - t0 ))" >> "$RUN/seconds.txt"
  )
  merge_units "$RUN/repo" "$RUN/scratch" >> "$RUN/where.txt"
  (
    cd "$RUN/scratch"
    t1=$(date +%s)
    f=normalize/fields.py
    if grep -q '"code"' "$f"; then
      python3 -c 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_text(p.read_text().replace(chr(34)+"code"+chr(34), chr(34)+"xcode"+chr(34), 1))' "$f"
      echo "planted: code -> xcode in $f" > "$RUN/plant.txt"
    else
      printf '\n# planted: no "code" key here to break\n' >> "$f"; echo "planted: no code key in $f" > "$RUN/plant.txt"
    fi
    git add "$f" && git commit -qm "planted: the xml sku key" && git rev-parse HEAD >> "$RUN/plant.txt"
    SID=$(json_field "$RUN/session1.json" session_id || true)
    printf '%s' "$FOLLOW" | python3 "$TEST/logline.py" "$RUN/runlog.jsonl" person correction > /dev/null
    python3 "$PROVE/pgtimeout.py" 1200 env $UNMARK claude -p "$FOLLOW" ${SID:+--resume "$SID"} "${FLAGS[@]}" \
      > "$RUN/session2.json" 2> "$RUN/session2.err" || echo "exit $?" >> "$RUN/session2.err"
    python3 "$TEST/logline.py" "$RUN/runlog.jsonl" executor result --from-json "$RUN/session2.json" > /dev/null 2>&1 || true
    git add -A && git commit -qm "the session's fix" --allow-empty
    echo "plant $(( $(date +%s) - t1 ))" >> "$RUN/seconds.txt"
    python3 - "$RUN" "$f" > "$RUN/truth.json" <<'PY'
import json, pathlib, subprocess, sys
run, owner = pathlib.Path(sys.argv[1]), sys.argv[2]
repo = run / "scratch"
changed = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", "HEAD~1", "HEAD"], capture_output=True, text=True).stdout.split()
def field(name, key):
    try:
        return json.loads((run / name).read_text()).get(key)
    except Exception:
        return None
seconds = {k: int(v) for k, v in (l.split() for l in (run / "seconds.txt").read_text().splitlines() if len(l.split()) == 2)}
cost = [field(n, "total_cost_usd") for n in ("session1.json", "session2.json")]
print(json.dumps({"run": run.name, "fix_changed": changed, "fix_landed_in_owner": owner in changed,
                  "why_recorded": bool(field("session2.json", "result")), "said": (field("session2.json", "result") or "")[:600],
                  "dollars_total": round(sum(c for c in cost if isinstance(c, (int, float))), 4),
                  "denials": sum(len(field(n, "permission_denials") or []) for n in ("session1.json", "session2.json")),
                  "turns": sum(field(n, "num_turns") or 0 for n in ("session1.json", "session2.json")),
                  "seconds": seconds, "handed_back": [], "red_first": [],
                  "where": (run / "where.txt").read_text()[:2000]}, indent=2))
PY
  )
  "$PROVE/score.sh" "$RUN/scratch" "$(cat "$RUN/base.sha")" "$RUN/runlog.jsonl" prompt "$RUN" > /dev/null
  stamp "x2 batch $i done"
done
python3 "$PROVE/x2_table.py" "$OUT" | tee "$OUT/x2-batch.md"
