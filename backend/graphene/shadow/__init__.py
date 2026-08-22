"""Shadow Agent: observe a finished agent session, reconstruct it, lint it.

Shadow data is a reconstruction of work Graphene did not govern. It lives in
its own store and is never cited by mission evidence. See docs/SHADOW.md.
"""

from .events import (
    SHADOW_EVENT_SCHEMA,
    ShadowClaim,
    ShadowEvent,
    ShadowSource,
    canonical_event_bytes,
    event_id_for,
    session_sha256,
)

__all__ = [
    "SHADOW_EVENT_SCHEMA",
    "ShadowClaim",
    "ShadowEvent",
    "ShadowSource",
    "canonical_event_bytes",
    "event_id_for",
    "session_sha256",
]
