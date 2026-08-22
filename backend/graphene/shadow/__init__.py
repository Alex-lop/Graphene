"""Shadow Agent: observe a finished agent session, reconstruct it, lint it.

Shadow data is a reconstruction of work Graphene did not govern. It lives in
its own store and is never cited by mission evidence. See docs/SHADOW.md.
"""

from .adapters import AdapterError, adapter_for
from .claims import extract_claims
from .classify import classify_command
from .events import (
    SHADOW_EVENT_SCHEMA,
    ShadowClaim,
    ShadowEvent,
    ShadowSource,
    canonical_event_bytes,
    event_id_for,
    session_sha256,
)
from .ingest import IngestResult, ingest_file
from .lint import RULES, LintReport, lint
from .reconstruct import ShadowGraph, graph_to_dot, reconstruct
from .report import render_report, report_value
from .store import ShadowStore

__all__ = [
    "RULES",
    "SHADOW_EVENT_SCHEMA",
    "AdapterError",
    "IngestResult",
    "LintReport",
    "ShadowClaim",
    "ShadowEvent",
    "ShadowGraph",
    "ShadowSource",
    "ShadowStore",
    "adapter_for",
    "canonical_event_bytes",
    "classify_command",
    "event_id_for",
    "extract_claims",
    "graph_to_dot",
    "ingest_file",
    "lint",
    "reconstruct",
    "render_report",
    "report_value",
    "session_sha256",
]
