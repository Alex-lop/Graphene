from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

from .cloud_protocol import AuthenticatedExecutor

_AUTHORIZATION = re.compile(r"^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$", re.I)
_GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
_MAX_AUTHORIZATION_BYTES = 8192
_MAX_BINDINGS = 64


class GoogleOidcVerificationError(ValueError):
    """A Google identity token did not authorize an executor."""


TokenVerifier = Callable[..., Mapping[str, Any]]


class GoogleOidcExecutorVerifier:
    """Verify a Google OIDC token and bind its subject to a configured executor.

    The immutable Google ``sub`` claim is the only mapping key. Email addresses and
    executor identifiers supplied by clients are never identity inputs.
    """

    def __init__(
        self,
        audience: str,
        executor_bindings: Mapping[str, str],
        *,
        token_verifier: TokenVerifier = id_token.verify_oauth2_token,
        clock: Callable[[], float] = time.time,
    ) -> None:
        parsed = urlsplit(audience)
        if (
            len(audience) > 512
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("audience must be an HTTPS service origin")
        if (
            not isinstance(executor_bindings, Mapping)
            or not 1 <= len(executor_bindings) <= _MAX_BINDINGS
        ):
            raise ValueError("executor bindings must contain between 1 and 64 subjects")

        normalized: dict[str, str] = {}
        for subject, executor_id in executor_bindings.items():
            if (
                not isinstance(subject, str)
                or not subject
                or subject != subject.strip()
                or len(subject) > 249
                or any(character.isspace() for character in subject)
            ):
                raise ValueError("executor binding contains an invalid Google subject")
            identity = AuthenticatedExecutor(
                principal=f"google:{subject}", executor_id=executor_id
            )
            normalized[subject] = identity.executor_id

        self.audience = audience
        self._bindings = normalized
        self._token_verifier = token_verifier
        self._clock = clock

    def __call__(self, request: Request) -> AuthenticatedExecutor:
        values = request.headers.getlist("authorization")
        if len(values) != 1 or len(values[0].encode("utf-8")) > _MAX_AUTHORIZATION_BYTES:
            raise GoogleOidcVerificationError("coordinator authentication failed")
        match = _AUTHORIZATION.fullmatch(values[0])
        if match is None:
            raise GoogleOidcVerificationError("coordinator authentication failed")

        try:
            claims = self._token_verifier(
                match.group(1),
                GoogleAuthRequest(),
                audience=self.audience,
                clock_skew_in_seconds=0,
            )
        except Exception as error:
            raise GoogleOidcVerificationError(
                "coordinator authentication failed"
            ) from error

        if not isinstance(claims, Mapping):
            raise GoogleOidcVerificationError("coordinator authentication failed")

        issuer = claims.get("iss")
        audience = claims.get("aud")
        expires_at = claims.get("exp")
        subject = claims.get("sub")
        if (
            issuer not in _GOOGLE_ISSUERS
            or audience != self.audience
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, (int, float))
            or expires_at <= self._clock()
            or not isinstance(subject, str)
            or subject not in self._bindings
        ):
            raise GoogleOidcVerificationError("coordinator authentication failed")
        return AuthenticatedExecutor(
            principal=f"google:{subject}", executor_id=self._bindings[subject]
        )


__all__ = [
    "GoogleOidcExecutorVerifier",
    "GoogleOidcVerificationError",
]
