#!/usr/bin/env python3
"""The live pre-registration's table, its hypothesis rows and its chart, from the run rows and the ledger.

    uv run python dev/test/evidence.py add <run-dir> --task T --arm A|B|B′|C [--rows FILE] [--tasks DIR]
    uv run python dev/test/evidence.py report --ledger FILE [--rows FILE] [--out FILE] [--svg FILE]
        [--task feeds] [--stand-in]

`add` counts one run, once, afterwards, and appends one row to --rows. <run-dir> is what newrun.sh,
arm_bprime.py or bench.py made: repo/, base.sha and runlog.jsonl, and void.txt when a fairness rule
voided the run (its text is the reason). From tally.py: accept.py's and quality.py's passed and failed
(only the counts are kept: a hidden check's name is the check), wall seconds, restarts, files outside
intent, forks and escalations. From attention.py: the modelled person-seconds, as the arm's tally arm
(A and C as `prompt`, B and B′ as `tree`). From the store (B, B′): landed, handed back and failed as
bench.py counts them, and every usage row. From arm-a.json beside the repo (A): arm_a.py's bill.

`report` fills the table and the hypothesis rows exactly as results-2026-09-28-live-prereg.md lays
them out, in markdown (--out, or printed), and draws --svg (docs/assets/evidence.svg by default).

- Each cell is every run's value in run order (by the run log's first entry), then the range, as
  results.py prints them. A void run is `void` in its cells and in no range or comparison. A cell no
  run reached says `not run`; a cell the pre-registration marks n/a stays n/a.
- **Dollars come from the ledger**: the ledger rows whose `at` falls between the run log's first and
  last entry (PROTOCOL.md rule 10: one run at a time on the machine). A run's dollars are `unknown`,
  never $0, when it has an unpriced attempt, when the ledger holds a different number of calls in
  that window than the run's usage rows count (a call no usage row holds, or one from something else),
  or when a ledger row falls in two runs' windows, or when the run has no usage row at all. C's
  dollars are Claude Code's own total, from the run log, and C is never charted.
- **"Higher" or "lower" only when the ranges do not overlap** (every run of one arm at or past every
  run of the other, and the medians differ); anything else is `no difference shown at n = …`, and a
  comparison with no runs on one side is `not tested`. Nothing here runs a significance test.
- **It refuses rows that are not live**: an A, B or B′ row with no usage row, or with one whose
  endpoint is not "token factory", a B or B′ row with an attempt that has no usage row of its own (a
  leaf run by an executor that writes none), and a C row with no Claude Code total, stop the report
  (exit 2) and name the runs, unless --stand-in is given; then the table's heading and the chart's
  title say STAND-IN, NOT LIVE, and name why. Nothing ties a C row to a real Claude Code session
  beyond that total, and the live heading says so.
- **It refuses practice, whatever the flags**: a run whose usage rows, or whose ledger rows in its window,
  say `practice` (made while GRAPHENE_AGENT_LIVE_USD was set: nemotron/night.py) is not added, and a
  report with one stops (exit 2), --stand-in or not. Practice is live, so STAND-IN would be false, and it
  never enters a registered table.

The chart is one task (--task, feeds by default): arms A, B and B′, each run a dot and the median a
bar, in hidden acceptance, held-out quality, modelled person-seconds and dollars, every axis from
zero. It is a plain SVG written here, with no dependency.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402
import tally  # noqa: E402
from attention import attention  # noqa: E402
from results import money, passed, spread  # noqa: E402

ARMS = ("A", "B", "B′", "C")
SPELLED = {"A": "A", "B": "B", "B′": "B′", "B'": "B′", "Bprime": "B′", "bprime": "B′", "C": "C"}
TALLY_ARM = {"A": "prompt", "B": "tree", "B′": "tree", "C": "prompt"}
TREE = ("B", "B′")  # the arms with leaves, forks and escalations
TASKS = ("feeds", "inventory", "logs", "report")  # the pre-registered order
QUALITY = ("feeds",)  # the tasks with a quality.py
LIVE = "token factory"
ROWS = HERE / "evidence.jsonl"
SVG = HERE.parent / "assets" / "evidence.svg"


# -- add: one run, counted -----------------------------------------------------------------------------


def _store(db: Path) -> list[tuple[str, str, dict]]:
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT node_id, kind, detail FROM node_log WHERE kind IN ('usage', 'attempt')")
    out = [(node, kind, json.loads(detail) if detail else {}) for node, kind, detail in rows.fetchall()]
    conn.close()
    return out


def count(run: Path, task: str, arm: str, tasks: Path) -> dict:
    """One row: every number the table needs, for one run."""
    card, repo = tasks / task, run / "repo"
    argv = [
        sys.executable,
        str(HERE / "tally.py"),
        str(repo),
        "--base",
        (run / "base.sha").read_text().strip(),
        "--intent",
        str(card / "intent_globs.txt"),
        "--accept",
        str(card / "accept.py"),
        "--arm",
        TALLY_ARM[arm],
        "--runlog",
        str(run / "runlog.jsonl"),
    ]
    if (card / "quality.py").is_file():
        argv += ["--quality", str(card / "quality.py")]
    t = json.loads(subprocess.run(argv, capture_output=True, text=True, check=True).stdout)
    seen = attention(run, TALLY_ARM[arm])
    lines = (run / "runlog.jsonl").read_text(encoding="utf-8").splitlines()
    stamps = [
        s for s in (tally.seconds(json.loads(ln).get("t")) for ln in lines if ln.strip()) if s is not None
    ]

    def counts(said: dict | None) -> dict | None:
        if said is None:
            return None
        return {k: said.get(k, 0) for k in ("passed", "failed")} | {"error": bool(said.get("error"))}

    logged = _store(repo / ".graphene" / "graphene.db")
    bills = [d for _, kind, d in logged if kind == "usage"]
    unpriced = t["executor_calls_unpriced"]
    if arm in TREE:  # as bench.py counts it: an attempt with no usage row of its own (tally would call every
        # Nemotron attempt unpriced, since its .graphene/runs/ text is not Claude Code's JSON)
        tries: dict[str, list[int]] = {}
        for node, kind, _ in logged:
            if node != "*":
                tries.setdefault(node, [0, 0])[kind == "usage"] += 1
        unpriced = sum(max(0, attempts - used) for attempts, used in tries.values())
    said = run / "arm-a.json"
    if arm == "A" and said.exists():
        bills.append(json.loads(said.read_text(encoding="utf-8")))
    row = {
        "task": task,
        "arm": arm,
        "run": run.name,
        "dir": str(run.resolve()),
        "void": (run / "void.txt").read_text(encoding="utf-8").strip() if (run / "void.txt").exists() else "",
        "t0": min(stamps, default=None),
        "t1": max(stamps, default=None),
        "accept": counts(t["acceptance"]),
        "quality": counts(t.get("quality")),
        "modelled_seconds": seen["modelled_seconds"],
        "person_acts": seen["acts"],
        "typed_chars": seen["typed_chars"],
        "read_words": seen["read_words"],
        "wall_seconds": t["wall_seconds"],
        "restarts": t["restarts"],
        "restarts_unmandated": t["restarts_unmandated"],
        "files_outside_intent": t["files_outside_intent_final"],
        "forks": t["forks"] if arm in TREE else None,
        "escalations": t["escalations"] if arm in TREE else None,
        "usage_calls": sum(int(b.get("calls") or 0) for b in bills),
        "endpoints": sorted({str(b.get("endpoint") or "no endpoint recorded") for b in bills}),
        "prompt_versions": sorted({str(b["prompt"]) for b in bills if b.get("prompt") is not None}),
        "unpriced": unpriced,
        "practice": any(b.get("practice") for b in bills),
        "claude_cost_usd": t["executor_cost_usd"] if arm == "C" else None,
        "counted_by": bench.graphene_sha(),
    }
    if arm in TREE:
        outcomes = [r["outcome"] for r in bench.leaf_rows(repo, run / "runlog.jsonl", {}, set())]
        row |= {k.replace(" ", "_"): outcomes.count(k) for k in ("landed", "handed back", "failed")}
    return row


# -- report: the table, the hypotheses, the chart ------------------------------------------------------


def why_not_live(r: dict) -> list[str]:
    """Nothing when the row is live: A, B and B′ with every usage row from Token Factory and, in B and B′,
    no attempt without one (a leaf run by an executor that writes none); C with Claude Code's own total."""
    if r["arm"] == "C":
        return [] if r["claude_cost_usd"] is not None else ["no Claude Code total"]
    said = [] if r["endpoints"] == [LIVE] else r["endpoints"] or ["no usage row"]
    return said + (["an attempt with no usage row"] if r["arm"] in TREE and r["unpriced"] else [])


