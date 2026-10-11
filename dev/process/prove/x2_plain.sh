#!/usr/bin/env bash
# X2 arm (b) · the plain session, once, independent of the build: feeds through one `claude -p` on
# Sonnet with the stand-in's flags, then the same plant and the same follow-up as a second message.
#
#   dev/process/prove/x2_plain.sh OUT [REPS]      REPS default 3; FAKE=1 spends nothing
#
# Per run, under OUT/runs/feeds-plain-<i>/: session1.json, session2.json (the follow-up), repo/,
# runlog.jsonl, seconds.txt, score.json. The follow-up sentence is the one every arm gets.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -ge 1 ] || { sed -n '2,9p' "$0"; exit 2; }
OUT=$(mkdir -p "$1/runs" && cd "$1" && pwd); REPS=${2:-3}
[ "${FAKE:-}" = 1 ] && export PATH="$PROVE/fake:$PATH"
FOLLOW="I broke something after your change: XML records now come out empty. Find it, fix it in the file that owns it, and say why."
FLAGS=(--model sonnet --permission-mode acceptEdits --output-format json --max-budget-usd 3
       --setting-sources project,local --strict-mcp-config
       --allowedTools Read Edit Write Glob Grep 'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)')
for i in $(seq 1 "$REPS"); do
  RUN="$OUT/runs/feeds-plain-$i"
  [ -e "$RUN" ] && { echo "$RUN exists; skipped"; continue; }
  stamp "x2 plain $i start"
  mkdir -p "$RUN/tmp"
  python3 "$TEST/make_task.py" feeds "$RUN/repo" | sed -n 's/^base  //p' > "$RUN/base.sha"
  : > "$RUN/runlog.jsonl"
  (
    cd "$RUN/repo"
    export TMPDIR="$RUN/tmp"
    python3 "$TEST/logline.py" "$RUN/runlog.jsonl" person prompt < "$TEST/tasks/feeds/paragraph.md" > /dev/null
    t0=$(date +%s)
    plain_claude -p "$(cat "$TEST/tasks/feeds/paragraph.md")" "${FLAGS[@]}" > "$RUN/session1.json" 2> "$RUN/session1.err" || echo "exit $?" >> "$RUN/session1.err"
    python3 "$TEST/logline.py" "$RUN/runlog.jsonl" executor result --from-json "$RUN/session1.json" > /dev/null 2>&1 || true
    git add -A && git commit -qm "the session's change" --allow-empty
    echo "main $(( $(date +%s) - t0 ))" >> "$RUN/seconds.txt"
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
    if [ -n "$SID" ]; then
      plain_claude -p "$FOLLOW" --resume "$SID" "${FLAGS[@]}" > "$RUN/session2.json" 2> "$RUN/session2.err" || echo "exit $?" >> "$RUN/session2.err"
    else
      plain_claude -p "$FOLLOW" "${FLAGS[@]}" > "$RUN/session2.json" 2> "$RUN/session2.err" || echo "exit $?" >> "$RUN/session2.err"
    fi
    python3 "$TEST/logline.py" "$RUN/runlog.jsonl" executor result --from-json "$RUN/session2.json" > /dev/null 2>&1 || true
    git add -A && git commit -qm "the session's fix" --allow-empty
    echo "plant $(( $(date +%s) - t1 ))" >> "$RUN/seconds.txt"
    # what only the contract records: did the fix land in the file that owns it, and is why said anywhere
    python3 - "$RUN" "$f" > "$RUN/truth.json" <<'PY'
import json, pathlib, subprocess, sys
run, owner = pathlib.Path(sys.argv[1]), sys.argv[2]
repo = run / "repo"
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
                  "seconds": seconds, "handed_back": [], "red_first": []}, indent=2))
PY
  )
  "$PROVE/score.sh" "$RUN/repo" "$(cat "$RUN/base.sha")" "$RUN/runlog.jsonl" prompt "$RUN" > /dev/null
  stamp "x2 plain $i done"
done
python3 "$PROVE/x2_table.py" "$OUT" | tee "$OUT/x2-plain.md"
