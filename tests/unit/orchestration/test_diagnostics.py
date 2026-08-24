from __future__ import annotations

import hashlib

from graphene.orchestration.diagnostics import CheckDiagnostic, summarize_check_failure

_PYTEST_FAILURES = """\
FF                                                                       [100%]
=================================== FAILURES ===================================
_______________________ test_quantities_match_balances ________________________
E       AssertionError: assert 3 == 4
=========================== short test summary info ============================
FAILED tests/test_report_json.py::test_quantities_match_balances - AssertionError: assert 3 == 4
FAILED tests/test_report_json.py::test_totals - AssertionError
2 failed, 5 passed in 0.42s
"""

_COLLECTION_ERROR = """\
=================================== ERRORS ====================================
E   ModuleNotFoundError: No module named 'ledger_service.report_json'
=========================== short test summary info ===========================
ERROR tests/test_x.py
!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!
1 error in 0.12s
"""


def _diag(
    output: str,
    *,
    exit_code: int = 1,
    timed_out: bool = False,
    output_truncated: bool = False,
    cleanup_complete: bool = True,
) -> CheckDiagnostic:
    return summarize_check_failure(
        output,
        exit_code=exit_code,
        timed_out=timed_out,
        output_truncated=output_truncated,
        cleanup_complete=cleanup_complete,
        output_sha256=hashlib.sha256(output.encode()).hexdigest(),
        output_byte_count=len(output.encode()),
    )


def test_pytest_failure_block_yields_sorted_nodeids_and_checks_failed() -> None:
    diagnostic = _diag(_PYTEST_FAILURES)
    assert diagnostic.failure_class == "checks_failed"
    assert diagnostic.failed_check_names == (
        "tests/test_report_json.py::test_quantities_match_balances",
        "tests/test_report_json.py::test_totals",
    )
    assert all(" - " not in name for name in diagnostic.failed_check_names)
    assert "2 failed, 5 passed" in diagnostic.summary
    assert len(diagnostic.summary) <= 1200


def test_collection_error_is_classified_before_checks_failed() -> None:
    diagnostic = _diag(_COLLECTION_ERROR, exit_code=2)
    assert diagnostic.failure_class == "collection_error"
    assert diagnostic.failed_check_names == ("tests/test_x.py",)
    assert "ERROR tests/test_x.py" in diagnostic.summary


def test_timeout_outranks_everything_else() -> None:
    diagnostic = _diag(_PYTEST_FAILURES, exit_code=124, timed_out=True, output_truncated=True)
    assert diagnostic.failure_class == "timed_out"


def test_truncation_outranks_content_parsing() -> None:
    diagnostic = _diag(_PYTEST_FAILURES, output_truncated=True)
    assert diagnostic.failure_class == "output_truncated"


def test_clean_nonzero_exit_with_unparseable_output_is_unclean_exit() -> None:
    diagnostic = _diag("Segmentation fault (core dumped)\n", exit_code=139)
    assert diagnostic.failure_class == "unclean_exit"
    assert diagnostic.failed_check_names == ()
    assert diagnostic.exit_code == 139


def test_secret_shaped_token_does_not_survive_into_summary() -> None:
    secret = "sk-" + "a" * 32
    diagnostic = _diag(f"E   RuntimeError: token API_KEY={secret} rejected\n1 failed in 0.1s\n")
    assert secret not in diagnostic.summary
    assert "<redacted>" in diagnostic.summary


def test_absolute_path_does_not_survive_into_summary() -> None:
    diagnostic = _diag("E   AssertionError: wrote /Users/alex/repo/artifacts/out.json unexpectedly\n")
    assert "/Users/alex" not in diagnostic.summary
    assert "out.json" in diagnostic.summary


def test_signature_ignores_timing_noise_and_digests() -> None:
    first = _diag(_PYTEST_FAILURES)
    second = _diag(_PYTEST_FAILURES.replace("in 0.42s", "in 9.99s"))
    assert first.output_sha256 != second.output_sha256
    assert first.summary != second.summary
    assert first.signature() == second.signature()


def test_signature_differs_when_the_failure_differs() -> None:
    assert _diag(_PYTEST_FAILURES).signature() != _diag("boom\n", exit_code=139).signature()


def test_never_raises_on_empty_input() -> None:
    diagnostic = _diag("")
    assert diagnostic.failure_class == "unclean_exit"
    assert diagnostic.failed_check_names == ()
    assert diagnostic.summary == ""


def test_never_raises_on_megabytes_of_junk() -> None:
    line = "FAILED " + "x" * 500 + " - \x00\x1b[31m junk\n"
    junk = line * (5 * 1024 * 1024 // len(line))
    diagnostic = _diag(junk, exit_code=2)
    assert isinstance(diagnostic, CheckDiagnostic)
    assert len(diagnostic.failed_check_names) <= 8
    assert all(len(name) <= 200 for name in diagnostic.failed_check_names)
    assert len(diagnostic.summary) <= 1200
    binary_blob = ("\x00\xff\ufeff" + "A" * 61) * (2 * 1024 * 1024 // 64)
    assert isinstance(_diag(binary_blob, exit_code=137), CheckDiagnostic)
