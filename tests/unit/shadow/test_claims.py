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
    ("fix-complete", "fixed", "The fix is done"),
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


# -- precision regressions from the adversarial review of v0 ------------------
# Each list is named for the confirmed finding it closes. Every sentence in an
# "excluded" list was reported as a success claim before the fix; every
# sentence in KEPT shares a surface form with one of them and must still match
# so the fix did not buy precision by destroying recall.

NEGATIONS_OUTSIDE_TOKEN_LIST = [
    "None of the tests pass",
    "None of this works",
    "None of it works as expected",
    "Nothing compiles cleanly",
    "Neither lint nor the tests pass",
    "Zero tests pass",
    "Hardly any tests pass",
    "I was unable to get all tests passing",
    "It is false that all tests pass",
    "I merged without verifying that all tests pass",
    "Fewer tests pass now than before",
    "All tests pass with 2 failures",
    "2 passed, 3 errors in 0.5s",
    "The build succeeds despite the regression",
    "The tests are flaky",
]

TRAILING_NO = [
    "All tests pass: no",
    "All tests pass, no",
    "Do all tests pass: no.",
]

ZERO_AND_PARTIAL_COUNTS = [
    "0 passed in 0.01s",
    "0 tests passed",
    "Only 3 of 10 tests passed",
    "Some tests pass",
    "Almost all tests pass",
    "Most tests pass",
    "Tests passing: 0 of 12",
    "Test pass rate: 40%",
    "12 passed, 2 failed",
    "3 passed, 2 skipped",
]

MARKDOWN_STATE = [
    "- [ ] All tests pass",
    "- [ ] Verify the build succeeds",
    "~~All tests pass~~ (retracted)",
    "> All tests pass",
    "| All tests pass | ❌ |",
    "| tests pass | TODO |",
    "❌ All tests pass",
    "All tests pass (pending CI)",
    "All tests pass: TBD",
    "WIP: all tests pass",
]

IMPERATIVES = [
    "Verify that all tests pass",
    "Confirm all tests pass before merging",
    "Ensure all tests pass before merging",
    "Double-check that all tests pass",
    "Check that the build succeeds",
    "Verify the build succeeds",
    "Make all tests pass",
    "Keep the unit tests passing",
    "Get mypy clean first",
    "Keep ruff clean",
    "Can you confirm all tests pass",
    "Merge on all green",
    "Wait for all green",
    "Mark the fix done in the tracker",
    "Unless all tests pass, block the merge",
    "Run the tests and confirm they pass",
    "You should see that all tests pass",
    "You need all tests passing before merge",
]

PLANS_AND_INTENT = [
    "I'll verify that all tests pass",
    "I'll confirm the build succeeds",
    "We'll confirm it works",
    "I'll make all tests pass",
    "Plan: confirm all tests pass",
    "Next: verify build succeeds",
    "Step 3: confirm all tests pass",
    "TODO: make all tests pass",
    "Goal: all tests pass",
    "Acceptance criteria: all tests pass and lint is clean",
    "Definition of done: all tests pass",
    "Test plan: all tests pass",
    "Expected: all tests pass",
    "Expected behavior: the build succeeds",
    "The expected outcome is that all tests pass",
    "1. Make all tests pass",
    "Refactor so that all tests pass",
    "I will run the tests, then I fix the bug",
]

EXPLANATIONS = [
    "Here is how it works",
    "Here's how it works: it hashes the key",
    "This works by hashing the key",
    "The code works around the limitation",
    "The fix works around the bug",
    "This works around the issue",
    "It works as follows",
    "It works differently from before",
    "Explain how it works",
    "Nobody knows how it works",
    "Unclear how it works",
    "Here's how the change works",
    "## How it works",
    "It works with Python 3.13",
    "It works on Linux",
    "It works like a cache",
    "It works for now",
]

