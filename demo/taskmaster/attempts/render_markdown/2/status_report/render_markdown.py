from .model import Status


def render_markdown(status: Status) -> str:
    cells = (status.service, status.state, status.note)
    return "| " + " | ".join(cell.replace("|", r"\|") for cell in cells) + " |"
