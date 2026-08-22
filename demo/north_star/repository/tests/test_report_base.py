from ledger_service import Item, Ledger, RedactionPolicy, build_report


def test_report_rows_are_plain_data() -> None:
    row = build_report(Ledger([Item("A1", "Widget")])).rows[0]
    assert row.as_dict() == {
        "sku": "A1",
        "name": "Widget",
        "unit": "each",
        "quantity": 0,
        "reorder_level": 0,
        "movement_count": 0,
        "last_movement_at": None,
        "notes": [],
        "below_reorder": False,
    }


def test_build_report_matches_balances_and_redacts_notes(ledger: Ledger) -> None:
    report = build_report(ledger)
    assert report.balances() == ledger.balances()
    bolt, nut, washer = report.rows
    assert (bolt.notes, bolt.below_reorder) == (("shipped", "damaged"), True)
    assert nut.notes == ("ask [REDACTED]",)
    assert (washer.movement_count, washer.last_movement_at, washer.notes) == (0, None, ())
    assert (report.item_count, report.total_quantity) == (3, 105)
    assert report.below_reorder == ("BOLT-M8",)
    assert bolt.as_dict()["notes"] == ["shipped", "damaged"]
    relaxed = build_report(ledger, RedactionPolicy(emails=False))
    assert relaxed.rows[1].notes == ("ask ops@example.com",)
