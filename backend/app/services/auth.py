"""Verification of Supabase access tokens.

The rule this module exists to enforce: **the authenticated user is derived
from a cryptographically verified token, never from anything the client says
about itself.** No endpoint accepts a user id in a body, a query string or a
header.

Two verification paths are supported, because Supabase projects come in two
flavours:

1. **Legacy HS256** — the project has a shared JWT secret. Verified locally
   with that secret. No network call.
2. **Asymmetric (RS256/ES256)** — the project publishes a JWKS document.
   The key set is fetched once and cached, then used to verify locally.

Both verify signature, expiry and audience. A token that fails any check is
rejected; there is no "trust it anyway" branch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.app.config import settings

# PyJWT is required for the private workspace but not for the public demo, so
# the import is soft: a deployment without it still serves the demo and returns
# a clear error from the private routes.
try:  # pragma: no cover - exercised by whether the package is installed
    import jwt
    from jwt import PyJWKClient

    _JWT_AVAILABLE = True
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore[assignment]
    PyJWKClient = None  # type: ignore[assignment]
    _JWT_AVAILABLE = False


class AuthError(Exception):
    """Any failure to establish who the caller is.

    Carries an HTTP status so routes can translate it without re-deciding:
    401 for "you are not authenticated", 503 for "this server cannot check".
    """

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AuthUser:
    """The verified caller. Every field comes from signed token claims."""

    id: str
    email: str | None
    role: str | None
    # The raw token, forwarded to Supabase so PostgREST and Storage apply this
    # user's RLS policies rather than the API acting as a privileged client.
    token: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "email": self.email, "role": self.role}


# --------------------------------------------------------------------------
# JWKS cache
# --------------------------------------------------------------------------
_jwk_client: Any = None


def _jwks_client() -> Any:
    """Return a cached PyJWKClient for the project's JWKS endpoint."""
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(
            f"{settings.supabase_auth_url}/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwk_client


def reset_jwks_cache() -> None:
    """Drop the cached key set. Used by tests."""
    global _jwk_client
    _jwk_client = None


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
def extract_bearer_token(authorization: str | None) -> str:
    """Pull the token out of an Authorization header, or fail cleanly."""
    if not authorization:
        raise AuthError("Missing Authorization header.")

    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthError("Authorization header must be 'Bearer <token>'.")

    return parts[1].strip()


def verify_token(token: str) -> AuthUser:
    """Verify a Supabase access token and return the user it identifies.

    Raises `AuthError` for every failure mode. The message is safe to return to
    the client: it never contains the token or any key material.
    """
    if not _JWT_AVAILABLE:
        raise AuthError(
            "Token verification is unavailable because PyJWT is not installed. "
            "Install it with: pip install 'pyjwt[crypto]'",
            status_code=503,
        )

    # Built-in accounts sign their own tokens. The same rule holds: the user is
    # taken from a verified signature, never from anything the client asserts.
    if settings.resolved_auth_mode == "local":
        from backend.app.services import local_auth

        try:
            claims = local_auth.verify_local_token(token)
        except local_auth.LocalAuthError as exc:
            raise AuthError(str(exc), exc.status_code) from exc
        return AuthUser(
            id=str(claims["sub"]),
            email=claims.get("email"),
            role=claims.get("role"),
            token=token,
        )

    if not settings.supabase_configured:
        raise AuthError(
            "The private workspace is not configured on this server.",
            status_code=503,
        )

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:  # noqa: BLE001 - any malformed token lands here
        raise AuthError("Malformed access token.") from exc

    algorithm = header.get("alg", "")
    options = {"require": ["exp", "sub"], "verify_aud": bool(settings.supabase_jwt_audience)}

    try:
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthError(
                    "This server has no SUPABASE_JWT_SECRET, so HS256 tokens "
                    "cannot be verified.",
                    status_code=503,
                )
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience or None,
                options=options,
            )
        elif algorithm in ("RS256", "ES256"):
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=settings.supabase_jwt_audience or None,
                options=options,
            )
        else:
            raise AuthError(f"Unsupported token algorithm '{algorithm}'.")
    except AuthError:
        raise
    except Exception as exc:  # noqa: BLE001
        # Deliberately generic: distinguishing "expired" from "bad signature"
        # to an unauthenticated caller tells an attacker more than it helps.
        raise AuthError("Invalid or expired access token.") from exc

    subject = claims.get("sub")
    if not subject:
        raise AuthError("Access token has no subject claim.")

    # PyJWT checks exp already; this guards a token with a missing or absurd
    # expiry that still satisfied the require list.
    expiry = claims.get("exp")
    if isinstance(expiry, (int, float)) and expiry < time.time():
        raise AuthError("Access token has expired.")

    return AuthUser(
        id=str(subject),
        email=claims.get("email"),
        role=claims.get("role"),
        token=token,
    )


def user_from_header(authorization: str | None) -> AuthUser:
    """Convenience wrapper: header in, verified user out."""
    return verify_token(extract_bearer_token(authorization))