def practice(rows: list[dict], ledger: list[dict]) -> list[str]:
    """The runs made under the person's opening, each with how it says so: no registered table takes one."""
    said = []
    for r in rows:
        if r.get("practice"):
            said.append(f"{r['task']} {r['arm']} {r['run']}: its usage rows say practice")
        elif r["t0"] is not None and any(
            e.get("practice") and r["t0"] <= float(e.get("at") or 0) <= r["t1"] for e in ledger
        ):
            said.append(f"{r['task']} {r['arm']} {r['run']}: the ledger's rows in its window say practice")
    return said


def not_live(rows: list[dict]) -> list[dict]:
    return [r for r in rows if why_not_live(r)]


def dollars(rows: list[dict], ledger: list[dict]) -> dict[str, float | str]:
    """Each run's dollars, by its directory: from the ledger in its window, or `unknown` (see the top)."""
    spend = [(k, float(e.get("at") or 0), float(e.get("dollars") or 0)) for k, e in enumerate(ledger)]
    within = {
        r["dir"]: [s for s in spend if r["t0"] is not None and r["t0"] <= s[1] <= r["t1"]]
        for r in rows
        if r["arm"] != "C"
    }
    seen: dict[tuple, int] = {}
    for found in within.values():
        for s in found:
            seen[s] = seen.get(s, 0) + 1
    out: dict[str, float | str] = {}
    for r in rows:
        if r["arm"] == "C":
            out[r["dir"]] = (
                "unknown" if r["unpriced"] or r["claude_cost_usd"] is None else r["claude_cost_usd"]
            )
        elif r["unpriced"] or any(seen[s] > 1 for s in within[r["dir"]]):
            out[r["dir"]] = "unknown"
        elif not r["usage_calls"] or len(within[r["dir"]]) != r["usage_calls"]:
            out[r["dir"]] = "unknown"
        else:
            out[r["dir"]] = round(sum(d for _, _, d in within[r["dir"]]), 6)
    return out


