"""The zero-spend automation baseline: every tactic on every goal, 60 s of wall clock each.

Writes Auto/Baseline.lean (one theorem per goal x tactic, each run through `attempt`, see
Harness.lean), runs it in ONE Lean process (Mathlib is loaded once), and turns what it printed into
Auto/baseline.md. A cell whose tactic reported "closed" is only counted closed when `#print axioms`
on its theorem shows nothing beyond propext, Classical.choice and Quot.sound.

    python3 Auto/run.py                       # every goal, every tactic
    python3 Auto/run.py --goals root,euclid --tactics omega,grind --out Auto/Rerun
    python3 Auto/run.py --project $HAMMERS --tactics duper,canonical --out Auto/Hammers
    python3 Auto/run.py --parse logs/baseline-....log   # rebuild the table from a log

The process as a whole has a backstop (subprocess timeout): a tactic that ignores the cancellation
token would otherwise hang the run. What the backstop killed is reported as "no result".
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # the Lean project
SECS = 60
STANDARD = {"propext", "Classical.choice", "Quot.sound"}

# (label, hypotheses (the needs' statements), statement, what it is)
GOALS: list[tuple[str, list[str], str, str]] = [
    ("root", [], "S_root", "whole theorem, as asked"),
    ("root_set", [], "S_root_set", "whole theorem, Set.Infinite form"),
    ("prime_mod_four", [], "S_prime_mod_four", "leaf"),
    ("mul_one_mod_four", [], "S_mul_one_mod_four", "leaf"),
    ("factor_three_mod_four", ["S_prime_mod_four", "S_mul_one_mod_four"], "S_factor_three_mod_four",
     "leaf (the key lemma)"),
    ("factor_three_mod_four_bare", [], "S_factor_three_mod_four", "the key lemma without its needs"),
    ("euclid_mod_four", [], "S_euclid_mod_four", "leaf (N subtraction)"),
    ("not_dvd_euclid", [], "S_not_dvd_euclid", "leaf (N subtraction)"),
    ("dvd_factorial", [], "S_dvd_factorial", "leaf"),
    ("euclid", ["S_factor_three_mod_four", "S_euclid_mod_four", "S_not_dvd_euclid", "S_dvd_factorial"],
     "S_root", "leaf (the argument)"),
    ("set_form", ["S_root"], "S_root_set", "leaf"),
    ("odd_factor_three", [], "S_odd_factor_three", "seeded: FALSE at n = 5"),
    ("euclid_mod_four_any", [], "S_euclid_mod_four_any", "seeded: FALSE at P = 0"),
    ("even_three_mod_four", [], "S_even_three_mod_four", "seeded: VACUOUS"),
]  # fmt: skip
# column -> the tactic as typed. The first eight are the directive's list plus simp_all (simp that uses
# the hypotheses); the next two are core's local library-suggestion relatives of a hammer; the hammers
# (Duper, Canonical) need the hammers project (--project, see the README).
TACTICS = {
    "decide": "decide", "norm_num": "norm_num", "simp": "simp", "simp_all": "simp_all", "omega": "omega",
    "aesop": "aesop", "exact?": "exact?", "grind": "grind", "grind+suggestions": "grind +suggestions",
    "try?": "try?", "duper": "duper [*]", "canonical": "canonical 55",
}  # fmt: skip
DEFAULT = "decide,norm_num,simp,simp_all,omega,aesop,exact?,grind,grind+suggestions,try?"


def ident(label: str, tactic: str) -> str:
    return "t_" + label + "__" + re.sub(r"\W", "_", tactic)


def lean_file(
    goals: list[tuple[str, list[str], str, str]],
    tactics: list[str],
    imports: list[str],
    harness: str = "Auto.Harness",
) -> str:
    out = [*(f"import {m}" for m in imports), f"import {harness}", "",
           "set_option Elab.async false", "set_option maxHeartbeats 0", ""]  # fmt: skip
    if "exact?" in tactics:  # the first exact? builds its index of Mathlib: pay that once, apart
        warm = ident("warmup", "exact?")
        out += [f'theorem {warm} : (2 : ℕ) ∣ 4 := by attempt "warmup/exact?" 300 (exact?)',
                f"#print axioms {warm}", ""]  # fmt: skip
    for label, needs, stmt, _ in goals:
        names = [f"h{i}" for i in range(len(needs))]
        typ = " → ".join([*needs, stmt])
        prelude = f"intro {' '.join(names)}; " if names else ""
        prelude += "".join(f"unfold {n} at {h}; " for n, h in zip(needs, names, strict=True))
        prelude += f"unfold {stmt}; "
        for tac in tactics:
            name = ident(label, tac)
            run = f'attempt "{label}/{tac}" {SECS} ({TACTICS[tac]})'
            out.append(f"theorem {name} : {typ} := by {prelude}{run}")
            out.append(f"#print axioms {name}")
        out.append("")
    return "\n".join(out)


def parse(log: str) -> dict[str, dict]:
    """label/tactic -> {status, ms, hb, why, axioms, found}. Lean prints a command's own messages (a
    `Try this`) before the lines the harness wrote during it, so a suggestion belongs to the START
    that follows it."""
    cells: dict[str, dict] = {}
    text = log
    pending = None  # the suggestion seen since the last START
    want_next = False  # "Try this:" alone on its line: the suggestion is the next line
    for line in text.splitlines():
        if want_next and line.strip():
            pending, want_next = line.strip().removeprefix("[apply] "), False
        elif line.startswith("START "):
            label = line[6:].strip()
            cells[label] = {"status": "timeout"}
            if pending:
                cells[label]["found"], pending = pending, None
        elif line.startswith("RESULT "):
            _, label, status, ms, *rest = line.split(" ", 4) + [""] * 1
            cell = cells.setdefault(label, {})
            cell.update(status=status, ms=int(ms))
            if status == "closed":
                cell["hb"] = int(rest[0]) if rest and rest[0].strip().isdigit() else None
            else:
                cell["why"] = " ".join(rest).strip()
        elif line.startswith(("Try this:", "Try these:")):
            said = line.split(":", 1)[1].strip()
            if said:
                pending = said.removeprefix("[apply] ")
            else:
                want_next = True
    # '#print axioms' reports may wrap over several lines
    flat = re.sub(r"\n\s+", " ", text)
    report = r"'(t_\w+|warmup)' (depends on axioms: \[([^\]]*)\]|does not depend on any axioms)"
    for m in re.finditer(report, flat):
        name, axioms = m.group(1).replace("warmup", ident("warmup", "exact?")), m.group(3)
        found = {a.strip() for a in axioms.split(",")} if axioms else set()
        for label, cell in cells.items():
            if "/" in label and ident(*label.split("/", 1)) == name:
                cell["axioms"] = found
    return cells


def cell_text(cell: dict | None) -> str:
    if not cell:
        return "no result"
    if cell["status"] == "timeout":
        return f"timed out (>{SECS} s)"
    secs = cell["ms"] / 1000
    if cell["status"] == "closed":
        if "axioms" not in cell:
            return f"closed {secs:.1f} s (axioms not printed)"
        extra = sorted(cell["axioms"] - STANDARD)
        if extra:
            return f"**closed?** {secs:.1f} s but axioms {', '.join(extra)}"
        return f"**closed** {secs:.1f} s"
    why = cell.get("why", "").replace("|", "\\|")
    why = why if len(why) <= 90 else why[:87] + "..."
    return f"failed {secs:.1f} s: {why}"


def short(cell: dict | None) -> str:
    """One cell of the compact table: closed (seconds), x failed, T timed out, closed? with bad axioms."""
    if not cell:
        return "-"
    if cell["status"] == "timeout":
        return "T"
    if cell["status"] == "closed":
        extra = cell.get("axioms", STANDARD) - STANDARD
        return f"closed? {cell['ms'] / 1000:.1f}" if extra else f"**{cell['ms'] / 1000:.2f}**"
    return "x"


def compact(cells: dict[str, dict], goals: list, tactics: list[str]) -> str:
    rows = ["| goal | " + " | ".join(tactics) + " |", "|---|" + "---|" * len(tactics)]
    for label, *_ in goals:
        rows.append(f"| `{label}` | " + " | ".join(short(cells.get(f"{label}/{t}")) for t in tactics) + " |")
    return "\n".join(rows) + "\n"


def table(cells: dict[str, dict], goals: list, tactics: list[str]) -> str:
    rows = ["| goal | what | " + " | ".join(f"`{t}`" for t in tactics) + " |",
            "|---|---|" + "---|" * len(tactics)]  # fmt: skip
    for label, _, _, what in goals:
        rows.append(f"| `{label}` | {what} | "
                    + " | ".join(cell_text(cells.get(f"{label}/{t}")) for t in tactics) + " |")  # fmt: skip
    found = [(k, c["found"]) for k, c in cells.items() if c.get("found")]
    if found:
        rows += ["", "What `exact?` (and any other `Try this`) found:", ""]
        rows += [f"- `{k}`: `{v}`" for k, v in found]
    warm = cells.get("warmup/exact?")
    if warm:
        rows += ["", f"The first `exact?` in the process (index build, on `2 ∣ 4`): {cell_text(warm)}."]
    return "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals", default="")
    ap.add_argument("--tactics", default=DEFAULT)
    ap.add_argument("--imports", default="Challenge,Seeded")
    ap.add_argument("--out", default="Auto/Baseline")
    ap.add_argument("--project", default=str(HERE), help="a Lake project with Auto/Harness.lean")
    ap.add_argument("--parse", default="")
    ap.add_argument("--harness", default="Auto.Harness", help="the harness's module name in --project")
    ap.add_argument(
        "--lake-lean",
        action="store_true",
        help="run with `lake lean` (it loads precompiled dynlibs, which Canonical needs)",
    )
    args = ap.parse_args()
    wanted = set(filter(None, args.goals.split(",")))
    goals = [g for g in GOALS if not wanted or g[0] in wanted]
    tactics = [t for t in args.tactics.split(",") if t]
    os.chdir(HERE)
    logs = HERE / "logs"
    if args.parse:
        cells = parse(Path(args.parse).read_text())
        print(compact(cells, goals, tactics) + "\n" + table(cells, goals, tactics))
        return 0
    project = Path(args.project).resolve()
    src = project / (args.out + ".lean")
    src.write_text(lean_file(goals, tactics, args.imports.split(","), args.harness))
    log = logs / f"{Path(args.out).name.lower()}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log.parent.mkdir(exist_ok=True)
    backstop = len(goals) * len(tactics) * (SECS + 5) + 900
    env = {**os.environ, "PATH": f"{Path.home()}/.elan/bin:{os.environ['PATH']}"}
    t0 = time.monotonic()
    with log.open("w") as fh:
        runner = ["lake", "lean"] if args.lake_lean else ["lake", "env", "lean"]
        proc = subprocess.Popen([*runner, str(src)], stdout=fh, stderr=subprocess.STDOUT,
                                env=env, cwd=project, start_new_session=True)  # fmt: skip
        try:
            code = proc.wait(timeout=backstop)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, 9)
            code = "killed by the backstop"
    wall = time.monotonic() - t0
    text = log.read_text()
    md = HERE / "Auto" / (Path(args.out).name.lower() + ".md")
    md.write_text(f"Run {time.strftime('%Y-%m-%d %H:%M')}; {len(goals)} goals x {len(tactics)} tactics, "
                  f"{SECS} s each; one Lean process, {wall:.0f} s wall, exit {code}; "
                  f"log {log.relative_to(HERE)}; project {project.name}.\n\n"
                  + compact(cells := parse(text), goals, tactics) + "\n"
                  + table(cells, goals, tactics))  # fmt: skip
    print(md.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
