_SECRET_MARKERS = ("api_key=", "password=", "token=")


def redact_note(note: str) -> str:
    lowered = note.lower()
    return "[redacted]" if any(marker in lowered for marker in _SECRET_MARKERS) else note
