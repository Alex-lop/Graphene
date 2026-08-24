# ledger_service

A small stock ledger: items, signed movements, deterministic replay, an audit
trail, note redaction, and a CLI. Standard library only; no network.

This is the **Graphene North Star demo target**: a live Graphene mission
edits a copy materialized by `scripts/materialize_north_star.py`.

## Layout

| Path | Role |
| --- | --- |
| `ledger_service/models.py` | validated `Item`, `Movement`, `Snapshot` |
| `ledger_service/ledger.py` | `Ledger`: balances, audit trail, error types |
| `ledger_service/redact.py` | `redact_text` + `RedactionPolicy` for notes |
| `ledger_service/report_base.py` | `Report` aggregation shared by renderers |
| `ledger_service/cli.py` | `balances`, `audit`, `report --format ...` |

## Usage

```
python -m ledger_service --ledger ledger.json balances|audit|report --format json
```

## Not there yet

`cli.render_report` already builds the `Report` once and dispatches
`--format json|markdown` to `ledger_service.report_json.render_json` /
`ledger_service.report_markdown.render_markdown`. Those two modules do not
exist yet, so the CLI exits 1 with `error: no ... report renderer`.
`tests/test_report_contract.py` is the exact contract for both renderers: it
skips while a module is absent and binds the moment it appears.

## Tests

```
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider
```
