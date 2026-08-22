import pytest

from ledger_service.models import Movement
from ledger_service.redact import (
    RedactionPolicy,
    is_sensitive,
    redact_movement,
    redact_movements,
    redact_text,
)

T = "2024-05-01T10:00:00+00:00"


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


def test_is_sensitive() -> None:
    assert is_sensitive("password=x")
    assert not is_sensitive("plain")


def test_redact_movement_returns_same_object_when_clean() -> None:
    movement = Movement("m1", "BOLT-M8", "receipt", 1, T, note="clean")
    assert redact_movement(movement) is movement


def test_redact_movement_replaces_note_only() -> None:
    movement = Movement("m1", "BOLT-M8", "receipt", 1, T, note="password=x")
    redacted = redact_movement(movement)
    assert redacted.note == "password=[REDACTED]"
    assert redacted.movement_id == movement.movement_id
    assert movement.note == "password=x"


def test_redact_movements_keeps_order() -> None:
    movements = [
        Movement("m2", "BOLT-M8", "receipt", 1, T, note="b@example.com"),
        Movement("m1", "BOLT-M8", "receipt", 1, T, note="fine"),
    ]
    redacted = redact_movements(movements)
    assert [(m.movement_id, m.note) for m in redacted] == [("m2", "[REDACTED]"), ("m1", "fine")]
