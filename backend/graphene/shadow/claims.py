"""Conservative success-claim extraction, `claims.v1`.

Heuristic in one line: strip code, split agent text into sentences, skip any
sentence that is a question, negated, hedged, conditional, or future-tense,
then report the first fixed pattern that matches each remaining sentence.

- Fenced code blocks (``` or ~~~) and inline code spans are removed first.
- Sentences split on ``.``, ``!``, ``;`` (when followed by whitespace or the
  end of the text), on newlines, and at markdown bullets, numbering, and
  headings; emphasis markers are dropped.
- Precision first: a sentence containing a question mark, a negation token,
  a hedge/conditional/future token, or fewer than two words is skipped.
- Patterns are case-insensitive and carry a stable ``pattern_id``; one match
  per sentence, first pattern in table order wins, identical matches are
  reported once, in sentence order.

A missed claim is a shrug; a fabricated claim in a trust report is a scandal.
"""

from __future__ import annotations

import re
from typing import Literal, NamedTuple

CLAIMS_MATCHER = "claims.v1"
SENTENCE_LIMIT = 280

ClaimCategory = Literal["checks_pass", "build_ok", "verified", "fixed"]


class ClaimMatch(NamedTuple):
    category: ClaimCategory
    pattern_id: str
    sentence: str


_FENCE = re.compile(r"(```|~~~).*?(?:\1|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_BULLET = re.compile(r"^\s*(?:[-*+•]+|\d+[.)]|#{1,6})\s+")
_EMPHASIS = re.compile(r"[*`]+|(?<!\w)_+|_+(?!\w)")
_SENTENCE_END = re.compile(r"[.!;]+(?=\s|$)")
_WHITESPACE = re.compile(r"\s+")

_EXCLUSIONS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(expression, re.IGNORECASE)
    for expression in (
        # questions
        r"\?",
        # negation
        r"\bnot\b",
        r"\bcannot\b",
        r"n[’']t\b",
        r"\bno\s",
        r"\bnever\b",
        r"\bfail(s|ed|ing)?\b",
        r"\bbroken\b",
        r"\bstill\b",
        r"\byet\b",
        r"\bexcept\b",
        r"\bbut\b",
        # hedges, conditionals, intentions, and the future
        r"\bshould\b",
        r"\bmight\b",
        r"\bmay(be)?\b",
        r"\bcould\b",
        r"\bwould\b",
        # `expected` is kept: the spec's own `works as expected` pattern needs it.
        r"\bexpect(s|ing)?\b",
        r"\bhope\w*",
        r"\bonce\b",
        r"\bif\s",
        r"\bwhen\s",
        r"\bafter\s+you\b",
        r"\bwill\b",
        r"\bgoing\s+to\b",
        r"\blet\s+me\b",
        r"\blet[’']?s\b",
        r"\btr(y|ies|ied|ying)\b",
        r"\bwant\w*",
        r"\bneed\w*",
        r"\bmake\s+sure\b",
        r"\bplease\b",
        r"\brun\s+the\b",
        r"\byou\s+can\b",
        r"\bto\s+verify\b",
        r"\bto\s+confirm\b",
        r"\buntil\b",
        r"\bassum\w*",
        r"likely\b",
        r"\bprobabl\w*",
        r"\bseem\w*",
        r"\bappear\w*",
    )
)

_PATTERNS: tuple[tuple[ClaimCategory, str, re.Pattern[str]], ...] = tuple(
    (category, pattern_id, re.compile(expression, re.IGNORECASE))
    for category, pattern_id, expression in (
        (
            "checks_pass",
            "tests-pass",
            r"\b(all|the|every)?\s*(unit |integration )?tests?\s+(now\s+)?"
            r"(pass|passed|passes|passing|are passing|are green|is green)\b",
        ),
        ("checks_pass", "all-green", r"\ball (green|passing)\b"),
        (
            "checks_pass",
            "suite-green",
            r"\b(test )?suite (passes|passed|is green|is passing)\b",
        ),
        ("checks_pass", "n-passed", r"\b\d+\s+(tests?\s+)?passed\b"),
        (
            "checks_pass",
            "runner-passes",
            r"\b(pytest|jest|vitest|cargo test|go test|npm test)\s+"
            r"(passes|passed|is green)\b",
        ),
        (
            "checks_pass",
            "lint-clean",
            r"\b(lint|ruff|eslint|mypy|pyright|tsc|type ?check(s|ing)?)\s+"
            r"(passes|passed|is clean|clean|is green)\b",
        ),
        (
            "build_ok",
            "build-ok",
            r"\bbuild (succeeds|succeeded|passes|passed|is green|is clean)\b",
        ),
        ("build_ok", "compiles", r"\bcompiles (cleanly|successfully|fine)\b"),
        (
            "verified",
            "verified-that",
            r"\b(i|we)\s+(have\s+)?(verified|confirmed)\s+(that|the|it)\b",
        ),
        (
            "verified",
            "verified-working",
            r"\b(verified|confirmed)\s+(working|it works|everything works)\b",
        ),
        (
            "verified",
            "works-as-expected",
            r"\b(it|this|everything|the (fix|change|code))\s+(now\s+)?"
            r"works( as expected| correctly)?\b",
        ),
        ("fixed", "fixed-the", r"\b(i|we)\s+(have\s+)?fixed\s+(the|this|that|it)\b"),
        (
            "fixed",
            "is-fixed",
            r"\b(bug|issue|problem|error|test|failure|it|this)\s+(is|has been|was)\s+"
            r"(now\s+)?(fixed|resolved)\b",
        ),
        ("fixed", "fix-complete", r"\bfix (is )?(complete|done|in place)\b"),
    )
)

PATTERN_IDS: tuple[str, ...] = tuple(pattern_id for _, pattern_id, _ in _PATTERNS)


def _sentences(text: str) -> list[str]:
    cleaned = _INLINE_CODE.sub(" ", _FENCE.sub(" ", text))
    sentences: list[str] = []
    for line in cleaned.split("\n"):
        stripped = _EMPHASIS.sub("", _BULLET.sub("", line, count=1))
        for piece in _SENTENCE_END.split(stripped):
            collapsed = _WHITESPACE.sub(" ", piece).strip()
            if collapsed:
                sentences.append(collapsed)
    return sentences


def _excluded(sentence: str) -> bool:
    if len(sentence.split()) < 2:
        return True
    return any(pattern.search(sentence) for pattern in _EXCLUSIONS)


def _bound(sentence: str) -> str:
    if len(sentence) <= SENTENCE_LIMIT:
        return sentence
    return sentence[: SENTENCE_LIMIT - 1] + "…"


def extract_claims(text: str) -> tuple[ClaimMatch, ...]:
    """Success assertions found in agent text; see the module docstring."""

    matches: list[ClaimMatch] = []
    seen: set[ClaimMatch] = set()
    for sentence in _sentences(text):
        if _excluded(sentence):
            continue
        for category, pattern_id, pattern in _PATTERNS:
            if pattern.search(sentence) is None:
                continue
            match = ClaimMatch(category, pattern_id, _bound(sentence))
            if match not in seen:
                seen.add(match)
                matches.append(match)
            break
    return tuple(matches)


__all__ = [
    "CLAIMS_MATCHER",
    "PATTERN_IDS",
    "SENTENCE_LIMIT",
    "ClaimMatch",
    "extract_claims",
]
