"""Append-only stock ledger with deterministic replay and an audit trail."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import Item, Movement, Snapshot, ValidationError


class LedgerError(Exception):
    """Base class for user-reportable failures."""


class UnknownItemError(LedgerError):
    """Unregistered SKU."""


class DuplicateMovementError(LedgerError):
    """Movement id already applied."""


class InsufficientStockError(LedgerError):
    """Balance would fall below zero."""


class DocumentError(LedgerError):
    """Malformed ledger document."""


@dataclass(frozen=True, slots=True)
class AuditEntry:
    sequence: int
    movement: Movement
    balance_before: int
    balance_after: int


class Ledger:
    def __init__(self, items: Iterable[Item] = ()) -> None:
        self._items: dict[str, Item] = {}
        self._balances: dict[str, int] = {}
        self._entries: list[AuditEntry] = []
        for item in items:
            self.register(item)

    def register(self, item: Item) -> None:
        if item.sku in self._items:
            raise LedgerError(f"duplicate item: {item.sku}")
        self._items[item.sku] = item
        self._balances[item.sku] = 0

    @property
    def items(self) -> tuple[Item, ...]:
        """Items ordered by SKU."""
        return tuple(self._items[sku] for sku in sorted(self._items))

    def item(self, sku: str) -> Item:
        if sku not in self._items:
            raise UnknownItemError(f"unknown sku: {sku}")
        return self._items[sku]

    def apply(self, movement: Movement) -> AuditEntry:
        self.item(movement.sku)
        if any(e.movement.movement_id == movement.movement_id for e in self._entries):
            raise DuplicateMovementError(f"duplicate movement: {movement.movement_id}")
        before = self._balances[movement.sku]
        after = before + movement.delta
        if after < 0:
            raise InsufficientStockError(
                f"{movement.sku}: {before} on hand, cannot remove {-movement.delta}"
            )
        entry = AuditEntry(len(self._entries) + 1, movement, before, after)
        self._entries.append(entry)
        self._balances[movement.sku] = after
        return entry

    def apply_all(self, movements: Iterable[Movement]) -> tuple[AuditEntry, ...]:
        """Apply in (timestamp, id) order regardless of input order."""
        ordered = sorted(movements, key=Movement.sort_key)
        return tuple(self.apply(movement) for movement in ordered)

    def balances(self) -> dict[str, int]:
        return {sku: self._balances[sku] for sku in sorted(self._balances)}

    def audit_trail(self, sku: str | None = None) -> tuple[AuditEntry, ...]:
        if sku is not None:
            self.item(sku)
        return tuple(e for e in self._entries if sku in (None, e.movement.sku))

    def snapshot(self, sku: str) -> Snapshot:
        entries = self.audit_trail(sku)
        return Snapshot(
            sku=sku,
            quantity=self._balances[sku],
            movement_count=len(entries),
            as_of=entries[-1].movement.recorded_at if entries else None,
        )

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> Ledger:
        rows = _section(document, "items")
        movements = _section(document, "movements")
        try:
            ledger = cls(Item(**row) for row in rows)
            ledger.apply_all(Movement(**row) for row in movements)
        except (TypeError, ValidationError) as error:
            raise DocumentError(f"ledger document is invalid: {error}") from error
        return ledger


def _section(document: Any, key: str) -> list[Mapping[str, Any]]:
    value = document.get(key) if isinstance(document, Mapping) else None
    if not isinstance(value, list) or not all(isinstance(r, Mapping) for r in value):
        raise DocumentError(f"ledger document needs a list of objects under {key!r}")
    return list(value)
