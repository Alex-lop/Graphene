"""Time between two log timestamps."""

from datetime import datetime


def elapsed(start, end):
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
