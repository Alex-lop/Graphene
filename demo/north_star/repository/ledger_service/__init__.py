"""A small stock ledger with an audit trail and a CLI; stdlib only."""

from .ledger import (
    AuditEntry,
    DocumentError,
    DuplicateMovementError,
    InsufficientStockError,
    Ledger,
    LedgerError,
    UnknownItemError,
)
from .models import Item, Movement, MovementKind, Snapshot, ValidationError
from .redact import DEFAULT_POLICY, RedactionPolicy, redact_text
from .report_base import Report, ReportRow, build_report

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_POLICY", "AuditEntry", "DocumentError", "DuplicateMovementError",
    "InsufficientStockError", "Item", "Ledger", "LedgerError", "Movement",
    "MovementKind", "RedactionPolicy", "Report", "ReportRow", "Snapshot",
    "UnknownItemError", "ValidationError", "build_report", "redact_text",
]
