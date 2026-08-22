"""Validated value objects; each dataclass checks itself in ``__post_init__``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

SKU_PATTERN = re.compile(r"[A-Z][A-Z0-9]{1,15}(?:-[A-Z0-9]{1,8})?")
MAX_NOTE_LENGTH = 512


class ValidationError(ValueError):
    """A value object would have been constructed in an invalid state."""


class MovementKind(StrEnum):
    RECEIPT = "receipt"  # quantity > 0, balance rises
    ISSUE = "issue"  # quantity > 0, balance falls
    ADJUSTMENT = "adjustment"  # any non-zero sign


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp with an offset; normalise to UTC."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"timestamp is not ISO 8601: {value!r}") from error
    if parsed.tzinfo is None:
        raise ValidationError(f"timestamp needs a UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def _check_sku(sku: object) -> None:
    if not isinstance(sku, str) or not SKU_PATTERN.fullmatch(sku):
        raise ValidationError(f"invalid sku: {sku!r}")


def _check_int(value: object, label: str, minimum: int | None = None) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}")


def _check_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must not be blank")


@dataclass(frozen=True, slots=True)
class Item:
    sku: str
    name: str
    unit: str = "each"
    reorder_level: int = 0

    def __post_init__(self) -> None:
        _check_sku(self.sku)
        _check_text(self.name, "item name")
        _check_text(self.unit, "item unit")
        _check_int(self.reorder_level, "reorder level", minimum=0)


@dataclass(frozen=True, slots=True)
class Movement:
    movement_id: str
    sku: str
    kind: MovementKind
    quantity: int
    recorded_at: str
    note: str = ""

    def __post_init__(self) -> None:
        _check_text(self.movement_id, "movement id")
        _check_sku(self.sku)
        try:
            object.__setattr__(self, "kind", MovementKind(self.kind))
        except ValueError as error:
            raise ValidationError(f"unknown movement kind: {self.kind!r}") from error
        _check_int(self.quantity, "quantity")
        if self.quantity == 0:
            raise ValidationError("quantity must not be zero")
        if self.kind is not MovementKind.ADJUSTMENT and self.quantity < 0:
            raise ValidationError(f"{self.kind.value} quantity must be positive")
        if not isinstance(self.note, str) or len(self.note) > MAX_NOTE_LENGTH:
            raise ValidationError("note must be a string of at most 512 chars")
        parse_timestamp(self.recorded_at)

    @property
    def delta(self) -> int:
        """Signed change applied to the on-hand balance."""
        return -self.quantity if self.kind is MovementKind.ISSUE else self.quantity

    def sort_key(self) -> tuple[datetime, str]:
        """Deterministic replay order: by time, then by movement id."""
        return (parse_timestamp(self.recorded_at), self.movement_id)


@dataclass(frozen=True, slots=True)
class Snapshot:
    sku: str
    quantity: int
    movement_count: int
    as_of: str | None = None

    def __post_init__(self) -> None:
        _check_sku(self.sku)
        _check_int(self.quantity, "snapshot quantity", minimum=0)
        _check_int(self.movement_count, "movement count", minimum=0)
        if (self.as_of is None) != (self.movement_count == 0):
            raise ValidationError("as_of is present exactly when movements exist")
        if self.as_of is not None:
            parse_timestamp(self.as_of)