def valid(rs: list[dict]) -> list[dict]:
    return [r for r in rs if not r["void"]]


def all_passed(said: dict | None) -> bool:
    return bool(said) and not said["error"] and not said["failed"] and bool(said["passed"])


def checks(rs: list[dict], key: str) -> str:
    """`5 · void · 6 of 6 (5–6)`: passed per run, of the total, as results.spread shows landed."""
    values = [
        "void"
        if r["void"]
        else "none"
        if r[key] is None
        else "error"
        if r[key]["error"]
        else r[key]["passed"]
        for r in rs
    ]
    totals = sorted(
        {r[key]["passed"] + r[key]["failed"] for r in valid(rs) if r[key] and not r[key]["error"]}
    )
    return spread(values, "/".join(map(str, totals)))


def number(v: float) -> str:
    return f"{v:g}"


def cells(task: str, arm: str, rs: list[dict], cost: dict) -> list[str]:
    na = "n/a"
    quality = task in QUALITY
    tree = arm in TREE
    if not rs:
        return [
            "0",
            "not run",
            "not run",
            "not run" if quality else na,
            *["not run"] * 4,
            *["not run" if tree else na] * 3,
        ]
    void = len(rs) - len(valid(rs))

    def each(f, fmt=number) -> str:
        return spread(["void" if r["void"] else f(r) for r in rs], fmt=fmt)

    return [
        str(len(rs)) + (f" ({void} void)" if void else ""),
        checks(rs, "accept"),
        " · ".join("void" if r["void"] else "yes" if all_passed(r["accept"]) else "no" for r in rs),
        checks(rs, "quality") if quality else na,
        each(lambda r: r["modelled_seconds"]),
        each(lambda r: cost[r["dir"]], fmt=money),
        each(lambda r: r["wall_seconds"]),
        each(lambda r: r["restarts"]) + "; unmandated " + each(lambda r: r["restarts_unmandated"]),
        " · ".join("void" if r["void"] else f"{r['landed']}/{r['handed_back']}/{r['failed']}" for r in rs)
        if tree
        else na,
        each(lambda r: r["forks"]) if tree else na,
        each(lambda r: r["escalations"]) if tree else na,
    ]


