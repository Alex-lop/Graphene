from status_report import Status
from status_report.cli import summary


def test_summary() -> None:
    assert summary(Status("api", "healthy", "ready")) == "api: healthy"
