"""Redaction at ingest.

Nothing unredacted is ever written to the shadow store. Excerpts are bounded,
whitespace-collapsed, and scrubbed of secret-shaped tokens; paths outside the
repository have the home directory collapsed. Full prompts, hidden reasoning,
file contents, command output, and environment values are never ingested.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from ..redaction import REDACTED, bounded_excerpt, redact_text

MESSAGE_EXCERPT_LIMIT = 280
COMMAND_EXCERPT_LIMIT = 200


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


def collapse_home_in_text(text: str, home: Path | None = None) -> str:
    """Replace every whole-component occurrence of the home directory with `~`."""

    base = (Path.home() if home is None else home).as_posix().rstrip("/")
    if not base:
        return text
    return re.sub(re.escape(base) + r"(?![^/\s'\"`)\]])", "~", text)


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
    "collapse_home_in_text",
    "normalize_relative",
    "redact_text",
]
