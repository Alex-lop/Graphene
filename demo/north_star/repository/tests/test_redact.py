import pytest

from ledger_service.redact import RedactionPolicy, redact_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("contact ops@example.com today", "contact [REDACTED] today"),
        ("token=abc123XYZ ok", "token=[REDACTED] ok"),
        ("api_key: sk-live-0001", "api_key: [REDACTED]"),
        ("API-KEY = value", "API-KEY = [REDACTED]"),
        ("password hunter2", "password hunter2"),
        ("Bearer abcdefghij.klmnop", "Bearer [REDACTED]"),
        ("digest 0123456789abcdef0123456789abcdef", "digest [REDACTED]"),
        ("short hex 0123abcd stays", "short hex 0123abcd stays"),
        ("plain note", "plain note"),
    ],
)
def test_redact_text_default_policy(text: str, expected: str) -> None:
    assert redact_text(text) == expected


def test_policy_toggles() -> None:
    text = "mail ops@example.com token=abc"
    assert redact_text(text, RedactionPolicy(emails=False)) == "mail ops@example.com token=[REDACTED]"
    assert redact_text(text, RedactionPolicy(secrets=False)) == "mail [REDACTED] token=abc"


def test_custom_placeholder() -> None:
    assert redact_text("token=abc", RedactionPolicy(placeholder="***")) == "token=***"
