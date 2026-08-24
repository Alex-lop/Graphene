"""Golden contract for the report renderers the mission adds; each test
skips until its module exists. Renderers must not re-aggregate the report."""

import json

import pytest

from ledger_service import Ledger, Movement, build_report

HEAD = "| sku | name | unit | quantity | reorder_level | below_reorder | notes |"
T = "2024-05-01T14:00:00+00:00"


@pytest.fixture
def report(ledger: Ledger):
    ledger.apply(Movement("m5", "WASHER", "receipt", 2, T, note="token=abc123XYZ ok"))
    ledger.apply(Movement("m6", "WASHER", "issue", 1, T, note="crate a|b"))
    return build_report(ledger)


def test_render_json(ledger: Ledger, report) -> None:
    mod = pytest.importorskip("ledger_service.report_json")
    text = mod.render_json(report)
    data = json.loads(text)
    assert sorted(data) == ["below_reorder", "item_count", "rows", "total_quantity"]
    assert data["item_count"] == report.item_count
    assert data["total_quantity"] == report.total_quantity
    assert data["below_reorder"] == list(report.below_reorder)
    assert data["rows"] == [row.as_dict() for row in report.rows]
    assert {r["sku"]: r["quantity"] for r in data["rows"]} == ledger.balances()
    assert text == json.dumps(data, sort_keys=True) + "\n"
    assert "abc123XYZ" not in text and "token=[REDACTED] ok" in text
    assert mod.render_json(report) == text


def test_render_markdown(report) -> None:
    mod = pytest.importorskip("ledger_service.report_markdown")
    text = mod.render_markdown(report)
    assert text.endswith("\n") and not text.endswith("\n\n")
    lines = text.splitlines()
    assert lines[0] == HEAD
    assert lines[1] == "|" + " --- |" * 7
    assert len(lines) == 2 + len(report.rows)
    for line, row in zip(lines[2:], report.rows):
        cells = (row.sku, row.name, row.unit, row.quantity,
                 row.reorder_level, row.below_reorder, "; ".join(row.notes))
        joined = " | ".join(str(cell).replace("|", "\\|") for cell in cells)
        assert line == f"| {joined} |"
    assert "abc123XYZ" not in text and "crate a\\|b" in text
    assert mod.render_markdown(report) == text