def compare(ours: list[float], theirs: list[float], names: tuple[str, str]) -> str:
    """Rule 2: higher or lower only when the ranges do not overlap and the medians differ."""
    if not ours or not theirs:
        return f"not tested (no {names[0] if not ours else names[1]} runs)"
    differ = statistics.median(ours) != statistics.median(theirs)
    if differ and min(ours) >= max(theirs):
        return "higher"
    if differ and max(ours) <= min(theirs):
        return "lower"
    n = f"n = {len(ours)}" if len(ours) == len(theirs) else f"n = {len(ours)} and {len(theirs)}"
    return f"no difference shown at {n}"


def registered(result: str, direction: str) -> str:
    if result not in ("higher", "lower"):
        return result
    which = "the registered direction" if result == direction else "against the registered direction"
    return f"{result} ({which})"


def value(r: dict, key: str, cost: dict) -> float | None:
    """One valid run's number: an erroring check passed nothing; a check not run, an unknown cost: None."""
    if key in ("accept", "quality"):
        return None if r[key] is None else 0 if r[key]["error"] else r[key]["passed"]
    if key == "dollars":
        return None if isinstance(cost[r["dir"]], str) else cost[r["dir"]]
    return r[key]


def values(rs: list[dict], key: str, cost: dict) -> list[float]:
    """The numbers a comparison is made of: the valid runs' values that are known."""
    return [v for v in (value(r, key, cost) for r in valid(rs)) if v is not None]


def hypotheses(by: dict, cost: dict) -> list[tuple[str, str, str]]:
    def c(task: str, key: str, a: str, b: str, direction: str) -> str:
        said = compare(values(by[task, a], key, cost), values(by[task, b], key, cost), (a, b))
        return registered(said, direction)

    def h1(task: str) -> str:
        said = f"accept: {c(task, 'accept', 'B', 'A', 'higher')}"
        return said + (f"; quality: {c(task, 'quality', 'B', 'A', 'higher')}" if task in QUALITY else "")

    def h3(task: str) -> str:
        said = f"accept: {c(task, 'accept', 'B', 'B′', 'higher')}"
        return said + (f"; quality: {c(task, 'quality', 'B', 'B′', 'higher')}" if task in QUALITY else "")

    def h2(task: str) -> str:
        return f"person-seconds: {c(task, 'modelled_seconds', 'B', 'A', 'lower')}"

    def per_accepted(arm: str) -> str:
        rs = valid(by["feeds", arm])
        if not rs:
            return f"{arm}: no runs"
        full = [r for r in rs if all_passed(r["accept"])]
        if any(isinstance(cost[r["dir"]], str) for r in rs):
            return f"{arm}: unknown (a run's cost is unknown)"
        if not full:
            return f"{arm}: no fully accepted run (0 of {len(rs)})"
        each = money(sum(cost[r["dir"]] for r in rs) / len(full))
        return f"{arm}: {each} ({len(full)} of {len(rs)} fully accepted)"

    b, cc = values(by["feeds", "B"], "accept", cost), values(by["feeds", "C"], "accept", cost)
    within = (
        "not tested"
        if not b or not cc
        else (
            f"B's accept ({min(b)}–{max(b)} passed) is "
            f"{'within' if min(cc) <= min(b) and max(b) <= max(cc) else 'not within'} "
            f"C's range ({min(cc)}–{max(cc)})"
        )
    )
    return [
        ("H1", "feeds, B against A, accept and quality", h1("feeds")),
        ("H2", "feeds, B against A, person-seconds", h2("feeds")),
        ("H3", "feeds, B against B′, accept and quality", h3("feeds")),
        (
            "H4",
            "inventory, logs, report: H1 to H3 each",
            " · ".join(f"{t}: H1 {h1(t)}; H2 {h2(t)}; H3 {h3(t)}" for t in TASKS[1:]),
        ),
        (
            "H5",
            "feeds, B against C, dollars per fully accepted run; accept",
            f"dollars per fully accepted run: {per_accepted('B')}; {per_accepted('C')}. {within}",
        ),
    ]


