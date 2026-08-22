from __future__ import annotations

import pytest

from graphene.shadow.claims import (
    CLAIMS_MATCHER,
    PATTERN_IDS,
    SENTENCE_LIMIT,
    ClaimMatch,
    extract_claims,
)
from graphene.shadow.events import ShadowClaim

POSITIVES = [
    ("tests-pass", "checks_pass", "All tests pass."),
    ("tests-pass", "checks_pass", "The unit tests now pass"),
    ("tests-pass", "checks_pass", "Every test passes"),
    ("tests-pass", "checks_pass", "Integration tests are green"),
    ("all-green", "checks_pass", "Everything is all green now"),
    ("suite-green", "checks_pass", "The test suite passes"),
    ("suite-green", "checks_pass", "Suite is green"),
    ("n-passed", "checks_pass", "42 passed in 1.2s"),
    ("n-passed", "checks_pass", "3 passed, 0 skipped"),
    ("runner-passes", "checks_pass", "pytest passes locally"),
    ("runner-passes", "checks_pass", "jest passed on CI"),
    ("lint-clean", "checks_pass", "Ruff is clean"),
    ("lint-clean", "checks_pass", "Lint passes and mypy passes"),
    ("lint-clean", "checks_pass", "type check is green"),
    ("build-ok", "build_ok", "The build succeeds"),
    ("build-ok", "build_ok", "Build is green"),
    ("compiles", "build_ok", "Everything compiles cleanly"),
    ("verified-that", "verified", "I have verified that the endpoint returns 200"),
    ("verified-that", "verified", "We confirmed the behaviour"),
    ("verified-working", "verified", "Verified working end to end"),
    ("verified-working", "verified", "Confirmed it works"),
    ("works-as-expected", "verified", "It works as expected"),
    ("works-as-expected", "verified", "The fix now works correctly"),
    ("works-as-expected", "verified", "Everything works"),
    ("fixed-the", "fixed", "I fixed the bug"),
    ("fixed-the", "fixed", "We have fixed this"),
    ("is-fixed", "fixed", "The issue is fixed"),
    ("is-fixed", "fixed", "The failure has been resolved"),
    ("is-fixed", "fixed", "This is now fixed"),
    ("fix-complete", "fixed", "The fix is in place"),
    ("fix-complete", "fixed", "Fix complete"),
]

EXCLUDED = [
    # question
    "Do the tests pass?",
    "All tests pass, right?",
    # negation
    "All tests pass, not sure about lint",
    "All tests pass, don't they",
    "Tests don’t pass",
    "No worries, all tests pass",
    "All tests pass, never mind the warnings",
    "tests fail",
    "All tests pass and the lint fails",
    "The tests failed before the fix and all tests pass after",
    "Build is green while tests are failing",
    "All tests pass but the build is broken",
    "All tests still pass",
    "All tests pass, lint not yet",
    "all green except one",
    # hedges, conditionals, and the future
    "tests should pass now",
    "All tests pass, might need a rerun",
    "All tests pass, may be flaky",
    "This could mean all tests pass",
    "That would mean all tests pass",
    "I expect all tests pass",
    "I hope all tests pass",
    "Hopefully all tests pass",
    "Once merged, all tests pass",
    "If you rerun, all tests pass",
    "When rerun, all tests pass",
    "After you rebase, all tests pass",
    "All tests pass, will rerun later",
    "Going to confirm all tests pass",
    "I'll run the tests",
    "Let me verify the tests pass",
    "Let's check that all tests pass",
    "Try again and all tests pass",
    "I want to confirm all tests pass",
    "Need to confirm all tests pass",
    "Make sure all tests pass",
    "Please confirm all tests pass",
    "Run the suite and all tests pass",
    "You can see all tests pass",
    "To verify, all tests pass",
    "To confirm: all tests pass",
    "Until then, all tests pass",
    "Assuming the fixture loads, all tests pass",
    "Likely all tests pass",
    "Probably all tests pass",
    "It seems all tests pass",
    "It appears all tests pass",
    # too short
    "Passed!",
    "Fixed.",
    "Verified",
]


