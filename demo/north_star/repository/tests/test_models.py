import pytest

from ledger_service.models import (
    Item,
    Movement,
    MovementKind,
    Snapshot,
    ValidationError,
)

T = "2024-05-01T10:00:00+00:00"


def test_item_defaults() -> None:
    item = Item("BOLT-M8", "M8 bolt")
    assert (item.unit, item.reorder_level) == ("each", 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sku": "bolt", "name": "x"},
        {"sku": "BOLT-M8", "name": "  "},
        {"sku": "BOLT-M8", "name": "x", "reorder_level": -1},
        {"sku": "BOLT-M8", "name": "x", "reorder_level": True},
    ],
)
def test_item_rejects_invalid(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Item(**kwargs)


def test_movement_kind_is_coerced_from_string() -> None:
    movement = Movement("m1", "BOLT-M8", "receipt", 5, T)
    assert movement.kind is MovementKind.RECEIPT
    assert movement.delta == 5


def test_delta_sign_follows_kind() -> None:
    assert Movement("m1", "BOLT-M8", MovementKind.ISSUE, 3, T).delta == -3
    assert Movement("m1", "BOLT-M8", "adjustment", -2, T).delta == -2


@pytest.mark.parametrize(
    ("kind", "quantity"),
    [("receipt", 0), ("receipt", -1), ("issue", -4), ("adjustment", 0), ("receipt", 1.5)],
)
def test_movement_rejects_bad_quantity(kind: str, quantity: object) -> None:
    with pytest.raises(ValidationError):
        Movement("m1", "BOLT-M8", kind, quantity, T)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"movement_id": " ", "kind": "receipt", "recorded_at": T},
        {"movement_id": "m1", "kind": "transfer", "recorded_at": T},
        {"movement_id": "m1", "kind": "receipt", "recorded_at": "yesterday"},
        {"movement_id": "m1", "kind": "receipt", "recorded_at": "2024-05-01T10:00:00"},
        {"movement_id": "m1", "kind": "receipt", "recorded_at": T, "note": "x" * 513},
    ],
)
def test_movement_rejects_invalid(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Movement(sku="BOLT-M8", quantity=1, **kwargs)  # type: ignore[arg-type]


def test_sort_key_normalises_offsets_then_uses_id() -> None:
    earlier = Movement("b", "BOLT-M8", "receipt", 1, "2024-05-01T12:00:00+02:00")
    later = Movement("a", "BOLT-M8", "receipt", 1, "2024-05-01T10:30:00+00:00")
    assert earlier.sort_key() < later.sort_key()
    same_a = Movement("a", "BOLT-M8", "receipt", 1, T)
    same_b = Movement("b", "BOLT-M8", "receipt", 1, T)
    assert same_a.sort_key() < same_b.sort_key()


def test_snapshot_validation() -> None:
    assert Snapshot("BOLT-M8", 0, 0).as_of is None
    assert Snapshot("BOLT-M8", 4, 2, T).movement_count == 2
    for args in (("BOLT-M8", -1, 0), ("BOLT-M8", 1, 0, T), ("BOLT-M8", 1, 2)):
        with pytest.raises(ValidationError):
            Snapshot(*args)
