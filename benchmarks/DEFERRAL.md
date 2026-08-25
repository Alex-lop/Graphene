# `graph_economics` is deferred, not measured

**Status: `not_proven`, deliberately, as of base commit `e75b7d6`.**

This file records why no credential-free benchmark under `benchmarks/` can
discharge the `graph_economics` claim, what a real one would need, and what was
rejected on the way to that conclusion. It exists so the next person does not
rebuild the same dead end.

The claim in question is economic: that compiling a goal into a typed,
permissioned DAG costs less than not doing so — fewer wasted attempts, less
rework, fewer conflicts, fewer tokens. That is a statement about *how often*
uncoordinated agents actually collide and *what* the collisions cost.

## Why the deterministic path cannot measure it

Three independent facts, each sufficient on its own.

**1. The harness's economics section requires receipts the deterministic driver
never emits.** `benchmarks/graph_economics.py` compares modes only for runs that
both succeed and pass an equal quality gate, and its economics section reports
median and P95 over `input_tokens`, `output_tokens`, `cost_usd`, `wall_seconds`
and the rest. The only credential-free driver, `scripted-local`
(`backend/graphene/orchestration/scripted.py`), emits no token, cost, or usage
field anywhere in its 2029 lines — the only `token` in the file is a lease
fencing token. Run credential-free, every economics metric is `"unavailable"`
and the comparison carries no economic content. The schema is honest about this;
that is what `"unavailable"` is for. Populating those fields from a scripted
driver would be fabricating measurements.

**2. The coordination mechanism is real, static, and already tested — and it is
not an economic result.** `validate_plan`
(`backend/graphene/orchestration/validation.py:97`) refuses any plan in which two
`WORK` tasks share a declared write path, raising `parallel_write_conflict` or
`ordered_write_conflict` (`validation.py:229`). That refusal is exact set
intersection over *declared* `write_paths`, decided before dispatch, and it is
already covered by `tests/unit/orchestration/test_validation.py:213` and `:408`.
A benchmark that re-runs it would re-demonstrate a unit test under a name that
promises economics. The mechanism's proof is the unit test; it is not evidence
about cost.

**3. The decisive one: the headline number would be authored by whoever writes
the fixture.** A coordinated-vs-uncoordinated comparison needs an uncoordinated
arm that actually collides. With deterministic scripted workers, *whether they
collide is a property of the script, not of the world.* The north-star fixture
makes this unusually clear: it is deliberately conflict-free. Its goal
(`demo/north_star/goal.json`) names four disjoint files;
`ledger_service/report_base.py` already supplies everything both renderers need
and `ledger_service/cli.py` already dispatches both formats, so the honest
two-worker decomposition has no shared write path at all. To make an
uncoordinated arm fail, the benchmark author must *introduce* the overlap. The
resulting ratio then reports the fixture's construction back to itself.

Point 3 is the repo's own governing failure mode, one turn removed. A check that
cannot observe what it certifies prints the same verdict either way
(`HANDOFF.md`, "checks that cannot fail"). This benchmark would be worse: it
*can* fail — flip the gate off and the comparison genuinely goes red — but what
it verifies is the gate's response, while the label it would discharge is about
cost. A real check wearing the wrong label is still a claim nobody measured.

## What was considered and rejected

| Candidate | Why it was rejected |
|---|---|
| Populate the three-mode harness with `scripted-local` | Every economics metric is `"unavailable"`; the result is the existing template with extra steps. |
| N unscoped scripted workers vs. the plan→approve→dispatch path, counting conflicts | The conflict rate is written into the scripted workers by hand. Measures the fixture, not the system. |
| Ablation: same workers, gate on vs. gate off, counting refusals | Sound and falsifiable, but it proves `validate_plan` refuses overlapping write scopes — which `tests/unit/orchestration/test_validation.py` already proves. No economic content. |
| Wall-clock or critical-path timing on scripted runs | Scripted workers sleep to a script; the timing measures the script. |

## What a real result requires

The harness already specifies it, and nothing here changes that contract:

- **Live runs with provider receipts.** Real workers against a real model, so
  `input_tokens`, `output_tokens`, `cached_input_tokens` and `cost_usd` come from
  the provider rather than from a fixture.
- **Repetitions, median and P95.** `graph_economics.py` reports
  `median` and `p95_nearest_rank` per mode; a single run is not a result.
- **An equal quality gate across all three modes**, digest-checked, with runs
  that fail the gate excluded from the economics section and counted in
  `excluded_failed_or_gate_failing_runs`.
- **An uncoordinated arm whose conflicts are observed, not scripted** — real
  agents given the whole goal with no write scopes, where the collision rate is
  measured because it was not chosen.
- **Raw receipts preserved** in a non-overwriting `--raw-directory` for audit.

Until those exist, `graph_economics` stays `not_proven` and no public surface
claims a measured economic advantage.

## Reproducing the two facts above

```sh
# The deterministic driver emits no token, cost, or usage field:
grep -n 'token\|usage\|cost' backend/graphene/orchestration/scripted.py
# (only `fencing_token` — a lease token — appears)

# The write-scope refusal is already a unit test:
uv run --frozen python -m pytest -q -p no:cacheprovider \
  tests/unit/orchestration/test_validation.py
```

The checked-in template `benchmarks/templates/graph_economics.not_proven.json`
remains `NOT PROVEN`. `tests/unit/test_graph_economics_deferral.py` fails if that
changes, or if a public surface starts claiming a measurement.
