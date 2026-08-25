# Public-surface sweep: is a measured economic advantage claimed anywhere?

Base `e75b7d6`, lane `lane/product-bench-2026-08-25`. Interpreter
`.venv/bin/python` (3.13); cwd repository root.

Decision (B) requires rewriting "every public sentence that implies a measured
economic advantage". **There are none.** This file records the check, because
"we found nothing" is worthless without showing the search could find something.

The matcher is `COMPARATIVE_CLAIM` from
`tests/unit/test_graph_economics_deferral.py` — quantified comparative phrasing
only, so that absolute spend figures ("$2.30 of receipt-derived spend across 14
missions") are correctly *not* flagged. It carries its own positive/negative
self-test in that file.

Run it over every `*.md`, `*.json`, `*.mjs`, `*.html` in the tree:

```sh
uv run --frozen python - <<'PY'
import sys
sys.path.insert(0, "tests/unit")
from test_graph_economics_deferral import COMPARATIVE_CLAIM, ROOT
for pattern in ("*.md", "*.json", "*.mjs", "*.html"):
    for f in ROOT.rglob(pattern):
        if any(p in {".git", ".venv", "node_modules", "All_md_files", "local",
                     "__pycache__"} for p in f.parts):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if COMPARATIVE_CLAIM.search(line):
                print(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:160]}")
PY
```

Result: **2 hits, 0 of them claims.**

| Hit | Why it is not a claim |
|---|---|
| `docs/GRAPH_NECESSITY_EVAL.md:66` — "viewer median time is at least 20% lower" | A pre-registered *ship threshold* for an eval that has not run. Line 3 of that file: "**Status: NOT YET RUN. No participant result is claimed.**" A decision rule, not a measurement. |
| `evidence/benchmarks/2026-08-25-graph-economics-deferral/README.md:25` | This lane's own record of the string it *planted* to prove the guard fires. Self-referential. |

Independently, a keyword sweep over `README.md`, `docs/`, `contracts/`, `demo/`,
`frontend/` and root `*.md` for the stems `econom`, `benchmark`, `token`, `cost`,
`cheap`, `waste`, `rework`, `conflict`, `faster`, `efficien`, `saving`, `%`
found every economics surface already carrying an explicit `NOT PROVEN` label,
and no comparative claim. `README.md:33` already states: "There is no
leaderboard here, no token-efficiency claim, and no speed or cost comparison."
`frontend/` and `demo/` contain zero economic copy — every `token` hit there is
an auth token and every `%` is CSS.

**So no public sentence was rewritten, because none needed it.** What was missing
was not truthfulness but *enforcement*: the `README.md:33` invariant was checked
once by hand (`CONTRACT_REPORT.md:78`, commit `d432397`) and by nothing since.
`tests/unit/test_graph_economics_deferral.py` now runs that check every suite.

**What this does not prove.** Nothing economic. It proves only that the repo
currently claims nothing economic, and that the claim-detector can see a
violation when one exists.
