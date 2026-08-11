from app.config import RATE_LIMIT_ENABLED

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60


def should_block(attempts: int, elapsed_seconds: int) -> bool:
    return (
        RATE_LIMIT_ENABLED
        and attempts >= MAX_ATTEMPTS
        and elapsed_seconds <= WINDOW_SECONDS
    )
