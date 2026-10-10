#!/usr/bin/env bash
# X7 · plan first auto against on, for decision 176: a Claude Code session with the hooks installed is given
# the feeds paragraph and a typo ask under each mode, and the plan's log says what each mode did with it.
#
#   dev/process/prove/x7.sh BIN OUT [REPS] [X4_CLONE X4_SHA]      REPS default 3; FAKE=1 spends nothing
#
# The session is auto_live.py's (dev/test/auto_live.py: acceptEdits, its TOOLS allowed, --max-turns 25, the
# isolation flags, a $1.50 cap, Sonnet) so a denial is never counted as a mode. Per run, under
# OUT/runs/<repo>-<mode>-<ask>-<i>/: stream.jsonl, plan.txt, plan.json, log.txt, board.txt, status.txt, row.json.
# With X4_CLONE and X4_SHA, one typo ask per mode also runs on that repository (WIDE was tuned on feeds).
# x7.md ends it: per mode and ask, how many runs reached the person as a tree, how many were taken at once, dollars.
. "$(dirname "$0")/common.sh"
[ $# -ge 2 ] || { sed -n '2,11p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2/runs" && cd "$2" && pwd); REPS=${3:-3}; X4CLONE=${4:-}; X4SHA=${5:-}
PLANNER="claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model sonnet --max-budget-usd 1.5 $ISO"
WITH=$("$TOOLPY" -c 'from graphene_map.run import DEFAULT_WITH; print(DEFAULT_WITH)')
for flag in "--model sonnet" "--max-budget-usd 2" "--strict-mcp-config" "--setting-sources project,local"; do
  case " $WITH " in *" ${flag%% *} "*) ;; *) WITH="$WITH $flag" ;; esac
done
TOOLS=(Read Edit Write Glob Grep 'Bash(graphene *)' 'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)')
PARAGRAPH=$(cat "$TEST/tasks/feeds/paragraph.md")
TYPO="fix the typo in the README's first heading"
stamp "x7 start: $BIN, $REPS a cell"

session() {  # session REPO MODE PROMPT RUN: one Claude Code session in REPO, the plan's state after it
  local repo=$1 mode=$2 prompt=$3 run=$4
  mkdir -p "$run"
  ( cd "$repo" && me graphene init --planner "$PLANNER" --executor "$WITH" > "$run/init.txt" 2>&1 || true
    me graphene plan first "$mode" > "$run/first.txt" 2>&1 || true )
  local t0; t0=$(date +%s)
  ( cd "$repo" && python3 "$PROVE/pgtimeout.py" 900 env $UNMARK claude -p "$prompt" --model sonnet --permission-mode acceptEdits \
      --output-format stream-json --verbose --max-turns 25 $ISO --max-budget-usd 1.5 --allowedTools "${TOOLS[@]}" \
      > "$run/stream.jsonl" 2> "$run/stream.err" < /dev/null ) || true
  echo "$(( $(date +%s) - t0 ))" > "$run/seconds.txt"
  ( cd "$repo"
    me graphene plan --text --all > "$run/plan.txt" 2>&1 || true
    me graphene plan --json --all > "$run/plan.json" 2>&1 || true
    me graphene plan log > "$run/log.txt" 2>&1 || true
    me graphene board > "$run/board.txt" 2>&1 || true
    git status --short > "$run/status.txt" 2>&1 || true )
  python3 - "$run" "$mode" "$prompt" <<'PY'
import json, re, sys, pathlib
run, mode, prompt = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
def read(name):
    p = run / name
    return p.read_text(errors="replace") if p.exists() else ""
log, plan, board, status = read("log.txt"), read("plan.txt"), read("board.txt"), read("status.txt")
try:
    nodes = json.loads(read("plan.json")).get("nodes", [])
except Exception:
    nodes = []
cost = turns = None
for line in read("stream.jsonl").splitlines():
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") == "result":
        cost, turns = ev.get("total_cost_usd"), ev.get("num_turns")
leaves = [n for n in nodes if not any(m.get("parent") == n["id"] for m in nodes)]
row = {
    "mode": mode, "ask": "typo" if prompt.startswith("fix the typo") else "paragraph",
    "nodes": len(nodes), "leaves": len(leaves), "states": sorted({n.get("state") for n in nodes}),
    "widths": [len(n.get("scope") or []) for n in leaves],
    "board_open": int(m.group(1)) if (m := re.search(r"the board: (\d+) open", board)) else 0,
    "taken_at_once": ("by their prompt" in log) or ("one-line ask" in log),
    "waited_for_person": any(n.get("state") == "proposed" for n in nodes),
    "wrote": any(s.strip() for s in status.splitlines()),
    "done": any(n.get("state") == "done" for n in nodes),
    "turns": turns, "dollars": round(cost or 0, 4), "seconds": int(read("seconds.txt") or 0),
}
(run / "row.json").write_text(json.dumps(row, indent=1))
print(json.dumps(row))
PY
}