def grouped(rows: list[dict]) -> tuple[list[str], dict]:
    tasks = [*TASKS, *sorted({r["task"] for r in rows} - set(TASKS))]
    by = {(t, a): [] for t in tasks for a in ARMS}
    for r in sorted(rows, key=lambda r: r["t0"] or 0):
        by[r["task"], r["arm"]].append(r)
    return tasks, by


def table(rows: list[dict], cost: dict, source: str, stand_in: list[str]) -> str:
    tasks, by = grouped(rows)
    head = (
        "| task | arm | runs | accept (passed/total per run) | all passed | quality | person-s (modelled) | "
        "dollars | wall s | restarts (unmandated) | landed / handed back / failed | forks | escalations |"
    )
    out = [
        "# The paragraph against the tree: the table",
        "",
        f"**STAND-IN, NOT LIVE:** these rows came from {', '.join(stand_in)}, not from Token Factory. "
        "Nothing here is evidence for the pre-registration's hypotheses."
        if stand_in
        else "Stand-in people with live models (rule 9): every A, B and B′ row's usage came from Token "
        "Factory, and every B and B′ attempt has a usage row of its own. A C row is counted when its run "
        "log holds Claude Code's own total; nothing else here checks that Claude Code ran it.",
        "",
        f"Generated by `dev/test/evidence.py` from {source}, as `results-2026-09-28-live-prereg.md` lays "
        "the table out: each cell is every run's value in run order, then the range. Dollars are the "
        "ledger's rows in each run's window, and C's are Claude Code's own total.",
        "",
        head,
        "|" + "---|" * 13,
    ]
    for t in tasks:
        if t not in TASKS and not any(by[t, a] for a in ARMS):
            continue
        for a in ARMS:
            out.append("| " + " | ".join([t, a, *cells(t, a, by[t, a], cost)]) + " |")
    out += [
        "",
        "Runs on a task past the four (item 5's real repository) are reported and are not part of the "
        "hypotheses."
        if any(t not in TASKS for t in tasks)
        else "",
        "",
        "| hypothesis | comparison | result (higher / lower / no difference shown / not tested) |",
        "|---|---|---|",
        *(f"| {h} | {what} | {said} |" for h, what, said in hypotheses(by, cost)),
        "",
        "One sentence on what the tables show, whatever it is, goes under them by hand; no number is typed.",
    ]
    return "\n".join(line for k, line in enumerate(out) if line or out[k - 1]) + "\n"


# -- the chart -----------------------------------------------------------------------------------------

STYLE = """
.surface{fill:#fcfcfb}.ink{fill:#0b0b0b}.ink2{fill:#52514e}.grid{stroke:#e4e3df}.median{stroke:#0b0b0b}
.A{fill:#2a78d6}.B{fill:#eb6834}.Bp{fill:#1baf7a}.dot{stroke:#fcfcfb;stroke-width:2}
@media (prefers-color-scheme: dark){.surface{fill:#1a1a19}.ink{fill:#ffffff}.ink2{fill:#c3c2b7}
.grid{stroke:#3a3a37}.median{stroke:#ffffff}.A{fill:#3987e5}.B{fill:#d95926}.Bp{fill:#199e70}
.dot{stroke:#1a1a19}}
text{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif}
"""
CLASS = {"A": "A", "B": "B", "B′": "Bp"}
LEGEND = {
    "A": "the paragraph to Nano, no tree",
    "B": "Graphene, the person prunes",
    "B′": "Graphene, every proposal accepted whole",
}


