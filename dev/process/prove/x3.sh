#!/usr/bin/env bash
# X3 · ten questions about a finished run: Graphene's record (arm A) against git plus the agents' last words
# (arm B), read by one Sonnet reader per arm, scored by script against truth.json.
#
#   dev/process/prove/x3.sh BIN X2_OUT OUT      X2_OUT holds runs/feeds-sealed-x2-*/ (planted X2 runs on that build)
#
# Per run, under OUT/<run>/: armA.txt and armB.txt (what each reader was given), armA.json and armB.json (the
# reader's answers in x3_schema.json), truth.json (copied), fix.json (the fix merge's files, from git). Arm A is
# `graphene plan record`, `graphene node show` for every leaf, `graphene plan log`, `git log --graph --oneline`,
# and `graphene node diff ID --stat` where the build has it. Arm B is `git log -p base..HEAD` (merge bodies
# included) and each attempt's final result text from the executors' own run logs. x3_score.py OUT ends it.
. "$(dirname "$0")/common.sh"
[ $# -ge 3 ] || { sed -n '2,11p' "$0"; exit 2; }
use_build "$1"; X2OUT=$(cd "$2" && pwd); OUT=$(mkdir -p "$3" && cd "$3" && pwd)
PROMPT=$(cat "$PROVE/x3_prompt.md"); SCHEMA=$(cat "$PROVE/x3_schema.json")
stamp "x3 start: $BIN on $X2OUT"
for RUN in "$X2OUT"/runs/feeds-sealed-x2-*; do
  [ -f "$RUN/truth.json" ] || continue
  name=$(basename "$RUN"); D="$OUT/$name"; mkdir -p "$D"; repo="$RUN/repo"; base=$(cat "$RUN/base.sha")
  cp "$RUN/truth.json" "$D/truth.json"
  ( cd "$repo"
    { echo "===== graphene plan record ====="; me graphene plan record 2>&1
      for id in $(me graphene plan --json --all 2>/dev/null | python3 -c 'import json,sys; ns=json.load(sys.stdin).get("nodes",[]); print(" ".join(n["id"] for n in ns if not any(m.get("parent")==n["id"] for m in ns)))'); do
        echo "===== graphene node show $id ====="; me graphene node show "$id" 2>&1
        if me graphene node diff "$id" --stat > "$D/.diff-$id" 2>&1; then echo "===== graphene node diff $id --stat ====="; cat "$D/.diff-$id"; fi
      done
      echo "===== graphene plan log ====="; me graphene plan log 2>&1
      echo "===== git log --graph --oneline ====="; git log --graph --oneline 2>&1
    } > "$D/armA.txt"
    { echo "===== git log -p $base..HEAD ====="; git log -p "$base..HEAD" 2>&1 | head -c 120000
      echo; echo "===== the executors' last words, one per attempt (from their own run logs) ====="
      python3 - "$repo" <<'PY'
import json, pathlib, sys
runs = pathlib.Path(sys.argv[1]) / ".graphene" / "runs"
for p in sorted(runs.glob("*.txt")) if runs.exists() else []:
    last = None
    for line in p.read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "result":
            last = ev
    if last is not None:
        print(f"--- {p.name}: {(last.get('result') or '')[:3000]}")
PY
    } > "$D/armB.txt"
  )
  python3 - "$repo" "$D" <<'PY'
import json, pathlib, subprocess, sys
repo, d = sys.argv[1], pathlib.Path(sys.argv[2])
truth = json.loads((d / "truth.json").read_text())
fix = None
reopened = {r["node"] for r in truth.get("reopened", [])}
for m in truth.get("merges", []):
    if m.get("id") in reopened and truth.get("planted_at") and m.get("at", 0) >= truth["planted_at"]:
        fix = m
sha = (fix or {}).get("sha") or (fix or {}).get("commit") or (fix or {}).get("hash")
files = []
if sha:
    files = subprocess.run(["git", "-C", repo, "diff", "--name-only", f"{sha}^1", sha], capture_output=True, text=True).stdout.split()
(d / "fix.json").write_text(json.dumps({"merge": fix, "sha": sha, "files": files}, indent=1))
PY
  for arm in A B; do
    [ -s "$D/arm$arm.json" ] && continue
    stamp "x3 $name arm $arm reader"
    python3 "$PROVE/pgtimeout.py" 600 env $UNMARK claude -p --model sonnet --tools '' --json-schema "$SCHEMA" $ISO --max-budget-usd 0.5 \
      --output-format json -- "$PROMPT

$(cat "$D/arm$arm.txt")" > "$D/arm$arm.json" 2> "$D/arm$arm.err" < /dev/null || true
  done
done
python3 "$PROVE/x3_score.py" "$OUT" | tee "$OUT/x3.md"
