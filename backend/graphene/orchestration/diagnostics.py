"""Turn raw check output into a structured, prompt-safe failure diagnostic.

The runtime keeps only ``output_sha256`` when a trusted check fails, so a
retry re-sends a byte-identical prompt and learns nothing. This is the pure
half of the fix: classify the failure and distill a redacted, bounded summary
that is safe for a model prompt and an event log, while the original bytes
stay auditable through their digest.
"""

from __future__ import annotations

import re
from typing import Literal

from ..hashing import sha256_hex
from ..models import FrozenModel, Sha256
from ..redaction import bounded_excerpt, redact_text

FailureClass = Literal[
    "checks_failed",
    "collection_error",
    "timed_out",
    "output_truncated",
    "unclean_exit",
]

# The evidence kind the runtime stores a diagnostic under, so a retry can resolve
# the previous attempt's diagnostic from committed evidence rather than memory.
CHECK_DIAGNOSTIC_KIND = "check-diagnostic"
MAX_FAILED_NAMES = 8
MAX_NAME_CHARS = 200
MAX_SUMMARY_CHARS = 1200
_TAIL_LINES = 12
_SUMMARY_HEADER = "short test summary info"
# Pytest short-summary lines: ``FAILED <nodeid> - message`` / ``ERROR <nodeid>``.
_NODE_LINE = re.compile(r"^(FAILED|ERROR) +(\S+)", re.MULTILINE)
# Absolute POSIX paths only: the lookbehind skips relative paths (``tests/x.py``),
# ``::`` node ids, and ``//`` in URLs. graphene.execution.adapter._sanitize_output
# is the upstream sanitiser (``<fixture>`` roots, ``<duration>s``); this pass is
# idempotent over its output and over already path-stripped text.
_ABS_PATH = re.compile(r"(?<![\w.:/])(?:/[\w.@+~-]+)+")


class CheckDiagnostic(FrozenModel):
    """One failed check attempt, distilled so the next attempt can differ."""

    schema_version: Literal[1] = 1
    failure_class: FailureClass
    failed_check_names: tuple[str, ...]
    summary: str
    exit_code: int
    output_sha256: Sha256
    output_byte_count: int

    def signature(self) -> str:
        """Stable identity of this failure: equal signatures mean the retry learned nothing."""

        # The digest and byte count are deliberately excluded: timing noise and
        # output churn must not make two identical failures look distinct.
        return sha256_hex("\n".join((self.failure_class, *self.failed_check_names)).encode())


def summarize_check_failure(
    output: str,
    *,
    exit_code: int,
    timed_out: bool,
    output_truncated: bool,
    cleanup_complete: bool,
    output_sha256: str,
    output_byte_count: int,
) -> CheckDiagnostic:
    """Never raises on hostile, empty, binary-ish, or gigantic output."""

    nodes = _NODE_LINE.findall(output)
    names = tuple(sorted({_clean_name(node) for _, node in nodes})[:MAX_FAILED_NAMES])
    # Precedence: transport truth outranks content (a timeout or truncated capture
    # means the text may be incomplete or misleading), collection errors outrank
    # failing checks (nothing actually ran), and unclean_exit is the residual.
    if timed_out:
        failure_class: FailureClass = "timed_out"
    elif output_truncated:
        failure_class = "output_truncated"
    elif "during collection" in output or any(
        kind == "ERROR" and "::" not in node for kind, node in nodes
    ):
        failure_class = "collection_error"
    elif names:
        failure_class = "checks_failed"
    else:
        # Includes a dirty cleanup (``cleanup_complete=False``): with nothing
        # better identified it lands in the same residual class as a bare exit.
        failure_class = "unclean_exit"
    summary = bounded_excerpt(
        _strip_absolute_paths(redact_text(_summary_source(output))), MAX_SUMMARY_CHARS
    )
    return CheckDiagnostic(
        failure_class=failure_class,
        failed_check_names=names,
        summary=summary or "",
        exit_code=exit_code,
        output_sha256=output_sha256,
        output_byte_count=output_byte_count,
    )


def _clean_name(node: str) -> str:
    # Redact before truncating so a cut can never expose half a secret.
    return _strip_absolute_paths(redact_text(node))[:MAX_NAME_CHARS]


def _strip_absolute_paths(text: str) -> str:
    return _ABS_PATH.sub(lambda match: match.group(0).rsplit("/", 1)[-1], text)


def _summary_source(output: str) -> str:
    """Prefer pytest's short summary, then error-ish lines, then the raw tail."""

    lines = output.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if _SUMMARY_HEADER in lines[index]:
            return "\n".join(lines[index + 1 :])
    interesting = [
        line
        for line in lines
        if line.startswith("E ") or "Error" in line or "FAILED" in line or "assert" in line
    ]
    if interesting:
        return "\n".join(interesting[-_TAIL_LINES:])
    return "\n".join(lines[-_TAIL_LINES:])


__all__ = [
    "CHECK_DIAGNOSTIC_KIND",
    "MAX_FAILED_NAMES",
    "MAX_NAME_CHARS",
    "MAX_SUMMARY_CHARS",
    "CheckDiagnostic",
    "FailureClass",
    "summarize_check_failure",
]
