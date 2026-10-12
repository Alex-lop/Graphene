#!/usr/bin/env bash
# X4: a real repository's open issue through the tree, on one build.
#
#   dev/process/prove/x4.sh <build-bin> <out-dir> <clone-dir> <sha> <issue-file> [parallel]
#
# A fresh copy of the pinned clone (no remote), `uv sync`, its venv first on PATH (what a person has), init with
# the X1 planner and the X2 executor line, `graphene ask` as the person with the issue's title and body, accept,
# `run --parallel 2`; afterwards the repo's own suite, the checks the planner wrote, red first's lines, what landed
# and what came back, the bill, and whether the venv's python imports the checkout from anywhere (the
# editable-install hole: a `python3 -m pytest` check in a clean worktree then tests the checkout, not the leaf).
set -euo pipefail
BIN=$1; OUT=$2; CLONE=$3; SHA=$4; ISSUE=$5; PAR=${6:-2}
export PATH="$BIN:$PATH"
export GH_CONFIG_DIR=$(mktemp -d) GH_TOKEN= GITHUB_TOKEN=
UNMARK="-u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_ENTRYPOINT -u AI_AGENT -u GRAPHENE_NODE -u GRAPHENE_PLANNER"
as_me() { env $UNMARK GRAPHENE_AS="person:$(id -un)" "$@"; }
ISO="--setting-sources project,local --strict-mcp-config"
PLANNER="claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format stream-json --verbose --model sonnet --max-budget-usd 1.5 --setting-sources project,local"
DEFAULT_WITH=$("$(dirname "$BIN")/graphene-map/bin/python" -c 'from graphene_map.run import DEFAULT_WITH; print(DEFAULT_WITH)')
EXEC="$DEFAULT_WITH --model sonnet"
case "$EXEC" in *--max-budget-usd*) ;; *) EXEC="$EXEC --max-budget-usd 2";; esac
case "$EXEC" in *--strict-mcp-config*) ;; *) EXEC="$EXEC --strict-mcp-config";; esac
case "$EXEC" in *--setting-sources*) ;; *) EXEC="$EXEC --setting-sources project,local";; esac
mkdir -p "$OUT"
REPO="$OUT/repo"
[ -e "$REPO" ] && { echo "$REPO exists; a run is never redone in place" >&2; exit 1; }
cp -R "$CLONE" "$REPO"
rm -rf "$REPO/.venv"  # the copied venv would still point at the clone it was built in
git -C "$REPO" remote -v | grep -q . && { echo "the clone still has a remote; refusing" >&2; exit 1; }
git -C "$REPO" checkout -q "$SHA"
git -C "$REPO" checkout -q -B x4 "$SHA"
( cd "$REPO" && uv sync -q ) > "$OUT/uv-sync.txt" 2>&1
export PATH="$REPO/.venv/bin:$PATH"
export VIRTUAL_ENV="$REPO/.venv"
{
  echo "build     $BIN"
  echo "graphene  $(graphene --version 2>&1 | tail -1)"
  echo "repo      $REPO at $SHA"
  echo "python3   $(command -v python3)"
  echo "editable  $(cd /tmp && python3 -c 'import importlib.metadata as m, json
for d in m.distributions():
    t = d.read_text("direct_url.json")
    if t and json.loads(t).get("dir_info", {}).get("editable"):
        print(d.metadata["Name"], json.loads(t)["url"])' 2>/dev/null | tr '\n' ';')"
  echo "imports   $(cd /tmp && python3 -c 'import importlib, os, sys, pathlib
pkg = next((p.name for p in pathlib.Path(sys.argv[1]).iterdir() if p.is_dir() and (p / "__init__.py").exists()), None)
m = importlib.import_module(pkg) if pkg else None
print(pkg, os.path.realpath(m.__file__) if m else None)' "$REPO/src")"
  echo "started   $(date -u +%FT%TZ)"
} | tee "$OUT/facts.txt"
cd "$REPO"
T0=$(date +%s)
as_me graphene init --planner "$PLANNER" --executor "$EXEC" > "$OUT/init.txt" 2>&1 || true
ASK_T0=$(date +%s)
as_me graphene ask "$(cat "$ISSUE")" > "$OUT/ask.txt" 2>&1; echo "ask exit $?" >> "$OUT/ask.txt"
echo "ask seconds $(( $(date +%s) - ASK_T0 ))" >> "$OUT/ask.txt"
as_me graphene plan --text > "$OUT/plan-proposed.txt" 2>&1 || true
as_me graphene plan accept > "$OUT/accept.txt" 2>&1 || true
RUN_T0=$(date +%s)
as_me graphene run --parallel "$PAR" > "$OUT/run.txt" 2>&1; echo "run exit $?" >> "$OUT/run.txt"
echo "run seconds $(( $(date +%s) - RUN_T0 ))" >> "$OUT/run.txt"
as_me graphene plan --text > "$OUT/plan-after.txt" 2>&1 || true
as_me graphene plan record > "$OUT/record.txt" 2>&1 || true
as_me graphene plan log > "$OUT/log.txt" 2>&1 || true
for id in $(grep -oE '^[a-z0-9-]+ (is done|handed back|landed)' "$OUT/run.txt" | awk '{print $1}' | sort -u); do
  as_me graphene node show "$id" > "$OUT/show-$id.txt" 2>&1 || true
done
git log --oneline --merges > "$OUT/merges.txt" 2>&1 || true
git log --format='%h %s' -20 > "$OUT/git-log.txt" 2>&1 || true
( uv run pytest -q 2>&1 | tail -5 ) > "$OUT/suite-after.txt" || true
echo "total seconds $(( $(date +%s) - T0 ))" >> "$OUT/facts.txt"
python3 - "$OUT" <<'PY'
import re, sys, pathlib
out = pathlib.Path(sys.argv[1])
run = (out / "run.txt").read_text(errors="replace")
ask = (out / "ask.txt").read_text(errors="replace")
plan = (out / "plan-proposed.txt").read_text(errors="replace")
lines = run.splitlines()
summary = {
    "ask exit": re.search(r"ask exit (\d+)", ask).group(1) if re.search(r"ask exit (\d+)", ask) else "?",
    "proposals by first answer": "no" if "again" in ask else "yes",
    "no proposal": "yes" if "no proposal" in ask else "no",
    "leaves proposed": len(re.findall(r"^\s*[?-] .*\[[a-z0-9-]+\]", plan, re.M)),
    "checks python3 -m pytest": plan.count("python3 -m pytest"),
    "checks uv run": plan.count("uv run"),
    "red first lines": [l for l in lines if "red first" in l or "would pass with nothing done" in l or "cannot run" in l or "editable" in l or "outside its scope" in l],
    "landed": [l.split()[0] for l in lines if re.match(r"^[a-z0-9-]+ (is done|landed)", l)],
    "came back": [l.split()[0] for l in lines if "handed back" in l],
    "last line": lines[-3] if len(lines) >= 3 else "",
}
for k, v in summary.items():
    print(f"{k}: {v}")
(out / "summary.md").write_text("\n".join(f"- **{k}**: {v}" for k, v in summary.items()) + "\n")
PY
