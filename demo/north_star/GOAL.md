# North Star mission goal

This is the goal handed to `graphene mission start` for the North Star demo
target in `demo/north_star/repository` (the `ledger_service` package).
`scripts/materialize_north_star.py DEST` reads `goal.json`, the
machine-readable twin of this file, and prints the exact command;
`tests/unit/test_north_star_target.py` proves the two files agree.

## Goal

> Add a redacted JSON status report and a Markdown status report to the ledger CLI; both must pass the existing suite plus new tests.

## Success criteria

Each criterion is one sentence and is checkable by the target's own test
suite, which is the policy's only command template
(`python -m pytest -q -p no:cacheprovider`). The CLI sorts criteria before
planning, so their order here carries no meaning.

1. Running ledger_service with report --format json prints one JSON object whose per-item quantities equal the balances command and whose notes have passed through the redaction policy.
2. Running ledger_service with report --format markdown prints a Markdown table with a header row and exactly one row per item, escaping pipe characters inside cells.
3. The existing tests and the new report tests all pass under python -m pytest -q -p no:cacheprovider.
4. No file outside ledger_service/ and tests/ is created or modified.

## Expected plan shape (an expectation, not a fixture)

The planner is live Gemini. Nothing in this section is fed to it, scripted,
or enforced; it is what a good plan for this goal looks like, so a reviewer
can judge the proposal that comes back before approving it.

- Work task A (parallel): a JSON renderer, for example
  `ledger_service/report_json.py`, built on `report_base.build_report`,
  plus `tests/test_report_json.py`.
- Work task B (parallel): a Markdown renderer, for example
  `ledger_service/report_markdown.py`, with one table row per item and pipe
  characters escaped, plus `tests/test_report_markdown.py`.
- Integration tail (depends on A and B): replace the `NotImplementedError`
  in `ledger_service/cli.py::render_report` with dispatch to both renderers
  and extend `tests/test_cli.py`.
- Verification: the `fixture-tests` command template run against the
  assembled candidate.

A and B touch disjoint files, so two workers can run them concurrently; the
tail is where the mission proves assembly and exact verification.

## Machine-readable twin

The block below is byte-for-byte the content of `goal.json`:

```json
{
  "schema_version": 1,
  "goal": "Add a redacted JSON status report and a Markdown status report to the ledger CLI; both must pass the existing suite plus new tests.",
  "success_criteria": [
    "Running ledger_service with report --format json prints one JSON object whose per-item quantities equal the balances command and whose notes have passed through the redaction policy.",
    "Running ledger_service with report --format markdown prints a Markdown table with a header row and exactly one row per item, escaping pipe characters inside cells.",
    "The existing tests and the new report tests all pass under python -m pytest -q -p no:cacheprovider.",
    "No file outside ledger_service/ and tests/ is created or modified."
  ]
}
```
