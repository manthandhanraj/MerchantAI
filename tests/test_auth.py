"""Access-token verification.

The property being protected: an endpoint's idea of who is calling comes from a
signature it checked, and from nothing else. These tests try the ways a caller
might attempt to be someone they are not.
"""

from __future__ import annotations

import time

import jwt
import pytest

from backend.app.config import settings
from backend.app.services import auth

SECRET = "test-jwt-secret-value-not-a-real-one"
USER = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """Pretend this deployment has a Supabase project with an HS256 secret."""
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    auth.reset_jwks_cache()


def make_token(**overrides) -> str:
    claims = {
        "sub": USER,
        "email": "owner@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        **overrides,
    }
    return jwt.encode(claims, overrides.pop("_secret", SECRET), algorithm="HS256")


# ---------------------------------------------------------------- headers
def test_missing_header_is_rejected():
    with pytest.raises(auth.AuthError) as caught:
        auth.extract_bearer_token(None)
    assert caught.value.status_code == 401


@pytest.mark.parametrize(
    "header",
    ["", "token-only", "Basic abc123", "Bearer", "Bearer   "],
)
def test_malformed_authorization_headers_are_rejected(header):
    with pytest.raises(auth.AuthError):
        auth.extract_bearer_token(header)


def test_bearer_token_is_extracted_case_insensitively():
    assert auth.extract_bearer_token("bearer abc.def.ghi") == "abc.def.ghi"


# ---------------------------------------------------------------- tokens
def test_valid_token_identifies_the_user():
    user = auth.verify_token(make_token())
    assert user.id == USER
    assert user.email == "owner@example.com"
    # The raw token is carried so downstream calls run as this user.
    assert user.token


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode({"sub": USER, "aud": "authenticated", "exp": int(time.time()) + 60},
                        "attacker-secret", algorithm="HS256")
    with pytest.raises(auth.AuthError):
        auth.verify_token(forged)


def test_expired_token_is_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify_token(make_token(exp=int(time.time()) - 10))


def test_token_without_subject_is_rejected():
    token = jwt.encode(
        {"aud": "authenticated", "exp": int(time.time()) + 60}, SECRET, algorithm="HS256"
    )
    with pytest.raises(auth.AuthError):
        auth.verify_token(token)


def test_token_for_another_audience_is_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify_token(make_token(aud="some-other-service"))


def test_unsigned_token_is_rejected():
    """The `alg: none` attack: a token with no signature must never verify."""
    unsigned = jwt.encode(
        {"sub": USER, "aud": "authenticated", "exp": int(time.time()) + 60},
        key="",
        algorithm="none",
    )
    with pytest.raises(auth.AuthError):
        auth.verify_token(unsigned)


def test_garbage_token_is_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify_token("not-a-jwt-at-all")


def test_error_message_never_leaks_the_secret_or_the_token():
    try:
        auth.verify_token(make_token(_secret="wrong-secret"))
    except auth.AuthError as exc:
        message = str(exc)
        assert SECRET not in message
        assert "eyJ" not in message  # no base64 JWT fragment
    else:  # pragma: no cover
        pytest.fail("expected AuthError")


def test_supabase_mode_without_a_project_reports_503(monkeypatch):
    """Explicitly asking for Supabase with no project is a server fault: 503."""
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    with pytest.raises(auth.AuthError) as caught:
        auth.verify_token(make_token())
    assert caught.value.status_code == 503


def test_no_project_falls_back_to_built_in_accounts(monkeypatch):
    """With no Supabase project, built-in accounts take over.

    A token signed with the Supabase secret is not a built-in token, so it is
    refused as unauthenticated rather than trusted.
    """
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    assert settings.resolved_auth_mode == "local"
    with pytest.raises(auth.AuthError) as caught:
        auth.verify_token(make_token())
    assert caught.value.status_code == 401


def test_hs256_without_a_configured_secret_is_not_trusted(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    with pytest.raises(auth.AuthError) as caught:
        auth.verify_token(make_token())
    assert caught.value.status_code == 503


def test_user_from_header_round_trip():
    user = auth.user_from_header(f"Bearer {make_token()}")
    assert user.id == USER
