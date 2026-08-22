import pytest

from ledger_service import Item, Ledger, Movement

ITEMS = (
    Item("BOLT-M8", "M8 bolt", reorder_level=70),
    Item("NUT-M8", "M8 nut"),
    Item("WASHER", "Washer", "box"),
)


def stamp(hour: int) -> str:
    return f"2024-05-01T{hour:02d}:00:00+00:00"


@pytest.fixture
def ledger() -> Ledger:
    # Four movements listed out of time order on purpose.
    ledger = Ledger(ITEMS)
    ledger.apply_all(
        [
            Movement("m3", "BOLT-M8", "issue", 30, stamp(12), note="shipped"),
            Movement("m1", "BOLT-M8", "receipt", 100, stamp(9)),
            Movement("m2", "NUT-M8", "receipt", 40, stamp(10), note="ask ops@example.com"),
            Movement("m4", "BOLT-M8", "adjustment", -5, stamp(13), note="damaged"),
        ]
    )
    return ledger
