import pytest

from status_report import Status
from status_report.cli import format_status


def test_formats_and_redacts_status() -> None:
    status = Status("api", "degraded", "token=do-not-show")
    assert format_status(status, "json") == (
        '{"note":"[redacted]","service":"api","state":"degraded"}'
    )
    assert format_status(status, "markdown") == "| api | degraded | [redacted] |"


def test_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="json or markdown"):
        format_status(Status("api", "healthy", "ready"), "xml")