for mode in auto on; do
  for i in $(seq 1 "$REPS"); do
    for ask in paragraph typo; do
      RUN="$OUT/runs/feeds-$mode-$ask-$i"
      [ -e "$RUN" ] && { echo "$RUN exists; skipped"; continue; }
      bash "$TEST/newrun.sh" "$OUT/runs" feeds sealed "x7$mode$ask" "$i" > "$OUT/runs/.newrun-$mode-$ask-$i.txt" 2>&1
      REPO="$OUT/runs/feeds-sealed-x7$mode$ask-$i/repo"
      if [ "$ask" = paragraph ]; then P="$PARAGRAPH"; else P="$TYPO"; fi
      stamp "x7 $mode $ask $i start"
      session "$REPO" "$mode" "$P" "$RUN"
      stamp "x7 $mode $ask $i done"
    done
  done
  if [ -n "$X4CLONE" ]; then
    RUN="$OUT/runs/x4-$mode-typo-1"
    if [ ! -e "$RUN" ]; then
      REPO="$OUT/runs/x4-$mode-repo"; cp -R "$X4CLONE" "$REPO"; rm -rf "$REPO/.venv"
      git -C "$REPO" remote -v | grep -q . && { echo "the X4 clone still has a remote; refusing" >&2; exit 1; }
      git -C "$REPO" checkout -q -B x7 "$X4SHA"
      stamp "x7 $mode x4 typo start"
      session "$REPO" "$mode" "$TYPO" "$RUN"
      stamp "x7 $mode x4 typo done"
    fi
  fi
done
python3 - "$OUT" <<'PY' | tee "$OUT/x7.md"
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
print(f"# X7 · plan first auto against on ({out})\n")
print("| repo | mode | ask | n | reached the person as a tree | taken at once | done in the session | leaves (widths) | board items | dollars (median) |")
print("|---|---|---|---|---|---|---|---|---|---|")
cells = {}
for p in sorted((out / "runs").iterdir()):
    if not (p / "row.json").exists():
        continue
    r = json.loads((p / "row.json").read_text())
    repo = "x4" if p.name.startswith("x4-") else "feeds"
    cells.setdefault((repo, r["mode"], r["ask"]), []).append(r)
for (repo, mode, ask), rs in sorted(cells.items()):
    n = len(rs)
    tree = sum(1 for r in rs if r["waited_for_person"])
    taken = sum(1 for r in rs if r["taken_at_once"])
    done = sum(1 for r in rs if r["done"])
    leaves = ", ".join(f"{r['leaves']} {r['widths']}" for r in rs)
    board = ", ".join(str(r["board_open"]) for r in rs)
    dollars = sorted(r["dollars"] for r in rs)[len(rs) // 2]
    print(f"| {repo} | {mode} | {ask} | {n} | {tree} of {n} | {taken} of {n} | {done} of {n} | {leaves} | {board} | ${dollars:.3f} |")
print("\nA run 'reached the person as a tree' when a proposed node waits in the plan after the session; 'taken at once' when the")
print("log says the ask was accepted by their prompt or as a one-line ask. Every session is Sonnet with auto_live.py's argv.")
PY
