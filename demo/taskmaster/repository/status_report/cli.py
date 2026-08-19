from .model import Status


def summary(status: Status) -> str:
    return f"{status.service}: {status.state}"
