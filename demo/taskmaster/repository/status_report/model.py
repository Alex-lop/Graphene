from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Status:
    service: str
    state: str
    note: str