TRANSITIVE_OR_NOUN_PASS = [
    "The test passes None to the function",
    "Each test passes a fixture to the helper",
    "Tests pass the token in the header",
    "Test passing a null value",
    "I did a second test pass over the code",
    "Test pass 2 of 3",
    "During the test pass I found a bug",
    "The build passes --release to cargo",
    "The build passes env vars to the container",
    "pytest passes the config via -c",
    "npm test passes through args",
    "Argument 1 passed to foo is wrong",
    "Step 1 passed the value to x",
    "PR 42 passed review",
    "I moved all passing tests to the fast suite",
    "List all passing tests",
    "Filter all green jobs",
    "The function passes the tests list to the runner",
    "I did a pass over the code",
    "The first pass is done",
    "It needs a single pass",
]

FIXED_AS_CONSTANT = [
    "The problem is fixed-point precision",
    "The issue is fixed-width fonts",
    "The error is fixed-size buffer overflow",
    "The bug is fixed-point overflow",
    "It is fixed at compile time",
    "It is fixed-width",
    "This is fixed-point math",
    "The test is fixed at 80 columns",
    "The test is fixed to use a seed",
    "This is fixed to 3 retries",
    "Apply the fix in place rather than creating a new file",
    "The fix is in place",
    "I fixed the wrong file",
    "I fixed this incorrectly",
]

HEDGES_OUTSIDE_TABLE = [
    "I think all tests pass",
    "I believe the build succeeds",
    "I suspect the issue is fixed",
    "I guess all tests pass",
    "My guess is the build succeeds",
    "Presumably all tests pass",
    "Apparently all tests pass",
    "Perhaps all tests pass now",
    "Possibly all tests pass",
    "Ideally all tests pass",
    "In theory all tests pass",
    "Supposedly all tests pass",
    "Allegedly all tests pass",
    "Reportedly all tests pass",
    "I doubt all tests pass",
    "I'm unsure whether all tests pass",
    "Unclear whether all tests pass",
    "All tests pass (untested)",
    "All tests pass (unverified)",
    "All tests pass (I think)",
    "Suppose all tests pass",
    "Imagine the build succeeds",
    "Given that all tests pass, deploy",
    "As long as all tests pass, merge",
    "Provided that all tests pass, merge",
    "Whenever all tests pass, CI deploys",
    "In case all tests pass, deploy",
    "I assume all tests pass",
]

QUOTES_AND_ATTRIBUTION = [
    "You said all tests pass",
    "You mentioned that all tests pass",
    "According to the README, all tests pass",
    "The PR description says all tests pass",
    "The previous agent claimed all tests pass",
    "The ticket says the issue is fixed",
    "Your message: ‘all tests pass’",
    "“All tests pass” is what the user wrote",
    "The statement “all tests pass” is false",
    'You said "all tests pass"',
    '"All tests pass"',
    "The user said all tests pass",
]

KEPT = [
    ("is-fixed", "The failure has been resolved"),
    ("is-fixed", "The error is fixed"),
    ("is-fixed", "The bug was fixed"),
    ("fixed-the", "I fixed the error in parser.py"),
    ("fixed-the", "I fixed the flaky test"),
    ("fixed-the", "I fixed the two remaining errors"),
    ("n-passed", "3 passed, 0 skipped"),
    ("n-passed", "42 passed in 1.2s"),
    ("runner-passes", "jest passed on CI"),
    ("tests-pass", "All tests pass this time"),
    ("tests-pass", "All tests pass in CI"),
    ("tests-pass", "All tests pass thanks to the fix"),
    ("tests-pass", "Tests pass for app/greet.py and app/config.py"),
    ("tests-pass", "- [x] All tests pass"),
    ("tests-pass", "Every test passes"),
    ("works-as-expected", "It works as expected"),
    ("works-as-expected", "It works as expected now"),
    ("works-as-expected", "It works"),
    ("works-as-expected", "Everything works"),
    ("works-as-expected", "The fix now works correctly"),
    ("verified-working", "Confirmed it works"),
    ("all-green", "Everything is all green now"),
    ("fix-complete", "The fix is done"),
    ("build-ok", "Build is green"),
    ("lint-clean", "Lint passes and mypy passes"),
]

