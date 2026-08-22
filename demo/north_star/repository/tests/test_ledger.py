import pytest

from ledger_service import (
    DocumentError,
    DuplicateMovementError,
    InsufficientStockError,
    Item,
    Ledger,
    LedgerError,
    Movement,
    UnknownItemError,
)

from .conftest import stamp

def test_balances_and_items_are_sorted_by_sku(ledger: Ledger) -> None:
    assert [item.sku for item in ledger.items] == ["BOLT-M8", "NUT-M8", "WASHER"]
    assert ledger.balances() == {"BOLT-M8": 65, "NUT-M8": 40, "WASHER": 0}


def test_replay_is_ordered_by_timestamp_not_input_order(ledger: Ledger) -> None:
    trail = ledger.audit_trail()
    assert [e.movement.movement_id for e in trail] == ["m1", "m2", "m3", "m4"]
    assert [e.sequence for e in trail] == [1, 2, 3, 4]
    assert [e.balance_after for e in trail] == [100, 40, 70, 65]


def test_audit_trail_and_snapshot_per_sku(ledger: Ledger) -> None:
    trail = ledger.audit_trail("BOLT-M8")
    assert [e.movement.movement_id for e in trail] == ["m1", "m3", "m4"]
    assert (trail[1].balance_before, trail[1].balance_after) == (100, 70)
    bolt, washer = ledger.snapshot("BOLT-M8"), ledger.snapshot("WASHER")
    assert (bolt.quantity, bolt.movement_count, bolt.as_of) == (65, 3, stamp(13))
    assert (washer.quantity, washer.movement_count, washer.as_of) == (0, 0, None)


def test_insufficient_stock_is_rejected_without_side_effects(ledger: Ledger) -> None:
    with pytest.raises(InsufficientStockError):
        ledger.apply(Movement("m5", "NUT-M8", "issue", 41, stamp(14)))
    assert ledger.balances()["NUT-M8"] == 40
    assert len(ledger.audit_trail()) == 4


def test_duplicates_and_unknown_skus_are_rejected(ledger: Ledger) -> None:
    with pytest.raises(DuplicateMovementError):
        ledger.apply(Movement("m1", "BOLT-M8", "receipt", 1, stamp(15)))
    with pytest.raises(UnknownItemError):
        ledger.apply(Movement("m9", "NOPE", "receipt", 1, stamp(15)))
    with pytest.raises(UnknownItemError):
        ledger.audit_trail("NOPE")
    with pytest.raises(LedgerError):
        Ledger([Item("A1", "first"), Item("A1", "second")])


def test_from_document_replays_in_time_order() -> None:
    issue = {"movement_id": "i", "kind": "issue", "quantity": 1, "recorded_at": stamp(2)}
    receipt = {"movement_id": "r", "kind": "receipt", "quantity": 3, "recorded_at": stamp(1)}
    document = {
        "items": [{"sku": "A1", "name": "Widget"}],
        "movements": [{"sku": "A1", **issue}, {"sku": "A1", **receipt}],
    }
    assert Ledger.from_document(document).balances() == {"A1": 2}


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"items": [], "movements": {}},
        {"items": [{"sku": "A1"}], "movements": []},
        {"items": [{"sku": "A1", "name": "x"}], "movements": [{"movement_id": "m"}]},
    ],
)
def test_from_document_rejects_malformed(document: dict[str, object]) -> None:
    with pytest.raises(DocumentError):
        Ledger.from_document(document)
