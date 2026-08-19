from .model import Status
from .redact import redact_note
from .render_json import render_json
from .render_markdown import render_markdown


def summary(status: Status) -> str:
    return f"{status.service}: {status.state}"


def format_status(status: Status, output_format: str) -> str:
    safe = Status(status.service, status.state, redact_note(status.note))
    if output_format == "json":
        return render_json(safe)
    if output_format == "markdown":
        return render_markdown(safe)
    raise ValueError("output format must be json or markdown")
