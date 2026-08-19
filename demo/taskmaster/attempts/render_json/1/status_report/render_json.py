import json

from .model import Status


def render_json(status: Status) -> str:
    return json.dumps(
        {"note": status.note, "service": status.service, "state": status.state},
        separators=(",", ":"),
        sort_keys=True,
    )
