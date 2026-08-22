# ledger_service

A small stock ledger: items, signed movements, deterministic replay, an audit
trail, note redaction, and a CLI. Standard library only; no network.

This is the **Graphene North Star demo target**: a live Graphene mission
edits it. `scripts/materialize_north_star.py` in the Graphene repository
copies it into a fresh Git repository and writes the `.graphene/project.json`
policy there; this tree deliberately has no `.graphene/` directory.

## Layout

| Path | Role |
| --- | --- |
| `ledger_service/models.py` | `Item`, `Movement`, `Snapshot` dataclasses with validation |
| `ledger_service/ledger.py` | `Ledger`: apply movements, balances, audit trail, error types |
| `ledger_service/redact.py` | `RedactionPolicy` and `redact_text` for free-text notes |
| `ledger_service/report_base.py` | `ReportRow`/`Report` aggregation shared by every report renderer |
| `ledger_service/cli.py` | `balances`, `audit`, and `report --format json|markdown` |

## Usage

```
python -m ledger_service --ledger ledger.json balances
python -m ledger_service --ledger ledger.json audit [--sku SKU]
python -m ledger_service --ledger ledger.json report --format json
```

The ledger document is `{"items": [...], "movements": [...]}`;
see `tests/test_cli.py`. Movements replay in `(recorded_at, movement_id)` order
no matter how the file lists them.

## Not there yet

`report --format json|markdown` is parsed by the CLI, but
`cli.render_report` raises `NotImplementedError("report renderers are added
by the mission")`. Renderers must build on `report_base.build_report`, which
redacts notes exactly once and whose `Report.balances()` equals the
`balances` command.

## Tests

```
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider
```
