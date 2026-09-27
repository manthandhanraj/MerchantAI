"""HTTP behaviour of the private API.

These test the edge the browser actually touches: what status an unauthenticated
or wrongly-authenticated request gets, and that the public demo endpoints are
untouched by any of it.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app
from backend.app.services import auth

SECRET = "api-test-secret-value"
USER = "11111111-1111-4111-8111-111111111111"

PRIVATE_GETS = [
    "/api/me",
    "/api/my/merchants",
    "/api/my/assistant/status",
    f"/api/my/merchants/{USER}",
    f"/api/my/merchants/{USER}/uploads",
    f"/api/my/merchants/{USER}/analyses",
    f"/api/my/merchants/{USER}/dashboard",
    f"/api/my/merchants/{USER}/insights",
    f"/api/my/merchants/{USER}/action-plan",
    f"/api/my/merchants/{USER}/forecast",
    f"/api/my/merchants/{USER}/reports",
]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    auth.reset_jwks_cache()


def token(**overrides) -> str:
    return jwt.encode(
        {
            "sub": USER,
            "email": "owner@example.com",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
            **overrides,
        },
        SECRET,
        algorithm="HS256",
    )


# ---------------------------------------------------------------- no token
@pytest.mark.parametrize("path", PRIVATE_GETS)
def test_private_routes_require_a_token(client, configured, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert isinstance(response.json()["detail"], str)


def test_private_post_routes_require_a_token(client, configured):
    assert client.post("/api/my/merchants", json={"name": "Shop"}).status_code == 401
    assert (
        client.post(f"/api/my/merchants/{USER}/analyses", json={}).status_code == 401
    )
    assert (
        client.post(
            f"/api/my/merchants/{USER}/assistant/ask", json={"question": "hi"}
        ).status_code
        == 401
    )


# ---------------------------------------------------------------- bad token
@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-jwt",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "token abc",
    ],
)
def test_malformed_credentials_are_rejected(client, configured, header):
    response = client.get("/api/me", headers={"Authorization": header})
    assert response.status_code == 401


def test_expired_token_is_rejected(client, configured):
    response = client.get(
        "/api/me", headers={"Authorization": f"Bearer {token(exp=int(time.time()) - 5)}"}
    )
    assert response.status_code == 401


def test_token_signed_by_someone_else_is_rejected(client, configured):
    forged = jwt.encode(
        {"sub": USER, "aud": "authenticated", "exp": int(time.time()) + 60},
        "attacker-secret",
        algorithm="HS256",
    )
    response = client.get("/api/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_error_body_is_json_and_carries_no_stack_trace(client, configured):
    response = client.get("/api/me", headers={"Authorization": "Bearer broken"})
    body = response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "Traceback" not in body
    assert "File \"" not in body


# ------------------------------------------------------- not configured
def test_supabase_mode_without_a_project_reports_503(client, monkeypatch):
    """Forcing Supabase with no project configured is reported, not hidden."""
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 503


def test_without_a_project_a_foreign_token_is_refused(client, monkeypatch):
    """Built-in accounts take over, and a token they did not sign gets 401."""
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 401


def test_health_reports_which_account_system_is_live(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    body = client.get("/api/health").json()
    assert body["auth_mode"] == "local"
    # Accounts work either way now.
    assert body["workspace_enabled"] is True

    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    body = client.get("/api/health").json()
    assert body["auth_mode"] == "supabase"
    assert body["workspace_enabled"] is True


# ------------------------------------------------- the public demo is intact
@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/merchants",
        "/api/dataset/summary",
        "/api/dataset/validation",
        "/api/dashboard?merchant_id=M001",
        "/api/insights?merchant_id=M001",
        "/api/recommendations?merchant_id=M001",
        "/api/action-plan?merchant_id=M001",
        "/api/forecast?merchant_id=M001",
        "/api/assistant/status",
    ],
)
def test_public_demo_endpoints_still_work_without_a_token(client, path):
    response = client.get(path)
    assert response.status_code == 200


def test_public_assistant_still_answers_without_a_token(client):
    response = client.post(
        "/api/assistant/ask",
        json={"merchant_id": "M001", "question": "What should I focus on today?"},
    )
    assert response.status_code == 200
    assert response.json()["answer"]
