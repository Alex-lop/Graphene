"""Conservative success-claim extraction, `claims.v1`.

Heuristic in one line: strip code, quotations, and struck-through text, split
agent text into sentences, skip any sentence that is a question, negated,
partial, hedged, conditional, future-tense, imperative, attributed to someone
else, or a markdown to-do, then report the first fixed pattern that matches
each remaining sentence.

- Fenced code blocks (``` or ~~~), inline code spans, ``~~struck~~`` text,
  and double-quoted or curly-quoted spans are removed first, so a sentence
  that was nothing but a quotation disappears.
- Blockquote lines (``>``) and table rows (``|``) are skipped.
- Sentences split on ``.``, ``!``, ``;`` (when followed by whitespace or the
  end of the text), on newlines, and at markdown bullets, numbering, and
  headings; emphasis markers are dropped.
- Precision first: a sentence containing a question mark, a negation token,
  a zero or partial count, a hedge/conditional/future token, a plan label,
  an unchecked ``[ ]`` box, an opening imperative verb, an attribution
  (``you said``, ``according to``), a transitive or noun use of ``pass``, a
  ``fixed-width``-style constant, a ``how it works`` explanation, or fewer
  than two words is skipped.
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
_STRUCK = re.compile(r"~~[^~\n]+~~")
_QUOTED = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’")
_BULLET = re.compile(r"^\s*(?:[-*+•]+|\d+[.)]|#{1,6})\s+")
_QUOTE_OR_TABLE = re.compile(r"^\s*[>|]")
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
        r"\bno\b",
        r"\bnone\b",
        r"\bnothing\b",
        r"\bneither\b",
        r"\bnor\b",
        r"\bnever\b",
        r"\bwithout\b",
        r"\bunable\b",
        r"\bzero\b",
        r"\bfalse\b",
        r"\bhardly\b",
        r"\bfewer\b",
        r"\bfail(s|ed|ing)?\b",
        r"\bbroken\b",
        r"\bwrong\b",
        r"\bincorrect\w*",
        r"\bmistake\w*",
        r"\bstill\b",
        r"\byet\b",
        r"\bexcept\b",
        r"\bbut\b",
        # zero and partial counts
        r"\b0\s+(?:tests?\s+)?pass(?:ed|es|ing)?\b",
        r"\b[1-9]\d*\s+skipped\b",
        r"\b\d+\s+of\s+\d+\b",
        r"\bpass(?:ing)?\s+rate\b",
        r"\bsome\b",
        r"\bmost\b",
        r"\balmost\b",
        r"\bonly\b",
        r"\bpartial\w*",
        r"\bpartly\b",
        # markdown state: unchecked boxes, failure marks, table cells, to-dos
        r"\[ \]",
        r"[❌✗✘🚫⛔🔴]",
        r"\s\|\s",
        r"\bwip\b",
        r"\btbd\b",
        r"\bpending\b",
        r"\btodo\b",
        r"\bto-do\b",
        r"\bin\s+progress\b",
        # hedges, conditionals, intentions, and the future
        r"\bshould\b",
        r"\bmight\b",
        r"\bmay(be)?\b",
        r"\bcould\b",
        r"\bwould\b",
        # `as expected` is kept: the spec's own `works as expected` pattern
        # needs it; every other `expected` is a plan or a criterion.
        r"\bexpect(s|ing)?\b",
        r"(?<!as )\bexpected\b",
        r"\bhope\w*",
        r"\bonce\b",
        r"\bif\s",
        r"\bwhen\s",
        r"\bwhenever\b",
        r"\bunless\b",
        r"\bafter\s+you\b",
        r"\bwill\b",
        r"[’']ll\b",
        r"\bgoing\s+to\b",
        r"\bthen\s+i\b",
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
        r"\bso\s+that\b",
        r"\buntil\b",
        r"\bassum\w*",
        r"likely\b",
        r"\bprobabl\w*",
        r"\bseem\w*",
        r"\bappear\w*",
        r"\bapparent\w*",
        r"\bthink\w*",
        r"\bthought\b",
        r"\bbeliev\w*",
        r"\bsuspect\w*",
        r"\bguess\w*",
        r"\bpresumabl\w*",
        r"\bperhaps\b",
        r"\bpossibl\w*",
        r"\bideally\b",
        r"\bin\s+theory\b",
        r"\bsuppos\w*",
        r"\balleged\w*",
        r"\breportedly\b",
        r"\bdoubt\w*",
        r"\bunsure\b",
        r"\bunclear\b",
        r"\buntested\b",
        r"\bunverified\b",
        r"\bimagine\b",
        r"\bgiven\s+that\b",
        r"\bas\s+long\s+as\b",
        r"\bprovided\s+that\b",
        r"\bin\s+case\b",
        r"\bwhether\b",
        # plans, criteria, and step labels
        r"\bstep\s*\d",
        r"\b(?:plans?|todo|to-do|goals?|expectations?|next|steps?|"
        r"acceptance\s+criteria|criteria|definition\s+of\s+done|test\s+plan|"
        r"objectives?|aims?)\s*:",
        # imperatives and instructions to the reader
        r"^(?:please|run|re-?run|check|double-?check|verify|confirm|ensure|"
        r"make|keep|get|merge|wait|mark|execute|try|let|explain|list|filter|"
        r"refactor|apply|add|remove|delete|update|install|deploy|push|commit|"
        r"retry|review|avoid|consider|skip|rebase|revert|bump|pin|disable|"
        r"enable|reset|restart|validate|remember|do)\b",
        r"\byou\s+(?:should|can|could|need|must|may|might|will|want|have\s+to|"
        r"ought)\b",
        r"\b(?:can|could|would|will|do|did|does)\s+you\b",
        # explanations of mechanism rather than reports of behaviour
        r"\bhow\s+(?:it|this|that|everything|the\s+\w+)\s+(?:now\s+)?works\b",
        r"\bworks\s+(?:around|by|with|on|like|for|as\s+follows|differently|via|"
        r"through)\b",
        # `pass` as a transitive verb or a noun
        r"\bpass(?:es|ed|ing)?\s+(?:the|a|an|to|into|through|along|over|via|"
        r"down|up|back|none|null|nil|it|them|its|their|our|my|your|env|args?|"
        r"arguments?|values?|vars?|variables?|data|options?|flags?|"
        r"param(?:eter)?s?|inputs?|outputs?|review|i|me|us|took|takes|lasted|"
        r"-{1,2}[\w-]+|\d)\b",
        r"\b(?:a|an|one|single|first|second|third|another|final|next|quick|"
        r"full|initial|cleanup|review)\s+(?:(?!(?:tests|checks|suites)\b)\w+\s+)"
        r"{0,2}pass\b",
        # `fixed` meaning constant, not repaired
        r"\bfixed[-\s]?(?:point|width|size|length|rate|cost|time|step|number)\b",
        r"\bfixed\s+(?:at|to|in\s+place)\b",
        # quotations and attributions to someone else
        r"\baccording\s+to\b",
        r"\bper\s+the\b",
        r"\byou\s+(?:said|mentioned|wrote|claimed|told|noted|stated|asked|"
        r"reported)\b",
        r"\b(?:user|reviewer|author|ticket|issue|readme|description|pr|commit|"
        r"comment|message|docs?|documentation|previous\s+agent|log)\s+"
        r"(?:says?|said|wrote|claims?|claimed|states?|stated|mentions?|"
        r"mentioned|notes?|noted|reports?|reported|suggests?|suggested|"
        r"indicates?|indicated)\b",
        r"\b(?:says|said|claimed|mentioned|stated)\b",
        r"\bclaims?\s+that\b",
    )
)

# A failure, error, regression, or flake named in a sentence negates it unless
# the sentence says that very thing was fixed ("the failure has been resolved",
# "I fixed the error in parser.py").
_NEGATED_NOUN = re.compile(r"\b(?:failures?|errors?|regressions?|flaky)\b", re.I)
_FIX_BEFORE = re.compile(
    r"\b(?:fix(?:ed|es)?|resolv(?:ed|es)|repaired|addressed|eliminated|removed|"
    r"handled)\s+(?:(?:the|this|that|a|an|all|both|every|each|its|their|my|our|"
    r"your|\d+)\s+)?(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)
_FIX_AFTER = re.compile(
    r"^\s+(?:is|was|are|were|has\s+been|have\s+been|got)\s+(?:now\s+)?"
    r"(?:fixed|resolved|gone|addressed)\b",
    re.IGNORECASE,
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
        (
            "checks_pass",
            "all-green",
            r"\ball (green|passing)\b"
            r"(?!\s+(?:tests?|jobs?|checks?|builds?|runs?|suites?|cases?|specs?)\b)",
        ),
        (
            "checks_pass",
            "suite-green",
            r"\b(test )?suite (passes|passed|is green|is passing)\b",
        ),
        ("checks_pass", "n-passed", r"\b[1-9]\d*\s+(tests?\s+)?passed\b"),
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
            # A pronoun subject, `works`, and nothing after it but an outcome
            # word: "it works by hashing" is an explanation, not a report.
            "verified",
            "works-as-expected",
            r"\b(it|this|everything|the (fix|change|code))\s+(now\s+)?works"
            r"(?:\s+(?:as expected|correctly|now|fine|properly|again))*$",
        ),
        ("fixed", "fixed-the", r"\b(i|we)\s+(have\s+)?fixed\s+(the|this|that|it)\b"),
        (
            "fixed",
            "is-fixed",
            r"\b(bug|issue|problem|error|test|failure|it|this)\s+(is|has been|was)\s+"
            r"(now\s+)?(fixed|resolved)\b",
        ),
        ("fixed", "fix-complete", r"\bfix (is )?(complete|done)\b"),
    )
)

PATTERN_IDS: tuple[str, ...] = tuple(pattern_id for _, pattern_id, _ in _PATTERNS)


def _sentences(text: str) -> list[str]:
    cleaned = _FENCE.sub(" ", text)
    for pattern in (_INLINE_CODE, _STRUCK, _QUOTED):
        cleaned = pattern.sub(" ", cleaned)
    sentences: list[str] = []
    for line in cleaned.split("\n"):
        if _QUOTE_OR_TABLE.match(line):
            continue
        stripped = _EMPHASIS.sub("", _BULLET.sub("", line, count=1))
        for piece in _SENTENCE_END.split(stripped):
            collapsed = _WHITESPACE.sub(" ", piece).strip()
            if collapsed and not _QUOTE_OR_TABLE.match(collapsed):
                sentences.append(collapsed)
    return sentences


def _negated_by_noun(sentence: str) -> bool:
    for found in _NEGATED_NOUN.finditer(sentence):
        if _FIX_BEFORE.search(sentence[: found.start()]):
            continue
        if _FIX_AFTER.match(sentence[found.end() :]):
            continue
        return True
    return False


def _excluded(sentence: str) -> bool:
    if len(sentence.split()) < 2:
        return True
    if any(pattern.search(sentence) for pattern in _EXCLUSIONS):
        return True
    return _negated_by_noun(sentence)


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
