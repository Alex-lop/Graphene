from status_report import Status
from status_report.render_markdown import render_markdown


def test_escapes_markdown_table_delimiters() -> None:
    assert render_markdown(Status("api", "degraded", "slow | retrying")) == (
        r"| api | degraded | slow \| retrying |"
    )