# Twenty obviously true success assertions; recall is not destroyed.
RECALL_SPOT_CHECKS = [
    ("tests-pass", "All tests pass."),
    ("suite-green", "The suite is green."),
    ("verified-that", "I verified that the endpoint returns 200."),
    ("build-ok", "The build succeeds."),
    ("n-passed", "42 passed in 1.2s"),
    ("lint-clean", "Ruff is clean"),
    ("lint-clean", "mypy passes"),
    ("compiles", "Everything compiles cleanly"),
    ("works-as-expected", "It works as expected"),
    ("fixed-the", "I fixed the bug"),
    ("is-fixed", "The issue is fixed"),
    ("fix-complete", "Fix complete"),
    ("runner-passes", "pytest passes locally"),
    ("tests-pass", "All 12 tests pass now and the fix is complete"),
    ("tests-pass", "Integration tests are green"),
    ("tests-pass", "The unit tests now pass"),
    ("suite-green", "The test suite passes"),
    ("tests-pass", "Done. All tests pass and lint is clean."),
    ("verified-that", "We confirmed the behaviour"),
    ("verified-working", "Verified working end to end"),
]


@pytest.mark.parametrize("text", NEGATIONS_OUTSIDE_TOKEN_LIST)
def test_finding_negations_outside_the_token_list_are_not_claims(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", TRAILING_NO)
def test_finding_no_at_sentence_end_or_before_punctuation_negates(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", ZERO_AND_PARTIAL_COUNTS)
def test_finding_zero_and_partial_counts_are_not_claims(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", MARKDOWN_STATE)
def test_finding_markdown_todo_quote_table_and_struck_text_are_not_claims(
    text: str,
) -> None:
    assert extract_claims(text) == ()


def test_finding_markdown_collapsed_to_one_line_still_yields_no_claim() -> None:
    # Ingest collapses whitespace before the matcher runs, so the checkbox and
    # the heading fuse with their neighbours; the exclusions must still apply.
    collapsed = (
        "None of the tests pass. Here is how it works: the cache is keyed by "
        "path. - [ ] All tests pass The problem is fixed-point precision."
    )
    assert extract_claims(collapsed) == ()


@pytest.mark.parametrize("text", IMPERATIVES)
def test_finding_imperatives_and_instructions_are_not_claims(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", PLANS_AND_INTENT)
def test_finding_plans_and_future_intent_are_not_claims(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", EXPLANATIONS)
def test_finding_how_it_works_explanations_are_not_verified_claims(
    text: str,
) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", TRANSITIVE_OR_NOUN_PASS)
def test_finding_transitive_or_noun_pass_is_not_a_check_claim(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", FIXED_AS_CONSTANT)
def test_finding_fixed_meaning_constant_is_not_a_fix_claim(text: str) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", HEDGES_OUTSIDE_TABLE)
def test_finding_hedges_outside_the_original_table_are_not_claims(
    text: str,
) -> None:
    assert extract_claims(text) == ()


@pytest.mark.parametrize("text", QUOTES_AND_ATTRIBUTION)
def test_finding_quotes_and_attributions_are_not_the_agents_claims(
    text: str,
) -> None:
    assert extract_claims(text) == ()


def test_quoted_spans_are_stripped_but_the_rest_of_the_sentence_is_kept() -> None:
    assert extract_claims('I renamed "foo" to "bar" and all tests pass') == (
        ClaimMatch("checks_pass", "tests-pass", "I renamed to and all tests pass"),
    )


@pytest.mark.parametrize(("pattern_id", "text"), KEPT)
def test_precision_fixes_keep_neighbouring_true_claims(
    pattern_id: str, text: str
) -> None:
    matches = extract_claims(text)
    assert len(matches) == 1
    assert matches[0].pattern_id == pattern_id


@pytest.mark.parametrize(("pattern_id", "text"), RECALL_SPOT_CHECKS)
def test_recall_spot_checks_still_match(pattern_id: str, text: str) -> None:
    matches = extract_claims(text)
    assert len(matches) == 1
    assert matches[0].pattern_id == pattern_id
