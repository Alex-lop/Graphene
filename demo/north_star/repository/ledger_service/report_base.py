"""Shared aggregation every report renderer builds on.

Renderers take a ``Report`` from ``build_report`` so they agree with each
other and with the ``balances`` command; notes are redacted once, here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .ledger import Ledger
from .redact import DEFAULT_POLICY, RedactionPolicy, redact_text


@dataclass(frozen=True, slots=True)
class ReportRow:
    """One item's status; ``notes`` are already redacted."""

    sku: str
    name: str
    unit: str
    quantity: int
    reorder_level: int
    movement_count: int
    last_movement_at: str | None
    notes: tuple[str, ...]

    @property
    def below_reorder(self) -> bool:
        return self.quantity < self.reorder_level

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["notes"] = list(self.notes)
        data["below_reorder"] = self.below_reorder
        return data


@dataclass(frozen=True, slots=True)
class Report:
    """Rows ordered by SKU plus totals derived from them."""

    rows: tuple[ReportRow, ...]

    @property
    def item_count(self) -> int:
        return len(self.rows)

    @property
    def total_quantity(self) -> int:
        return sum(row.quantity for row in self.rows)

    @property
    def below_reorder(self) -> tuple[str, ...]:
        return tuple(row.sku for row in self.rows if row.below_reorder)

    def balances(self) -> dict[str, int]:
        """Must equal ``Ledger.balances()`` for the source ledger."""
        return {row.sku: row.quantity for row in self.rows}


def build_report(ledger: Ledger, policy: RedactionPolicy = DEFAULT_POLICY) -> Report:
    rows: list[ReportRow] = []
    for item in ledger.items:
        entries = ledger.audit_trail(item.sku)
        snapshot = ledger.snapshot(item.sku)
        notes = tuple(
            redact_text(entry.movement.note, policy)
            for entry in entries
            if entry.movement.note
        )
        rows.append(
            ReportRow(
                sku=item.sku,
                name=item.name,
                unit=item.unit,
                quantity=snapshot.quantity,
                reorder_level=item.reorder_level,
                movement_count=snapshot.movement_count,
                last_movement_at=snapshot.as_of,
                notes=notes,
            )
        )
    return Report(tuple(rows))