def text(
    cls: str, x: float, y: float, size: int, words: str, anchor: str = "start", bold: bool = False
) -> str:
    weight = ' font-weight="600"' if bold else ""
    return (f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}"{weight}>'
            f"{html.escape(words)}</text>")  # fmt: skip


def line(cls: str, x1: float, x2: float, y: float, width: int) -> str:
    return (
        f'<line class="{cls}" x1="{x1:.1f}" x2="{x2:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke-width="{width}"/>'
    )


def chart(rows: list[dict], cost: dict, task: str, stand_in: list[str], source: str) -> str:
    _, by = grouped(rows)
    panels = [
        ("hidden acceptance", "checks passed", "accept"),
        ("held-out quality", "checks passed", "quality"),
        ("your attention", "person-seconds, modelled", "modelled_seconds"),
        ("dollars", "at list price", "dollars"),
    ]
    width, height, left, top, plot_h, pw, gap = 960, 440, 88, 132, 210, 166, 66
    title = f"The same paragraph to Nemotron, with the tree and without: {task}"
    if stand_in:
        title = "STAND-IN, NOT LIVE: " + title
        sub = f"These rows came from {', '.join(stand_in)}, not Token Factory. They show the chart works."
    else:
        sub = (
            "Live Nemotron on Token Factory; the people are stand-ins. Each dot is a run, the bar the median."
        )
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" role="img" aria-label="{html.escape(title)}">',
        f"<style>{STYLE}</style>",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        text("ink", left - 64, 36, 19, title, bold=True),
        text("ink2", left - 64, 60, 13, sub),
        text(
            "ink2",
            left - 64,
            80,
            13,
            "Every axis starts at zero. C, Claude Code, is a reference point and is "
            "never drawn beside these arms.",
        ),  # fmt: skip
    ]
    for k, (name, unit, key) in enumerate(panels):
        x0, base = left + k * (pw + gap), top + plot_h
        out += [text("ink", x0, top - 22, 14, name, bold=True), text("ink2", x0, top - 6, 12, unit)]
        if key == "quality" and task not in QUALITY:
            out.append(text("ink2", x0, top + plot_h / 2, 12, "n/a for this task"))
            continue
        runs = {a: [(r, value(r, key, cost)) for r in valid(by[task, a])] for a in CLASS}
        known = {a: [(r, v) for r, v in pairs if v is not None] for a, pairs in runs.items()}
        totals = [r[key]["passed"] + r[key]["failed"] for pairs in runs.values() for r, _ in pairs
                  if key in ("accept", "quality") and r[key] and not r[key]["error"]]  # fmt: skip
        most = max([*totals, *(v for pairs in known.values() for _, v in pairs)], default=0) or 1

        def y(v: float) -> float:
            return base - plot_h * v / most  # noqa: B023  (each panel's own scale, used within it)

        for v in (0, most):
            shown = money(v) if key == "dollars" else number(round(v, 1))
            out += [line("grid", x0, x0 + pw, y(v), 1), text("ink2", x0 - 6, y(v) + 4, 11, shown, "end")]
        for j, a in enumerate(CLASS):
            cx, pairs = x0 + pw * (j + 0.5) / 3, known[a]
            out.append(text("ink", cx, base + 20, 13, a, "middle"))
            if not pairs:
                out.append(
                    text("ink2", cx, base - 8, 11, "none drawn" if by[task, a] else "no runs", "middle")
                )
            else:
                out.append(line("median", cx - 20, cx + 20, y(statistics.median(v for _, v in pairs)), 2))
            step = min(8.0, 40.0 / max(1, len(pairs)))
            for i, (r, v) in enumerate(pairs):
                shown = money(v) if key == "dollars" else number(v)
                dx, said = (i - (len(pairs) - 1) / 2) * step, html.escape(f"{a} · {r['run']}: {shown}")
                out.append(f'<circle class="dot {CLASS[a]}" cx="{cx + dx:.1f}" cy="{y(v):.1f}" r="5">'
                           f"<title>{said}</title></circle>")  # fmt: skip
            missing = [("void", len(by[task, a]) - len(runs[a])), ("unknown", len(runs[a]) - len(pairs))]
            said = ", ".join(f"{n} {w}" for w, n in missing if n)
            if said:
                out.append(text("ink2", cx, base + 36, 11, said, "middle"))
    for k, (a, said) in enumerate(LEGEND.items()):
        out.append(f'<circle class="dot {CLASS[a]}" cx="{left - 58 + 300 * k}" cy="{height - 48}" r="5"/>')
        out.append(text("ink2", left - 48 + 300 * k, height - 44, 12, f"{a}  {said}"))
    out += [
        text(
            "ink2",
            left - 64,
            height - 22,
            11,
            f"Generated by dev/test/evidence.py from {source}; dollars are "
            "the ledger's rows in each run's window, and a run whose cost is unknown is not drawn.",
        ),  # fmt: skip
        "</svg>",
    ]
    return "\n".join(out) + "\n"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="do", required=True)
    add = sub.add_parser("add", help="count one run and append its row")
    add.add_argument("run", type=Path)
    add.add_argument("--task", required=True)
    add.add_argument("--arm", required=True, choices=sorted(SPELLED))
    add.add_argument("--rows", type=Path, default=ROWS)
    add.add_argument("--tasks", type=Path, default=HERE / "tasks", help="where <task>/accept.py is")
    rep = sub.add_parser("report", help="fill the table and draw the chart")
    rep.add_argument("--rows", type=Path, default=ROWS)
    rep.add_argument("--ledger", type=Path, required=True, help="the night's Token Factory ledger")
    rep.add_argument("--out", type=Path, help="the markdown table (printed when not given)")
    rep.add_argument("--svg", type=Path, default=SVG)
    rep.add_argument("--task", default="feeds", help="the task the chart draws")
    rep.add_argument("--stand-in", action="store_true", help="draw rows that are not live, and say so")
    args = ap.parse_args(argv)

    if args.do == "add":
        arm = SPELLED[args.arm]
        run = args.run.resolve()
        rows = read_jsonl(args.rows) if args.rows.exists() else []
        if any(r["dir"] == str(run) for r in rows):
            print(f"{run} is counted already in {args.rows}; a run is counted once")
            return 2
        row = count(run, args.task, arm, args.tasks)
        if row["practice"]:
            print(f"not added: {run.name} is practice (its usage rows were made while "
                  "GRAPHENE_AGENT_LIVE_USD was set), and a registered table takes none; run it again from a "
                  "shell without it")  # fmt: skip
            return 2
        with args.rows.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        acc = row["accept"]
        print(
            f"{row['task']} {arm} {row['run']}: accept {passed(acc)}, {row['modelled_seconds']} person-s "
            f"modelled, {row['usage_calls']} calls from {', '.join(row['endpoints']) or 'nowhere'}; "
            f"{args.rows}"
        )
        return 0

    rows = read_jsonl(args.rows)
    ledger = read_jsonl(args.ledger) if args.ledger.exists() else []
    drilled = practice(rows, ledger)
    if drilled:
        print("not drawn: these runs are practice (made while GRAPHENE_AGENT_LIVE_USD was set), and a "
              "registered table takes none, --stand-in or not:")  # fmt: skip
        for line in drilled:
            print(f"  {line}")
        return 2
    away = not_live(rows)
    if away and not args.stand_in:
        print("not drawn: these rows are not live (their usage is not all from Token Factory):")
        for r in away:
            print(f"  {r['task']} {r['arm']} {r['run']}: {', '.join(why_not_live(r))}")
        print("--stand-in draws them anyway, and the table and the chart then say STAND-IN, NOT LIVE")
        return 2
    stand_in = sorted({e for r in away for e in why_not_live(r)})
    cost = dollars(rows, ledger)
    source = f"`{args.rows.name}` and `{args.ledger.name}`"
    md = table(rows, cost, source, stand_in)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
    else:
        print(md)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(
        chart(rows, cost, args.task, stand_in, f"{args.rows.name} and {args.ledger.name}"), encoding="utf-8"
    )
    print(f"wrote {args.svg}" + (f" and {args.out}" if args.out else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
