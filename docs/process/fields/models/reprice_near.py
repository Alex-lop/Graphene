"""Reprice NEAR AI's PutnamBench trajectories (costs.tsv) at other list prices.
Same tokens, different price sheet: not a prediction of what another model would do."""

import csv
import statistics as st

rows = list(csv.DictReader(open("near-costs.tsv"), delimiter="\t"))
# $ per 1M tokens: (cached input, uncached input, output). Sources in models.md.
SHEETS = {
    "as_submitted (NEAR, DeepSeek API w/ cache)": None,  # use cost_usd column
    "Token Factory list, no cache discount: V4-Flash-0731 0.14/0.28, V4-Pro 1.75/3.5": {
        "deepseek-v4-flash": (0.14, 0.14, 0.28),
        "deepseek-v4-pro": (1.75, 1.75, 3.5),
    },
    "Token Factory, flash rows repriced at V4-Pro-0813 1.32/3.96 (pro rows too)": {
        "deepseek-v4-flash": (1.32, 1.32, 3.96),
        "deepseek-v4-pro": (1.32, 1.32, 3.96),
    },
    "Token Factory Nemotron-3-Super 0.30/0.90 (all rows)": {
        "deepseek-v4-flash": (0.30, 0.30, 0.90),
        "deepseek-v4-pro": (0.30, 0.30, 0.90),
    },
    "Token Factory Nemotron-3-Nano 0.06/0.24 (all rows)": {
        "deepseek-v4-flash": (0.06, 0.06, 0.24),
        "deepseek-v4-pro": (0.06, 0.06, 0.24),
    },
    "GPT-5.5 5/0.50 cached/30": {
        "deepseek-v4-flash": (0.50, 5.0, 30.0),
        "deepseek-v4-pro": (0.50, 5.0, 30.0),
    },
    "Claude Opus 5.5 4/0.20 cache hit/20": {
        "deepseek-v4-flash": (0.20, 4.0, 20.0),
        "deepseek-v4-pro": (0.20, 4.0, 20.0),
    },
}
models = sorted({r["model"] for r in rows})
tot = {k: sum(int(r[k]) for r in rows) for k in ("cached_tokens", "input_tokens", "output_tokens")}
problems = sorted({r["problem"] for r in rows})
runs = {p: sum(r["problem"] == p for r in rows) for p in problems}
print(
    "rows",
    len(rows),
    "problems",
    len(problems),
    "models",
    models,
    "solved rows",
    sum(int(r["solved"]) for r in rows),
)
print(
    "token totals",
    tot,
    "cached share of input %.4f" % (tot["cached_tokens"] / (tot["cached_tokens"] + tot["input_tokens"])),
)
for name, sheet in SHEETS.items():
    per = {}
    for r in rows:
        if sheet is None:
            c = float(r["cost_usd"])
        else:
            pc, pi, po = sheet[r["model"]]
            c = (
                int(r["cached_tokens"]) * pc + int(r["input_tokens"]) * pi + int(r["output_tokens"]) * po
            ) / 1e6
        per[r["problem"]] = per.get(r["problem"], 0) + c
    v = list(per.values())
    print(
        f"{name}: total ${sum(v):,.2f}  mean ${st.mean(v):.2f}  median ${st.median(v):.3f}  max ${max(v):.2f}"
    )
    multi = [per[p] for p in per if runs[p] > 1]
    print(
        f"    problems with more than one run: {len(multi)} carry ${sum(multi):,.2f};"
        f" the other {len(per) - len(multi)} carry ${sum(v) - sum(multi):,.2f}"
    )
# sanity: as-submitted total should be ~$111.85 (README)
assert abs(sum(float(r["cost_usd"]) for r in rows) - 111.85) < 1.0