@pytest.mark.parametrize(("pattern_id", "category", "text"), POSITIVES)
def test_every_pattern_has_a_positive(
    pattern_id: str, category: str, text: str
) -> None:
    matches = extract_claims(text)
    assert len(matches) == 1
    match = matches[0]
    assert match.pattern_id == pattern_id
    assert match.category == category
    assert match.sentence == text.rstrip(".")
    # pattern_id satisfies the event schema's identifier rule
    ShadowClaim(matcher=CLAIMS_MATCHER, category=match.category, pattern_id=pattern_id)


def test_positive_table_covers_every_pattern_id() -> None:
    assert set(PATTERN_IDS) == {pattern_id for pattern_id, _, _ in POSITIVES}
    assert len(PATTERN_IDS) == len(set(PATTERN_IDS)) == 14


@pytest.mark.parametrize("text", EXCLUDED)
def test_exclusions(text: str) -> None:
    assert extract_claims(text) == ()


def test_fenced_code_is_ignored() -> None:
    assert extract_claims("Output:\n```\nAll tests pass\n```\n") == ()
    assert extract_claims("~~~text\nAll tests pass\n~~~") == ()
    assert extract_claims("```\nAll tests pass\nunterminated fence") == ()
    around = extract_claims("Build succeeds.\n```\ntests fail\n```\nAll tests pass.")
    assert [match.pattern_id for match in around] == ["build-ok", "tests-pass"]


def test_inline_code_is_ignored() -> None:
    assert extract_claims("Ran `pytest` and saw `All tests pass`") == ()
    assert extract_claims("Ran `pytest -q` and all tests pass") == (
        ClaimMatch("checks_pass", "tests-pass", "Ran and all tests pass"),
    )


def test_sentences_split_on_bullets_and_punctuation() -> None:
    text = (
        "## Summary\n"
        "- All tests pass\n"
        "* Build succeeds\n"
        "1. It works as expected\n"
        "The issue is fixed; lint is clean! Ruff is clean.\n"
        "**Verified working**"
    )
    assert [match.pattern_id for match in extract_claims(text)] == [
        "tests-pass",
        "build-ok",
        "works-as-expected",
        "is-fixed",
        "lint-clean",
        "lint-clean",
        "verified-working",
    ]


def test_one_match_per_sentence_in_table_order() -> None:
    sentence = "I have verified that all tests pass and the build succeeds"
    assert extract_claims(sentence) == (
        ClaimMatch("checks_pass", "tests-pass", sentence),
    )
    # earlier table entries win over later ones on the same sentence
    assert extract_claims("12 tests passed")[0].pattern_id == "tests-pass"
    assert extract_claims("cargo test is green")[0].pattern_id == "tests-pass"


def test_question_mark_anywhere_excludes_the_whole_sentence() -> None:
    assert extract_claims("Did it work? All tests pass.") == ()
    assert extract_claims("Did it work?\nAll tests pass.") == (
        ClaimMatch("checks_pass", "tests-pass", "All tests pass"),
    )


def test_identical_matches_are_deduplicated_in_order() -> None:
    text = "All tests pass.\n\nBuild succeeds.\nAll tests pass.\n- all tests pass"
    assert extract_claims(text) == (
        ClaimMatch("checks_pass", "tests-pass", "All tests pass"),
        ClaimMatch("build_ok", "build-ok", "Build succeeds"),
        ClaimMatch("checks_pass", "tests-pass", "all tests pass"),
    )


def test_sentence_is_whitespace_collapsed_and_bounded() -> None:
    assert extract_claims("  All \t tests\r\n") == ()
    assert extract_claims("  All \t tests   pass   ") == (
        ClaimMatch("checks_pass", "tests-pass", "All tests pass"),
    )
    long = "All tests pass " + "x" * 400
    (match,) = extract_claims(long)
    assert len(match.sentence) == SENTENCE_LIMIT
    assert match.sentence.endswith("…")
    assert match.sentence.startswith("All tests pass ")


def test_matcher_version_matches_the_event_schema() -> None:
    assert CLAIMS_MATCHER == "claims.v1"
    assert ShadowClaim(matcher=CLAIMS_MATCHER, category="fixed", pattern_id="is-fixed")


def test_empty_and_whitespace_text() -> None:
    assert extract_claims("") == ()
    assert extract_claims("\n\n  \n") == ()
