"""Redaction at ingest.

Nothing unredacted is ever written to the shadow store. Excerpts are bounded,
whitespace-collapsed, and scrubbed of secret-shaped tokens; paths outside the
repository have the home directory collapsed. Full prompts, hidden reasoning,
file contents, command output, and environment values are never ingested.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

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


def collapse_home(path: str, home: Path | None = None) -> str:
    """Replace the home directory prefix with `~` for display outside the repo."""

    base = Path.home() if home is None else home
    base_text = base.as_posix().rstrip("/")
    if not base_text:
        return path
    if path == base_text:
        return "~"
    if path.startswith(base_text + "/"):
        return "~" + path[len(base_text) :]
    return path


def normalize_relative(path: str) -> str | None:
    """Canonical repository-relative POSIX path, or None when not expressible."""

    if not path or "\0" in path or "\\" in path:
        return None
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        return None
    text = parsed.as_posix()
    if text in {"", "."} or text.startswith("./"):
        text = text[2:] if text.startswith("./") else ""
    if not text or text == "." or len(text) > 256:
        return None
    return text


def classify_path(
    raw: str, *, repo_root: Path | None, cwd: Path | None, home: Path | None = None
) -> tuple[str | None, str | None]:
    """Return (repo_relative, outside) for one raw path string.

    Exactly one of the two is non-None unless the path is unusable. Relative
    paths resolve against `cwd`; when no repository root is known, any relative
    path is taken as repository-relative and any absolute path is outside.
    """

    if not raw or "\0" in raw or len(raw) > 4096:
        return None, None
    text = raw.strip()
    if not text:
        return None, None
    candidate = Path(text)
    if not candidate.is_absolute():
        if cwd is None or repo_root is None:
            return normalize_relative(text), None
        candidate = cwd / candidate
    resolved = _lexical(candidate)
    if repo_root is not None:
        root = _lexical(repo_root)
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            return None, collapse_home(resolved.as_posix(), home)
        relative_text = relative.as_posix()
        if relative_text == ".":
            return None, None
        return normalize_relative(relative_text), None
    return None, collapse_home(resolved.as_posix(), home)


def _lexical(path: Path) -> Path:
    """Resolve `.` and `..` lexically without touching the filesystem."""

    parts: list[str] = []
    for part in path.as_posix().split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return Path("/" + "/".join(parts))


__all__ = [
    "COMMAND_EXCERPT_LIMIT",
    "MESSAGE_EXCERPT_LIMIT",
    "REDACTED",
    "bounded_excerpt",
    "classify_path",
    "collapse_home",
    "normalize_relative",
    "redact_text",
]
