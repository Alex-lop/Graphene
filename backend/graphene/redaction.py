"""Secret-shaped text scrubbing, shared by every subsystem that emits text.

Both the shadow store's ingest path and the mission runtime's check diagnostics
put third-party text where a human or a model will read it, and neither may
carry a credential there. One definition, so a pattern added here reaches both:
``graphene.orchestration`` and ``graphene.shadow`` are deliberately forbidden
from importing each other (tests/unit/shadow/test_isolation.py), and this module
is the neutral ground that keeps that true without duplicating the patterns.
"""

from __future__ import annotations

import re

REDACTED = "<redacted>"
MESSAGE_EXCERPT_LIMIT = 280
COMMAND_EXCERPT_LIMIT = 200

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(
        r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|"
        r"CREDENTIALS?|PRIVATE[_-]?KEY)[A-Z0-9_]*\s*[=:]\s*['\"]?[^\s'\"]{4,}['\"]?"
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bhttps?://[^\s/@]+:[^\s/@]+@"),
)
_WHITESPACE = re.compile(r"\s+")
# C0 and C1 controls plus the zero-width characters (U+200B..U+200D, U+FEFF)
# that an emitter could use to split a secret so the patterns miss it.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200d\ufeff]")


def redact_text(text: str) -> str:
    scrubbed = text
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(REDACTED, scrubbed)
    return scrubbed


def bounded_excerpt(text: str, limit: int) -> str | None:
    """A single-line, redacted, length-bounded excerpt; None when empty."""

    if limit < 2:
        raise ValueError("excerpt limit must leave room for an ellipsis")
    # Strip control and zero-width characters BEFORE scanning, so a secret
    # split by one cannot slip past the patterns and be reassembled by the
    # strip; then scan again after whitespace collapse, belt and braces.
    collapsed = _WHITESPACE.sub(" ", redact_text(_CONTROL.sub("", text))).strip()
    collapsed = redact_text(collapsed)
    if not collapsed:
        return None
    if len(collapsed) > limit:
        return collapsed[: limit - 1] + "…"
    return collapsed


__all__ = [
    "REDACTED",
    "bounded_excerpt",
    "redact_text",
]
