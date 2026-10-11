#!/usr/bin/env bash
# X5 · the editable-install hole, with no model and at $0: a src-layout fixture installed editable by
# `uv sync`, two leaves, a fake executor that breaks the leaf's function in its worktree and calls done.
#
#   dev/process/prove/x5.sh BIN OUT
#
# Three combinations, each in a fresh fixture under OUT/<combo>/: (1) checks `python3 -m pytest` with
# the fixture's .venv/bin first on PATH; (2) checks `uv run pytest`, the same PATH; (3) `python3 -m pytest`
# with PATH=/usr/bin:/bin plus the build's bin (no pytest anywhere). Per combination: did a land, did b
# land (git log --merges), red first's lines verbatim, attempts, hand-backs. Writes OUT/x5.md.
# Leaf a owns src/pkg/__init__.py and its check names tests/ (outside its scope); leaf b owns
# src/pkg/b.py and tests/test_b.py and its check names only its own test file.
set -euo pipefail
. "$(dirname "$0")/common.sh"
[ $# -eq 2 ] || { sed -n '2,12p' "$0"; exit 2; }
use_build "$1"; OUT=$(mkdir -p "$2" && cd "$2" && pwd)
EXEC="python3 $PROVE/x5_exec.py"
fixture() {  # fixture DIR CHECK_A CHECK_B : a src-layout project, editable in its own .venv, committed
  local dir=$1
  mkdir -p "$dir/src/pkg" "$dir/tests"
  cat > "$dir/pyproject.toml" <<'TOML'
[project]
name = "pkg"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = []

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pkg"]
TOML
  printf 'def add(a, b):\n    return a + b\n' > "$dir/src/pkg/__init__.py"
  printf 'def mul(a, b):\n    return a * b\n' > "$dir/src/pkg/b.py"
  printf 'from pkg import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n' > "$dir/tests/test_add.py"
  printf 'from pkg.b import mul\n\n\ndef test_mul():\n    assert mul(2, 3) == 6\n' > "$dir/tests/test_b.py"
  printf '.venv/\n__pycache__/\n.pytest_cache/\n' > "$dir/.gitignore"
  (cd "$dir" && git init -q -b main && uv sync -q && git add -A && git commit -qm "a src-layout package, installed editable")
}
combo() {  # combo NAME CHECK_A CHECK_B PATH
  local name=$1 check_a=$2 check_b=$3 path=$4
  local dir="$OUT/$name"
  [ "$path" = "@VENV@" ] && path="$dir/.venv/bin:$BIN:$PATH"  # the fixture's own venv first: an activated venv
  [ -e "$dir" ] && { echo "$dir exists; skipped"; return; }
  stamp "x5 $name start"
  fixture "$dir"
  (
    cd "$dir"
    export PATH="$path"
    {
      echo "PATH=$PATH"; echo "python3: $(command -v python3 || echo none) ($(python3 --version 2>&1))"
      echo "pytest: $(python3 -c 'import pytest; print(pytest.__version__)' 2>&1 | tail -1)"
      echo "direct_url.json: $(cat .venv/lib/python3*/site-packages/pkg-*.dist-info/direct_url.json 2>/dev/null || echo none)"
    } > info.txt
    me graphene init --planner "$EXEC" --executor "$EXEC" > init.txt 2>&1 || true
    me graphene node add "a: add" --id a --scope src/pkg/__init__.py --check "$check_a" --goal "keep add correct" > add.txt 2>&1
    me graphene node add "b: mul" --id b --scope src/pkg/b.py --scope tests/test_b.py --check "$check_b" --goal "keep mul correct" >> add.txt 2>&1
    me graphene plan accept > accept.txt 2>&1 || true
    # the executor asks the check's own interpreter where pkg comes from, in its worktree, before done
    case "$check_a" in uv\ run*) probe="uv run python -c 'import pkg; print(pkg.__file__)'" ;;
                       *) probe="python3 -c 'import pkg; print(pkg.__file__)'" ;; esac
    X5_PROBE="$probe" X5_ORIGIN="$dir/origin.txt" me graphene run --with "$EXEC" --parallel 2 > run.txt 2>&1 || echo "exit=$?" >> run.txt
    git log --merges --format='%h %s' > merges.txt
    me graphene plan > plan.txt 2>&1 || true
    me graphene plan log > log.txt 2>&1 || true
    "$TOOLPY" "$PROVE/check_rows.py" . > checks.txt 2>&1 || true  # every check's output, whole
  )
  stamp "x5 $name done"
}
combo python3-venv "python3 -m pytest -q tests" "python3 -m pytest -q tests/test_b.py" "@VENV@"
combo uvrun-venv "uv run pytest -q tests" "uv run pytest -q tests/test_b.py" "@VENV@"
combo python3-bare "python3 -m pytest -q tests" "python3 -m pytest -q tests/test_b.py" "/usr/bin:/bin:$BIN"
python3 - "$OUT" > "$OUT/x5.md" <<'PY'
import pathlib, re, sys
out = pathlib.Path(sys.argv[1])
print(f"# X5 · the editable-install hole ({out})\n")
print("| combination | a landed | b landed | pkg imported from (in the worktree) | hand-backs | attempts | red first |")
print("|---|---|---|---|---|---|---|")
for d in sorted(p for p in out.iterdir() if p.is_dir()):
    run = (d / "run.txt").read_text(errors="replace") if (d / "run.txt").exists() else ""
    merges = (d / "merges.txt").read_text() if (d / "merges.txt").exists() else ""
    origin = (d / "origin.txt").read_text(errors="replace") if (d / "origin.txt").exists() else ""
    where = "<br>".join(sorted({("the checkout" if "/worktrees/" not in l.split("pkg imported from ")[-1] else "its worktree")
                                + (" (" + l.split(" in ")[0] + ")") for l in origin.splitlines() if "imported from" in l}))
    red = "<br>".join(l.strip() for l in run.splitlines() if l.startswith("red first") or ": its check" in l)
    print(f"| {d.name} | {'yes' if '(a)' in merges else 'no'} | {'yes' if '(b)' in merges else 'no'} | {where or '?'} | "
          f"{run.count('handed back')} | {len(re.findall(r'attempt \\d+:', run))} | {red or 'none'} |")
for d in sorted(p for p in out.iterdir() if p.is_dir()):
    print(f"\n## {d.name}\n")
    for name in ("info.txt", "origin.txt", "run.txt", "merges.txt", "log.txt", "checks.txt"):
        if (d / name).exists():
            print(f"### {name}\n```\n{(d / name).read_text(errors='replace').rstrip()}\n```")
    for log in sorted((d / ".graphene" / "runs").glob("*.txt")):  # each attempt's executor output, whole
        print(f"### {log.name}\n```\n{log.read_text(errors='replace').rstrip()[-1500:]}\n```")
PY
cat "$OUT/x5.md"
