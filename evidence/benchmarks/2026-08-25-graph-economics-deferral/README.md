# `graph_economics` deferral — falsification probes

Base commit `e75b7d6`. Guard: `tests/unit/test_graph_economics_deferral.py`
(commit `7f046f9`). Reasoning: `benchmarks/DEFERRAL.md`.

A guard that only ever passes proves nothing, so each assertion was mutated in
turn and the suite re-run. Every probe reverted immediately
(`git checkout -- <file>`); the tree was clean afterwards.

Command, per probe:

```sh
uv run --frozen python -m pytest -q -p no:cacheprovider \
  tests/unit/test_graph_economics_deferral.py
```

Interpreter: `.venv/bin/python` (3.13); cwd: repository root.

| Probe (mutation applied) | Result |
|---|---|
| baseline, unmutated tree | `5 passed` |
| `benchmarks/templates/graph_economics.not_proven.json`: `"proof_status":"NOT PROVEN"` → `"PROVEN"` | `1 failed, 4 passed` |
| `contracts/product_proof.json`: `graph_economics.status` `not_proven` → `verified` | `1 failed, 4 passed` |
| `README.md`: disclaimer "no token-efficiency claim, and no speed or cost comparison" deleted | `1 failed, 4 passed` |
| `docs/PRODUCT.md`: planted "uses 40% fewer tokens than a linear transcript" | `1 failed, 4 passed` |

Each probe fails exactly one assertion, so no guard is masking another.

The comparative-claim matcher additionally carries its own self-test
(`test_comparative_claim_matcher_can_observe_a_violation`): it must fire on four
planted violations and stay silent on three honest lines, including the absolute
spend figure `$2.30 of receipt-derived spend across 14 missions`. That check
exists so the scan cannot degrade into one that passes because it has stopped
observing anything — the failure shape catalogued in `HANDOFF.md`,
"checks that cannot fail".

**What this evidence does not prove.** Nothing about economics. No token, cost,
latency, median or P95 result exists; `graph_economics` remains `not_proven`.
This records only that the deferral is enforced by a check that can fail.
