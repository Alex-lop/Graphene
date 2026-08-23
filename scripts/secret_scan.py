#!/usr/bin/env python3
"""Location-only secret scan: prints file, line, and pattern name — never the match.

Scans, in order: every tracked file in the working tree, the staged diff, and
the patches of the last N local commits (default 30). Exit 1 when anything
matches outside tests/ (or anywhere with --strict), 0 otherwise. Exclusions are paths nobody should be scanning into a
transcript in the first place (.env, local/, .git/).

    uv run --frozen python scripts/secret_scan.py [--commits N] [--include-untracked]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "google-oauth-token": re.compile(r"ya29\.[0-9A-Za-z_-]{30,}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "github-pat-fine-grained": re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "slack-token": re.compile(r"xox[abprs]-[0-9A-Za-z-]{10,}"),
    "bearer-token": re.compile(r"[Bb]earer\s+[A-Za-z0-9_\-.=]{30,}"),
    "assigned-secret": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{32,}"
    ),
}
# Known-false-positive substrings (documentation placeholders, hashes in tests).
ALLOW = re.compile(
    r"(?i)example|placeholder|redacted|sha256|<[^>]+>|\.\.\.|…|x{8,}|a{8,}"
)
EXCLUDED = (".env", "local/", ".git/", "uv.lock", "frontend/dist/", "node_modules/")


def _scan_text(text: str, label: str, findings: list[str]) -> None:
    """Report ``label:line pattern``; inside a patch, label the diff's file too."""

    context = ""
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("commit "):
            context = line.split()[1]
        elif line.startswith("diff --git "):
            context = f"{context.split('@')[0]}@{line.split(' b/', 1)[-1]}"
        for name, pattern in PATTERNS.items():
            match = pattern.search(line)
            if match and not ALLOW.search(line):
                where = f"{label}:{number}" + (f" ({context})" if context else "")
                findings.append(f"{where} {name}")


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--commits", type=int, default=30)
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument("--strict", action="store_true", help="fail on tests/ too")
    args = parser.parse_args()

    findings: list[str] = []
    listing = ["ls-files", "-z"]
    if args.include_untracked:
        listing += ["--others", "--cached", "--exclude-standard"]
    for name in _git(*listing).split("\0"):
        if not name or name.startswith(EXCLUDED) or name in EXCLUDED:
            continue
        path = Path(name)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        _scan_text(text, name, findings)
    _scan_text(_git("diff", "--cached"), "STAGED", findings)
    if args.commits > 0:
        _scan_text(
            _git("log", "-p", f"-n{args.commits}", "--format=commit %h", "--", "."),
            f"LOG(last {args.commits})",
            findings,
        )
    for item in findings:
        print(item)
    # Redaction tests under tests/ hold deliberately fake secrets; they are
    # printed for review but only fail the scan with --strict.
    outside_tests = [item for item in findings if "tests/" not in item]
    print(
        f"secret-scan: {len(findings)} finding(s), {len(outside_tests)} outside tests/"
    )
    return 1 if (outside_tests or (args.strict and findings)) else 0


if __name__ == "__main__":
    sys.exit(main())
