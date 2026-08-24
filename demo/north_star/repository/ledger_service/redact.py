"""Redaction of free-text notes before they leave the service."""

from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDER = "[REDACTED]"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|token|password|passwd|secret)\b(\s*[=:]\s*)(\S+)"
)
BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Which classes of content to replace, and with what."""

    emails: bool = True
    secrets: bool = True
    placeholder: str = PLACEHOLDER

    def __post_init__(self) -> None:
        if not self.placeholder.strip():
            raise ValueError("placeholder must not be blank")


DEFAULT_POLICY = RedactionPolicy()


def redact_text(text: str, policy: RedactionPolicy = DEFAULT_POLICY) -> str:
    """Return ``text`` with every sensitive span replaced by the placeholder."""
    result = text
    if policy.secrets:
        result = SECRET_ASSIGNMENT.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{policy.placeholder}", result
        )
        result = BEARER.sub(lambda m: f"{m.group(1)} {policy.placeholder}", result)
        result = LONG_HEX.sub(policy.placeholder, result)
    if policy.emails:
        result = EMAIL.sub(policy.placeholder, result)
    return result
