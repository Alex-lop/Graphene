from status_report.redact import redact_note


def test_redacts_secret_bearing_notes() -> None:
    assert redact_note("token=do-not-show") == "[redacted]"
    assert redact_note("retrying") == "retrying"
