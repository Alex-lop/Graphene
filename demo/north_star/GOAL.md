# North Star mission goal

This is the goal handed to `graphene mission start` for the North Star demo
target in `demo/north_star/repository` (the `ledger_service` package).
`scripts/materialize_north_star.py DEST` reads `goal.json`, the
machine-readable twin of this file, and prints the exact command;
`tests/unit/test_north_star_target.py` proves the two files agree.

## Goal

> Add a redacted JSON status report and a Markdown status report to the ledger CLI; the CLI already dispatches both formats, so implement the two renderer modules and their tests.

## Success criteria

Each criterion is one sentence and is mechanically checked by the golden
contract test that ships in the target (`tests/test_report_contract.py`),
run by the policy's only command template
(`python -m pytest -q -p no:cacheprovider`). The CLI sorts criteria before
planning, so their order here carries no meaning.

1. ledger_service/report_json.py defines render_json(report) returning one JSON object with item_count, total_quantity, below_reorder and rows, where rows are the report rows as dictionaries, per-item quantities equal the balances command, and notes have passed through the redaction policy.
2. ledger_service/report_markdown.py defines render_markdown(report) returning a Markdown table with the exact header and separator rows, one row per item in report order, pipe characters inside cells escaped, and notes joined with a semicolon and a space.
3. The existing tests and the new report tests all pass under python -m pytest -q -p no:cacheprovider.
4. No file outside ledger_service/report_json.py, ledger_service/report_markdown.py, tests/test_report_json.py and tests/test_report_markdown.py is created or modified.

## Expected plan shape (an expectation, not a fixture)

The planner is live Gemini. Nothing in this section is fed to it, scripted,
or enforced; it is what a good plan for this goal looks like, so a reviewer
can judge the proposal that comes back before approving it.

- Work task A (parallel): `ledger_service/report_json.py` defining
  `render_json(report)` over the `Report` from `report_base.build_report`,
  plus `tests/test_report_json.py`.
- Work task B (parallel): `ledger_service/report_markdown.py` defining
  `render_markdown(report)`, plus `tests/test_report_markdown.py`.
- Deterministic assembly, already in the repository: `ledger_service/cli.py`
  ships dispatching `report --format json|markdown` to the two renderer
  modules, and the policy's write scope excludes `cli.py`, so no integration
  task can even be planned.
- Verification tail: the `fixture-tests` command template against the
  assembled candidate. `tests/test_report_contract.py` skips while a
  renderer module is absent and binds the moment it appears, so the tail is
  exact rather than prose-judged.

A and B touch disjoint files, so two workers can run them concurrently.

## Why this shape

Twelve live missions ran against the previous shape of this target; two
completed, and every other failure was on the model-generated report tasks or
on a model-invented `cli_integration` task wiring the renderers together. The
convergence directive prescribes two disjoint Gemini work tasks, deterministic
assembly, and a verification tail — and that whatever remains model-generated
gets a sharper criterion, not a weaker check. So assembly stopped being model
work (the dispatch ships in `cli.py`, which the policy makes unwritable), and
the two model tasks kept their subjects but lost the guesswork: the golden
contract test ships in the base repository, readable but not writable under
the policy, turning the criteria from prose into exact assertions — strictly
stronger, never weaker. The markdown renderer stayed as the second task
because this target has no other naturally disjoint second task, and the
flakiness it caused was underspecification, now removed by the contract test.
A reviewer who reads "the flaky markdown-report generation leaves the
critical path" more literally can drop criterion 2 and its task without
touching anything else.

## Retry budget

`policy.template.json` sets `retry_limit: 2`, not 1. `graphene demo --live`
starts its mission with `--inject-check-fault`, which deliberately fails a
task's first trusted check, so at `retry_limit: 1` the model would be left with
exactly one real attempt and no recovery — the demo would be measuring the
injected fault rather than the product. Two retries give the sequence: injected
fault, one real attempt, and one diagnostic-aware repair. It is never a blind
extra draw, because a repeat of the same failure signature terminalizes the task
immediately.

The 2026-08-23 completion gate (9/10 ordinary, 3/3 controlled-failure) was
measured at `retry_limit: 1`, which is the stricter setting; raising it does not
retroactively loosen that number.

## Machine-readable twin

The block below is byte-for-byte the content of `goal.json`:

```json
{
  "schema_version": 1,
  "goal": "Add a redacted JSON status report and a Markdown status report to the ledger CLI; the CLI already dispatches both formats, so implement the two renderer modules and their tests.",
  "success_criteria": [
    "ledger_service/report_json.py defines render_json(report) returning one JSON object with item_count, total_quantity, below_reorder and rows, where rows are the report rows as dictionaries, per-item quantities equal the balances command, and notes have passed through the redaction policy.",
    "ledger_service/report_markdown.py defines render_markdown(report) returning a Markdown table with the exact header and separator rows, one row per item in report order, pipe characters inside cells escaped, and notes joined with a semicolon and a space.",
    "The existing tests and the new report tests all pass under python -m pytest -q -p no:cacheprovider.",
    "No file outside ledger_service/report_json.py, ledger_service/report_markdown.py, tests/test_report_json.py and tests/test_report_markdown.py is created or modified."
  ]
}
```
