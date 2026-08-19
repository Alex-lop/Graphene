from .model import Status


def render_markdown(status: Status) -> str:
    return f"| {status.service} | {status.state} | {status.note} |"
