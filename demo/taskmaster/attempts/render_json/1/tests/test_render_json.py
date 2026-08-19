from status_report import Status
from status_report.render_json import render_json


def test_renders_canonical_json() -> None:
    assert render_json(Status("api", "healthy", "ready")) == (
        '{"note":"ready","service":"api","state":"healthy"}'
    )
