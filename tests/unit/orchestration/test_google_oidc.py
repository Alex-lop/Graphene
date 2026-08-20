from __future__ import annotations

from collections.abc import Mapping

import pytest
from google.oauth2 import id_token
from starlette.requests import Request

from graphene.orchestration.google_oidc import (
    GoogleOidcExecutorVerifier,
    GoogleOidcVerificationError,
)

AUDIENCE = "https://coordinator.example.run.app"
TOKEN = "header.payload.signature"


def request_with_headers(*headers: tuple[bytes, bytes]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/missions/mission_1/claims",
            "headers": list(headers),
        }
    )


def test_google_oidc_verifier_binds_verified_subject_server_side():
    captured = {}

    def verify(token, request, *, audience, clock_skew_in_seconds):
        captured.update(
            token=token,
            request=request,
            audience=audience,
            clock_skew_in_seconds=clock_skew_in_seconds,
        )
        return {
            "iss": "https://accounts.google.com",
            "aud": AUDIENCE,
            "exp": 1_800_000_000,
            "sub": "google-subject-1",
            "email": "ignored@example.invalid",
        }

    verifier = GoogleOidcExecutorVerifier(
        AUDIENCE,
        {"google-subject-1": "executor_private_1"},
        token_verifier=verify,
        clock=lambda: 1_700_000_000,
    )
    identity = verifier(
        request_with_headers((b"authorization", f"Bearer {TOKEN}".encode()))
    )

    assert identity.model_dump() == {
        "principal": "google:google-subject-1",
        "executor_id": "executor_private_1",
    }
    assert captured["token"] == TOKEN
    assert captured["audience"] == AUDIENCE
    assert captured["clock_skew_in_seconds"] == 0
    assert captured["request"] is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://issuer.example.invalid"},
        {"aud": "https://other.example.run.app"},
        {"exp": 1_699_999_999},
        {"exp": True},
        {"sub": "unmapped-subject"},
    ],
)
def test_google_oidc_verifier_rejects_untrusted_claims(
    overrides: Mapping[str, object],
):
    claims = {
        "iss": "accounts.google.com",
        "aud": AUDIENCE,
        "exp": 1_800_000_000,
        "sub": "google-subject-1",
        **overrides,
    }
    verifier = GoogleOidcExecutorVerifier(
        AUDIENCE,
        {"google-subject-1": "executor_private_1"},
        token_verifier=lambda *_args, **_kwargs: claims,
        clock=lambda: 1_700_000_000,
    )

    with pytest.raises(
        GoogleOidcVerificationError, match="coordinator authentication failed"
    ):
        verifier(
            request_with_headers((b"authorization", f"Bearer {TOKEN}".encode()))
        )


@pytest.mark.parametrize(
    "headers",
    [
        (),
        ((b"authorization", b"Basic opaque"),),
        ((b"authorization", b"Bearer not-a-jwt"),),
        (
            (b"authorization", f"Bearer {TOKEN}".encode()),
            (b"authorization", f"Bearer {TOKEN}".encode()),
        ),
        ((b"authorization", b"Bearer " + b"a" * 8192),),
    ],
)
def test_google_oidc_verifier_rejects_ambiguous_or_unbounded_headers(headers):
    verifier = GoogleOidcExecutorVerifier(
        AUDIENCE,
        {"google-subject-1": "executor_private_1"},
        token_verifier=lambda *_args, **_kwargs: pytest.fail(
            "malformed credentials must not reach token verification"
        ),
    )

    with pytest.raises(GoogleOidcVerificationError):
        verifier(request_with_headers(*headers))


def test_google_oidc_configuration_is_bounded_and_defaults_to_official_verifier():
    verifier = GoogleOidcExecutorVerifier(
        AUDIENCE, {"google-subject-1": "executor_private_1"}
    )
    assert verifier._token_verifier is id_token.verify_oauth2_token

    with pytest.raises(ValueError, match="HTTPS service origin"):
        GoogleOidcExecutorVerifier(
            "http://coordinator.invalid",
            {"google-subject-1": "executor_private_1"},
        )
    with pytest.raises(ValueError, match="between 1 and 64"):
        GoogleOidcExecutorVerifier(AUDIENCE, {})
